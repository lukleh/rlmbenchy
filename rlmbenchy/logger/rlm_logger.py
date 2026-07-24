"""Trajectory logger for RLM runs.

The runtime still emits compact domain events internally.  This logger turns
them into OpenTelemetry-shaped JSONL records: logs for every event, spans for
paired lifecycle events, and metric records for usage/duration measurements.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from rlmbenchy.logger.otel import (
    OTEL_SCHEMA_NAME,
    OTEL_SCHEMA_VERSION,
    attributes_for_event,
    event_name,
    metric_points_from_event,
    otel_resource,
    otel_scope,
    span_event_from_event,
    span_id_for_key,
    timestamp_nanos,
    trace_id_for_run,
)
from rlmbenchy.rlm._response_extraction import safe_optional_int as _safe_optional_int


LOG_SCHEMA_NAME = OTEL_SCHEMA_NAME
LOG_SCHEMA_VERSION = OTEL_SCHEMA_VERSION


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, ModuleType):
        return f"<module '{value.__name__}'>"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        # Emit sets as sorted lists so asdict(config) preserves structure
        # for frozen fields like LMProfile.ignore_unsupported_parameters.
        return sorted((_serialize_value(item) for item in value), key=str)
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if callable(value):
        return f"<{type(value).__name__} '{getattr(value, '__name__', repr(value))}'>"
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


class RLMLogger:
    """Capture run metadata and events as OpenTelemetry-shaped JSONL."""

    def __init__(
        self,
        log_dir: str | Path | None = None,
        file_name: str = "rlmbenchy",
        on_event: Callable[[dict[str, Any]], None] | None = None,
        *,
        capture_trajectory: bool = False,
    ) -> None:
        """Create a logger.

        ``capture_trajectory`` keeps emitted OTel records in memory for callers
        that explicitly use ``get_trajectory()``. Disk logging and ``on_event``
        callbacks do not require it.
        """
        self._save_to_disk = log_dir is not None
        self.log_dir = str(log_dir) if log_dir is not None else None
        self._file_name = file_name
        self.log_file_path: str | None = None
        self.on_event = on_event
        self._capture_trajectory = capture_trajectory
        if self._save_to_disk and self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

        self._records: list[dict[str, Any]] = []
        self._open_spans: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._record_count = 0
        self._event_count = 0
        self._metadata_logged = False
        self._run_id: str | None = None
        self._trace_id: str | None = None
        self._started_at: datetime | None = None
        self._step_finished_count = 0
        self._rotate_log_file()

    def _rotate_log_file(self) -> None:
        self._run_id = str(uuid.uuid4())[:8]
        self._trace_id = trace_id_for_run(self._run_id)
        if self._save_to_disk and self.log_dir:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
            self.log_file_path = os.path.join(
                self.log_dir,
                f"{self._file_name}_{timestamp}_{self._run_id}.jsonl",
            )
        else:
            self.log_file_path = None

    def _ensure_run_id(self) -> str:
        if not self._run_id:
            self._rotate_log_file()
        assert self._run_id is not None
        return self._run_id

    def _ensure_trace_id(self) -> str:
        if not self._trace_id:
            self._trace_id = trace_id_for_run(self._ensure_run_id())
        return self._trace_id

    def _new_timestamp(self) -> datetime:
        current = datetime.now(timezone.utc)
        if self._started_at is None:
            self._started_at = current
        return current

    def _run_elapsed_ms(self, timestamp: datetime) -> int:
        if self._started_at is None:
            return 0
        elapsed_s = (timestamp - self._started_at).total_seconds()
        return max(0, int(round(elapsed_s * 1000.0)))

    def _next_record_index(self) -> int:
        self._record_count += 1
        return self._record_count

    def _next_event_index(self) -> int:
        self._event_count += 1
        return self._event_count

    def _base_record(self, record_type: str) -> dict[str, Any]:
        seq = self._next_record_index()
        return {
            "schema_name": LOG_SCHEMA_NAME,
            "schema_version": LOG_SCHEMA_VERSION,
            "record_type": record_type,
            "record_id": f"{self._ensure_run_id()}:record:{seq}",
            "seq": seq,
            "run_id": self._ensure_run_id(),
            "trace_id": self._ensure_trace_id(),
            "resource": otel_resource(),
            "scope": otel_scope(),
        }

    def _write_record(self, record: dict[str, Any]) -> None:
        if self._capture_trajectory:
            self._records.append(record)
        if self._save_to_disk and self.log_file_path:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
                f.write("\n")
        if self.on_event is not None:
            self.on_event(record)

    def _event_from_payload(
        self,
        payload: dict[str, Any],
        *,
        timestamp: datetime,
    ) -> dict[str, Any]:
        allowed_keys = {
            "event_type",
            "task_id",
            "step_index",
            "call_id",
            "parent_call_id",
            "data",
            "stats",
            "summary",
        }
        unknown_keys = sorted(
            str(key) for key in payload.keys() if str(key) not in allowed_keys
        )
        if unknown_keys:
            raise ValueError(
                "Telemetry payload contains unsupported top-level keys. "
                f"Allowed keys: {sorted(allowed_keys)}. Received extras: {unknown_keys}"
            )

        event_type = str(payload.get("event_type") or "").strip()
        if not event_type:
            raise ValueError("Telemetry payload must include a non-empty `event_type`.")

        data = payload.get("data", {})
        stats = payload.get("stats", {})
        summary = payload.get("summary", {})
        if not isinstance(data, dict):
            raise ValueError("Telemetry payload `data` must be a dict.")
        if not isinstance(stats, dict):
            raise ValueError("Telemetry payload `stats` must be a dict.")
        if not isinstance(summary, dict):
            raise ValueError("Telemetry payload `summary` must be a dict.")

        event_seq = self._next_event_index()
        task_id_raw = str(payload.get("task_id") or "").strip()
        call_id_raw = str(payload.get("call_id") or "").strip()
        parent_call_id_raw = str(payload.get("parent_call_id") or "").strip()
        event: dict[str, Any] = {
            "event_id": f"{self._ensure_run_id()}:event:{event_seq}",
            "event_seq": event_seq,
            "event_type": event_type,
            "ts": timestamp.isoformat(),
            "run_id": self._ensure_run_id(),
            "data": _serialize_value(data),
            "stats": {
                "run_elapsed_ms": self._run_elapsed_ms(timestamp),
                **_serialize_value(stats),
            },
            "summary": _serialize_value(summary),
        }
        if task_id_raw:
            event["task_id"] = task_id_raw
        step_index = _safe_optional_int(payload.get("step_index"))
        if step_index is not None:
            event["step_index"] = step_index
        if call_id_raw:
            event["call_id"] = call_id_raw
        if parent_call_id_raw:
            event["parent_call_id"] = parent_call_id_raw
        return event

    def _write_log_record(self, event: dict[str, Any]) -> None:
        attrs = attributes_for_event(event)
        span_id = self._span_id_for_event(event) or ""
        record = {
            **self._base_record("log"),
            "event_id": event["event_id"],
            "event_seq": event["event_seq"],
            "time": event["ts"],
            "time_unix_nano": timestamp_nanos(str(event["ts"])),
            "observed_time": event["ts"],
            "observed_time_unix_nano": timestamp_nanos(str(event["ts"])),
            "span_id": span_id,
            "severity_text": "ERROR"
            if str(event["event_type"]).endswith(".error")
            else "INFO",
            "severity_number": 17 if str(event["event_type"]).endswith(".error") else 9,
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
        self._write_record(record)

    def _write_metric_records(self, event: dict[str, Any]) -> None:
        points = metric_points_from_event(event)
        for point in points:
            record = {
                **self._base_record("metric"),
                "time": event["ts"],
                "time_unix_nano": timestamp_nanos(str(event["ts"])),
                **point,
            }
            self._write_record(record)

    def _span_key(self, event: dict[str, Any]) -> tuple[Any, ...] | None:
        event_type = str(event.get("event_type") or "")
        if event_type.startswith("run."):
            return ("run", self._ensure_run_id())
        if event_type.startswith("task."):
            return ("task", event.get("task_id"))
        if event_type.startswith("step."):
            return ("step", event.get("task_id"), event.get("step_index"))
        if event_type.startswith(("llm.", "subllm.", "repl.", "tool.")):
            return ("call", event.get("call_id"))
        return None

    def _parent_span_key(self, event: dict[str, Any]) -> tuple[Any, ...] | None:
        event_type = str(event.get("event_type") or "")
        if event_type.startswith("run."):
            return None
        if event_type.startswith("task."):
            return ("run", self._ensure_run_id())
        if event_type.startswith("step."):
            if event.get("task_id"):
                return ("task", event.get("task_id"))
            return ("run", self._ensure_run_id())
        if event.get("parent_call_id"):
            return ("call", event.get("parent_call_id"))
        if event.get("step_index") is not None:
            return ("step", event.get("task_id"), event.get("step_index"))
        if event.get("task_id"):
            return ("task", event.get("task_id"))
        return ("run", self._ensure_run_id())

    def _span_id_for_key(self, key: tuple[Any, ...] | None) -> str | None:
        if key is None:
            return None
        return span_id_for_key(
            self._ensure_run_id(), ":".join(str(part) for part in key)
        )

    def _span_id_for_event(self, event: dict[str, Any]) -> str | None:
        return self._span_id_for_key(self._span_key(event))

    def _span_name(
        self, start_event: dict[str, Any], end_event: dict[str, Any] | None = None
    ) -> str:
        event_type = str(start_event.get("event_type") or "")
        end_data = end_event.get("data", {}) if isinstance(end_event, dict) else {}
        start_data = start_event.get("data", {})
        data = end_data if isinstance(end_data, dict) and end_data else start_data
        if event_type.startswith("run."):
            return "rlmbenchy.run"
        if event_type.startswith("task."):
            return "rlmbenchy.task"
        if event_type.startswith("step."):
            return "rlmbenchy.step"
        if event_type.startswith(("llm.", "subllm.")):
            model = str(data.get("model") or start_data.get("model") or "").strip()
            return f"chat {model}" if model else "gen_ai.chat"
        if event_type.startswith("repl."):
            return "jsonrpc execute"
        if event_type.startswith("tool."):
            tool_name = str(
                data.get("tool_name") or start_data.get("tool_name") or ""
            ).strip()
            return f"execute_tool {tool_name}" if tool_name else "execute_tool"
        return event_type or "rlmbenchy.span"

    def _span_kind(self, event: dict[str, Any]) -> str:
        event_type = str(event.get("event_type") or "")
        if event_type.startswith(("llm.", "subllm.", "repl.")):
            return "CLIENT"
        return "INTERNAL"

    def _span_status(self, end_event: dict[str, Any]) -> dict[str, Any]:
        event_type = str(end_event.get("event_type") or "")
        raw_data = end_event.get("data")
        data: dict[str, Any] = dict(raw_data) if isinstance(raw_data, dict) else {}
        error_type = data.get("error_type") or data.get("error")
        if event_type.endswith(".error") or str(data.get("status") or "") == "error":
            return {
                "code": "ERROR",
                "message": str(data.get("error_message") or error_type or ""),
            }
        return {"code": "OK"}

    def _span_attributes(
        self,
        start_event: dict[str, Any],
        end_event: dict[str, Any],
    ) -> dict[str, Any]:
        attrs = attributes_for_event(start_event)
        for key, value in attributes_for_event(end_event).items():
            if key == "gen_ai.provider.name" and value == "unknown" and key in attrs:
                continue
            attrs[key] = value
        attrs["rlmbenchy.span.start_event_type"] = start_event["event_type"]
        attrs["rlmbenchy.span.end_event_type"] = end_event["event_type"]
        return attrs

    def _start_span(self, event: dict[str, Any]) -> None:
        key = self._span_key(event)
        if key is None:
            return
        self._open_spans[key] = event

    def _end_span(self, event: dict[str, Any]) -> None:
        key = self._span_key(event)
        if key is None:
            return
        start_event = self._open_spans.pop(key, None)
        if start_event is None:
            start_event = event
        parent_span_id = self._span_id_for_key(self._parent_span_key(start_event))
        span_id = self._span_id_for_key(key)
        if span_id is None:
            return
        record = {
            **self._base_record("span"),
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": self._span_name(start_event, event),
            "span_kind": self._span_kind(start_event),
            "start_time": start_event["ts"],
            "start_time_unix_nano": timestamp_nanos(str(start_event["ts"])),
            "end_time": event["ts"],
            "end_time_unix_nano": timestamp_nanos(str(event["ts"])),
            "status": self._span_status(event),
            "attributes": self._span_attributes(start_event, event),
            "events": [
                span_event_from_event(start_event),
                span_event_from_event(event),
            ],
        }
        self._write_record(record)

    @staticmethod
    def _is_span_start(event_type: str) -> bool:
        return event_type in {
            "run.started",
            "task.started",
            "step.started",
            "llm.request",
            "subllm.request",
            "repl.request",
            "tool.request",
        }

    @staticmethod
    def _is_span_end(event_type: str) -> bool:
        return event_type in {
            "run.finished",
            "task.finished",
            "step.finished",
            "llm.response",
            "llm.error",
            "subllm.response",
            "subllm.error",
            "repl.response",
            "repl.error",
            "repl.final",
            "tool.response",
            "tool.error",
        }

    def _capture_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "")
        if event_type == "step.finished":
            self._step_finished_count += 1

        self._write_log_record(event)
        self._write_metric_records(event)
        if self._is_span_start(event_type):
            self._start_span(event)
        if self._is_span_end(event_type):
            self._end_span(event)

    def log_metadata(self, metadata: dict[str, Any]) -> None:
        """Capture run metadata once per run."""
        if self._metadata_logged:
            return

        self._ensure_run_id()
        serialized = _serialize_value(metadata)
        self._metadata_logged = True

        data = dict(serialized)
        n_tasks = _safe_optional_int(data.pop("n_tasks", None))
        payload: dict[str, Any] = {
            "event_type": "run.started",
            "data": data,
            "stats": {},
            "summary": {},
        }
        if n_tasks is not None:
            payload["summary"] = {"n_tasks": n_tasks}
        event = self._event_from_payload(payload, timestamp=self._new_timestamp())
        self._capture_event(event)

    def log(self, iteration: dict[str, Any]) -> None:
        """Capture one canonical domain event as OpenTelemetry records."""
        timestamp = self._new_timestamp()
        payload = _serialize_value(iteration)
        event = self._event_from_payload(payload, timestamp=timestamp)
        self._capture_event(event)

    def log_run_result(self, result: dict[str, Any]) -> None:
        """Capture final run outcome."""
        timestamp = self._new_timestamp()
        serialized = _serialize_value(result)
        data: dict[str, Any] = {}
        stats: dict[str, Any] = {}

        if "stop_reason" in serialized:
            data["stop_reason"] = serialized["stop_reason"]
        elif "termination_reason" in serialized:
            data["stop_reason"] = serialized["termination_reason"]

        for key in ("status", "error_type", "error_message", "final_outputs"):
            if key in serialized:
                data[key] = serialized[key]

        elapsed = serialized.get("elapsed_ms")
        if elapsed is not None:
            stats["elapsed_ms"] = elapsed

        event = self._event_from_payload(
            {
                "event_type": "run.finished",
                "data": data,
                "stats": stats,
                "summary": {},
            },
            timestamp=timestamp,
        )
        self._capture_event(event)

    def get_trajectory(self) -> dict[str, Any] | None:
        """Return the in-memory OpenTelemetry-shaped records."""
        if not self._capture_trajectory or not self._metadata_logged:
            return None
        return {
            "schema_name": LOG_SCHEMA_NAME,
            "schema_version": LOG_SCHEMA_VERSION,
            "run_id": self._ensure_run_id(),
            "trace_id": self._ensure_trace_id(),
            "log_file_path": self.log_file_path,
            "records": list(self._records),
        }

    @property
    def iteration_count(self) -> int:
        return self._step_finished_count
