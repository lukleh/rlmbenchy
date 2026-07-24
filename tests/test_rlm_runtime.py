from __future__ import annotations

import json
from pathlib import Path
import subprocess

import dspy
import pytest
from dspy.adapters.types.reasoning import Reasoning as DspyReasoning
from dspy.utils.exceptions import AdapterParseError
from dspy.predict.rlm import RLM as OfficialRLM
from dspy.primitives.code_interpreter import CodeInterpreterError, FinalOutput
from dspy.primitives.repl_types import REPLHistory
from dspy.utils.callback import BaseCallback
from types import SimpleNamespace

from rlmbenchy.logger import RLMLogger
from rlmbenchy.rlm.executor import run_task
from rlmbenchy.rlm.reasoning import install_reasoning_native_allowlist_override
from rlmbenchy.rlm.repl import (
    LocalProcessReplRuntime,
    ReplExecutionTimeoutError,
    ReplRuntimeError,
)
import rlmbenchy.rlm.rlm as dspy_rlm_module
from rlmbenchy.rlm.rlm import RLM, RLMRunTelemetry
from rlmbenchy.rlm.types import RLMRunConfig, StopReason


class _Signature(dspy.Signature):
    task: str = dspy.InputField()
    answer: str = dspy.OutputField()


class _DescribedSignature(dspy.Signature):
    task: str = dspy.InputField(desc="Task prompt.")
    answer: str = dspy.OutputField()


class _ReservedOutputSignature(dspy.Signature):
    task: str = dspy.InputField()
    trajectory: str = dspy.OutputField()


def _dataset_lookup(prompt: str) -> str:
    return f"echo:{prompt}"


def _start_raw_repl_worker() -> subprocess.Popen[str]:
    return LocalProcessReplRuntime()._start_process()


def _send_worker_message(
    process: subprocess.Popen[str],
    payload: object,
    *,
    raw: bool = False,
) -> None:
    assert process.stdin is not None
    line = str(payload) if raw else json.dumps(payload)
    process.stdin.write(line + "\n")
    process.stdin.flush()


def _read_worker_message(process: subprocess.Popen[str]) -> dict[str, object]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line
    message = json.loads(line)
    assert isinstance(message, dict)
    return message


def _stop_raw_repl_worker(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        _send_worker_message(process, {"jsonrpc": "2.0", "method": "shutdown"})
        process.wait(timeout=3)
    except Exception:
        process.kill()
        process.wait(timeout=3)


class _DummyProcess:
    def __init__(self, *, running: bool) -> None:
        self._running = running

    def poll(self) -> int | None:
        return None if self._running else 1


class _DummyInterpreter:
    def __init__(self, *, running: bool) -> None:
        self.tools: dict[str, object] = {}
        self.output_fields: list[dict[str, object]] | None = None
        self._tools_registered = True
        self.process = _DummyProcess(running=running)
        self.register_calls = 0

    def _register_tools(self) -> None:
        self.register_calls += 1
        self._tools_registered = True


class _ReasoningWrapper:
    def __init__(self, content: str) -> None:
        self.content = content


class _PredictorSequence:
    def __init__(self, predictions: list[object]) -> None:
        self._predictions = list(predictions)
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        assert self._predictions, "predictor called more times than expected"
        prediction = self._predictions.pop(0)
        if isinstance(prediction, BaseException):
            raise prediction
        assert isinstance(prediction, SimpleNamespace)
        return prediction


class _DeleteTrackingSignature:
    def __init__(self) -> None:
        self.deleted_fields: list[str] = []

    def delete(self, field_name: str) -> _DeleteTrackingSignature:
        self.deleted_fields.append(field_name)
        return self


class _ReasoningLM:
    def __init__(self, model: str, kwargs: dict[str, object] | None = None) -> None:
        self.model = model
        self.kwargs = dict(kwargs or {})
        self.model_type = "chat"
        self.supports_reasoning = True


class _ExecuteInterpreter:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.setup_variables: dict[str, object] = {}
        self.tools: dict[str, object] = {}
        self.output_fields: list[dict[str, object]] | None = None
        self._tools_registered = True
        self.process = None

    def execute(self, code: str, variables: dict[str, object] | None = None) -> object:
        if variables is not None:
            # Variable-injection setup call — record but don't consume an outcome
            self.setup_variables = dict(variables)
            return ""
        self.calls.append((code, {}))
        assert self._outcomes, "execute called more times than expected"
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _LifecycleInterpreter:
    def __init__(self, *, forward_outcomes: list[list[object]]) -> None:
        self._forward_outcomes = [list(outcomes) for outcomes in forward_outcomes]
        self._active_outcomes: list[object] = []
        self._forward_index = 0
        self.start_calls = 0
        self.shutdown_calls = 0
        self.register_calls = 0
        self.tools: dict[str, object] = {}
        self.output_fields: list[dict[str, object]] | None = None
        self._tools_registered = True
        self.process = _DummyProcess(running=False)

    def start(self) -> None:
        self.start_calls += 1
        if self._forward_index < len(self._forward_outcomes):
            self._active_outcomes = list(self._forward_outcomes[self._forward_index])
        else:
            self._active_outcomes = []
        self._forward_index += 1
        self.process = _DummyProcess(running=True)

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.process = _DummyProcess(running=False)

    def _register_tools(self) -> None:
        self.register_calls += 1
        self._tools_registered = True

    def execute(self, code: str, variables: dict[str, object] | None = None) -> object:
        if variables is not None:
            return ""
        assert self._active_outcomes, (
            "execute called more times than expected for this forward"
        )
        outcome = self._active_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _NoopRuntime:
    def shutdown(self) -> None:
        pass


class _FakeLMResponse:
    def __init__(
        self,
        *,
        text: str,
        usage: dict[str, int],
        model: str = "fake-response-model",
    ) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
        self.usage = usage
        self.model = model
        self._hidden_params: dict[str, object] = {}


class _LMCallbackRecorder(BaseCallback):
    def __init__(self) -> None:
        self.starts: list[dict[str, object]] = []
        self.ends: list[object] = []

    def on_lm_start(
        self, call_id: str, instance: object, inputs: dict[str, object]
    ) -> None:
        del call_id, instance
        self.starts.append(inputs)

    def on_lm_end(
        self, call_id: str, outputs: object | None, exception: Exception | None = None
    ) -> None:
        del call_id, exception
        self.ends.append(outputs)


class _StepObserverRecorder:
    def __init__(self) -> None:
        self.starts: list[dict[str, object]] = []
        self.finishes: list[dict[str, object]] = []

    def on_step_started(self, *, step_index: int, context: dict[str, object]) -> None:
        self.starts.append(
            {
                "step_index": step_index,
                "context": dict(context),
            }
        )

    def on_step_finished(self, *, step_index: int, outcome: dict[str, object]) -> None:
        self.finishes.append(
            {
                "step_index": step_index,
                "outcome": dict(outcome),
            }
        )


class _CallbackLM(dspy.LM):
    def __init__(self, *, callbacks: list[BaseCallback]) -> None:
        super().__init__("openai/fake-model", callbacks=callbacks)
        self.forward_calls: list[dict[str, object]] = []

    def forward(self, prompt=None, messages=None, **kwargs):
        self.forward_calls.append(
            {
                "prompt": prompt,
                "messages": messages,
                "kwargs": dict(kwargs),
            }
        )
        return _FakeLMResponse(
            text=f"analysis:{prompt}",
            usage={"prompt_tokens": 11, "completion_tokens": 7},
        )


def _pred(reasoning: object, code: object) -> SimpleNamespace:
    return SimpleNamespace(reasoning=reasoning, code=code)


def _answer_outputs(value: object) -> dict[str, object]:
    return {"answer": value}


def _extract_pred(value: object) -> SimpleNamespace:
    return SimpleNamespace(answer=value)


def _telemetry(rlm: RLM):
    telemetry = rlm.last_run_telemetry
    assert telemetry is not None
    return telemetry


def test_inject_tools_registers_when_runtime_running() -> None:
    interpreter = _DummyInterpreter(running=True)
    rlm = RLM(
        _Signature,
        tools=[dspy.Tool(_dataset_lookup, name="dataset_lookup")],
        interpreter=interpreter,  # type: ignore[arg-type]
    )

    rlm._inject_tools()

    assert "dataset_lookup" in interpreter.tools
    assert "llm_query" in interpreter.tools
    assert interpreter.register_calls == 1
    assert interpreter._tools_registered is True


def test_inject_tools_defers_registration_when_runtime_not_running() -> None:
    interpreter = _DummyInterpreter(running=False)
    rlm = RLM(
        _Signature,
        tools=[dspy.Tool(_dataset_lookup, name="dataset_lookup")],
        interpreter=interpreter,  # type: ignore[arg-type]
    )

    rlm._inject_tools()

    assert "dataset_lookup" in interpreter.tools
    assert "llm_query" in interpreter.tools
    assert interpreter.register_calls == 0
    assert interpreter._tools_registered is False


def test_action_signature_uses_variables_info_pattern() -> None:
    """Our action signature uses variables_info (like DSPy's RLM) instead of
    copying user input fields directly."""
    ours = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]
    official = OfficialRLM(_Signature, max_llm_calls=200)

    our_sig = ours.generate_action.signature
    official_sig = official.generate_action.signature

    # Our action sig uses variables_info like DSPy's RLM — no user fields directly.
    assert list(our_sig.input_fields) == ["variables_info", "repl_history", "iteration"]
    assert list(our_sig.output_fields) == ["reasoning", "code"]
    assert our_sig.input_fields["variables_info"].annotation is str
    assert our_sig.input_fields["repl_history"].annotation is REPLHistory
    assert our_sig.input_fields["iteration"].annotation is str
    assert our_sig.output_fields["reasoning"].annotation is dspy.Reasoning
    assert our_sig.output_fields["code"].annotation is str

    # DSPy's official RLM also uses variables_info.
    assert "variables_info" in official_sig.input_fields
    assert "repl_history" in official_sig.input_fields
    assert "task" not in official_sig.input_fields  # user fields are NOT in action sig

    # Both use SUBMIT as the structured termination keyword.
    assert "SUBMIT(" in our_sig.instructions
    assert "FINAL(" not in our_sig.instructions
    assert "variables_info" in our_sig.instructions
    assert "print compact, targeted observations" in our_sig.instructions
    assert "Input values are not shown in this prompt" in our_sig.instructions
    assert "Before printing a full input value" in our_sig.instructions
    assert "ORCHESTRATE, DON'T JUST SOLVE" in our_sig.instructions
    assert "Everything you print becomes part of `repl_history`" in our_sig.instructions
    assert "`llm_query` has no access to REPL variables" in our_sig.instructions
    assert "Avoid many tiny calls" in our_sig.instructions
    assert "iteration budget is nearly exhausted" in our_sig.instructions
    assert "supported by observed outputs" in our_sig.instructions


def test_variables_info_omits_input_value_previews() -> None:
    rlm = RLM(
        _DescribedSignature,
        interpreter=_DummyInterpreter(running=False),  # type: ignore[arg-type]
    )

    variables_info = rlm._build_variables_info(task="PRIVATE_VALUE_DO_NOT_RENDER")
    rendered = "\n".join(variables_info)

    assert "Variable: `task`" in rendered
    assert "Type: str" in rendered
    assert "Description: Task prompt." in rendered
    assert "Total length: 27 characters" in rendered
    assert "Preview:" not in rendered
    assert "PRIVATE_VALUE_DO_NOT_RENDER" not in rendered


def test_inject_tools_with_no_custom_tools_keeps_builtin_llm_query() -> None:
    interpreter = _DummyInterpreter(running=True)
    rlm = RLM(_Signature, interpreter=interpreter)  # type: ignore[arg-type]

    rlm._inject_tools()

    assert set(interpreter.tools) == {"llm_query"}
    assert interpreter.register_calls == 1
    assert interpreter._tools_registered is True


def test_rlm_rejects_reserved_output_names_even_for_direct_signatures() -> None:
    with pytest.raises(ValueError, match="reserved by RLM runtime metadata"):
        RLM(
            _ReservedOutputSignature,
            interpreter=_DummyInterpreter(running=False),  # type: ignore[arg-type]
        )


def test_llm_query_tool_calls_sub_lm_with_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeLM:
        def __call__(self, prompt: str) -> list[str]:
            captured["prompt"] = prompt
            return ["ok"]

    monkeypatch.setattr(dspy.settings, "lm", _FakeLM(), raising=False)
    rlm = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]

    output = rlm._llm_query_tool("hello")

    assert output == "ok"
    assert captured == {"prompt": "hello"}


def test_llm_query_uses_public_lm_call_path_and_preserves_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = _LMCallbackRecorder()
    lm = _CallbackLM(callbacks=[callback])
    monkeypatch.setattr(dspy.settings, "lm", lm, raising=False)

    rlm = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]
    text = rlm._llm_query_tool("hello")

    assert text == "analysis:hello"
    assert lm.forward_calls == [
        {
            "prompt": "hello",
            "messages": None,
            "kwargs": {},
        }
    ]
    assert callback.starts == [{"prompt": "hello", "messages": None, "kwargs": {}}]
    assert callback.ends == [["analysis:hello"]]


def test_llm_query_respects_custom_lm_call_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _CustomCallLM:
        def __init__(self) -> None:
            self.called: dict[str, object] | None = None
            self.history: list[dict[str, object]] = []

        def __call__(self, prompt=None, messages=None, **kwargs):
            self.called = {
                "prompt": prompt,
                "messages": messages,
                "kwargs": dict(kwargs),
            }
            return [f"custom:{prompt}"]

        def forward(self, prompt=None, messages=None, **kwargs):
            del prompt, messages, kwargs
            raise AssertionError("forward should not be called directly")

    lm = _CustomCallLM()
    monkeypatch.setattr(dspy.settings, "lm", lm, raising=False)

    rlm = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]
    text = rlm._llm_query_tool("hello")

    assert text == "custom:hello"
    assert lm.called == {
        "prompt": "hello",
        "messages": None,
        "kwargs": {},
    }


def test_llm_query_tool_raises_when_prompt_exceeds_hard_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class _FakeLM:
        def __call__(self, prompt: str) -> list[str]:
            nonlocal called
            called = True
            return ["should-not-run"]

    monkeypatch.setattr(dspy.settings, "lm", _FakeLM(), raising=False)
    rlm = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r"hard limit: 20000"):
        rlm._llm_query_tool("x" * 20001)

    assert called is False


def test_llm_query_tool_allows_prompt_at_hard_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeLM:
        def __call__(self, prompt: str) -> list[str]:
            captured["prompt_len"] = len(prompt)
            return ["ok"]

    monkeypatch.setattr(dspy.settings, "lm", _FakeLM(), raising=False)
    rlm = RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]

    output = rlm._llm_query_tool("x" * 20000)

    assert output == "ok"
    assert captured == {"prompt_len": 20000}


def test_llm_query_tool_enforces_call_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _FakeLM:
        def __call__(self, prompt: str) -> list[str]:
            calls.append(prompt)
            return [f"ok:{prompt}"]

    monkeypatch.setattr(dspy.settings, "lm", _FakeLM(), raising=False)
    rlm = RLM(
        _Signature,
        max_llm_calls=1,
        interpreter=_DummyInterpreter(running=False),  # type: ignore[arg-type]
    )

    assert rlm._llm_query_tool("one") == "ok:one"
    with pytest.raises(RuntimeError, match="llm_query call budget exhausted"):
        rlm._llm_query_tool("two")

    assert calls == ["one"]


def test_llm_query_tool_allows_zero_budget_without_calling_lm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class _FakeLM:
        def __call__(self, prompt: str) -> list[str]:
            nonlocal called
            called = True
            return [f"ok:{prompt}"]

    monkeypatch.setattr(dspy.settings, "lm", _FakeLM(), raising=False)
    rlm = RLM(
        _Signature,
        max_llm_calls=0,
        interpreter=_DummyInterpreter(running=False),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="used 0 of 0"):
        rlm._llm_query_tool("one")

    assert called is False


def test_forward_starts_and_stops_fresh_runtime_each_call() -> None:
    interpreter = _LifecycleInterpreter(
        forward_outcomes=[
            [FinalOutput({"answer": "first"})],
            [FinalOutput({"answer": "second"})],
        ]
    )
    rlm = RLM(_Signature, max_iterations=1, interpreter=interpreter)  # type: ignore[arg-type]

    rlm.generate_action = _PredictorSequence(
        [_pred("step-1", "SUBMIT(answer='first')")]
    )  # type: ignore[assignment]
    first = rlm.forward(task="task-1")

    rlm.generate_action = _PredictorSequence(
        [_pred("step-1", "SUBMIT(answer='second')")]
    )  # type: ignore[assignment]
    second = rlm.forward(task="task-2")

    assert first.answer == "first"
    assert first.final_reasoning == "step-1"
    assert second.answer == "second"
    assert second.final_reasoning == "step-1"
    assert _telemetry(rlm).final_outputs == _answer_outputs("second")
    assert _telemetry(rlm).error is None
    assert interpreter.start_calls == 2
    assert interpreter.shutdown_calls == 2
    assert interpreter.register_calls == 2


def test_forward_treats_repl_timeout_as_fatal_task_error() -> None:
    interpreter = _ExecuteInterpreter(
        [
            ReplExecutionTimeoutError("Execution timed out after 10.0s."),
            FinalOutput({"answer": "ok"}),
        ]
    )
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    predictor = _PredictorSequence(
        [
            _pred("step-1", "print('first')"),
            _pred("step-2", "SUBMIT(answer='ok')"),
        ]
    )
    rlm.generate_action = predictor  # type: ignore[assignment]

    with pytest.raises(ReplExecutionTimeoutError, match="timed out"):
        rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert telemetry.final_outputs is None
    assert telemetry.error is not None
    assert "timed out" in telemetry.error.lower()
    assert telemetry.code == "print('first')"
    assert len(interpreter.calls) == 1
    assert len(predictor.calls) == 1


def test_forward_returns_final_output_and_collects_stdout() -> None:
    interpreter = _ExecuteInterpreter(
        ["first-output", FinalOutput({"answer": "final-answer"})]
    )
    rlm = RLM(_Signature, max_iterations=3, interpreter=interpreter)  # type: ignore[arg-type]
    predictor = _PredictorSequence(
        [
            _pred(_ReasoningWrapper("step-1"), "```python\nprint('a')\n```"),
            _pred(_ReasoningWrapper("step-2"), "```python\nSUBMIT(answer='done')\n```"),
        ]
    )
    rlm.generate_action = predictor  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert result.answer == "final-answer"
    assert result.final_reasoning == "step-2"
    assert telemetry.final_outputs == _answer_outputs("final-answer")
    assert telemetry.stdout == "first-output"
    assert telemetry.error is None
    assert telemetry.reasoning == "step-2"
    assert telemetry.code == "SUBMIT(answer='done')"
    assert interpreter.calls[0][0] == "print('a')"
    assert interpreter.calls[1][0] == "SUBMIT(answer='done')"
    assert [call["iteration"] for call in predictor.calls] == ["1/3", "2/3"]
    assert all("variables_info" in call for call in predictor.calls)
    rendered_variables_info = "\n".join(predictor.calls[0]["variables_info"])
    assert "Preview:" not in rendered_variables_info
    assert "demo task" not in rendered_variables_info


def test_forward_notifies_step_observer_for_continue_then_final() -> None:
    interpreter = _ExecuteInterpreter(
        ["first-output", FinalOutput({"answer": "final-answer"})]
    )
    observer = _StepObserverRecorder()
    rlm = RLM(
        _Signature,
        max_iterations=3,
        interpreter=interpreter,  # type: ignore[arg-type]
        step_observer=observer,
    )
    predictor = _PredictorSequence(
        [
            _pred("step-1", "```python\nprint('a')\n```"),
            _pred("step-2", "```python\nSUBMIT(answer='done')\n```"),
        ]
    )
    rlm.generate_action = predictor  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    assert result.answer == "final-answer"
    assert _telemetry(rlm).final_outputs == _answer_outputs("final-answer")
    assert [item["step_index"] for item in observer.starts] == [1, 2]
    assert observer.starts[0]["context"] == {
        "max_iterations": 3,
        "remaining_iteration_budget": 3,
        "repl_history_before": 0,
    }
    assert observer.starts[1]["context"] == {
        "max_iterations": 3,
        "remaining_iteration_budget": 2,
        "repl_history_before": 1,
    }
    assert [item["step_index"] for item in observer.finishes] == [1, 2]
    assert observer.finishes[0]["outcome"]["data"] == {
        "status": "continue",
        "stop_reason": None,
        "parse_success": True,
        "final_signal": False,
    }
    assert observer.finishes[0]["outcome"]["summary"] == {}
    assert isinstance(observer.finishes[0]["outcome"]["stats"]["elapsed_ms"], int)
    assert observer.finishes[1]["outcome"]["data"] == {
        "status": "success",
        "stop_reason": "final",
        "parse_success": True,
        "final_signal": True,
    }
    assert observer.finishes[1]["outcome"]["summary"] == {}
    assert isinstance(observer.finishes[1]["outcome"]["stats"]["elapsed_ms"], int)


def test_forward_notifies_step_observer_for_empty_code_recovery() -> None:
    interpreter = _ExecuteInterpreter([FinalOutput({"answer": "ok"})])
    observer = _StepObserverRecorder()
    rlm = RLM(
        _Signature,
        max_iterations=2,
        interpreter=interpreter,  # type: ignore[arg-type]
        step_observer=observer,
    )
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred(_ReasoningWrapper("empty"), None),
            _pred(_ReasoningWrapper("retry"), "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    assert result.answer == "ok"
    assert _telemetry(rlm).final_outputs == _answer_outputs("ok")
    assert [item["step_index"] for item in observer.starts] == [1, 2]
    assert [item["step_index"] for item in observer.finishes] == [1, 2]
    assert observer.finishes[0]["outcome"]["data"] == {
        "status": "error",
        "stop_reason": "empty_code",
        "parse_success": False,
        "final_signal": False,
    }
    assert observer.finishes[0]["outcome"]["summary"] == {}
    assert observer.finishes[1]["outcome"]["data"] == {
        "status": "success",
        "stop_reason": "final",
        "parse_success": True,
        "final_signal": True,
    }
    assert observer.finishes[1]["outcome"]["summary"] == {}


def test_forward_recovers_from_syntax_error_and_continues() -> None:
    interpreter = _ExecuteInterpreter(
        [SyntaxError("broken syntax"), FinalOutput({"answer": "ok"})]
    )
    rlm = RLM(_Signature, max_iterations=3, interpreter=interpreter)  # type: ignore[arg-type]
    predictor = _PredictorSequence(
        [
            _pred(_ReasoningWrapper("try-1"), "```python\nbad =\n```"),
            _pred(_ReasoningWrapper("try-2"), "SUBMIT(answer='ok')"),
        ]
    )
    rlm.generate_action = predictor  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert result.answer == "ok"
    assert telemetry.final_outputs == _answer_outputs("ok")
    assert telemetry.error is None
    assert telemetry.reasoning == "try-2"
    assert telemetry.code == "SUBMIT(answer='ok')"
    assert len(interpreter.calls) == 2
    assert interpreter.calls[0][0] == "bad ="
    assert interpreter.calls[1][0] == "SUBMIT(answer='ok')"


def test_forward_recovers_from_action_adapter_parse_error_and_continues() -> None:
    interpreter = _ExecuteInterpreter([FinalOutput({"answer": "ok"})])
    observer = _StepObserverRecorder()
    rlm = RLM(
        _Signature,
        max_iterations=2,
        interpreter=interpreter,  # type: ignore[arg-type]
        step_observer=observer,
    )
    parse_error = AdapterParseError(
        "JSONAdapter",
        rlm.generate_action.signature,
        '{"analysis": "not executable code"}',
    )
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            parse_error,
            _pred(_ReasoningWrapper("retry"), "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert result.answer == "ok"
    assert telemetry.final_outputs == _answer_outputs("ok")
    assert telemetry.error is None
    assert len(interpreter.calls) == 1
    assert interpreter.calls[0][0] == "SUBMIT(answer='ok')"
    assert telemetry.trajectory[0]["code"] == ""
    assert "AdapterParseError" in telemetry.trajectory[0]["output"]
    assert observer.finishes[0]["outcome"]["data"] == {
        "status": "error",
        "stop_reason": StopReason.PARSE_FAILURE.value,
        "parse_success": False,
        "final_signal": False,
        "parse_failure_type": "adapter_parse_error",
        "consecutive_parse_failures": 1,
    }


def test_forward_stops_after_consecutive_action_adapter_parse_errors() -> None:
    interpreter = _ExecuteInterpreter([])
    rlm = RLM(_Signature, max_iterations=5, interpreter=interpreter)  # type: ignore[arg-type]
    parse_errors = [
        AdapterParseError(
            "JSONAdapter",
            rlm.generate_action.signature,
            f'{{"analysis": "bad {index}"}}',
        )
        for index in range(3)
    ]
    rlm.generate_action = _PredictorSequence(parse_errors)  # type: ignore[assignment]

    with pytest.raises(ReplRuntimeError, match="AdapterParseError"):
        rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert telemetry.stop_reason == StopReason.PARSE_FAILURE.value
    assert telemetry.final_outputs is None
    assert telemetry.error is not None
    assert "AdapterParseError" in telemetry.error
    assert len(telemetry.trajectory) == 3
    assert interpreter.calls == []


def test_forward_returns_last_interpreter_error_when_no_final() -> None:
    interpreter = _ExecuteInterpreter([CodeInterpreterError("boom")])
    rlm = RLM(
        _Signature,
        max_iterations=1,
        interpreter=interpreter,
    )  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence([_pred("single-step", "print('x')")])  # type: ignore[assignment]
    rlm.extract = _PredictorSequence([_extract_pred("fallback")])  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert result.answer == "fallback"
    assert result.final_reasoning == "Extract forced final output"
    assert telemetry.final_outputs == _answer_outputs("fallback")
    assert telemetry.error is None
    assert telemetry.reasoning == "single-step"
    assert telemetry.code == "print('x')"
    assert result.trajectory == [
        {
            "reasoning": "single-step",
            "code": "print('x')",
            "output": "[Error] boom",
        }
    ]


def test_forward_returns_max_iterations_error_when_no_final_or_exception() -> None:
    interpreter = _ExecuteInterpreter(["", None])
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred(_ReasoningWrapper("r1"), "print('one')"),
            _pred(_ReasoningWrapper("r2"), "```python\nprint('two')\n```"),
        ]
    )
    rlm.extract = _PredictorSequence([_extract_pred("fallback")])  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert result.answer == "fallback"
    assert result.final_reasoning == "Extract forced final output"
    assert telemetry.final_outputs == _answer_outputs("fallback")
    assert telemetry.stdout == ""
    assert telemetry.reasoning == "r2"
    assert telemetry.code == "print('two')"
    assert [call[0] for call in interpreter.calls] == ["print('one')", "print('two')"]


def test_forward_emits_extract_fallback_as_extra_step() -> None:
    interpreter = _ExecuteInterpreter(["", None])
    observer = _StepObserverRecorder()
    rlm = RLM(
        _Signature,
        max_iterations=2,
        interpreter=interpreter,  # type: ignore[arg-type]
        step_observer=observer,
    )
    action_predictor = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred("r1", "print('one')"),
            _pred("r2", "print('two')"),
        ]
    )
    extract_predictor = _PredictorSequence([_extract_pred("fallback")])
    rlm.generate_action = action_predictor  # type: ignore[assignment]
    rlm.extract = extract_predictor  # type: ignore[assignment]

    result = rlm.forward(task="demo task")

    assert result.answer == "fallback"
    assert result.final_reasoning == "Extract forced final output"
    assert [item["step_index"] for item in observer.starts] == [1, 2, 3]
    assert observer.starts[2]["context"] == {
        "max_iterations": 2,
        "remaining_iteration_budget": 0,
        "repl_history_before": 2,
        "extract_fallback": True,
    }
    assert [item["step_index"] for item in observer.finishes] == [1, 2, 3]
    assert observer.finishes[2]["outcome"]["data"] == {
        "status": "success",
        "stop_reason": "final",
        "parse_success": True,
        "final_signal": True,
        "extract_fallback": True,
        "final_outputs": {"answer": "fallback"},
    }
    assert observer.finishes[2]["outcome"]["summary"] == {}
    assert len(action_predictor.calls) == 2
    assert len(extract_predictor.calls) == 1


def test_forward_handles_missing_code_field_without_crashing() -> None:
    interpreter = _ExecuteInterpreter([FinalOutput({"answer": "ok"})])
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred(_ReasoningWrapper("empty"), None),
            _pred(_ReasoningWrapper("retry"), "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    assert result.answer == "ok"
    assert _telemetry(rlm).final_outputs == _answer_outputs("ok")
    assert _telemetry(rlm).error is None
    assert len(interpreter.calls) == 1
    assert interpreter.calls[0][0] == "SUBMIT(answer='ok')"


def test_run_task_preserves_last_run_telemetry_when_rlm_raises(tmp_path) -> None:
    class _TelemetryFailingRLM:
        def __init__(self, signature, **kwargs) -> None:  # noqa: ANN001, ANN003
            del signature, kwargs
            self.last_run_telemetry: RLMRunTelemetry | None = None

        def __call__(self, **kwargs):
            del kwargs
            self.last_run_telemetry = RLMRunTelemetry(
                latency_s=0.25,
                stop_reason=StopReason.EXECUTION_ERROR.value,
                finalized=False,
                final_outputs=None,
                reasoning="step-1",
                code="print('first')",
                stdout="partial output",
                error="[Error] Execution timed out after 10.0s.",
                trajectory=[
                    {
                        "reasoning": "step-1",
                        "code": "print('first')",
                        "output": "[Error] Execution timed out after 10.0s.",
                    }
                ],
            )
            raise ReplExecutionTimeoutError("Execution timed out after 10.0s.")

    task_run, logger = run_task(
        signature=_Signature,
        run_config=RLMRunConfig(
            api_base="https://example.invalid/v1",
            model="openai/fake-model",
            api_key="test-key",
        ),
        task_inputs={"task": "demo task"},
        logger=RLMLogger(log_dir=tmp_path),
        runtime=_NoopRuntime(),  # type: ignore[arg-type]
        build_lm_fn=lambda **kwargs: object(),
        rlm_cls=_TelemetryFailingRLM,  # type: ignore[arg-type]
        configure_fn=lambda **kwargs: None,
    )

    assert task_run.status == "error"
    assert task_run.stop_reason == StopReason.EXECUTION_ERROR.value
    assert task_run.final_outputs is None
    assert task_run.reasoning == "step-1"
    assert task_run.code == "print('first')"
    assert task_run.observed == "partial output"
    assert task_run.error == "[Error] Execution timed out after 10.0s."
    assert task_run.loop_result.iterations == 1
    assert task_run.loop_result.error == "[Error] Execution timed out after 10.0s."
    # The disk JSONL is the telemetry record; confirm the run was logged there.
    assert logger.log_file_path is not None
    assert Path(logger.log_file_path).exists()


def test_run_task_scopes_lm_and_adapter_settings(tmp_path) -> None:
    outer_lm = object()
    built_lm = object()
    seen: dict[str, object | None] = {}

    class _SettingsInspectingRLM:
        def __init__(self, signature, **kwargs) -> None:  # noqa: ANN001, ANN003
            del signature, kwargs
            self.last_run_telemetry: RLMRunTelemetry | None = None

        def __call__(self, **kwargs):
            del kwargs
            seen["lm"] = dspy.settings.get("lm")
            seen["adapter"] = dspy.settings.get("adapter")
            self.last_run_telemetry = RLMRunTelemetry(
                latency_s=0.01,
                stop_reason=StopReason.SUCCESS.value,
                finalized=True,
                final_outputs={"answer": "ok"},
                reasoning="done",
                code="SUBMIT(answer='ok')",
                stdout="",
                error=None,
                trajectory=[],
            )
            return dspy.Prediction(answer="ok")

    with dspy.context(lm=outer_lm, adapter=None):
        task_run, _logger = run_task(
            signature=_Signature,
            run_config=RLMRunConfig(
                api_base="https://example.invalid/v1",
                model="openai/fake-model",
                api_key="test-key",
                adapter_mode="json",
            ),
            task_inputs={"task": "demo task"},
            logger=RLMLogger(log_dir=tmp_path),
            runtime=_NoopRuntime(),  # type: ignore[arg-type]
            build_lm_fn=lambda **kwargs: built_lm,
            rlm_cls=_SettingsInspectingRLM,  # type: ignore[arg-type]
        )
        assert dspy.settings.get("lm") is outer_lm
        assert dspy.settings.get("adapter") is None

    assert task_run.status == "success"
    assert seen["lm"] is built_lm
    assert isinstance(seen["adapter"], dspy.JSONAdapter)


def test_forward_recovers_from_generic_interpreter_exception() -> None:
    interpreter = _ExecuteInterpreter(
        [ValueError("boom"), FinalOutput({"answer": "ok"})]
    )
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred("first", "print('x')"),
            _pred("second", "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    assert result.answer == "ok"
    assert _telemetry(rlm).final_outputs == _answer_outputs("ok")
    assert _telemetry(rlm).error is None
    assert len(interpreter.calls) == 2


def test_forward_recovers_from_nonfatal_code_interpreter_error() -> None:
    interpreter = _ExecuteInterpreter(
        [CodeInterpreterError("boom"), FinalOutput({"answer": "ok"})]
    )
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred("first", "print('x')"),
            _pred("second", "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    assert result.answer == "ok"
    assert _telemetry(rlm).final_outputs == _answer_outputs("ok")
    assert _telemetry(rlm).error is None
    assert len(interpreter.calls) == 2


def test_strip_code_fences_handles_fenced_and_raw_code() -> None:
    assert dspy_rlm_module._strip_code_fences("```python\nx = 1\n```") == "x = 1"
    assert dspy_rlm_module._strip_code_fences("```py\nx = 2\n```") == "x = 2"
    assert dspy_rlm_module._strip_code_fences("```python3\nx = 3\n```") == "x = 3"
    assert dspy_rlm_module._strip_code_fences("```\nx = 4\n```") == "x = 4"
    assert dspy_rlm_module._strip_code_fences("```py3\nx = 5\n```") == "x = 5"
    assert (
        dspy_rlm_module._strip_code_fences(
            "intro text\n```python\nx = 6\n```\noutro text"
        )
        == "x = 6"
    )
    assert (
        dspy_rlm_module._strip_code_fences("```\n```python\nx = 7\n```\n```") == "x = 7"
    )
    assert (
        dspy_rlm_module._strip_code_fences(
            "answer = 'ok'\nSUBMIT(answer=answer)\n[[ ## completed ]]"
        )
        == "answer = 'ok'\nSUBMIT(answer=answer)"
    )
    assert (
        dspy_rlm_module._strip_code_fences(
            "[[ ## code ## ]]\n```python\nx = 8\n[[ ## completed ## ]]"
        )
        == "x = 8"
    )
    assert dspy_rlm_module._strip_code_fences("  print('raw')  ") == "print('raw')"


def test_strip_code_fences_rejects_non_python_fences() -> None:
    with pytest.raises(SyntaxError, match="Expected Python code but got ```json fence"):
        dspy_rlm_module._strip_code_fences('```json\n{"x": 1}\n```')


def test_forward_recovers_from_invalid_fenced_code_block() -> None:
    interpreter = _ExecuteInterpreter([FinalOutput({"answer": "ok"})])
    rlm = RLM(_Signature, max_iterations=2, interpreter=interpreter)  # type: ignore[arg-type]
    rlm.generate_action = _PredictorSequence(  # type: ignore[assignment]
        [
            _pred("first", '```json\n{"oops": true}\n```'),
            _pred("second", "SUBMIT(answer='ok')"),
        ]
    )

    result = rlm.forward(task="demo task")

    assert result.answer == "ok"
    assert len(interpreter.calls) == 1
    assert _telemetry(rlm).final_outputs == _answer_outputs("ok")


def test_init_installs_reasoning_override(monkeypatch) -> None:
    calls = 0

    def _fake_install() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        "rlmbenchy.rlm.rlm.install_reasoning_native_allowlist_override",
        _fake_install,
    )

    RLM(_Signature, interpreter=_DummyInterpreter(running=False))  # type: ignore[arg-type]

    assert calls == 1


def test_litellm_reports_previously_allowlisted_models_as_reasoning_capable() -> None:
    """Q3a depends on LiteLLM's upstream metadata reporting these four
    OpenRouter models as reasoning-capable. If that regresses, profiles
    silently stop emitting native reasoning. Guard it here."""

    from litellm.utils import supports_reasoning

    for model in (
        "openrouter/openai/gpt-oss-20b",
        "openrouter/openai/gpt-oss-120b",
        "openrouter/qwen/qwen3.5-27b",
        "openrouter/qwen/qwen3.5-35b-a3b",
    ):
        assert supports_reasoning(model) is True, model


def test_reasoning_override_delegates_previously_allowlisted_models() -> None:
    """gpt-oss / qwen3.5 models used to be hardcoded in an allowlist because
    LiteLLM lacked reasoning metadata for them. Now that LiteLLM reports
    them as reasoning-capable, our patch only holds back the ChatGPT
    Responses transport — everything else runs through upstream DSPy."""

    install_reasoning_native_allowlist_override()
    signature = _DeleteTrackingSignature()
    lm = _ReasoningLM("openrouter/openai/gpt-oss-120b")
    lm_kwargs: dict[str, object] = {}

    result = DspyReasoning.adapt_to_native_lm_feature(
        signature,
        "reasoning",
        lm,
        lm_kwargs,
    )

    assert result is signature
    assert signature.deleted_fields == ["reasoning"]
    assert lm_kwargs["reasoning_effort"] == "low"


def test_reasoning_override_preserves_fallback_for_non_allowlisted_models() -> None:
    install_reasoning_native_allowlist_override()
    signature = _DeleteTrackingSignature()
    lm = _ReasoningLM("openrouter/openai/gpt-4o")
    lm_kwargs: dict[str, object] = {}

    result = DspyReasoning.adapt_to_native_lm_feature(
        signature,
        "reasoning",
        lm,
        lm_kwargs,
    )

    assert result is signature
    assert signature.deleted_fields == ["reasoning"]
    assert lm_kwargs["reasoning_effort"] == "low"


def test_reasoning_override_preserves_explicit_field_for_chatgpt_responses_transport() -> (
    None
):
    install_reasoning_native_allowlist_override()
    signature = _DeleteTrackingSignature()
    lm = _ReasoningLM(
        "openai/gpt-5.6-terra",
        kwargs={"api_base": "https://chatgpt.com/backend-api/codex"},
    )
    lm.model_type = "responses"
    lm_kwargs: dict[str, object] = {}

    result = DspyReasoning.adapt_to_native_lm_feature(
        signature,
        "reasoning",
        lm,
        lm_kwargs,
    )

    assert result is signature
    assert signature.deleted_fields == []
    assert "reasoning_effort" not in lm_kwargs


def test_repl_worker_reports_parse_error_for_invalid_json() -> None:
    process = _start_raw_repl_worker()
    try:
        _send_worker_message(process, "{not-json", raw=True)
        response = _read_worker_message(process)
    finally:
        _stop_raw_repl_worker(process)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert response["error"]["code"] == -32700  # type: ignore[index]


def test_repl_worker_rejects_missing_jsonrpc_version() -> None:
    process = _start_raw_repl_worker()
    try:
        _send_worker_message(
            process,
            {"method": "execute", "params": {"code": "print(1)"}, "id": 1},
        )
        response = _read_worker_message(process)
    finally:
        _stop_raw_repl_worker(process)

    assert response["id"] == 1
    assert response["error"]["code"] == -32600  # type: ignore[index]
    assert "jsonrpc" in response["error"]["message"]  # type: ignore[index]


def test_repl_worker_rejects_batch_requests_as_unsupported() -> None:
    process = _start_raw_repl_worker()
    try:
        _send_worker_message(
            process,
            [
                {
                    "jsonrpc": "2.0",
                    "method": "execute",
                    "params": {"code": "print(1)"},
                    "id": 1,
                }
            ],
        )
        response = _read_worker_message(process)
    finally:
        _stop_raw_repl_worker(process)

    assert response["id"] is None
    assert response["error"]["code"] == -32600  # type: ignore[index]
    assert "batch requests are unsupported" in response["error"]["message"]  # type: ignore[index]


def test_repl_worker_reports_invalid_params_for_bad_execute_code() -> None:
    process = _start_raw_repl_worker()
    try:
        _send_worker_message(
            process,
            {"jsonrpc": "2.0", "method": "execute", "params": {"code": 123}, "id": 1},
        )
        response = _read_worker_message(process)
    finally:
        _stop_raw_repl_worker(process)

    assert response["id"] == 1
    assert response["error"]["code"] == -32602  # type: ignore[index]
    assert response["error"]["data"]["type"] == "InvalidParams"  # type: ignore[index]


def test_repl_worker_reports_method_not_found_for_unknown_method() -> None:
    process = _start_raw_repl_worker()
    try:
        _send_worker_message(
            process,
            {"jsonrpc": "2.0", "method": "missing", "params": {}, "id": 1},
        )
        response = _read_worker_message(process)
    finally:
        _stop_raw_repl_worker(process)

    assert response["id"] == 1
    assert response["error"]["code"] == -32601  # type: ignore[index]
    assert response["error"]["data"]["type"] == "MethodNotFound"  # type: ignore[index]


def test_repl_worker_shutdown_notification_exits_without_response() -> None:
    process = _start_raw_repl_worker()
    _send_worker_message(process, {"jsonrpc": "2.0", "method": "shutdown"})
    process.wait(timeout=3)

    assert process.returncode == 0
    assert process.stdout is not None
    assert process.stdout.read() == ""


def test_host_rejects_malformed_tool_call_params() -> None:
    sent: list[dict[str, object]] = []
    runtime = LocalProcessReplRuntime(tools={"echo": lambda value: value})
    runtime._send = lambda payload: sent.append(payload)  # type: ignore[method-assign]

    runtime._handle_tool_call(
        {
            "jsonrpc": "2.0",
            "method": "tool_call",
            "params": {"name": "echo", "args": "not-a-list", "kwargs": {}},
            "id": 7,
        }
    )

    assert sent == [
        {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params: expected list 'args'.",
                "data": {"type": "InvalidParams"},
            },
            "id": 7,
        }
    ]


def test_host_reports_tool_result_serialization_error_as_tool_call_error() -> None:
    sent: list[dict[str, object]] = []
    runtime = LocalProcessReplRuntime(tools={"bad": lambda: {1, 2}})
    original_send = runtime._send

    def _serializing_send(payload: dict[str, object]) -> None:
        json.dumps(payload)
        sent.append(payload)

    runtime._send = _serializing_send  # type: ignore[method-assign]
    try:
        runtime._handle_tool_call(
            {
                "jsonrpc": "2.0",
                "method": "tool_call",
                "params": {"name": "bad", "args": [], "kwargs": {}},
                "id": 8,
            }
        )
    finally:
        runtime._send = original_send  # type: ignore[method-assign]

    assert len(sent) == 1
    assert sent[0]["id"] == 8
    error = sent[0]["error"]
    assert error["code"] == -32002  # type: ignore[index]
    assert error["data"]["type"] == "TypeError"  # type: ignore[index]
    assert "not JSON serializable" in error["message"]  # type: ignore[index]


def test_host_rejects_boolean_response_id() -> None:
    with pytest.raises(ReplRuntimeError, match="response ID mismatch"):
        from rlmbenchy.rlm import repl as repl_module

        repl_module._validate_jsonrpc_response(
            {"jsonrpc": "2.0", "result": {"output": ""}, "id": True},
            expected_id=1,
            context="test",
        )


def test_forward_integrates_with_real_repl_and_custom_tool_roundtrip() -> None:
    tool_calls: list[int] = []

    def compute_stats(value: int) -> dict[str, int]:
        tool_calls.append(value)
        return {"value": value, "double": value * 2}

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1",
                "```python\nstats = compute_stats(21)\nprint(stats['double'])\n```",
            ),
            _pred("step-2", "```python\nSUBMIT(answer=stats['double'])\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=3,
            tools=[dspy.Tool(compute_stats, name="compute_stats")],
            interpreter=interpreter,
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    assert tool_calls == [21]
    telemetry = _telemetry(rlm)
    assert result.answer == "42"
    assert telemetry.final_outputs == _answer_outputs("42")
    assert telemetry.stdout == "42\n"
    assert telemetry.error is None
    assert telemetry.code == "SUBMIT(answer=stats['double'])"


def test_forward_integrates_with_real_repl_builtin_llm_query() -> None:
    calls: list[str] = []

    class _FakeSubLM:
        def __call__(self, prompt: str) -> list[str]:
            calls.append(prompt)
            return [f"analysis:{prompt}"]

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1", "```python\nllm_text = llm_query(task)\nprint(llm_text)\n```"
            ),
            _pred("step-2", "```python\nSUBMIT(answer=llm_text)\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=3,
            interpreter=interpreter,
            sub_lm=_FakeSubLM(),  # type: ignore[arg-type]
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    assert calls == ["demo task"]
    telemetry = _telemetry(rlm)
    assert result.answer == "analysis:demo task"
    assert telemetry.final_outputs == _answer_outputs("analysis:demo task")
    assert telemetry.stdout == "analysis:demo task\n"
    assert telemetry.error is None
    assert telemetry.code == "SUBMIT(answer=llm_text)"


def test_forward_real_repl_llm_query_budget_error_then_final() -> None:
    calls: list[str] = []

    class _FakeSubLM:
        def __call__(self, prompt: str) -> list[str]:
            calls.append(prompt)
            return [f"analysis:{prompt}"]

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1",
                "```python\nfirst = llm_query('one')\nsecond = llm_query('two')\n```",
            ),
            _pred("step-2", "```python\nSUBMIT(answer='recovered')\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=2,
            max_llm_calls=1,
            interpreter=interpreter,
            sub_lm=_FakeSubLM(),  # type: ignore[arg-type]
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    telemetry = _telemetry(rlm)
    assert calls == ["one"]
    assert result.answer == "recovered"
    assert telemetry.final_outputs == _answer_outputs("recovered")
    assert "llm_query call budget exhausted" in telemetry.trajectory[0]["output"]


def test_forward_integrates_with_real_repl_tool_error_then_final() -> None:
    tool_calls: list[tuple[int, int]] = []

    def divide(a: int, b: int) -> float:
        tool_calls.append((a, b))
        return a / b

    predictor = _PredictorSequence(
        [
            _pred("step-1", "```python\nvalue = divide(10, 0)\n```"),
            _pred(
                "step-2", "```python\nvalue = divide(10, 2)\nSUBMIT(answer=value)\n```"
            ),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=3,
            tools=[dspy.Tool(divide, name="divide")],
            interpreter=interpreter,
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    assert tool_calls == [(10, 0), (10, 2)]
    telemetry = _telemetry(rlm)
    assert result.answer == "5.0"
    assert telemetry.final_outputs == _answer_outputs("5.0")
    assert telemetry.error is None
    assert telemetry.code == "value = divide(10, 2)\nSUBMIT(answer=value)"


def test_forward_integrates_with_real_repl_multiple_tools_kwargs_and_state() -> None:
    add_calls: list[tuple[int, int]] = []
    meta_calls: list[tuple[str, str]] = []

    def add(a: int, b: int = 0) -> int:
        add_calls.append((a, b))
        return a + b

    def make_meta(text: str, prefix: str = "") -> dict[str, object]:
        meta_calls.append((text, prefix))
        return {"prefix": prefix, "text": text, "length": len(text)}

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1",
                "```python\nx = add(2, b=5)\nmeta = make_meta(task, prefix='T')\nprint(x)\nprint(meta['prefix'])\n```",
            ),
            _pred("step-2", "```python\nSUBMIT(answer=f\"{x}:{meta['length']}\")\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=3,
            tools=[
                dspy.Tool(add, name="add"),
                dspy.Tool(make_meta, name="make_meta"),
            ],
            interpreter=interpreter,
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="hello")

    assert add_calls == [(2, 5)]
    assert meta_calls == [("hello", "T")]
    assert result.answer == "7:5"
    assert _telemetry(rlm).final_outputs == _answer_outputs("7:5")
    assert _telemetry(rlm).stdout == "7\nT\n"
    assert _telemetry(rlm).error is None


def test_forward_real_repl_tool_call_ids_increment_across_iterations() -> None:
    send_payloads: list[dict[str, object]] = []

    def plus_one(value: int) -> int:
        return value + 1

    def times_ten(value: int) -> int:
        return value * 10

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1", "```python\na = plus_one(1)\nb = times_ten(a)\nprint(b)\n```"
            ),
            _pred("step-2", "```python\nc = plus_one(5)\nSUBMIT(answer=c)\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        original_send = interpreter._send

        def _capture_send(payload: dict[str, object]) -> None:
            send_payloads.append(dict(payload))
            original_send(payload)

        interpreter._send = _capture_send  # type: ignore[method-assign]

        rlm = RLM(
            _Signature,
            max_iterations=3,
            tools=[
                dspy.Tool(plus_one, name="plus_one"),
                dspy.Tool(times_ten, name="times_ten"),
            ],
            interpreter=interpreter,
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    tool_call_responses = [
        payload for payload in send_payloads if "method" not in payload
    ]
    assert [payload["id"] for payload in tool_call_responses] == [1, 2, 3]
    assert result.answer == "6"
    assert _telemetry(rlm).final_outputs == _answer_outputs("6")
    assert _telemetry(rlm).stdout == "20\n"
    assert _telemetry(rlm).error is None


def test_forward_real_repl_tool_error_response_preserves_tool_call_ids() -> None:
    send_payloads: list[dict[str, object]] = []
    tool_calls: list[int] = []

    def maybe_fail(value: int) -> int:
        tool_calls.append(value)
        if value < 0:
            raise ValueError("negative value")
        return value * 2

    predictor = _PredictorSequence(
        [
            _pred("step-1", "```python\nx = maybe_fail(-1)\n```"),
            _pred("step-2", "```python\nx = maybe_fail(4)\nSUBMIT(answer=x)\n```"),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        original_send = interpreter._send

        def _capture_send(payload: dict[str, object]) -> None:
            send_payloads.append(dict(payload))
            original_send(payload)

        interpreter._send = _capture_send  # type: ignore[method-assign]

        rlm = RLM(
            _Signature,
            max_iterations=3,
            tools=[dspy.Tool(maybe_fail, name="maybe_fail")],
            interpreter=interpreter,
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    tool_call_responses = [
        payload for payload in send_payloads if "method" not in payload
    ]
    assert [payload["id"] for payload in tool_call_responses] == [1, 2]
    assert "error" in tool_call_responses[0]
    assert "result" in tool_call_responses[1]
    assert tool_calls == [-1, 4]
    assert result.answer == "8"
    assert _telemetry(rlm).final_outputs == _answer_outputs("8")
    assert _telemetry(rlm).error is None


def test_forward_real_repl_custom_llm_query_tool_overrides_builtin() -> None:
    builtin_calls: list[str] = []
    custom_calls: list[str] = []

    class _FakeSubLM:
        def __call__(self, prompt: str) -> list[str]:
            builtin_calls.append(prompt)
            return [f"builtin:{prompt}"]

    def custom_llm_query(prompt: str) -> str:
        custom_calls.append(prompt)
        return f"custom:{prompt}"

    predictor = _PredictorSequence(
        [
            _pred(
                "step-1", "```python\ntext = llm_query(task)\nSUBMIT(answer=text)\n```"
            ),
        ]
    )

    with LocalProcessReplRuntime() as interpreter:
        rlm = RLM(
            _Signature,
            max_iterations=2,
            tools=[dspy.Tool(custom_llm_query, name="llm_query")],
            interpreter=interpreter,
            sub_lm=_FakeSubLM(),  # type: ignore[arg-type]
        )
        rlm.generate_action = predictor  # type: ignore[assignment]
        result = rlm.forward(task="demo task")

    assert custom_calls == ["demo task"]
    assert builtin_calls == []
    assert result.answer == "custom:demo task"
    assert _telemetry(rlm).final_outputs == _answer_outputs("custom:demo task")
    assert _telemetry(rlm).error is None
