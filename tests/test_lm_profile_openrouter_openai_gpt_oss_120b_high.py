from __future__ import annotations

import pytest

from rlmbenchy.workbench.config import LMProfile
from tests.lm_profile_checks import (
    assert_profile_identity,
    assert_profile_request,
    load_bundled_profile,
)

PROFILE_FILENAME = "model-openrouter-openai-gpt-oss-120b_high.toml"


@pytest.fixture
def profile() -> LMProfile:
    return load_bundled_profile(PROFILE_FILENAME)


def test_profile_identity(profile: LMProfile) -> None:
    assert_profile_identity(
        profile,
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-120b",
    )


def test_profile_request_defaults(profile: LMProfile) -> None:
    assert_profile_request(
        profile,
        {
            "temperature": 1.0,
            "top_p": 1.0,
            "reasoning_effort": "high",
            "include_reasoning": True,
            "provider": {"sort": "price"},
        },
        ignore_unsupported_parameters=("provider",),
    )
