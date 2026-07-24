from __future__ import annotations

import json
from pathlib import Path

import pytest

from otel_fixture_support import to_otel_fixture_records
from rlmbenchy.cli import main


def _write_log(path, entries) -> None:  # noqa: ANN001, ANN201
    lines = [
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_logs_stats_json_output(tmp_path, capsys) -> None:  # noqa: ANN001
    log_path = tmp_path / "stats.jsonl"
    _write_log(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_1",
                "data": {
                    "run_config_name": "p",
                    "workload": "tasks_v0",
                    "model_id": "m",
                    "config": {"seed": 1},
                },
            },
            {
                "event_type": "step.finished",
                "run_id": "run_1",
                "step_index": 1,
                "data": {
                    "parse_success": True,
                    "parse_strategy": "markdown",
                    "final_signal": True,
                },
                "stats": {"elapsed_ms": 10},
            },
            {
                "event_type": "run.finished",
                "run_id": "run_1",
                "data": {"final_outputs": {"answer": "1"}, "stop_reason": "success"},
            },
        ],
    )

    main(["logs", "stats", "--log-file", str(log_path), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["run_count"] == 1
    assert payload["status_counts"]["PASS"] == 1


def test_logs_latest_prints_path(tmp_path, capsys) -> None:  # noqa: ANN001
    first = tmp_path / "rlm_a.jsonl"
    second = tmp_path / "rlm_b.jsonl"
    _write_log(first, [{"event_type": "run.started", "run_id": "run_a"}])
    _write_log(second, [{"event_type": "run.started", "run_id": "run_b"}])
    (tmp_path / "z_notes.jsonl").write_text(
        '{"not": "an rlmbenchy log"}\n',
        encoding="utf-8",
    )

    main(["logs", "latest", "--log-dir", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert out.endswith(".jsonl")
    assert Path(out).name in {"rlm_a.jsonl", "rlm_b.jsonl"}


def test_logs_latest_raises_when_missing(tmp_path) -> None:  # noqa: ANN001
    with pytest.raises(SystemExit):
        main(["logs", "latest", "--log-dir", str(tmp_path)])
