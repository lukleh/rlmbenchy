"""Shared helpers for bundled LM profile tests."""

from __future__ import annotations

import contextlib
import signal
import socket
import sys
import threading
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pytest

from rlmbenchy.chatgpt_auth import is_chatgpt_api_base, resolve_chatgpt_auth
from rlmbenchy.rlm.lm import build_lm
from rlmbenchy.runtime_config import (
    BUNDLED_LM_PROFILES_DIR,
    load_project_env,
    resolve_openrouter_api_key,
    resolve_secret_for_env,
)
from rlmbenchy.workbench.config import LMProfile, load_lm_profile


PROFILE_PATHS = tuple(sorted(BUNDLED_LM_PROFILES_DIR.glob("*.toml")))
PROFILE_PARAMS = [pytest.param(path, id=path.stem) for path in PROFILE_PATHS]
SMOKE_PROMPT = "Reply with exactly this text and no extra words: rlmbenchy-ok"
MAX_PREVIEW_CHARS = 800
LIVE_CALL_CLIENT_TIMEOUT_S = 20
LIVE_CALL_HARD_TIMEOUT_S = 45
LIVE_CALL_MAX_TOKENS = 128


def load_bundled_profile(filename: str) -> LMProfile:
    return load_lm_profile(BUNDLED_LM_PROFILES_DIR / filename)


def assert_profile_identity(
    profile: LMProfile,
    *,
    api_base: str,
    model: str,
    api_key_env: str | None = None,
    lm_transport: str = "auto",
) -> None:
    assert profile.api_base == api_base
    assert profile.model == model
    assert profile.api_key_env == api_key_env
    assert profile.lm_transport == lm_transport


def assert_profile_request(
    profile: LMProfile,
    expected_request: dict[str, Any],
    *,
    supported_parameter_mode: str = "warn",
    ignore_unsupported_parameters: tuple[str, ...] = (),
) -> None:
    assert profile.request_kwargs == expected_request
    assert profile.supported_parameter_mode == supported_parameter_mode
    assert profile.ignore_unsupported_parameters == frozenset(
        ignore_unsupported_parameters
    )


def assert_profile_parses(profile: LMProfile) -> None:
    assert profile.api_base
    assert profile.model


def _is_loopback_endpoint(api_base: str) -> bool:
    parsed = urlparse(api_base)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _skip_if_loopback_endpoint_is_unavailable(
    api_base: str,
    *,
    pytest_config: pytest.Config | None = None,
) -> None:
    parsed = urlparse(api_base)
    host = parsed.hostname
    if not host:
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return
    except OSError as exc:
        _emit_live_line(
            pytest_config,
            f"[live_llm] skip: local LM endpoint {api_base!r} is not reachable: {exc}",
        )
        pytest.skip(f"local LM endpoint {api_base!r} is not reachable: {exc}")


def _emit_live_line(config: pytest.Config | None, message: str) -> None:
    capture_manager = (
        config.pluginmanager.get_plugin("capturemanager")
        if config is not None
        else None
    )
    if capture_manager is None:
        sys.__stdout__.write(f"{message}\n")
        sys.__stdout__.flush()
        return

    capture_manager.suspend_global_capture(in_=False)
    try:
        sys.__stdout__.write(f"{message}\n")
        sys.__stdout__.flush()
    finally:
        capture_manager.resume_global_capture()


def _preview_text(value: str, *, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars]}..."


def _resolve_api_key_or_skip(
    profile: LMProfile,
    *,
    pytest_config: pytest.Config | None = None,
) -> str:
    load_project_env()

    explicit_key = str(profile.api_key or "").strip()
    if profile.api_key_env:
        api_key = resolve_secret_for_env(profile.api_key_env, explicit=profile.api_key)
        if api_key:
            return api_key
        message = (
            f"Missing model API key in environment variable {profile.api_key_env!r}."
        )
        _emit_live_line(pytest_config, f"[live_llm] skip: {message}")
        pytest.skip(message)

    if "openrouter.ai" in profile.api_base.lower():
        api_key = resolve_openrouter_api_key(profile.api_key)
        if api_key:
            return api_key
        _emit_live_line(
            pytest_config,
            "[live_llm] skip: OPENROUTER_API_KEY not set (env or project .env)",
        )
        pytest.skip("OPENROUTER_API_KEY not set (env or project .env)")

    if explicit_key:
        return explicit_key

    if is_chatgpt_api_base(profile.api_base):
        try:
            return resolve_chatgpt_auth(
                api_base=profile.api_base,
                api_key=profile.api_key,
            ).access_token
        except RuntimeError as exc:
            _emit_live_line(pytest_config, f"[live_llm] skip: {exc}")
            pytest.skip(str(exc))

    return ""


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        chunks: list[str] = []
        for key in ("text", "content", "answer", "reasoning", "reasoning_content"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                chunks.append(nested)
        return "\n".join(chunks)
    if isinstance(value, list):
        return "\n".join(_extract_text(item) for item in value)
    return str(value or "")


@contextlib.contextmanager
def live_call_deadline(seconds: int, message: str) -> Iterator[None]:
    can_use_alarm = (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, "SIGALRM")
        and hasattr(signal, "setitimer")
    )
    if not can_use_alarm:
        yield
        return

    def _raise_timeout(signum: int, frame: Any) -> None:
        del signum, frame
        raise TimeoutError(message)

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_live_profile_smoke(
    profile: LMProfile,
    *,
    profile_name: str | None = None,
    pytest_config: pytest.Config | None = None,
) -> None:
    display_name = profile_name or profile.model
    _emit_live_line(pytest_config, f"[live_llm] profile: {display_name}")
    _emit_live_line(pytest_config, f"[live_llm] endpoint: {profile.api_base}")
    _emit_live_line(pytest_config, f"[live_llm] model: {profile.model}")
    _emit_live_line(pytest_config, f"[live_llm] request: {profile.request_kwargs!r}")
    _emit_live_line(pytest_config, f"[live_llm] input: {SMOKE_PROMPT!r}")

    if _is_loopback_endpoint(profile.api_base):
        _skip_if_loopback_endpoint_is_unavailable(
            profile.api_base,
            pytest_config=pytest_config,
        )

    api_key = _resolve_api_key_or_skip(profile, pytest_config=pytest_config)

    lm = build_lm(
        api_base=profile.api_base,
        model=profile.model,
        api_key=api_key,
        request_kwargs=profile.request_kwargs,
        lm_transport=profile.lm_transport,
        timeout=LIVE_CALL_CLIENT_TIMEOUT_S,
        num_retries=0,
    )

    _emit_live_line(
        pytest_config,
        "[live_llm] calling endpoint: "
        f"client_timeout={LIVE_CALL_CLIENT_TIMEOUT_S}s "
        f"hard_timeout={LIVE_CALL_HARD_TIMEOUT_S}s "
        f"max_tokens={LIVE_CALL_MAX_TOKENS} retries=0",
    )
    try:
        with live_call_deadline(
            LIVE_CALL_HARD_TIMEOUT_S,
            f"live LM profile smoke timed out after {LIVE_CALL_HARD_TIMEOUT_S}s",
        ):
            outputs = lm(
                messages=[{"role": "user", "content": SMOKE_PROMPT}],
                max_tokens=LIVE_CALL_MAX_TOKENS,
            )
    except TimeoutError as exc:
        _emit_live_line(pytest_config, f"[live_llm] fail: {exc}")
        pytest.fail(str(exc))
    except Exception as exc:
        _emit_live_line(
            pytest_config,
            f"[live_llm] fail: {type(exc).__name__}: {exc}",
        )
        raise

    rendered = _extract_text(outputs).strip()

    _emit_live_line(
        pytest_config,
        f"[live_llm] output: {_preview_text(rendered)!r}",
    )

    assert "rlmbenchy-ok" in rendered.lower()
