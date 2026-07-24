"""Check contract tasks workload loader."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import WorkloadBundle
from rlmbenchy.datahub.workloads.check_contract.source import (
    DEFAULT_TASKS_PATH,
    load_workload_tasks,
)

WORKLOAD_NAME = "check_contract"


class CheckContractSignature(dspy.Signature):
    """Answer the query using the provided context data."""

    query: str = dspy.InputField(desc="The question or instruction to answer.")
    context: str = dspy.InputField(desc="Supporting data (CSV, JSON, logs, etc.).")
    answer: str = dspy.OutputField(desc="The answer to the query.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load check contract tasks from JSON."""
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
        signature=CheckContractSignature,
        metadata={
            "source": "local_json",
            "tasks_path": str(tasks_path),
            "loaded_tasks": len(tasks),
        },
    )
