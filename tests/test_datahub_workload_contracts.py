from __future__ import annotations

from rlmbenchy.datahub.workloads import (
    longbench_codeqa,
    oolong,
    oolong_pairs,
    open_subtitles,
)


def test_oolong_loader_normalizes_missing_metadata_to_dict(monkeypatch) -> None:
    monkeypatch.setattr(
        oolong,
        "iter_oolong_tasks",
        lambda **kwargs: [
            {
                "task_id": "t1",
                "context": "Country: Czech Republic",
                "query": "What is the capital?",
                "expected": {"kind": "exact", "value": "Prague"},
                "dataset_meta": None,
            }
        ],
    )
    monkeypatch.setattr(oolong, "build_tools", lambda *args, **kwargs: [])

    bundle = oolong.load_workload(None, None, {})

    assert bundle.tasks[0].metadata == {}


def test_oolong_pairs_loader_normalizes_missing_metadata_to_dict(monkeypatch) -> None:
    monkeypatch.setattr(
        oolong_pairs,
        "iter_oolong_pairs_tasks",
        lambda **kwargs: [
            {
                "task_id": "t1",
                "context": "user_1: Prague",
                "dataset_meta": None,
            }
        ],
    )
    monkeypatch.setattr(oolong_pairs, "build_tools", lambda *args, **kwargs: [])

    bundle = oolong_pairs.load_workload(None, None, {})

    assert bundle.tasks[0].metadata == {}


def test_longbench_loader_normalizes_missing_metadata_to_dict(monkeypatch) -> None:
    monkeypatch.setattr(
        longbench_codeqa,
        "iter_longbench_codeqa_tasks",
        lambda **kwargs: [
            {
                "task_id": "t1",
                "code_context": "def answer(): return 'B'",
                "query": "Which option is correct?",
                "options": "A. A\nB. B",
                "expected": {"kind": "exact", "value": "B"},
                "dataset_meta": None,
            }
        ],
    )
    monkeypatch.setattr(longbench_codeqa, "build_tools", lambda *args, **kwargs: [])

    bundle = longbench_codeqa.load_workload(None, None, {})

    assert bundle.tasks[0].metadata == {}


def test_open_subtitles_loader_normalizes_missing_metadata_to_dict(monkeypatch) -> None:
    monkeypatch.setattr(
        open_subtitles,
        "iter_open_subtitles_tasks",
        lambda **kwargs: [
            {
                "task_id": "t1",
                "query": "Translate this.\n\nWhere are you going?",
                "expected": {"kind": "exact", "value": "Kam jdeš?"},
                "dataset_meta": None,
            }
        ],
    )
    monkeypatch.setattr(open_subtitles, "build_tools", lambda *args, **kwargs: [])

    bundle = open_subtitles.load_workload(None, None, {})

    assert bundle.tasks[0].metadata == {}
