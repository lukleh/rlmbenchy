from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from rlmbenchy.logger.rlm_logger import RLMLogger

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "schemas" / "otel-log-v1.schema.json"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_valid_records(records: list[dict[str, Any]]) -> None:
    validator = Draft202012Validator(_load_schema())
    for record in records:
        errors = sorted(validator.iter_errors(record), key=lambda error: error.path)
        assert errors == [], [
            {
                "record_id": record.get("record_id"),
                "path": list(error.path),
                "message": error.message,
            }
            for error in errors
        ]


def test_otel_log_schema_is_valid_json_schema() -> None:
    Draft202012Validator.check_schema(_load_schema())


def test_otel_log_schema_validates_golden_fixtures() -> None:
    records: list[dict[str, Any]] = []
    for path in sorted(GOLDEN_DIR.glob("*.jsonl")):
        records.extend(_load_jsonl(path))

    assert records
    _assert_valid_records(records)


def test_otel_log_schema_validates_runtime_log_span_and_metric_records(
    tmp_path: Path,
) -> None:
    logger = RLMLogger(log_dir=tmp_path, file_name="schema")
    logger.log_metadata(
        {"model_id": "openai/fake", "api_base": "https://api.openai.com"}
    )
    logger.log(
        {
            "event_type": "llm.request",
            "call_id": "call_1",
            "data": {"model": "openai/fake"},
            "stats": {"prompt_chars": 12},
        }
    )
    logger.log(
        {
            "event_type": "llm.response",
            "call_id": "call_1",
            "data": {"model": "openai/fake", "response_text": "ok"},
            "stats": {"elapsed_ms": 25, "prompt_tokens": 5, "generated_tokens": 2},
        }
    )
    logger.log_run_result(
        {"status": "success", "stop_reason": "success", "elapsed_ms": 30}
    )

    assert logger.log_file_path is not None
    records = _load_jsonl(Path(logger.log_file_path))
    assert {record["record_type"] for record in records} >= {"log", "span", "metric"}
    _assert_valid_records(records)
