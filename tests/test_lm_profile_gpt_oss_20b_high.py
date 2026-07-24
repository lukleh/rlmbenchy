"""Characterize the ``_high`` OpenRouter gpt-oss-20b profile.

Layer A (always runs): parses the TOML profile and pins the intended values
for ``reasoning_effort``, ``include_reasoning``, and ``provider.sort`` so
accidental edits surface as test failures. Also asserts that
``reasoning_format`` is absent — that key is a llama.cpp server-side parsing
directive with no documented effect on OpenRouter.

Layer B (marked ``live_llm``, skipped without an OPENROUTER_API_KEY in either
the environment or the project ``.env``): builds a real ``dspy.LM`` from the
profile, calls ``dspy.Predict`` with a signature whose outputs are
``reasoning: dspy.Reasoning`` and ``code: str`` on a challenging combinatorics
problem, and verifies that OpenRouter surfaces a separate reasoning channel
(driven by ``include_reasoning=true`` + ``reasoning_effort=high``).
"""

from __future__ import annotations

from typing import Any

import dspy
import pytest

from rlmbenchy.rlm.lm import build_lm, resolve_model_api_key
from rlmbenchy.runtime_config import (
    BUNDLED_LM_PROFILES_DIR,
    resolve_openrouter_api_key,
)
from rlmbenchy.workbench.config import LMProfile, load_lm_profile

PROFILE_PATH = BUNDLED_LM_PROFILES_DIR / "model-openrouter-openai-gpt-oss-20b_high.toml"

TILING_PROBLEM = (
    "Count the number of distinct ways to tile a 4x10 rectangle using 1x2 "
    "dominoes (each domino placed horizontally or vertically, every cell "
    "covered exactly once). Output just the integer count."
)


# ---------------------------------------------------------------------------
# Layer A — static profile assertions (no network)
# ---------------------------------------------------------------------------


@pytest.fixture
def profile() -> LMProfile:
    return load_lm_profile(PROFILE_PATH)


def test_profile_identity(profile: LMProfile) -> None:
    assert profile.model == "openrouter/openai/gpt-oss-20b"
    assert profile.api_base == "https://openrouter.ai/api/v1"
    assert profile.request_kwargs["temperature"] == 1.0
    assert profile.request_kwargs["top_p"] == 1.0


def test_profile_enables_high_reasoning_and_price_routing(profile: LMProfile) -> None:
    assert profile.request_kwargs["reasoning_effort"] == "high"
    assert profile.request_kwargs["include_reasoning"] is True
    assert profile.request_kwargs["provider"] == {"sort": "price"}
    assert "reasoning_format" not in profile.request_kwargs, (
        "reasoning_format is a llama.cpp server-only parameter and must not "
        "appear on OpenRouter profiles"
    )
    assert "provider" in profile.ignore_unsupported_parameters


# ---------------------------------------------------------------------------
# Layer B — live LM characterization (opt-in, hits OpenRouter)
# ---------------------------------------------------------------------------


class _ReasoningCodeSig(dspy.Signature):
    """Given a problem, write Python code that solves it and prints the answer."""

    task: str = dspy.InputField(desc="The problem to solve")
    reasoning: dspy.Reasoning = dspy.OutputField()
    code: str = dspy.OutputField(
        desc=(
            "Python code that solves the task. "
            "Use markdown code block format: ```python\\n<code>\\n```"
        )
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
    )


def _last_raw_response(lm: dspy.LM) -> Any:
    assert lm.history, "LM history should contain at least one entry after predict()"
    return lm.history[-1].get("response")


def _provider_reasoning_channel(response: Any) -> str:
    """Concatenate reasoning text surfaced by the provider via
    ``message.reasoning`` / ``message.reasoning_content``. Empty string means
    no separate reasoning channel was returned."""
    choices = (
        getattr(response, "choices", None)
        if not isinstance(response, dict)
        else response.get("choices")
    )
    if not choices:
        return ""
    chunks: list[str] = []
    for choice in choices:
        message = (
            getattr(choice, "message", None)
            if not isinstance(choice, dict)
            else choice.get("message")
        )
        if message is None:
            continue
        for attr in ("reasoning", "reasoning_content"):
            value = (
                getattr(message, attr, None)
                if not isinstance(message, dict)
                else message.get(attr)
            )
            if isinstance(value, str) and value.strip():
                chunks.append(value)
    return "\n".join(chunks)


@pytest.mark.live_llm
@pytest.mark.skipif(
    not resolve_openrouter_api_key(),
    reason="OPENROUTER_API_KEY not set (env or project .env)",
)
def test_high_surfaces_provider_reasoning_channel(
    profile: LMProfile,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lm = _build_lm_from_profile(profile)

    with dspy.context(lm=lm):
        pred = dspy.Predict(_ReasoningCodeSig)(task=TILING_PROBLEM)

    channel = _provider_reasoning_channel(_last_raw_response(lm))

    with capsys.disabled():
        print("\n=== _high — provider reasoning channel (first 400 chars) ===")
        print(repr(channel[:400]))
        print("=== _high — pred.reasoning (first 400 chars) ===")
        print(repr(str(pred.reasoning)[:400]))
        print(f"=== channel length: {len(channel)} chars ===")

    assert channel, (
        "expected _high profile to surface a reasoning channel "
        "(driven by include_reasoning=true + reasoning_effort=high)"
    )
