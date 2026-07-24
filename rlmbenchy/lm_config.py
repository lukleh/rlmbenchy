"""Shared config parsing and provider-validation utilities for DSPy-backed flows."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

# These are convenience constants for callers that want explicit defaults.
# parse_lm_config() itself requires callers to pass defaults explicitly —
# it will NOT silently fall back to these if the config omits [lm] fields.
DEFAULT_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/openai/gpt-oss-20b"

VALID_REASONING_FORMATS = {"none", "auto", "deepseek", "deepseek-legacy"}
VALID_UNSUPPORTED_PARAMETER_MODES = {"off", "warn", "error"}
VALID_LM_TRANSPORTS = {"auto", "chatgpt_responses"}

_OPENROUTER_SUPPORTED_PARAMS_CACHE: dict[str, set[str]] | None = None


def parse_optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer, not a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"{field_name} must be an integer, got {value!r}.")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must be an integer.")
        try:
            return int(stripped)
        except ValueError:
            raise ValueError(f"{field_name} must be an integer.") from None
    raise ValueError(f"{field_name} must be an integer.")


def parse_optional_choice(
    value: object, field_name: str, valid_choices: set[str]
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be one of {sorted(valid_choices)}.")
    normalized = value.strip().lower()
    if normalized not in valid_choices:
        raise ValueError(f"{field_name} must be one of {sorted(valid_choices)}.")
    return normalized


def parse_optional_keyword(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return normalized


def parse_optional_bool_or_on_off(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true"}:
            return True
        if normalized in {"off", "false"}:
            return False
    raise ValueError(f"{field_name} must be a boolean, 'on', or 'off'.")


def parse_supported_params(value: object) -> tuple[str, frozenset[str]]:
    if value is None:
        return "warn", frozenset()
    if not isinstance(value, dict):
        raise ValueError("lm.supported_params must be a table/object.")

    value_dict: dict[str, Any] = {str(key): item for key, item in value.items()}
    mode_raw = value_dict.get("mode", "warn")
    allow_raw = value_dict.get("ignore", [])
    mode = str(mode_raw).strip().lower()
    if mode == "ignore":
        mode = "off"
    if mode not in VALID_UNSUPPORTED_PARAMETER_MODES:
        raise ValueError(
            "lm.supported_params.mode must be one of "
            f"{sorted(VALID_UNSUPPORTED_PARAMETER_MODES)}."
        )
    if not isinstance(allow_raw, list):
        raise ValueError(
            "lm.supported_params.ignore must be a list of parameter names."
        )

    allow = frozenset(str(item).strip() for item in allow_raw if str(item).strip())
    return mode, allow


def parse_lm_transport(value: object) -> str:
    transport = parse_optional_choice(
        value,
        "lm.transport",
        VALID_LM_TRANSPORTS,
    )
    return transport or "auto"


def parse_optional_secret_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def normalize_request_kwargs(
    request_kwargs: dict[str, Any],
    *,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> dict[str, Any]:
    normalized = dict(request_kwargs)

    if "temperature" in normalized:
        temperature_raw = normalized["temperature"]
        if isinstance(temperature_raw, bool):
            raise ValueError("lm.request.temperature must be numeric, not a boolean.")
        try:
            normalized["temperature"] = float(temperature_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("lm.request.temperature must be numeric.") from exc
    elif default_temperature is not None:
        normalized["temperature"] = float(default_temperature)

    if "max_tokens" in normalized:
        max_tokens = parse_optional_int(
            normalized["max_tokens"], "lm.request.max_tokens"
        )
        if max_tokens is None or max_tokens <= 0:
            raise ValueError("lm.request.max_tokens must be > 0.")
        normalized["max_tokens"] = max_tokens
    elif default_max_tokens is not None:
        normalized["max_tokens"] = default_max_tokens

    if "reasoning" in normalized:
        reasoning_raw = normalized["reasoning"]
        if not isinstance(reasoning_raw, dict):
            raise ValueError("lm.request.reasoning must be a table/object.")
        reasoning = dict(reasoning_raw)
        if "effort" in reasoning:
            reasoning["effort"] = parse_optional_keyword(
                reasoning["effort"],
                "lm.request.reasoning.effort",
            )
        if reasoning:
            normalized["reasoning"] = reasoning
        else:
            normalized.pop("reasoning")

    if "reasoning_effort" in normalized:
        normalized["reasoning_effort"] = parse_optional_keyword(
            normalized["reasoning_effort"],
            "lm.request.reasoning_effort",
        )

    if "reasoning_format" in normalized:
        normalized["reasoning_format"] = parse_optional_choice(
            normalized["reasoning_format"],
            "lm.request.reasoning_format",
            VALID_REASONING_FORMATS,
        )

    if "chat_template_kwargs" in normalized:
        kwargs_raw = normalized["chat_template_kwargs"]
        if not isinstance(kwargs_raw, dict):
            raise ValueError("lm.request.chat_template_kwargs must be a table/object.")
        kwargs = dict(kwargs_raw)
        if "enable_thinking" in kwargs:
            kwargs["enable_thinking"] = parse_optional_bool_or_on_off(
                kwargs["enable_thinking"],
                "lm.request.chat_template_kwargs.enable_thinking",
            )
        if kwargs:
            normalized["chat_template_kwargs"] = kwargs
        else:
            normalized.pop("chat_template_kwargs")

    if "include_reasoning" in normalized:
        normalized["include_reasoning"] = parse_optional_bool_or_on_off(
            normalized["include_reasoning"],
            "lm.request.include_reasoning",
        )

    return normalized


def parse_lm_auth_config(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    lm_raw = raw.get("lm", {})
    lm_raw = lm_raw if isinstance(lm_raw, dict) else {}
    api_key = parse_optional_secret_string(lm_raw.get("api_key"))
    api_key_env = parse_optional_secret_string(lm_raw.get("api_key_env"))
    return api_key, api_key_env


def parse_lm_config(
    raw: dict[str, Any],
    *,
    default_api_base: str,
    default_model: str,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> tuple[str, str, dict[str, Any], str, frozenset[str], str]:
    """Parse LM connection and request settings from a raw config dict.

    Callers must supply ``default_api_base`` and ``default_model`` explicitly
    so that the defaults are visible at the call site rather than buried here.
    """
    lm_raw = raw.get("lm", {})
    lm_raw = lm_raw if isinstance(lm_raw, dict) else {}

    api_base = str(lm_raw.get("api_base", default_api_base)).strip() or default_api_base
    model = str(lm_raw.get("model", default_model)).strip() or default_model
    lm_transport = parse_lm_transport(lm_raw.get("transport"))

    request_raw = lm_raw.get("request", {})
    request_raw = request_raw if isinstance(request_raw, dict) else {}

    request_kwargs: dict[str, Any] = dict(request_raw)

    request_kwargs = normalize_request_kwargs(
        request_kwargs,
        default_temperature=default_temperature,
        default_max_tokens=default_max_tokens,
    )
    supported_mode, ignore_unsupported = parse_supported_params(
        lm_raw.get("supported_params")
    )

    return (
        api_base.strip(),
        model.strip(),
        request_kwargs,
        supported_mode,
        ignore_unsupported,
        lm_transport,
    )


def fetch_openrouter_supported_parameters(model: str) -> set[str] | None:
    global _OPENROUTER_SUPPORTED_PARAMS_CACHE

    if _OPENROUTER_SUPPORTED_PARAMS_CACHE is None:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "rlmbenchy/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        cache: dict[str, set[str]] = {}
        rows = payload.get("data", [])
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model_id = row.get("id")
                supported_parameters = row.get("supported_parameters")
                if isinstance(model_id, str) and isinstance(supported_parameters, list):
                    cache[model_id] = {
                        param
                        for param in supported_parameters
                        if isinstance(param, str)
                    }
        _OPENROUTER_SUPPORTED_PARAMS_CACHE = cache

    model_lookup = model.removeprefix("openrouter/")
    return _OPENROUTER_SUPPORTED_PARAMS_CACHE.get(model_lookup)


def accepted_parameter_names(key: str) -> set[str]:
    if key == "reasoning":
        return {"reasoning", "reasoning_effort"}
    return {key}


def validate_supported_parameters_for_openrouter(
    *,
    api_base: str,
    model: str,
    supported_parameter_mode: str,
    ignore_unsupported_parameters: frozenset[str],
    request_params: dict[str, Any],
) -> None:
    mode = str(supported_parameter_mode).strip().lower() or "warn"
    if mode == "ignore":
        mode = "off"
    if mode not in VALID_UNSUPPORTED_PARAMETER_MODES:
        raise ValueError(
            "supported_parameter_mode must be one of "
            f"{sorted(VALID_UNSUPPORTED_PARAMETER_MODES)}."
        )
    if mode == "off":
        return

    if "openrouter.ai" not in api_base:
        return

    supported = fetch_openrouter_supported_parameters(model)
    if supported is None:
        message = (
            f"provider-parameter validation unavailable for model={model}; "
            "failed to load OpenRouter model metadata."
        )
        if mode == "error":
            raise ValueError(message)
        print(f"validation_warning={message}", file=sys.stderr)
        return

    unsupported: list[str] = []
    for key in request_params:
        if key in ignore_unsupported_parameters:
            continue
        accepted = accepted_parameter_names(key)
        if not (accepted & supported):
            unsupported.append(f"{key} (expected one of {sorted(accepted)})")

    if not unsupported:
        return

    details = ", ".join(unsupported)
    message = (
        f"unsupported parameters for model={model}: {details}. "
        f"Allowed by model metadata: {sorted(supported)}"
    )
    if mode == "error":
        raise ValueError(message)
    print(f"validation_warning={message}", file=sys.stderr)
