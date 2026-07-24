from __future__ import annotations

import pytest

from rlmbenchy.workbench.config import LMProfile
from tests.lm_profile_checks import (
    assert_profile_identity,
    assert_profile_request,
    load_bundled_profile,
)

PROFILE_FILENAME = "model-chatgpt-gpt-5.5_medium.toml"


@pytest.fixture
def profile() -> LMProfile:
    return load_bundled_profile(PROFILE_FILENAME)


def test_profile_identity(profile: LMProfile) -> None:
    assert_profile_identity(
        profile,
        api_base="https://chatgpt.com/backend-api/codex",
        model="chatgpt/gpt-5.5",
        lm_transport="chatgpt_responses",
    )


def test_profile_request_defaults(profile: LMProfile) -> None:
    assert_profile_request(
        profile,
        {"reasoning": {"effort": "medium"}, "temperature": 1.0},
        supported_parameter_mode="off",
    )
