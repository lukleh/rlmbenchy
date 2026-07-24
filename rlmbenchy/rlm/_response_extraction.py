"""Private helpers for extracting structured data from LLM responses.

These utilities normalise heterogeneous provider response formats (OpenAI,
ChatGPT Responses API, LiteLLM, etc.) into consistent dicts consumed by
:class:`LMLoggingCallback`.  Nothing here is part of the public API.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from rlmbenchy.chatgpt_auth import (
    extract_reasoning_text_from_responses_payload,
    extract_text_from_responses_payload,
)

_DSPY_OUTPUT_FIELD_RE = re.compile(r"\[\[\s*##\s*([A-Za-z0-9_]+)\s*##\s*\]\]")

# ---------------------------------------------------------------------------
# Low-level serialisation
# ---------------------------------------------------------------------------


def response_to_dict(response: Any, *, _max_depth: int = 32) -> dict[str, Any]:
    def _jsonish(value: Any, depth: int = 0) -> Any:
        if depth > _max_depth:
            return {}
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): _jsonish(item, depth + 1) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonish(item, depth + 1) for item in value]
        for method_name in ("model_dump", "to_dict", "dict"):
            method = getattr(value, method_name, None)
            if not callable(method):
                continue
            try:
                dumped = method()
            except TypeError:
                continue
            if isinstance(dumped, dict):
                return _jsonish(dumped, depth + 1)
        try:
            attrs = vars(value)
        except TypeError:
            return {}
        return {
            key_str: _jsonish(item, depth + 1)
            for key in attrs
            if not (key_str := str(key)).startswith("_")
            and not callable(item := attrs[key])
        }

    payload = _jsonish(response)
    if isinstance(payload, dict):
        return payload
    return {}


def mapping_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return response_to_dict(value)


def response_attr_to_dict(response: Any, attr_name: str) -> dict[str, Any]:
    if response is None:
        return {}
    try:
        value = getattr(response, attr_name, None)
    except Exception:
        return {}
    return mapping_to_dict(value)


# ---------------------------------------------------------------------------
# Primitive readers
# ---------------------------------------------------------------------------


def _coerce_number(value: Any, cast: Any) -> Any:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return cast(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return cast(stripped)
        except ValueError:
            return None
    return None


def read_object_float(response: Any, attrs: tuple[str, ...]) -> float | None:
    if response is None:
        return None
    for attr in attrs:
        try:
            value = getattr(response, attr, None)
        except Exception:
            continue
        coerced = _coerce_number(value, float)
        if coerced is not None:
            return coerced
    return None


def read_int(d: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        coerced = _coerce_number(d.get(key), int)
        if coerced is not None:
            return coerced
    return None


def read_float(d: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        coerced = _coerce_number(d.get(key), float)
        if coerced is not None:
            return coerced
    return None


def safe_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def coerce_count(value: Any) -> int:
    coerced = safe_optional_int(value)
    return 0 if coerced is None else coerced


# ---------------------------------------------------------------------------
# Response content extraction
# ---------------------------------------------------------------------------


def extract_lm_response_preview(
    response: Any, *, _precomputed_dict: dict[str, Any] | None = None
) -> str:
    response_dict = (
        _precomputed_dict
        if _precomputed_dict is not None
        else response_to_dict(response)
    )
    response_text = extract_text_from_responses_payload(response_dict)
    if response_text:
        return response_text

    choices = response_dict.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content or "")


def extract_lm_response_message(response: Any) -> dict[str, Any] | None:
    response_dict = response_to_dict(response)
    response_text = extract_text_from_responses_payload(response_dict)
    if response_text:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": response_text,
        }
        reasoning = extract_reasoning_text_from_responses_payload(response_dict)
        if not reasoning:
            reasoning = extract_dspy_output_field_text(response_text, "reasoning") or ""
        if reasoning:
            message["reasoning_content"] = reasoning
        return message

    choices = response_dict.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None

    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message", {})
    if not isinstance(message, dict) or not message:
        return None
    return message


def extract_lm_reasoning_text(response: Any) -> str | None:
    response_dict = response_to_dict(response)
    responses_reasoning = extract_reasoning_text_from_responses_payload(response_dict)
    if responses_reasoning:
        return responses_reasoning

    response_text = extract_lm_response_preview(
        response, _precomputed_dict=response_dict
    )
    structured_reasoning = extract_dspy_output_field_text(response_text, "reasoning")
    if structured_reasoning:
        return structured_reasoning

    message = extract_lm_response_message(response)
    if isinstance(message, dict):
        for key in ("reasoning_content", "reasoning", "reasoning_text"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value

    for key in ("reasoning_content", "reasoning", "reasoning_text"):
        value = response_dict.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def extract_dspy_output_field_text(text: Any, field_name: str) -> str | None:
    raw = str(text or "")
    if not raw.strip():
        return None

    matches = list(_DSPY_OUTPUT_FIELD_RE.finditer(raw))
    if not matches:
        return None

    target = field_name.strip().lower()
    for index, match in enumerate(matches):
        name = str(match.group(1) or "").strip().lower()
        if name != target:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        value = raw[start:end].strip()
        if not value:
            return None
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, str):
            value = parsed.strip()
        return value or None
    return None


def extract_lm_finish_reason(response: Any) -> str | None:
    response_dict = response_to_dict(response)
    status = str(response_dict.get("status") or "").strip()
    if status:
        return status
    choices = response_dict.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    finish_reason = first.get("finish_reason")
    if finish_reason in (None, ""):
        return None
    return str(finish_reason)


# ---------------------------------------------------------------------------
# Token usage and cost
# ---------------------------------------------------------------------------


def extract_lm_token_usage(response: Any) -> dict[str, int | None]:
    response_dict = response_to_dict(response)
    usage = {}
    for candidate in (
        response_attr_to_dict(response, "usage"),
        mapping_to_dict(response_dict.get("usage")),
    ):
        if candidate:
            usage = candidate
            break

    prompt_tokens = read_int(usage, ("prompt_tokens", "input_tokens"))
    generated_tokens = read_int(usage, ("completion_tokens", "output_tokens"))
    total_tokens = read_int(usage, ("total_tokens",))
    if (
        total_tokens is None
        and prompt_tokens is not None
        and generated_tokens is not None
    ):
        total_tokens = prompt_tokens + generated_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "total_tokens": total_tokens,
    }


def extract_lm_cost(response: Any) -> float | None:
    response_dict = response_to_dict(response)
    object_cost = read_object_float(response, ("cost", "response_cost"))
    if object_cost is not None:
        return object_cost

    for candidate in (
        response_dict,
        response_attr_to_dict(response, "usage"),
        mapping_to_dict(response_dict.get("usage")),
        response_attr_to_dict(response, "_hidden_params"),
        mapping_to_dict(response_dict.get("_hidden_params")),
    ):
        cost = read_float(candidate, ("cost", "response_cost"))
        if cost is not None:
            return cost
    return None


# ---------------------------------------------------------------------------
# Compact logging-oriented extraction API
#
# LMLoggingCallback depends on this narrow surface. Each helper takes what
# the callback actually has at the point of call: a response object (may be
# None on error), a history entry (may be None if DSPy didn't record one),
# and in one case the DSPy `outputs` for a preview fallback.
#
# Internally these dispatch to the provider-shape helpers above
# (OpenAI-style choices, ChatGPT Responses output arrays, DSPy history).
# ---------------------------------------------------------------------------

_EMPTY_TOKEN_USAGE = {
    "prompt_tokens": None,
    "generated_tokens": None,
    "total_tokens": None,
}


def _empty_token_usage() -> dict[str, int | None]:
    return dict(_EMPTY_TOKEN_USAGE)


def _has_token_usage(usage: dict[str, int | None]) -> bool:
    return usage["prompt_tokens"] is not None or usage["generated_tokens"] is not None


def extract_usage(
    response: Any,
    history_entry: dict[str, Any] | None,
) -> dict[str, int | None]:
    """Return `{prompt_tokens, generated_tokens, total_tokens}` for logging.

    Preference: current response usage first, then the DSPy history entry's
    top-level `usage` dict. Never probes `lm.history` — that would allow a
    later call to bleed into an earlier call's log.
    """
    if response is not None:
        usage = extract_lm_token_usage(response)
        if _has_token_usage(usage):
            return usage
    if isinstance(history_entry, dict):
        usage_dict = history_entry.get("usage")
        if usage_dict is not None:
            return extract_lm_token_usage({"usage": usage_dict})
    return _empty_token_usage()


def extract_cost(response: Any) -> float | None:
    """Return the LM-reported cost in USD, or None if unknown.

    Only consults the current response — no history fallback, no estimation.
    """
    if response is None:
        return None
    return extract_lm_cost(response)


def extract_finish_reason(response: Any) -> str | None:
    if response is None:
        return None
    return extract_lm_finish_reason(response)


def extract_preview(response: Any, outputs: Any = None) -> str:
    """Short text preview of the response. Falls back to DSPy outputs."""
    preview = extract_lm_response_preview(response) if response is not None else ""
    if preview:
        return preview
    return lm_outputs_preview(outputs)


def extract_reasoning(response: Any) -> str | None:
    if response is None:
        return None
    return extract_lm_reasoning_text(response)


def extract_message(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    return extract_lm_response_message(response)


# ---------------------------------------------------------------------------
# Usage coverage tracking
# ---------------------------------------------------------------------------


def usage_coverage_payload(
    *,
    total_lm_responses: int,
    token_usage_responses: int,
    prompt_tokens_known_responses: int,
    generated_tokens_known_responses: int,
    complete_token_usage_responses: int,
) -> dict[str, Any]:
    total = max(0, int(total_lm_responses))
    prompt_known = min(total, max(0, int(prompt_tokens_known_responses)))
    generated_known = min(total, max(0, int(generated_tokens_known_responses)))
    complete_known = min(total, max(0, int(complete_token_usage_responses)))
    token_usage = min(
        total,
        max(
            0, int(token_usage_responses), prompt_known, generated_known, complete_known
        ),
    )
    return {
        "total_lm_responses": total,
        "token_usage_responses": token_usage,
        "prompt_tokens_known_responses": prompt_known,
        "generated_tokens_known_responses": generated_known,
        "complete_token_usage_responses": complete_known,
        "prompt_tokens_complete": (total == 0 or prompt_known == total),
        "generated_tokens_complete": (total == 0 or generated_known == total),
        "total_tokens_complete": (total == 0 or complete_known == total),
    }


def normalize_usage_coverage(coverage: Any) -> dict[str, Any]:
    data = coverage if isinstance(coverage, dict) else {}
    return usage_coverage_payload(
        total_lm_responses=coerce_count(data.get("total_lm_responses")),
        token_usage_responses=coerce_count(data.get("token_usage_responses")),
        prompt_tokens_known_responses=coerce_count(
            data.get("prompt_tokens_known_responses")
        ),
        generated_tokens_known_responses=coerce_count(
            data.get("generated_tokens_known_responses")
        ),
        complete_token_usage_responses=coerce_count(
            data.get("complete_token_usage_responses")
        ),
    )


def usage_coverage_from_summary(usage_summary: Any) -> dict[str, Any]:
    summary = usage_summary if isinstance(usage_summary, dict) else {}
    coverage_raw = summary.get("coverage")
    if isinstance(coverage_raw, dict):
        return normalize_usage_coverage(coverage_raw)

    prompt_present = summary.get("prompt_tokens") is not None
    generated_present = summary.get("generated_tokens") is not None
    if not prompt_present and not generated_present:
        return usage_coverage_payload(
            total_lm_responses=0,
            token_usage_responses=0,
            prompt_tokens_known_responses=0,
            generated_tokens_known_responses=0,
            complete_token_usage_responses=0,
        )

    return usage_coverage_payload(
        total_lm_responses=1,
        token_usage_responses=1,
        prompt_tokens_known_responses=(1 if prompt_present else 0),
        generated_tokens_known_responses=(1 if generated_present else 0),
        complete_token_usage_responses=(
            1 if prompt_present and generated_present else 0
        ),
    )


def tokens_per_second_summary(
    *,
    prompt_tokens: int | None,
    generated_tokens: int | None,
    elapsed_s: float,
    usage_coverage: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    total_tokens = (
        int(prompt_tokens or 0) + int(generated_tokens or 0)
        if prompt_tokens is not None or generated_tokens is not None
        else None
    )
    normalized_coverage = (
        normalize_usage_coverage(usage_coverage) if usage_coverage is not None else None
    )

    def _rate(tokens: int | None, *, complete: bool) -> float | None:
        if tokens is None or elapsed_s <= 0 or not complete:
            return None
        return round(float(tokens) / elapsed_s, 2)

    prompt_complete = (
        bool(normalized_coverage.get("prompt_tokens_complete"))
        if normalized_coverage is not None
        else prompt_tokens is not None
    )
    generated_complete = (
        bool(normalized_coverage.get("generated_tokens_complete"))
        if normalized_coverage is not None
        else generated_tokens is not None
    )
    total_complete = (
        bool(normalized_coverage.get("total_tokens_complete"))
        if normalized_coverage is not None
        else (prompt_tokens is not None and generated_tokens is not None)
    )

    return {
        "prompt_tokens_per_s": _rate(prompt_tokens, complete=prompt_complete),
        "generated_tokens_per_s": _rate(generated_tokens, complete=generated_complete),
        "total_tokens_per_s": _rate(total_tokens, complete=total_complete),
    }


# ---------------------------------------------------------------------------
# Performance and activity summaries
# ---------------------------------------------------------------------------


def performance_summary(
    *, usage_summary: dict[str, Any], elapsed_s: float
) -> dict[str, Any]:
    usage_coverage = usage_coverage_from_summary(usage_summary)
    return {
        "tokens_per_second": tokens_per_second_summary(
            prompt_tokens=safe_optional_int(usage_summary.get("prompt_tokens")),
            generated_tokens=safe_optional_int(usage_summary.get("generated_tokens")),
            elapsed_s=elapsed_s,
            usage_coverage=usage_coverage,
        )
    }


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).strip().lower()
            if key_lower in {"api_key", "authorization", "auth_token", "token"}:
                redacted[str(key)] = "***REDACTED***"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


def history_entry_for_logged_call(
    lm: Any,
    *,
    history_len_before: int | None,
) -> dict[str, Any] | None:
    history = getattr(lm, "history", None)
    if not isinstance(history, list) or not history:
        return None
    if (
        history_len_before is not None
        and history_len_before >= 0
        and len(history) <= history_len_before
    ):
        return None
    entry = history[-1]
    return entry if isinstance(entry, dict) else None


def lm_outputs_preview(outputs: Any) -> str:
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, dict):
            for key in ("text", "content"):
                value = first.get(key)
                if isinstance(value, str) and value:
                    return value
        if first is not None:
            return str(first)
    if outputs is None:
        return ""
    return str(outputs)


def content_char_count(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, (int, float)) and not isinstance(content, bool):
        return len(str(content))
    if isinstance(content, bool):
        return len(str(content))
    if isinstance(content, list):
        return sum(content_char_count(item) for item in content)
    if isinstance(content, tuple):
        return sum(content_char_count(item) for item in content)
    if isinstance(content, dict):
        if "text" in content:
            return content_char_count(content.get("text"))
        if "content" in content:
            return content_char_count(content.get("content"))
        if "parts" in content:
            return content_char_count(content.get("parts"))
        return 0
    return 0


def message_char_count(message: Any) -> int:
    if isinstance(message, dict):
        return content_char_count(message.get("content"))
    return content_char_count(message)


def event_prompt_chars(payload: dict[str, Any]) -> int | None:
    prompt_chars = payload.get("prompt_chars")
    if isinstance(prompt_chars, int) and prompt_chars >= 0:
        return prompt_chars

    messages = payload.get("messages")
    if isinstance(messages, list):
        return sum(message_char_count(message) for message in messages)

    prompt = payload.get("prompt")
    if prompt is not None:
        return content_char_count(prompt)
    return None
