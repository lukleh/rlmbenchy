from __future__ import annotations

import json
from pathlib import Path

from rlmbenchy.logger.otel import domain_events_from_otel_records
from rlmbenchy.logger.rlm_logger import RLMLogger, _serialize_value


def test_serialize_value_emits_sets_as_sorted_lists() -> None:
    assert _serialize_value(frozenset({"temperature", "top_p", "max_tokens"})) == [
        "max_tokens",
        "temperature",
        "top_p",
    ]
    assert _serialize_value({"a", 3, 1, 2}) == [1, 2, 3, "a"]


def test_serialize_value_handles_nested_frozenset_in_dict() -> None:
    payload = {"lm": {"ignore_unsupported_parameters": frozenset({"reasoning_effort"})}}

    assert _serialize_value(payload) == {
        "lm": {"ignore_unsupported_parameters": ["reasoning_effort"]}
    }


def test_log_metadata_preserves_frozenset_structure_in_written_log(
    tmp_path: Path,
) -> None:
    logger = RLMLogger(log_dir=tmp_path, file_name="test")
    metadata = {
        "config": {
            "lm": {
                "ignore_unsupported_parameters": frozenset({"temperature"}),
            },
        },
    }

    logger.log_metadata(metadata)

    assert logger.log_file_path is not None
    raw = Path(logger.log_file_path).read_text(encoding="utf-8").splitlines()
    entry = json.loads(raw[0])
    assert entry["schema_name"] == "rlmbenchy_otel"
    assert entry["record_type"] == "log"
    assert entry["event_name"] == "rlmbenchy.run.started"
    assert entry["body"]["data"]["config"]["lm"]["ignore_unsupported_parameters"] == [
        "temperature"
    ]

    domain_event = domain_events_from_otel_records([entry])[0]
    assert domain_event["event_type"] == "run.started"
    assert domain_event["data"]["config"]["lm"]["ignore_unsupported_parameters"] == [
        "temperature"
    ]


def test_logger_writes_spans_and_metrics(tmp_path: Path) -> None:
    logger = RLMLogger(log_dir=tmp_path, file_name="test")

    logger.log_metadata(
        {"model_id": "openai/fake", "api_base": "https://api.openai.com"}
    )
    logger.log(
        {
            "event_type": "llm.request",
            "call_id": "call_1",
            "data": {
                "model": "openai/fake",
                "request_kwargs": {"temperature": 0.0},
            },
            "stats": {"prompt_chars": 12},
        }
    )
    logger.log(
        {
            "event_type": "llm.response",
            "call_id": "call_1",
            "data": {"model": "openai/fake", "response_text": "ok"},
            "stats": {
                "elapsed_ms": 25,
                "prompt_tokens": 5,
                "generated_tokens": 2,
                "total_tokens": 7,
                "cost_usd": 0.01,
            },
        }
    )
    logger.log_run_result(
        {"status": "success", "stop_reason": "success", "elapsed_ms": 30}
    )

    assert logger.log_file_path is not None
    records = [
        json.loads(line)
        for line in Path(logger.log_file_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_types = [record["record_type"] for record in records]
    assert "log" in record_types
    assert "span" in record_types
    assert "metric" in record_types

    llm_span = next(
        record for record in records if record.get("name") == "chat openai/fake"
    )
    assert llm_span["span_kind"] == "CLIENT"
    assert llm_span["status"]["code"] == "OK"
    assert llm_span["attributes"]["gen_ai.operation.name"] == "chat"
    assert llm_span["attributes"]["gen_ai.provider.name"] == "openai"
    assert llm_span["attributes"]["gen_ai.usage.input_tokens"] == 5
    assert llm_span["attributes"]["gen_ai.usage.output_tokens"] == 2
