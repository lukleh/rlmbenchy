"""Shared task-filter helpers for workload loaders."""

from collections.abc import Mapping, Sequence

from rlmbenchy.datahub.types import WorkloadTask
from rlmbenchy.datahub.workloads.support.task_selection import normalize_task_id_filter


def apply_task_filters(
    tasks: Sequence[WorkloadTask],
    *,
    task_id: str | None,
    task_limit: int | None,
) -> list[WorkloadTask]:
    filtered = list(tasks)
    task_id_normalized = normalize_task_id_filter(task_id)
    if task_id_normalized:
        return [task for task in filtered if task.id == task_id_normalized]
    if task_limit is not None:
        filtered = filtered[: max(0, int(task_limit))]
    return filtered


def filter_payload_by_tasks[PayloadT](
    payload_by_task_id: Mapping[str, PayloadT],
    tasks: Sequence[WorkloadTask],
) -> dict[str, PayloadT]:
    kept_ids = {task.id for task in tasks}
    return {
        task_id: payload
        for task_id, payload in payload_by_task_id.items()
        if task_id in kept_ids
    }


__all__ = [
    "apply_task_filters",
    "filter_payload_by_tasks",
]
