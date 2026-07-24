"""Local override for DSPy native reasoning policy on the ChatGPT Responses transport.

The ChatGPT subscription Responses transport returns reasoning summaries in a
shape DSPy's native postprocessor cannot populate from reliably, so we keep
the explicit `reasoning` output field in the rendered signature. For every
other transport we defer to DSPy's upstream logic, which now checks
`lm.supports_reasoning`; for DSPy's stock `LM`, that still delegates to
LiteLLM's `supports_reasoning(model)`.

Gotcha before resurrecting a per-model allowlist here: `supports_reasoning`
is backed by `litellm.model_cost`, which LiteLLM builds at import time by
fetching `model_prices_and_context_window.json` from GitHub `main` — not
from the pinned wheel. A model that is "not supported" in the bundled
backup can still return True live, and vice versa, with no LiteLLM version
change. See `rlmbenchy/resources/lm_profiles/README.md` → "LiteLLM supports_reasoning()
— the version pin does not pin the answer" for the full story and the
recommended `LITELLM_LOCAL_MODEL_COST_MAP=True` mitigation.
"""

from __future__ import annotations

from typing import Any

from dspy.adapters.types.reasoning import Reasoning as DspyReasoning

from rlmbenchy.chatgpt_auth import is_chatgpt_api_base

_PATCH_ATTR = "_rlmbenchy_reasoning_allowlist_patch"
_UNPATCHED_ADAPT_TO_NATIVE = DspyReasoning.adapt_to_native_lm_feature


def _uses_chatgpt_responses_transport(lm: Any) -> bool:
    api_base = ""
    kwargs = getattr(lm, "kwargs", None)
    if isinstance(kwargs, dict):
        api_base = str(kwargs.get("api_base") or "").strip()

    model_type = str(getattr(lm, "model_type", "") or "").strip().lower()
    return model_type == "responses" and is_chatgpt_api_base(api_base)


def install_reasoning_native_allowlist_override() -> None:
    """Patch dspy.Reasoning so ChatGPT Responses transport keeps the
    explicit reasoning output field. All other transports run unchanged."""
    current = DspyReasoning.adapt_to_native_lm_feature
    current_func = getattr(current, "__func__", current)
    if getattr(current_func, _PATCH_ATTR, False):
        return

    original = _UNPATCHED_ADAPT_TO_NATIVE

    def _patched_adapt_to_native_lm_feature(
        cls: type[DspyReasoning],
        signature: Any,
        field_name: str,
        lm: Any,
        lm_kwargs: dict[str, Any],
    ) -> Any:
        del cls  # required by the classmethod wrapper below; we don't use it
        if _uses_chatgpt_responses_transport(lm):
            return signature
        return original(signature, field_name, lm, lm_kwargs)

    setattr(_patched_adapt_to_native_lm_feature, _PATCH_ATTR, True)
    setattr(
        DspyReasoning,
        "adapt_to_native_lm_feature",
        classmethod(_patched_adapt_to_native_lm_feature),
    )
