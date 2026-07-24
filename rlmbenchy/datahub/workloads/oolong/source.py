"""OOLONG source helpers shared by the workload and local entrypoints."""

from collections.abc import Iterator
from typing import Any

from rlmbenchy.datahub.workloads.support.hf import coerce_expected, iter_rows
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_payload_ids,
    canonical_task_id,
    normalize_task_id_filter,
    task_id_matches,
)

DEFAULT_DATASET_ID = "oolongbench/oolong-synth"
DEFAULT_WORKLOAD_CONFIG = "default"
DEFAULT_EXAMPLE_CONFIG = "default"
DEFAULT_SPLIT = "test"


def extract_question(row: dict[str, Any]) -> str:
    return str(row.get("question") or "").strip()


def extract_answer(row: dict[str, Any]) -> str:
    return str(row.get("answer") or "").strip()


def extract_context(row: dict[str, Any]) -> str:
    return str(row.get("context_window_text") or "").strip()


def task_id_for_row(row: dict[str, Any], *, index: int, config: str, split: str) -> str:
    source_id = str(row.get("id") or "").strip()
    if source_id:
        return canonical_task_id("oolong", config, split, f"row_{index:05d}", source_id)
    return canonical_task_id("oolong", config, split, f"row_{index:05d}")


def oolong_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
    score_kind: str = "exact",
) -> dict[str, Any] | None:
    question = extract_question(row)
    answer = extract_answer(row)
    context = extract_context(row)
    if not question or not answer:
        return None

    task_id = task_id_for_row(row, index=index, config=config, split=split)
    source_id = str(row.get("id") or "").strip() or None
    return {
        "task_id": task_id,
        "category": "oolong",
        "query": question,
        "context": context,
        "expected": coerce_expected(answer, score_kind),
        "dataset_meta": {
            "source": "oolong",
            "config": config,
            "split": split,
            "row_index": index,
            "source_id": source_id,
        },
    }


def iter_oolong_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_WORKLOAD_CONFIG,
    split: str = DEFAULT_SPLIT,
    score_kind: str = "exact",
    max_rows: int | None = 50,
    token: str | None = None,
    task_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    task_id_filter = normalize_task_id_filter(task_id)
    rows = iter_rows(
        dataset_id=dataset_id,
        config=config,
        split=split,
        max_rows=None if task_id_filter else max_rows,
        token=token,
    )
    for index, row in enumerate(rows):
        raw_task_id = task_id_for_row(row, index=index, config=config, split=split)
        if not task_id_matches(raw_task_id, task_id_filter):
            continue
        task = oolong_row_to_task(
            row,
            index=index,
            config=config,
            split=split,
            score_kind=score_kind,
        )
        if task is not None:
            yield task
            if task_id_filter:
                break


def load_oolong_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_WORKLOAD_CONFIG,
    split: str = DEFAULT_SPLIT,
    score_kind: str = "exact",
    max_rows: int | None = 50,
    token: str | None = None,
) -> list[dict[str, Any]]:
    tasks = list(
        iter_oolong_tasks(
            dataset_id=dataset_id,
            config=config,
            split=split,
            score_kind=score_kind,
            max_rows=max_rows,
            token=token,
        )
    )
    if not tasks:
        raise RuntimeError("No OOLONG tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="oolong")
    return tasks


__all__ = [
    "DEFAULT_DATASET_ID",
    "DEFAULT_EXAMPLE_CONFIG",
    "DEFAULT_SPLIT",
    "DEFAULT_WORKLOAD_CONFIG",
    "extract_answer",
    "extract_context",
    "extract_question",
    "iter_oolong_tasks",
    "load_oolong_tasks",
    "oolong_row_to_task",
    "task_id_for_row",
]
