"""Shared runtime pieces for the RLM library and workbench."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rlmbenchy.logger.rlm_logger import RLMLogger

import dspy
from dspy.primitives.code_interpreter import FinalOutput
from dspy.utils.callback import ACTIVE_CALL_ID, BaseCallback

from rlmbenchy.rlm._response_extraction import (
    coerce_count as _coerce_count,
)
from rlmbenchy.rlm._response_extraction import (
    event_prompt_chars as _event_prompt_chars,
)
from rlmbenchy.rlm._response_extraction import (
    extract_cost,
    extract_finish_reason,
    extract_message,
    extract_preview,
    extract_reasoning,
    extract_usage,
)
from rlmbenchy.rlm._response_extraction import (
    history_entry_for_logged_call as _history_entry_for_logged_call,
)
from rlmbenchy.rlm._response_extraction import (
    redact_sensitive as _redact_sensitive,
)
from rlmbenchy.rlm._response_extraction import (
    response_to_dict as _response_to_dict,
)
from rlmbenchy.rlm._response_extraction import (
    safe_optional_int as _safe_optional_int,
)

DEFAULT_SIGNATURE_ID = "rlm_signature"
RLM_MAX_ITERATIONS = 100
RLM_MAX_LLM_CALLS = 200
VALID_ADAPTER_MODES = ("auto", "chat", "json")


def normalize_adapter_mode(raw: Any) -> str:
    """Normalize a configured adapter mode."""

    lowered = str(raw or "auto").strip().lower()
    aliases = {
        "": "auto",
        "auto": "auto",
        "default": "auto",
        "none": "auto",
        "chat": "chat",
        "chatadapter": "chat",
        "json": "json",
        "jsonadapter": "json",
    }
    normalized = aliases.get(lowered, lowered)
    if normalized not in VALID_ADAPTER_MODES:
        expected = ", ".join(VALID_ADAPTER_MODES)
        raise ValueError(
            f"Unsupported adapter mode {raw!r}. Expected one of: {expected}."
        )
    return normalized


def build_adapter(mode: str | None) -> dspy.Adapter | None:
    """Build a settings adapter for the requested mode.

    `auto` preserves DSPy's default behavior by leaving `settings.adapter` unset.
    `chat` forces ChatAdapter without JSON fallback so comparisons stay clean.
    `json` forces JSONAdapter.
    """

    normalized = normalize_adapter_mode(mode)
    if normalized == "auto":
        return None
    if normalized == "chat":
        return dspy.ChatAdapter(use_json_adapter_fallback=False)
    return dspy.JSONAdapter()


class LMLoggingCallback(BaseCallback):
    """DSPy callback that emits call-level telemetry events.

    Run/task lifecycle is owned by the runner, not this callback.
    Step lifecycle is owned by the RLM loop via the StepObserver protocol.
    This callback owns: llm.*, repl.*, tool.*, subllm.* events.
    """

    def __init__(
        self,
        *,
        logger: RLMLogger,
        task_id: str | None = None,
    ) -> None:
        self._logger = logger
        self._task_id = task_id
        self._request_index = 0
        self._current_step_index = 0
        self._inflight: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Module lifecycle — no-ops (runner owns run/task lifecycle)
    # ------------------------------------------------------------------

    def on_module_start(
        self,
        call_id: str,
        instance: Any,
        inputs: dict[str, Any],
    ) -> None:
        pass

    def on_module_end(
        self,
        call_id: str,
        outputs: Any | None,
        exception: Exception | None = None,
    ) -> None:
        pass

    # ------------------------------------------------------------------
    # Step lifecycle (StepObserver protocol — RLM loop owns step events)
    # ------------------------------------------------------------------

    def on_step_started(self, *, step_index: int, context: dict[str, Any]) -> None:
        self._current_step_index = step_index
        self._emit(
            {
                "event_type": "step.started",
                "data": context,
                "stats": {},
                "summary": {},
            }
        )

    def on_step_finished(self, *, step_index: int, outcome: dict[str, Any]) -> None:
        self._emit(
            {
                "event_type": "step.finished",
                "data": outcome.get("data", {}),
                "stats": outcome.get("stats", {}),
                "summary": outcome.get("summary", {}),
            },
            step_index=step_index,
        )

    # ------------------------------------------------------------------
    # LM lifecycle (llm.request / llm.response)
    # ------------------------------------------------------------------

    def on_lm_start(
        self,
        call_id: str,
        instance: Any,
        inputs: dict[str, Any],
    ) -> None:
        self._request_index += 1
        # DSPy sets ACTIVE_CALL_ID *after* start callbacks return, so at
        # this point the ContextVar still holds the parent's call_id.
        parent_call_id = ACTIVE_CALL_ID.get(None)
        is_sub = self._inside_repl()
        event_prefix = "subllm" if is_sub else "llm"

        prompt = inputs.get("prompt")
        messages = inputs.get("messages")
        request_kwargs = inputs.get("kwargs")
        if not isinstance(request_kwargs, dict):
            request_kwargs = {}
        payload_messages = messages or [{"role": "user", "content": prompt}]
        merged_kwargs = {
            **dict(getattr(instance, "kwargs", {}) or {}),
            **request_kwargs,
        }
        safe_kwargs = _redact_sensitive(merged_kwargs)
        prompt_chars = _event_prompt_chars(
            {"prompt": prompt, "messages": payload_messages}
        )

        self._inflight[call_id] = {
            "request_index": self._request_index,
            "started_at": time.perf_counter(),
            "lm": instance,
            "history_len_before": len(getattr(instance, "history", []) or []),
            "is_sub": is_sub,
            "parent_call_id": parent_call_id,
            "prompt": prompt,
            "prompt_chars": prompt_chars,
        }

        if is_sub:
            # Sub-LLM call (e.g. llm_query inside REPL execution)
            tool_name = self._enclosing_tool_name()
            self._emit(
                {
                    "event_type": f"{event_prefix}.request",
                    "call_id": call_id,
                    "parent_call_id": parent_call_id,
                    "data": {
                        "tool_name": tool_name,
                        "model": getattr(instance, "model", None),
                        "prompt": prompt,
                        "request_kwargs": safe_kwargs,
                    },
                    "stats": {"prompt_chars": prompt_chars},
                    "summary": {},
                }
            )
        else:
            # Main LM call
            provider_request: dict[str, Any] = {
                "model": getattr(instance, "model", None),
                "messages": payload_messages,
            }
            if prompt is not None:
                provider_request["prompt"] = prompt
            if safe_kwargs:
                provider_request["request_kwargs"] = safe_kwargs
            self._emit(
                {
                    "event_type": f"{event_prefix}.request",
                    "call_id": call_id,
                    "data": {
                        "request_index": self._request_index,
                        "model": getattr(instance, "model", None),
                        "prompt": prompt,
                        "messages": payload_messages,
                        "request_kwargs": safe_kwargs,
                        "provider_request": provider_request,
                    },
                    "stats": {"prompt_chars": prompt_chars},
                    "summary": {},
                }
            )

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | list[dict[str, Any] | str] | None,
        exception: Exception | None = None,
    ) -> None:
        context = self._inflight.pop(call_id, {})
        request_index = _safe_optional_int(context.get("request_index"))
        started_at = context.get("started_at")
        lm = context.get("lm")
        is_sub = context.get("is_sub", False)
        parent_call_id = context.get("parent_call_id")
        event_prefix = "subllm" if is_sub else "llm"
        elapsed_ms = (
            int((time.perf_counter() - started_at) * 1000) if started_at else None
        )
        history_entry = _history_entry_for_logged_call(
            lm,
            history_len_before=_safe_optional_int(context.get("history_len_before")),
        )

        if exception is not None:
            error_data: dict[str, Any] = {
                "error_type": type(exception).__name__,
                "error_message": str(exception),
                "model": getattr(lm, "model", None),
            }
            error_stats: dict[str, Any] = {}
            if elapsed_ms is not None:
                error_stats["elapsed_ms"] = elapsed_ms
            if is_sub:
                error_data["tool_name"] = self._enclosing_tool_name()
                error_data["prompt"] = context.get("prompt")
                error_stats["prompt_chars"] = _coerce_count(context.get("prompt_chars"))
            else:
                error_data["request_index"] = request_index
                error_data["provider_error"] = {
                    "type": type(exception).__name__,
                    "message": str(exception),
                }
            error_event: dict[str, Any] = {
                "event_type": f"{event_prefix}.error",
                "call_id": call_id,
                "data": error_data,
                "stats": error_stats,
                "summary": {},
            }
            if parent_call_id:
                error_event["parent_call_id"] = parent_call_id
            self._emit(error_event)
            return

        response = (
            history_entry.get("response") if isinstance(history_entry, dict) else None
        )
        token_usage = extract_usage(response, history_entry)
        cost_usd = extract_cost(response)
        response_dict = _response_to_dict(response) if response is not None else {}
        response_preview = extract_preview(response, outputs)

        if is_sub:
            # Sub-LLM response
            sub_stats: dict[str, Any] = {**token_usage}
            if elapsed_ms is not None:
                sub_stats["elapsed_ms"] = elapsed_ms
            if cost_usd is not None:
                sub_stats["cost_usd"] = cost_usd
            sub_event: dict[str, Any] = {
                "event_type": f"{event_prefix}.response",
                "call_id": call_id,
                "data": {
                    "tool_name": self._enclosing_tool_name(),
                    "model": getattr(lm, "model", None),
                    "response": response_preview,
                    "provider_response": _redact_sensitive(response_dict),
                },
                "stats": sub_stats,
                "summary": {},
            }
            if parent_call_id:
                sub_event["parent_call_id"] = parent_call_id
            self._emit(sub_event)
            return

        # Main LM response
        response_data: dict[str, Any] = {
            "request_index": request_index,
            "model": getattr(lm, "model", None),
            "provider_response": _redact_sensitive(response_dict),
            "response_text": response_preview,
        }
        response_stats: dict[str, Any] = {
            **token_usage,
        }
        response_summary: dict[str, Any] = {
            "response_preview": response_preview,
        }
        response_event: dict[str, Any] = {
            "event_type": f"{event_prefix}.response",
            "call_id": call_id,
            "data": response_data,
            "stats": response_stats,
            "summary": response_summary,
        }
        if elapsed_ms is not None:
            response_stats["elapsed_ms"] = elapsed_ms
        if cost_usd is not None:
            response_stats["cost_usd"] = cost_usd
        response_message = extract_message(response)
        if response_message is not None:
            response_data["response_message"] = response_message
        reasoning_text = extract_reasoning(response)
        if reasoning_text is not None:
            response_data["reasoning_text"] = reasoning_text
        finish_reason = extract_finish_reason(response)
        if finish_reason is not None:
            response_data["finish_reason"] = finish_reason
        if cost_usd is not None:
            response_stats["cost_usd"] = round(cost_usd, 8)
        if (
            token_usage.get("prompt_tokens") is not None
            or token_usage.get("generated_tokens") is not None
        ):
            response_summary["usage"] = token_usage
        self._emit(response_event)

    # ------------------------------------------------------------------
    # Tool lifecycle (repl.* / tool.*)
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        call_id: str,
        instance: Any,
        inputs: dict[str, Any],
    ) -> None:
        tool_name = getattr(instance, "name", None) or ""
        parent_call_id = ACTIVE_CALL_ID.get(None)
        self._inflight[call_id] = {
            "tool_name": tool_name,
            "started_at": time.perf_counter(),
            "parent_call_id": parent_call_id,
        }
        if tool_name == "repl":
            code = (inputs.get("kwargs") or {}).get("code", "")
            self._emit(
                {
                    "event_type": "repl.request",
                    "call_id": call_id,
                    "data": {"code": code},
                    "stats": {},
                    "summary": {},
                }
            )
        else:
            # Non-REPL tools, including llm_query, get their own tool envelope.
            args = inputs.get("args", [])
            kwargs = inputs.get("kwargs", {})
            event: dict[str, Any] = {
                "event_type": "tool.request",
                "call_id": call_id,
                "data": {"tool_name": tool_name, "args": args, "kwargs": kwargs},
                "stats": {},
                "summary": {},
            }
            if parent_call_id:
                event["parent_call_id"] = parent_call_id
            self._emit(event)

    def on_tool_end(
        self,
        call_id: str,
        outputs: Any | None,
        exception: Exception | None = None,
    ) -> None:
        context = self._inflight.pop(call_id, {})
        tool_name = context.get("tool_name", "")
        started_at = context.get("started_at")
        parent_call_id = context.get("parent_call_id")
        elapsed_ms = (
            int((time.perf_counter() - started_at) * 1000) if started_at else None
        )

        if tool_name == "repl":
            self._emit_repl_end(call_id, outputs, exception, elapsed_ms)
        else:
            self._emit_tool_end(
                call_id, tool_name, outputs, exception, elapsed_ms, parent_call_id
            )

    def _emit_repl_end(
        self,
        call_id: str,
        outputs: Any | None,
        exception: Exception | None,
        elapsed_ms: int | None,
    ) -> None:
        stats: dict[str, Any] = {}
        if elapsed_ms is not None:
            stats["elapsed_ms"] = elapsed_ms
        if exception is not None:
            self._emit(
                {
                    "event_type": "repl.error",
                    "call_id": call_id,
                    "data": {
                        "error": str(exception),
                        "error_type": type(exception).__name__,
                    },
                    "stats": stats,
                    "summary": {},
                }
            )
        elif isinstance(outputs, FinalOutput):
            self._emit(
                {
                    "event_type": "repl.final",
                    "call_id": call_id,
                    "data": {"final_outputs": outputs.output},
                    "stats": stats,
                    "summary": {},
                }
            )
        else:
            self._emit(
                {
                    "event_type": "repl.response",
                    "call_id": call_id,
                    "data": {"output": str(outputs or "")},
                    "stats": stats,
                    "summary": {},
                }
            )

    def _emit_tool_end(
        self,
        call_id: str,
        tool_name: str,
        outputs: Any | None,
        exception: Exception | None,
        elapsed_ms: int | None,
        parent_call_id: str | None,
    ) -> None:
        stats: dict[str, Any] = {}
        if elapsed_ms is not None:
            stats["elapsed_ms"] = elapsed_ms
        if exception is not None:
            event: dict[str, Any] = {
                "event_type": "tool.error",
                "call_id": call_id,
                "data": {
                    "tool_name": tool_name,
                    "error_type": type(exception).__name__,
                    "error_message": str(exception),
                },
                "stats": stats,
                "summary": {},
            }
        else:
            event = {
                "event_type": "tool.response",
                "call_id": call_id,
                "data": {"tool_name": tool_name, "result": outputs},
                "stats": stats,
                "summary": {},
            }
        if parent_call_id:
            event["parent_call_id"] = parent_call_id
        self._emit(event)

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inside_repl(self) -> bool:
        """True when a REPL tool call is in-flight.

        This relies on the REPL host loop being single-threaded and
        synchronous: on_tool_start for the REPL fires before any nested
        tool dispatch, and on_tool_end fires only after the REPL
        subprocess finishes.  Nested tool calls from the subprocess are
        handled one at a time by _handle_tool_call(), which blocks until
        the tool returns.
        """
        return any(ctx.get("tool_name") == "repl" for ctx in self._inflight.values())

    def _enclosing_tool_name(self) -> str | None:
        """Return the tool name of the most recent non-repl inflight tool."""
        for ctx in reversed(list(self._inflight.values())):
            name = ctx.get("tool_name")
            if name and name != "repl":
                return name
        return None

    def _emit(
        self,
        payload: dict[str, Any],
        *,
        step_index: int | None = None,
    ) -> None:
        if self._task_id:
            payload["task_id"] = self._task_id
        step_index_value = (
            step_index if step_index is not None else self._current_step_index
        )
        if step_index_value > 0:
            payload["step_index"] = step_index_value
        self._logger.log(payload)


__all__ = [
    "DEFAULT_SIGNATURE_ID",
    "RLM_MAX_ITERATIONS",
    "RLM_MAX_LLM_CALLS",
    "VALID_ADAPTER_MODES",
    "LMLoggingCallback",
    "build_adapter",
    "normalize_adapter_mode",
]
