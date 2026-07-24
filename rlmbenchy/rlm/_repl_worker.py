"""REPL worker process — runs inside a subprocess via ``python -c``.

This module is NOT imported directly.  Its source is read as a string by
``repl.py`` and passed to ``python -u -c <source>`` (or the Docker equivalent).

Extracting it to a real ``.py`` file means it gets linting, IDE support, and
readable tracebacks instead of living as a multi-hundred-line string literal.
"""
# ruff: noqa: T201, S102 — print() is the intended transport; exec() is the core mechanism.

import contextlib
import io
import json
import keyword
import linecache
import sys
import traceback


# ── Transport ──────────────────────────────────────────────────────────────


def _send(message):
    stream = sys.__stdout__
    if stream is None:
        raise RuntimeError("REPL transport stdout is unavailable.")
    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    stream.flush()


def _receive():
    line = sys.stdin.readline()
    if not line:
        raise EOFError("REPL stdin closed.")
    return json.loads(line)


# ── JSON-RPC helpers (worker side) ─────────────────────────────────────────

JSONRPC_VERSION = "2.0"
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602


def _jsonrpc_result(result, id):
    return {"jsonrpc": JSONRPC_VERSION, "result": result, "id": id}


def _jsonrpc_error(code, message, id, data=None):
    err = {"code": code, "message": message}
    if data:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "error": err, "id": id}


def _is_valid_subset_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _response_error_id(message):
    value = message.get("id")
    return value if _is_valid_subset_id(value) else None


JSONRPC_APP_ERRORS = {
    "SyntaxError": -32000,
    "NameError": -32001,
    "TypeError": -32002,
    "ValueError": -32003,
    "AttributeError": -32004,
    "IndexError": -32005,
    "KeyError": -32006,
    "RuntimeError": -32007,
    "Unknown": -32099,
}


# ── FinalOutput exception ─────────────────────────────────────────────────


class FinalOutput(BaseException):
    def __init__(self, value):
        self.value = value


def _install_submit(output_fields):
    namespace = {
        "FinalOutput": FinalOutput,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "None": None,
    }
    if not output_fields:

        def SUBMIT(**kwargs):
            raise FinalOutput(dict(kwargs))

        globals()["SUBMIT"] = SUBMIT
        return

    params = []
    result_fields = []
    for field in output_fields:
        name = field["name"]
        type_name = field.get("type")
        if isinstance(type_name, str) and type_name in {
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
        }:
            params.append(f"{name}: {type_name}")
        else:
            params.append(name)
        result_fields.append(f"{name!r}: {name}")

    signature = ", ".join(params)
    payload = ", ".join(result_fields)
    source = f"def SUBMIT(*, {signature}):\n    raise FinalOutput({{{payload}}})\n"
    exec(source, namespace, namespace)  # noqa: S102
    globals()["SUBMIT"] = namespace["SUBMIT"]


class ToolCallError(RuntimeError):
    pass


_SNIPPET_FILENAME_PREFIX = "<rlm-snippet:"
_PRELUDE_FILENAME_PREFIX = "<rlm-prelude:"


def _cache_virtual_source(filename, source):
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)


def _snippet_filename(msg_id):
    return f"{_SNIPPET_FILENAME_PREFIX}{msg_id}>"


def _prelude_filename(msg_id):
    return f"{_PRELUDE_FILENAME_PREFIX}{msg_id}>"


def _is_snippet_frame(tb):
    if tb is None:
        return False
    filename = tb.tb_frame.f_code.co_filename
    return isinstance(filename, str) and filename.startswith(_SNIPPET_FILENAME_PREFIX)


def _first_snippet_tb(tb):
    while tb is not None and not _is_snippet_frame(tb):
        tb = tb.tb_next
    return tb


def _format_syntax_error(exc):
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


def _format_runtime_error(exc):
    snippet_tb = _first_snippet_tb(exc.__traceback__)
    formatted_tb = snippet_tb or exc.__traceback__
    return "".join(traceback.format_exception(type(exc), exc, formatted_tb)).strip()


# ── Tool stub factory ─────────────────────────────────────────────────────

_tool_call_id = 0


def _make_tool_stub(name):
    def _stub(*args, **kwargs):
        global _tool_call_id
        _tool_call_id += 1
        request_id = _tool_call_id
        _send(
            {
                "jsonrpc": JSONRPC_VERSION,
                "method": "tool_call",
                "params": {"name": name, "args": list(args), "kwargs": kwargs},
                "id": request_id,
            }
        )
        reply = _receive()
        if not isinstance(reply, dict) or reply.get("jsonrpc") != JSONRPC_VERSION:
            raise RuntimeError("Invalid JSON-RPC response for tool call.")
        if reply.get("id") != request_id:
            raise RuntimeError(
                f"Tool call response ID mismatch: expected {request_id}, got {reply.get('id')}"
            )
        if "error" in reply:
            error = reply["error"]
            data = error.get("data") or {}
            error_type = data.get("type")
            message = error.get("message", "Tool call failed.")
            if error_type:
                raise ToolCallError(f"{error_type}: {message}")
            raise ToolCallError(message)
        result = reply.get("result")
        if isinstance(result, dict) and result.get("type") == "json":
            value = result.get("value")
            if isinstance(value, str):
                return json.loads(value)
            return value
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return result

    return _stub


# ── Main loop ──────────────────────────────────────────────────────────────

while True:
    try:
        message = _receive()
    except EOFError:
        break
    except json.JSONDecodeError as exc:
        _send(
            _jsonrpc_error(
                JSONRPC_PARSE_ERROR,
                f"Parse error: {exc}",
                None,
                {"type": "JSONDecodeError"},
            )
        )
        continue
    except Exception as exc:
        _send(
            _jsonrpc_error(
                JSONRPC_INVALID_REQUEST,
                f"Invalid request payload: {exc}",
                None,
                {"type": type(exc).__name__},
            )
        )
        continue

    if not isinstance(message, dict):
        _send(
            _jsonrpc_error(
                JSONRPC_INVALID_REQUEST,
                "Invalid request payload: expected object; batch requests are unsupported.",
                None,
                {"type": "InvalidRequest"},
            )
        )
        continue

    msg_id = _response_error_id(message)
    if message.get("jsonrpc") != JSONRPC_VERSION:
        _send(
            _jsonrpc_error(
                JSONRPC_INVALID_REQUEST,
                "Invalid request payload: expected jsonrpc='2.0'.",
                msg_id,
                {"type": "InvalidRequest"},
            )
        )
        continue

    method = message.get("method")
    if not isinstance(method, str):
        _send(
            _jsonrpc_error(
                JSONRPC_INVALID_REQUEST,
                "Invalid request payload: expected string 'method'.",
                msg_id,
                {"type": "InvalidRequest"},
            )
        )
        continue

    params = message.get("params", {})

    if method == "shutdown":
        if "id" in message:
            _send(_jsonrpc_result({"shutdown": True}, msg_id))
        break

    if not isinstance(params, dict):
        _send(
            _jsonrpc_error(
                JSONRPC_INVALID_PARAMS,
                "Invalid params: expected object.",
                msg_id,
                {"type": "InvalidParams"},
            )
        )
        continue

    if method == "execute":
        if not _is_valid_subset_id(message.get("id")):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_REQUEST,
                    "Invalid request payload: execute requires an integer id.",
                    None,
                    {"type": "InvalidRequest"},
                )
            )
            continue
        code = params.get("code")
        if not isinstance(code, str):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected string 'code'.",
                    msg_id,
                    {"type": "InvalidParams"},
                )
            )
            continue
        prelude = params.get("prelude")
        if prelude is not None and not isinstance(prelude, str):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected string 'prelude'.",
                    msg_id,
                    {"type": "InvalidParams"},
                )
            )
            continue

        output_buffer = io.StringIO()
        snippet_filename = _snippet_filename(msg_id)
        try:
            with (
                contextlib.redirect_stdout(output_buffer),
                contextlib.redirect_stderr(output_buffer),
            ):
                if prelude:
                    prelude_filename = _prelude_filename(msg_id)
                    _cache_virtual_source(prelude_filename, prelude)
                    prelude_compiled = compile(prelude, prelude_filename, "exec")
                    exec(prelude_compiled, globals(), globals())  # noqa: S102
                _cache_virtual_source(snippet_filename, code)
                compiled = compile(code, snippet_filename, "exec")
                exec(compiled, globals(), globals())  # noqa: S102
        except FinalOutput as fo:
            _send(_jsonrpc_result({"final": fo.value}, msg_id))
        except SyntaxError as se:
            _send(
                _jsonrpc_error(
                    -32000, _format_syntax_error(se), msg_id, {"type": "SyntaxError"}
                )
            )
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            error_type = type(exc).__name__
            error_code = JSONRPC_APP_ERRORS.get(
                error_type, JSONRPC_APP_ERRORS["Unknown"]
            )
            _send(
                _jsonrpc_error(
                    error_code, _format_runtime_error(exc), msg_id, {"type": error_type}
                )
            )
        else:
            output = output_buffer.getvalue()
            _send(_jsonrpc_result({"output": output}, msg_id))

    elif method == "register":
        if not _is_valid_subset_id(message.get("id")):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_REQUEST,
                    "Invalid request payload: register requires an integer id.",
                    None,
                    {"type": "InvalidRequest"},
                )
            )
            continue
        tools = params.get("tools", [])
        outputs = params.get("outputs", [])
        if not isinstance(tools, list):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected list 'tools'.",
                    msg_id,
                    {"type": "InvalidParams"},
                )
            )
            continue
        if not isinstance(outputs, list):
            _send(
                _jsonrpc_error(
                    JSONRPC_INVALID_PARAMS,
                    "Invalid params: expected list 'outputs'.",
                    msg_id,
                    {"type": "InvalidParams"},
                )
            )
            continue
        tool_names = []
        for tool_info in tools:
            if not isinstance(tool_info, dict) or not isinstance(
                tool_info.get("name"), str
            ):
                _send(
                    _jsonrpc_error(
                        JSONRPC_INVALID_PARAMS,
                        "Invalid tool descriptor in register request.",
                        msg_id,
                        {"type": "InvalidParams"},
                    )
                )
                break
            tool_names.append(tool_info["name"])
        else:
            output_fields = []
            for output_info in outputs:
                if not isinstance(output_info, dict) or not isinstance(
                    output_info.get("name"), str
                ):
                    _send(
                        _jsonrpc_error(
                            JSONRPC_INVALID_PARAMS,
                            "Invalid output descriptor in register request.",
                            msg_id,
                            {"type": "InvalidParams"},
                        )
                    )
                    break
                name = output_info["name"]
                if not name.isidentifier() or keyword.iskeyword(name):
                    _send(
                        _jsonrpc_error(
                            JSONRPC_INVALID_PARAMS,
                            f"Invalid output field name: {name!r}.",
                            msg_id,
                            {"type": "InvalidParams"},
                        )
                    )
                    break
                output_fields.append(dict(output_info))
            else:
                _install_submit(output_fields)
                for tool_name in tool_names:
                    globals()[tool_name] = _make_tool_stub(tool_name)
                _send(
                    _jsonrpc_result(
                        {
                            "registered": tool_names,
                            "outputs": [field["name"] for field in output_fields],
                        },
                        msg_id,
                    )
                )
                continue
            continue
        continue

    else:
        _send(
            _jsonrpc_error(
                JSONRPC_METHOD_NOT_FOUND,
                f"Unknown method: {method}",
                msg_id,
                {"type": "MethodNotFound"},
            )
        )
