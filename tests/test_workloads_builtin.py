from __future__ import annotations

import pytest

from rlmbenchy.datahub.registry import (
    WORKLOAD_BROWSECOMP_PLUS,
    WORKLOAD_CHECK_ADAPTER_MATRIX,
    WORKLOAD_CHECK_CONTRACT,
    WORKLOAD_LONGBENCH_CODEQA,
    WORKLOAD_OOLONG,
    WORKLOAD_OOLONG_PAIRS,
    WORKLOAD_OPEN_SUBTITLES,
    WORKLOAD_S_NIAH,
    WORKLOAD_TASKS_V0,
    load_workload,
)
from rlmbenchy.datahub.workloads.check_adapter_matrix.source import (
    load_check_adapter_matrix_tasks,
)
from rlmbenchy.datahub.workloads.tasks_v0.source import load_tasks_v0_tasks


def test_tasks_v0_workload_loads_from_path_option(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"id":"t1","task":"one","answer":"ONE"},{"id":"t2","task":"two"}]',
        encoding="utf-8",
    )

    bundle = load_workload(
        WORKLOAD_TASKS_V0,
        task_limit=1,
        task_id=None,
        options={"tasks_path": str(tasks_path)},
    )

    assert bundle.workload_name == WORKLOAD_TASKS_V0
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    assert task.id == "t1"
    assert task.inputs["task"] == "one"
    assert task.answer == "ONE"
    assert bundle.tools == []
    assert bundle.metadata["loaded_tasks"] == 1


def test_tasks_v0_workload_honors_task_limit(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"id":"t1","task":"one"},{"id":"t2","task":"two"},{"id":"t3","task":"three"}]',
        encoding="utf-8",
    )

    bundle = load_workload(
        WORKLOAD_TASKS_V0,
        task_limit=2,
        task_id=None,
        options={"tasks_path": str(tasks_path)},
    )

    assert bundle.metadata["task_limit"] == 2
    assert len(bundle.tasks) == 2


def test_tasks_v0_relative_tasks_path_resolves_from_cwd(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tasks_path = workspace / "relative_tasks.json"
    tasks_path.write_text('[{"id":"rel-1","task":"from cwd"}]', encoding="utf-8")
    monkeypatch.chdir(workspace)

    bundle = load_workload(
        WORKLOAD_TASKS_V0,
        task_limit=1,
        task_id=None,
        options={"tasks_path": "relative_tasks.json"},
    )

    assert bundle.tasks[0].id == "rel-1"
    assert bundle.metadata["tasks_path"] == str(tasks_path.resolve())


@pytest.mark.parametrize(
    ("payload", "pattern"),
    [
        ('[{"task_id":"t1","task":"one"}]', "unsupported `task_id`"),
        ('[{"id":"t1","data":"one"}]', "unsupported `data`"),
    ],
)
def test_tasks_v0_workload_rejects_legacy_row_aliases(
    tmp_path, payload, pattern
) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(payload, encoding="utf-8")

    with pytest.raises(RuntimeError, match=pattern):
        load_workload(
            WORKLOAD_TASKS_V0,
            task_limit=1,
            task_id=None,
            options={"tasks_path": str(tasks_path)},
        )


def test_tasks_v0_generated_ids_preserve_original_row_numbers_when_skipping_non_dict_rows(
    tmp_path,
) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[null,{"task":"one"},{"task":"two"}]',
        encoding="utf-8",
    )

    preview_tasks = load_tasks_v0_tasks(tasks_path=tasks_path)
    bundle = load_workload(
        WORKLOAD_TASKS_V0,
        task_limit=None,
        task_id="v0_task_002",
        options={"tasks_path": str(tasks_path)},
    )

    assert preview_tasks[0]["task_id"] == "v0_task_002"
    assert preview_tasks[0]["dataset_meta"]["row_index"] == 1
    assert [task.id for task in bundle.tasks] == ["v0_task_002"]
    assert bundle.tasks[0].inputs["task"] == "one"


def test_tasks_v0_workload_rejects_duplicate_task_ids(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"id":"dup","task":"one"},{"id":"dup","task":"two"}]',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Duplicate task ids.*'dup'"):
        load_workload(
            WORKLOAD_TASKS_V0,
            task_limit=None,
            task_id=None,
            options={"tasks_path": str(tasks_path)},
        )


def test_check_contract_workload_rejects_duplicate_task_ids(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"task_id":"dup","query":"one"},{"task_id":"dup","query":"two"}]',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Duplicate task ids.*'dup'"):
        load_workload(
            WORKLOAD_CHECK_CONTRACT,
            task_limit=None,
            task_id=None,
            options={"tasks_path": str(tasks_path)},
        )


def test_check_adapter_matrix_generated_ids_preserve_original_row_numbers_when_skipping_non_dict_rows(
    tmp_path,
) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[null,{"query":"one","expected":"ONE"},{"query":"two"}]',
        encoding="utf-8",
    )

    preview_tasks = load_check_adapter_matrix_tasks(tasks_path=tasks_path)
    bundle = load_workload(
        WORKLOAD_CHECK_ADAPTER_MATRIX,
        task_limit=None,
        task_id="matrix_002",
        options={"tasks_path": str(tasks_path)},
    )

    assert preview_tasks[0]["task_id"] == "matrix_002"
    assert preview_tasks[0]["dataset_meta"]["row_index"] == 1
    assert [task.id for task in bundle.tasks] == ["matrix_002"]
    assert bundle.tasks[0].inputs["question"] == "one"


def test_check_adapter_matrix_workload_rejects_duplicate_task_ids(tmp_path) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        '[{"task_id":"dup","query":"one"},{"task_id":"dup","query":"two"}]',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Duplicate task ids.*'dup'"):
        load_workload(
            WORKLOAD_CHECK_ADAPTER_MATRIX,
            task_limit=None,
            task_id=None,
            options={"tasks_path": str(tasks_path)},
        )


def test_unknown_workload_raises_key_error() -> None:
    with pytest.raises(ValueError):
        load_workload("not-a-workload", task_limit=1, task_id=None)


def test_browsecomp_workload_builds_tasks_and_access_tool(monkeypatch) -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "What is the capital?",
            "answer": "Prague",
            "gold_docs": [{"title": "DocA", "text": "Prague is the capital city."}],
            "evidence_docs": [],
            "negative_docs": ["Noise doc."],
        }
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "Tevatron/browsecomp-plus"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert bundle.workload_name == WORKLOAD_BROWSECOMP_PLUS
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    expected_task_id = "browsecomp_plus_default_test_row_00000_q1"
    assert task.id == expected_task_id
    assert task.inputs["question"] == "What is the capital?"
    assert task.answer == "Prague"
    assert task.inputs["query_id"] == expected_task_id
    assert task.inputs["docs_total"] == 2
    assert task.metadata["source_query_id"] == "q1"
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "browsecomp_get_docs"
    tool_output = bundle.tools[0].func(expected_task_id, 0, 1)
    assert tool_output == ["DocA\nPrague is the capital city."]
    assert bundle.tools[0].func(expected_task_id, 99, 1) == []


def test_browsecomp_workload_honors_task_limit_for_fetch(monkeypatch) -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "Q1",
            "gold_docs": ["D1"],
            "evidence_docs": [],
            "negative_docs": [],
        },
        {
            "query_id": "q2",
            "query": "Q2",
            "gold_docs": ["D2"],
            "evidence_docs": [],
            "negative_docs": [],
        },
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert len(bundle.tasks) == 1
    assert bundle.metadata["task_limit"] == 1
    assert len(bundle.tasks) == 1


def test_browsecomp_workload_passes_explicit_token_to_hf_loader(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeDataset:
        def __iter__(self):
            yield {
                "query_id": "q1",
                "query": "Q1",
                "answer": "A1",
                "gold_docs": ["D1"],
                "evidence_docs": [],
                "negative_docs": [],
            }

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        captured["dataset_id"] = dataset_id
        captured["config"] = config
        captured["split"] = split
        captured["token"] = token
        captured["streaming"] = streaming
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=1,
        task_id=None,
        options={"token": "hf-explicit-token"},
    )

    assert bundle.tasks[0].id == "browsecomp_plus_default_test_row_00000_q1"
    assert captured == {
        "dataset_id": "Tevatron/browsecomp-plus",
        "config": "default",
        "split": "test",
        "token": "hf-explicit-token",
        "streaming": False,
    }


def test_browsecomp_workload_keeps_all_docs_by_default(monkeypatch) -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "Q1",
            "answer": "A1",
            "gold_docs": [{"title": "Gold1", "text": "G1"}],
            "evidence_docs": [{"title": "Ev1", "text": "E1"}],
            "negative_docs": [
                {"title": "Neg1", "text": "N1"},
                {"title": "Neg2", "text": "N2"},
            ],
        }
    ]

    class _FakeDataset:
        def __iter__(self):
            return iter(rows)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "Tevatron/browsecomp-plus"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=1,
        task_id=None,
        options={},
    )

    task = bundle.tasks[0]
    assert task.inputs["docs_total"] == 4
    assert bundle.metadata["max_docs_per_task"] is None
    assert bundle.metadata["max_docs_per_tool_call"] is None
    assert bundle.tools[0].func(task.id) == [
        "Gold1\nG1",
        "Ev1\nE1",
        "Neg1\nN1",
        "Neg2\nN2",
    ]


def test_browsecomp_workload_stops_after_matching_runtime_task_id(monkeypatch) -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "Q1",
            "answer": "A1",
            "gold_docs": ["D1"],
            "evidence_docs": [],
            "negative_docs": [],
        },
        {
            "query_id": "q2",
            "query": "Q2",
            "answer": "A2",
            "gold_docs": ["D2"],
            "evidence_docs": [],
            "negative_docs": [],
        },
        {
            "query_id": "q3",
            "query": "Q3",
            "answer": "A3",
            "gold_docs": ["D3"],
            "evidence_docs": [],
            "negative_docs": [],
        },
    ]
    seen_query_ids: list[str] = []

    class _FakeDataset:
        def __iter__(self):
            for row in rows:
                seen_query_ids.append(str(row["query_id"]))
                yield row

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "Tevatron/browsecomp-plus"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=0,
        task_id="browsecomp_plus_default_test_row_00001_q2",
        options={},
    )

    assert [task.id for task in bundle.tasks] == [
        "browsecomp_plus_default_test_row_00001_q2"
    ]
    assert seen_query_ids == ["q1", "q2"]


def test_browsecomp_workload_canonicalizes_duplicate_source_query_ids(
    monkeypatch,
) -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "Q1",
            "answer": "A1",
            "gold_docs": ["D1"],
            "evidence_docs": [],
            "negative_docs": [],
        },
        {
            "query_id": "q1",
            "query": "Q2",
            "answer": "A2",
            "gold_docs": ["D2"],
            "evidence_docs": [],
            "negative_docs": [],
        },
    ]

    class _FakeDataset:
        def __iter__(self):
            return iter(rows)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_BROWSECOMP_PLUS,
        task_limit=None,
        task_id=None,
        options={},
    )

    assert [task.id for task in bundle.tasks] == [
        "browsecomp_plus_default_test_row_00000_q1",
        "browsecomp_plus_default_test_row_00001_q1",
    ]
    assert [task.metadata["source_query_id"] for task in bundle.tasks] == ["q1", "q1"]
    assert bundle.tools[0].func(bundle.tasks[0].id) == ["D1"]
    assert bundle.tools[0].func(bundle.tasks[1].id) == ["D2"]


def test_oolong_workload_builds_tasks_and_context_tool(monkeypatch) -> None:
    rows = [
        {
            "id": "sample_1",
            "question": "Which city is the capital?",
            "answer": "Prague",
            "context_window_text": "Country: Czech Republic\nCapital: Prague",
        }
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "oolongbench/oolong-synth"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_OOLONG,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert bundle.workload_name == WORKLOAD_OOLONG
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    expected_task_id = "oolong_default_test_row_00000_sample_1"
    assert task.id == expected_task_id
    assert task.inputs["question"] == "Which city is the capital?"
    assert task.inputs["task_id"] == expected_task_id
    assert task.inputs["context_lines"] == 2
    assert task.metadata["source_id"] == "sample_1"
    assert task.answer == {"kind": "exact", "value": "Prague"}
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "oolong_get_context"
    assert (
        bundle.tools[0].func(expected_task_id)
        == "Country: Czech Republic\nCapital: Prague"
    )


def test_oolong_task_id_lookup_scans_past_default_max_rows(monkeypatch) -> None:
    rows = [
        {
            "id": "sample_1",
            "question": "Q1",
            "answer": "A1",
            "context_window_text": "C1",
        },
        {
            "id": "target",
            "question": "Q2",
            "answer": "A2",
            "context_window_text": "C2",
        },
        {
            "id": "after",
            "question": "Q3",
            "answer": "A3",
            "context_window_text": "C3",
        },
    ]
    seen_ids: list[str] = []

    class _FakeDataset:
        def __iter__(self):
            for row in rows:
                seen_ids.append(str(row["id"]))
                yield row

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_OOLONG,
        task_limit=None,
        task_id="oolong_default_test_row_00001_target",
        options={"max_rows": 1},
    )

    assert [task.id for task in bundle.tasks] == [
        "oolong_default_test_row_00001_target"
    ]
    assert bundle.tools[0].func("oolong_default_test_row_00001_target") == "C2"
    assert seen_ids == ["sample_1", "target"]


def test_oolong_workload_canonicalizes_duplicate_source_ids(monkeypatch) -> None:
    rows = [
        {
            "id": "dup",
            "question": "Q1",
            "answer": "A1",
            "context_window_text": "C1",
        },
        {
            "id": "dup",
            "question": "Q2",
            "answer": "A2",
            "context_window_text": "C2",
        },
    ]

    class _FakeDataset:
        def __iter__(self):
            return iter(rows)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_OOLONG,
        task_limit=None,
        task_id=None,
        options={},
    )

    assert [task.id for task in bundle.tasks] == [
        "oolong_default_test_row_00000_dup",
        "oolong_default_test_row_00001_dup",
    ]
    assert [task.metadata["source_id"] for task in bundle.tasks] == ["dup", "dup"]


def test_oolong_pairs_workload_builds_tasks_and_context_tool(monkeypatch) -> None:
    rows = [
        {
            "id": "pair_1",
            "context_window_text": "user_1: Prague\nuser_2: Brno",
        }
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "oolongbench/oolong-synth"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_OOLONG_PAIRS,
        task_limit=1,
        task_id=None,
        options={"query_index": 1},
    )

    assert bundle.workload_name == WORKLOAD_OOLONG_PAIRS
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    expected_task_id = "oolong_pairs_default_test_query_1_row_00000_pair_1"
    assert task.id == expected_task_id
    assert "entity or human being" in task.inputs["question"]
    assert task.inputs["task_id"] == expected_task_id
    assert task.inputs["context_lines"] == 2
    assert task.metadata["source_id"] == "pair_1"
    assert task.answer is None
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "oolong_pairs_get_context"
    assert bundle.tools[0].func(expected_task_id) == "user_1: Prague\nuser_2: Brno"


def test_oolong_pairs_task_id_lookup_scans_past_default_max_rows(monkeypatch) -> None:
    rows = [
        {"id": "pair_1", "context_window_text": "C1"},
        {"id": "target", "context_window_text": "C2"},
        {"id": "after", "context_window_text": "C3"},
    ]
    seen_ids: list[str] = []

    class _FakeDataset:
        def __iter__(self):
            for row in rows:
                seen_ids.append(str(row["id"]))
                yield row

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_OOLONG_PAIRS,
        task_limit=None,
        task_id="oolong_pairs_default_test_query_0_row_00001_target",
        options={"max_rows": 1},
    )

    assert [task.id for task in bundle.tasks] == [
        "oolong_pairs_default_test_query_0_row_00001_target"
    ]
    assert (
        bundle.tools[0].func("oolong_pairs_default_test_query_0_row_00001_target")
        == "C2"
    )
    assert seen_ids == ["pair_1", "target"]


def test_longbench_codeqa_workload_builds_tasks_and_code_tool(monkeypatch) -> None:
    rows = [
        {
            "id": "lb_1",
            "sub_domain": "Code repo QA",
            "question": "What should the function return?",
            "context": "def answer():\n    return 'B'",
            "choice_A": "A value",
            "choice_B": "B value",
            "choice_C": "C value",
            "choice_D": "D value",
            "answer": "B",
        }
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "zai-org/LongBench-v2"
        assert config == "default"
        assert split == "train"
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_LONGBENCH_CODEQA,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert bundle.workload_name == WORKLOAD_LONGBENCH_CODEQA
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    expected_task_id = "longbench_codeqa_default_train_row_00000_lb_1"
    assert task.id == expected_task_id
    assert "Choose the best option" in task.inputs["question"]
    assert task.inputs["task_id"] == expected_task_id
    assert task.inputs["code_lines"] == 2
    assert task.metadata["source_id"] == "lb_1"
    assert "A. A value" in task.inputs["options"]
    assert task.answer == {"kind": "exact", "value": "B"}
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "longbench_get_code_context"
    assert bundle.tools[0].func(expected_task_id) == "def answer():\n    return 'B'"


def test_longbench_codeqa_max_rows_counts_emitted_codeqa_tasks(monkeypatch) -> None:
    rows = [
        {
            "_id": "academic_1",
            "sub_domain": "Academic",
            "question": "Skipped?",
            "context": "paper",
            "choice_A": "No",
            "answer": "A",
        },
        {
            "_id": "code_1",
            "sub_domain": "Code repo QA",
            "question": "Q1",
            "context": "code1",
            "choice_A": "One",
            "answer": "A",
        },
        {
            "_id": "code_2",
            "sub_domain": "Code repo QA",
            "question": "Q2",
            "context": "code2",
            "choice_B": "Two",
            "answer": "B",
        },
    ]
    seen_ids: list[str] = []

    class _FakeDataset:
        def __iter__(self):
            for row in rows:
                seen_ids.append(str(row["_id"]))
                yield row

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_LONGBENCH_CODEQA,
        task_limit=None,
        task_id=None,
        options={"max_rows": 1},
    )

    assert [task.id for task in bundle.tasks] == [
        "longbench_codeqa_default_train_row_00001_code_1"
    ]
    assert seen_ids == ["academic_1", "code_1"]


def test_longbench_codeqa_task_id_lookup_scans_past_default_max_rows(
    monkeypatch,
) -> None:
    rows = [
        {
            "id": "lb_1",
            "sub_domain": "Code repo QA",
            "question": "Q1",
            "context": "code1",
            "choice_A": "One",
            "answer": "A",
        },
        {
            "id": "target",
            "sub_domain": "Code repo QA",
            "question": "Q2",
            "context": "code2",
            "choice_B": "Two",
            "answer": "B",
        },
        {
            "id": "after",
            "sub_domain": "Code repo QA",
            "question": "Q3",
            "context": "code3",
            "choice_C": "Three",
            "answer": "C",
        },
    ]
    seen_ids: list[str] = []

    class _FakeDataset:
        def __iter__(self):
            for row in rows:
                seen_ids.append(str(row["id"]))
                yield row

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_LONGBENCH_CODEQA,
        task_limit=None,
        task_id="longbench_codeqa_default_train_row_00001_target",
        options={"max_rows": 1},
    )

    assert [task.id for task in bundle.tasks] == [
        "longbench_codeqa_default_train_row_00001_target"
    ]
    assert (
        bundle.tools[0].func("longbench_codeqa_default_train_row_00001_target")
        == "code2"
    )
    assert seen_ids == ["lb_1", "target"]


def test_longbench_codeqa_workload_preserves_raw_context_with_options_heading(
    monkeypatch,
) -> None:
    rows = [
        {
            "id": "lb_options",
            "sub_domain": "Code repo QA",
            "question": "Which branch is taken?",
            "context": "docs/config.md\n\nOptions:\ninternal heading\n\nif enabled:\n    return 'B'",
            "choice_A": "Branch A",
            "choice_B": "Branch B",
            "choice_C": "Branch C",
            "choice_D": "Branch D",
            "answer": "B",
        }
    ]

    class _FakeDataset:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "zai-org/LongBench-v2"
        assert config == "default"
        assert split == "train"
        assert streaming is False
        return _FakeDataset(rows)

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    bundle = load_workload(
        WORKLOAD_LONGBENCH_CODEQA,
        task_limit=1,
        task_id=None,
        options={},
    )

    task = bundle.tasks[0]
    assert task.inputs["code_lines"] == 7
    assert (
        task.inputs["options"] == "A. Branch A\nB. Branch B\nC. Branch C\nD. Branch D"
    )
    assert (
        bundle.tools[0].func("longbench_codeqa_default_train_row_00000_lb_options")
        == rows[0]["context"]
    )


def test_open_subtitles_workload_builds_tasks_and_source_text_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "rlmbenchy.datahub.workloads.open_subtitles.iter_open_subtitles_tasks",
        lambda **_: iter(
            [
                {
                    "task_id": "os_1",
                    "category": "open_subtitles",
                    "query": (
                        "Translate the subtitle text from en to hi. "
                        "Return only the translated text.\n\nHello there."
                    ),
                    "context": "Domain: movie/TV subtitles\nSource language: en\nTarget language: hi",
                    "expected": {"kind": "exact", "value": "namaste"},
                    "dataset_meta": {
                        "source": "open_subtitles",
                        "dataset_id": "Helsinki-NLP/open_subtitles",
                        "config": "en-hi",
                        "split": "train",
                        "row_index": 0,
                        "direction": "forward",
                        "source_lang": "en",
                        "target_lang": "hi",
                    },
                },
            ]
        ),
    )

    bundle = load_workload(
        WORKLOAD_OPEN_SUBTITLES,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert bundle.workload_name == WORKLOAD_OPEN_SUBTITLES
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    assert task.id == "os_1"
    assert task.inputs["task_id"] == "os_1"
    assert task.inputs["source_lang"] == "en"
    assert task.inputs["target_lang"] == "hi"
    assert task.answer == {"kind": "exact", "value": "namaste"}
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "subtitles_get_source_text"
    assert bundle.tools[0].func("os_1") == "Hello there."


def test_open_subtitles_task_id_lookup_scans_past_default_max_rows(monkeypatch) -> None:
    rows = [
        {
            "id": "0",
            "translation": {"en": "One.", "hi": "uno"},
            "meta": {},
        },
        {
            "id": "target",
            "translation": {"en": "Two.", "hi": "dos"},
            "meta": {},
        },
        {
            "id": "after",
            "translation": {"en": "Three.", "hi": "tres"},
            "meta": {},
        },
    ]
    seen_ids: list[str] = []

    def _fake_iter_open_subtitles_rows(**_kwargs):
        for row in rows:
            seen_ids.append(str(row["id"]))
            yield row

    monkeypatch.setattr(
        "rlmbenchy.datahub.workloads.open_subtitles.source._iter_open_subtitles_rows",
        _fake_iter_open_subtitles_rows,
    )

    bundle = load_workload(
        WORKLOAD_OPEN_SUBTITLES,
        task_limit=None,
        task_id="open_subtitles_en-hi_train_forward_row_00001_target",
        options={"max_rows": 1},
    )

    assert [task.id for task in bundle.tasks] == [
        "open_subtitles_en-hi_train_forward_row_00001_target"
    ]
    assert (
        bundle.tools[0].func("open_subtitles_en-hi_train_forward_row_00001_target")
        == "Two."
    )
    assert seen_ids == ["0", "target"]


def test_open_subtitles_workload_canonicalizes_duplicate_source_ids(
    monkeypatch,
) -> None:
    rows = [
        {"id": "dup", "translation": {"en": "One.", "hi": "uno"}, "meta": {}},
        {"id": "dup", "translation": {"en": "Two.", "hi": "dos"}, "meta": {}},
    ]

    def _fake_iter_open_subtitles_rows(**_kwargs):
        yield from rows

    monkeypatch.setattr(
        "rlmbenchy.datahub.workloads.open_subtitles.source._iter_open_subtitles_rows",
        _fake_iter_open_subtitles_rows,
    )

    bundle = load_workload(
        WORKLOAD_OPEN_SUBTITLES,
        task_limit=None,
        task_id=None,
        options={},
    )

    assert [task.id for task in bundle.tasks] == [
        "open_subtitles_en-hi_train_forward_row_00000_dup",
        "open_subtitles_en-hi_train_forward_row_00001_dup",
    ]
    assert [task.metadata["source_id"] for task in bundle.tasks] == ["dup", "dup"]


def test_s_niah_workload_builds_task_and_haystack_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "rlmbenchy.datahub.workloads.s_niah.build_s_niah_synthetic_task",
        lambda **_: {
            "task_id": "s_niah_synthetic_seed_1_lines_120_account_id",
            "category": "s_niah_synthetic",
            "query": "What is the value of account_id? Return only the value.",
            "context": "record_0000: token_a=111; token_b=222\nrecord_0001: account_id=54321",
            "expected": {"kind": "exact", "value": "54321"},
            "dataset_meta": {
                "source": "s_niah_synthetic",
                "seed": 1,
                "haystack_lines": 120,
                "needle_position": 1,
                "needle_key": "account_id",
            },
        },
    )

    bundle = load_workload(
        WORKLOAD_S_NIAH,
        task_limit=1,
        task_id=None,
        options={},
    )

    assert bundle.workload_name == WORKLOAD_S_NIAH
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    assert task.id == "s_niah_synthetic_seed_1_lines_120_account_id"
    assert task.inputs["task_id"] == "s_niah_synthetic_seed_1_lines_120_account_id"
    assert task.inputs["needle_key"] == "account_id"
    assert task.inputs["haystack_lines"] == 120
    assert task.answer == {"kind": "exact", "value": "54321"}
    assert len(bundle.tools) == 1
    assert bundle.tools[0].name == "s_niah_get_haystack"
    assert bundle.tools[0].func("s_niah_synthetic_seed_1_lines_120_account_id") == (
        "record_0000: token_a=111; token_b=222\nrecord_0001: account_id=54321"
    )
