"""tasks_v0 workload loader."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import WorkloadBundle
from rlmbenchy.datahub.workloads.tasks_v0.source import (
    DEFAULT_TASKS_PATH,
    load_workload_tasks,
)
from rlmbenchy.datahub.workloads.tasks_v0.tools import build_tools

WORKLOAD_NAME = "tasks_v0"


class TasksV0Signature(dspy.Signature):
    """Solve the task described below. Return the answer in the requested format."""

    task: str = dspy.InputField(
        desc="Full task description with instructions and data."
    )
    answer: str = dspy.OutputField(desc="The solution to the task.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load local JSON tasks from `tasks.json` or an override path."""

    tasks_path_raw = options.get("tasks_path", str(DEFAULT_TASKS_PATH))
    tasks_path, tasks = load_workload_tasks(
        tasks_path=tasks_path_raw,
        task_id=task_id,
        task_limit=task_limit,
    )

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(),
        signature=TasksV0Signature,
        metadata={
            "source": "local_json",
            "tasks_path": str(tasks_path),
            "loaded_tasks": len(tasks),
            "task_id_filter": str(task_id).strip() if task_id else None,
            "task_limit": task_limit,
        },
    )
