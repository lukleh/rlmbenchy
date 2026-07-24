"""Pin the LiteLLM model-cost map behavior the rest of the codebase depends on.

Together with ``rlmbenchy/_litellm_bootstrap.py`` and the repo-root
``conftest.py``, this guards against silent drift in
``supports_reasoning(model)`` — see ``rlmbenchy/resources/lm_profiles/README.md`` for the
full rationale. If any of these assertions regresses after a ``litellm``
bump, either the bundled ``model_prices_and_context_window_backup.json``
stopped listing a model we rely on, or ``LITELLM_LOCAL_MODEL_COST_MAP`` is
no longer set early enough in the import chain.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


def test_litellm_local_model_cost_map_is_enabled() -> None:
    """The bootstrap sets this env var before LiteLLM is imported. If it is
    unset here, either the bootstrap regressed or something imported LiteLLM
    before the bootstrap ran."""
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP", "").lower() == "true"


def test_rlmbenchy_import_suppresses_optional_litellm_provider_warnings() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import rlmbenchy; print('ok')"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "ok"
    assert "could not pre-load" not in result.stderr


@pytest.mark.parametrize(
    "model",
    ["gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
)
def test_new_chatgpt_models_are_registered_in_local_model_map(model: str) -> None:
    """The bootstrap overlays ChatGPT models absent from pinned LiteLLM data."""
    import litellm
    from litellm.utils import supports_native_streaming, supports_reasoning

    assert model in litellm.model_cost
    assert litellm.model_cost[model]["litellm_provider"] == "openai"
    assert supports_native_streaming(model, None) is True
    assert supports_reasoning(model, None) is True


@pytest.mark.parametrize(
    "model",
    [
        "openrouter/openai/gpt-oss-20b",
        "openrouter/openai/gpt-oss-120b",
        "openrouter/qwen/qwen3.5-27b",
        "openrouter/qwen/qwen3.5-35b-a3b",
        "gpt-5.5",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    ],
)
def test_supports_reasoning_true_for_local_model_map(model: str) -> None:
    """These models must report ``supports_reasoning=True`` from the pinned
    local map plus bootstrap overlays. If this breaks after a ``litellm`` bump the
    bundled JSON likely dropped or relabeled the entry; re-pin ``litellm``
    to a version that still lists the model, or register it explicitly via
    ``litellm.register_model(...)``.

    Without this guarantee, the local reasoning allowlist removed in commit
    ``d48ebe9`` ("Drop reasoning allowlist: migrate profiles to
    reasoning_effort") would need to come back.
    """
    from litellm import supports_reasoning

    assert supports_reasoning(model) is True, (
        f"{model} missing/supports_reasoning!=true in litellm's bundled model map."
    )
