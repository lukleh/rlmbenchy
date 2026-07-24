"""OpenTelemetry-shaped logging helpers."""

from __future__ import annotations

import calendar
import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from rlmbenchy.logger.coerce import coerce_float as _safe_float
from rlmbenchy.logger.coerce import coerce_int as _safe_int

OTEL_SCHEMA_NAME = "rlmbenchy_otel"
OTEL_SCHEMA_VERSION = 1
OTEL_SCOPE_NAME = "rlmbenchy.rlm"
OTEL_SCOPE_VERSION = "0.1.0"

_MISSING = object()


def is_otel_record(record: dict[str, Any]) -> bool:
    return (
        str(record.get("schema_name") or "").strip() == OTEL_SCHEMA_NAME
        and _safe_int(record.get("schema_version")) == OTEL_SCHEMA_VERSION
    )


def trace_id_for_run(run_id: str) -> str:
    return hashlib.sha256(f"trace:{run_id}".encode()).hexdigest()[:32]


def span_id_for_key(run_id: str, key: str) -> str:
    return hashlib.sha256(f"span:{run_id}:{key}".encode()).hexdigest()[:16]


def otel_resource(
    *,
    service_name: str = "rlmbenchy",
    service_version: str = OTEL_SCOPE_VERSION,
) -> dict[str, Any]:
    return {
        "service.name": service_name,
        "service.version": service_version,
    }


def otel_scope() -> dict[str, Any]:
    return {
        "name": OTEL_SCOPE_NAME,
        "version": OTEL_SCOPE_VERSION,
    }


def timestamp_nanos(value: datetime | str | None) -> str:
    if value is None:
        dt = datetime.now(UTC)
    elif isinstance(value, datetime):
        dt = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    seconds = calendar.timegm(dt.timetuple())
    return str((seconds * 1_000_000_000) + (dt.microsecond * 1000))


def event_name(event_type: str) -> str:
    cleaned = str(event_type or "").strip().replace("_", ".")
    return f"rlmbenchy.{cleaned}" if cleaned else "rlmbenchy.event"


def infer_genai_provider(model: Any) -> str:
    text = str(model or "").strip().lower()
    if not text:
        return "unknown"
    if text.startswith("openrouter/"):
        text = text.removeprefix("openrouter/")
    provider = text.split("/", 1)[0]
    aliases = {
        "anthropic": "anthropic",
        "aws": "aws.bedrock",
        "bedrock": "aws.bedrock",
        "chatgpt": "openai",
        "cohere": "cohere",
        "deepseek": "deepseek",
        "gemini": "gcp.gemini",
        "google": "gcp.gemini",
        "groq": "groq",
        "mistral": "mistral_ai",
        "mistral_ai": "mistral_ai",
        "openai": "openai",
        "perplexity": "perplexity",
        "xai": "x_ai",
        "x_ai": "x_ai",
    }
    return aliases.get(provider, provider or "unknown")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _put_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value is not _MISSING:
        target[key] = value


def _server_address(api_base: Any) -> str | None:
    text = str(api_base or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    return parsed.hostname or text


def _request_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("request_kwargs")
    return dict(value) if isinstance(value, dict) else {}


def attributes_for_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "").strip()
    data = _mapping(event.get("data"))
    stats = _mapping(event.get("stats"))
    summary = _mapping(event.get("summary"))
    attrs: dict[str, Any] = {
        "rlmbenchy.event_type": event_type,
        "rlmbenchy.event_id": event.get("event_id"),
        "rlmbenchy.event_seq": event.get("event_seq"),
        "rlmbenchy.run_id": event.get("run_id"),
        "rlmbenchy.log.schema_version": OTEL_SCHEMA_VERSION,
    }
    _put_if_present(attrs, "rlmbenchy.task_id", event.get("task_id"))
    _put_if_present(attrs, "rlmbenchy.step_index", event.get("step_index"))
    _put_if_present(attrs, "rlmbenchy.call_id", event.get("call_id"))
    _put_if_present(attrs, "rlmbenchy.parent_call_id", event.get("parent_call_id"))
    _put_if_present(attrs, "rlmbenchy.run.elapsed_ms", stats.get("run_elapsed_ms"))

    for key in ("status", "stop_reason", "error_type"):
        value = data.get(key, _MISSING)
        _put_if_present(attrs, f"rlmbenchy.{key}", value)

    if event_type.startswith(("llm.", "subllm.")):
        model = data.get("model") or data.get("request_model")
        attrs["gen_ai.operation.name"] = "chat"
        attrs["gen_ai.provider.name"] = infer_genai_provider(model)
        _put_if_present(attrs, "gen_ai.request.model", model)
        kwargs = _request_kwargs(data)
        for source, target in (
            ("temperature", "gen_ai.request.temperature"),
            ("top_p", "gen_ai.request.top_p"),
            ("top_k", "gen_ai.request.top_k"),
            ("max_tokens", "gen_ai.request.max_tokens"),
            ("seed", "gen_ai.request.seed"),
            ("stream", "gen_ai.request.stream"),
            ("presence_penalty", "gen_ai.request.presence_penalty"),
            ("frequency_penalty", "gen_ai.request.frequency_penalty"),
        ):
            _put_if_present(attrs, target, kwargs.get(source, _MISSING))
        _put_if_present(attrs, "gen_ai.usage.input_tokens", stats.get("prompt_tokens"))
        _put_if_present(
            attrs, "gen_ai.usage.output_tokens", stats.get("generated_tokens")
        )
        finish_reason = data.get("finish_reason")
        if finish_reason is not None:
            attrs["gen_ai.response.finish_reasons"] = [str(finish_reason)]
        _put_if_present(
            attrs, "rlmbenchy.gen_ai.total_tokens", stats.get("total_tokens")
        )
        _put_if_present(attrs, "rlmbenchy.gen_ai.cost_usd", stats.get("cost_usd"))
        _put_if_present(attrs, "rlmbenchy.prompt_chars", stats.get("prompt_chars"))
        _put_if_present(
            attrs, "rlmbenchy.response.preview", summary.get("response_preview")
        )

    if event_type.startswith("tool."):
        tool_name = data.get("tool_name")
        attrs["gen_ai.operation.name"] = "execute_tool"
        _put_if_present(attrs, "gen_ai.tool.name", tool_name)
        _put_if_present(attrs, "gen_ai.tool.call.id", event.get("call_id"))

    if event_type.startswith("repl."):
        attrs["rpc.system.name"] = "jsonrpc"
        attrs["jsonrpc.protocol.version"] = "2.0"
        attrs["rpc.method"] = "execute"
        _put_if_present(attrs, "jsonrpc.request.id", event.get("call_id"))
        if event_type == "repl.error":
            _put_if_present(attrs, "rpc.response.status_code", "-32000")
        elif event_type in {"repl.response", "repl.final"}:
            attrs["rpc.response.status_code"] = "OK"
        code = data.get("code")
        output = data.get("output")
        if isinstance(code, str):
            attrs["rlmbenchy.repl.code_chars"] = len(code)
        if isinstance(output, str):
            attrs["rlmbenchy.repl.output_chars"] = len(output)
        if event_type == "repl.final":
            attrs["rlmbenchy.repl.final"] = True

    error_type = data.get("error_type") or data.get("error")
    if event_type.endswith(".error") or str(data.get("status") or "") == "error":
        attrs["error.type"] = str(error_type or "_OTHER")
        _put_if_present(
            attrs,
            "exception.message",
            data.get("error_message") or data.get("error"),
        )

    api_base = data.get("api_base")
    if api_base:
        _put_if_present(attrs, "server.address", _server_address(api_base))
        attrs["rlmbenchy.api_base"] = api_base

    return {str(key): value for key, value in attrs.items() if value is not None}


def span_event_from_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "").strip()
    return {
        "name": event_name(event_type),
        "time": event["ts"],
        "time_unix_nano": timestamp_nanos(str(event["ts"])),
        "attributes": {
            **attributes_for_event(event),
            "rlmbenchy.data": _mapping(event.get("data")),
            "rlmbenchy.stats": _mapping(event.get("stats")),
            "rlmbenchy.summary": _mapping(event.get("summary")),
        },
    }


def metric_points_from_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    event_type = str(event.get("event_type") or "").strip()
    data = _mapping(event.get("data"))
    stats = _mapping(event.get("stats"))
    if (
        not event_type.endswith((".response", ".error", ".finished", ".final"))
        and event_type != "task.evaluated"
    ):
        return []

    base_attrs = attributes_for_event(event)
    points: list[dict[str, Any]] = []

    if event_type.startswith(("llm.", "subllm.")):
        for token_type, stat_name in (
            ("input", "prompt_tokens"),
            ("output", "generated_tokens"),
        ):
            value = _safe_int(stats.get(stat_name))
            if value is not None:
                attrs = {**base_attrs, "gen_ai.token.type": token_type}
                points.append(
                    {
                        "name": "gen_ai.client.token.usage",
                        "description": "Number of input and output tokens used.",
                        "unit": "{token}",
                        "instrument_type": "histogram",
                        "value": value,
                        "attributes": attrs,
                    }
                )
        elapsed_ms = _safe_float(stats.get("elapsed_ms"))
        if elapsed_ms is not None:
            points.append(
                {
                    "name": "gen_ai.client.operation.duration",
                    "description": "GenAI operation duration.",
                    "unit": "s",
                    "instrument_type": "histogram",
                    "value": elapsed_ms / 1000.0,
                    "attributes": base_attrs,
                }
            )
        cost = _safe_float(stats.get("cost_usd"))
        if cost is not None:
            points.append(
                {
                    "name": "rlmbenchy.gen_ai.client.cost",
                    "description": "Best-effort provider cost reported for a GenAI call.",
                    "unit": "USD",
                    "instrument_type": "sum",
                    "value": cost,
                    "attributes": base_attrs,
                }
            )

    elapsed_ms = _safe_float(stats.get("elapsed_ms"))
    if elapsed_ms is not None and event_type in {
        "run.finished",
        "task.finished",
        "step.finished",
        "repl.response",
        "repl.error",
        "repl.final",
        "tool.response",
        "tool.error",
    }:
        duration_name = (
            event_type.replace(".finished", "")
            .replace(".response", "")
            .replace(".error", "")
            .replace(".final", "")
        )
        points.append(
            {
                "name": f"rlmbenchy.{duration_name}.duration",
                "description": f"RLMBenchy {duration_name} duration.",
                "unit": "s",
                "instrument_type": "histogram",
                "value": elapsed_ms / 1000.0,
                "attributes": base_attrs,
            }
        )

    if event_type == "task.evaluated" and "correctness" in data:
        correctness = data.get("correctness")
        if correctness is not None:
            points.append(
                {
                    "name": "rlmbenchy.task.correctness",
                    "description": "Task correctness score coerced to 0 or 1 when available.",
                    "unit": "1",
                    "instrument_type": "gauge",
                    "value": 1 if correctness is True else 0,
                    "attributes": base_attrs,
                }
            )
    return points


def _event_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("event_type"),
        entry.get("ts"),
        entry.get("run_id"),
        entry.get("task_id"),
        entry.get("step_index"),
        entry.get("call_id"),
    )


def _context_from_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for attr_key, domain_key in (
        ("rlmbenchy.run_id", "run_id"),
        ("rlmbenchy.task_id", "task_id"),
        ("rlmbenchy.step_index", "step_index"),
        ("rlmbenchy.call_id", "call_id"),
        ("rlmbenchy.parent_call_id", "parent_call_id"),
    ):
        if attr_key in attrs:
            context[domain_key] = attrs[attr_key]
    return context


def _domain_event_from_attrs(
    *,
    attrs: dict[str, Any],
    ts: str,
    default_event_id: str,
    default_seq: int,
) -> dict[str, Any]:
    event_type = str(attrs.get("rlmbenchy.event_type") or "").strip()
    entry: dict[str, Any] = {
        "event_id": attrs.get("rlmbenchy.event_id") or default_event_id,
        "seq": _safe_int(attrs.get("rlmbenchy.event_seq")) or default_seq,
        "event_type": event_type,
        "ts": ts,
        "run_id": attrs.get("rlmbenchy.run_id"),
        "data": _mapping(attrs.get("rlmbenchy.data")),
        "stats": _mapping(attrs.get("rlmbenchy.stats")),
        "summary": _mapping(attrs.get("rlmbenchy.summary")),
    }
    entry.update(_context_from_attrs(attrs))
    return {key: value for key, value in entry.items() if value is not None}


def _domain_event_from_log(
    record: dict[str, Any], default_seq: int
) -> dict[str, Any] | None:
    attrs = _mapping(record.get("attributes"))
    body = _mapping(record.get("body"))
    if "rlmbenchy.data" not in attrs:
        attrs["rlmbenchy.data"] = _mapping(body.get("data"))
    if "rlmbenchy.stats" not in attrs:
        attrs["rlmbenchy.stats"] = _mapping(body.get("stats"))
    if "rlmbenchy.summary" not in attrs:
        attrs["rlmbenchy.summary"] = _mapping(body.get("summary"))
    if "rlmbenchy.event_type" not in attrs:
        attrs["rlmbenchy.event_type"] = record.get("event_name", "").removeprefix(
            "rlmbenchy."
        )
    event_type = str(attrs.get("rlmbenchy.event_type") or "").strip()
    if not event_type:
        return None
    ts = str(record.get("time") or record.get("observed_time") or "")
    if not ts:
        return None
    return _domain_event_from_attrs(
        attrs=attrs,
        ts=ts,
        default_event_id=str(record.get("event_id") or record.get("record_id") or ""),
        default_seq=default_seq,
    )


def _domain_events_from_span(
    record: dict[str, Any], default_seq: int
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, span_event in enumerate(record.get("events") or [], start=1):
        if not isinstance(span_event, dict):
            continue
        attrs = _mapping(span_event.get("attributes"))
        if not str(attrs.get("rlmbenchy.event_type") or "").strip():
            continue
        ts = str(span_event.get("time") or "")
        if not ts:
            continue
        entries.append(
            _domain_event_from_attrs(
                attrs=attrs,
                ts=ts,
                default_event_id=f"{record.get('record_id')}:event:{index}",
                default_seq=default_seq + index,
            )
        )
    return entries


def domain_events_from_otel_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for default_seq, record in enumerate(records, start=1):
        if not is_otel_record(record) or record.get("record_type") != "log":
            continue
        entry = _domain_event_from_log(record, default_seq)
        if entry is None:
            continue
        key = _event_key(entry)
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)

    for default_seq, record in enumerate(records, start=1 + len(entries)):
        if not is_otel_record(record) or record.get("record_type") != "span":
            continue
        for entry in _domain_events_from_span(record, default_seq):
            key = _event_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    entries.sort(
        key=lambda item: (_safe_int(item.get("seq")) or 0, str(item.get("ts") or ""))
    )
    return entries
