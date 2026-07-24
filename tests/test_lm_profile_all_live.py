"""Generic live smoke coverage for every bundled LM profile.

The provider-specific live tests in this directory characterize reasoning
surfaces and profile defaults. This file covers the broader contract: every
checked-in LM profile should be capable of making one real endpoint call when
its required auth or local server is available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rlmbenchy.workbench.config import load_lm_profile
from tests.lm_profile_checks import (
    PROFILE_PARAMS,
    PROFILE_PATHS,
    assert_profile_parses,
    run_live_profile_smoke,
)


SPECIFIC_PROFILE_TEST_FILES = {
    "model-chatgpt-gpt-5.5_high.toml": "test_lm_profile_chatgpt_gpt_5_5_high.py",
    "model-chatgpt-gpt-5.5_low.toml": "test_lm_profile_chatgpt_gpt_5_5_low.py",
    "model-chatgpt-gpt-5.5_medium.toml": "test_lm_profile_chatgpt_gpt_5_5_medium.py",
    "model-chatgpt-gpt-5.5_xhigh.toml": "test_lm_profile_chatgpt_gpt_5_5_xhigh.py",
    "model-chatgpt-gpt-5.6-luna_high.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-luna_low.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-luna_max.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-luna_medium.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-luna_xhigh.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-sol_high.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-sol_low.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-sol_max.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-sol_medium.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-sol_xhigh.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-terra_high.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-terra_low.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-terra_max.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-terra_medium.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-chatgpt-gpt-5.6-terra_xhigh.toml": "test_lm_profile_chatgpt_gpt_5_6.py",
    "model-local-gpt-oss-20b.toml": "test_lm_profile_local_gpt_oss_20b.py",
    "model-nvidia-google-gemma-3-27b-it.toml": "test_lm_profile_nvidia_google_gemma_3_27b_it.py",
    "model-nvidia-nemotron-3-super-120b-a12b.toml": "test_lm_profile_nvidia_nemotron_3_super_120b_a12b.py",
    "model-openrouter-google-gemma-4-26b-a4b_thinking.toml": "test_lm_profile_openrouter_google_gemma_4_26b_a4b_thinking.py",
    "model-openrouter-google-gemma-4-31b_thinking.toml": "test_lm_profile_openrouter_google_gemma_4_31b_thinking.py",
    "model-openrouter-openai-gpt-oss-120b_high.toml": "test_lm_profile_openrouter_openai_gpt_oss_120b_high.py",
    "model-openrouter-openai-gpt-oss-20b_high.toml": "test_lm_profile_gpt_oss_20b_high.py",
    "model-openrouter-qwen-qwen3-14b.toml": "test_lm_profile_openrouter_qwen_qwen3_14b.py",
    "model-openrouter-qwen-qwen3.5-27b_thinking.toml": "test_lm_profile_openrouter_qwen_qwen3_5_27b_thinking.py",
    "model-openrouter-qwen-qwen3.5-35b-a3b_thinking.toml": "test_lm_profile_openrouter_qwen_qwen3_5_35b_a3b_thinking.py",
}


@pytest.mark.parametrize("profile_path", PROFILE_PARAMS)
def test_bundled_lm_profile_parses(profile_path: Path) -> None:
    profile = load_lm_profile(profile_path)

    assert_profile_parses(profile)


def test_each_bundled_lm_profile_has_specific_test_file() -> None:
    test_dir = Path(__file__).resolve().parent
    profile_names = {profile_path.name for profile_path in PROFILE_PATHS}

    missing_mapping = sorted(profile_names - SPECIFIC_PROFILE_TEST_FILES.keys())
    stale_mapping = sorted(SPECIFIC_PROFILE_TEST_FILES.keys() - profile_names)
    missing_files = sorted(
        test_file
        for test_file in SPECIFIC_PROFILE_TEST_FILES.values()
        if not (test_dir / test_file).exists()
    )

    assert not missing_mapping
    assert not stale_mapping
    assert not missing_files


@pytest.mark.live_llm
@pytest.mark.parametrize("profile_path", PROFILE_PARAMS)
def test_live_bundled_lm_profile_answers(
    profile_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    profile = load_lm_profile(profile_path)

    run_live_profile_smoke(
        profile,
        profile_name=profile_path.name,
        pytest_config=request.config,
    )
