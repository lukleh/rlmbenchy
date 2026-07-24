from __future__ import annotations

from typing import Any

import pytest

from rlmbenchy.datahub.workloads import longcot as workload_module
from rlmbenchy.datahub.workloads.longcot import (
    WORKLOAD_NAME,
    LongCoTSignature,
    load_workload,
)
from rlmbenchy.datahub.workloads.longcot import source as longcot_source
from rlmbenchy.datahub.workloads.longcot.source import (
    extract_raw_answer,
    extract_raw_answer_encoded,
    extract_template,
    longcot_row_to_task,
    task_id_for_row,
)


def _hf_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "question_id": "Sudoku_easy_1",
        "domain": "logic",
        "difficulty": "easy",
        "template": "Sudoku",
        "prompt": "Solve this Sudoku and return solution = <grid>.",
        "answer": "null",
        "canary": "canary-guid-001",
    }
    base.update(overrides)
    return base


def _bundled_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "question_id": "BlocksWorld_easy_1",
        "domain": "logic",
        "difficulty": "easy",
        "prompt": "Rearrange the blocks and return solution = [...].",
        "answer": None,
        "problem": {
            "template": "BlocksWorld",
            "config": {"n": 60, "k": 3},
            "instance": {"initial_state": [], "goal_state": []},
        },
    }
    base.update(overrides)
    return base


def test_longcot_loader_produces_workload_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        workload_module,
        "iter_longcot_tasks",
        lambda **_kwargs: iter(
            [
                {
                    "task_id": "Sudoku_easy_1",
                    "prompt": "Solve this Sudoku.",
                    "metadata": {
                        "source": "longcot",
                        "domain": "logic",
                        "difficulty": "easy",
                        "template": "Sudoku",
                        "question_id": "Sudoku_easy_1",
                        "config": "logic",
                        "split": "easy",
                        "row_index": 0,
                        "raw_answer": None,
                        "canary": "canary-guid-001",
                    },
                }
            ]
        ),
    )

    bundle = load_workload(None, None, {})

    assert bundle.workload_name == WORKLOAD_NAME == "longcot"
    assert bundle.tools == []
    assert bundle.signature is LongCoTSignature
    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    assert task.id == "Sudoku_easy_1"
    assert task.inputs == {"prompt": "Solve this Sudoku."}
    assert task.answer is None
    assert task.metadata["domain"] == "logic"
    assert task.metadata["difficulty"] == "easy"
    assert task.metadata["template"] == "Sudoku"
    assert task.metadata["question_id"] == "Sudoku_easy_1"
    assert task.metadata["raw_answer"] is None
    assert task.metadata["canary"] == "canary-guid-001"
    assert bundle.metadata["source"] == "hf_datasets_server"
    assert bundle.metadata["dataset_id"] == "LongHorizonReasoning/longcot"
    assert bundle.metadata["config"] == "logic"
    assert bundle.metadata["split"] == "easy"
    assert bundle.metadata["loaded_tasks"] == 1


def test_longcot_source_row_to_task_maps_hf_row() -> None:
    task = longcot_row_to_task(_hf_row(), index=0, config="logic", split="easy")
    assert task is not None
    assert task["task_id"] == "longcot_logic_easy_logic_row_00000_Sudoku_easy_1"
    assert task["prompt"].startswith("Solve this Sudoku")
    assert task["metadata"]["template"] == "Sudoku"
    assert task["metadata"]["question_id"] == "Sudoku_easy_1"
    assert task["metadata"]["raw_answer"] is None  # "null" → None
    assert task["metadata"]["raw_answer_encoded"] == "null"
    assert task["metadata"]["canary"] == "canary-guid-001"


def test_longcot_source_row_to_task_maps_bundled_row() -> None:
    task = longcot_row_to_task(_bundled_row(), index=0, config="logic", split="easy")
    assert task is not None
    assert task["metadata"]["template"] == "BlocksWorld"
    assert task["metadata"]["question_id"] == "BlocksWorld_easy_1"
    assert task["metadata"]["raw_answer"] is None
    assert task["metadata"]["raw_answer_encoded"] is None


def test_longcot_source_task_id_falls_back_when_missing() -> None:
    row = _hf_row(question_id="")
    task = longcot_row_to_task(row, index=0, config="logic", split="easy")
    assert task is not None
    assert task["task_id"] == "longcot_logic_easy_logic_row_00000"


def test_longcot_source_task_id_for_row_helper_synthesizes_id() -> None:
    assert (
        task_id_for_row({"question_id": ""}, index=3, config="math", split="hard")
        == "longcot_math_hard_row_00003"
    )
    assert (
        task_id_for_row({"question_id": "custom"}, index=0, config="math", split="hard")
        == "longcot_math_hard_row_00000_custom"
    )


def test_longcot_source_task_id_for_row_namespaces_all_config_ids() -> None:
    assert (
        task_id_for_row(
            {"question_id": "401", "domain": "math"},
            index=0,
            config="all",
            split="hard",
        )
        == "longcot_all_hard_math_row_00000_401"
    )
    assert (
        task_id_for_row(
            {"question_id": "math_401", "domain": "math"},
            index=0,
            config="all",
            split="hard",
        )
        == "longcot_all_hard_math_row_00000_math_401"
    )


def test_longcot_source_row_to_task_skips_empty_prompt() -> None:
    row = _hf_row(prompt="")
    assert longcot_row_to_task(row, index=0, config="logic", split="easy") is None


def test_longcot_extract_template_prefers_top_level_then_problem() -> None:
    assert extract_template({"template": "Sudoku"}) == "Sudoku"
    assert extract_template({"problem": {"template": "BlocksWorld"}}) == "BlocksWorld"
    assert extract_template({}) is None
    assert extract_template({"template": "   "}) is None


def test_longcot_extract_raw_answer_parses_hf_json_strings() -> None:
    assert extract_raw_answer({"answer": "null"}) is None
    assert extract_raw_answer({"answer": '["2013^{4025}", "2692"]'}) == [
        "2013^{4025}",
        "2692",
    ]
    assert extract_raw_answer({"answer": '"canonical_smiles"'}) == "canonical_smiles"
    assert extract_raw_answer({"answer": '{"q1": "a", "q2": "b"}'}) == {
        "q1": "a",
        "q2": "b",
    }


def test_longcot_extract_raw_answer_encoded_preserves_wire_bytes() -> None:
    assert extract_raw_answer_encoded({"answer": "null"}) == "null"
    assert (
        extract_raw_answer_encoded({"answer": '"canonical_smiles"'})
        == '"canonical_smiles"'
    )
    # Bare-token convention violation: raw_answer would type-flip to int,
    # but the wire bytes stay recoverable here.
    assert extract_raw_answer_encoded({"answer": "1"}) == "1"
    assert extract_raw_answer({"answer": "1"}) == 1
    # Bundled-JSON shape: answer is already native, no wire string to keep.
    assert extract_raw_answer_encoded({"answer": None}) is None
    assert extract_raw_answer_encoded({"answer": ["a", "b"]}) is None
    assert extract_raw_answer_encoded({}) is None


def test_longcot_extract_raw_answer_preserves_native_bundled_types() -> None:
    assert extract_raw_answer({"answer": None}) is None
    assert extract_raw_answer({"answer": ["a", "b"]}) == ["a", "b"]
    assert extract_raw_answer({"answer": {"q1": "a"}}) == {"q1": "a"}
    assert extract_raw_answer({"answer": 42}) == 42


def test_longcot_extract_raw_answer_falls_back_to_string_on_invalid_json() -> None:
    assert extract_raw_answer({"answer": "not-valid-json-{"}) == "not-valid-json-{"


def test_longcot_loader_raises_when_all_rows_skipped(monkeypatch) -> None:
    monkeypatch.setattr(
        workload_module, "iter_longcot_tasks", lambda **_kwargs: iter(())
    )

    with pytest.raises(RuntimeError, match="No LongCoT tasks were loaded."):
        load_workload(None, None, {})


def test_longcot_loader_respects_task_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        workload_module,
        "iter_longcot_tasks",
        lambda **_kwargs: iter(
            [
                {
                    "task_id": f"t{i}",
                    "prompt": f"prompt {i}",
                    "metadata": {
                        "source": "longcot",
                        "domain": "logic",
                        "difficulty": "easy",
                        "template": "BlocksWorld",
                        "question_id": f"t{i}",
                        "config": "logic",
                        "split": "easy",
                        "row_index": i,
                        "raw_answer": None,
                        "canary": None,
                    },
                }
                for i in range(5)
            ]
        ),
    )

    bundle = load_workload(2, None, {})
    assert [task.id for task in bundle.tasks] == ["t0", "t1"]


def test_longcot_loader_filters_to_single_task_id(monkeypatch) -> None:
    monkeypatch.setattr(
        workload_module,
        "iter_longcot_tasks",
        lambda **_kwargs: iter(
            [
                {
                    "task_id": task_id,
                    "prompt": "p",
                    "metadata": {
                        "source": "longcot",
                        "domain": "logic",
                        "difficulty": "easy",
                        "template": "BlocksWorld",
                        "question_id": task_id,
                        "config": "logic",
                        "split": "easy",
                        "row_index": index,
                        "raw_answer": None,
                        "canary": None,
                    },
                }
                for index, task_id in enumerate(["t0", "t1", "t2"])
            ]
        ),
    )

    bundle = load_workload(None, "t1", {})
    assert [task.id for task in bundle.tasks] == ["t1"]


def test_longcot_loader_real_path_supports_bundled_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        longcot_source, "iter_rows", lambda **_kwargs: iter([_bundled_row()])
    )

    bundle = load_workload(None, None, {})

    assert [task.id for task in bundle.tasks] == [
        "longcot_logic_easy_logic_row_00000_BlocksWorld_easy_1"
    ]
    assert bundle.tasks[0].metadata["template"] == "BlocksWorld"
    assert bundle.tasks[0].metadata["question_id"] == "BlocksWorld_easy_1"


def test_longcot_loader_task_id_lookup_scans_past_smoke_default(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    rows = [_hf_row(question_id=f"Sudoku_easy_{index}") for index in range(1, 7)]
    seen_ids: list[str] = []

    def _iter_rows(**kwargs: Any):
        captured.update(kwargs)
        for row in rows:
            seen_ids.append(str(row["question_id"]))
            yield row

    monkeypatch.setattr(longcot_source, "iter_rows", _iter_rows)

    bundle = load_workload(
        None,
        "longcot_logic_easy_logic_row_00005_Sudoku_easy_6",
        {},
    )

    assert captured["max_rows"] is None
    assert [task.id for task in bundle.tasks] == [
        "longcot_logic_easy_logic_row_00005_Sudoku_easy_6"
    ]
    assert seen_ids == [f"Sudoku_easy_{index}" for index in range(1, 7)]


def test_longcot_loader_namespaces_duplicate_ids_for_all_config(monkeypatch) -> None:
    monkeypatch.setattr(
        longcot_source,
        "iter_rows",
        lambda **_kwargs: iter(
            [
                _hf_row(
                    question_id="401",
                    domain="chess",
                    difficulty="hard",
                    template="max_rooks",
                ),
                _hf_row(
                    question_id="401",
                    domain="math",
                    difficulty="hard",
                    template="dag",
                ),
            ]
        ),
    )

    bundle = load_workload(
        None, None, {"config": "all", "split": "hard", "max_rows": 2}
    )

    assert [task.id for task in bundle.tasks] == [
        "longcot_all_hard_chess_row_00000_401",
        "longcot_all_hard_math_row_00001_401",
    ]
    assert [task.metadata["question_id"] for task in bundle.tasks] == ["401", "401"]
