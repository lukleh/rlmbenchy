"""LongBench-v2 CodeQA source helpers shared by the workload and local entrypoints."""

from collections.abc import Iterator
from typing import Any

from rlmbenchy.datahub.workloads.support.hf import coerce_expected, iter_rows
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_payload_ids,
    canonical_task_id,
    normalize_task_id_filter,
    task_id_matches,
)

DEFAULT_DATASET_ID = "zai-org/LongBench-v2"
DEFAULT_CONFIG = "default"
DEFAULT_SPLIT = "train"


def is_codeqa_row(row: dict[str, Any]) -> bool:
    return str(row.get("sub_domain") or "").strip() == "Code repo QA"


def extract_question(row: dict[str, Any]) -> str:
    return str(row.get("question") or "").strip()


def extract_context(row: dict[str, Any]) -> str:
    return str(row.get("context") or "").strip()


def extract_answer(row: dict[str, Any]) -> str:
    return str(row.get("answer") or "").strip()


def extract_options(row: dict[str, Any]) -> list[str]:
    choices: list[str] = []
    for label in ("A", "B", "C", "D"):
        value = str(row.get(f"choice_{label}") or "").strip()
        if value:
            choices.append(f"{label}. {value}")
    return choices


def build_query(question: str) -> str:
    return (
        f"{question}\n\n"
        "Choose the best option and return only the final option label "
        "(A, B, C, or D)."
    )


def task_id_for_row(row: dict[str, Any], *, index: int, config: str, split: str) -> str:
    source_id = str(row.get("_id") or row.get("id") or "").strip()
    parts = ("longbench_codeqa", config, split, f"row_{index:05d}")
    if source_id:
        return canonical_task_id(*parts, source_id)
    return canonical_task_id(*parts)


def longbench_codeqa_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str = DEFAULT_CONFIG,
    split: str,
    score_kind: str = "exact",
) -> dict[str, Any] | None:
    if not is_codeqa_row(row):
        return None
    question = extract_question(row)
    context = extract_context(row)
    answer = extract_answer(row)
    if not question or not context or not answer:
        return None
    source_id = str(row.get("_id") or row.get("id") or "").strip() or None

    merged_context = context
    options = extract_options(row)
    options_block = "\n".join(options)
    if options:
        merged_context = f"{context}\n\nOptions:\n{options_block}"

    return {
        "task_id": task_id_for_row(row, index=index, config=config, split=split),
        "category": "longbench_v2_codeqa",
        "query": build_query(question),
        "context": merged_context,
        "code_context": context,
        "options": options_block,
        "expected": coerce_expected(answer, score_kind),
        "dataset_meta": {
            "source": "longbench_v2",
            "config": config,
            "split": split,
            "row_index": index,
            "source_id": source_id,
        },
    }


def iter_longbench_codeqa_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    score_kind: str = "exact",
    max_rows: int | None = 50,
    token: str | None = None,
    task_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows must be >= 0 or None.")
    task_id_filter = normalize_task_id_filter(task_id)
    if max_rows == 0 and not task_id_filter:
        return
    rows = iter_rows(
        dataset_id=dataset_id,
        config=config,
        split=split,
        max_rows=None,
        token=token,
    )
    emitted_tasks = 0
    for index, row in enumerate(rows):
        raw_task_id = task_id_for_row(row, index=index, config=config, split=split)
        if not task_id_matches(raw_task_id, task_id_filter):
            continue
        task = longbench_codeqa_row_to_task(
            row,
            index=index,
            config=config,
            split=split,
            score_kind=score_kind,
        )
        if task is not None:
            yield task
            emitted_tasks += 1
            if task_id_filter:
                break
            if max_rows is not None and emitted_tasks >= max_rows:
                break


def load_longbench_codeqa_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    score_kind: str = "exact",
    max_rows: int | None = 50,
    token: str | None = None,
) -> list[dict[str, Any]]:
    tasks = list(
        iter_longbench_codeqa_tasks(
            dataset_id=dataset_id,
            config=config,
            split=split,
            score_kind=score_kind,
            max_rows=max_rows,
            token=token,
        )
    )
    if not tasks:
        raise RuntimeError("No LongBench-v2 CodeQA tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="longbench_codeqa")
    return tasks


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_DATASET_ID",
    "DEFAULT_SPLIT",
    "build_query",
    "extract_answer",
    "extract_context",
    "extract_options",
    "extract_question",
    "is_codeqa_row",
    "iter_longbench_codeqa_tasks",
    "load_longbench_codeqa_tasks",
    "longbench_codeqa_row_to_task",
    "task_id_for_row",
]
