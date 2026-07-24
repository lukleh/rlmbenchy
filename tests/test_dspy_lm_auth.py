from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
from dspy.utils.exceptions import (
    ContextWindowExceededError as DspyContextWindowExceededError,
)
from litellm import ContextWindowExceededError as LitellmContextWindowExceededError

from rlmbenchy.lm_config import validate_supported_parameters_for_openrouter
from rlmbenchy.rlm.lm import ChatGPTResponsesLM, build_lm, resolve_model_api_key
from rlmbenchy.workbench.config import load_lm_profile


def test_load_config_parses_optional_lm_auth_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "chatgpt.toml"
    config_path.write_text(
        """
[lm]
api_base = "https://chatgpt.com/backend-api/codex"
model = "chatgpt/gpt-5.6-terra"
api_key_env = "CHATGPT_TEST_KEY"
""".strip(),
        encoding="utf-8",
    )

    config = load_lm_profile(config_path)

    assert config.api_base == "https://chatgpt.com/backend-api/codex"
    assert config.model == "chatgpt/gpt-5.6-terra"
    assert config.api_key is None
    assert config.api_key_env == "CHATGPT_TEST_KEY"


def test_load_config_preserves_reasoning_effort_without_allowlist(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "chatgpt_custom_effort.toml"
    config_path.write_text(
        """
[lm]
api_base = "https://chatgpt.com/backend-api/codex"
model = "chatgpt/gpt-5.6-terra"

[lm.request]
reasoning = { effort = "future-tier" }
""".strip(),
        encoding="utf-8",
    )

    config = load_lm_profile(config_path)

    assert config.request_kwargs["reasoning"] == {"effort": "future-tier"}


def test_load_config_parses_explicit_lm_transport(tmp_path: Path) -> None:
    config_path = tmp_path / "chatgpt_transport.toml"
    config_path.write_text(
        """
[lm]
api_base = "https://chatgpt.com/backend-api/codex"
model = "chatgpt/gpt-5.6-terra"
transport = "chatgpt_responses"
""".strip(),
        encoding="utf-8",
    )

    config = load_lm_profile(config_path)

    assert config.lm_transport == "chatgpt_responses"


def test_resolve_model_api_key_from_named_env(monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("CHATGPT_TEST_KEY", "test-value")

    resolved = resolve_model_api_key(
        api_base="https://chatgpt.com/backend-api/codex",
        api_key_env="CHATGPT_TEST_KEY",
    )

    assert resolved == "test-value"


def test_resolve_model_api_key_prefers_env_over_explicit_key(monkeypatch) -> None:
    monkeypatch.setenv("CHATGPT_TEST_KEY", "test-value")

    resolved = resolve_model_api_key(
        api_base="https://chatgpt.com/backend-api/codex",
        api_key="config-key",
        api_key_env="CHATGPT_TEST_KEY",
    )

    assert resolved == "test-value"


def test_resolve_model_api_key_defaults_blank_for_non_chatgpt_non_openrouter() -> None:
    resolved = resolve_model_api_key(
        api_base="https://example.com/v1",
    )

    assert resolved == ""


def test_resolve_model_api_key_from_codex_auth(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    auth_file = codex_home / "auth.json"
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": (
                        "eyJhbGciOiJIUzI1NiJ9."
                        "eyJleHAiOjQxMDI0NDQ4MDAsImh0dHBzOi8vYXBpLm9wZW5haS5jb20vYXV0aCI6eyJjaGF0Z3B0X2FjY291bnRfaWQiOiJhY2N0XzEyMyJ9fQ."
                        "signature"
                    ),
                    "refresh_token": "refresh-123",
                    "id_token": "id-token-123",
                    "account_id": "acct_123",
                }
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_model_api_key(
        api_base="https://chatgpt.com/backend-api/codex",
    )

    assert resolved.startswith("eyJhbGciOiJIUzI1NiJ9.")


def test_build_lm_uses_codex_headers_for_chatgpt(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_lm(model: str, **kwargs):  # noqa: ANN003, ANN201
        captured["model"] = model
        captured.update(kwargs)
        return SimpleNamespace(model=model, kwargs=kwargs)

    monkeypatch.setattr("rlmbenchy.rlm.lm.ChatGPTResponsesLM", _fake_lm)
    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.resolve_chatgpt_auth",
        lambda **kwargs: SimpleNamespace(
            access_token="access-123", account_id="acct_123"
        ),
    )

    build_lm(
        api_base="https://chatgpt.com/backend-api/codex",
        model="chatgpt/gpt-5.6-terra",
        api_key="",
        request_kwargs={"temperature": 1.0},
    )

    assert captured["model"] == "openai/gpt-5.6-terra"
    assert captured["model_type"] == "responses"
    assert captured["api_key"] == "access-123"
    assert isinstance(captured["extra_headers"], dict)
    assert captured["extra_headers"]["ChatGPT-Account-Id"] == "acct_123"


def test_build_lm_installs_reasoning_override(monkeypatch) -> None:
    calls = 0

    def _fake_install() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.install_reasoning_native_allowlist_override",
        _fake_install,
    )
    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.ChatGPTResponsesLM",
        lambda model, **kwargs: SimpleNamespace(model=model, kwargs=kwargs),
    )
    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.resolve_chatgpt_auth",
        lambda **kwargs: SimpleNamespace(
            access_token="access-123", account_id="acct_123"
        ),
    )

    _ = build_lm(
        api_base="https://chatgpt.com/backend-api/codex",
        model="chatgpt/gpt-5.6-terra",
        api_key="",
        request_kwargs={},
    )

    assert calls == 1


def test_build_lm_fails_fast_for_official_codex_shape() -> None:
    with pytest.raises(RuntimeError, match="backend-api/codex"):
        build_lm(
            api_base="https://chatgpt.com/backend-api",
            model="chatgpt/gpt-5.6-terra",
            api_key="access-123",
        )


def test_build_lm_rejects_chatgpt_responses_transport_for_non_chatgpt_api_base() -> (
    None
):
    with pytest.raises(ValueError, match="requires a ChatGPT api_base"):
        build_lm(
            api_base="https://openrouter.ai/api/v1",
            model="openrouter/openai/gpt-oss-20b",
            api_key="",
            lm_transport="chatgpt_responses",
        )


def test_validate_supported_parameters_skips_non_openrouter_silently(capsys) -> None:
    validate_supported_parameters_for_openrouter(
        api_base="https://chatgpt.com/backend-api/codex",
        model="chatgpt/gpt-5.6-terra",
        supported_parameter_mode="warn",
        ignore_unsupported_parameters=frozenset(),
        request_params={"temperature": 1.0},
    )

    assert capsys.readouterr().out == ""


def test_validate_supported_parameters_warns_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "rlmbenchy.lm_config.fetch_openrouter_supported_parameters",
        lambda model: {"temperature"},
    )

    validate_supported_parameters_for_openrouter(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        supported_parameter_mode="warn",
        ignore_unsupported_parameters=frozenset(),
        request_params={"definitely_not_supported": 1},
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "validation_warning=unsupported parameters" in captured.err


def test_validate_supported_parameters_error_mode_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rlmbenchy.lm_config.fetch_openrouter_supported_parameters",
        lambda model: {"temperature"},
    )

    with pytest.raises(ValueError, match="unsupported parameters"):
        validate_supported_parameters_for_openrouter(
            api_base="https://openrouter.ai/api/v1",
            model="openrouter/openai/gpt-oss-20b",
            supported_parameter_mode="error",
            ignore_unsupported_parameters=frozenset(),
            request_params={"definitely_not_supported": 1},
        )


def test_chatgpt_responses_lm_suppresses_known_pydantic_usage_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class _FakeStream:
        def __init__(self) -> None:
            self.completed_response = SimpleNamespace(response={"id": "resp_123"})

        def __iter__(self):  # noqa: ANN201
            warnings.warn_explicit(
                (
                    "Pydantic serializer warnings:\n"
                    "PydanticSerializationUnexpectedValue(Expected `ResponseAPIUsage`)"
                ),
                category=UserWarning,
                filename="pydantic/main.py",
                lineno=1,
                module="pydantic.main",
            )
            return iter(())

    def _fake_build_chatgpt_responses_request(**kwargs):  # noqa: ANN003, ANN201
        captured["request_model"] = kwargs["model"]
        return SimpleNamespace(
            input=[{"role": "user", "content": "hi"}],
            instructions=None,
            model=kwargs["model"],
            seed=None,
            reasoning=None,
            text=None,
        )

    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.build_chatgpt_responses_request",
        _fake_build_chatgpt_responses_request,
    )
    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.dspy_lm_module.litellm.responses",
        lambda **kwargs: (
            captured.update(
                litellm_model=kwargs["model"],
                stream=kwargs["stream"],
                api_base=kwargs["api_base"],
            )
            or _FakeStream()
        ),
    )

    lm = ChatGPTResponsesLM(
        "openai/gpt-5.6-terra",
        api_base="https://chatgpt.com/backend-api/codex",
        api_key="access-123",
        cache=False,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = lm.forward(messages=[{"role": "user", "content": "hello"}])

    assert response == {"id": "resp_123"}
    assert captured["request_model"] == "gpt-5.6-terra"
    assert captured["litellm_model"] == "openai/gpt-5.6-terra"
    assert captured["stream"] is True
    assert captured["api_base"] == "https://chatgpt.com/backend-api/codex"
    assert caught == []


def test_chatgpt_responses_lm_maps_context_window_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.build_chatgpt_responses_request",
        lambda **kwargs: SimpleNamespace(
            input=[{"role": "user", "content": "hi"}],
            instructions=None,
            model=kwargs["model"],
            seed=None,
            reasoning=None,
            text=None,
        ),
    )

    def _raise_context_window(**kwargs):  # noqa: ANN003, ANN202
        raise LitellmContextWindowExceededError(
            "too long",
            model=kwargs["model"],
            llm_provider="openai",
        )

    monkeypatch.setattr(
        "rlmbenchy.rlm.lm.dspy_lm_module.litellm.responses",
        _raise_context_window,
    )

    lm = ChatGPTResponsesLM(
        "openai/gpt-5.6-terra",
        api_base="https://chatgpt.com/backend-api/codex",
        api_key="access-123",
        cache=False,
    )

    with pytest.raises(DspyContextWindowExceededError, match="openai/gpt-5.6-terra"):
        lm.forward(messages=[{"role": "user", "content": "hello"}])


def test_chatgpt_responses_lm_processes_and_logs_plain_response_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_response = {
        "id": "resp_123",
        "model": "gpt-5.6-terra",
        "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        "output": [
            {"type": "reasoning", "summary": [{"text": "Think first."}]},
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "lookup",
                "arguments": '{"city": "Brno"}',
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Final answer"}],
            },
        ],
    }

    monkeypatch.setattr(
        ChatGPTResponsesLM,
        "forward",
        lambda self, prompt=None, messages=None, **kwargs: raw_response,
    )

    lm = ChatGPTResponsesLM(
        "openai/gpt-5.6-terra",
        api_base="https://chatgpt.com/backend-api/codex",
        api_key="access-123",
        cache=False,
    )

    outputs = lm("hello")

    assert outputs == [
        {
            "text": "Final answer",
            "tool_calls": [
                {
                    "type": "function_call",
                    "call_id": "call_123",
                    "name": "lookup",
                    "arguments": '{"city": "Brno"}',
                }
            ],
            "reasoning_content": "Think first.",
        }
    ]
    assert lm.history[0]["response"] == raw_response
    assert lm.history[0]["usage"] == {
        "input_tokens": 5,
        "output_tokens": 7,
        "total_tokens": 12,
    }
    assert lm.history[0]["response_model"] == "gpt-5.6-terra"
