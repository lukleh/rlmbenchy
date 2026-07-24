from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rlmbenchy.logger.otel import (
    OTEL_SCHEMA_NAME,
    OTEL_SCHEMA_VERSION,
    attributes_for_event,
    event_name,
    otel_resource,
    otel_scope,
    span_id_for_key,
    timestamp_nanos,
    trace_id_for_run,
)


def _span_key(event: dict[str, Any]) -> tuple[Any, ...] | None:
    event_type = str(event.get("event_type") or "")
    if event_type.startswith("run."):
        return ("run", event.get("run_id"))
    if event_type.startswith("task."):
        return ("task", event.get("task_id"))
    if event_type.startswith("step."):
        return ("step", event.get("task_id"), event.get("step_index"))
    if event_type.startswith(("llm.", "subllm.", "repl.", "tool.")):
        return ("call", event.get("call_id"))
    return None


def _span_id_for_event(event: dict[str, Any]) -> str:
    run_id = str(event.get("run_id") or "run_fixture")
    key = _span_key(event)
    if key is None:
        return ""
    return span_id_for_key(run_id, ":".join(str(part) for part in key))


def _base_event(*, event_type: str, run_id: str, seq: int, ts: str) -> dict[str, Any]:
    return {
        "event_id": f"{run_id}:event:{seq}",
        "event_seq": seq,
        "seq": seq,
        "event_type": event_type,
        "ts": ts,
        "run_id": run_id,
        "data": {},
        "stats": {"run_elapsed_ms": seq - 1},
        "summary": {},
    }


def _log_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    seq = int(event["seq"])
    run_id = str(event["run_id"])
    attrs = attributes_for_event(event)
    is_error = str(event["event_type"]).endswith(".error")
    return {
        "schema_name": OTEL_SCHEMA_NAME,
        "schema_version": OTEL_SCHEMA_VERSION,
        "record_type": "log",
        "record_id": f"{run_id}:record:{seq}",
        "seq": seq,
        "run_id": run_id,
        "trace_id": trace_id_for_run(run_id),
        "resource": otel_resource(),
        "scope": otel_scope(),
        "event_id": event["event_id"],
        "event_seq": event["event_seq"],
        "time": event["ts"],
        "time_unix_nano": timestamp_nanos(str(event["ts"])),
        "observed_time": event["ts"],
        "observed_time_unix_nano": timestamp_nanos(str(event["ts"])),
        "span_id": _span_id_for_event(event),
        "severity_text": "ERROR" if is_error else "INFO",
        "severity_number": 17 if is_error else 9,
        "event_name": event_name(str(event["event_type"])),
        "body": {
            "data": event["data"],
            "stats": event["stats"],
            "summary": event["summary"],
        },
        "attributes": {
            **attrs,
            "rlmbenchy.data": event["data"],
            "rlmbenchy.stats": event["stats"],
            "rlmbenchy.summary": event["summary"],
        },
    }


def to_otel_fixture_records(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    current_run_id = "run_fixture"
    base_ts = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

    for seq, raw in enumerate(entries, start=1):
        if "type" in raw or "event" in raw:
            raise ValueError("Fixtures must use canonical domain event rows.")

        event_type = str(raw.get("event_type") or "").strip()
        if not event_type:
            raise ValueError("Fixtures must include `event_type`.")

        current_run_id = (
            str(raw.get("run_id") or current_run_id).strip() or current_run_id
        )
        ts = (
            str(raw.get("ts") or "").strip()
            or (base_ts + timedelta(seconds=seq - 1)).isoformat()
        )

        event = _base_event(
            event_type=event_type, run_id=current_run_id, seq=seq, ts=ts
        )

        for key in (
            "event_id",
            "event_seq",
            "seq",
            "event_type",
            "ts",
            "run_id",
            "task_id",
            "step_index",
            "call_id",
            "parent_call_id",
        ):
            if key in raw:
                event[key] = raw[key]

        for section in ("data", "stats", "summary"):
            payload = raw.get(section)
            if payload is None:
                continue
            if not isinstance(payload, dict):
                raise ValueError(f"Fixture section `{section}` must be a dict.")
            event[section] = {**event[section], **payload}

        if "run_elapsed_ms" in raw:
            event["stats"]["run_elapsed_ms"] = int(raw["run_elapsed_ms"])

        converted.append(_log_record_from_event(event))

    return converted
