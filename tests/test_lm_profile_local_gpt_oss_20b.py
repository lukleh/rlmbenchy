from __future__ import annotations

import pytest

from rlmbenchy.workbench.config import LMProfile
from tests.lm_profile_checks import (
    assert_profile_identity,
    assert_profile_request,
    load_bundled_profile,
)

PROFILE_FILENAME = "model-local-gpt-oss-20b.toml"


@pytest.fixture
def profile() -> LMProfile:
    return load_bundled_profile(PROFILE_FILENAME)


def test_profile_identity(profile: LMProfile) -> None:
    assert_profile_identity(
        profile,
        api_base="http://127.0.0.1:8001/v1",
        model="gpt-oss-20b",
    )


def test_profile_request_defaults(profile: LMProfile) -> None:
    assert_profile_request(
        profile,
        {
            "temperature": 1.0,
            "top_p": 1.0,
            "max_tokens": 1024,
            "reasoning_format": "deepseek",
        },
    )
