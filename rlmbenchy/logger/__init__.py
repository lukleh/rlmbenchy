"""Logging helpers for minimal RLM."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rlmbenchy.logger.rlm_logger import RLMLogger
from rlmbenchy.logger.verbose import VerbosePrinter

if TYPE_CHECKING:
    from rlmbenchy.logger.api import (
        build_run_index,
        find_log_files,
        load_latest_run,
        load_run,
        load_runs,
        run_calls,
        run_final_outputs,
        run_steps,
        run_summary,
        run_task_results,
        run_tasks,
        summarize_latest_progress,
        summarize_run_progress,
    )
    from rlmbenchy.logger.viewer import (
        DEFAULT_LOG_DIR,
        build_show_payload,
        build_stats_payload,
        build_tree_payload,
        find_latest_log_file,
        format_show_text,
        format_stats_text,
        format_tree_text,
        resolve_log_file,
    )

__all__ = [
    "DEFAULT_LOG_DIR",
    "RLMLogger",
    "VerbosePrinter",
    "build_run_index",
    "build_show_payload",
    "build_stats_payload",
    "build_tree_payload",
    "find_latest_log_file",
    "find_log_files",
    "format_show_text",
    "format_stats_text",
    "format_tree_text",
    "load_latest_run",
    "load_run",
    "load_runs",
    "resolve_log_file",
    "run_calls",
    "run_final_outputs",
    "run_steps",
    "run_summary",
    "run_task_results",
    "run_tasks",
    "summarize_latest_progress",
    "summarize_run_progress",
]

_API_EXPORTS = {
    "build_run_index",
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
}

_VIEWER_EXPORTS = {
    "DEFAULT_LOG_DIR",
    "find_latest_log_file",
    "resolve_log_file",
    "build_stats_payload",
    "build_tree_payload",
    "build_show_payload",
    "format_stats_text",
    "format_tree_text",
    "format_show_text",
}


def __getattr__(name: str) -> Any:
    if name in _API_EXPORTS:
        from rlmbenchy.logger import api as _api

        return getattr(_api, name)
    if name in _VIEWER_EXPORTS:
        from rlmbenchy.logger import viewer as _viewer

        return getattr(_viewer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
