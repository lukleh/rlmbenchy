from __future__ import annotations

import pytest

from tests.lm_profile_checks import (
    assert_profile_identity,
    assert_profile_request,
    load_bundled_profile,
)

MODEL_VARIANTS = ("sol", "terra", "luna")
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
PROFILE_CASES = [
    pytest.param(model_variant, effort, id=f"{model_variant}-{effort}")
    for model_variant in MODEL_VARIANTS
    for effort in REASONING_EFFORTS
]


@pytest.mark.parametrize(("model_variant", "effort"), PROFILE_CASES)
def test_profile(model_variant: str, effort: str) -> None:
    model = f"gpt-5.6-{model_variant}"
    profile = load_bundled_profile(f"model-chatgpt-{model}_{effort}.toml")

    assert_profile_identity(
        profile,
        api_base="https://chatgpt.com/backend-api/codex",
        model=f"chatgpt/{model}",
        lm_transport="chatgpt_responses",
    )
    assert_profile_request(
        profile,
        {"reasoning": {"effort": effort}, "temperature": 1.0},
        supported_parameter_mode="off",
    )
