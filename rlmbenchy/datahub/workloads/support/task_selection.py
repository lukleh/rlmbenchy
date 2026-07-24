"""Shared task selection and task-id validation helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, TypeVar

from rlmbenchy.datahub.types import WorkloadTask

PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True)
class DuplicateId:
    """Diagnostic for one duplicated task id."""

    task_id: str
    first_index: int
    duplicate_index: int


def normalize_task_id_filter(task_id: str | None) -> str | None:
    """Normalize an optional exact task-id selector."""

    if task_id is None:
        return None
    normalized = str(task_id).strip()
    return normalized or None


def normalize_task_id_part(value: object, *, fallback: str = "unknown") -> str:
    """Normalize one component for a canonical task id."""

    text = str(value).strip()
    if not text:
        text = fallback
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return text or fallback


def canonical_task_id(*parts: object) -> str:
    """Build a deterministic task id from source dimensions."""

    return "_".join(normalize_task_id_part(part) for part in parts)


def find_duplicate_ids(ids: Iterable[str]) -> list[DuplicateId]:
    """Return duplicate ids with first and duplicate positions."""

    seen: dict[str, int] = {}
    duplicates: list[DuplicateId] = []
    for index, raw_id in enumerate(ids):
        task_id = str(raw_id).strip()
        if task_id in seen:
            duplicates.append(
                DuplicateId(
                    task_id=task_id,
                    first_index=seen[task_id],
                    duplicate_index=index,
                )
            )
            continue
        seen[task_id] = index
    return duplicates


def assert_unique_ids(ids: Iterable[str], *, scope: str) -> None:
    duplicates = find_duplicate_ids(ids)
    if not duplicates:
        return
    details = ", ".join(
        f"{item.task_id!r} at indexes {item.first_index} and {item.duplicate_index}"
        for item in duplicates[:5]
    )
    if len(duplicates) > 5:
        details += f", and {len(duplicates) - 5} more"
    raise RuntimeError(f"Duplicate task ids in {scope}: {details}")


def assert_unique_task_ids(tasks: Iterable[WorkloadTask], *, scope: str) -> None:
    assert_unique_ids((task.id for task in tasks), scope=scope)


def assert_unique_task_payload_ids(
    payloads: Iterable[Mapping[str, Any]], *, scope: str
) -> None:
    assert_unique_ids(
        (str(payload.get("task_id") or "").strip() for payload in payloads),
        scope=scope,
    )


def put_unique_payload(
    payloads: MutableMapping[str, PayloadT],
    task_id: str,
    payload: PayloadT,
    *,
    scope: str,
) -> None:
    normalized = str(task_id).strip()
    if normalized in payloads:
        raise RuntimeError(f"Duplicate task id in {scope}: {normalized!r}")
    payloads[normalized] = payload


def task_id_matches(task_id: str, selector: str | None) -> bool:
    return selector is None or str(task_id).strip() == selector


__all__ = [
    "DuplicateId",
    "assert_unique_ids",
    "assert_unique_task_ids",
    "assert_unique_task_payload_ids",
    "canonical_task_id",
    "find_duplicate_ids",
    "normalize_task_id_filter",
    "normalize_task_id_part",
    "put_unique_payload",
    "task_id_matches",
]
