"""Adapter matrix check tasks workload loader."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import WorkloadBundle
from rlmbenchy.datahub.workloads.check_adapter_matrix.source import (
    DEFAULT_TASKS_PATH,
    load_workload_tasks,
)

WORKLOAD_NAME = "check_adapter_matrix"


class CheckAdapterMatrixSignature(dspy.Signature):
    """Answer the question. Return only the requested value."""

    question: str = dspy.InputField(desc="The question to answer.")
    answer: str = dspy.OutputField(desc="The answer.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load adapter matrix check tasks from JSON."""
    tasks_path_raw = options.get("tasks_path", str(DEFAULT_TASKS_PATH))
    tasks_path, tasks = load_workload_tasks(
        tasks_path=tasks_path_raw,
        task_id=task_id,
        task_limit=task_limit,
    )

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=[],
        signature=CheckAdapterMatrixSignature,
        metadata={
            "source": "local_json",
            "tasks_path": str(tasks_path),
            "loaded_tasks": len(tasks),
        },
    )
