from pathlib import Path

import pytest

import rlmbenchy.datahub.workloads.open_subtitles.source as open_subtitles_module
from rlmbenchy.datahub.workloads.browsecomp_plus.source import browsecomp_row_to_task
from rlmbenchy.datahub.workloads.longbench_codeqa.source import (
    iter_longbench_codeqa_tasks,
    longbench_codeqa_row_to_task,
)
from rlmbenchy.datahub.workloads.oolong.source import oolong_row_to_task
from rlmbenchy.datahub.workloads.oolong_pairs.source import (
    OOLONG_PAIRS_QUERY_TEMPLATES,
    oolong_pairs_row_to_task,
)
from rlmbenchy.datahub.workloads.open_subtitles.source import (
    load_open_subtitles_tasks,
    open_subtitles_row_to_task,
)
from rlmbenchy.datahub.workloads.s_niah.source import build_s_niah_synthetic_task


def test_oolong_pairs_row_to_task() -> None:
    row = {"context_window_text": "ctx", "id": "sample_1"}
    task = oolong_pairs_row_to_task(
        row, index=0, config="default", split="test", query_index=1
    )
    assert task is not None
    assert task["category"] == "oolong_pairs"
    assert task["context"] == "ctx"
    assert task["query"] == OOLONG_PAIRS_QUERY_TEMPLATES[1]
    assert task["expected"] is None


def test_oolong_pairs_row_to_task_ignores_sample_id_alias() -> None:
    row = {"context_window_text": "ctx", "sample_id": "legacy_sample"}
    task = oolong_pairs_row_to_task(
        row, index=0, config="default", split="test", query_index=1
    )

    assert task is not None
    assert task["task_id"] == "oolong_pairs_default_test_query_1_row_00000"


def test_oolong_row_to_task() -> None:
    row = {
        "id": "sample_1",
        "question": "Which city is the capital?",
        "answer": "Prague",
        "context_window_text": "Country: Czech Republic\nCapital: Prague",
    }
    task = oolong_row_to_task(row, index=0, config="default", split="test")
    assert task is not None
    assert task["category"] == "oolong"
    assert task["task_id"] == "oolong_default_test_row_00000_sample_1"
    assert task["query"] == "Which city is the capital?"
    assert task["expected"]["value"] == "Prague"


def test_oolong_row_to_task_ignores_sample_id_alias() -> None:
    row = {
        "sample_id": "legacy_sample",
        "question": "Which city is the capital?",
        "answer": "Prague",
        "context_window_text": "Country: Czech Republic\nCapital: Prague",
    }

    task = oolong_row_to_task(row, index=0, config="default", split="test")

    assert task is not None
    assert task["task_id"] == "oolong_default_test_row_00000"


def test_longbench_codeqa_row_to_task() -> None:
    row = {
        "_id": "66fa208bbb02136c067c5fc1",
        "sub_domain": "Code repo QA",
        "question": "What is correct?",
        "context": "repo context",
        "choice_A": "one",
        "choice_B": "two",
        "choice_C": "three",
        "choice_D": "four",
        "answer": "B",
    }
    task = longbench_codeqa_row_to_task(row, index=0, split="train")
    assert task is not None
    assert task["category"] == "longbench_v2_codeqa"
    assert (
        task["task_id"]
        == "longbench_codeqa_default_train_row_00000_66fa208bbb02136c067c5fc1"
    )
    assert task["dataset_meta"]["source_id"] == "66fa208bbb02136c067c5fc1"
    assert "Options" in task["context"]
    assert task["code_context"] == "repo context"
    assert task["options"] == "A. one\nB. two\nC. three\nD. four"
    assert task["expected"]["value"] == "B"


def test_longbench_codeqa_row_to_task_ignores_sample_id_alias() -> None:
    row = {
        "sub_domain": "Code repo QA",
        "sample_id": "legacy_sample",
        "question": "What is correct?",
        "context": "repo context",
        "choice_A": "one",
        "choice_B": "two",
        "choice_C": "three",
        "choice_D": "four",
        "answer": "B",
    }

    task = longbench_codeqa_row_to_task(row, index=0, split="train")

    assert task is not None
    assert task["task_id"] == "longbench_codeqa_default_train_row_00000"


def test_longbench_codeqa_max_rows_zero_does_not_read_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_load_dataset(*args, **kwargs):
        raise AssertionError("dataset should not be loaded")

    monkeypatch.setattr("datasets.load_dataset", _fail_load_dataset)

    assert list(iter_longbench_codeqa_tasks(max_rows=0)) == []


def test_longbench_codeqa_row_to_task_keeps_raw_context_with_options_heading() -> None:
    row = {
        "sub_domain": "Code repo QA",
        "question": "Which option is correct?",
        "context": "README\n\nOptions:\nkeep this heading\n\nsrc/main.py",
        "choice_A": "alpha",
        "choice_B": "beta",
        "choice_C": "gamma",
        "choice_D": "delta",
        "answer": "C",
    }

    task = longbench_codeqa_row_to_task(row, index=0, split="train")

    assert task is not None
    assert task["code_context"] == row["context"]
    assert task["options"] == "A. alpha\nB. beta\nC. gamma\nD. delta"
    assert task["context"].startswith(row["context"])


def test_browsecomp_row_to_task() -> None:
    row = {
        "query_id": "q1",
        "query": "Who wrote the paper?",
        "answer": "Alice Smith",
        "gold_docs": [{"title": "Doc1", "text": "Alice Smith wrote it."}],
        "evidence_docs": [],
        "negative_docs": [],
    }
    task = browsecomp_row_to_task(row, index=0, split="test", max_docs=5)
    assert task is not None
    assert task["category"] == "browsecomp_plus"
    assert "[DOC 1]" in task["context"]
    assert task["expected"]["kind"] == "contains"


def test_browsecomp_row_to_task_ignores_id_alias() -> None:
    row = {
        "id": "legacy_q1",
        "query": "Who wrote the paper?",
        "answer": "Alice Smith",
        "gold_docs": [{"title": "Doc1", "text": "Alice Smith wrote it."}],
        "evidence_docs": [],
        "negative_docs": [],
    }

    task = browsecomp_row_to_task(row, index=0, split="test", max_docs=5)

    assert task is not None
    assert task["task_id"] == "browsecomp_plus_default_test_row_00000_row_00001"


def test_browsecomp_row_to_task_requires_canonical_answer_field() -> None:
    row = {
        "query_id": "q1",
        "query": "Who wrote the paper?",
        "gold_answer": "Alice Smith",
        "gold_docs": [{"title": "Doc1", "text": "Alice Smith wrote it."}],
        "evidence_docs": [],
        "negative_docs": [],
    }

    assert browsecomp_row_to_task(row, index=0, split="test", max_docs=5) is None


def test_browsecomp_row_to_task_keeps_all_docs_by_default() -> None:
    row = {
        "query_id": "q1",
        "query": "Who wrote the paper?",
        "answer": "Alice Smith",
        "gold_docs": [{"title": "Doc1", "text": "Alice Smith wrote it."}],
        "evidence_docs": [{"title": "Doc2", "text": "Supporting evidence."}],
        "negative_docs": [{"title": "Doc3", "text": "Distractor."}],
    }
    task = browsecomp_row_to_task(row, index=0, split="test")
    assert task is not None
    assert task["context"].count("[DOC ") == 3
    assert "Doc3" in task["context"]


def test_build_s_niah_synthetic_task_deterministic() -> None:
    task_a = build_s_niah_synthetic_task(seed=7, haystack_lines=40)
    task_b = build_s_niah_synthetic_task(seed=7, haystack_lines=40)
    assert task_a["expected"] == task_b["expected"]
    assert task_a["context"] == task_b["context"]
    assert task_a["category"] == "s_niah_synthetic"
    assert task_a["task_id"] == "s_niah_synthetic_seed_7_lines_40_account_id"


def test_open_subtitles_row_to_task_forward_and_reverse() -> None:
    row = {
        "id": "13",
        "translation": {"en": "Where are you going?", "hi": "tum kahaan ja rahe ho?"},
        "meta": {"year": 2017, "imdbId": 7006210},
    }
    forward = open_subtitles_row_to_task(
        row,
        index=13,
        config="en-hi",
        split="train",
        direction="forward",
    )
    assert forward is not None
    assert forward["category"] == "open_subtitles"
    assert forward["expected"]["value"] == "tum kahaan ja rahe ho?"
    assert "Translate the subtitle text from en to hi" in forward["query"]

    reverse = open_subtitles_row_to_task(
        row,
        index=13,
        config="en-hi",
        split="train",
        direction="reverse",
    )
    assert reverse is not None
    assert reverse["expected"]["value"] == "Where are you going?"
    assert "Translate the subtitle text from hi to en" in reverse["query"]


def test_load_open_subtitles_tasks_rejects_non_train_split() -> None:
    with pytest.raises(ValueError, match="split='train'"):
        load_open_subtitles_tasks(split="test", max_rows=1)


def test_open_subtitles_cache_path_uses_runtime_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RLMBENCHY_CACHE_DIR", str(cache_dir))

    cached_path = open_subtitles_module._cached_zip_path(
        "https://example.com/archive.zip",
        "en-hi",
    )

    assert cached_path.parent == cache_dir / "datahub" / "open_subtitles"
    assert cached_path.name.startswith("en-hi_")
    assert cached_path.suffix == ".zip"


def test_load_open_subtitles_tasks_uses_train_split_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rows = [
        {
            "id": "7",
            "translation": {"en": "Good night.", "hi": "shubh ratri."},
            "meta": {"year": 2017, "imdbId": 7006210},
        }
    ]
    monkeypatch.setattr(
        "rlmbenchy.datahub.workloads.open_subtitles.source._load_open_subtitles_rows",
        lambda **_: fake_rows,
    )

    tasks = load_open_subtitles_tasks(split="train", config="en-hi", max_rows=1)
    assert len(tasks) == 1
    assert tasks[0]["dataset_meta"]["split"] == "train"
