"""OOLONG-Pairs workload loader with tool-based context access."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import (
    WorkloadBundle,
    WorkloadTask,
)
from rlmbenchy.datahub.workloads.oolong_pairs.source import (
    DEFAULT_CONFIG,
    DEFAULT_DATASET_ID,
    DEFAULT_SPLIT,
    iter_oolong_pairs_tasks,
    query_for_index,
    resolve_query_index,
)
from rlmbenchy.datahub.workloads.oolong_pairs.tools import build_tools
from rlmbenchy.datahub.workloads.support.task_filters import (
    apply_task_filters,
    filter_payload_by_tasks,
)
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
    put_unique_payload,
)

WORKLOAD_NAME = "oolong_pairs"


class OolongPairsSignature(dspy.Signature):
    """Answer the question using the context data.
    Use oolong_pairs_get_context(task_id) to retrieve the full context text."""

    question: str = dspy.InputField(desc="The question to answer.")
    task_id: str = dspy.InputField(
        desc="Task identifier for oolong_pairs_get_context tool."
    )
    context_lines: int = dspy.InputField(desc="Number of lines in the context.")
    answer: str = dspy.OutputField(desc="The answer to the question.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load OOLONG-Pairs tasks with context behind a tool."""

    dataset_id = str(options.get("dataset_id", DEFAULT_DATASET_ID)).strip()
    config = str(options.get("config", DEFAULT_CONFIG)).strip()
    split = str(options.get("split", DEFAULT_SPLIT)).strip()
    query_index = int(options.get("query_index", 0))
    task_id_filter = normalize_task_id_filter(task_id)
    max_rows = options.get("max_rows", 20)
    if max_rows is not None:
        max_rows = int(max_rows)

    task_payloads = iter_oolong_pairs_tasks(
        dataset_id=dataset_id,
        config=config,
        split=split,
        query_index=query_index,
        max_rows=max_rows,
        token=options.get("token"),
        task_id=task_id_filter,
    )

    resolved_query_index = resolve_query_index(query_index)
    query = query_for_index(resolved_query_index)

    tasks: list[WorkloadTask] = []
    context_by_task_id: dict[str, str] = {}

    for task_payload in task_payloads:
        raw_id = str(task_payload["task_id"])
        context = str(task_payload["context"])
        metadata = task_payload.get("dataset_meta")
        put_unique_payload(context_by_task_id, raw_id, context, scope="oolong_pairs")
        context_lines = context.count("\n") + 1

        tasks.append(
            WorkloadTask(
                id=raw_id,
                inputs={
                    "question": query,
                    "task_id": raw_id,
                    "context_lines": context_lines,
                },
                answer=None,
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        )

    if not tasks and task_id_filter is None:
        raise RuntimeError("No OOLONG-Pairs tasks were loaded.")

    tasks = apply_task_filters(tasks, task_id=task_id_filter, task_limit=task_limit)
    assert_unique_task_ids(tasks, scope="oolong_pairs")
    context_by_task_id = filter_payload_by_tasks(context_by_task_id, tasks)

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(context_by_task_id),
        signature=OolongPairsSignature,
        metadata={
            "source": "hf_datasets_server",
            "dataset_id": dataset_id,
            "config": config,
            "split": split,
            "loaded_tasks": len(tasks),
            "task_limit": task_limit,
            "task_id_filter": task_id_filter,
            "query_index": resolved_query_index,
        },
    )
