"""Regression tests for the compact LM response extraction API.

These tests pin the observable telemetry-log contract: given a realistic
response payload, each of the six public `extract_*` helpers produces a
stable value. If provider adapters inside `_response_extraction.py` are
reshuffled, these assertions must continue to hold.
"""

from __future__ import annotations

from typing import Any

from rlmbenchy.rlm._response_extraction import (
    extract_cost,
    extract_finish_reason,
    extract_message,
    extract_preview,
    extract_reasoning,
    extract_usage,
)


def _openai_chat_response() -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Final answer: 4.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 8,
            "total_tokens": 50,
        },
        "cost": 0.00123,
    }


def _chatgpt_responses_payload() -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Here is the answer."}],
            }
        ],
        "reasoning": {
            "summary": [{"type": "summary_text", "text": "I verified via SUBMIT."}]
        },
        "usage": {
            "input_tokens": 17,
            "output_tokens": 9,
            "total_tokens": 26,
        },
    }


def _history_entry_with_usage() -> dict[str, Any]:
    return {
        "response": None,
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    }


# ---------------------------------------------------------------------------
# extract_usage
# ---------------------------------------------------------------------------


def test_extract_usage_reads_openai_style_response_first() -> None:
    usage = extract_usage(_openai_chat_response(), history_entry=None)
    assert usage == {
        "prompt_tokens": 42,
        "generated_tokens": 8,
        "total_tokens": 50,
    }


def test_extract_usage_reads_chatgpt_responses_aliases() -> None:
    usage = extract_usage(_chatgpt_responses_payload(), history_entry=None)
    assert usage == {
        "prompt_tokens": 17,
        "generated_tokens": 9,
        "total_tokens": 26,
    }


def test_extract_usage_falls_back_to_history_when_response_missing() -> None:
    usage = extract_usage(None, _history_entry_with_usage())
    assert usage == {
        "prompt_tokens": 5,
        "generated_tokens": 7,
        "total_tokens": 12,
    }


def test_extract_usage_prefers_response_over_history() -> None:
    # Response wins even if history holds different tokens.
    usage = extract_usage(_openai_chat_response(), _history_entry_with_usage())
    assert usage == {
        "prompt_tokens": 42,
        "generated_tokens": 8,
        "total_tokens": 50,
    }


def test_extract_usage_returns_empty_when_nothing_present() -> None:
    assert extract_usage(None, None) == {
        "prompt_tokens": None,
        "generated_tokens": None,
        "total_tokens": None,
    }


# ---------------------------------------------------------------------------
# extract_cost
# ---------------------------------------------------------------------------


def test_extract_cost_reads_top_level_cost_field() -> None:
    assert extract_cost(_openai_chat_response()) == 0.00123


def test_extract_cost_reads_hidden_params() -> None:
    response = {"_hidden_params": {"response_cost": 0.0007}}
    assert extract_cost(response) == 0.0007


def test_extract_cost_returns_none_when_absent() -> None:
    assert extract_cost({"choices": []}) is None


def test_extract_cost_none_for_none_response() -> None:
    assert extract_cost(None) is None


# ---------------------------------------------------------------------------
# extract_finish_reason
# ---------------------------------------------------------------------------


def test_extract_finish_reason_from_choices() -> None:
    assert extract_finish_reason(_openai_chat_response()) == "stop"


def test_extract_finish_reason_from_status() -> None:
    assert extract_finish_reason(_chatgpt_responses_payload()) == "completed"


def test_extract_finish_reason_none_for_none_response() -> None:
    assert extract_finish_reason(None) is None


# ---------------------------------------------------------------------------
# extract_preview
# ---------------------------------------------------------------------------


def test_extract_preview_from_openai_choices() -> None:
    assert extract_preview(_openai_chat_response()) == "Final answer: 4."


def test_extract_preview_from_chatgpt_responses_output() -> None:
    assert extract_preview(_chatgpt_responses_payload()) == "Here is the answer."


def test_extract_preview_falls_back_to_dspy_outputs() -> None:
    preview = extract_preview(None, outputs=[{"text": "fallback content"}])
    assert preview == "fallback content"


def test_extract_preview_empty_when_nothing_available() -> None:
    assert extract_preview(None) == ""


# ---------------------------------------------------------------------------
# extract_reasoning
# ---------------------------------------------------------------------------


def test_extract_reasoning_from_chatgpt_responses_summary() -> None:
    assert extract_reasoning(_chatgpt_responses_payload()) == "I verified via SUBMIT."


def test_extract_reasoning_none_when_absent() -> None:
    assert extract_reasoning(_openai_chat_response()) is None


def test_extract_reasoning_none_for_none_response() -> None:
    assert extract_reasoning(None) is None


# ---------------------------------------------------------------------------
# extract_message
# ---------------------------------------------------------------------------


def test_extract_message_returns_openai_message_dict() -> None:
    message = extract_message(_openai_chat_response())
    assert message == {"role": "assistant", "content": "Final answer: 4."}


def test_extract_message_includes_reasoning_for_chatgpt_responses() -> None:
    message = extract_message(_chatgpt_responses_payload())
    assert message is not None
    assert message["role"] == "assistant"
    assert message["content"] == "Here is the answer."
    assert message.get("reasoning_content") == "I verified via SUBMIT."


def test_extract_message_none_when_no_choices() -> None:
    assert extract_message({"choices": []}) is None


def test_extract_message_none_for_none_response() -> None:
    assert extract_message(None) is None
