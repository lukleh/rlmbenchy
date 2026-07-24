"""Opt-in helpers for auditing workload task-id sources."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rlmbenchy.datahub.workloads.support.task_selection import (
    DuplicateId,
    find_duplicate_ids,
)

RowIdBuilder = Callable[[Mapping[str, Any], int], str]


@dataclass(frozen=True)
class TaskIdAudit:
    """Summary of canonical task ids observed in a workload source."""

    scope: str
    row_count: int
    task_ids: tuple[str, ...]
    duplicates: tuple[DuplicateId, ...]

    @property
    def has_duplicates(self) -> bool:
        return bool(self.duplicates)


def audit_task_ids(
    rows: Iterable[Mapping[str, Any]],
    *,
    scope: str,
    task_id_for_row: RowIdBuilder,
    max_rows: int | None = None,
) -> TaskIdAudit:
    """Collect canonical task ids from rows without loading workload bundles."""

    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows must be >= 0 or None.")

    task_ids: list[str] = []
    for index, row in enumerate(rows):
        if max_rows is not None and len(task_ids) >= max_rows:
            break
        task_id = str(task_id_for_row(row, index)).strip()
        if not task_id:
            continue
        task_ids.append(task_id)

    return TaskIdAudit(
        scope=scope,
        row_count=len(task_ids),
        task_ids=tuple(task_ids),
        duplicates=tuple(find_duplicate_ids(task_ids)),
    )


def audit_json_task_file(
    path: str | Path,
    *,
    scope: str,
    id_field: str = "id",
    fallback_prefix: str = "task",
) -> TaskIdAudit:
    """Audit ids in a local JSON task file containing a list of row objects."""

    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError(f"Expected list of tasks in {path}")

    dict_rows = [dict(row) for row in rows if isinstance(row, dict)]

    def _task_id_for_row(row: Mapping[str, Any], index: int) -> str:
        return str(row.get(id_field) or f"{fallback_prefix}_{index + 1:03d}").strip()

    return audit_task_ids(
        dict_rows,
        scope=scope,
        task_id_for_row=_task_id_for_row,
    )


__all__ = [
    "TaskIdAudit",
    "audit_json_task_file",
    "audit_task_ids",
]
