"""check_adapter_matrix source helpers shared by the workload-local entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rlmbenchy.datahub.types import WorkloadTask
from rlmbenchy.datahub.workloads.support.paths import resolve_option_path_from_cwd
from rlmbenchy.datahub.workloads.support.task_filters import apply_task_filters
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    assert_unique_task_payload_ids,
)
from rlmbenchy.resources import resource_path

DEFAULT_TASKS_PATH = resource_path(
    "rlmbenchy.datahub.workloads.check_adapter_matrix", "tasks.json"
)


def resolve_tasks_path(tasks_path: str | Path = DEFAULT_TASKS_PATH) -> Path:
    return resolve_option_path_from_cwd(tasks_path, default_path=DEFAULT_TASKS_PATH)


def _normalize_row(
    row: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    return {
        "task_id": str(row.get("task_id") or f"matrix_{index + 1:03d}").strip(),
        "query": str(row.get("query") or "").strip(),
        "expected": row.get("expected"),
        "metadata": {
            key: value
            for key, value in row.items()
            if key not in {"task_id", "query", "expected"}
        },
    }


def task_row_to_task(
    row: dict[str, Any], *, index: int, tasks_path: Path
) -> dict[str, Any]:
    normalized = _normalize_row(row, index=index)
    return {
        "task_id": normalized["task_id"],
        "category": "check_adapter_matrix",
        "query": normalized["query"],
        "context": "",
        "expected": normalized["expected"],
        "dataset_meta": {
            "source": "check_adapter_matrix",
            "tasks_path": str(tasks_path),
            "row_index": index,
        },
    }


def row_to_workload_task(row: dict[str, Any], *, index: int) -> WorkloadTask:
    normalized = _normalize_row(row, index=index)
    return WorkloadTask(
        id=str(normalized["task_id"]),
        inputs={"question": str(normalized["query"])},
        answer=normalized["expected"],
        metadata=dict(normalized["metadata"]),
    )


def _load_rows(tasks_path: str | Path = DEFAULT_TASKS_PATH) -> tuple[Path, list[Any]]:
    resolved_tasks_path = resolve_tasks_path(tasks_path)
    rows = json.loads(resolved_tasks_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError(f"Expected list of tasks in {resolved_tasks_path}")
    return resolved_tasks_path, rows


def _iter_task_rows(
    tasks_path: str | Path = DEFAULT_TASKS_PATH,
) -> tuple[Path, list[tuple[int, dict[str, Any]]]]:
    resolved_tasks_path, rows = _load_rows(tasks_path)
    return resolved_tasks_path, [
        (index, dict(row)) for index, row in enumerate(rows) if isinstance(row, dict)
    ]


def load_task_rows(tasks_path: str | Path = DEFAULT_TASKS_PATH) -> list[dict[str, Any]]:
    _, task_rows = _iter_task_rows(tasks_path)
    return [row for _, row in task_rows]


def load_check_adapter_matrix_tasks(
    *,
    tasks_path: str | Path = DEFAULT_TASKS_PATH,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    resolved_tasks_path, task_rows = _iter_task_rows(tasks_path)
    tasks: list[dict[str, Any]] = []
    for index, row in task_rows:
        tasks.append(
            task_row_to_task(dict(row), index=index, tasks_path=resolved_tasks_path)
        )
        if max_rows is not None and len(tasks) >= max(0, int(max_rows)):
            break

    if not tasks:
        raise RuntimeError("No check_adapter_matrix tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="check_adapter_matrix")
    return tasks


def load_workload_tasks(
    *,
    tasks_path: str | Path = DEFAULT_TASKS_PATH,
    task_limit: int | None = None,
    task_id: str | None = None,
) -> tuple[Path, list[WorkloadTask]]:
    resolved_tasks_path, task_rows = _iter_task_rows(tasks_path)
    tasks = apply_task_filters(
        [row_to_workload_task(row, index=index) for index, row in task_rows],
        task_id=task_id,
        task_limit=task_limit,
    )
    assert_unique_task_ids(tasks, scope="check_adapter_matrix")
    return resolved_tasks_path, tasks


__all__ = [
    "DEFAULT_TASKS_PATH",
    "load_task_rows",
    "load_check_adapter_matrix_tasks",
    "load_workload_tasks",
    "resolve_tasks_path",
    "row_to_workload_task",
    "task_row_to_task",
]
