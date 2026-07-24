"""Empirically characterize the three reasoning-related flags we use in the
``_high`` gpt-oss-20b profile:

- ``reasoning_effort`` — per OpenRouter docs: ``xhigh|high|medium|low|minimal|none``,
  allocating 95/80/50/20/10/0 % of tokens to reasoning respectively. We test
  that observable reasoning channel grows with effort.
- ``reasoning_format`` — a **llama.cpp-server-only** per-request parameter
  (values: ``none|auto|deepseek|deepseek-legacy``) telling that server to
  parse ``<think>…</think>`` blocks into ``message.reasoning_content``. Not
  read by vLLM or SGLang (they use ``--reasoning-parser`` at startup) and
  not documented by OpenRouter or LiteLLM. We test whether setting it on
  OpenRouter changes anything.
- ``include_reasoning`` — per OpenRouter docs: ``true`` ≡ ``reasoning: {}`` and
  ``false`` ≡ ``reasoning: { exclude: true }``. We test whether ``false``
  actually suppresses the reasoning channel.

All tests are ``live_llm``-marked and skip when no OpenRouter key is available.
They run against ``openrouter/openai/gpt-oss-20b`` on a fixed tiling prompt so
results are comparable across runs. Temperature is 1.0 (the OpenAI-recommended
value for gpt-oss), so assertions compare *orders of magnitude* and *presence*,
not exact lengths.
"""

from __future__ import annotations

from typing import Any

import dspy
import pytest

from rlmbenchy.rlm.lm import build_lm
from rlmbenchy.runtime_config import resolve_openrouter_api_key


API_BASE = "https://openrouter.ai/api/v1"
MODEL = "openrouter/openai/gpt-oss-20b"
TILING_PROBLEM = (
    "Count the number of distinct ways to tile a 4x10 rectangle using 1x2 "
    "dominoes (each domino placed horizontally or vertically, every cell "
    "covered exactly once). Output just the integer count."
)


# ---------------------------------------------------------------------------
# Shared helpers
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


def _build_lm(**extra_request_kwargs: Any) -> dspy.LM:
    api_key = resolve_openrouter_api_key() or ""
    return build_lm(
        api_base=API_BASE,
        model=MODEL,
        api_key=api_key,
        request_kwargs={
            "temperature": 1.0,
            "top_p": 1.0,
            **extra_request_kwargs,
        },
    )


def _call(lm: dspy.LM) -> dspy.Prediction:
    with dspy.context(lm=lm):
        return dspy.Predict(_ReasoningCodeSig)(task=TILING_PROBLEM)


def _last_response(lm: dspy.LM) -> Any:
    assert lm.history, "LM history should contain at least one entry after predict()"
    return lm.history[-1].get("response")


def _extract_message(response: Any) -> Any:
    choices = (
        getattr(response, "choices", None)
        if not isinstance(response, dict)
        else response.get("choices")
    )
    if not choices:
        return None
    choice = choices[0]
    return (
        getattr(choice, "message", None)
        if not isinstance(choice, dict)
        else choice.get("message")
    )


def _get_field(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None) if not isinstance(obj, dict) else obj.get(name)
        if value is not None:
            return value
    return None


def _reasoning_channel_len(response: Any) -> int:
    message = _extract_message(response)
    if message is None:
        return 0
    text = _get_field(message, "reasoning", "reasoning_content")
    return len(text) if isinstance(text, str) else 0


def _content_len(response: Any) -> int:
    message = _extract_message(response)
    if message is None:
        return 0
    text = _get_field(message, "content")
    return len(text) if isinstance(text, str) else 0


_SKIP_IF_NO_KEY = pytest.mark.skipif(
    not resolve_openrouter_api_key(),
    reason="OPENROUTER_API_KEY not set (env or project .env)",
)


# ---------------------------------------------------------------------------
# Flag 1 — reasoning_effort: does higher effort produce more reasoning?
# ---------------------------------------------------------------------------


@pytest.mark.live_llm
@_SKIP_IF_NO_KEY
def test_reasoning_effort_scales_channel_length(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lengths: dict[str, int] = {}
    for effort in ("low", "medium", "high"):
        lm = _build_lm(reasoning_effort=effort)
        _call(lm)
        lengths[effort] = _reasoning_channel_len(_last_response(lm))

    with capsys.disabled():
        print("\n=== reasoning_effort -> reasoning channel length (chars) ===")
        for effort, length in lengths.items():
            print(f"  {effort:>6s}: {length}")

    assert lengths["low"] > 0, "expected some reasoning even at low effort"
    assert lengths["high"] > lengths["low"], (
        f"expected reasoning_effort=high to produce strictly more reasoning than "
        f"low. low={lengths['low']}, high={lengths['high']}"
    )


# ---------------------------------------------------------------------------
# Flag 2 — reasoning_format: does setting it change anything on OpenRouter?
# ---------------------------------------------------------------------------


@pytest.mark.live_llm
@_SKIP_IF_NO_KEY
def test_reasoning_format_deepseek_is_a_noop_on_openrouter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """reasoning_format is a Groq-specific parameter (values: parsed|hidden|raw).
    OpenRouter does not document it. We expect setting it on OpenRouter to have
    no effect on where reasoning lands in the response.
    """
    lm_without = _build_lm(reasoning_effort="high")
    lm_with = _build_lm(reasoning_effort="high", reasoning_format="deepseek")
    _call(lm_without)
    _call(lm_with)

    resp_without = _last_response(lm_without)
    resp_with = _last_response(lm_with)

    reasoning_len_without = _reasoning_channel_len(resp_without)
    reasoning_len_with = _reasoning_channel_len(resp_with)
    content_len_without = _content_len(resp_without)
    content_len_with = _content_len(resp_with)

    with capsys.disabled():
        print(
            "\n=== reasoning_format=deepseek vs omitted (with reasoning_effort=high) ==="
        )
        print(
            f"  WITHOUT: reasoning_channel={reasoning_len_without} chars, "
            f"content={content_len_without} chars"
        )
        print(
            f"  WITH   : reasoning_channel={reasoning_len_with} chars, "
            f"content={content_len_with} chars"
        )

    assert reasoning_len_without > 0
    assert reasoning_len_with > 0, (
        "expected reasoning channel to still be populated when reasoning_format "
        "is set — if this fails, the param may actually DO something on OpenRouter"
    )


# ---------------------------------------------------------------------------
# Flag 3 — include_reasoning: does false actually suppress the channel?
# ---------------------------------------------------------------------------


@pytest.mark.live_llm
@_SKIP_IF_NO_KEY
def test_include_reasoning_false_suppresses_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Per OpenRouter docs: include_reasoning=true ≡ reasoning: {},
    include_reasoning=false ≡ reasoning: { exclude: true } (reason internally,
    don't return the trace). With reasoning_effort=high also set, we want to
    see whether the two flags compose as expected.
    """
    lm_true = _build_lm(reasoning_effort="high", include_reasoning=True)
    lm_false = _build_lm(reasoning_effort="high", include_reasoning=False)
    lm_omit = _build_lm(reasoning_effort="high")

    _call(lm_true)
    _call(lm_false)
    _call(lm_omit)

    len_true = _reasoning_channel_len(_last_response(lm_true))
    len_false = _reasoning_channel_len(_last_response(lm_false))
    len_omit = _reasoning_channel_len(_last_response(lm_omit))

    with capsys.disabled():
        print("\n=== include_reasoning variants (reasoning_effort=high) ===")
        print(f"  include_reasoning=true   : reasoning_channel={len_true} chars")
        print(f"  include_reasoning=false  : reasoning_channel={len_false} chars")
        print(f"  include_reasoning omitted: reasoning_channel={len_omit} chars")

    assert len_true > 0, "expected reasoning channel with include_reasoning=true"
    assert len_omit > 0, "expected reasoning channel when flag is omitted"
    assert len_false == 0, (
        f"expected include_reasoning=false to suppress the reasoning channel, "
        f"but got {len_false} chars"
    )
