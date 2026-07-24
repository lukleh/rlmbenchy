from __future__ import annotations

import rlmbenchy.rlm._response_extraction as extraction_module


def test_extract_lm_token_usage_reads_openai_style_usage() -> None:
    usage = extraction_module.extract_lm_token_usage(
        {"usage": {"prompt_tokens": 123, "completion_tokens": 45}}
    )
    assert usage == {"prompt_tokens": 123, "generated_tokens": 45, "total_tokens": 168}


def test_extract_lm_token_usage_reads_input_output_aliases() -> None:
    usage = extraction_module.extract_lm_token_usage(
        {"usage": {"input_tokens": "77", "output_tokens": 12.0}}
    )
    assert usage == {"prompt_tokens": 77, "generated_tokens": 12, "total_tokens": 89}


def test_extract_lm_cost_reads_response_object_hidden_params() -> None:
    class _Response:
        def __init__(self) -> None:
            self._hidden_params = {"response_cost": 0.01234567}

        def model_dump(self) -> dict[str, object]:
            return {"usage": {"prompt_tokens": 11, "completion_tokens": 7}}

    assert extraction_module.extract_lm_cost(_Response()) == 0.01234567
