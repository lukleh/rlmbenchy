from __future__ import annotations

import json
from pathlib import Path

from otel_fixture_support import to_otel_fixture_records
from rlmbenchy.logger.viewer import (
    build_show_payload,
    build_stats_payload,
    build_tree_payload,
    describe_run,
    find_latest_log_file,
    format_show_text,
    resolve_log_file,
)


def test_describe_run_prefers_run_config_name() -> None:
    label = describe_run(
        {
            "run_config_name": "run-xyz",
            "lm_profile_name": "main-profile",
            "model_id": "openrouter/openai/gpt-oss-20b",
            "workload": "tasks_v0",
        }
    )

    assert label == "run-xyz+tasks_v0"


def test_describe_run_falls_back_to_lm_profile_name() -> None:
    label = describe_run(
        {
            "lm_profile_name": "main-profile",
            "model_id": "openrouter/openai/gpt-oss-20b",
            "workload": "tasks_v0",
        }
    )

    assert label == "main-profile+tasks_v0"


def test_describe_run_falls_back_to_model_stem_when_names_missing() -> None:
    label = describe_run(
        {
            "model_id": "openrouter/openai/gpt-oss-20b",
            "workload": "tasks_v0",
        }
    )

    assert label == "gpt-oss-20b+tasks_v0"


def _write_log(path, entries) -> None:
    lines = [
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_log_viewer_stats_and_tree_use_otel_records(tmp_path) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_run1.jsonl"
    _write_log(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_1",
                "data": {
                    "run_config_name": "openrouter_oss20b",
                    "lm_profile_name": "openrouter_oss20b",
                    "workload": "tasks_v0",
                    "model_id": "openai/gpt-oss-20b",
                    "config": {"seed": 7},
                },
            },
            {
                "event_type": "task.started",
                "run_id": "run_1",
                "task_id": "t1",
                "data": {"query": "solve it", "task_inputs": {"query": "solve it"}},
            },
            {
                "event_type": "step.started",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "data": {"max_iterations": 10},
            },
            {
                "event_type": "llm.request",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1",
                "data": {
                    "request_index": 1,
                    "model": "openai/gpt-oss-20b",
                    "messages": [],
                },
            },
            {
                "event_type": "llm.response",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1",
                "data": {
                    "response_text": "SUBMIT(answer=42)",
                    "reasoning_text": "simple math",
                },
                "stats": {
                    "elapsed_ms": 100,
                    "prompt_tokens": 10,
                    "generated_tokens": 5,
                    "total_tokens": 15,
                },
            },
            {
                "event_type": "repl.request",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"code": "SUBMIT(answer=42)"},
            },
            {
                "event_type": "repl.final",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"final_outputs": {"answer": 42}},
                "stats": {"elapsed_ms": 2},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                    "final_signal": True,
                    "parse_strategy": "markdown",
                    "code_block_count": 2,
                    "multiple_code_blocks": True,
                },
                "stats": {"elapsed_ms": 123},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_1",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": 42},
                    "finalized": True,
                },
                "stats": {"elapsed_ms": 123},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_1",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 123},
            },
        ],
    )

    stats = build_stats_payload(log_path)
    assert stats["run_count"] == 1
    assert stats["status_counts"]["PASS"] == 1
    assert stats["total_iterations"] == 1
    assert stats["total_multi_code_block_iterations"] == 1
    assert stats["parse_strategy_counts"] == {"markdown": 1}

    tree = build_tree_payload(log_path, run_id="run_1")
    assert tree["run_count"] == 1
    assert tree["runs"][0]["summary"]["status"] == "PASS"
    assert tree["runs"][0]["steps"][0]["parse_success"] is True
    assert tree["runs"][0]["steps"][0]["multiple_code_blocks"] is True
    assert tree["runs"][0]["steps"][0]["code_block_count"] == 2


def test_log_viewer_resolves_explicit_and_latest_log_paths(tmp_path) -> None:
    log_path = tmp_path / "rlm_current.jsonl"
    _write_log(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_current",
                "data": {
                    "run_config_name": "local_oss20b",
                    "workload": "tasks_v0",
                    "model_id": "m",
                    "config": {"seed": 3},
                },
            },
            {
                "event_type": "step.finished",
                "run_id": "run_current",
                "step_index": 1,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                },
                "stats": {"elapsed_ms": 5},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_current",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                },
                "stats": {"elapsed_ms": 5},
            },
        ],
    )

    assert resolve_log_file(log_file=log_path, log_dir=tmp_path) == log_path
    assert resolve_log_file(log_file=None, log_dir=tmp_path) == log_path

    tree = build_tree_payload(log_path)
    summary = tree["runs"][0]["summary"]
    assert summary["stop_reason"] == "success"
    assert summary["final_outputs"] == {"answer": "ok"}


def test_log_viewer_latest_ignores_non_rlm_jsonl_files(tmp_path: Path) -> None:
    log_path = tmp_path / "rlm_current.jsonl"
    _write_log(log_path, [{"event_type": "run.started", "run_id": "run_current"}])
    note_path = tmp_path / "z_notes.jsonl"
    note_path.write_text('{"not": "an rlmbenchy log"}\n', encoding="utf-8")

    assert find_latest_log_file(tmp_path) == log_path
    assert resolve_log_file(log_file=None, log_dir=tmp_path) == log_path


def test_log_viewer_show_only_failures_and_latest(tmp_path) -> None:
    log_a = tmp_path / "rlm_a.jsonl"
    log_b = tmp_path / "rlm_b.jsonl"
    _write_log(
        log_a,
        [
            {"event_type": "run.started", "run_id": "run_a"},
            {
                "event_type": "task.started",
                "run_id": "run_a",
                "task_id": "t1",
                "data": {"query": "ok"},
            },
            {
                "event_type": "step.started",
                "run_id": "run_a",
                "task_id": "t1",
                "step_index": 1,
                "data": {"max_iterations": 10},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_a",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1",
                "data": {"response_text": "SUBMIT(answer='ok')"},
                "stats": {
                    "elapsed_ms": 10,
                    "prompt_tokens": 5,
                    "generated_tokens": 3,
                    "total_tokens": 8,
                },
            },
            {
                "event_type": "repl.request",
                "run_id": "run_a",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"code": "SUBMIT(answer='ok')"},
            },
            {
                "event_type": "repl.final",
                "run_id": "run_a",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"final_outputs": {"answer": "ok"}},
                "stats": {"elapsed_ms": 1},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_a",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                    "final_signal": True,
                },
                "stats": {"elapsed_ms": 12},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_a",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                    "finalized": True,
                },
                "stats": {"elapsed_ms": 12},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_a",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 12},
            },
        ],
    )
    _write_log(
        log_b,
        [
            {"event_type": "run.started", "run_id": "run_b"},
            {
                "event_type": "task.started",
                "run_id": "run_b",
                "task_id": "t1",
                "data": {"query": "fail"},
            },
            {
                "event_type": "step.started",
                "run_id": "run_b",
                "task_id": "t1",
                "step_index": 1,
                "data": {"max_iterations": 10},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_b",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1",
                "data": {"response_text": "I can't do this"},
                "stats": {
                    "elapsed_ms": 10,
                    "prompt_tokens": 5,
                    "generated_tokens": 3,
                    "total_tokens": 8,
                },
            },
            {
                "event_type": "step.finished",
                "run_id": "run_b",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "error",
                    "stop_reason": "empty_code",
                    "parse_success": False,
                    "final_signal": False,
                },
                "stats": {"elapsed_ms": 11},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_b",
                "task_id": "t1",
                "data": {
                    "status": "error",
                    "stop_reason": "parse_failure",
                    "finalized": False,
                },
                "stats": {"elapsed_ms": 11},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_b",
                "data": {"status": "error", "stop_reason": "parse_failure"},
                "stats": {"elapsed_ms": 11},
            },
        ],
    )
    latest = find_latest_log_file(tmp_path)
    assert latest is not None
    assert latest.name in {"rlm_a.jsonl", "rlm_b.jsonl"}

    payload = build_show_payload(log_b, only_failures=True, limit=10)
    assert payload["row_count"] >= 2
    kinds = {row["type"] for row in payload["rows"]}
    assert "step_finished" in kinds
    assert "run_finished" in kinds


def test_log_viewer_show_uses_step_index(tmp_path) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_run1.jsonl"
    _write_log(
        log_path,
        [
            {"event_type": "run.started", "run_id": "run_1"},
            {
                "event_type": "task.started",
                "run_id": "run_1",
                "task_id": "t1",
                "data": {"query": "step test"},
            },
            {
                "event_type": "step.started",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 3,
                "data": {"max_iterations": 10},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 3,
                "call_id": "llm:1",
                "data": {"response_text": "step code"},
                "stats": {
                    "elapsed_ms": 10,
                    "prompt_tokens": 5,
                    "generated_tokens": 3,
                    "total_tokens": 8,
                },
            },
            {
                "event_type": "repl.request",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 3,
                "call_id": "repl:1",
                "data": {"code": "step"},
            },
            {
                "event_type": "repl.response",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 3,
                "call_id": "repl:1",
                "data": {"output": "ok"},
                "stats": {"elapsed_ms": 1},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_1",
                "task_id": "t1",
                "step_index": 3,
                "data": {
                    "status": "continue",
                    "stop_reason": None,
                    "parse_success": True,
                    "final_signal": False,
                },
                "stats": {"elapsed_ms": 11},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_1",
                "task_id": "t1",
                "data": {
                    "status": "partial",
                    "stop_reason": "no_final",
                    "finalized": False,
                },
                "stats": {"elapsed_ms": 11},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_1",
                "data": {"status": "partial", "stop_reason": "no_final"},
                "stats": {"elapsed_ms": 11},
            },
        ],
    )

    payload = build_show_payload(log_path, limit=10)
    iteration_row = next(
        row for row in payload["rows"] if row["type"] == "step_finished"
    )
    assert iteration_row["iteration"] == 3
    assert "iteration=3" in format_show_text(payload)


def test_log_viewer_show_failure_rows_include_execution_details(tmp_path) -> None:
    log_path = tmp_path / "rlm_2026-03-07_12-00-00_runotel.jsonl"
    _write_log(
        log_path,
        [
            {"event_type": "run.started", "run_id": "run_otel"},
            {
                "event_type": "task.started",
                "run_id": "run_otel",
                "task_id": "t1",
                "data": {"query": "error test"},
            },
            {
                "event_type": "step.started",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "data": {"max_iterations": 10},
            },
            {
                "event_type": "llm.response",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "llm:1",
                "data": {"response_text": "print('a')"},
                "stats": {
                    "elapsed_ms": 10,
                    "prompt_tokens": 5,
                    "generated_tokens": 3,
                    "total_tokens": 8,
                },
            },
            {
                "event_type": "repl.request",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"code": "print('a')"},
            },
            {
                "event_type": "repl.error",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "repl:1",
                "data": {"error": "boom", "error_type": "RuntimeError"},
                "stats": {"elapsed_ms": 5},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_otel",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "error",
                    "stop_reason": "execution_error",
                    "parse_success": False,
                    "final_signal": False,
                },
                "stats": {"elapsed_ms": 111},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_otel",
                "task_id": "t1",
                "data": {
                    "status": "error",
                    "stop_reason": "execution_error",
                    "exec_error": "boom",
                    "finalized": False,
                },
                "stats": {"elapsed_ms": 111},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_otel",
                "data": {"status": "error", "stop_reason": "execution_error"},
                "stats": {"elapsed_ms": 111},
            },
        ],
    )

    payload = build_show_payload(log_path, only_failures=True)
    iteration_row = next(
        row for row in payload["rows"] if row["type"] == "step_finished"
    )
    assert iteration_row["executed_code"] == "print('a')"
    assert iteration_row["execution_error"] == "boom"


def test_log_viewer_resolve_log_file_raises_for_missing_explicit_path(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.jsonl"

    try:
        resolve_log_file(log_file=missing, log_dir=tmp_path)
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
