"""Pin the bundled NVIDIA Gemma 3 27B IT profile and smoke-test it live.

Layer A (always runs): parse the TOML profile and pin the intended endpoint,
model, auth env var, and request defaults.

Layer B (marked ``live_llm``): build a real ``dspy.LM`` from the profile,
send a tiny prompt to the NVIDIA-hosted NIM endpoint, and verify that the
response contains the expected answer.
"""

from __future__ import annotations

import dspy
import pytest

from rlmbenchy.rlm.lm import build_lm, resolve_model_api_key
from rlmbenchy.runtime_config import BUNDLED_LM_PROFILES_DIR, resolve_secret_for_env
from rlmbenchy.workbench.config import LMProfile, load_lm_profile
from tests.lm_profile_checks import (
    LIVE_CALL_CLIENT_TIMEOUT_S,
    LIVE_CALL_HARD_TIMEOUT_S,
    live_call_deadline,
)


PROFILE_PATH = BUNDLED_LM_PROFILES_DIR / "model-nvidia-google-gemma-3-27b-it.toml"


@pytest.fixture
def profile() -> LMProfile:
    return load_lm_profile(PROFILE_PATH)


def test_profile_identity(profile: LMProfile) -> None:
    assert profile.api_base == "https://integrate.api.nvidia.com/v1"
    assert profile.model == "google/gemma-3-27b-it"
    assert profile.api_key_env == "NVIDIA_API_KEY"


def test_profile_request_defaults(profile: LMProfile) -> None:
    assert profile.request_kwargs["temperature"] == 1.0
    assert profile.request_kwargs["top_p"] == 0.95
    assert profile.request_kwargs["top_k"] == 64
    assert "chat_template_kwargs" not in profile.request_kwargs


class _AnswerSig(dspy.Signature):
    """Reply with a short, exact answer."""

    question: str = dspy.InputField()
    answer: str = dspy.OutputField(
        desc="Reply with exactly the requested short answer."
    )


def _build_lm_from_profile(profile: LMProfile) -> dspy.LM:
    api_key = resolve_model_api_key(
        api_base=profile.api_base,
        api_key=profile.api_key,
        api_key_env=profile.api_key_env,
    )
    return build_lm(
        api_base=profile.api_base,
        model=profile.model,
        api_key=api_key,
        request_kwargs=profile.request_kwargs,
        lm_transport=profile.lm_transport,
        timeout=LIVE_CALL_CLIENT_TIMEOUT_S,
        num_retries=0,
    )


@pytest.mark.live_llm
@pytest.mark.skipif(
    not resolve_secret_for_env("NVIDIA_API_KEY"),
    reason="NVIDIA_API_KEY not set (env or project .env)",
)
def test_live_profile_smoke_surfaces_answer(
    profile: LMProfile,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lm = _build_lm_from_profile(profile)
    question = "Reply with exactly: 4"

    with capsys.disabled():
        print(f"\n[live_llm] profile: {PROFILE_PATH.name}")
        print(f"[live_llm] endpoint: {profile.api_base}")
        print(f"[live_llm] model: {profile.model}")
        print(f"[live_llm] request: {profile.request_kwargs!r}")
        print(f"[live_llm] input: {question!r}")
        print(
            "[live_llm] calling endpoint: "
            f"client_timeout={LIVE_CALL_CLIENT_TIMEOUT_S}s "
            f"hard_timeout={LIVE_CALL_HARD_TIMEOUT_S}s retries=0"
        )

    try:
        with live_call_deadline(
            LIVE_CALL_HARD_TIMEOUT_S,
            f"live NVIDIA Gemma profile smoke timed out after {LIVE_CALL_HARD_TIMEOUT_S}s",
        ):
            with dspy.context(lm=lm):
                pred = dspy.Predict(_AnswerSig)(
                    question=question,
                )
    except TimeoutError as exc:
        with capsys.disabled():
            print(f"[live_llm] fail: {exc}")
        pytest.fail(str(exc))

    with capsys.disabled():
        print(f"[live_llm] output: {str(pred.answer).strip()!r}")

    assert str(pred.answer).strip().startswith("4")
