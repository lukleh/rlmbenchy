"""LongCoT workload loader.

Streams long-horizon reasoning problems from the Hugging Face dataset
``LongHorizonReasoning/longcot`` and exposes each question as a single-input
``prompt -> solution`` task. The prompt contains the full problem statement
and the required answer format (``solution = ...``); the workload ships no
tools and does not attempt to verify answers, because upstream verification
is template-specific and outside the scope of this repo.
"""

from typing import Any

import dspy

from rlmbenchy.datahub.types import WorkloadBundle, WorkloadTask
from rlmbenchy.datahub.workloads.longcot.source import (
    DEFAULT_CONFIG,
    DEFAULT_DATASET_ID,
    DEFAULT_MAX_ROWS,
    DEFAULT_SPLIT,
    iter_longcot_tasks,
)
from rlmbenchy.datahub.workloads.longcot.tools import build_tools
from rlmbenchy.datahub.workloads.support.task_filters import apply_task_filters
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
)

WORKLOAD_NAME = "longcot"


class LongCoTSignature(dspy.Signature):
    """Solve the long-horizon reasoning problem stated in the prompt.
    The prompt tells you the exact answer format (typically 'solution = <value>')."""

    prompt: str = dspy.InputField(
        desc="Full problem statement including required answer format."
    )
    solution: str = dspy.OutputField(desc="Your final answer for the problem.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load LongCoT questions from Hugging Face as single-prompt tasks."""

    task_id_filter = normalize_task_id_filter(task_id)
    dataset_id = str(options.get("dataset_id", DEFAULT_DATASET_ID)).strip()
    config = str(options.get("config", DEFAULT_CONFIG)).strip()
    split = str(options.get("split", DEFAULT_SPLIT)).strip()
    max_rows_raw = options.get("max_rows", DEFAULT_MAX_ROWS)
    max_rows = int(max_rows_raw) if max_rows_raw is not None else None

    task_payloads = iter_longcot_tasks(
        dataset_id=dataset_id,
        config=config,
        split=split,
        max_rows=max_rows,
        token=options.get("token"),
        task_id=task_id_filter,
    )

    tasks: list[WorkloadTask] = []
    for task_payload in task_payloads:
        metadata = dict(task_payload["metadata"])
        tasks.append(
            WorkloadTask(
                id=str(task_payload["task_id"]),
                inputs={"prompt": str(task_payload["prompt"])},
                answer=None,
                metadata=metadata,
            )
        )

    if not tasks and task_id_filter is None:
        raise RuntimeError("No LongCoT tasks were loaded.")

    tasks = apply_task_filters(tasks, task_id=task_id_filter, task_limit=task_limit)
    assert_unique_task_ids(tasks, scope="longcot")

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(),
        signature=LongCoTSignature,
        metadata={
            "source": "hf_datasets_server",
            "dataset_id": dataset_id,
            "config": config,
            "split": split,
            "loaded_tasks": len(tasks),
            "task_limit": task_limit,
            "task_id_filter": task_id_filter,
        },
    )
