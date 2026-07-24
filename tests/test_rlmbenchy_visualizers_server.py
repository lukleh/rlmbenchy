from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from otel_fixture_support import to_otel_fixture_records
from rlmbenchy.visualizers.web.server import _build_handler


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False)
        for entry in to_otel_fixture_records(entries)
    )
    path.write_text(payload + "\n", encoding="utf-8")


def test_server_exposes_health_runs_and_run_payload(tmp_path: Path) -> None:
    static_dir = (
        Path(__file__).resolve().parents[1]
        / "rlmbenchy"
        / "visualizers"
        / "web"
        / "static"
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    log_path = log_dir / "rlm_2026-03-07_12-00-00_server123.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "event_type": "run.started",
                "run_id": "run_server",
                "summary": {"n_tasks": 1},
            },
            {
                "event_type": "task.started",
                "run_id": "run_server",
                "task_id": "t1",
                "data": {"query": "task body", "task_inputs": {"task": "task body"}},
            },
            {
                "event_type": "step.started",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
            },
            {
                "event_type": "llm.request",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call_lm_1",
            },
            {
                "event_type": "llm.response",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "call_id": "call_lm_1",
                "data": {"reasoning_text": "reasoning"},
            },
            {
                "event_type": "repl.request",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "data": {"code": "print('ok')"},
            },
            {
                "event_type": "repl.response",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "data": {"output": "ok"},
            },
            {
                "event_type": "repl.final",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "data": {"final_outputs": {"answer": "ok"}},
            },
            {
                "event_type": "step.finished",
                "run_id": "run_server",
                "task_id": "t1",
                "step_index": 1,
                "data": {
                    "status": "success",
                    "stop_reason": "final",
                    "parse_success": True,
                    "final_signal": True,
                },
                "stats": {"elapsed_ms": 12},
            },
            {
                "event_type": "task.finished",
                "run_id": "run_server",
                "task_id": "t1",
                "data": {
                    "status": "success",
                    "stop_reason": "success",
                    "final_outputs": {"answer": "ok"},
                    "observed": 'ok\n\n{"answer": "ok"}',
                    "finalized": True,
                },
            },
            {
                "event_type": "run.finished",
                "run_id": "run_server",
                "data": {"status": "success", "stop_reason": "success"},
                "stats": {"elapsed_ms": 12},
            },
        ],
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler(static_dir, log_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/api/health") as response:
            health = json.load(response)
        assert health == {"ok": True}

        with urlopen(f"{base_url}/api/runs?limit=5") as response:
            runs = json.load(response)
        assert runs["log_dir"] == str(log_dir)
        assert runs["runs"][0]["log_file"] == log_path.name
        assert runs["runs"][0]["report_file"] is None

        with urlopen(f"{base_url}/api/run?log={log_path.name}") as response:
            payload = json.load(response)
        assert payload["run_id"] == "run_server"
        assert payload["summary"]["status"] == "success"
        assert payload["batch_summary"] is None
        assert payload["tasks"][0]["task_id"] == "t1"
        assert payload["tasks"][0]["steps"][0]["observed"] == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_server_returns_404_for_unknown_log(tmp_path: Path) -> None:
    static_dir = (
        Path(__file__).resolve().parents[1]
        / "rlmbenchy"
        / "visualizers"
        / "web"
        / "static"
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler(static_dir, log_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            with urlopen(f"{base_url}/api/run?log=missing.jsonl"):
                raise AssertionError("expected 404")
        except HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
