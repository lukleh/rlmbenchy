"""JSONL trajectory log viewer utilities for rlmbenchy.

All interpretation is delegated to the shared projection layer
(``rlmbenchy.logger.projection``). This module provides the
payload-building and text-formatting API consumed by ``rlmbenchy logs``
CLI commands.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from rlmbenchy.logger.log_files import find_latest_log_file as _find_latest_log_file
from rlmbenchy.logger.preview import snippet as _snippet
from rlmbenchy.logger.projection import (
    _percentile,
    _safe_int,
    normalize_run,
)
from rlmbenchy.runtime_paths import resolve_runtime_paths

DEFAULT_LOG_DIR = resolve_runtime_paths().rlm_log_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def describe_run(metadata: dict[str, Any]) -> str:
    """Human label for a run: ``<source>+<workload>``.

    Source preference: run_config_name > lm_profile_name > the trailing
    segment of model_id.
    """
    label = metadata.get("run_config_name") or metadata.get("lm_profile_name")
    if not label:
        model = str(metadata.get("model_id") or "")
        label = model.rsplit("/", 1)[-1] if model else "?"
    workload = str(metadata.get("workload") or "?")
    return f"{label}+{workload}"


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def find_latest_log_file(log_dir: Path | str = DEFAULT_LOG_DIR) -> Path | None:
    return _find_latest_log_file(log_dir)


def resolve_log_file(
    *,
    log_file: Path | str | None,
    log_dir: Path | str = DEFAULT_LOG_DIR,
) -> Path:
    if log_file is not None:
        resolved = Path(log_file)
        if not resolved.exists():
            raise FileNotFoundError(f"Log file not found: {resolved}")
        return resolved
    latest = find_latest_log_file(log_dir)
    if latest is None:
        raise FileNotFoundError(
            f"No rlmbenchy .jsonl log files found in: {Path(log_dir)}"
        )
    return latest


def _run_summary_from_normalized(n: dict[str, Any]) -> dict[str, Any]:
    """Derive a compact run summary from ``normalize_run()`` output."""
    summary = n.get("summary") or {}
    tasks = n.get("tasks") or []
    steps = [step for task in tasks for step in (task.get("steps") or [])]
    parse_failures = sum(1 for step in steps if not step.get("parse_success"))
    status = str(summary.get("status") or "")
    stop_reason = str(summary.get("stop_reason") or "")
    return {
        "run_id": n.get("run_id", ""),
        "status": "PASS" if stop_reason == "success" else "FAIL",
        "stop_reason": stop_reason,
        "iterations": len(steps),
        "parse_failures": parse_failures,
        "duration_ms": _safe_int(summary.get("elapsed_ms")),
        "final_outputs": summary.get("final_outputs"),
        "error": summary.get("error"),
        "status_raw": status,
    }


# ---------------------------------------------------------------------------
# Payload builders — delegate to normalize_run()
# ---------------------------------------------------------------------------


def build_stats_payload(
    path: Path | str, *, run_id: str | None = None
) -> dict[str, Any]:
    resolved_path = Path(path)
    normalized = normalize_run(resolved_path)
    runs_data = [normalized]  # one file = one run in v2

    if run_id is not None:
        runs_data = [r for r in runs_data if r.get("run_id") == run_id]
        if not runs_data:
            raise KeyError(f"run_id not found in log: {run_id}")

    summaries = [_run_summary_from_normalized(r) for r in runs_data]
    status_counts = Counter(s["status"] for s in summaries)
    stop_reason_counts = Counter(s["stop_reason"] for s in summaries)
    steps = [
        step
        for run in runs_data
        for task in (run.get("tasks") or [])
        for step in (task.get("steps") or [])
    ]

    total_iterations = sum(s["iterations"] for s in summaries)
    total_parse_failures = sum(s["parse_failures"] for s in summaries)
    parse_failure_rate = (
        (total_parse_failures / total_iterations) if total_iterations else 0.0
    )
    total_multi_code_block_iterations = sum(
        1 for step in steps if step.get("multiple_code_blocks")
    )
    multi_code_block_iteration_rate = (
        total_multi_code_block_iterations / total_iterations
        if total_iterations
        else 0.0
    )
    runs_with_multi_code_blocks = sum(
        1
        for run in runs_data
        if any(
            step.get("multiple_code_blocks")
            for task in (run.get("tasks") or [])
            for step in (task.get("steps") or [])
        )
    )
    multi_code_block_run_rate = (
        runs_with_multi_code_blocks / len(runs_data) if runs_data else 0.0
    )
    parse_strategy_counts = Counter(
        str(step.get("parse_strategy") or "").strip()
        for step in steps
        if str(step.get("parse_strategy") or "").strip()
    )
    parse_failure_type_counts = Counter(
        str(step.get("parse_failure_type") or "").strip()
        for step in steps
        if str(step.get("parse_failure_type") or "").strip()
    )

    iteration_counts = [s["iterations"] for s in summaries]
    duration_values = [s["duration_ms"] for s in summaries]
    avg_iterations = (
        float(sum(iteration_counts)) / len(iteration_counts)
        if iteration_counts
        else 0.0
    )
    avg_duration_ms = (
        float(sum(duration_values)) / len(duration_values) if duration_values else 0.0
    )

    return {
        "log_file": str(resolved_path),
        "run_count": len(runs_data),
        "status_counts": dict(status_counts),
        "stop_reason_counts": dict(stop_reason_counts),
        "total_iterations": total_iterations,
        "total_parse_failures": total_parse_failures,
        "parse_failure_rate": parse_failure_rate,
        "total_multi_code_block_iterations": total_multi_code_block_iterations,
        "multi_code_block_iteration_rate": multi_code_block_iteration_rate,
        "runs_with_multi_code_blocks": runs_with_multi_code_blocks,
        "multi_code_block_run_rate": multi_code_block_run_rate,
        "avg_iterations_per_run": avg_iterations,
        "p95_iterations_per_run": _percentile(iteration_counts, 95.0),
        "avg_duration_ms_per_run": avg_duration_ms,
        "p95_duration_ms_per_run": _percentile(duration_values, 95.0),
        "parse_strategy_counts": dict(parse_strategy_counts),
        "parse_failure_type_counts": dict(parse_failure_type_counts),
        "runs": summaries,
    }


def build_tree_payload(
    path: Path | str,
    *,
    run_id: str | None = None,
    max_preview_chars: int = 140,
) -> dict[str, Any]:
    resolved_path = Path(path)
    normalized = normalize_run(resolved_path)
    runs_data = [normalized]

    if run_id is not None:
        runs_data = [r for r in runs_data if r.get("run_id") == run_id]
        if not runs_data:
            raise KeyError(f"run_id not found in log: {run_id}")

    data_runs: list[dict[str, Any]] = []
    for index, run in enumerate(runs_data, start=1):
        summary = _run_summary_from_normalized(run)
        run_started = run.get("run_started") or {}
        tasks = run.get("tasks") or []
        steps_out: list[dict[str, Any]] = []
        for task in tasks:
            for step in task.get("steps") or []:
                steps_out.append(
                    {
                        "iteration": step.get("step_index", len(steps_out) + 1),
                        "parse_success": bool(step.get("parse_success")),
                        "parse_strategy": step.get("parse_strategy") or "",
                        "parse_failure_type": step.get("parse_failure_type"),
                        "code_block_count": _safe_int(step.get("code_block_count")),
                        "multiple_code_blocks": bool(step.get("multiple_code_blocks")),
                        "execution_error": step.get("exec_error") or None,
                        "final_signal": step.get("final_outputs") is not None,
                        "duration_ms": _safe_int(step.get("latency_ms")),
                        "code_preview": _snippet(
                            step.get("code"), max_chars=max_preview_chars
                        ),
                        "stdout_preview": _snippet(
                            step.get("observed"), max_chars=max_preview_chars
                        ),
                    }
                )
        data_runs.append(
            {
                "index": index,
                "summary": summary,
                "run_started": dict(run_started),
                "steps": steps_out,
                "extra_entry_count": 0,
            }
        )

    return {
        "log_file": str(resolved_path),
        "run_count": len(data_runs),
        "runs": data_runs,
    }


def build_show_payload(
    path: Path | str,
    *,
    run_id: str | None = None,
    only_failures: bool = False,
    limit: int = 80,
    max_preview_chars: int = 160,
) -> dict[str, Any]:
    resolved_path = Path(path)
    normalized = normalize_run(resolved_path)

    if run_id is not None and normalized.get("run_id") != run_id:
        raise KeyError(f"run_id not found in log: {run_id}")

    run_summary = _run_summary_from_normalized(normalized)
    run_started = normalized.get("run_started") or {}
    tasks = normalized.get("tasks") or []

    rows: list[dict[str, Any]] = []
    row_index = 0

    # run.started row
    row_index += 1
    rows.append(
        {
            "line_no": row_index,
            "run_id": normalized.get("run_id", ""),
            "type": "run_started",
            "event_type": "run.started",
            "timestamp": run_started.get("ts"),
            "iteration": 0,
            "parse_success": None,
            "parse_strategy": None,
            "parse_failure_type": None,
            "code_block_count": 0,
            "multiple_code_blocks": False,
            "execution_error": None,
            "final_signal": None,
            "stop_reason": None,
            "status": None,
            "preview": (
                f"config={describe_run(run_started)} "
                f"model={run_started.get('model_id')} "
                f"seed={(run_started.get('config') or {}).get('seed')}"
            ),
        }
    )

    # Step rows from tasks
    for task in tasks:
        for step in task.get("steps") or []:
            row_index += 1
            parse_success = bool(step.get("parse_success"))
            exec_error = step.get("exec_error") or None
            code = str(step.get("code") or "")
            observed = str(step.get("observed") or "")
            row: dict[str, Any] = {
                "line_no": row_index,
                "run_id": normalized.get("run_id", ""),
                "type": "step_finished",
                "event_type": "step.finished",
                "timestamp": step.get("timestamp"),
                "iteration": step.get("step_index", 0),
                "parse_success": parse_success,
                "parse_strategy": step.get("parse_strategy") or None,
                "parse_failure_type": step.get("parse_failure_type"),
                "code_block_count": _safe_int(step.get("code_block_count")),
                "multiple_code_blocks": bool(step.get("multiple_code_blocks")),
                "execution_error": exec_error,
                "final_signal": step.get("final_outputs") is not None,
                "stop_reason": step.get("stop_reason"),
                "status": step.get("status"),
                "preview": (
                    _snippet(exec_error or code, max_chars=max_preview_chars)
                    if not parse_success
                    else _snippet(code or observed, max_chars=max_preview_chars)
                ),
            }
            if only_failures:
                is_failure = not parse_success or bool(exec_error)
                if not is_failure:
                    continue
                if code:
                    row["executed_code"] = code
                if observed:
                    row["execution_stdout"] = observed
            rows.append(row)

    # run.finished row
    row_index += 1
    run_finished_row: dict[str, Any] = {
        "line_no": row_index,
        "run_id": normalized.get("run_id", ""),
        "type": "run_finished",
        "event_type": "run.finished",
        "timestamp": None,
        "iteration": 0,
        "parse_success": None,
        "parse_strategy": None,
        "parse_failure_type": None,
        "code_block_count": 0,
        "multiple_code_blocks": False,
        "execution_error": None,
        "final_signal": None,
        "stop_reason": run_summary["stop_reason"],
        "status": run_summary["status"],
        "preview": (
            f"stop={run_summary['stop_reason']} "
            f"final={run_summary['final_outputs']!r} "
            f"iters={run_summary['iterations']}"
        ),
    }
    if only_failures and run_summary["status"] != "FAIL":
        pass  # skip
    else:
        rows.append(run_finished_row)

    rows = sorted(rows, key=lambda item: item.get("line_no") or 0)
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    return {
        "log_file": str(resolved_path),
        "row_count": len(rows),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Text formatters (unchanged public API)
# ---------------------------------------------------------------------------


def format_stats_text(payload: dict[str, Any]) -> str:
    lines = [
        f"log_file={payload.get('log_file')}",
        f"runs={payload.get('run_count')}",
        f"status_counts={payload.get('status_counts', {})}",
        f"stop_reason_counts={payload.get('stop_reason_counts', {})}",
        (
            f"iterations total={payload.get('total_iterations')} "
            f"avg_per_run={payload.get('avg_iterations_per_run'):.2f} "
            f"p95_per_run={payload.get('p95_iterations_per_run'):.2f}"
        ),
        (
            f"duration_ms avg_per_run={payload.get('avg_duration_ms_per_run'):.1f} "
            f"p95_per_run={payload.get('p95_duration_ms_per_run'):.1f}"
        ),
        (
            f"parse_failures total={payload.get('total_parse_failures')} "
            f"rate={payload.get('parse_failure_rate'):.3f}"
        ),
        (
            f"multi_code_blocks iterations={payload.get('total_multi_code_block_iterations')} "
            f"rate={payload.get('multi_code_block_iteration_rate'):.3f} "
            f"runs={payload.get('runs_with_multi_code_blocks')} "
            f"run_rate={payload.get('multi_code_block_run_rate'):.3f}"
        ),
        f"parse_strategy_counts={payload.get('parse_strategy_counts', {})}",
        f"parse_failure_type_counts={payload.get('parse_failure_type_counts', {})}",
    ]
    return "\n".join(lines)


def format_tree_text(payload: dict[str, Any]) -> str:
    lines = [
        f"log_file={payload.get('log_file')}",
        f"run_count={payload.get('run_count')}",
    ]
    for run in payload.get("runs", []):
        summary = run.get("summary") or {}
        run_started = run.get("run_started") or {}
        lines.append(
            f"run[{run.get('index')}]: id={summary.get('run_id')} "
            f"status={summary.get('status')} stop={summary.get('stop_reason')} "
            f"iters={summary.get('iterations')} parse_failures={summary.get('parse_failures')} "
            f"duration_ms={summary.get('duration_ms')}"
        )
        lines.append(
            f"  config={describe_run(run_started)} "
            f"model={run_started.get('model_id')} "
            f"seed={(run_started.get('config') or {}).get('seed')}"
        )
        lines.append(f"  final_outputs={summary.get('final_outputs')!r}")
        if summary.get("error"):
            lines.append(f"  error={summary.get('error')}")

        for item in run.get("steps", []):
            lines.append(
                f"  iter {item.get('iteration')}: "
                f"parse={'ok' if item.get('parse_success') else 'fail'} "
                f"strategy={item.get('parse_strategy') or '<none>'} "
                f"failure={item.get('parse_failure_type') or '<none>'} "
                f"code_blocks={item.get('code_block_count') or 0} "
                f"multi={'yes' if item.get('multiple_code_blocks') else 'no'} "
                f"final={item.get('final_signal') or '<none>'} "
                f"duration_ms={item.get('duration_ms')}"
            )
            if item.get("execution_error"):
                lines.append(f"    execution_error={item.get('execution_error')}")
            if item.get("code_preview"):
                lines.append(f"    code={item.get('code_preview')}")
            if item.get("stdout_preview"):
                lines.append(f"    stdout={item.get('stdout_preview')}")
    return "\n".join(lines)


def format_show_text(payload: dict[str, Any]) -> str:
    lines = [
        f"log_file={payload.get('log_file')}",
        f"rows={payload.get('row_count')}",
    ]
    for row in payload.get("rows", []):
        lines.append(
            f"[line {row.get('line_no')}] run_id={row.get('run_id')} "
            f"type={row.get('type')} event={row.get('event_type') or '-'} "
            f"iteration={row.get('iteration') or '-'} "
            f"code_blocks={row.get('code_block_count') or 0} "
            f"multi={'yes' if row.get('multiple_code_blocks') else 'no'} "
            f"stop={row.get('stop_reason') or '-'} "
            f"status={row.get('status') or '-'} "
            f"preview={row.get('preview')}"
        )
        if row.get("executed_code"):
            lines.append(f"  executed_code:\n{row['executed_code']}")
        if row.get("execution_stdout"):
            lines.append(f"  execution_stdout:\n{row['execution_stdout']}")
        if row.get("execution_stderr"):
            lines.append(f"  execution_stderr:\n{row['execution_stderr']}")
        if row.get("execution_error"):
            lines.append(f"  execution_error:\n{row['execution_error']}")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_LOG_DIR",
    "build_show_payload",
    "build_stats_payload",
    "build_tree_payload",
    "find_latest_log_file",
    "format_show_text",
    "format_stats_text",
    "format_tree_text",
    "resolve_log_file",
]
