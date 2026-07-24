"""Public helpers for inspecting rlmbenchy runtime results."""

from __future__ import annotations

from typing import Any

RETRYABLE_TOOL_STATUS_CODES = {429, 502, 503, 504}


def extract_final_answer(task_run: Any, *, field: str = "answer") -> str | None:
    """Extract a text final answer from a task run or its loop result."""
    for source in (task_run, _runtime_field(task_run, "loop_result", "loopResult")):
        outputs = _runtime_field(source, "final_outputs", "finalOutputs")
        if isinstance(outputs, dict):
            value = outputs.get(field)
            if isinstance(value, str) and value.strip():
                return value
    return None


def loop_result_summary(loop_result: Any) -> dict[str, Any]:
    """Return a stable summary of a loop result object."""
    if loop_result is None:
        return {}
    return {
        "stopReason": _string_or_none(
            _runtime_field(loop_result, "stop_reason", "stopReason")
        ),
        "iterations": _runtime_field(loop_result, "iterations"),
        "error": _string_or_none(_runtime_field(loop_result, "error")),
    }


def is_retryable_tool_error(loop_result: Any) -> bool:
    """Return whether loop metadata contains a retryable tool failure."""
    metadata = _runtime_field(loop_result, "metadata")
    for entry in _metadata_events(metadata):
        if str(_runtime_field(entry, "event_type", "eventType") or "") != "tool.error":
            continue
        data = _runtime_field(entry, "data")
        status_code = _optional_int(_runtime_field(data, "status_code", "statusCode"))
        if status_code in RETRYABLE_TOOL_STATUS_CODES:
            return True
        error_message = str(_runtime_field(data, "error_message", "errorMessage") or "")
        if any(token in error_message for token in (" 429", " 502", " 503", " 504")):
            return True
    return False


def _metadata_events(metadata: Any) -> list[Any]:
    if isinstance(metadata, list):
        return metadata
    if isinstance(metadata, tuple):
        return list(metadata)
    events = _runtime_field(metadata, "events")
    if isinstance(events, list):
        return events
    if isinstance(events, tuple):
        return list(events)
    trajectory = _runtime_field(metadata, "trajectory")
    if trajectory is not None:
        return _metadata_events(trajectory)
    return []


def _runtime_field(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        attr = getattr(value, name, None)
        if attr is not None:
            return attr
    return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "RETRYABLE_TOOL_STATUS_CODES",
    "extract_final_answer",
    "is_retryable_tool_error",
    "loop_result_summary",
]
