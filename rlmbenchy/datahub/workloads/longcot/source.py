"""LongCoT source helpers shared by the workload loader."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from rlmbenchy.datahub.workloads.support.hf import iter_rows
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_payload_ids,
    canonical_task_id,
    normalize_task_id_filter,
    task_id_matches,
)

DEFAULT_DATASET_ID = "LongHorizonReasoning/longcot"
DEFAULT_CONFIG = "logic"
DEFAULT_SPLIT = "easy"
DEFAULT_MAX_ROWS = 5


def extract_prompt(row: dict[str, Any]) -> str:
    return str(row.get("prompt") or "").strip()


def extract_domain(row: dict[str, Any]) -> str | None:
    return str(row.get("domain") or "").strip() or None


def extract_question_id(row: dict[str, Any]) -> str | None:
    return str(row.get("question_id") or "").strip() or None


def extract_template(row: dict[str, Any]) -> str | None:
    value = row.get("template")
    if isinstance(value, str) and value.strip():
        return value.strip()
    problem = row.get("problem")
    if isinstance(problem, dict):
        nested = problem.get("template")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def extract_raw_answer(row: dict[str, Any]) -> Any:
    """Return the row's answer in its native shape.

    On HF, ``answer`` is a JSON-encoded string (``"null"`` when bundled data
    would have ``None``, ``'["a", "b"]'`` for list answers, ``'"SMILES"'``
    for string answers, etc.). Parse if possible; otherwise return as-is.
    """

    value = row.get("answer")
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text
    return value


def extract_raw_answer_encoded(row: dict[str, Any]) -> str | None:
    """Return the answer's original wire bytes (HF JSON-string) when available.

    Stored alongside ``raw_answer`` so an offline verifier can distinguish a
    convention violation like a bare ``"1"`` token (which ``json.loads`` turns
    into ``int(1)``) from an intentionally wrapped ``'"1"'`` string. Returns
    ``None`` when the upstream field is not a string (bundled JSON shape).
    """

    value = row.get("answer")
    if isinstance(value, str):
        return value
    return None


def task_id_for_row(row: dict[str, Any], *, index: int, config: str, split: str) -> str:
    raw_id = extract_question_id(row)
    domain = extract_domain(row)
    parts = ["longcot", config, split]
    if domain:
        parts.append(domain)
    parts.append(f"row_{index:05d}")
    if raw_id:
        parts.append(raw_id)
    return canonical_task_id(*parts)


def longcot_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
) -> dict[str, Any] | None:
    prompt = extract_prompt(row)
    if not prompt:
        return None
    domain = extract_domain(row)
    question_id = extract_question_id(row)
    return {
        "task_id": task_id_for_row(row, index=index, config=config, split=split),
        "prompt": prompt,
        "metadata": {
            "source": "longcot",
            "domain": domain,
            "difficulty": str(row.get("difficulty") or "").strip() or None,
            "template": extract_template(row),
            "question_id": question_id,
            "config": config,
            "split": split,
            "row_index": index,
            "raw_answer": extract_raw_answer(row),
            "raw_answer_encoded": extract_raw_answer_encoded(row),
            "canary": row.get("canary"),
        },
    }


def iter_longcot_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    max_rows: int | None = DEFAULT_MAX_ROWS,
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
        task = longcot_row_to_task(row, index=index, config=config, split=split)
        if task is not None:
            yield task
            if task_id_filter:
                break


def load_longcot_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    max_rows: int | None = DEFAULT_MAX_ROWS,
    token: str | None = None,
) -> list[dict[str, Any]]:
    tasks = list(
        iter_longcot_tasks(
            dataset_id=dataset_id,
            config=config,
            split=split,
            max_rows=max_rows,
            token=token,
        )
    )
    if not tasks:
        raise RuntimeError("No LongCoT tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="longcot")
    return tasks


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_DATASET_ID",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_SPLIT",
    "extract_domain",
    "extract_prompt",
    "extract_question_id",
    "extract_raw_answer",
    "extract_raw_answer_encoded",
    "extract_template",
    "iter_longcot_tasks",
    "load_longcot_tasks",
    "longcot_row_to_task",
    "task_id_for_row",
]
