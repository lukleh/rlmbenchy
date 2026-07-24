from __future__ import annotations

import json
from pathlib import Path

from otel_fixture_support import to_otel_fixture_records
import rlmbenchy.logger as logger
from rlmbenchy.logger.api import (
    build_run_index,
    find_latest_log_file,
    load_latest_run,
    load_runs,
    run_calls,
    run_final_outputs,
    run_steps,
    run_summary,
    run_task_results,
    summarize_latest_progress,
)


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    )
    path.write_text(payload + "\n", encoding="utf-8")


def test_logger_api_loads_latest_projection_and_progress(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    older_log = log_dir / "rlmbenchy_2026-03-07_12-00-00_old.jsonl"
    older_log.write_text("", encoding="utf-8")

    log_path = log_dir / "rlmbenchy_2026-03-07_12-00-01_new.jsonl"
    _write_jsonl(
        log_path,
        [
            {"event_type": "run.started", "run_id": "run_api"},
            {
                "event_type": "task.started",
                "run_id": "run_api",
                "task_id": "t1",
                "data": {"query": "who mentions Brno?"},
            },
            {
                "event_type": "step.started",
                "run_id": "run_api",
                "task_id": "t1",
                "step_index": 1,
            },
            {
                "event_type": "tool.request",
                "run_id": "run_api",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call-search",
                "data": {"tool_name": "search_catalog"},
            },
            {
                "event_type": "tool.response",
                "run_id": "run_api",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call-search",
                "data": {
                    "tool_name": "search_catalog",
                    "result": {"results": [{"chunkId": "chunk-1"}]},
                },
            },
            {
                "event_type": "subllm.request",
                "run_id": "run_api",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call-sub",
                "data": {"tool_name": "llm_query"},
            },
            {
                "event_type": "subllm.response",
                "run_id": "run_api",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call-sub",
                "data": {"tool_name": "llm_query", "response": "ok"},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_api",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_api",
                "data": {"status": "success", "stop_reason": "success"},
            },
        ],
    )

    assert find_latest_log_file(log_dir) == log_path

    projection = load_latest_run(log_dir)
    assert projection is not None
    assert projection["run_id"] == "run_api"
    assert load_runs(log_dir, limit=1) == [projection]
    assert build_run_index(log_dir, limit=5)[0]["log_file"] == log_path.name

    calls = run_calls(projection)
    assert [call["kind"] for call in calls] == ["tool", "llm_query"]
    assert calls[0]["name"] == "search_catalog"
    assert calls[0]["response"]["result"] == {"results": [{"chunkId": "chunk-1"}]}
    assert len(run_steps(projection)) == 1
    assert run_final_outputs(projection) == {"answer": "ok"}
    assert run_summary(projection)["finalOutputs"] == {"answer": "ok"}
    assert run_task_results(projection) == [
        {
            "taskId": "t1",
            "task": "who mentions Brno?",
            "taskInputs": {},
            "status": "success",
            "stopReason": "success",
            "finalized": True,
            "finalOutputs": {"answer": "ok"},
            "observed": "",
            "execError": "",
            "parseSuccess": True,
            "latencyMs": 0,
            "iterations": 1,
            "usageSummary": {
                "prompt_tokens": 0,
                "generated_tokens": 0,
                "total_tokens": 0,
            },
            "activitySummary": {
                "event_count": 7,
                "last_event": "task.finished",
                "iteration_count": 1,
                "llm_calls": 0,
                "llm_errors": 0,
                "model_steps": 1,
                "repl_calls": 0,
                "repl_errors": 0,
                "tool_calls": 1,
                "tool_call_errors": 0,
                "subllm_calls": 1,
                "subllm_errors": 0,
                "final_signals": 0,
                "event_counts": {
                    "step.started": 1,
                    "subllm.request": 1,
                    "subllm.response": 1,
                    "task.finished": 1,
                    "task.started": 1,
                    "tool.request": 1,
                    "tool.response": 1,
                },
            },
        }
    ]

    assert summarize_latest_progress(log_dir) == {
        "runId": "run_api",
        "logFile": log_path.name,
        "logPath": str(log_path),
        "status": "success",
        "stopReason": "success",
        "lastEvent": "task.finished",
        "lastEventAt": "2026-03-07T12:00:07+00:00",
        "eventCount": 7,
        "elapsedMs": 0,
        "steps": 1,
        "toolCalls": 1,
        "subLlmCalls": 1,
        "llmCalls": 0,
        "toolErrors": 0,
        "subLlmErrors": 0,
        "llmErrors": 0,
    }


def test_logger_api_returns_none_without_logs(tmp_path: Path) -> None:
    assert find_latest_log_file(tmp_path / "missing") is None
    assert load_latest_run(tmp_path / "missing") is None
    assert summarize_latest_progress(tmp_path / "missing") is None


def test_logger_api_ignores_non_rlm_jsonl_files(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "notes.jsonl").write_text(
        '{"not": "an rlmbenchy log"}\n',
        encoding="utf-8",
    )

    assert find_latest_log_file(log_dir) is None


def test_logger_package_root_reexports_stable_api(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "rlmbenchy_2026-03-07_12-00-00_root.jsonl"
    _write_jsonl(
        log_path,
        [
            {"event_type": "run.started", "run_id": "run_root"},
            {
                "event_type": "run.finished",
                "run_id": "run_root",
                "data": {"status": "success", "stop_reason": "success"},
            },
        ],
    )

    projection = logger.load_run(log_path)

    assert logger.find_log_files(log_dir) == [log_path]
    assert logger.find_latest_log_file(log_dir) == log_path
    assert logger.run_summary(projection)["runId"] == "run_root"
