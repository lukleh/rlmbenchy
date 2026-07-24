"""Workbench CLI built on top of the reusable RLM runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from rlmbenchy.logger.api import load_run, run_summary, run_tasks
from rlmbenchy.workbench.config import BenchRunConfig, load_bench_run_config
from rlmbenchy.workbench.runner import run_workload


def _snippet(value: Any, *, max_chars: int = 220) -> str:
    del max_chars
    return str(value or "").strip()


def _format_optional_int(value: Any) -> str:
    if isinstance(value, bool):
        return "0"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "0"
        try:
            return f"{int(float(text)):,}"
        except ValueError:
            return "0"
    return "0"


def _format_elapsed_seconds(elapsed_ms: Any) -> str:
    if isinstance(elapsed_ms, bool):
        return "0.000s"
    if isinstance(elapsed_ms, (int, float)):
        return f"{float(elapsed_ms) / 1000.0:.3f}s"
    if isinstance(elapsed_ms, str):
        text = elapsed_ms.strip()
        if not text:
            return "0.000s"
        try:
            return f"{float(text) / 1000.0:.3f}s"
        except ValueError:
            return "0.000s"
    return "0.000s"


def _format_single_task_completion(log_path: Path) -> list[str]:
    resolved_log_path = log_path.expanduser().resolve()
    lines = [f"log_path={resolved_log_path}"]

    try:
        normalized = load_run(resolved_log_path)
    except Exception as exc:
        lines.append(f"summary_unavailable={type(exc).__name__}: {exc}")
        return lines

    summary = run_summary(normalized)
    usage_summary = dict(summary.get("usageSummary") or {})
    activity_summary = dict(summary.get("activitySummary") or {})
    tasks = run_tasks(normalized)
    task_id = ""
    if len(tasks) == 1:
        task_id = str(tasks[0].get("task_id") or "").strip()

    summary_parts = []
    if task_id:
        summary_parts.append(f"task_id={task_id}")
    summary_parts.extend(
        [
            f"status={summary.get('status', 'unknown')}",
            f"stop_reason={summary.get('stopReason', 'unknown')}",
            f"elapsed={_format_elapsed_seconds(summary.get('elapsedMs'))}",
            f"total_tokens={_format_optional_int(usage_summary.get('total_tokens'))}",
            f"llm_calls={_format_optional_int(activity_summary.get('llm_calls'))}",
            f"tool_calls={_format_optional_int(activity_summary.get('tool_calls'))}",
        ]
    )
    lines.append("summary=" + " ".join(summary_parts))

    final_outputs = summary.get("finalOutputs")
    if final_outputs is not None:
        lines.append(f"final_outputs={_snippet(final_outputs)}")

    error = summary.get("error")
    if error not in (None, ""):
        lines.append(f"error={_snippet(error)}")

    return lines


def _print_single_task_completion(log_path: Path) -> None:
    for line in _format_single_task_completion(log_path):
        print(line)


def add_run_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_dest: str = "run_config",
) -> None:
    parser.add_argument(
        "--config",
        dest=config_dest,
        required=True,
        help="Path to TOML run config.",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="Run a single task by exact task id.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Per-invocation seed (overrides config.seed).",
    )
    parser.add_argument(
        "--repl-backend",
        choices=("docker", "local"),
        default=None,
        help="REPL backend (overrides config.repl.backend).",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RLM workbench runner.")
    add_run_arguments(parser)
    return parser.parse_args(argv)


def run_from_config_path(
    config_path: Path,
    *,
    task_id: str | None = None,
    seed: int | None = None,
    repl_backend: str | None = None,
) -> Path:
    """Load a run config from disk and execute the workload.

    Returns the log file path produced by the run.
    """
    resolved_path = Path(config_path).expanduser().resolve()
    config: BenchRunConfig = load_bench_run_config(resolved_path)
    print(f"config={resolved_path}")

    log_path = run_workload(
        config,
        task_id=task_id,
        seed=seed,
        repl_backend=repl_backend,
        run_config_name=resolved_path.stem,
        lm_profile_name=None,
        sub_lm_profile_name=None,
    )
    if task_id:
        _print_single_task_completion(log_path)
    return log_path


def main(argv: list[str] | None = None) -> None:
    args = parse_args() if argv is None else parse_args(argv)
    run_from_config_path(
        Path(str(args.run_config)),
        task_id=str(args.task_id) if args.task_id else None,
        seed=int(args.seed) if args.seed is not None else None,
        repl_backend=str(args.repl_backend) if args.repl_backend else None,
    )


__all__ = [
    "add_run_arguments",
    "main",
    "parse_args",
    "run_from_config_path",
]


if __name__ == "__main__":
    main()
