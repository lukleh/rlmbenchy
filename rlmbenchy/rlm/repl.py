"""Minimal REPL runtime core — JSON-RPC 2.0 protocol.

This module is intentionally small and explicit. It is a reference for the
project's preferred style in core runtime code:

1. Keep the runtime agnostic.
2. Keep the protocol tiny (JSON-RPC 2.0 over stdin/stdout).
3. Keep state outside the runtime (callers bootstrap via ``execute``).
4. Fail fast instead of hiding protocol/runtime failures.

Wire protocol (JSON-RPC 2.0 over JSON lines):

Host → Worker:
  ``{"jsonrpc":"2.0","method":"execute","params":{"code":...},"id":1}``
  ``{"jsonrpc":"2.0","method":"register","params":{"tools":[...],"outputs":[...]},"id":2}``
  ``{"jsonrpc":"2.0","method":"shutdown"}``  (notification, no id)

Worker → Host:
  ``{"jsonrpc":"2.0","result":{"output":"..."},"id":1}``  (success)
  ``{"jsonrpc":"2.0","result":{"final":...},"id":1}``     (SUBMIT called)
  ``{"jsonrpc":"2.0","error":{...},"id":1}``               (error)
  ``{"jsonrpc":"2.0","method":"tool_call","params":{...},"id":100}``  (tool request)

Supported subset:
  object messages only; batch arrays are unsupported.
  request ids are integers.
  ``execute`` and ``register`` require ids; ``shutdown`` is a notification.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeGuard

from dspy.primitives.code_interpreter import CodeInterpreterError, FinalOutput


class ReplRuntimeError(CodeInterpreterError):
    """Fatal REPL transport/protocol/runtime error."""


class ReplExecutionTimeoutError(ReplRuntimeError):
    """Execution exceeded the configured runtime budget."""


# ── JSON-RPC helpers (host side) ──────────────────────────────────────────

JSONRPC_VERSION = "2.0"
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602

JSONRPC_APP_ERRORS = {
    "SyntaxError": -32000,
    "NameError": -32001,
    "TypeError": -32002,
    "ValueError": -32003,
    "AttributeError": -32004,
    "IndexError": -32005,
    "KeyError": -32006,
    "RuntimeError": -32007,
    "CodeInterpreterError": -32008,
    "Unknown": -32099,
}


def _jsonrpc_request_obj(method: str, params: dict, id: int) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params, "id": id}


def _jsonrpc_notification(method: str) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "method": method}


def _jsonrpc_result_obj(result: Any, id: int) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "result": result, "id": id}


def _jsonrpc_error_obj(
    code: int,
    message: str,
    id: int | None,
    data: dict | None = None,
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "error": err, "id": id}


def _is_valid_subset_id(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _response_error_id(message: dict[str, Any]) -> int | None:
    value = message.get("id")
    return value if _is_valid_subset_id(value) else None


def _looks_like_protocol_frame(message: dict[str, Any]) -> bool:
    return any(key in message for key in ("jsonrpc", "method", "result", "error"))


def _validate_jsonrpc_envelope(message: dict[str, Any], *, context: str) -> None:
    if message.get("jsonrpc") != JSONRPC_VERSION:
        raise ReplRuntimeError(
            f"Invalid JSON-RPC message from REPL worker during {context}: "
            "expected jsonrpc='2.0'."
        )


def _validate_jsonrpc_response(
    message: dict[str, Any],
    *,
    expected_id: int,
    context: str,
) -> None:
    _validate_jsonrpc_envelope(message, context=context)

    has_result = "result" in message
    has_error = "error" in message
    if has_result == has_error:
        raise ReplRuntimeError(
            f"Invalid JSON-RPC response from REPL worker during {context}: "
            "expected exactly one of result or error."
        )

    response_id = message.get("id")
    if not _is_valid_subset_id(response_id) or response_id != expected_id:
        raise ReplRuntimeError(
            f"Invalid JSON-RPC response from REPL worker during {context}: "
            f"response ID mismatch (expected {expected_id}, got {response_id})."
        )

    if has_error:
        error = message["error"]
        if (
            not isinstance(error, dict)
            or not isinstance(error.get("code"), int)
            or not isinstance(error.get("message"), str)
        ):
            raise ReplRuntimeError(
                f"Invalid JSON-RPC error from REPL worker during {context}: "
                "expected error object with integer code and string message."
            )


def _prefix_error_type(error_type: str, message: str) -> str:
    clean = str(message or "").strip()
    if not clean:
        return f"{error_type}:"
    first_line = clean.splitlines()[0].strip()
    if first_line.startswith(f"{error_type}:"):
        return clean
    return f"{error_type}:\n{clean}"


# ── Worker source (runs inside subprocess) ────────────────────────────────
# The worker is a standalone Python script in _repl_worker.py.  We read it
# once at import time and pass it to ``python -u -c <source>``.  Keeping it
# in a real .py file means it gets linting, IDE navigation, and readable
# tracebacks — unlike the multi-hundred-line string literal it replaced.

_WORKER_SOURCE_PATH = Path(__file__).with_name("_repl_worker.py")
REPL_WORKER_SOURCE = _WORKER_SOURCE_PATH.read_text(encoding="utf-8")


# ── Base implementation ───────────────────────────────────────────────────


class _BaseProcessReplRuntime:
    """Shared process transport for local/docker REPL backends."""

    def __init__(
        self,
        *,
        tools: dict[str, Callable[..., Any]] | None = None,
        output_fields: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tools: dict[str, Callable[..., Any]] = dict(tools) if tools else {}
        self.output_fields: list[dict[str, Any]] | None = (
            list(output_fields) if output_fields else None
        )
        self._tools_registered = False
        self._request_id = 0
        self.process: subprocess.Popen[str] | None = None

    @property
    def tools(self) -> dict[str, Callable[..., Any]]:
        # Return the live mapping so DSPy-compatible runtimes can mutate in-place
        # (e.g., interpreter.tools.update(...)).
        return self._tools

    def _start_process(self) -> subprocess.Popen[str]:
        raise NotImplementedError

    def start(self) -> None:
        """Start a new worker process, replacing any existing one."""
        self.shutdown()
        self._request_id = 0
        self._tools_registered = False
        self.process = self._start_process()
        self._register_tools()

    def shutdown(self) -> None:
        """Best-effort process shutdown."""
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self._send(_jsonrpc_notification("shutdown"))
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait()
            except Exception:
                self.process.kill()
                self.process.wait()
        self._tools_registered = False
        self.process = None

    def __enter__(self) -> _BaseProcessReplRuntime:
        """Context manager support: start on enter."""
        self.start()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        """Context manager support: always stop on exit."""
        self.shutdown()

    def _register_tools(self) -> None:
        """Register tools and output fields with the worker process."""
        if self._tools_registered:
            return
        params: dict[str, Any] = {}
        if self._tools:
            params["tools"] = [{"name": name} for name in self._tools]
        if self.output_fields:
            params["outputs"] = list(self.output_fields)
        if not params:
            self._tools_registered = True
            return
        self._request_id += 1
        self._send(_jsonrpc_request_obj("register", params, self._request_id))
        response = self._receive()
        _validate_jsonrpc_response(
            response,
            expected_id=self._request_id,
            context="register",
        )
        if "error" in response:
            raise ReplRuntimeError(
                f"Failed to register runtime surface: {response['error']['message']}"
            )
        self._tools_registered = True

    def _handle_tool_call(self, request: dict) -> None:
        """Handle a tool_call request from the worker."""
        request_id = _response_error_id(request)
        if request.get("jsonrpc") != JSONRPC_VERSION:
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_REQUEST,
                    "Invalid request: expected jsonrpc='2.0'.",
                    request_id,
                    {"type": "InvalidRequest"},
                )
            )
            return
        if not _is_valid_subset_id(request.get("id")):
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_REQUEST,
                    "Invalid request: tool_call requires an integer id.",
                    request_id,
                    {"type": "InvalidRequest"},
                )
            )
            return
        request_id = request["id"]
        if request.get("method") != "tool_call":
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_METHOD_NOT_FOUND,
                    f"Unknown method: {request.get('method')}",
                    request_id,
                    {"type": "MethodNotFound"},
                )
            )
            return

        params = request.get("params")
        if not isinstance(params, dict):
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected object.",
                    request_id,
                    {"type": "InvalidParams"},
                )
            )
            return
        tool_name = params.get("name")
        args = params.get("args", [])
        kwargs_raw = params.get("kwargs", {})
        if not isinstance(tool_name, str):
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected string 'name'.",
                    request_id,
                    {"type": "InvalidParams"},
                )
            )
            return
        if not isinstance(args, list):
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected list 'args'.",
                    request_id,
                    {"type": "InvalidParams"},
                )
            )
            return
        if not isinstance(kwargs_raw, dict):
            self._send(
                _jsonrpc_error_obj(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected object 'kwargs'.",
                    request_id,
                    {"type": "InvalidParams"},
                )
            )
            return
        kwargs = dict(kwargs_raw)

        try:
            if tool_name not in self._tools:
                raise CodeInterpreterError(f"Unknown tool: {tool_name}")
            tool_fn = self._tools[tool_name]
            result = tool_fn(*args, **kwargs)
            response = _jsonrpc_result_obj({"value": result, "type": "raw"}, request_id)
            self._send(response)
        except Exception as e:
            error_type = type(e).__name__
            error_code = JSONRPC_APP_ERRORS.get(
                error_type, JSONRPC_APP_ERRORS["Unknown"]
            )
            response = _jsonrpc_error_obj(
                error_code, str(e), request_id, {"type": error_type}
            )
            self._send(response)

    def execute(self, code: str, variables: dict[str, Any] | None = None) -> Any:
        """Execute code and return result, FinalOutput, or raise on error.

        Returns:
            FinalOutput — if SUBMIT() was called
            str — captured stdout (may be empty string)
            None — if no output

        Raises:
            SyntaxError — on invalid Python syntax
            CodeInterpreterError — on runtime errors or protocol failures
        """
        if self.process is None or self.process.poll() is not None:
            raise ReplRuntimeError("REPL worker is not running.")

        if not self._tools_registered:
            self._register_tools()

        prelude: str | None = None
        if variables:
            assignments = [f"{k} = {repr(v)}" for k, v in variables.items()]
            prelude = "\n".join(assignments)

        self._request_id += 1
        execute_request_id = self._request_id

        try:
            params: dict[str, Any] = {"code": code}
            if prelude:
                params["prelude"] = prelude
            self._send(_jsonrpc_request_obj("execute", params, execute_request_id))
        except Exception as exc:
            raise ReplRuntimeError(
                f"Failed to submit code to REPL worker: {exc}"
            ) from exc

        while True:
            if self.process is None or self.process.stdout is None:
                raise ReplRuntimeError("REPL worker is not running.")

            raw_line = self._readline()
            line = raw_line.strip()
            if not line or not line.startswith("{"):
                # Ignore non-JSON noise from subprocess stdout (e.g., os.system output).
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # Ignore malformed JSON noise and keep waiting for a valid protocol frame.
                continue
            if not isinstance(msg, dict):
                continue
            if not _looks_like_protocol_frame(msg):
                continue
            _validate_jsonrpc_envelope(msg, context="execute")

            # Tool call from worker — handle and continue waiting
            if "method" in msg:
                if msg["method"] == "tool_call":
                    self._handle_tool_call(msg)
                    continue
                request_id = _response_error_id(msg)
                if request_id is not None:
                    self._send(
                        _jsonrpc_error_obj(
                            JSONRPC_METHOD_NOT_FOUND,
                            f"Unknown method: {msg.get('method')}",
                            request_id,
                            {"type": "MethodNotFound"},
                        )
                    )
                continue

            # Success response
            if "result" in msg:
                _validate_jsonrpc_response(
                    msg,
                    expected_id=execute_request_id,
                    context="execute",
                )
                result = msg["result"]
                if not isinstance(result, dict):
                    raise ReplRuntimeError(
                        "Invalid JSON-RPC result from REPL worker during execute: "
                        "expected result object."
                    )
                if "final" in result:
                    return FinalOutput(result["final"])
                return result.get("output") or None

            # Error response
            if "error" in msg:
                _validate_jsonrpc_response(
                    msg,
                    expected_id=execute_request_id,
                    context="execute",
                )
                error = msg["error"]
                error_code = error.get("code", JSONRPC_APP_ERRORS["Unknown"])
                error_message = error.get("message", "Unknown error")
                error_data = error.get("data", {})
                if not isinstance(error_data, dict):
                    error_data = {}
                error_type = error_data.get("type", "Error")

                if error_code == JSONRPC_APP_ERRORS["SyntaxError"]:
                    raise SyntaxError(_prefix_error_type("SyntaxError", error_message))
                raise CodeInterpreterError(
                    _prefix_error_type(error_type, error_message)
                )

    def _readline(self) -> str:
        """Read one raw line from worker stdout and surface EOF cleanly."""
        if self.process is None or self.process.stdout is None:
            raise ReplRuntimeError("REPL worker is not running.")
        line = self.process.stdout.readline()
        if line:
            return line

        exit_code = self.process.poll()
        if exit_code is None:
            raise ReplRuntimeError("No output from REPL worker.")

        stderr_text = ""
        if self.process.stderr is not None:
            try:
                stderr_text = (self.process.stderr.read() or "").strip()
            except Exception:
                stderr_text = ""
        if stderr_text:
            raise ReplRuntimeError(
                f"REPL worker exited with code {exit_code}. Stderr: {stderr_text}"
            )
        raise ReplRuntimeError(f"REPL worker exited with code {exit_code}.")

    def _send(self, payload: dict[str, Any]) -> None:
        """Send one JSON message to worker stdin."""
        if self.process is None or self.process.stdin is None:
            raise ReplRuntimeError("REPL worker is not running.")
        if self.process.poll() is not None:
            raise ReplRuntimeError(
                f"REPL worker exited with code {self.process.returncode}."
            )
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _receive(self) -> dict[str, Any]:
        """Receive one JSON message from worker stdout."""
        return json.loads(self._readline())


class LocalProcessReplRuntime(_BaseProcessReplRuntime):
    """REPL backend that runs the worker in the local Python interpreter."""

    def _start_process(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-u", "-c", REPL_WORKER_SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )


class DockerReplRuntime(_BaseProcessReplRuntime):
    """REPL backend that runs the same worker inside a Docker container."""

    def __init__(
        self,
        *,
        image: str = "python:3.14-slim",
        tools: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        super().__init__(tools=tools)
        self.image = image

    def _start_process(self) -> subprocess.Popen[str]:
        command = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=64m,nosuid,nodev",
        ]
        command.extend(
            [
                self.image,
                "python",
                "-u",
                "-c",
                REPL_WORKER_SOURCE,
            ]
        )
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )


VALID_REPL_BACKENDS = ("docker", "local")


def normalize_repl_backend(repl_backend: str | None, *, default: str = "docker") -> str:
    resolved = str(repl_backend or default).strip().lower() or default
    if resolved not in VALID_REPL_BACKENDS:
        expected = ", ".join(repr(name) for name in VALID_REPL_BACKENDS)
        raise ValueError(
            f"Unsupported repl backend {resolved!r}. Expected one of: {expected}."
        )
    return resolved


def runtime_factory_for_backend(
    repl_backend: str | None,
) -> type[LocalProcessReplRuntime | DockerReplRuntime]:
    resolved = normalize_repl_backend(repl_backend)
    if resolved == "local":
        return LocalProcessReplRuntime
    return DockerReplRuntime


def build_repl_runtime(
    repl_backend: str | None,
) -> LocalProcessReplRuntime | DockerReplRuntime:
    return runtime_factory_for_backend(repl_backend)()
