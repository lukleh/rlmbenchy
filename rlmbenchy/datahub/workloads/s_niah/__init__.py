"""Synthetic Needle-In-A-Haystack (S-NIAH) workload loader with tool-based access."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import (
    WorkloadBundle,
    WorkloadTask,
)
from rlmbenchy.datahub.workloads.s_niah.source import (
    DEFAULT_HAYSTACK_LINES,
    DEFAULT_NEEDLE_KEY,
    DEFAULT_SEED,
    build_s_niah_synthetic_task,
)
from rlmbenchy.datahub.workloads.s_niah.tools import build_tools
from rlmbenchy.datahub.workloads.support.task_filters import (
    apply_task_filters,
    filter_payload_by_tasks,
)
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
)

WORKLOAD_NAME = "s_niah"


class SNiahSignature(dspy.Signature):
    """Find the value of the specified key in the haystack.
    Use s_niah_get_haystack(task_id) to retrieve the haystack data."""

    task_id: str = dspy.InputField(desc="Task identifier for tool calls.")
    needle_key: str = dspy.InputField(desc="The key to search for in the haystack.")
    haystack_lines: int = dspy.InputField(desc="Number of lines in the haystack.")
    answer: str = dspy.OutputField(desc="The value of the needle key.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load S-NIAH tasks with haystack behind a tool."""

    seed = int(options.get("seed", DEFAULT_SEED))
    haystack_lines = int(options.get("haystack_lines", DEFAULT_HAYSTACK_LINES))
    needle_key = str(options.get("needle_key", DEFAULT_NEEDLE_KEY)).strip()

    raw = build_s_niah_synthetic_task(
        seed=seed,
        haystack_lines=haystack_lines,
        needle_key=needle_key,
    )

    raw_id = str(raw["task_id"])
    context = str(raw["context"])
    expected = raw.get("expected")
    dataset_meta = raw.get("dataset_meta", {})

    tasks = [
        WorkloadTask(
            id=raw_id,
            inputs={
                "task_id": raw_id,
                "needle_key": needle_key,
                "haystack_lines": haystack_lines,
            },
            answer=expected,
            metadata=dataset_meta,
        )
    ]

    haystack_by_task_id: dict[str, str] = {raw_id: context}

    tasks = apply_task_filters(
        tasks,
        task_id=normalize_task_id_filter(task_id),
        task_limit=task_limit,
    )
    assert_unique_task_ids(tasks, scope="s_niah")
    haystack_by_task_id = filter_payload_by_tasks(haystack_by_task_id, tasks)

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(haystack_by_task_id),
        signature=SNiahSignature,
        metadata={
            "source": "synthetic",
            "seed": seed,
            "haystack_lines": haystack_lines,
            "needle_key": needle_key,
            "loaded_tasks": len(tasks),
            "task_limit": task_limit,
            "task_id_filter": str(task_id).strip() if task_id else None,
        },
    )
