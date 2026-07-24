"""Telemetry-contract regression: drive LMLoggingCallback end-to-end.

These tests exist because the helper-level tests in
``test_response_extraction_compact.py`` assert what each extractor
returns, but they do not exercise the callsite wiring in
``LMLoggingCallback.on_lm_start`` / ``on_lm_end``. A change that
shuffles the ``data`` / ``stats`` / ``summary`` buckets, changes which
extractor feeds which field, or breaks the outputs-fallback would still
pass the helper suite. This file catches that class of regression by
simulating a full LM call lifecycle and inspecting the emitted telemetry
events.
"""

from __future__ import annotations

from typing import Any

from rlmbenchy.logger.otel import domain_events_from_otel_records
from rlmbenchy.logger.rlm_logger import RLMLogger
from rlmbenchy.rlm.runtime import LMLoggingCallback


class _FakeLM:
    """Minimal DSPy-LM-shaped stand-in for the callback."""

    def __init__(self, model: str, history: list[dict[str, Any]]) -> None:
        self.model = model
        self.kwargs: dict[str, Any] = {}
        self.history = history


def _capture_events(tmp_path) -> tuple[RLMLogger, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    logger = RLMLogger(log_dir=None, on_event=events.append)
    # Callback's _emit path reads task_id from `_task_id`; None is fine.
    del tmp_path
    return logger, events


def _find(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    domain_events = domain_events_from_otel_records(events)
    for entry in domain_events:
        if entry.get("event_type") == event_type:
            return entry
    raise AssertionError(
        f"No {event_type!r} event emitted. Saw: "
        f"{[e.get('event_type') for e in domain_events]}"
    )


def _openai_chat_history_entry() -> dict[str, Any]:
    """A DSPy-history-entry-shaped dict with an OpenAI-style response."""
    return {
        "prompt": "solve: 2+2",
        "response": {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "4"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 13,
                "completion_tokens": 1,
                "total_tokens": 14,
            },
            "cost": 0.00042,
        },
    }


def test_callback_emits_llm_request_with_expected_buckets(tmp_path) -> None:
    logger, events = _capture_events(tmp_path)
    callback = LMLoggingCallback(logger=logger)

    fake_lm = _FakeLM(model="openai/fake", history=[])
    callback.on_lm_start(
        "call_req",
        fake_lm,
        {
            "prompt": None,
            "messages": [{"role": "user", "content": "solve: 2+2"}],
            "kwargs": {"temperature": 0.0},
        },
    )

    request = _find(events, "llm.request")
    data = request["data"]
    stats = request["stats"]
    summary = request["summary"]

    assert data["model"] == "openai/fake"
    assert data["request_index"] == 1
    assert data["messages"] == [{"role": "user", "content": "solve: 2+2"}]
    assert data["request_kwargs"] == {"temperature": 0.0}
    assert data["provider_request"]["model"] == "openai/fake"
    assert data["provider_request"]["messages"] == data["messages"]
    assert stats["prompt_chars"] == len("solve: 2+2")
    assert summary == {}


def test_callback_emits_llm_response_with_telemetry_contract_keys(tmp_path) -> None:
    logger, events = _capture_events(tmp_path)
    callback = LMLoggingCallback(logger=logger)

    fake_lm = _FakeLM(model="openai/fake", history=[])
    callback.on_lm_start(
        "call_1",
        fake_lm,
        {
            "prompt": None,
            "messages": [{"role": "user", "content": "solve: 2+2"}],
            "kwargs": {},
        },
    )

    # Simulate DSPy appending the response to the LM history after the call.
    fake_lm.history.append(_openai_chat_history_entry())

    callback.on_lm_end("call_1", outputs=[{"text": "4"}], exception=None)

    response = _find(events, "llm.response")
    data = response["data"]
    stats = response["stats"]
    summary = response["summary"]

    # data bucket: request index + redacted provider response + preview text
    # + extractor-sourced response_message / reasoning / finish_reason
    assert data["request_index"] == 1
    assert data["response_text"] == "4"
    assert data["response_message"] == {"role": "assistant", "content": "4"}
    assert "reasoning_text" not in data  # OpenAI chat has no reasoning
    assert data["finish_reason"] == "stop"
    assert data["provider_response"]["choices"][0]["message"]["content"] == "4"

    # stats bucket: token usage, elapsed_ms, and cost_usd
    assert stats["prompt_tokens"] == 13
    assert stats["generated_tokens"] == 1
    assert stats["total_tokens"] == 14
    assert stats["cost_usd"] == round(0.00042, 8)
    assert isinstance(stats["elapsed_ms"], int)
    assert stats["elapsed_ms"] >= 0

    # summary bucket: preview + usage rollup
    assert summary["response_preview"] == "4"
    assert summary["usage"] == {
        "prompt_tokens": 13,
        "generated_tokens": 1,
        "total_tokens": 14,
    }


def test_callback_response_preview_falls_back_to_dspy_outputs(tmp_path) -> None:
    """If the response has no extractable text, the preview must fall back
    to the DSPy outputs passed to on_lm_end. This is the ``extract_preview``
    contract at the callsite."""
    logger, events = _capture_events(tmp_path)
    callback = LMLoggingCallback(logger=logger)

    fake_lm = _FakeLM(model="openai/fake", history=[])
    callback.on_lm_start(
        "call_fallback",
        fake_lm,
        {"prompt": None, "messages": [{"role": "user", "content": "hi"}], "kwargs": {}},
    )
    # Response with no choices/output arrays — preview extractor yields "".
    fake_lm.history.append(
        {"response": {"usage": {"prompt_tokens": 5, "completion_tokens": 3}}}
    )

    callback.on_lm_end(
        "call_fallback",
        outputs=[{"text": "from-outputs-fallback"}],
        exception=None,
    )

    response = _find(events, "llm.response")
    assert response["data"]["response_text"] == "from-outputs-fallback"
    assert response["summary"]["response_preview"] == "from-outputs-fallback"


def test_callback_emits_llm_error_on_exception(tmp_path) -> None:
    logger, events = _capture_events(tmp_path)
    callback = LMLoggingCallback(logger=logger)

    fake_lm = _FakeLM(model="openai/fake", history=[])
    callback.on_lm_start(
        "call_err",
        fake_lm,
        {"prompt": None, "messages": [{"role": "user", "content": "x"}], "kwargs": {}},
    )
    callback.on_lm_end("call_err", outputs=None, exception=RuntimeError("boom"))

    error = _find(events, "llm.error")
    assert error["data"]["error_type"] == "RuntimeError"
    assert error["data"]["error_message"] == "boom"
    assert error["data"]["provider_error"] == {
        "type": "RuntimeError",
        "message": "boom",
    }
    assert "elapsed_ms" in error["stats"]


def test_callback_usage_from_history_entry_usage_field(tmp_path) -> None:
    """When the response object has no usage dict, extract_usage must fall
    back to the history entry's top-level ``usage`` field. This regression-
    pins the (response, history_entry) argument order at the callsite."""
    logger, events = _capture_events(tmp_path)
    callback = LMLoggingCallback(logger=logger)

    fake_lm = _FakeLM(model="openai/fake", history=[])
    callback.on_lm_start(
        "call_hist",
        fake_lm,
        {"prompt": None, "messages": [{"role": "user", "content": "x"}], "kwargs": {}},
    )
    # Response has no usage; history entry has usage alongside response.
    fake_lm.history.append(
        {
            "response": {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            },
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        }
    )

    callback.on_lm_end("call_hist", outputs=None, exception=None)

    response = _find(events, "llm.response")
    assert response["stats"]["prompt_tokens"] == 7
    assert response["stats"]["generated_tokens"] == 2
    assert response["stats"]["total_tokens"] == 9
