"""LongBench-v2 CodeQA workload loader with tool-based code access."""

from typing import Any

import dspy

from rlmbenchy.datahub.types import (
    WorkloadBundle,
    WorkloadTask,
)
from rlmbenchy.datahub.workloads.longbench_codeqa.source import (
    DEFAULT_CONFIG,
    DEFAULT_DATASET_ID,
    DEFAULT_SPLIT,
    iter_longbench_codeqa_tasks,
)
from rlmbenchy.datahub.workloads.longbench_codeqa.tools import build_tools
from rlmbenchy.datahub.workloads.support.task_filters import (
    apply_task_filters,
    filter_payload_by_tasks,
)
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
    put_unique_payload,
)

WORKLOAD_NAME = "longbench_codeqa"


class LongBenchCodeQASignature(dspy.Signature):
    """Answer the code question by examining the code repository.
    Use longbench_get_code_context(task_id) to retrieve the full code."""

    question: str = dspy.InputField(
        desc="The question about the code, including answer options."
    )
    task_id: str = dspy.InputField(
        desc="Task identifier for longbench_get_code_context tool."
    )
    code_lines: int = dspy.InputField(desc="Number of lines in the code context.")
    options: str = dspy.InputField(desc="Multiple choice options (A/B/C/D).")
    answer: str = dspy.OutputField(desc="The option label (A, B, C, or D).")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load LongBench-v2 CodeQA tasks with code context behind a tool."""

    dataset_id = str(options.get("dataset_id", DEFAULT_DATASET_ID)).strip()
    config = str(options.get("config", DEFAULT_CONFIG)).strip()
    split = str(options.get("split", DEFAULT_SPLIT)).strip()
    score_kind = str(options.get("score_kind", "exact")).strip()
    task_id_filter = normalize_task_id_filter(task_id)
    max_rows = options.get("max_rows", 50)
    if max_rows is not None:
        max_rows = int(max_rows)

    task_payloads = iter_longbench_codeqa_tasks(
        dataset_id=dataset_id,
        config=config,
        split=split,
        score_kind=score_kind,
        max_rows=max_rows,
        token=options.get("token"),
        task_id=task_id_filter,
    )

    tasks: list[WorkloadTask] = []
    code_by_task_id: dict[str, str] = {}

    for task_payload in task_payloads:
        raw_id = str(task_payload["task_id"])
        code_context = str(task_payload["code_context"])
        options_block = str(task_payload.get("options") or "")
        metadata = task_payload.get("dataset_meta")
        put_unique_payload(
            code_by_task_id,
            raw_id,
            code_context,
            scope="longbench_codeqa",
        )
        code_lines = code_context.count("\n") + 1

        tasks.append(
            WorkloadTask(
                id=raw_id,
                inputs={
                    "question": str(task_payload["query"]),
                    "task_id": raw_id,
                    "code_lines": code_lines,
                    "options": options_block,
                },
                answer=task_payload.get("expected"),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        )

    if not tasks and task_id_filter is None:
        raise RuntimeError("No LongBench-v2 CodeQA tasks were loaded.")

    tasks = apply_task_filters(tasks, task_id=task_id_filter, task_limit=task_limit)
    assert_unique_task_ids(tasks, scope="longbench_codeqa")
    code_by_task_id = filter_payload_by_tasks(code_by_task_id, tasks)

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(code_by_task_id),
        signature=LongBenchCodeQASignature,
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
