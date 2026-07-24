from __future__ import annotations

import pytest

from rlmbenchy.datahub.types import WorkloadTask
from rlmbenchy.datahub.workloads.support.task_filters import apply_task_filters
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_ids,
    assert_unique_task_ids,
    canonical_task_id,
    normalize_task_id_filter,
    normalize_task_id_part,
    put_unique_payload,
)


def test_normalize_task_id_filter_trims_blank_to_none() -> None:
    assert normalize_task_id_filter(None) is None
    assert normalize_task_id_filter("") is None
    assert normalize_task_id_filter("  ") is None
    assert normalize_task_id_filter(" target ") == "target"


def test_canonical_task_id_normalizes_parts_without_collapsing_case() -> None:
    assert normalize_task_id_part("  Code repo QA  ") == "Code_repo_QA"
    assert canonical_task_id("longbench", "default", "row_00001", "ID/42") == (
        "longbench_default_row_00001_ID_42"
    )


def test_assert_unique_task_ids_accepts_unique_tasks() -> None:
    assert_unique_task_ids(
        [
            WorkloadTask(id="t1", inputs={}),
            WorkloadTask(id="t2", inputs={}),
        ],
        scope="test workload",
    )


def test_assert_unique_ids_reports_duplicate_positions() -> None:
    with pytest.raises(RuntimeError, match="'t1' at indexes 0 and 2"):
        assert_unique_ids(["t1", "t2", "t1"], scope="test workload")


def test_put_unique_payload_rejects_duplicate_keys() -> None:
    payloads: dict[str, str] = {}

    put_unique_payload(payloads, "t1", "one", scope="tool payloads")

    with pytest.raises(RuntimeError, match="Duplicate task id.*'t1'"):
        put_unique_payload(payloads, "t1", "two", scope="tool payloads")

    assert payloads == {"t1": "one"}


def test_apply_task_filters_task_id_takes_precedence_over_limit() -> None:
    tasks = [
        WorkloadTask(id="first", inputs={}),
        WorkloadTask(id="target", inputs={}),
    ]

    filtered = apply_task_filters(tasks, task_id=" target ", task_limit=0)

    assert [task.id for task in filtered] == ["target"]
