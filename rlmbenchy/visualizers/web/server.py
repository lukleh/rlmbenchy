"""Serve the rlmbenchy trajectory visualizer locally."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rlmbenchy.logger.api import build_run_index, load_run
from rlmbenchy.resources import resource_path
from rlmbenchy.runtime_paths import resolve_runtime_paths

DEFAULT_STATIC_DIR = resource_path("rlmbenchy.visualizers.web", "static")
DEFAULT_LOG_DIR = resolve_runtime_paths().rlm_log_dir


def _resolve_file_name(root: Path, raw_name: str, expected_suffix: str) -> Path:
    name = Path(raw_name).name
    if name != raw_name:
        raise FileNotFoundError(f"Invalid file name: {raw_name}")
    if not name.endswith(expected_suffix):
        raise FileNotFoundError(f"Expected a {expected_suffix} file: {raw_name}")

    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise FileNotFoundError(f"Path traversal is not allowed: {raw_name}")
    if not candidate.is_file():
        raise FileNotFoundError(f"File not found: {raw_name}")
    return candidate


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _build_handler(
    static_dir: Path,
    log_dir: Path,
):
    class VisualizerHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def _write_json(
            self, payload: dict[str, Any], status: int = HTTPStatus.OK
        ) -> None:
            encoded = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._write_json({"ok": True})
                return

            if parsed.path == "/api/runs":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["25"])[0])
                payload = {
                    "runs": build_run_index(
                        log_dir,
                        limit=max(1, limit),
                    ),
                    "log_dir": str(log_dir),
                }
                self._write_json(payload)
                return

            if parsed.path == "/api/run":
                query = parse_qs(parsed.query)
                log_name = str(query.get("log", [""])[0]).strip()

                if not log_name:
                    self._write_json(
                        {"error": "Missing required query parameter: log"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

                try:
                    log_path = _resolve_file_name(log_dir, log_name, ".jsonl")
                except FileNotFoundError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                    return

                payload = load_run(
                    log_path,
                )
                self._write_json(payload)
                return

            super().do_GET()

    return VisualizerHandler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the rlmbenchy log visualizer.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1"
    )
    parser.add_argument(
        "--port", type=int, default=8027, help="Bind port. Default: 8027"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"Directory with rlmbenchy JSONL logs. Default: {DEFAULT_LOG_DIR}",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open browser automatically.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    static_dir = DEFAULT_STATIC_DIR.resolve()
    log_dir = args.log_dir.expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = _build_handler(
        static_dir=static_dir,
        log_dir=log_dir,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)

    url = f"http://{args.host}:{args.port}"
    print(f"Serving visualizer on {url}")
    print(f"log_dir={log_dir}")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
