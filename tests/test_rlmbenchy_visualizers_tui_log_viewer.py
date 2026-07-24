from __future__ import annotations

import json
from pathlib import Path

from otel_fixture_support import to_otel_fixture_records
from rlmbenchy.visualizers.tui.log_viewer import (
    ViewerState,
    load_run_payload,
    load_runs,
    refresh_current_run,
    wrap_lines,
)


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    )
    path.write_text(payload + "\n", encoding="utf-8")


def test_wrap_lines_splits_by_width() -> None:
    assert wrap_lines("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_load_runs_and_payload_use_otel_logs(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    log_path = log_dir / "rlm_2026-03-07_12-00-00_tui12345.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_tui",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_tui",
                "task_id": "t1",
                "data": {"query": "task body", "task_inputs": {"task": "task body"}},
            },
            {
                "event_type": "step.started",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
            },
            {
                "event_type": "llm.request",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call_lm_1",
            },
            {
                "event_type": "llm.response",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call_lm_1",
                "data": {"reasoning_text": "think"},
            },
            {
                "event_type": "repl.request",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "data": {"code": "print('ok')"},
            },
            {
                "event_type": "repl.response",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "data": {"output": "ok"},
            },
            {
                "event_type": "repl.final",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "data": {"final_outputs": {"answer": "ok"}},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_tui",
                "task_id": "t1",
                "step_index": 1,
                "data": {"status": "success", "stop_reason": "final"},
                "stats": {"elapsed_ms": 12},
                "summary": {"parse_success": True, "final_signal": True},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_tui",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                    "observed": 'ok\n\n{"answer": "ok"}',
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_tui",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 12},
            },
        ],
    )

    runs = load_runs(log_dir)
    assert len(runs) == 1
    assert runs[0]["log_file"] == log_path.name

    payload = load_run_payload(log_dir, runs[0])
    assert payload["run_id"] == "run_tui"
    assert payload["summary"]["status"] == "success"
    assert payload["tasks"][0]["steps"][0]["reasoning"] == "think"


def test_refresh_current_run_updates_payload_and_clamps_step_index(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = ViewerState(
        runs=[{"log_file": "rlm_2026-03-04_17-09-37_61e833d8.jsonl"}],
        run_index=0,
        step_index=5,
    )
    state.current = {"tasks": [{"task_id": "old"}]}

    def _fake_load_run_payload(_log_dir: Path, _run_row: dict) -> dict:
        steps = [
            {"step_index": 1, "task_id": "new_t1"},
            {"step_index": 2, "task_id": "new_t1"},
        ]
        return {
            "log_file": "rlm_2026-03-04_17-09-37_61e833d8.jsonl",
            "summary": {"status": "running"},
            "tasks": [{"task_id": "new_t1", "steps": steps}],
            "all_steps": steps,
        }

    monkeypatch.setattr(
        "rlmbenchy.visualizers.tui.log_viewer.load_run_payload",
        _fake_load_run_payload,
    )

    refresh_current_run(state, tmp_path)

    assert state.current is not None
    assert [task["task_id"] for task in state.current["tasks"]] == ["new_t1"]
    assert state.step_index == 1
