"""Pin LiteLLM to its bundled model-cost map.

LiteLLM otherwise fetches ``model_prices_and_context_window.json`` from
GitHub ``main`` at import time, meaning the value behind
``dspy.LM.supports_reasoning`` can change without any package version bump.
For DSPy's stock LM, that property is backed by LiteLLM's
``supports_reasoning(model)``. Setting
``LITELLM_LOCAL_MODEL_COST_MAP=True`` forces LiteLLM to use the JSON bundled
in the installed wheel, making ``uv.lock`` the single source of truth.

See ``rlmbenchy/resources/lm_profiles/README.md`` → "LiteLLM supports_reasoning() — the
version pin does not pin the answer" for the full story.

This module must be imported **before** any ``import litellm`` or
``import dspy`` in the process, because LiteLLM reads the env variable once
at its own module import time.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


_LOCAL_MODEL_COST_OVERLAY = {
    "gpt-5.5": {
        "cache_read_input_token_cost": 5e-07,
        "cache_read_input_token_cost_above_272k_tokens": 1e-06,
        "input_cost_per_token": 5e-06,
        "input_cost_per_token_above_272k_tokens": 1e-05,
        "litellm_provider": "openai",
        "max_input_tokens": 1050000,
        "max_output_tokens": 128000,
        "max_tokens": 128000,
        "mode": "chat",
        "output_cost_per_token": 3e-05,
        "output_cost_per_token_above_272k_tokens": 4.5e-05,
        "supported_endpoints": [
            "/v1/chat/completions",
            "/v1/batch",
            "/v1/responses",
        ],
        "supported_modalities": ["text", "image"],
        "supported_output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_native_streaming": True,
        "supports_parallel_function_calling": True,
        "supports_pdf_input": True,
        "supports_prompt_caching": True,
        "supports_reasoning": True,
        "supports_response_schema": True,
        "supports_service_tier": True,
        "supports_system_messages": True,
        "supports_tool_choice": True,
        "supports_vision": True,
        "supports_web_search": True,
        "supports_none_reasoning_effort": True,
        "supports_xhigh_reasoning_effort": True,
        "supports_minimal_reasoning_effort": True,
    },
    **{
        model: {
            "litellm_provider": "openai",
            "max_input_tokens": 272000,
            "mode": "chat",
            "supported_endpoints": ["/v1/responses"],
            "supports_native_streaming": True,
            "supports_reasoning": True,
            "supports_xhigh_reasoning_effort": True,
        }
        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    },
}


def register_local_litellm_models() -> None:
    """Register model metadata missing from LiteLLM's pinned local map."""

    litellm_logger = logging.getLogger("LiteLLM")
    previous_logger_disabled = litellm_logger.disabled
    litellm_logger.disabled = True
    try:
        import litellm
    finally:
        litellm_logger.disabled = previous_logger_disabled

    previous_suppress_debug_info = litellm.suppress_debug_info
    litellm.suppress_debug_info = True
    try:
        litellm.register_model(model_cost=_LOCAL_MODEL_COST_OVERLAY)
    finally:
        litellm.suppress_debug_info = previous_suppress_debug_info


register_local_litellm_models()
