"""BrowseComp-Plus workload loader with a dataset access tool."""

from typing import Any

import dspy

from rlmbenchy.datahub.workloads.support.hf import iter_rows
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
)
from rlmbenchy.datahub.workloads.browsecomp_plus.tools import build_tools
from rlmbenchy.datahub.workloads.browsecomp_plus.source import (
    DEFAULT_CONFIG,
    DEFAULT_DATASET_ID,
    DEFAULT_SPLIT,
    collect_docs,
    extract_expected_answer,
    extract_query_id,
    task_id_for_query_id,
)
from rlmbenchy.datahub.types import (
    WorkloadBundle,
    WorkloadTask,
)

WORKLOAD_NAME = "browsecomp_plus"


class BrowseCompPlusSignature(dspy.Signature):
    """Find the answer to the question using the available documents.
    Use browsecomp_get_docs(query_id, offset, max_docs) to retrieve document pages."""

    question: str = dspy.InputField(desc="The question to answer.")
    query_id: str = dspy.InputField(
        desc="Document collection identifier for browsecomp_get_docs tool."
    )
    docs_total: int = dspy.InputField(desc="Total number of available documents.")
    answer: str = dspy.OutputField(desc="The answer to the question.")


def _parse_optional_positive_int(value: Any, *, option_name: str) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{option_name} must be > 0 when provided.")
    return parsed


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load BrowseComp tasks and attach `browsecomp_get_docs` tool."""
    dataset_id = str(options.get("dataset_id", DEFAULT_DATASET_ID)).strip()
    config = str(options.get("config", DEFAULT_CONFIG)).strip()
    split = str(options.get("split", DEFAULT_SPLIT)).strip()
    max_docs_per_task = _parse_optional_positive_int(
        options.get("max_docs_per_task"),
        option_name="max_docs_per_task",
    )
    max_docs_per_tool_call = _parse_optional_positive_int(
        options.get("max_docs_per_tool_call"),
        option_name="max_docs_per_tool_call",
    )

    task_id_filter = normalize_task_id_filter(task_id) or ""
    target_count = (
        None if task_id_filter or task_limit is None else max(0, int(task_limit))
    )

    tasks: list[WorkloadTask] = []
    docs_by_query_id: dict[str, list[str]] = {}

    row_iter = iter_rows(
        dataset_id=dataset_id,
        config=config,
        split=split,
        max_rows=None,
        token=options.get("token"),
    )
    for row_index, row in enumerate(row_iter):
        if target_count is not None and len(tasks) >= target_count:
            break

        query = str(row.get("query") or "").strip()
        query_id = extract_query_id(row, index=row_index)
        run_task_id = task_id_for_query_id(
            query_id,
            config=config,
            split=split,
            index=row_index,
        )

        if task_id_filter and run_task_id != task_id_filter:
            continue

        docs = collect_docs(row, max_docs=max_docs_per_task)

        docs_by_query_id[run_task_id] = docs
        tasks.append(
            WorkloadTask(
                id=run_task_id,
                inputs={
                    "question": query,
                    "query_id": run_task_id,
                    "docs_total": len(docs),
                },
                answer=extract_expected_answer(row),
                metadata={
                    "source_query_id": query_id,
                    "docs_total": len(docs),
                },
            )
        )

        if task_id_filter:
            break

    assert_unique_task_ids(tasks, scope="browsecomp_plus")

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(docs_by_query_id, default_max_docs=max_docs_per_tool_call),
        signature=BrowseCompPlusSignature,
        metadata={
            "source": "huggingface_datasets",
            "dataset_id": dataset_id,
            "config": config,
            "split": split,
            "task_limit": task_limit,
            "task_id_filter": task_id_filter or None,
            "loaded_tasks": len(tasks),
            "max_docs_per_task": max_docs_per_task,
            "max_docs_per_tool_call": max_docs_per_tool_call,
        },
    )
