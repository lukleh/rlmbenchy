"""Experimental, read-only compatibility with Codex ChatGPT authentication."""

from __future__ import annotations

import base64
import json
import os
import platform
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

CHATGPT_CODEX_API_BASE = "https://chatgpt.com/backend-api/codex"
CHATGPT_OFFICIAL_API_BASE = "https://chatgpt.com/backend-api"
TOKEN_EXPIRY_SKEW_SECONDS = 60
DEFAULT_CHATGPT_ORIGINATOR = "rlmbenchy"
DEFAULT_RESPONSES_INSTRUCTIONS = "You are a concise assistant."
_FILE_AUTH_LOGIN_GUIDANCE = (
    "Run `codex login -c cli_auth_credentials_store=file` and retry. "
    "This stores sensitive Codex tokens in a plaintext `auth.json` file; "
    "protect it like a password."
)


@dataclass(frozen=True)
class ChatGPTAuthContext:
    access_token: str
    account_id: str | None = None


@dataclass(frozen=True)
class ChatGPTResponsesRequest:
    model: str
    instructions: str
    input: list[dict[str, Any]]
    seed: int | None = None
    reasoning: dict[str, Any] | None = None
    text: dict[str, Any] | None = None


def is_chatgpt_api_base(api_base: str) -> bool:
    normalized = str(api_base or "").strip().rstrip("/").lower()
    return normalized == CHATGPT_CODEX_API_BASE.lower()


def is_chatgpt_official_api_base(api_base: str) -> bool:
    normalized = str(api_base or "").strip().rstrip("/").lower()
    return normalized == CHATGPT_OFFICIAL_API_BASE.lower()


def normalize_chatgpt_model_for_openai_api(model: str) -> str:
    value = str(model or "").strip()
    if "/" not in value:
        return value
    provider, model_name = value.split("/", 1)
    if provider in {"chatgpt", "openai"} and model_name:
        return model_name
    return value


def normalize_chatgpt_model_for_litellm(model: str) -> str:
    value = str(model or "").strip()
    if value.startswith("chatgpt/"):
        return f"openai/{value.split('/', 1)[1]}"
    return value


def resolve_chatgpt_auth(
    *,
    api_base: str,
    api_key: str | None = None,
) -> ChatGPTAuthContext | None:
    if not is_chatgpt_api_base(api_base):
        return None

    explicit_api_key = str(api_key or "").strip()
    if explicit_api_key:
        return ChatGPTAuthContext(
            access_token=explicit_api_key,
            account_id=extract_account_id(explicit_api_key),
        )

    return _load_codex_auth_context()


def build_chatgpt_extra_headers(
    *,
    api_base: str,
    account_id: str | None,
) -> dict[str, str]:
    del api_base
    originator = DEFAULT_CHATGPT_ORIGINATOR
    headers = {
        "originator": originator,
        "user-agent": _default_chatgpt_user_agent(originator=originator),
        "session_id": str(uuid4()),
        "OpenAI-Beta": "responses=experimental",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def build_chatgpt_responses_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    default_instructions: str = DEFAULT_RESPONSES_INSTRUCTIONS,
) -> ChatGPTResponsesRequest:
    cfg = dict(config or {})
    instructions_chunks: list[str] = []
    input_messages: list[dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip().lower() or "user"
        content = _convert_message_content_to_responses_content(message.get("content"))
        if role in {"system", "developer"}:
            if content:
                instructions_chunks.append(_responses_content_to_text(content))
            continue
        if not content:
            continue
        input_messages.append({"role": role, "content": content})

    if not input_messages:
        input_messages.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": ""}],
            }
        )

    explicit_instructions = str(cfg.pop("instructions", "") or "").strip()
    instructions = explicit_instructions or "\n\n".join(
        chunk for chunk in instructions_chunks if chunk
    )
    if not instructions:
        instructions = default_instructions

    seed_value = cfg.pop("seed", None)
    seed: int | None = None
    if isinstance(seed_value, bool):
        seed = None
    elif isinstance(seed_value, int):
        seed = seed_value
    elif isinstance(seed_value, float):
        seed = int(seed_value)
    elif isinstance(seed_value, str) and seed_value.strip():
        try:
            seed = int(float(seed_value))
        except ValueError:
            seed = None

    reasoning = cfg.pop("reasoning", None)
    if not isinstance(reasoning, dict) or not reasoning:
        reasoning = None

    text = cfg.pop("text", None)
    if not isinstance(text, dict) or not text:
        text = None

    return ChatGPTResponsesRequest(
        model=model,
        instructions=instructions,
        input=input_messages,
        seed=seed,
        reasoning=reasoning,
        text=text,
    )


def extract_text_from_responses_payload(payload: Any) -> str:
    response = _extract_response_object(payload)
    if not isinstance(response, dict):
        return ""

    chunks: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or str(item.get("type") or "") != "message":
            continue
        for content_item in item.get("content") or []:
            if not isinstance(content_item, dict):
                continue
            if str(content_item.get("type") or "") == "output_text":
                text = str(content_item.get("text") or "")
                if text:
                    chunks.append(text)
    return "".join(chunks).strip()


def extract_reasoning_text_from_responses_payload(payload: Any) -> str:
    response = _extract_response_object(payload)
    if not isinstance(response, dict):
        return ""

    chunks: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or str(item.get("type") or "") != "reasoning":
            continue
        for content_item in item.get("content") or []:
            if not isinstance(content_item, dict):
                continue
            text = str(content_item.get("text") or "")
            if text:
                chunks.append(text)
        for summary_item in item.get("summary") or []:
            if not isinstance(summary_item, dict):
                continue
            text = str(summary_item.get("text") or "")
            if text:
                chunks.append(text)
    if chunks:
        return "".join(chunks).strip()

    reasoning = response.get("reasoning")
    if isinstance(reasoning, dict):
        for summary_item in reasoning.get("summary") or []:
            if not isinstance(summary_item, dict):
                continue
            text = str(summary_item.get("text") or "")
            if text:
                chunks.append(text)
    return "".join(chunks).strip()


def _default_chatgpt_user_agent(*, originator: str) -> str:
    system = platform.system() or "Unknown"
    release = platform.release() or "0"
    machine = platform.machine() or "unknown"
    return f"{originator}/{_distribution_version()} ({system} {release}; {machine})"


def _distribution_version() -> str:
    try:
        return version("rlmbenchy")
    except PackageNotFoundError:
        return "0+unknown"


def resolve_codex_auth_file() -> Path:
    codex_home = os.getenv("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _load_codex_auth_context() -> ChatGPTAuthContext:
    auth_file = resolve_codex_auth_file()
    payload = _read_json_file(auth_file)
    if payload is None:
        raise RuntimeError(
            "Missing file-backed Codex ChatGPT auth. Expected an access token in "
            f"`{auth_file}`. {_FILE_AUTH_LOGIN_GUIDANCE} Credentials stored only "
            "in the Codex keyring are unavailable to this experimental transport."
        )

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise RuntimeError(
            "Invalid Codex auth payload. Expected ChatGPT tokens in "
            f"`{auth_file}`. {_FILE_AUTH_LOGIN_GUIDANCE}"
        )

    access_token = str(tokens.get("access_token") or "").strip()
    id_token = str(tokens.get("id_token") or "").strip()
    account_id = str(tokens.get("account_id") or "").strip() or None

    if not access_token:
        raise RuntimeError(
            "Invalid Codex auth payload. Expected an access token in "
            f"`{auth_file}`. {_FILE_AUTH_LOGIN_GUIDANCE}"
        )

    if _is_token_expired(access_token):
        raise RuntimeError(
            f"The Codex ChatGPT access token in `{auth_file}` is expired. "
            "rlmbenchy treats Codex credentials as read-only and will not refresh "
            f"or rewrite them. {_FILE_AUTH_LOGIN_GUIDANCE}"
        )

    return ChatGPTAuthContext(
        access_token=access_token,
        account_id=account_id or extract_account_id(id_token or access_token),
    )


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _is_token_expired(token: str) -> bool:
    expires_at = get_expires_at(token)
    if expires_at is None:
        return True
    return time.time() >= float(expires_at) - TOKEN_EXPIRY_SKEW_SECONDS


def get_expires_at(token: str | None) -> int | None:
    claims = decode_jwt_claims(token)
    exp = claims.get("exp")
    if isinstance(exp, (int, float)):
        return int(exp)
    return None


def extract_account_id(token: str | None) -> str | None:
    claims = decode_jwt_claims(token)
    auth_claims = claims.get("https://api.openai.com/auth")
    if not isinstance(auth_claims, dict):
        return None
    account_id = auth_claims.get("chatgpt_account_id")
    if isinstance(account_id, str) and account_id.strip():
        return account_id.strip()
    return None


def decode_jwt_claims(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(payload_b64)
        decoded = json.loads(payload.decode("utf-8"))
    except Exception:
        return {}
    if isinstance(decoded, dict):
        return decoded
    return {}


def _convert_message_content_to_responses_content(
    content: Any,
) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        text = content.strip()
        return [{"type": "input_text", "text": text}] if text else []
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for item in content:
            block = _convert_content_item_to_responses_block(item)
            if block is not None:
                blocks.append(block)
        return blocks
    if isinstance(content, dict):
        block = _convert_content_item_to_responses_block(content)
        return [block] if block is not None else []
    text = str(content).strip()
    return [{"type": "input_text", "text": text}] if text else []


def _convert_content_item_to_responses_block(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        text = item.strip()
        return {"type": "input_text", "text": text} if text else None
    if not isinstance(item, dict):
        text = str(item).strip()
        return {"type": "input_text", "text": text} if text else None

    item_type = str(item.get("type") or "").strip().lower()
    if item_type in {"text", "input_text", "output_text"}:
        text = str(item.get("text") or item.get("content") or "").strip()
        return {"type": "input_text", "text": text} if text else None
    if item_type == "image_url":
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            url = str(image_url.get("url") or "").strip()
        else:
            url = str(image_url or "").strip()
        return {"type": "input_image", "image_url": url} if url else None
    if item_type == "input_image":
        payload = dict(item)
        if isinstance(payload.get("image_url"), dict):
            image_url = str(payload["image_url"].get("url") or "").strip()
            payload["image_url"] = image_url
        if str(payload.get("image_url") or "").strip():
            payload["type"] = "input_image"
            return payload
        return None
    if item_type:
        return dict(item)

    text = str(item.get("text") or item.get("content") or "").strip()
    return {"type": "input_text", "text": text} if text else None


def _responses_content_to_text(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("content") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_response_object(payload: Any) -> dict[str, Any] | None:
    if hasattr(payload, "model_dump"):
        try:
            payload = payload.model_dump()
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    if isinstance(response, dict):
        return response
    return payload
