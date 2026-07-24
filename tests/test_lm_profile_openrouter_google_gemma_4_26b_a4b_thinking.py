from __future__ import annotations

import pytest

from rlmbenchy.workbench.config import LMProfile
from tests.lm_profile_checks import (
    assert_profile_identity,
    assert_profile_request,
    load_bundled_profile,
)


PROFILE_FILENAME = "model-openrouter-google-gemma-4-26b-a4b_thinking.toml"


@pytest.fixture
def profile() -> LMProfile:
    return load_bundled_profile(PROFILE_FILENAME)


def test_profile_identity(profile: LMProfile) -> None:
    assert_profile_identity(
        profile,
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/google/gemma-4-26b-a4b-it",
    )


def test_profile_request_defaults(profile: LMProfile) -> None:
    assert_profile_request(
        profile,
        {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 65,
            "reasoning": {"enabled": True},
            "provider": {"sort": "price"},
        },
        ignore_unsupported_parameters=("provider",),
    )
