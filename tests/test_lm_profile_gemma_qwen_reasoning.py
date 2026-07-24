"""Live characterization of the Gemma 4 and Qwen 3 / 3.5 ``_thinking`` profiles.

All tests are marked ``live_llm`` and skip when ``OPENROUTER_API_KEY`` is not
set (in the environment or the project ``.env``). Each parameterized case loads
a profile, builds its LM, calls ``dspy.Predict`` on a fixed combinatorics prompt,
and asserts that OpenRouter surfaces the provider reasoning channel — driven by
``reasoning = { enabled = true }`` in the profile.

The same tests also serve as a drift guard for the structured reasoning schema
used across these profiles; ``include_reasoning = true`` (legacy) would satisfy
the runtime at OpenRouter today, but these tests pin the canonical
``reasoning = { enabled = true }`` form.
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
from rlmbenchy.workbench.config import load_lm_profile


PROFILES_DIR = BUNDLED_LM_PROFILES_DIR

TILING_PROBLEM = (
    "Count the number of distinct ways to tile a 4x10 rectangle using 1x2 "
    "dominoes (each domino placed horizontally or vertically, every cell "
    "covered exactly once). Output just the integer count."
)


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


def _build_lm_from_profile(profile_filename: str) -> dspy.LM:
    profile = load_lm_profile(PROFILES_DIR / profile_filename)
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


def _reasoning_channel_len(response: Any) -> int:
    """Return total length of reasoning text across OpenRouter's possible
    surfaces: ``message.reasoning`` (OpenRouter-normalized) or
    ``message.reasoning_content`` (llama.cpp-style passthrough)."""
    choices = (
        getattr(response, "choices", None)
        if not isinstance(response, dict)
        else response.get("choices")
    )
    if not choices:
        return 0
    total = 0
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
            if isinstance(value, str):
                total += len(value)
    return total


_SKIP_IF_NO_KEY = pytest.mark.skipif(
    not resolve_openrouter_api_key(),
    reason="OPENROUTER_API_KEY not set (env or project .env)",
)


_THINKING_PROFILES = [
    "model-openrouter-google-gemma-4-31b_thinking.toml",
    "model-openrouter-google-gemma-4-26b-a4b_thinking.toml",
    "model-openrouter-qwen-qwen3-14b.toml",
    "model-openrouter-qwen-qwen3.5-27b_thinking.toml",
    "model-openrouter-qwen-qwen3.5-35b-a3b_thinking.toml",
]


@pytest.mark.live_llm
@_SKIP_IF_NO_KEY
@pytest.mark.parametrize("profile_filename", _THINKING_PROFILES)
def test_openrouter_thinking_profile_surfaces_reasoning_channel(
    profile_filename: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lm = _build_lm_from_profile(profile_filename)

    with dspy.context(lm=lm):
        pred = dspy.Predict(_ReasoningCodeSig)(task=TILING_PROBLEM)

    assert lm.history, "LM history should contain at least one entry after predict()"
    channel_len = _reasoning_channel_len(lm.history[-1].get("response"))

    with capsys.disabled():
        print(f"\n[{profile_filename}] reasoning channel: {channel_len} chars")
        print(f"  pred.reasoning preview: {str(pred.reasoning)[:200]!r}")

    assert channel_len > 0, (
        f"expected {profile_filename} to surface a non-empty reasoning channel "
        f"on OpenRouter via reasoning = {{ enabled = true }}, got 0 chars"
    )
