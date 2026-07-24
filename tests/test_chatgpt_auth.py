from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

from rlmbenchy.chatgpt_auth import (
    build_chatgpt_extra_headers,
    resolve_chatgpt_auth,
)


def _access_token(*, expires_at: int, account_id: str = "acct_123") -> str:
    claims = {
        "exp": expires_at,
        "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def _write_codex_auth(
    path: Path,
    *,
    access_token: str,
    refresh_token: str = "refresh-token-that-must-not-be-used",
) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
            }
        ),
        encoding="utf-8",
    )


def test_headers_identify_rlmbenchy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rlmbenchy.chatgpt_auth._distribution_version",
        lambda: "1.2.3",
    )

    headers = build_chatgpt_extra_headers(
        api_base="https://chatgpt.com/backend-api/codex",
        account_id="acct_123",
    )

    assert headers["originator"] == "rlmbenchy"
    assert headers["user-agent"].startswith("rlmbenchy/1.2.3 (")
    assert headers["ChatGPT-Account-Id"] == "acct_123"


def test_missing_file_explains_how_to_create_file_backed_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    auth_file = codex_home / "auth.json"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(RuntimeError) as exc_info:
        resolve_chatgpt_auth(
            api_base="https://chatgpt.com/backend-api/codex",
        )

    message = str(exc_info.value)
    assert "codex login -c cli_auth_credentials_store=file" in message
    assert "keyring" in message
    assert "plaintext" in message
    assert not auth_file.exists()


def test_codex_auth_file_is_read_only_when_token_is_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    auth_file = codex_home / "auth.json"
    token = _access_token(expires_at=int(time.time()) + 3600)
    _write_codex_auth(auth_file, access_token=token)
    original = auth_file.read_bytes()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    auth = resolve_chatgpt_auth(
        api_base="https://chatgpt.com/backend-api/codex",
    )

    assert auth is not None
    assert auth.access_token == token
    assert auth.account_id == "acct_123"
    assert auth_file.read_bytes() == original


def test_expired_codex_token_is_not_refreshed_or_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    auth_file = codex_home / "auth.json"
    _write_codex_auth(
        auth_file,
        access_token=_access_token(expires_at=int(time.time()) - 3600),
    )
    original = auth_file.read_bytes()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(
        RuntimeError,
        match=r"read-only.*cli_auth_credentials_store=file",
    ):
        resolve_chatgpt_auth(
            api_base="https://chatgpt.com/backend-api/codex",
        )

    assert auth_file.read_bytes() == original
