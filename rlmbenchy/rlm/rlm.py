"""Core RLM loop implementation.

Implements Algorithm 1 from the RLM paper (Zhang et al., 2026):

    state <- InitREPL(prompt=P)
    state <- AddFunction(state, sub_RLM_M)
    hist  <- [Metadata(state)]
    while True do
        code             <- LLM_M(hist)
        (state, stdout)  <- REPL(state, code)
        hist             <- hist || code || Metadata(stdout)
        if state[Final] is set then return state[Final]

All logging is handled externally via runtime callbacks (e.g. ``LMLoggingCallback``).
This module has no knowledge of loggers, event streams, or console output.
"""

from __future__ import annotations

import inspect
import json
import keyword
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import dspy
import pydantic
from dspy import Signature, Tool
from dspy.adapters.utils import parse_value, serialize_for_json, translate_field_type
from dspy.primitives.code_interpreter import (
    CodeInterpreter,
    CodeInterpreterError,
    FinalOutput,
)
from dspy.primitives.repl_types import REPLHistory
from dspy.utils.exceptions import AdapterParseError

from rlmbenchy.rlm.reasoning import install_reasoning_native_allowlist_override
from rlmbenchy.rlm.repl import ReplRuntimeError
from rlmbenchy.rlm.signatures import RESERVED_RLM_PREDICTION_FIELDS
from rlmbenchy.rlm.types import StopReason

_PYTHON_FENCE_LANGS = {"python", "py", "python3", "py3", ""}
LLM_QUERY_PROMPT_CHAR_LIMIT = 20_000
MAX_CONSECUTIVE_ACTION_PARSE_FAILURES = 3
_COMPLETED_FIELD_RE = re.compile(
    r"\[\[\s*##\s*completed\s*(?:##)?\s*\]\]", re.IGNORECASE
)
_CODE_FIELD_RE = re.compile(r"^\s*\[\[\s*##\s*code\s*##\s*\]\]\s*", re.IGNORECASE)

ACTION_INSTRUCTIONS_TEMPLATE = """\
You are tasked with producing the following outputs:
{output_fields}

You have access to a Python REPL environment. Write Python code and it will be \
executed. You will see the output, then write more code based on what you learned. \
This is an iterative process.

Pre-loaded in the REPL:
- Input variables described in `variables_info` below. The metadata lists names, \
types, descriptions, and serialized lengths; the full values are loaded in the \
REPL and can be inspected from code. Input values are not shown in this prompt. \
Before printing a full input value, inspect its size and shape.
- `llm_query(prompt)` - query a sub-LLM (~{llm_query_prompt_capacity_k}K char \
capacity) for semantic analysis
  HARD LIMIT: prompt must be <= {llm_query_prompt_char_limit} characters or \
llm_query raises ValueError.
  Use llm_query after inspecting relevant evidence when you need higher-level \
semantic help.
- `print()` - print compact, targeted observations to see results. For large \
objects, print keys, counts, lengths, and short samples first instead of whole \
payloads.
- `SUBMIT({final_output_signature})` - submit final outputs when done
- Standard libraries: re, json, collections, math, etc.

IMPORTANT: This is ITERATIVE. Each code block you write will execute, you'll see \
the output, then you decide what to do next. Do NOT try to solve everything in one \
step.

1. EXPLORE FIRST - Inspect available variables before processing them. Print \
types, lengths, keys, counts, schemas, and short samples. Do not print large \
values whole.
2. ORCHESTRATE, DON'T JUST SOLVE - Use the REPL to break the task into \
deterministic checks, filtering, extraction, semantic interpretation, and final \
assembly. Keep exact values in variables and operate on them from code.
3. KEEP HISTORY SMALL - Everything you print becomes part of `repl_history`. \
Long stdout reduces future reasoning quality. Print compact observations, \
samples, summaries, and candidate answers, not full documents, full tool \
results, or large intermediate data.
4. USE PYTHON BEFORE llm_query - Use Python for exact search, counting, \
filtering, parsing, sorting, and deduplication. Call `llm_query` only after you \
have selected the relevant text or evidence that needs semantic interpretation.
5. PASS COMPLETE SUBCALL CONTEXT - `llm_query` has no access to REPL variables \
unless you include their relevant contents in the prompt. Give it focused \
inputs and ask for terse, structured outputs that can be parsed or compared in \
code.
6. RESPECT SUBCALL BUDGETS - Each `llm_query` prompt must stay under \
{llm_query_prompt_char_limit} characters, and you have at most {max_llm_calls} \
sub-LLM calls. Avoid many tiny calls. Filter or chunk in Python first, then \
query only the strongest candidates.
7. ITERATE AND VERIFY - Execute one useful code step, inspect the output, then \
decide the next step. If results are empty, surprising, or inconsistent, debug \
before finalizing. Before `SUBMIT`, check that the answer is supported by \
observed outputs.
8. SUBMIT INTENTIONALLY - `SUBMIT({final_output_signature})` ends the current \
run immediately. If you need to inspect a candidate answer, print it first and \
submit in a later step. If the iteration budget is nearly exhausted, submit the \
best supported answer instead of leaving the run without a final output.

You have max {max_llm_calls} sub-LLM calls. When done, call SUBMIT() with your \
outputs."""

EXTRACT_INSTRUCTIONS = """Based on the REPL trajectory, extract the final outputs now.

Review your trajectory to see what information you gathered and what values you computed,
then provide the final outputs."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(code: str) -> str:
    """Extract Python code from markdown fences, or return as-is if no fences."""
    code = code.strip()
    code = _CODE_FIELD_RE.sub("", code, count=1).strip()
    completed_match = _COMPLETED_FIELD_RE.search(code)
    if completed_match is not None:
        code = code[: completed_match.start()].strip()
    if "```" not in code:
        return code

    # Strip outer decorative fence pairs (e.g. ```\n```python\n...\n```\n```).
    lines = code.splitlines()
    while len(lines) >= 2 and lines[0].strip() == "```" and lines[-1].strip() == "```":
        lines.pop(0)
        lines.pop()
    code = "\n".join(lines).strip()
    if "```" not in code:
        return code

    # Find the first opening fence and ignore any prose before it.
    fence_start = code.find("```")
    lang_line, separator, remainder = code[fence_start + 3 :].partition("\n")
    if not separator:
        return code

    # Accept python-labeled fences or bare ``` fences; reject explicit non-Python tags.
    lang = (lang_line.strip().split(maxsplit=1)[0] if lang_line.strip() else "").lower()
    if lang not in _PYTHON_FENCE_LANGS:
        raise SyntaxError(
            f"Expected Python code but got ```{lang} fence. Write Python code, not {lang}."
        )

    block_end = remainder.find("```")
    if block_end == -1:
        return remainder.strip()

    return remainder[:block_end].strip()


def _normalize_optional_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    return str(value)


def _make_repl_callable(tool_name: str, tool: Tool) -> Any:
    """Wrap a DSPy Tool so it can be called naturally from REPL code."""
    try:
        sig = inspect.signature(tool.func)
    except (TypeError, ValueError):
        sig = None

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        if sig is not None:
            bound = sig.bind(*args, **kwargs)
            return tool(**dict(bound.arguments))
        if args:
            raise TypeError(
                f"Tool {tool_name!r} does not support positional arguments."
            )
        return tool(**kwargs)

    if sig is not None:
        _wrapped.__signature__ = sig  # ty: ignore[unresolved-attribute]
    return _wrapped


# ---------------------------------------------------------------------------
# Step observer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StepObserver(Protocol):
    """Hook for step lifecycle events emitted by the RLM loop."""

    def on_step_started(self, *, step_index: int, context: dict[str, Any]) -> None: ...
    def on_step_finished(self, *, step_index: int, outcome: dict[str, Any]) -> None: ...


@runtime_checkable
class _PollingProcess(Protocol):
    def poll(self) -> int | None: ...


@runtime_checkable
class _ToolRegisteringInterpreter(Protocol):
    tools: dict[str, Any]
    output_fields: list[dict[str, Any]] | None
    process: _PollingProcess | None
    _tools_registered: bool

    def _register_tools(self) -> None: ...


@dataclass(frozen=True)
class RLMRunTelemetry:
    latency_s: float
    stop_reason: str
    finalized: bool
    final_outputs: dict[str, Any] | None
    reasoning: str
    code: str
    stdout: str
    error: str | None
    trajectory: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# RLM
# ---------------------------------------------------------------------------


class RLM(dspy.Module):
    """Single-task RLM executor with a persistent REPL.

    Implements the RLM loop: call LM -> execute code in REPL -> feed output
    back -> stop on ``SUBMIT(**outputs)`` or iteration budget exhausted.
    """

    signature: type[Signature]

    def __init__(
        self,
        signature: type[Signature] | str,
        *,
        interpreter: CodeInterpreter,
        max_iterations: int = 100,
        max_llm_calls: int = 200,
        tools: list[Tool] | None = None,
        sub_lm: dspy.LM | None = None,
        step_observer: StepObserver | None = None,
    ) -> None:
        super().__init__()
        resolved_signature = dspy.ensure_signature(signature)
        if resolved_signature is None:
            raise TypeError("RLM signature could not be resolved.")
        self.signature = resolved_signature
        self.max_iterations = max_iterations
        self.max_llm_calls = int(max_llm_calls)
        if self.max_llm_calls < 0:
            raise ValueError("max_llm_calls must be >= 0.")
        self._llm_query_calls = 0
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            func_name = getattr(tool.func, "__name__", "")
            tool_name = str(tool.name or func_name or f"tool_{len(self._tools) + 1}")
            self._tools[tool_name] = tool
        self.interpreter = interpreter
        self.sub_lm = sub_lm
        self._step_observer = step_observer
        self.repl_tool = dspy.Tool(
            self._execute_in_repl,
            name="repl",
            desc="Execute Python code in the persistent REPL",
            args={"code": {"type": "string", "desc": "Python code to execute"}},
        )

        install_reasoning_native_allowlist_override()
        self._validate_signature_outputs()
        action_sig, extract_sig = self._build_signatures()
        self.generate_action = dspy.Predict(action_sig)
        self.extract = dspy.Predict(extract_sig)
        self._last_run_telemetry: RLMRunTelemetry | None = None

    @property
    def last_run_telemetry(self) -> RLMRunTelemetry | None:
        return self._last_run_telemetry

    # ------------------------------------------------------------------
    # Signature building
    # ------------------------------------------------------------------

    def _validate_inputs(self, input_args: dict[str, Any]) -> None:
        missing = set(self.signature.input_fields.keys()) - set(input_args.keys())
        if missing:
            raise ValueError(f"Missing required inputs: {sorted(missing)}")

    def _validate_signature_outputs(self) -> None:
        for name in self.signature.output_fields:
            if not name.isidentifier():
                raise ValueError(
                    f"Invalid output field name {name!r}: must be a valid Python identifier."
                )
            if keyword.iskeyword(name):
                raise ValueError(
                    f"Invalid output field name {name!r}: Python keywords are not allowed."
                )
            if name in RESERVED_RLM_PREDICTION_FIELDS:
                raise ValueError(
                    f"Invalid output field name {name!r}: reserved by RLM runtime metadata."
                )

    def _build_variables_info(self, **input_args: Any) -> list[str]:
        """Build prompt metadata for runtime input values without value previews."""
        variables_info: list[str] = []
        for name, value in input_args.items():
            field_info = self.signature.input_fields.get(name)
            jsonable = serialize_for_json(value)
            if isinstance(jsonable, (dict, list)):
                value_str = json.dumps(jsonable, indent=2)
            else:
                value_str = str(jsonable)

            lines = [f"Variable: `{name}` (access it in your code)"]
            lines.append(f"Type: {type(value).__name__}")
            schema_extra = (
                field_info.json_schema_extra if field_info is not None else None
            )
            if isinstance(schema_extra, dict):
                raw_desc = schema_extra.get("desc", "")
                if raw_desc and not str(raw_desc).startswith("${"):
                    lines.append(f"Description: {raw_desc}")
                constraints = schema_extra.get("constraints", "")
                if constraints:
                    lines.append(f"Constraints: {constraints}")
            lines.append(f"Total length: {len(value_str):,} characters")
            variables_info.append("\n".join(lines))
        return variables_info

    def _get_output_fields_info(self) -> list[dict[str, str]]:
        fields: list[dict[str, str]] = []
        for name, field in self.signature.output_fields.items():
            field_info = {"name": name}
            annotation = getattr(field, "annotation", str)
            if annotation in {str, int, float, bool, list, dict}:
                field_info["type"] = annotation.__name__
            fields.append(field_info)
        return fields

    def _build_signatures(self) -> tuple[type[Signature], type[Signature]]:
        final_output_signature = ", ".join(
            f"{name}=..." for name in self.signature.output_fields
        )
        output_fields_desc = "\n".join(
            f"- {translate_field_type(name, field)}"
            for name, field in self.signature.output_fields.items()
        )

        task_instructions = (
            f"{self.signature.instructions}\n\n" if self.signature.instructions else ""
        )
        tool_docs = self._format_tool_docs()

        instructions = (
            task_instructions
            + ACTION_INSTRUCTIONS_TEMPLATE.format(
                final_output_signature=final_output_signature,
                output_fields=output_fields_desc,
                max_llm_calls=self.max_llm_calls,
                llm_query_prompt_capacity_k=LLM_QUERY_PROMPT_CHAR_LIMIT // 1000,
                llm_query_prompt_char_limit=f"{LLM_QUERY_PROMPT_CHAR_LIMIT:,}",
            )
            + tool_docs
        )

        action_sig = dspy.make_signature({}, instructions)
        action_sig = (
            action_sig.append(
                "variables_info",
                dspy.InputField(desc="Metadata about variables pre-loaded in the REPL"),
                type_=str,
            )
            .append(
                "repl_history",
                dspy.InputField(desc="Previous REPL code executions and their outputs"),
                type_=REPLHistory,
            )
            .append(
                "iteration",
                dspy.InputField(
                    desc="Current iteration number (1-indexed) out of max_iterations"
                ),
                type_=str,
            )
            .append(
                "reasoning",
                dspy.OutputField(
                    desc="Think step-by-step: what do you know? What remains? Plan your next action."
                ),
                type_=dspy.Reasoning,
            )
            .append(
                "code",
                dspy.OutputField(
                    desc="Python code to execute. Use markdown code block format: ```python\\n<code>\\n```"
                ),
                type_=str,
            )
        )

        extract_task_instructions = (
            "The trajectory was generated with the following objective:\n"
            f"{self.signature.instructions}\n\n"
            if self.signature.instructions
            else ""
        )
        extract_fields = {
            name: (getattr(field, "annotation", str), field)
            for name, field in self.signature.output_fields.items()
        }
        extract_sig = dspy.make_signature(
            extract_fields, extract_task_instructions + EXTRACT_INSTRUCTIONS
        )
        extract_sig = extract_sig.prepend(
            "repl_history",
            dspy.InputField(desc="Your REPL interactions so far"),
            type_=REPLHistory,
        )
        extract_sig = extract_sig.prepend(
            "variables_info",
            dspy.InputField(desc="Metadata about variables pre-loaded in the REPL"),
            type_=str,
        )
        return action_sig, extract_sig

    def _format_tool_docs(self) -> str:
        if not self._tools:
            return ""
        lines = [
            "\nAdditional tools pre-loaded in the REPL (call them directly from code):"
        ]
        for tool in self._tools.values():
            params = []
            for arg_name, arg_schema in (tool.args or {}).items():
                arg_type = arg_schema.get("type", "Any")
                params.append(f"{arg_name}: {arg_type}")
            sig_str = f"{tool.name}({', '.join(params)})"
            desc = (tool.desc or "No description").replace("\n", "  ")
            lines.append(f"- `{sig_str}` - {desc}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool chain
    # ------------------------------------------------------------------

    def _llm_query_tool(self, prompt: str) -> str:
        prompt_text = str(prompt)
        if len(prompt_text) > LLM_QUERY_PROMPT_CHAR_LIMIT:
            raise ValueError(
                f"llm_query prompt too long: {len(prompt_text)} characters "
                f"(hard limit: {LLM_QUERY_PROMPT_CHAR_LIMIT})."
            )
        lm = self.sub_lm if self.sub_lm is not None else dspy.settings.lm
        if lm is None:
            raise RuntimeError(
                "No LM configured. Use dspy.configure(lm=...) or pass sub_lm to RLM."
            )
        if self._llm_query_calls >= self.max_llm_calls:
            raise RuntimeError(
                "llm_query call budget exhausted: "
                f"used {self._llm_query_calls} of {self.max_llm_calls}."
            )
        self._llm_query_calls += 1
        outputs = lm(prompt_text)
        item = outputs[0] if isinstance(outputs, list) and outputs else outputs
        if isinstance(item, dict):
            return item.get("text") or ""
        return str(item)

    def _prepare_execution_tools(self) -> dict[str, Any]:
        tools: dict[str, Any] = {
            "llm_query": _make_repl_callable(
                "llm_query",
                dspy.Tool(self._llm_query_tool, name="llm_query"),
            )
        }
        tools.update(
            {
                name: _make_repl_callable(name, tool)
                for name, tool in self._tools.items()
            }
        )
        return tools

    def _execute_in_repl(self, code: str) -> Any:
        """Thin wrapper so interpreter.execute can be called as a dspy.Tool."""
        return self.interpreter.execute(code)

    def _make_submit_tool(self) -> Any:
        def _submit(**kwargs: Any) -> Any:
            final_output_type: Any = FinalOutput
            raise final_output_type(dict(kwargs))

        return _submit

    def _inject_tools(self) -> None:
        execution_tools = self._prepare_execution_tools()
        self.interpreter.tools.update(execution_tools)
        if not isinstance(self.interpreter, _ToolRegisteringInterpreter):
            self.interpreter.tools["SUBMIT"] = self._make_submit_tool()
            return
        self.interpreter.output_fields = self._get_output_fields_info()
        self.interpreter._tools_registered = False
        process = self.interpreter.process
        if process is not None and process.poll() is None:
            self.interpreter._register_tools()

    def _trajectory_from_history(self, history: REPLHistory) -> list[dict[str, Any]]:
        return [entry.model_dump() for entry in history]

    def _set_last_run_telemetry(
        self,
        *,
        task_start: float,
        stop_reason: str,
        finalized: bool,
        final_outputs: dict[str, Any] | None,
        reasoning: str,
        code: str,
        stdout: str,
        error: str | None,
        trajectory: list[dict[str, Any]],
    ) -> None:
        self._last_run_telemetry = RLMRunTelemetry(
            latency_s=time.perf_counter() - task_start,
            stop_reason=stop_reason,
            finalized=finalized,
            final_outputs=final_outputs,
            reasoning=reasoning,
            code=code,
            stdout=stdout,
            error=error,
            trajectory=list(trajectory),
        )

    def _build_success_prediction(
        self,
        *,
        parsed_outputs: dict[str, Any],
        history: REPLHistory,
        final_reasoning: str,
    ) -> dspy.Prediction:
        return dspy.Prediction(
            **parsed_outputs,
            trajectory=self._trajectory_from_history(history),
            final_reasoning=final_reasoning,
        )

    def _extract_fallback(
        self,
        *,
        variables_info: list[str],
        history: REPLHistory,
        output_field_names: list[str],
    ) -> dict[str, Any]:
        extract_pred = self.extract(
            variables_info=variables_info,
            repl_history=history,
        )
        return {name: getattr(extract_pred, name) for name in output_field_names}

    def _format_iteration_error(self, exc: BaseException) -> str:
        if isinstance(exc, (SyntaxError, CodeInterpreterError)):
            return f"[Error] {exc}"
        return f"[Error] {type(exc).__name__}: {exc}"

    def _process_final_output(
        self,
        result: FinalOutput,
    ) -> tuple[dict[str, Any] | None, str | None]:
        output_field_names = list(self.signature.output_fields.keys())
        raw_output = result.output

        if not isinstance(raw_output, dict):
            return (
                None,
                f"[Error] SUBMIT returned {type(raw_output).__name__}, expected dict with fields: {output_field_names}",
            )

        missing = set(output_field_names) - set(raw_output.keys())
        if missing:
            return (
                None,
                f"[Error] Missing output fields: {sorted(missing)}. Use SUBMIT({', '.join(f'{name}=...' for name in output_field_names)})",
            )

        parsed_outputs: dict[str, Any] = {}
        type_errors: list[str] = []
        for name in output_field_names:
            field = self.signature.output_fields[name]
            annotation = getattr(field, "annotation", str)
            try:
                parsed_outputs[name] = parse_value(raw_output[name], annotation)
            except (ValueError, pydantic.ValidationError) as exc:
                annotation_name = (
                    annotation.__name__
                    if hasattr(annotation, "__name__")
                    else str(annotation)
                )
                type_errors.append(
                    f"{name}: expected {annotation_name}, got {type(raw_output[name]).__name__}: {exc}"
                )

        if type_errors:
            return (None, "[Type Error] " + "; ".join(type_errors))

        return (parsed_outputs, None)

    def _emit_step_finished(
        self,
        *,
        step_index: int,
        step_start: float,
        status: str,
        stop_reason: str | None,
        parse_success: bool,
        final_signal: bool,
        extra_data: dict[str, Any] | None = None,
        final_outputs: dict[str, Any] | None = None,
    ) -> None:
        if self._step_observer is None:
            return
        data: dict[str, Any] = {
            "status": status,
            "stop_reason": stop_reason,
            "parse_success": parse_success,
            "final_signal": final_signal,
        }
        if extra_data:
            data.update(extra_data)
        if final_outputs is not None:
            data["final_outputs"] = dict(final_outputs)
        self._step_observer.on_step_finished(
            step_index=step_index,
            outcome={
                "data": data,
                "stats": {"elapsed_ms": int((time.perf_counter() - step_start) * 1000)},
                "summary": {},
            },
        )

    def _emit_step_started(
        self,
        *,
        step_index: int,
        context: dict[str, Any],
    ) -> None:
        if self._step_observer is None:
            return
        self._step_observer.on_step_started(step_index=step_index, context=context)

    # ------------------------------------------------------------------
    # Execution — Algorithm 1
    # ------------------------------------------------------------------

    def forward(self, **kwargs: Any) -> dspy.Prediction:
        """Run the iterative reasoning/execution loop for a single task."""
        self._validate_inputs(kwargs)
        self._last_run_telemetry = None
        self._llm_query_calls = 0
        task_start = time.perf_counter()
        output_field_names = list(self.signature.output_fields.keys())

        # Build metadata for the LLM (name/type/size) while the REPL gets the
        # full values injected once at startup.
        variables_info = self._build_variables_info(**kwargs)

        # -- Init REPL --
        runtime_started = False
        history = REPLHistory()
        last_reasoning = ""
        last_code = ""
        all_stdout: list[str] = []
        last_error: str | None = None
        consecutive_action_parse_failures = 0
        try:
            if hasattr(self.interpreter, "start"):
                self.interpreter.start()  # type: ignore[attr-defined]
                runtime_started = True

            try:
                self._inject_tools()
            except Exception as exc:
                error_msg = (
                    f"[Error] failed to initialize REPL: {type(exc).__name__}: {exc}"
                )
                self._set_last_run_telemetry(
                    task_start=task_start,
                    stop_reason="execution_error",
                    finalized=False,
                    final_outputs=None,
                    reasoning="",
                    code="",
                    stdout="",
                    error=error_msg,
                    trajectory=[],
                )
                raise ReplRuntimeError(error_msg) from exc

            try:
                self.interpreter.execute("pass", variables=kwargs)
            except Exception as exc:
                error_msg = (
                    f"[Error] failed to inject variables: {type(exc).__name__}: {exc}"
                )
                self._set_last_run_telemetry(
                    task_start=task_start,
                    stop_reason="execution_error",
                    finalized=False,
                    final_outputs=None,
                    reasoning="",
                    code="",
                    stdout="",
                    error=error_msg,
                    trajectory=[],
                )
                raise ReplRuntimeError(error_msg) from exc

            for iteration in range(self.max_iterations):
                step_index = iteration + 1
                step_start = time.perf_counter()

                # -- step.started --
                self._emit_step_started(
                    step_index=step_index,
                    context={
                        "max_iterations": self.max_iterations,
                        "remaining_iteration_budget": self.max_iterations - iteration,
                        "repl_history_before": len(history),
                    },
                )

                # -- LLM generates reasoning + code --
                try:
                    pred = self.generate_action(
                        variables_info=variables_info,
                        repl_history=history,
                        iteration=f"{step_index}/{self.max_iterations}",
                    )
                except AdapterParseError as exc:
                    consecutive_action_parse_failures += 1
                    last_error = self._format_iteration_error(exc)
                    history = history.append(
                        reasoning="",
                        code="",
                        output=last_error,
                    )
                    self._emit_step_finished(
                        step_index=step_index,
                        step_start=step_start,
                        status="error",
                        stop_reason=StopReason.PARSE_FAILURE.value,
                        parse_success=False,
                        final_signal=False,
                        extra_data={
                            "parse_failure_type": "adapter_parse_error",
                            "consecutive_parse_failures": consecutive_action_parse_failures,
                        },
                    )
                    if (
                        consecutive_action_parse_failures
                        >= MAX_CONSECUTIVE_ACTION_PARSE_FAILURES
                    ):
                        self._set_last_run_telemetry(
                            task_start=task_start,
                            stop_reason=StopReason.PARSE_FAILURE.value,
                            finalized=False,
                            final_outputs=None,
                            reasoning=last_reasoning,
                            code=last_code,
                            stdout="\n".join(all_stdout),
                            error=last_error,
                            trajectory=self._trajectory_from_history(history),
                        )
                        raise ReplRuntimeError(last_error) from exc
                    continue
                consecutive_action_parse_failures = 0
                last_reasoning = _normalize_optional_text(pred.reasoning)
                raw_code = _normalize_optional_text(getattr(pred, "code", None))
                try:
                    code = _strip_code_fences(raw_code) if raw_code.strip() else ""
                except SyntaxError as exc:
                    code = raw_code.strip()
                    last_code = code
                    last_error = self._format_iteration_error(exc)
                    history = history.append(
                        reasoning=last_reasoning,
                        code=code,
                        output=last_error,
                    )
                    self._emit_step_finished(
                        step_index=step_index,
                        step_start=step_start,
                        status="error",
                        stop_reason="execution_error",
                        parse_success=True,
                        final_signal=False,
                    )
                    continue

                if not code.strip():
                    last_error = "[Error] model returned empty code"
                    history = history.append(
                        reasoning=last_reasoning,
                        code="",
                        output=last_error,
                    )
                    self._emit_step_finished(
                        step_index=step_index,
                        step_start=step_start,
                        status="error",
                        stop_reason="empty_code",
                        parse_success=False,
                        final_signal=False,
                    )
                    continue

                last_code = code

                # -- Execute in REPL --
                try:
                    result = self.repl_tool(code=code)
                except Exception as exc:
                    error_msg = self._format_iteration_error(exc)
                    last_error = error_msg
                    if isinstance(exc, ReplRuntimeError):
                        fatal_history = history.append(
                            reasoning=last_reasoning,
                            code=code,
                            output=error_msg,
                        )
                        self._emit_step_finished(
                            step_index=step_index,
                            step_start=step_start,
                            status="error",
                            stop_reason="execution_error",
                            parse_success=True,
                            final_signal=False,
                        )
                        self._set_last_run_telemetry(
                            task_start=task_start,
                            stop_reason="execution_error",
                            finalized=False,
                            final_outputs=None,
                            reasoning=last_reasoning,
                            code=code,
                            stdout="\n".join(all_stdout),
                            error=error_msg,
                            trajectory=self._trajectory_from_history(fatal_history),
                        )
                        raise
                    history = history.append(
                        reasoning=last_reasoning,
                        code=code,
                        output=error_msg,
                    )
                    self._emit_step_finished(
                        step_index=step_index,
                        step_start=step_start,
                        status="error",
                        stop_reason="execution_error",
                        parse_success=True,
                        final_signal=False,
                    )
                    continue

                # -- Check for SUBMIT --
                if isinstance(result, FinalOutput):
                    parsed_outputs, error_msg = self._process_final_output(result)
                    if error_msg:
                        last_error = error_msg
                        history = history.append(
                            reasoning=last_reasoning,
                            code=code,
                            output=error_msg,
                        )
                        self._emit_step_finished(
                            step_index=step_index,
                            step_start=step_start,
                            status="error",
                            stop_reason="invalid_final_outputs",
                            parse_success=True,
                            final_signal=False,
                        )
                        continue
                    final_history = history.append(
                        reasoning=last_reasoning,
                        code=code,
                        output=f"FINAL: {parsed_outputs}",
                    )
                    self._emit_step_finished(
                        step_index=step_index,
                        step_start=step_start,
                        status="success",
                        stop_reason="final",
                        parse_success=True,
                        final_signal=True,
                    )
                    prediction = self._build_success_prediction(
                        parsed_outputs=parsed_outputs or {},
                        history=final_history,
                        final_reasoning=last_reasoning,
                    )
                    self._set_last_run_telemetry(
                        task_start=task_start,
                        stop_reason="success",
                        finalized=True,
                        final_outputs=parsed_outputs,
                        reasoning=last_reasoning,
                        code=code,
                        stdout="\n".join(all_stdout),
                        error=None,
                        trajectory=self._trajectory_from_history(final_history),
                    )
                    return prediction

                # -- Feed output back --
                output = result or ""
                if output:
                    all_stdout.append(output)
                history_output = output or "(no output - did you forget to print?)"
                history = history.append(
                    reasoning=last_reasoning, code=code, output=history_output
                )

                self._emit_step_finished(
                    step_index=step_index,
                    step_start=step_start,
                    status="continue",
                    stop_reason=None,
                    parse_success=True,
                    final_signal=False,
                )

            extract_step_index = self.max_iterations + 1
            extract_step_start = time.perf_counter()
            self._emit_step_started(
                step_index=extract_step_index,
                context={
                    "max_iterations": self.max_iterations,
                    "remaining_iteration_budget": 0,
                    "repl_history_before": len(history),
                    "extract_fallback": True,
                },
            )
            try:
                parsed_outputs = self._extract_fallback(
                    variables_info=variables_info,
                    history=history,
                    output_field_names=output_field_names,
                )
            except Exception as exc:
                error_msg = self._format_iteration_error(exc)
                self._emit_step_finished(
                    step_index=extract_step_index,
                    step_start=extract_step_start,
                    status="error",
                    stop_reason="execution_error",
                    parse_success=False,
                    final_signal=False,
                    extra_data={"extract_fallback": True},
                )
                self._set_last_run_telemetry(
                    task_start=task_start,
                    stop_reason="execution_error",
                    finalized=False,
                    final_outputs=None,
                    reasoning=last_reasoning,
                    code=last_code,
                    stdout="\n".join(all_stdout),
                    error=error_msg,
                    trajectory=self._trajectory_from_history(history),
                )
                raise
            self._emit_step_finished(
                step_index=extract_step_index,
                step_start=extract_step_start,
                status="success",
                stop_reason="final",
                parse_success=True,
                final_signal=True,
                extra_data={"extract_fallback": True},
                final_outputs=parsed_outputs,
            )
            self._set_last_run_telemetry(
                task_start=task_start,
                stop_reason="success",
                finalized=True,
                final_outputs=parsed_outputs,
                reasoning=last_reasoning,
                code=last_code,
                stdout="\n".join(all_stdout),
                error=None,
                trajectory=self._trajectory_from_history(history),
            )
            return self._build_success_prediction(
                parsed_outputs=parsed_outputs,
                history=history,
                final_reasoning="Extract forced final output",
            )
        except Exception as exc:
            if self._last_run_telemetry is None:
                self._set_last_run_telemetry(
                    task_start=task_start,
                    stop_reason="execution_error",
                    finalized=False,
                    final_outputs=None,
                    reasoning=last_reasoning,
                    code=last_code,
                    stdout="\n".join(all_stdout),
                    error=self._format_iteration_error(exc),
                    trajectory=self._trajectory_from_history(history),
                )
            raise
        finally:
            if runtime_started and hasattr(self.interpreter, "shutdown"):
                try:
                    self.interpreter.shutdown()  # type: ignore[attr-defined]
                except Exception:
                    pass


__all__ = [
    "ACTION_INSTRUCTIONS_TEMPLATE",
    "EXTRACT_INSTRUCTIONS",
    "LLM_QUERY_PROMPT_CHAR_LIMIT",
    "RLM",
    "RLMRunTelemetry",
    "StepObserver",
    "_normalize_optional_text",
    "_strip_code_fences",
]
