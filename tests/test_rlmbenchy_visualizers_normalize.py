from __future__ import annotations

import json
from pathlib import Path

import pytest

from otel_fixture_support import to_otel_fixture_records
from rlmbenchy.logger.projection import build_run_index, normalize_run


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    )
    path.write_text(payload + "\n", encoding="utf-8")


def test_normalize_run_builds_tasks_steps_and_calls_from_otel_records(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_abcd1234.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_otel",
                "data": {"workload": "tasks_v0"},
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_otel",
                "task_id": "t1",
                "data": {
                    "query": "solve task one",
                    "task_inputs": {"task": "solve task one"},
                },
            },
            {
                "event_type": "step.started",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "data": {"max_iterations": 100},
            },
            {
                "event_type": "llm.request",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1:1",
                "data": {
                    "request_index": 1,
                    "model": "fake-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            },
            {
                "event_type": "llm.response",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1:1",
                "data": {
                    "response_text": "hi",
                    "reasoning_text": "reasoning from otel",
                },
                "stats": {
                    "elapsed_ms": 17,
                    "prompt_tokens": 9,
                    "generated_tokens": 3,
                    "total_tokens": 12,
                },
                "summary": {"response_preview": "hi"},
            },
            {
                "event_type": "tool.request",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "tool:1:1",
                "data": {"tool_name": "lookup", "args": ["x"], "kwargs": {"limit": 3}},
            },
            {
                "event_type": "tool.response",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "tool:1:1",
                "data": {"tool_name": "lookup", "result": {"value": 4}},
                "stats": {"elapsed_ms": 8},
            },
            {
                "event_type": "repl.request",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1:1",
                "data": {"code": "print('ok')"},
            },
            {
                "event_type": "repl.final",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1:1",
                "data": {
                    "code": "SUBMIT(answer='ok')",
                    "final_outputs": {"answer": "ok"},
                },
            },
            {
                "event_type": "step.finished",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                    "final_signal": True,
                },
                "stats": {"elapsed_ms": 42},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_otel",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                    "observed": "ok",
                    "finalized": True,
                },
                "stats": {"elapsed_ms": 42},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_otel",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 42},
            },
        ],
    )

    payload = normalize_run(log_path)

    assert payload["run_id"] == "run_otel"
    assert payload["summary"]["status"] == "success"
    assert payload["summary"]["n_tasks"] == 1
    assert payload["summary"]["usage_summary"]["total_tokens"] == 12

    task = payload["tasks"][0]
    assert task["task_id"] == "t1"
    assert task["task"] == "solve task one"
    assert task["observed"] == "ok"
    assert task["finalized"] is True

    step = task["steps"][0]
    assert step["reasoning"] == "reasoning from otel"
    assert step["code"] == "print('ok')"
    assert step["final_outputs"] == {"answer": "ok"}
    assert step["finalized"] is True
    assert step["call_summary"] == {"lm": 1, "tool": 1, "llm_query": 0}

    sections = step["narrative_sections"]
    kinds_by_label = {s["label"]: s["kind"] for s in sections}
    assert kinds_by_label["Task"] == "text"
    assert kinds_by_label["Reasoning"] == "text"
    assert kinds_by_label["Code"] == "text"
    assert kinds_by_label["Final Outputs"] == "final"
    assert kinds_by_label["Calls"] == "call_summary"
    labels = [s["label"] for s in sections]
    assert labels.index("Task") < labels.index("Reasoning") < labels.index("Code")
    assert labels.index("Code") < labels.index("Final Outputs")
    assert payload["all_steps"] == task["steps"]
    assert all(s.get("task") for s in payload["all_steps"])

    lm_call = step["calls"][0]
    assert lm_call["kind"] == "lm"
    assert lm_call["name"] == "fake-model"
    assert lm_call["response_preview"] == "hi"
    assert lm_call["duration_ms"] == 17

    tool_call = step["calls"][1]
    assert tool_call["kind"] == "tool"
    assert tool_call["request"]["args"] == ["x"]
    assert tool_call["response"]["result"] == {"value": 4}


def test_normalize_run_finalizes_extract_fallback_step_without_repl_final(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_fallback.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_fallback",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_fallback",
                "task_id": "t1",
                "data": {
                    "query": "budget task",
                    "task_inputs": {"task": "budget task"},
                },
            },
            {
                "event_type": "step.started",
                "run_id": "run_fallback",
                "task_id": "t1",
                "step_index": 1,
            },
            {
                "event_type": "step.finished",
                "run_id": "run_fallback",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "continue",
                    "stop_reason": None,
                    "parse_success": True,
                    "final_signal": False,
                },
            },
            {
                "event_type": "step.started",
                "run_id": "run_fallback",
                "task_id": "t1",
                "step_index": 2,
                "data": {"extract_fallback": True},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_fallback",
                "task_id": "t1",
                "step_index": 2,
                "call_id": "llm:2:1",
                "data": {"response_text": "answer extracted"},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_fallback",
                "task_id": "t1",
                "step_index": 2,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                    "final_signal": True,
                    "extract_fallback": True,
                    "final_outputs": {"answer": "fallback"},
                },
            },
            {
                "event_type": "task.finished",
                "run_id": "run_fallback",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "fallback"},
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_fallback",
                "data": {"status": "success", "stop_reason": "success"},
            },
        ],
    )

    payload = normalize_run(log_path)
    steps = payload["tasks"][0]["steps"]
    assert [s["step_index"] for s in steps] == [1, 2]
    fallback_step = steps[1]
    assert fallback_step["finalized"] is True
    assert fallback_step["final_outputs"] == {"answer": "fallback"}
    # Projection normalizes emitter's "success" to "final" so viewers
    # (TUI/web) pick the finalized styling; "success" leaks through
    # would render as a neutral step.
    assert fallback_step["status"] == "final"


def test_normalize_run_materializes_live_run_without_finished_rows(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_live1234.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_live",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_live",
                "task_id": "t1",
                "data": {"query": "live task", "task_inputs": {"task": "live task"}},
            },
            {
                "event_type": "step.started",
                "run_id": "run_live",
                "task_id": "t1",
                "step_index": 1,
            },
            {
                "event_type": "llm.request",
                "run_id": "run_live",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1:1",
                "data": {"prompt": "hello"},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_live",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1:1",
                "data": {"response_text": "thinking..."},
                "stats": {"prompt_tokens": 13, "generated_tokens": 4},
                "summary": {"response_preview": "thinking..."},
            },
            {
                "event_type": "repl.request",
                "run_id": "run_live",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1:1",
                "data": {"code": "print('live')"},
            },
            {
                "event_type": "repl.response",
                "run_id": "run_live",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1:1",
                "data": {"code": "print('live')", "stdout": "live output"},
            },
        ],
    )

    payload = normalize_run(log_path)

    assert payload["summary"]["status"] == "running"
    assert payload["summary"]["stop_reason"] == "running"
    assert payload["summary"]["usage_summary"] == {
        "prompt_tokens": 13,
        "generated_tokens": 4,
        "total_tokens": 17,
    }

    task = payload["tasks"][0]
    assert task["task"] == "live task"
    assert task["task_inputs"] == {"task": "live task"}
    assert task["usage_summary"]["total_tokens"] == 17

    step = task["steps"][0]
    assert step["code"] == "print('live')"
    assert step["observed"] == "live output"
    assert step["calls"][0]["response_preview"] == "thinking..."


def test_normalize_run_reclassifies_no_final_with_exec_error(tmp_path: Path) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_error123.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_error",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_error",
                "task_id": "t1",
                "data": {"query": "q"},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_error",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "error",
                    "stop_reason": "empty_code",
                    "parse_success": False,
                    "parse_failure_type": "empty_code",
                },
            },
            {
                "event_type": "task.finished",
                "run_id": "run_error",
                "task_id": "t1",
                "data": {
                    "status": "partial",
                    "stop_reason": "no_final",
                    "exec_error": "[Error] model returned empty code",
                    "finalized": False,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_error",
                "data": {"status": "success", "stop_reason": "no_final"},
            },
        ],
    )

    payload = normalize_run(log_path)
    assert payload["summary"]["status"] == "error"
    assert payload["summary"]["stop_reason"] == "execution_error"


def test_normalize_run_uses_task_evaluation_for_matching_task_only(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_multitask.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_multi",
                "summary": {"n_tasks": 2},
            },
            {
                "event_type": "task.started",
                "run_id": "run_multi",
                "task_id": "t1",
                "data": {"query": "task one", "task_inputs": {"task": "task one"}},
            },
            {
                "event_type": "task.evaluated",
                "run_id": "run_multi",
                "task_id": "t1",
                "data": {"observed": "obs1"},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_multi",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "finalized": True,
                },
            },
            {
                "event_type": "task.started",
                "run_id": "run_multi",
                "task_id": "t2",
                "data": {"query": "task two", "task_inputs": {"task": "task two"}},
            },
            {
                "event_type": "task.evaluated",
                "run_id": "run_multi",
                "task_id": "t2",
                "data": {"observed": "obs2"},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_multi",
                "task_id": "t2",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_multi",
                "data": {"status": "success", "stop_reason": "success"},
            },
        ],
    )

    payload = normalize_run(log_path)

    assert payload["tasks"][0]["task_id"] == "t1"
    assert payload["tasks"][0]["observed"] == "obs1"
    assert payload["tasks"][1]["task_id"] == "t2"
    assert payload["tasks"][1]["observed"] == "obs2"


def test_normalize_run_rejects_non_otel_logs(tmp_path: Path) -> None:
    log_path = tmp_path / "invalid.jsonl"
    log_path.write_text(json.dumps({"type": "metadata"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported log schema"):
        normalize_run(log_path)


def test_normalize_run_rejects_unsupported_otel_schema_version(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "unsupported-version.jsonl"
    [entry] = to_otel_fixture_records(
        [{"event_type": "run.started", "run_id": "run_future"}]
    )
    entry["schema_version"] = 999
    log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported log schema"):
        normalize_run(log_path)


def test_build_run_index_uses_otel_logs(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "rlmbenchy_2026-03-07_12-00-00_index123.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_index",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_index",
                "task_id": "t1",
                "data": {"query": "task body"},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_index",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_index",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 10},
            },
        ],
    )

    runs = build_run_index(log_dir, limit=10)

    assert len(runs) == 1
    assert runs[0]["log_file"] == log_path.name
    assert runs[0]["report_file"] is None
    assert runs[0]["status"] == "success"
    assert runs[0]["n_tasks"] == 1


def test_normalize_run_populates_task_even_without_step_rows(tmp_path: Path) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_taskonly.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_task_only",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_task_only",
                "task_id": "t1",
                "data": {"query": "task body", "task_inputs": {"task": "task body"}},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_task_only",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "observed": "x",
                    "final_outputs": {"answer": "x"},
                    "finalized": True,
                },
                "stats": {"elapsed_ms": 12},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_task_only",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 12},
            },
        ],
    )

    payload = normalize_run(log_path)
    task = payload["tasks"][0]
    assert task["task_id"] == "t1"
    assert task["observed"] == "x"
    assert task["finalized"] is True
    assert len(task["steps"]) == 1
    synthetic = task["steps"][0]
    assert synthetic["step_index"] == 0
    assert synthetic["finalized"] is True
    assert synthetic["final_outputs"] == {"answer": "x"}
    assert synthetic["status"] == "final"
    assert payload["all_steps"] == task["steps"]


# Tests for synthetic task creation and virtual step derivation have been
# removed — current telemetry logs always emit explicit task.started and
# step.* events.
