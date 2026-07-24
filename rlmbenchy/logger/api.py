"""Public API for reading rlmbenchy telemetry output.

This module is the stable boundary for applications that need to inspect
rlmbenchy runs. Callers should use these helpers instead of reading JSONL
records or OpenTelemetry fields directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rlmbenchy.logger.coerce import coerce_float as _coerce_float
from rlmbenchy.logger.coerce import coerce_int_or as _int
from rlmbenchy.logger.log_files import find_latest_log_file, find_log_files
from rlmbenchy.logger.projection import build_run_index as _build_run_index
from rlmbenchy.logger.projection import normalize_run


def load_run(log_file: Path | str) -> dict[str, Any]:
    """Load one telemetry log as a normalized run projection."""
    return normalize_run(Path(log_file))


def build_run_index(log_dir: Path | str, *, limit: int = 25) -> list[dict[str, Any]]:
    """Return compact run rows for a log directory."""
    return _build_run_index(Path(log_dir), limit=limit)


def load_runs(
    log_dir: Path | str,
    *,
    limit: int | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Load normalized run projections from a log directory.

    By default unreadable or unsupported logs are skipped, which is useful for
    viewers and batch eval summaries. Set ``strict=True`` when a caller needs
    schema or parsing failures to fail the whole operation.
    """
    paths = find_log_files(log_dir)
    if limit is not None:
        paths = paths[: max(0, limit)]

    runs: list[dict[str, Any]] = []
    for log_file in paths:
        try:
            runs.append(load_run(log_file))
        except Exception:
            if strict:
                raise
    return runs


def load_latest_run(log_dir: Path | str) -> dict[str, Any] | None:
    """Load the newest run projection from a log directory."""
    log_file = find_latest_log_file(log_dir)
    if log_file is None:
        return None
    return load_run(log_file)


def run_summary(run_projection: dict[str, Any]) -> dict[str, Any]:
    """Return a stable summary for a normalized run projection."""
    summary = _mapping(run_projection.get("summary"))
    return {
        "runId": str(run_projection.get("run_id") or ""),
        "logFile": str(run_projection.get("log_file") or ""),
        "logPath": str(run_projection.get("log_path") or ""),
        "status": str(summary.get("status") or ""),
        "stopReason": str(summary.get("stop_reason") or ""),
        "nTasks": _int(summary.get("n_tasks")),
        "finalizedCount": _int(summary.get("finalized_count")),
        "finalizationRate": _float(summary.get("finalization_rate")),
        "tasksWithExecError": _int(summary.get("tasks_with_exec_error")),
        "elapsedMs": _int(summary.get("elapsed_ms")),
        "finalOutputs": summary.get("final_outputs"),
        "error": summary.get("error"),
        "lastEvent": str(summary.get("last_event") or ""),
        "lastEventAt": str(summary.get("last_event_at") or ""),
        "eventCount": _int(summary.get("event_count")),
        "usageSummary": dict(_mapping(summary.get("usage_summary"))),
        "activitySummary": dict(_mapping(summary.get("activity_summary"))),
    }


def run_tasks(run_projection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return task projections in run order."""
    return [
        dict(task)
        for task in (run_projection.get("tasks") or [])
        if isinstance(task, dict)
    ]


def run_steps(run_projection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return step projections in execution order."""
    return [
        dict(step)
        for step in (run_projection.get("all_steps") or [])
        if isinstance(step, dict)
    ]


def run_calls(
    run_projection: dict[str, Any],
    *,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    """Return calls from a normalized run projection in execution order."""
    calls: list[dict[str, Any]] = []
    for step in run_projection.get("all_steps") or []:
        if not isinstance(step, dict):
            continue
        for call in step.get("calls") or []:
            if not isinstance(call, dict):
                continue
            if kind is not None and call.get("kind") != kind:
                continue
            calls.append(dict(call))
    return calls


def run_final_outputs(run_projection: dict[str, Any]) -> Any:
    """Return final outputs for a run, if present."""
    return run_summary(run_projection).get("finalOutputs")


def run_task_results(run_projection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact task result rows for evals and reports."""
    results: list[dict[str, Any]] = []
    for task in run_tasks(run_projection):
        summary = _mapping(task.get("summary"))
        usage_summary = _mapping(
            task.get("usage_summary") or summary.get("usage_summary")
        )
        activity_summary = _mapping(
            task.get("activity_summary") or summary.get("activity_summary")
        )
        steps = task.get("steps")
        results.append(
            {
                "taskId": str(task.get("task_id") or ""),
                "task": str(task.get("task") or ""),
                "taskInputs": task.get("task_inputs") or {},
                "status": str(task.get("status") or summary.get("status") or ""),
                "stopReason": str(
                    task.get("stop_reason") or summary.get("stop_reason") or ""
                ),
                "finalized": bool(task.get("finalized") or summary.get("finalized")),
                "finalOutputs": task.get("final_outputs"),
                "observed": task.get("observed"),
                "execError": str(
                    task.get("exec_error") or summary.get("exec_error") or ""
                ),
                "parseSuccess": bool(
                    task.get("parse_success") or summary.get("parse_success")
                ),
                "latencyMs": _int(task.get("latency_ms") or summary.get("latency_ms")),
                "iterations": _int(
                    summary.get("iterations"),
                    default=len(steps) if isinstance(steps, list) else 0,
                ),
                "usageSummary": dict(usage_summary),
                "activitySummary": dict(activity_summary),
            }
        )
    return results


def summarize_run_progress(run_projection: dict[str, Any]) -> dict[str, Any]:
    """Build a compact progress summary from a normalized run projection."""
    summary = _mapping(run_projection.get("summary"))
    activity = _mapping(summary.get("activity_summary"))
    all_steps = [
        step
        for step in (run_projection.get("all_steps") or [])
        if isinstance(step, dict)
    ]
    calls = run_calls(run_projection)
    tool_calls = [call for call in calls if call.get("kind") == "tool"]
    sub_llm_calls = [call for call in calls if call.get("kind") == "llm_query"]
    lm_calls = [call for call in calls if call.get("kind") == "lm"]

    return {
        "runId": str(run_projection.get("run_id") or ""),
        "logFile": str(run_projection.get("log_file") or ""),
        "logPath": str(run_projection.get("log_path") or ""),
        "status": str(summary.get("status") or ""),
        "stopReason": str(summary.get("stop_reason") or ""),
        "lastEvent": str(summary.get("last_event") or ""),
        "lastEventAt": str(summary.get("last_event_at") or ""),
        "eventCount": _int(summary.get("event_count")),
        "elapsedMs": _int(summary.get("elapsed_ms")),
        "steps": _first_positive_int(activity.get("model_steps"), len(all_steps)),
        "toolCalls": _first_positive_int(activity.get("tool_calls"), len(tool_calls)),
        "subLlmCalls": _first_positive_int(
            activity.get("subllm_calls"),
            len(sub_llm_calls),
        ),
        "llmCalls": _first_positive_int(activity.get("llm_calls"), len(lm_calls)),
        "toolErrors": _int(activity.get("tool_call_errors")),
        "subLlmErrors": _int(activity.get("subllm_errors")),
        "llmErrors": _int(activity.get("llm_errors")),
    }


def summarize_latest_progress(log_dir: Path | str) -> dict[str, Any] | None:
    """Summarize progress for the newest run in a log directory."""
    run_projection = load_latest_run(log_dir)
    if run_projection is None:
        return None
    return summarize_run_progress(run_projection)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    coerced = _coerce_float(value)
    return default if coerced is None else coerced


def _first_positive_int(*values: Any) -> int:
    for value in values:
        number = _int(value)
        if number > 0:
            return number
    return 0


__all__ = [
    "build_run_index",
    "find_latest_log_file",
    "find_log_files",
    "load_latest_run",
    "load_run",
    "load_runs",
    "run_calls",
    "run_final_outputs",
    "run_steps",
    "run_summary",
    "run_task_results",
    "run_tasks",
    "summarize_latest_progress",
    "summarize_run_progress",
]
