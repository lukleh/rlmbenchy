"""Shared telemetry projection helpers."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rlmbenchy.logger.coerce import coerce_int
from rlmbenchy.logger.coerce import coerce_int_or as _safe_int
from rlmbenchy.logger.log_files import find_log_files
from rlmbenchy.logger.otel import (
    OTEL_SCHEMA_NAME,
    domain_events_from_otel_records,
    is_otel_record,
)
from rlmbenchy.logger.preview import (
    build_narrative_sections as _build_narrative_sections,
)
from rlmbenchy.logger.preview import call_request_preview as _call_request_preview
from rlmbenchy.logger.preview import call_response_preview as _call_response_preview
from rlmbenchy.logger.preview import snippet as _snippet
from rlmbenchy.logger.step_derivation import (
    extract_code_from_response as _extract_code_from_response,
)
from rlmbenchy.rlm._response_extraction import safe_optional_int as _safe_optional_int

CALL_EVENTS = {
    "llm.request",
    "llm.response",
    "llm.error",
    "tool.request",
    "tool.response",
    "tool.error",
    "subllm.request",
    "subllm.response",
    "subllm.error",
}
CALL_PAYLOAD_EXCLUDE_FIELDS = {
    "schema_name",
    "schema_version",
    "event_id",
    "seq",
    "event_type",
    "ts",
    "run_elapsed_ms",
    "run_id",
    "task_id",
    "step_index",
    "call_id",
    "data",
    "stats",
    "summary",
}
ERROR_STOP_REASONS = {
    "parse_failure",
    "empty_code",
    "execution_error",
}


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_values[lower])
    ratio = rank - lower
    return sorted_values[lower] * (1.0 - ratio) + sorted_values[upper] * ratio


def _normalize_observed(value: Any) -> Any:
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _flatten_domain_event(entry: dict[str, Any]) -> dict[str, Any]:
    flat = dict(entry)
    flat.update(_mapping(entry.get("data")))
    flat.update(_mapping(entry.get("stats")))
    flat.update(_mapping(entry.get("summary")))
    return flat


def _task_prompt_from_inputs(task_inputs: Any) -> str:
    if isinstance(task_inputs, str):
        return task_inputs.strip()
    if not isinstance(task_inputs, dict):
        return ""
    for key in ("task", "query", "question", "prompt", "instruction", "input"):
        value = task_inputs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    raw_entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        raw_entries.append(payload)

    if not raw_entries:
        return []

    if not all(is_otel_record(payload) for payload in raw_entries):
        raise ValueError(
            f"Unsupported log schema in {path.name}. Expected {OTEL_SCHEMA_NAME}."
        )

    return [
        _flatten_domain_event(entry)
        for entry in domain_events_from_otel_records(raw_entries)
    ]


def _usage_summary_from_mapping(
    payload: Any,
    *,
    infer_total: bool,
) -> dict[str, int]:
    data = payload if isinstance(payload, dict) else {}
    prompt_tokens = _safe_int(data.get("prompt_tokens"), default=0)
    generated_tokens = _safe_int(data.get("generated_tokens"), default=0)
    total_tokens_raw = coerce_int(data.get("total_tokens"))
    total_tokens = 0 if total_tokens_raw is None else total_tokens_raw
    if infer_total and total_tokens_raw is None:
        total_tokens = prompt_tokens + generated_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "total_tokens": total_tokens,
    }


def _usage_from_entry(entry: dict[str, Any]) -> dict[str, int]:
    event_type = str(entry.get("event_type") or "").strip()
    if event_type not in {"llm.response", "subllm.response"}:
        return _usage_summary_from_mapping({}, infer_total=False)
    return _usage_summary_from_mapping(entry, infer_total=True)


def _normalize_usage_summary(payload: Any) -> dict[str, int]:
    return _usage_summary_from_mapping(payload, infer_total=True)


def _sum_usage_summaries(items: list[dict[str, Any]]) -> dict[str, int]:
    normalized = [
        _usage_summary_from_mapping(item, infer_total=False) for item in items
    ]
    prompt_tokens = sum(item["prompt_tokens"] for item in normalized)
    generated_tokens = sum(item["generated_tokens"] for item in normalized)
    total_tokens = sum(item["total_tokens"] for item in normalized)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + generated_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "total_tokens": total_tokens,
    }


def _usage_summary_from_entries(entries: list[dict[str, Any]]) -> dict[str, int]:
    return _sum_usage_summaries([_usage_from_entry(entry) for entry in entries])


def _normalize_activity_summary(payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    event_counts_raw = data.get("event_counts")
    event_counts = {
        str(event_name): _safe_int(count, default=0)
        for event_name, count in (
            event_counts_raw.items() if isinstance(event_counts_raw, dict) else []
        )
    }
    event_count = _safe_int(data.get("event_count"), default=0)
    if event_count <= 0 and event_counts:
        event_count = sum(event_counts.values())
    return {
        "event_count": event_count,
        "last_event": str(data.get("last_event") or ""),
        "iteration_count": _safe_int(data.get("iteration_count"), default=0),
        "llm_calls": _safe_int(data.get("llm_calls"), default=0),
        "llm_errors": _safe_int(data.get("llm_errors"), default=0),
        "model_steps": _safe_int(data.get("model_steps"), default=0),
        "repl_calls": _safe_int(data.get("repl_calls"), default=0),
        "repl_errors": _safe_int(data.get("repl_errors"), default=0),
        "tool_calls": _safe_int(data.get("tool_calls"), default=0),
        "tool_call_errors": _safe_int(data.get("tool_call_errors"), default=0),
        "subllm_calls": _safe_int(data.get("subllm_calls"), default=0),
        "subllm_errors": _safe_int(data.get("subllm_errors"), default=0),
        "final_signals": _safe_int(data.get("final_signals"), default=0),
        "event_counts": {
            event_name: count for event_name, count in sorted(event_counts.items())
        },
    }


def _sum_activity_summaries(
    items: list[dict[str, Any]], *, last_event: str = ""
) -> dict[str, Any]:
    event_counts: Counter[str] = Counter()
    summary: dict[str, Any] = {
        "event_count": 0,
        "last_event": last_event,
        "iteration_count": 0,
        "llm_calls": 0,
        "llm_errors": 0,
        "model_steps": 0,
        "repl_calls": 0,
        "repl_errors": 0,
        "tool_calls": 0,
        "tool_call_errors": 0,
        "subllm_calls": 0,
        "subllm_errors": 0,
        "final_signals": 0,
    }
    for item in items:
        summary["event_count"] += _safe_int(item.get("event_count"), default=0)
        summary["iteration_count"] += _safe_int(item.get("iteration_count"), default=0)
        summary["llm_calls"] += _safe_int(item.get("llm_calls"), default=0)
        summary["llm_errors"] += _safe_int(item.get("llm_errors"), default=0)
        summary["model_steps"] += _safe_int(item.get("model_steps"), default=0)
        summary["repl_calls"] += _safe_int(item.get("repl_calls"), default=0)
        summary["repl_errors"] += _safe_int(item.get("repl_errors"), default=0)
        summary["tool_calls"] += _safe_int(item.get("tool_calls"), default=0)
        summary["tool_call_errors"] += _safe_int(
            item.get("tool_call_errors"), default=0
        )
        summary["subllm_calls"] += _safe_int(item.get("subllm_calls"), default=0)
        summary["subllm_errors"] += _safe_int(item.get("subllm_errors"), default=0)
        summary["final_signals"] += _safe_int(item.get("final_signals"), default=0)
        for event_name, count in dict(item.get("event_counts") or {}).items():
            event_counts[str(event_name)] += _safe_int(count, default=0)
        item_last_event = str(item.get("last_event") or "").strip()
        if item_last_event:
            summary["last_event"] = item_last_event
    summary["event_counts"] = {
        event_name: count for event_name, count in sorted(event_counts.items())
    }
    return summary


def _activity_summary_from_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts: Counter[str] = Counter()
    max_step_index = 0
    last_event_type = ""
    for entry in entries:
        event_type = str(entry.get("event_type") or "").strip()
        if event_type:
            event_counts[event_type] += 1
            last_event_type = event_type
        max_step_index = max(
            max_step_index, _safe_int(entry.get("step_index"), default=0)
        )
    return {
        "event_count": len(entries),
        "last_event": last_event_type,
        "iteration_count": max_step_index,
        "llm_calls": int(event_counts.get("llm.response", 0))
        + int(event_counts.get("llm.error", 0)),
        "llm_errors": int(event_counts.get("llm.error", 0)),
        "model_steps": int(event_counts.get("step.started", 0)),
        "repl_calls": int(event_counts.get("repl.request", 0)),
        "repl_errors": int(event_counts.get("repl.error", 0)),
        "tool_calls": int(event_counts.get("tool.request", 0)),
        "tool_call_errors": int(event_counts.get("tool.error", 0)),
        "subllm_calls": int(event_counts.get("subllm.request", 0)),
        "subllm_errors": int(event_counts.get("subllm.error", 0)),
        "final_signals": int(event_counts.get("repl.final", 0)),
        "event_counts": {
            event_name: count for event_name, count in sorted(event_counts.items())
        },
    }


def _derive_summary_state(
    *,
    run_finished: dict[str, Any],
    has_run_result: bool,
    task_count: int,
    finalized_count: int,
    tasks_with_exec_error: int,
) -> tuple[str, str]:
    if not has_run_result:
        return "running", "running"

    stop_reason = (
        str(
            run_finished.get("stop_reason")
            or run_finished.get("termination_reason")
            or ""
        )
        .strip()
        .lower()
    )
    if not stop_reason:
        if tasks_with_exec_error > 0:
            stop_reason = "execution_error"
        elif task_count > 0 and finalized_count == task_count:
            stop_reason = "success"
        else:
            stop_reason = "no_final"
    elif stop_reason == "no_final" and tasks_with_exec_error > 0:
        stop_reason = "execution_error"

    status_raw = str(run_finished.get("status") or "").strip().lower()
    if status_raw in {"running", "partial", "error", "failed", "failure"}:
        return status_raw, stop_reason

    if stop_reason == "success":
        if tasks_with_exec_error > 0:
            return "error", stop_reason
        if task_count > 0 and finalized_count < task_count:
            return "partial", stop_reason
        return "success", stop_reason
    if stop_reason in ERROR_STOP_REASONS:
        return "error", stop_reason
    if stop_reason == "running":
        return "running", stop_reason
    if stop_reason == "no_final":
        return ("error" if tasks_with_exec_error > 0 else "partial"), stop_reason
    return status_raw or "partial", stop_reason


def _call_kind(event_type: str) -> str | None:
    if event_type.startswith("llm."):
        return "lm"
    if event_type.startswith("tool."):
        return "tool"
    if event_type.startswith("subllm."):
        return "llm_query"
    return None


def _call_name(kind: str, entry: dict[str, Any]) -> str:
    if kind == "lm":
        model = str(entry.get("model") or "").strip()
        return model or "main model"
    if kind == "llm_query":
        return str(entry.get("tool_name") or "llm_query")
    return str(entry.get("tool_name") or "<unknown>")


def _call_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in entry.items()
        if str(key) not in CALL_PAYLOAD_EXCLUDE_FIELDS
    }


def _call_usage(entry: dict[str, Any]) -> dict[str, int | None]:
    prompt_tokens = _safe_optional_int(entry.get("prompt_tokens"))
    generated_tokens = _safe_optional_int(entry.get("generated_tokens"))
    total_tokens = _safe_optional_int(entry.get("total_tokens"))
    if (
        total_tokens is None
        and prompt_tokens is not None
        and generated_tokens is not None
    ):
        total_tokens = prompt_tokens + generated_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "total_tokens": total_tokens,
    }


def _build_step_calls(step_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_call: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in step_entries:
        event_type = str(entry.get("event_type") or "").strip()
        if event_type not in CALL_EVENTS:
            continue
        call_id = str(entry.get("call_id") or "").strip()
        if not call_id:
            raise ValueError(
                f"Call event `{event_type}` is missing required `call_id`."
            )
        by_call[call_id].append(entry)

    calls: list[dict[str, Any]] = []
    ordered_call_ids = sorted(
        by_call,
        key=lambda call_id: min(
            _safe_int(event.get("seq"), default=0) for event in by_call[call_id]
        ),
    )
    for call_id in ordered_call_ids:
        events = by_call[call_id]
        req = next(
            (e for e in events if str(e.get("event_type") or "").endswith(".request")),
            None,
        )
        resp = next(
            (
                e
                for e in events
                if str(e.get("event_type") or "").endswith((".response", ".error"))
            ),
            None,
        )
        ref = req or resp
        if ref is None:
            continue
        kind = _call_kind(str(ref.get("event_type") or ""))
        if kind is None:
            continue

        call: dict[str, Any] = {
            "call_id": call_id,
            "index": len(calls) + 1,
            "kind": kind,
            "name": _call_name(kind, ref),
            "status": "pending",
            "request_event": "",
            "response_event": "",
            "request": None,
            "response": None,
            "request_preview": "",
            "response_preview": "",
            "request_timestamp": "",
            "response_timestamp": "",
            "duration_ms": None,
            "request_index": _safe_optional_int(ref.get("request_index")),
            "prompt_tokens": None,
            "generated_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "error": "",
        }
        model = str(ref.get("model") or "").strip()
        if model:
            call["model"] = model

        if req is not None:
            call["request_event"] = str(req.get("event_type") or "")
            call["request"] = _call_payload(req)
            call["request_preview"] = _call_request_preview(kind, req)
            call["request_timestamp"] = str(req.get("ts") or "")

        if resp is not None:
            resp_event = str(resp.get("event_type") or "")
            call["status"] = "error" if resp_event.endswith(".error") else "ok"
            call["response_event"] = resp_event
            call["response"] = _call_payload(resp)
            call["response_preview"] = _call_response_preview(kind, resp)
            call["response_timestamp"] = str(resp.get("ts") or "")
            call["duration_ms"] = _safe_optional_int(resp.get("elapsed_ms"))

            usage = _call_usage(resp)
            for usage_key, usage_value in usage.items():
                if usage_value is not None:
                    call[usage_key] = usage_value

            cost_usd = resp.get("cost_usd")
            if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool):
                call["cost_usd"] = round(float(cost_usd), 8)

            error = str(resp.get("error_message") or "").strip()
            if error:
                call["error"] = error

        calls.append(call)

    return calls


def _step_status(step: dict[str, Any]) -> str:
    if str(step.get("exec_error") or "").strip():
        return "error"
    if bool(step.get("finalized")):
        return "final"
    return "pending"


def _build_task_steps(
    task_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_step: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in task_entries:
        step_index = _safe_int(entry.get("step_index"), default=0)
        if step_index > 0:
            by_step[step_index].append(entry)

    if not by_step:
        return []

    steps: list[dict[str, Any]] = []
    for step_index in sorted(by_step):
        entries = by_step[step_index]
        first_entry = entries[0]
        step_started = next(
            (e for e in entries if str(e.get("event_type") or "") == "step.started"), {}
        )
        step_finished = next(
            (e for e in entries if str(e.get("event_type") or "") == "step.finished"),
            {},
        )
        repl_request = next(
            (e for e in entries if str(e.get("event_type") or "") == "repl.request"), {}
        )
        repl_response = next(
            (
                e
                for e in reversed(entries)
                if str(e.get("event_type") or "") in {"repl.response", "repl.error"}
            ),
            {},
        )
        repl_final = next(
            (e for e in entries if str(e.get("event_type") or "") == "repl.final"), {}
        )
        llm_resp = next(
            (e for e in entries if str(e.get("event_type") or "") == "llm.response"), {}
        )
        calls = _build_step_calls(entries)

        # LOGS.md strictness: canonical fields are read from their declared
        # bucket (data or stats). Legacy placement in `summary` is treated
        # as absent — pre-canonical logs no longer normalize into finalized
        # steps.
        step_finished_data = dict(step_finished.get("data") or {})
        step_finished_stats = dict(step_finished.get("stats") or {})
        repl_final_data = dict(repl_final.get("data") or {})
        repl_request_data = dict(repl_request.get("data") or {})
        repl_response_data = dict(repl_response.get("data") or {})
        llm_resp_data = dict(llm_resp.get("data") or {})

        # Narrative: derive from child events only (never from step.finished)
        reasoning = str(llm_resp_data.get("reasoning_text") or "").strip()
        code = str(repl_request_data.get("code") or "").strip()
        if not code:
            code = _extract_code_from_response(llm_resp_data)
        observed_raw = str(
            repl_response_data.get("output") or repl_response_data.get("stdout") or ""
        )
        exec_error = str(
            repl_response_data.get("error")
            or repl_response_data.get("error_message")
            or ""
        ).strip()

        final_signal = bool(step_finished_data.get("final_signal"))
        final_outputs = None
        if final_signal:
            # Union, not fallback: exactly one of these shapes is present per
            # finalized step. SUBMIT path emits `repl.final.data.final_outputs`;
            # extract-fallback path has no REPL call and instead carries
            # `final_outputs` on `step.finished.data`. Picking between them
            # is disambiguation by event presence, not "prefer explicit, fall
            # back to derived" (see docs/LOGS.md invariant).
            if repl_final:
                final_outputs = repl_final_data.get("final_outputs")
            else:
                final_outputs = step_finished_data.get("final_outputs")
        finalized = final_outputs is not None

        parse_success = (
            bool(step_finished_data.get("parse_success"))
            if "parse_success" in step_finished_data
            else bool(code)
        )

        call_counts = {"lm": 0, "tool": 0, "llm_query": 0}
        for call in calls:
            kind = str(call.get("kind") or "")
            if kind in call_counts:
                call_counts[kind] += 1

        step: dict[str, Any] = {
            "task_id": str(first_entry.get("task_id") or ""),
            "step_index": step_index,
            "timestamp": str(step_started.get("ts") or first_entry.get("ts") or ""),
            "reasoning": reasoning,
            "code": code,
            "observed": _normalize_observed(observed_raw)
            if observed_raw not in (None, "")
            else "",
            "finalized": finalized,
            "final_outputs": final_outputs,
            "exec_error": exec_error,
            "parse_success": parse_success,
            "parse_strategy": str(
                step_finished_data.get("parse_strategy") or ""
            ).strip(),
            "parse_failure_type": str(
                step_finished_data.get("parse_failure_type") or ""
            ).strip()
            or None,
            "code_block_count": _safe_int(
                step_finished_data.get("code_block_count"), default=0
            ),
            "multiple_code_blocks": bool(
                step_finished_data.get("multiple_code_blocks")
            ),
            "latency_ms": _safe_int(step_finished_stats.get("elapsed_ms")),
            "calls": calls,
            "call_summary": call_counts,
            "events": sorted({str(e.get("event_type") or "") for e in entries} - {""}),
            "event_count": len(entries),
        }
        if step["code_block_count"] > 1:
            step["multiple_code_blocks"] = True
        step["stop_reason"] = step_finished_data.get("stop_reason")
        emitted_status = str(step_finished_data.get("status") or "").strip()
        # The emitter uses "success" for the SUBMIT / extract-fallback case;
        # viewers expect "final" to select the finalized styling.
        if emitted_status == "success":
            step["status"] = "final"
        else:
            step["status"] = emitted_status or _step_status(step)
        step["summary"] = {
            "status": step["status"],
            "stop_reason": step["stop_reason"],
            "parse_success": bool(step["parse_success"]),
            "finalized": bool(step["finalized"]),
            "exec_error": str(step["exec_error"] or ""),
            "latency_ms": _safe_int(step.get("latency_ms")),
            "code_block_count": int(step.get("code_block_count") or 0),
            "multiple_code_blocks": bool(step.get("multiple_code_blocks")),
            "call_summary": dict(call_counts),
            "event_count": len(entries),
        }
        steps.append(step)

    for index, step in enumerate(steps, start=1):
        step["index"] = index
    return steps


def _build_tasks(
    entries_by_task: dict[str, list[dict[str, Any]]],
    *,
    task_evaluations_by_task: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task_id, task_entries in entries_by_task.items():
        task_evaluated = dict((task_evaluations_by_task or {}).get(task_id) or {})
        eval_data = dict(task_evaluated.get("data") or {})
        started = next(
            (
                e
                for e in task_entries
                if str(e.get("event_type") or "") == "task.started"
            ),
            {},
        )
        finished = next(
            (
                e
                for e in task_entries
                if str(e.get("event_type") or "") == "task.finished"
            ),
            {},
        )
        steps = _build_task_steps(task_entries)
        last_step = steps[-1] if steps else {}

        task_inputs = started.get("task_inputs") or {}
        task_prompt = str(
            started.get("query") or _task_prompt_from_inputs(task_inputs) or ""
        ).strip()
        reasoning = str(last_step.get("reasoning") or "").strip()
        code = str(last_step.get("code") or "").strip()
        observed_raw = eval_data.get("observed") or finished.get("observed")
        if observed_raw in (None, ""):
            observed_raw = last_step.get("observed")
        observed = (
            _normalize_observed(observed_raw) if observed_raw not in (None, "") else ""
        )

        final_outputs = finished.get("final_outputs")
        if final_outputs is None:
            final_outputs = last_step.get("final_outputs")

        finalized_raw = finished.get("finalized")
        finalized = (
            bool(finalized_raw)
            if finalized_raw is not None
            else final_outputs is not None
        )

        exec_error = str(
            finished.get("exec_error") or last_step.get("exec_error") or ""
        ).strip()

        latency_ms = _safe_int(
            finished.get("elapsed_ms"),
            default=sum(_safe_int(step.get("latency_ms"), default=0) for step in steps),
        )

        parse_success = (
            bool(finished.get("parse_success"))
            if "parse_success" in finished
            else not bool(exec_error)
        )

        usage_summary = _normalize_usage_summary(
            _usage_summary_from_entries(task_entries)
        )
        activity_summary = _normalize_activity_summary(
            _activity_summary_from_entries(task_entries)
        )

        task_order = _safe_int(started.get("task_index"), default=10000)
        task_status = str(finished.get("status") or "").strip() or (
            "success"
            if finalized and not exec_error
            else ("error" if exec_error else "partial")
        )
        task_stop_reason = str(
            finished.get("stop_reason") or last_step.get("stop_reason") or ""
        ).strip()
        if not task_stop_reason:
            task_stop_reason = (
                "success"
                if finalized and not exec_error
                else ("execution_error" if exec_error else "running")
            )

        if not steps:
            synthetic_step: dict[str, Any] = {
                "task_id": task_id,
                "step_index": 0,
                "timestamp": str(started.get("ts") or finished.get("ts") or ""),
                "reasoning": reasoning,
                "code": code,
                "observed": observed,
                "finalized": finalized,
                "final_outputs": final_outputs,
                "exec_error": exec_error,
                "parse_success": parse_success,
                "latency_ms": latency_ms,
                "calls": [],
                "call_summary": {"lm": 0, "tool": 0, "llm_query": 0},
                "events": [],
                "event_count": 0,
                "stop_reason": task_stop_reason,
                "index": 1,
            }
            synthetic_step["status"] = _step_status(synthetic_step)
            steps = [synthetic_step]

        for step in steps:
            step["narrative_sections"] = _build_narrative_sections(
                step, task_prompt=task_prompt
            )
            step["task"] = task_prompt
            if step.get("task_inputs") in (None, {}):
                step["task_inputs"] = task_inputs

        task: dict[str, Any] = {
            "task_id": task_id,
            "timestamp": str(started.get("ts") or finished.get("ts") or ""),
            "task": task_prompt,
            "task_inputs": task_inputs,
            "reasoning": reasoning,
            "code": code,
            "observed": observed,
            "finalized": finalized,
            "final_outputs": final_outputs,
            "exec_error": exec_error,
            "latency_ms": latency_ms,
            "parse_success": parse_success,
            "status": task_status,
            "stop_reason": task_stop_reason,
            "usage_summary": usage_summary,
            "activity_summary": activity_summary,
            "steps": steps,
            "summary": {
                "status": task_status,
                "stop_reason": task_stop_reason,
                "finalized": finalized,
                "parse_success": parse_success,
                "exec_error": exec_error,
                "latency_ms": latency_ms,
                "iterations": len(steps),
                "usage_summary": usage_summary,
                "activity_summary": activity_summary,
            },
            "_task_order": task_order,
        }
        tasks.append(task)

    tasks.sort(
        key=lambda task: (
            _safe_int(task.get("_task_order"), default=10000),
            str(task.get("task_id") or ""),
        )
    )
    for index, task in enumerate(tasks, start=1):
        task["index"] = index
        task.pop("_task_order", None)
    return tasks


def normalize_run(log_path: Path) -> dict[str, Any]:
    entries = _parse_jsonl(log_path)

    run_started = next(
        (entry for entry in entries if entry.get("event_type") == "run.started"), {}
    )

    run_finished = next(
        (
            entry
            for entry in reversed(entries)
            if entry.get("event_type") == "run.finished"
        ),
        {},
    )
    task_evaluations_by_task: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("event_type") != "task.evaluated":
            continue
        task_id = str(entry.get("task_id") or "").strip()
        if task_id:
            task_evaluations_by_task[task_id] = entry

    event_entries = [
        entry
        for entry in entries
        if entry.get("event_type")
        not in {"run.started", "run.finished", "task.evaluated"}
    ]
    last_entry = event_entries[-1] if event_entries else {}

    entries_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in event_entries:
        task_id = str(entry.get("task_id") or "").strip()
        if task_id:
            entries_by_task[task_id].append(entry)

    tasks = _build_tasks(
        entries_by_task,
        task_evaluations_by_task=task_evaluations_by_task or None,
    )
    task_count = len(tasks)
    finalized_count = sum(1 for task in tasks if bool(task.get("finalized")))
    finalization_rate = (finalized_count / task_count) if task_count else 0.0
    tasks_with_exec_error = sum(
        1 for task in tasks if str(task.get("exec_error") or "").strip()
    )

    elapsed_ms = _safe_int(run_finished.get("elapsed_ms"))
    if elapsed_ms <= 0:
        elapsed_ms = sum(_safe_int(task.get("latency_ms"), default=0) for task in tasks)

    status, stop_reason = _derive_summary_state(
        run_finished=run_finished,
        has_run_result=bool(run_finished),
        task_count=task_count,
        finalized_count=finalized_count,
        tasks_with_exec_error=tasks_with_exec_error,
    )

    usage_summary = _normalize_usage_summary(
        _sum_usage_summaries([dict(task.get("usage_summary") or {}) for task in tasks])
        or _usage_summary_from_entries(event_entries),
    )

    activity_summary = _normalize_activity_summary(
        _sum_activity_summaries(
            [dict(task.get("activity_summary") or {}) for task in tasks],
            last_event=str(last_entry.get("event_type") or ""),
        ),
    )

    final_outputs = run_finished.get("final_outputs")
    if final_outputs is None:
        for task in reversed(tasks):
            task_final_outputs = task.get("final_outputs")
            if task_final_outputs is not None:
                final_outputs = task_final_outputs
                break

    error_message = run_finished.get("error_message")
    if error_message in (None, ""):
        for task in tasks:
            task_error = str(task.get("exec_error") or "").strip()
            if task_error:
                error_message = task_error
                break

    all_steps: list[dict[str, Any]] = []
    for task in tasks:
        all_steps.extend(task.get("steps") or [])

    return {
        "run_id": str(run_started.get("run_id") or run_finished.get("run_id") or ""),
        "log_file": log_path.name,
        "log_path": str(log_path),
        "run_started": dict(run_started),
        "summary": {
            "status": status,
            "stop_reason": stop_reason,
            "n_tasks": task_count,
            "finalized_count": finalized_count,
            "finalization_rate": finalization_rate,
            "tasks_with_exec_error": tasks_with_exec_error,
            "elapsed_ms": elapsed_ms,
            "final_outputs": final_outputs,
            "error": error_message,
            "last_event": str(last_entry.get("event_type") or ""),
            "last_event_at": str(last_entry.get("ts") or ""),
            "event_count": len(event_entries),
            "usage_summary": usage_summary,
            "activity_summary": activity_summary,
        },
        "batch_summary": None,
        "tasks": tasks,
        "all_steps": all_steps,
    }


def build_run_index(log_dir: Path, *, limit: int = 25) -> list[dict[str, Any]]:
    log_paths = find_log_files(log_dir)

    runs: list[dict[str, Any]] = []
    for log_path in log_paths[:limit]:
        try:
            normalized = normalize_run(log_path)
        except ValueError:
            continue
        tasks = normalized.get("tasks", [])
        first_task = tasks[0] if tasks else {}
        summary = dict(normalized.get("summary") or {})
        usage_summary = dict(summary.get("usage_summary") or {})
        activity_summary = dict(summary.get("activity_summary") or {})
        runs.append(
            {
                "run_id": normalized.get("run_id"),
                "log_file": log_path.name,
                "report_file": None,
                "workload": normalized.get("run_started", {}).get("workload"),
                "task_preview": _snippet(first_task.get("task", ""), max_chars=120),
                "n_tasks": summary.get("n_tasks", 0),
                "finalized_count": summary.get("finalized_count", 0),
                "tasks_with_exec_error": summary.get("tasks_with_exec_error", 0),
                "finalization_rate": summary.get("finalization_rate", 0.0),
                "elapsed_ms": summary.get("elapsed_ms", 0),
                "status": summary.get("status", "unknown"),
                "last_event": summary.get("last_event", ""),
                "last_event_at": summary.get("last_event_at", ""),
                "event_count": summary.get("event_count", 0),
                "total_tokens": usage_summary.get("total_tokens", 0),
                "llm_calls": activity_summary.get("llm_calls", 0),
                "tool_calls": activity_summary.get("tool_calls", 0),
                "subllm_calls": activity_summary.get("subllm_calls", 0),
            }
        )
    return runs


__all__ = ["build_run_index", "normalize_run"]
