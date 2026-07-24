"""Generate golden OpenTelemetry log fixtures for contract tests.

Run with: uv run python tests/fixtures/golden/generate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from otel_fixture_support import to_otel_fixture_records

FIXTURES_DIR = Path(__file__).parent


def _write_jsonl(name: str, entries: list[dict]) -> None:
    path = FIXTURES_DIR / f"{name}.jsonl"
    lines = [
        json.dumps(e, ensure_ascii=False) for e in to_otel_fixture_records(entries)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path.name} ({len(lines)} events)")


def _answer_outputs(value: object) -> dict[str, object]:
    return {"answer": value}


# ---------------------------------------------------------------------------
# 1. Normal multi-step run — 3 steps, SUBMIT on step 3
# ---------------------------------------------------------------------------
_write_jsonl(
    "normal_multi_step",
    [
        {
            "event_type": "run.started",
            "run_id": "golden01",
            "data": {
                "runner": "rlm",
                "model_id": "test/model",
                "api_base": "http://localhost",
                "adapter_backend": "chat",
                "request_config": {},
                "loop_config": {"max_iterations": 10},
                "tool_manifest": [],
            },
        },
        {
            "event_type": "task.started",
            "run_id": "golden01",
            "task_id": "task_1",
            "data": {
                "query": "What is 2+2?",
                "context": "",
                "task_inputs": {"query": "What is 2+2?"},
                "expected_answer": "4",
            },
        },
        # Step 1: normal execution
        {
            "event_type": "step.started",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "max_iterations": 10,
                "remaining_iteration_budget": 10,
                "repl_history_before": 0,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "model": "test/model",
                "messages": [{"role": "user", "content": "..."}],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 100},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "provider_response": {},
                "response_text": "print(2+2)",
                "reasoning_text": "I'll compute 2+2",
            },
            "stats": {
                "elapsed_ms": 500,
                "prompt_tokens": 50,
                "generated_tokens": 20,
                "total_tokens": 70,
            },
            "summary": {"response_preview": "print(2+2)"},
        },
        {
            "event_type": "repl.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "repl:1",
            "data": {"code": "print(2+2)"},
        },
        {
            "event_type": "repl.response",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "repl:1",
            "data": {"output": "4"},
            "stats": {"elapsed_ms": 10},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "status": "continue",
                "stop_reason": None,
                "parse_success": True,
                "final_signal": False,
            },
            "stats": {"elapsed_ms": 520},
        },
        # Step 2: another iteration
        {
            "event_type": "step.started",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "data": {
                "max_iterations": 10,
                "remaining_iteration_budget": 9,
                "repl_history_before": 1,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "llm:2",
            "data": {
                "request_index": 2,
                "model": "test/model",
                "messages": [],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 200},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "llm:2",
            "data": {
                "request_index": 2,
                "provider_response": {},
                "response_text": "x = 2 + 2\nprint(x)",
            },
            "stats": {
                "elapsed_ms": 400,
                "prompt_tokens": 80,
                "generated_tokens": 25,
                "total_tokens": 105,
            },
            "summary": {"response_preview": "x = 2 + 2"},
        },
        {
            "event_type": "repl.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "repl:2",
            "data": {"code": "x = 2 + 2\nprint(x)"},
        },
        {
            "event_type": "repl.response",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "repl:2",
            "data": {"output": "4"},
            "stats": {"elapsed_ms": 8},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 2,
            "data": {
                "status": "continue",
                "stop_reason": None,
                "parse_success": True,
                "final_signal": False,
            },
            "stats": {"elapsed_ms": 415},
        },
        # Step 3: SUBMIT
        {
            "event_type": "step.started",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "data": {
                "max_iterations": 10,
                "remaining_iteration_budget": 8,
                "repl_history_before": 2,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "call_id": "llm:3",
            "data": {
                "request_index": 3,
                "model": "test/model",
                "messages": [],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 300},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "call_id": "llm:3",
            "data": {
                "request_index": 3,
                "provider_response": {},
                "response_text": "SUBMIT(answer=4)",
            },
            "stats": {
                "elapsed_ms": 300,
                "prompt_tokens": 100,
                "generated_tokens": 10,
                "total_tokens": 110,
            },
            "summary": {"response_preview": "SUBMIT(answer=4)"},
        },
        {
            "event_type": "repl.request",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "call_id": "repl:3",
            "data": {"code": "SUBMIT(answer=4)"},
        },
        {
            "event_type": "repl.final",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "call_id": "repl:3",
            "data": {"final_outputs": _answer_outputs(4)},
            "stats": {"elapsed_ms": 5},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden01",
            "task_id": "task_1",
            "step_index": 3,
            "data": {
                "status": "success",
                "stop_reason": "final",
                "parse_success": True,
                "final_signal": True,
            },
            "stats": {"elapsed_ms": 310},
        },
        {
            "event_type": "task.finished",
            "run_id": "golden01",
            "task_id": "task_1",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs(4),
                "observed": '4\n{"answer": 4}',
                "exec_error": None,
                "finalized": True,
            },
            "stats": {"elapsed_ms": 1250},
        },
        {
            "event_type": "task.evaluated",
            "run_id": "golden01",
            "task_id": "task_1",
            "data": {
                "expected_answer": "4",
                "correctness": True,
                "observed": '4\n{"answer": 4}',
            },
        },
        {
            "event_type": "run.finished",
            "run_id": "golden01",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs(4),
            },
            "stats": {"elapsed_ms": 1260},
        },
    ],
)


# ---------------------------------------------------------------------------
# 2. Parse failure — step where LLM returns but no executable code
# ---------------------------------------------------------------------------
_write_jsonl(
    "parse_failure",
    [
        {
            "event_type": "run.started",
            "run_id": "golden02",
            "data": {
                "runner": "rlm",
                "model_id": "test/model",
                "api_base": "http://localhost",
                "adapter_backend": "chat",
                "request_config": {},
                "loop_config": {"max_iterations": 3},
                "tool_manifest": [],
            },
        },
        {
            "event_type": "task.started",
            "run_id": "golden02",
            "task_id": "task_1",
            "data": {"query": "Solve X", "task_inputs": {"query": "Solve X"}},
        },
        # Step 1: parse failure (empty code)
        {
            "event_type": "step.started",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "max_iterations": 3,
                "remaining_iteration_budget": 3,
                "repl_history_before": 0,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "model": "test/model",
                "messages": [],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 50},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "provider_response": {},
                "response_text": "I need to think about this...",
            },
            "stats": {
                "elapsed_ms": 600,
                "prompt_tokens": 30,
                "generated_tokens": 15,
                "total_tokens": 45,
            },
            "summary": {"response_preview": "I need to think about this..."},
        },
        # No repl.request — code was empty
        {
            "event_type": "step.finished",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "status": "error",
                "stop_reason": "empty_code",
                "parse_success": False,
                "final_signal": False,
            },
            "stats": {"elapsed_ms": 610},
        },
        # Step 2: succeeds with SUBMIT
        {
            "event_type": "step.started",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "data": {
                "max_iterations": 3,
                "remaining_iteration_budget": 2,
                "repl_history_before": 1,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "llm:2",
            "data": {
                "request_index": 2,
                "model": "test/model",
                "messages": [],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 100},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "llm:2",
            "data": {
                "request_index": 2,
                "provider_response": {},
                "response_text": "SUBMIT(answer='done')",
            },
            "stats": {
                "elapsed_ms": 400,
                "prompt_tokens": 50,
                "generated_tokens": 10,
                "total_tokens": 60,
            },
            "summary": {"response_preview": "SUBMIT(answer='done')"},
        },
        {
            "event_type": "repl.request",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "repl:2",
            "data": {"code": "SUBMIT(answer='done')"},
        },
        {
            "event_type": "repl.final",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "call_id": "repl:2",
            "data": {"final_outputs": _answer_outputs("done")},
            "stats": {"elapsed_ms": 3},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden02",
            "task_id": "task_1",
            "step_index": 2,
            "data": {
                "status": "success",
                "stop_reason": "final",
                "parse_success": True,
                "final_signal": True,
            },
            "stats": {"elapsed_ms": 410},
        },
        {
            "event_type": "task.finished",
            "run_id": "golden02",
            "task_id": "task_1",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs("done"),
                "observed": '{"answer": "done"}',
                "finalized": True,
            },
            "stats": {"elapsed_ms": 1025},
        },
        {
            "event_type": "run.finished",
            "run_id": "golden02",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs("done"),
            },
            "stats": {"elapsed_ms": 1030},
        },
    ],
)


# ---------------------------------------------------------------------------
# 3. LLM error — step where the provider returns an error
# ---------------------------------------------------------------------------
_write_jsonl(
    "llm_error",
    [
        {
            "event_type": "run.started",
            "run_id": "golden03",
            "data": {
                "runner": "rlm",
                "model_id": "test/model",
                "api_base": "http://localhost",
                "adapter_backend": "chat",
                "request_config": {},
                "loop_config": {"max_iterations": 3},
                "tool_manifest": [],
            },
        },
        {
            "event_type": "task.started",
            "run_id": "golden03",
            "task_id": "task_1",
            "data": {"query": "Solve Y", "task_inputs": {"query": "Solve Y"}},
        },
        # Step 1: LLM error
        {
            "event_type": "step.started",
            "run_id": "golden03",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "max_iterations": 3,
                "remaining_iteration_budget": 3,
                "repl_history_before": 0,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden03",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "model": "test/model",
                "messages": [],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 50},
        },
        {
            "event_type": "llm.error",
            "run_id": "golden03",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "error_type": "APIConnectionError",
                "error_message": "Connection refused",
                "provider_error": {
                    "type": "APIConnectionError",
                    "message": "Connection refused",
                },
            },
            "stats": {"elapsed_ms": 100},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden03",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "status": "error",
                "stop_reason": "llm_error",
                "parse_success": False,
                "final_signal": False,
            },
            "stats": {"elapsed_ms": 105},
        },
        {
            "event_type": "task.finished",
            "run_id": "golden03",
            "task_id": "task_1",
            "data": {
                "status": "error",
                "stop_reason": "execution_error",
                "final_outputs": None,
                "observed": "",
                "exec_error": "Connection refused",
                "finalized": False,
            },
            "stats": {"elapsed_ms": 110},
        },
        {
            "event_type": "run.finished",
            "run_id": "golden03",
            "data": {
                "status": "error",
                "stop_reason": "execution_error",
                "final_outputs": None,
            },
            "stats": {"elapsed_ms": 115},
        },
    ],
)


# ---------------------------------------------------------------------------
# 4. Final success — single step reaching SUBMIT immediately
# ---------------------------------------------------------------------------
_write_jsonl(
    "final_success",
    [
        {
            "event_type": "run.started",
            "run_id": "golden04",
            "data": {
                "runner": "rlm",
                "model_id": "test/model",
                "api_base": "http://localhost",
                "adapter_backend": "chat",
                "request_config": {},
                "loop_config": {"max_iterations": 10},
                "tool_manifest": [],
            },
        },
        {
            "event_type": "task.started",
            "run_id": "golden04",
            "task_id": "task_1",
            "data": {
                "query": "What is 1+1?",
                "task_inputs": {"query": "What is 1+1?"},
                "expected_answer": "2",
            },
        },
        # Step 1: immediate SUBMIT
        {
            "event_type": "step.started",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "max_iterations": 10,
                "remaining_iteration_budget": 10,
                "repl_history_before": 0,
            },
        },
        {
            "event_type": "llm.request",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "model": "test/model",
                "messages": [{"role": "user", "content": "What is 1+1?"}],
                "prompt": None,
                "request_kwargs": {},
                "provider_request": {},
            },
            "stats": {"prompt_chars": 80},
        },
        {
            "event_type": "llm.response",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "llm:1",
            "data": {
                "request_index": 1,
                "provider_response": {},
                "response_text": "SUBMIT(answer=2)",
                "reasoning_text": "Simple addition",
            },
            "stats": {
                "elapsed_ms": 200,
                "prompt_tokens": 40,
                "generated_tokens": 8,
                "total_tokens": 48,
            },
            "summary": {"response_preview": "SUBMIT(answer=2)"},
        },
        {
            "event_type": "repl.request",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "repl:1",
            "data": {"code": "SUBMIT(answer=2)"},
        },
        {
            "event_type": "repl.final",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "call_id": "repl:1",
            "data": {"final_outputs": _answer_outputs(2)},
            "stats": {"elapsed_ms": 2},
        },
        {
            "event_type": "step.finished",
            "run_id": "golden04",
            "task_id": "task_1",
            "step_index": 1,
            "data": {
                "status": "success",
                "stop_reason": "final",
                "parse_success": True,
                "final_signal": True,
            },
            "stats": {"elapsed_ms": 210},
        },
        {
            "event_type": "task.finished",
            "run_id": "golden04",
            "task_id": "task_1",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs(2),
                "observed": '{"answer": 2}',
                "exec_error": None,
                "finalized": True,
            },
            "stats": {"elapsed_ms": 215},
        },
        {
            "event_type": "task.evaluated",
            "run_id": "golden04",
            "task_id": "task_1",
            "data": {
                "expected_answer": "2",
                "correctness": True,
                "observed": '{"answer": 2}',
            },
        },
        {
            "event_type": "run.finished",
            "run_id": "golden04",
            "data": {
                "status": "success",
                "stop_reason": "success",
                "final_outputs": _answer_outputs(2),
            },
            "stats": {"elapsed_ms": 220},
        },
    ],
)

print("Golden fixtures generated.")
