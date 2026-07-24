from __future__ import annotations

import pytest

from rlmbenchy.datahub.workloads.support.task_id_audit import (
    audit_json_task_file,
    audit_task_ids,
)


def test_audit_task_ids_reports_unique_rows() -> None:
    audit = audit_task_ids(
        [{"id": "a"}, {"id": "b"}],
        scope="demo",
        task_id_for_row=lambda row, index: str(row.get("id") or f"fallback_{index}"),
    )

    assert audit.scope == "demo"
    assert audit.row_count == 2
    assert audit.task_ids == ("a", "b")
    assert audit.duplicates == ()
    assert audit.has_duplicates is False


def test_audit_task_ids_reports_duplicate_indexes() -> None:
    audit = audit_task_ids(
        [{"id": "a"}, {"id": "b"}, {"id": "a"}],
        scope="demo",
        task_id_for_row=lambda row, _index: str(row["id"]),
    )

    assert audit.has_duplicates is True
    assert audit.duplicates[0].task_id == "a"
    assert audit.duplicates[0].first_index == 0
    assert audit.duplicates[0].duplicate_index == 2


def test_audit_json_task_file_uses_fallback_ids(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"task":"one"},{"id":"custom","task":"two"}]', encoding="utf-8"
    )

    audit = audit_json_task_file(
        tasks_path,
        scope="tasks_v0",
        id_field="id",
        fallback_prefix="v0_task",
    )

    assert audit.task_ids == ("v0_task_001", "custom")


def test_audit_task_ids_rejects_negative_max_rows() -> None:
    with pytest.raises(ValueError, match="max_rows"):
        audit_task_ids(
            [],
            scope="demo",
            task_id_for_row=lambda _row, _index: "unused",
            max_rows=-1,
        )
