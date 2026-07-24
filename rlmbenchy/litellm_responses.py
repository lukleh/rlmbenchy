"""Normalize LiteLLM responses streams into plain Responses API payload dicts."""

from __future__ import annotations

from typing import Any
import warnings

from rlmbenchy.rlm._response_extraction import response_to_dict

_KNOWN_RESPONSE_USAGE_WARNING = r"Pydantic serializer warnings:[\s\S]*ResponseAPIUsage"


def _read_field(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _event_type_value(event: Any) -> str:
    raw_type = _read_field(event, "type")
    if hasattr(raw_type, "value"):
        raw_type = getattr(raw_type, "value")
    return str(raw_type or "").strip()


def _safe_output_index(event: Any) -> int | None:
    raw_index = _read_field(event, "output_index")
    if isinstance(raw_index, bool):
        return None
    if isinstance(raw_index, int):
        return raw_index
    if isinstance(raw_index, float):
        return int(raw_index)
    if isinstance(raw_index, str):
        stripped = raw_index.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _normalize_stream_item(item: Any) -> dict[str, Any] | None:
    payload = response_to_dict(item)
    return payload if payload else None


def _hydrate_output_from_stream_events(events: list[Any]) -> list[dict[str, Any]]:
    output_items: dict[int, dict[str, Any]] = {}

    for event in events:
        output_index = _safe_output_index(event)
        if output_index is None:
            continue

        item = _normalize_stream_item(_read_field(event, "item"))
        if item is None:
            continue

        event_type = _event_type_value(event)
        if event_type == "response.output_item.added":
            output_items.setdefault(output_index, item)
            continue
        if event_type == "response.output_item.done":
            output_items[output_index] = item

    return [output_items[index] for index in sorted(output_items)]


def drain_litellm_responses_stream(stream: Any) -> dict[str, Any]:
    """Consume a LiteLLM responses stream and return a plain response payload."""

    events: list[Any] = []
    with warnings.catch_warnings():
        # LiteLLM mutates a Responses API usage object into a chat-style usage
        # dict for logging, which triggers a harmless serializer warning during
        # stream finalization inside pydantic.main.
        warnings.filterwarnings(
            "ignore",
            message=_KNOWN_RESPONSE_USAGE_WARNING,
            category=UserWarning,
            module=r"pydantic\.main",
        )
        for event in stream:
            events.append(event)

    completed = _read_field(stream, "completed_response")
    response = _read_field(completed, "response")
    if response is None:
        raise RuntimeError(
            "ChatGPT responses stream ended without a completed response."
        )

    response_dict = response_to_dict(response)
    output = response_dict.get("output")
    if not isinstance(output, list) or not output:
        hydrated_output = _hydrate_output_from_stream_events(events)
        if hydrated_output:
            response_dict["output"] = hydrated_output
    return response_dict
