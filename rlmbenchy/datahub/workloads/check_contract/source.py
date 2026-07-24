"""check_contract source helpers shared by the workload-local entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from rlmbenchy.datahub.types import WorkloadTask
from rlmbenchy.datahub.workloads.support.paths import resolve_option_path_from_cwd
from rlmbenchy.datahub.workloads.support.task_filters import apply_task_filters
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    assert_unique_task_payload_ids,
)
from rlmbenchy.resources import resource_path

DEFAULT_TASKS_PATH = resource_path(
    "rlmbenchy.datahub.workloads.check_contract", "tasks.json"
)


def resolve_tasks_path(tasks_path: str | Path = DEFAULT_TASKS_PATH) -> Path:
    return resolve_option_path_from_cwd(tasks_path, default_path=DEFAULT_TASKS_PATH)


def _normalize_task_row(row: dict[str, Any], index: int) -> dict[str, Any] | None:
    task_id = str(row.get("task_id") or f"check_{index + 1:03d}").strip()
    query = str(row.get("query") or "").strip()
    if not task_id or not query:
        return None

    context_chunks = row.get("context_chunks")
    if context_chunks is not None:
        if not isinstance(context_chunks, list) or not all(
            isinstance(chunk, str) for chunk in context_chunks
        ):
            return None
        context: str | list[str] = [str(chunk) for chunk in context_chunks]
    else:
        context = row.get("context", "")
        if not isinstance(context, str):
            return None

    return {
        "task_id": task_id,
        "query": query,
        "category": str(row.get("category") or "unknown").strip() or "unknown",
        "context": context,
        "metadata": {
            key: value
            for key, value in row.items()
            if key not in {"task_id", "query", "context", "context_chunks", "category"}
        },
    }


def load_task_rows(tasks_path: Path | str = DEFAULT_TASKS_PATH) -> list[dict[str, Any]]:
    resolved_tasks_path = resolve_tasks_path(tasks_path)
    rows = json.loads(resolved_tasks_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise TypeError(f"Task file must contain a JSON list: {resolved_tasks_path}")

    tasks = [
        normalized
        for index, row in enumerate(rows)
        if isinstance(row, dict)
        for normalized in [_normalize_task_row(cast(dict[str, Any], row), index)]
        if normalized is not None
    ]
    if not tasks:
        raise ValueError("Task file has no valid tasks.")
    return tasks


def _context_text(context: str | list[str]) -> str:
    if isinstance(context, list):
        return "\n\n".join(context)
    return str(context)


def task_row_to_task(
    row: dict[str, Any], *, index: int, tasks_path: Path
) -> dict[str, Any]:
    context_raw = row.get("context", "")
    context = (
        "\n\n".join(context_raw) if isinstance(context_raw, list) else str(context_raw)
    )
    return {
        "task_id": str(row["task_id"]),
        "category": str(row.get("category") or "check_contract"),
        "query": str(row["query"]),
        "context": context,
        "expected": row.get("answer"),
        "dataset_meta": {
            "source": "check_contract",
            "tasks_path": str(tasks_path),
            "row_index": index,
            "metadata": dict(row.get("metadata") or {}),
        },
    }


def row_to_workload_task(row: dict[str, Any], *, index: int) -> WorkloadTask:
    del index
    return WorkloadTask(
        id=str(row["task_id"]),
        inputs={
            "query": str(row["query"]),
            "context": _context_text(row["context"]),
        },
        answer=None,
        metadata={
            "category": row["category"],
            **dict(row["metadata"]),
        },
    )


def load_check_contract_tasks(
    *,
    tasks_path: str | Path = DEFAULT_TASKS_PATH,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    resolved_tasks_path = resolve_tasks_path(tasks_path)
    rows = load_task_rows(resolved_tasks_path)
    tasks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        tasks.append(
            task_row_to_task(dict(row), index=index, tasks_path=resolved_tasks_path)
        )
        if max_rows is not None and len(tasks) >= max(0, int(max_rows)):
            break

    if not tasks:
        raise RuntimeError("No check_contract tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="check_contract")
    return tasks


def load_workload_tasks(
    *,
    tasks_path: str | Path = DEFAULT_TASKS_PATH,
    task_limit: int | None = None,
    task_id: str | None = None,
) -> tuple[Path, list[WorkloadTask]]:
    resolved_tasks_path = resolve_tasks_path(tasks_path)
    tasks = apply_task_filters(
        [
            row_to_workload_task(row, index=index)
            for index, row in enumerate(load_task_rows(resolved_tasks_path))
        ],
        task_id=task_id,
        task_limit=task_limit,
    )
    assert_unique_task_ids(tasks, scope="check_contract")
    return resolved_tasks_path, tasks


__all__ = [
    "DEFAULT_TASKS_PATH",
    "load_check_contract_tasks",
    "load_task_rows",
    "load_workload_tasks",
    "resolve_tasks_path",
    "row_to_workload_task",
    "task_row_to_task",
]
