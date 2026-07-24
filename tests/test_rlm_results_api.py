from __future__ import annotations

from types import SimpleNamespace

from rlmbenchy.rlm.results import (
    extract_final_answer,
    is_retryable_tool_error,
    loop_result_summary,
)


def test_results_api_extracts_final_answer_from_task_run_or_loop_result() -> None:
    task_run = SimpleNamespace(
        final_outputs=None,
        loop_result=SimpleNamespace(final_outputs={"answer": "final text"}),
    )

    assert extract_final_answer(task_run) == "final text"


def test_results_api_accepts_mapping_runtime_shapes() -> None:
    task_run = {
        "finalOutputs": None,
        "loopResult": {
            "final_outputs": {"answer": "mapped final"},
            "stopReason": "success",
            "iterations": 3,
            "error": "",
        },
    }

    assert extract_final_answer(task_run) == "mapped final"
    assert loop_result_summary(task_run["loopResult"]) == {
        "stopReason": "success",
        "iterations": 3,
        "error": None,
    }


def test_results_api_summarizes_loop_result_without_metadata() -> None:
    loop_result = SimpleNamespace(
        stop_reason="success",
        iterations=2,
        error=None,
        metadata={"events": []},
    )

    assert loop_result_summary(loop_result) == {
        "stopReason": "success",
        "iterations": 2,
        "error": None,
    }


def test_results_api_classifies_retryable_tool_error_metadata() -> None:
    loop_result = SimpleNamespace(
        metadata=SimpleNamespace(
            events=[
                {
                    "event_type": "tool.error",
                    "data": {
                        "error_message": "Internal request timed out. HTTP 504",
                        "status_code": 504,
                    },
                }
            ]
        )
    )

    assert is_retryable_tool_error(loop_result) is True
