"""OOLONG-Pairs source helpers shared by the workload and local entrypoints."""

from collections.abc import Iterator
from typing import Any

from rlmbenchy.datahub.workloads.support.hf import iter_rows
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_payload_ids,
    canonical_task_id,
    normalize_task_id_filter,
    task_id_matches,
)

OOLONG_PAIRS_QUERY_TEMPLATES: tuple[str, ...] = (
    "List all user ID pairs where both users have at least one numeric value or location.",
    "List all user ID pairs where both users have at least one entity or human being.",
    "List all user ID pairs where both users have at least one description/abstract concept or abbreviation.",
    "List all user ID pairs where both users have at least one location or abbreviation.",
    "List all user ID pairs such that one user has at least one entity and one abbreviation, and the other user has exactly one entity.",
)

DEFAULT_DATASET_ID = "oolongbench/oolong-synth"
DEFAULT_CONFIG = "default"
DEFAULT_SPLIT = "test"


def extract_context(row: dict[str, Any]) -> str:
    return str(row.get("context_window_text") or "").strip()


def resolve_query_index(query_index: int) -> int:
    return max(0, min(int(query_index), len(OOLONG_PAIRS_QUERY_TEMPLATES) - 1))


def query_for_index(query_index: int) -> str:
    return OOLONG_PAIRS_QUERY_TEMPLATES[resolve_query_index(query_index)]


def task_id_for_row(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
    query_index: int,
) -> str:
    source_id = str(row.get("id") or "").strip()
    parts = ("oolong_pairs", config, split, f"query_{query_index}", f"row_{index:05d}")
    if source_id:
        return canonical_task_id(*parts, source_id)
    return canonical_task_id(*parts)


def oolong_pairs_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
    query_index: int = 0,
) -> dict[str, Any] | None:
    context = extract_context(row)
    if not context:
        return None
    resolved_query_index = resolve_query_index(query_index)
    source_id = str(row.get("id") or "").strip() or None
    return {
        "task_id": task_id_for_row(
            row,
            index=index,
            config=config,
            split=split,
            query_index=resolved_query_index,
        ),
        "category": "oolong_pairs",
        "query": OOLONG_PAIRS_QUERY_TEMPLATES[resolved_query_index],
        "context": context,
        "expected": None,
        "dataset_meta": {
            "source": "oolong_pairs",
            "config": config,
            "split": split,
            "row_index": index,
            "query_index": resolved_query_index,
            "source_id": source_id,
        },
    }


def iter_oolong_pairs_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    query_index: int = 0,
    max_rows: int | None = 20,
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
        resolved_query_index = resolve_query_index(query_index)
        raw_task_id = task_id_for_row(
            row,
            index=index,
            config=config,
            split=split,
            query_index=resolved_query_index,
        )
        if not task_id_matches(raw_task_id, task_id_filter):
            continue
        task = oolong_pairs_row_to_task(
            row,
            index=index,
            config=config,
            split=split,
            query_index=query_index,
        )
        if task is not None:
            yield task
            if task_id_filter:
                break


def load_oolong_pairs_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    query_index: int = 0,
    max_rows: int | None = 20,
    token: str | None = None,
) -> list[dict[str, Any]]:
    tasks = list(
        iter_oolong_pairs_tasks(
            dataset_id=dataset_id,
            config=config,
            split=split,
            query_index=query_index,
            max_rows=max_rows,
            token=token,
        )
    )
    if not tasks:
        raise RuntimeError("No OOLONG-Pairs tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="oolong_pairs")
    return tasks


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_DATASET_ID",
    "DEFAULT_SPLIT",
    "OOLONG_PAIRS_QUERY_TEMPLATES",
    "extract_context",
    "iter_oolong_pairs_tasks",
    "load_oolong_pairs_tasks",
    "oolong_pairs_row_to_task",
    "query_for_index",
    "resolve_query_index",
    "task_id_for_row",
]
