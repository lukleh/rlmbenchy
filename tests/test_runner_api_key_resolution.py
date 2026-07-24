from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlmbenchy.rlm.lm import resolve_model_api_key as _resolve_api_key


def test_resolve_api_key_uses_config_value_without_secret_source() -> None:
    assert (
        _resolve_api_key(
            api_base="https://example.com/v1",
            api_key="explicit-key",
        )
        == "explicit-key"
    )


def test_resolve_api_key_from_named_env(monkeypatch) -> None:
    monkeypatch.setenv("MY_TEST_KEY", "abc123")
    assert (
        _resolve_api_key(
            api_base="https://example.com/v1",
            api_key_env="MY_TEST_KEY",
        )
        == "abc123"
    )


def test_resolve_api_key_missing_named_env_raises(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_ENV_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _resolve_api_key(
            api_base="https://example.com/v1",
            api_key_env="MISSING_ENV_KEY",
        )


def test_resolve_api_key_openrouter_default_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert _resolve_api_key(api_base="https://openrouter.ai/api/v1") == "or-key"


def test_resolve_api_key_prefers_env_over_config_value(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert (
        _resolve_api_key(
            api_base="https://openrouter.ai/api/v1",
            api_key="config-key",
        )
        == "or-key"
    )


def test_resolve_api_key_openrouter_from_secrets_file(
    monkeypatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    secrets_file = config_dir / "secrets.toml"
    secrets_file.parent.mkdir(parents=True, exist_ok=True)
    secrets_file.write_text(
        '[providers.openrouter]\napi_key = "secret-or-key"\n',
        encoding="utf-8",
    )
    assert _resolve_api_key(api_base="https://openrouter.ai/api/v1") == "secret-or-key"


def test_resolve_api_key_local_endpoint_none() -> None:
    assert _resolve_api_key(api_base="http://127.0.0.1:8001/v1") == ""


def test_resolve_api_key_from_codex_auth(monkeypatch, tmp_path: Path) -> None:
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
    assert _resolve_api_key(
        api_base="https://chatgpt.com/backend-api/codex",
    ).startswith("eyJhbGciOiJIUzI1NiJ9.")
