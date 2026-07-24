from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlmbenchy.datahub.workloads.transcripts import load_workload
from rlmbenchy.datahub.workloads.support.active_task import active_task


def _write_transcript(root: Path, hash_id: str, segments: list[str]) -> None:
    transcript_dir = root / hash_id
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "transcript.txt").write_text(
        "\n".join(segments) + "\n", encoding="utf-8"
    )


def _tool(bundle, name: str):
    return next(tool.func for tool in bundle.tools if tool.name == name)


def test_transcript_tools_are_scoped_to_active_task(tmp_path: Path) -> None:
    hash_a = "a" * 64
    hash_b = "b" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_a, ["a-one", "a-two"])
    _write_transcript(transcripts_root, hash_b, ["b-one"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "task_a",
                    "query": "Use only transcript A",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_a]}},
                },
                {
                    "id": "task_b",
                    "query": "Use only transcript B",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_b]}},
                },
            ]
        ),
        encoding="utf-8",
    )

    bundle = load_workload(
        task_limit=None,
        task_id=None,
        options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
    )

    list_transcripts = _tool(bundle, "list_transcripts")
    get_segments = _tool(bundle, "get_segments")
    segment_count = _tool(bundle, "segment_count")
    get_segment = _tool(bundle, "get_segment")

    with active_task(bundle.tasks[0].id):
        assert list_transcripts() == [{"hash_id": hash_a, "segment_count": 2}]
        assert segment_count() == 2
        assert get_segment(2) == f"[{hash_a}] a-two"
        with pytest.raises(KeyError):
            get_segments(hash_b)

    with active_task(bundle.tasks[1].id):
        assert list_transcripts() == [{"hash_id": hash_b, "segment_count": 1}]
        assert segment_count() == 1
        assert get_segment(1) == f"[{hash_b}] b-one"
        with pytest.raises(KeyError):
            get_segments(hash_a)


def test_transcript_workload_uses_runtime_config(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    share_dir = tmp_path / "share"
    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("RLMBENCHY_SHARE_DIR", str(share_dir))

    hash_id = "c" * 64
    transcripts_root = share_dir / "datasets" / "transcripts" / "transcripts"
    transcripts_root.mkdir(parents=True)
    _write_transcript(transcripts_root, hash_id, ["segment-one", "segment-two"])

    tasks_path = share_dir / "workloads" / "transcripts" / "tasks.json"
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "task_c",
                    "query": "Use the configured transcript root",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "transcripts.toml").write_text(
        f'root = "{transcripts_root.as_posix()}"\n'
        f'tasks_path = "{tasks_path.as_posix()}"\n',
        encoding="utf-8",
    )

    bundle = load_workload(task_limit=None, task_id=None, options={})

    assert bundle.metadata["root"] == str(transcripts_root.resolve())
    assert bundle.metadata["tasks_path"] == str(tasks_path.resolve())
    assert [task.id for task in bundle.tasks] == ["task_c"]
    assert bundle.tasks[0].inputs["transcripts_count"] == 1


def test_transcript_tasks_env_does_not_override_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    share_dir = tmp_path / "share"
    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("RLMBENCHY_SHARE_DIR", str(share_dir))

    hash_id = "d" * 64
    transcripts_root = share_dir / "datasets" / "transcripts" / "transcripts"
    transcripts_root.mkdir(parents=True)
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    configured_tasks_path = share_dir / "workloads" / "transcripts" / "tasks.json"
    configured_tasks_path.parent.mkdir(parents=True, exist_ok=True)
    configured_tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "configured_task",
                    "query": "Use configured tasks path",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    env_tasks_path = tmp_path / "env_tasks.json"
    env_tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "env_task",
                    "query": "This env-based tasks path should be ignored",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "transcripts.toml").write_text(
        f'root = "{transcripts_root.as_posix()}"\n'
        f'tasks_path = "{configured_tasks_path.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRANSCRIPTS_TASKS", str(env_tasks_path))

    bundle = load_workload(task_limit=None, task_id=None, options={})

    assert bundle.metadata["tasks_path"] == str(configured_tasks_path.resolve())
    assert [task.id for task in bundle.tasks] == ["configured_task"]


def test_transcript_workload_rejects_query_lines_in_default_runtime_share_tasks_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(tmp_path / "config"))
    share_dir = tmp_path / "share"
    monkeypatch.setenv("RLMBENCHY_SHARE_DIR", str(share_dir))

    hash_id = "e" * 64
    transcripts_root = share_dir / "datasets" / "transcripts" / "transcripts"
    transcripts_root.mkdir(parents=True)
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    tasks_path = share_dir / "workloads" / "transcripts" / "tasks.json"
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "default_task",
                    "query_lines": [
                        "Use the selected transcript.",
                        "Return a compact summary.",
                    ],
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    before = tasks_path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="unsupported `query_lines`"):
        load_workload(
            task_limit=None, task_id=None, options={"root": str(transcripts_root)}
        )

    assert tasks_path.read_text(encoding="utf-8") == before


def test_transcript_workload_rejects_query_lines(tmp_path: Path) -> None:
    hash_id = "e" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "task_e",
                    "query": "Use the selected transcript",
                    "query_lines": ["Use the selected transcript"],
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unsupported `query_lines`"):
        load_workload(
            task_limit=None,
            task_id=None,
            options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
        )


def test_transcript_example_tasks_file_loads(tmp_path: Path) -> None:
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, "0" * 64, ["segment-0"])

    tasks_path = (
        Path(__file__).resolve().parents[1]
        / "rlmbenchy"
        / "datahub"
        / "workloads"
        / "transcripts"
        / "tasks.example.json"
    )

    bundle = load_workload(
        task_limit=None,
        task_id=None,
        options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
    )

    assert len(bundle.tasks) == 1
    assert bundle.tasks[0].id == "transcripts_smoke_first_1"


def test_transcript_task_id_takes_precedence_over_task_limit(tmp_path: Path) -> None:
    hash_a = "a" * 64
    hash_b = "b" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_a, ["segment-a"])
    _write_transcript(transcripts_root, hash_b, ["segment-b"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "task_a",
                    "query": "Use transcript A",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_a]}},
                },
                {
                    "id": "task_b",
                    "query": "Use transcript B",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_b]}},
                },
            ]
        ),
        encoding="utf-8",
    )

    bundle = load_workload(
        task_limit=0,
        task_id=" task_b ",
        options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
    )

    assert [task.id for task in bundle.tasks] == ["task_b"]
    assert bundle.tasks[0].metadata["row_index"] == 1


def test_transcript_workload_rejects_task_id_alias(tmp_path: Path) -> None:
    hash_id = "f" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "task_id": "task_f",
                    "query": "Use the selected transcript",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unsupported `task_id`"):
        load_workload(
            task_limit=None,
            task_id=None,
            options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
        )


def test_transcript_workload_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    hash_id = "f" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "dup",
                    "query": "Use the selected transcript",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                },
                {
                    "id": "dup",
                    "query": "Use the selected transcript again",
                    "data": {"selector": {"mode": "HASH_IDS", "value": [hash_id]}},
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Duplicate task ids.*'dup'"):
        load_workload(
            task_limit=None,
            task_id=None,
            options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
        )


def test_transcript_workload_rejects_selector_shorthand(tmp_path: Path) -> None:
    hash_id = "g" * 64
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _write_transcript(transcripts_root, hash_id, ["segment-one"])

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "task_g",
                    "query": "Use the selected transcript",
                    "data": {"hash_ids": [hash_id]},
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unsupported `data.hash_ids`"):
        load_workload(
            task_limit=None,
            task_id=None,
            options={"root": str(transcripts_root), "tasks_path": str(tasks_path)},
        )
