"""Shared LM helpers for the RLM runtime."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import dspy
from dspy.clients import lm as dspy_lm_module
from dspy.dsp.utils import settings as dspy_settings
from dspy.utils.exceptions import (
    ContextWindowExceededError as DspyContextWindowExceededError,
)
from litellm import ContextWindowExceededError as LitellmContextWindowExceededError

from rlmbenchy.chatgpt_auth import (
    CHATGPT_CODEX_API_BASE,
    CHATGPT_OFFICIAL_API_BASE,
    build_chatgpt_extra_headers,
    build_chatgpt_responses_request,
    extract_reasoning_text_from_responses_payload,
    extract_text_from_responses_payload,
    is_chatgpt_api_base,
    is_chatgpt_official_api_base,
    normalize_chatgpt_model_for_litellm,
    normalize_chatgpt_model_for_openai_api,
    resolve_chatgpt_auth,
)
from rlmbenchy.litellm_responses import drain_litellm_responses_stream
from rlmbenchy.lm_config import VALID_LM_TRANSPORTS
from rlmbenchy.rlm.reasoning import install_reasoning_native_allowlist_override
from rlmbenchy.runtime_config import (
    load_project_env,
    resolve_openrouter_api_key,
    resolve_secret_for_env,
)


class ChatGPTResponsesLM(dspy.LM):
    """LM wrapper for ChatGPT subscription-backed responses transport."""

    def _process_response(self, response: Any) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            return super()._process_response(response)

        result: dict[str, Any] = {}

        text = extract_text_from_responses_payload(response)
        if text:
            result["text"] = text

        tool_calls: list[dict[str, Any]] = []
        for item in response.get("output") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") == "function_call":
                tool_calls.append(item)
        if tool_calls:
            result["tool_calls"] = tool_calls

        reasoning = extract_reasoning_text_from_responses_payload(response)
        if reasoning:
            result["reasoning_content"] = reasoning

        return [result]

    def _process_lm_response(
        self,
        response: Any,
        prompt: str | None,
        messages: list[dict[str, Any]] | None,
        **kwargs: Any,
    ) -> list[dict[str, Any] | str]:
        if not isinstance(response, dict):
            return super()._process_lm_response(response, prompt, messages, **kwargs)

        outputs: list[dict[str, Any] | str] = list(self._process_response(response))
        if dspy_settings.disable_history:
            return outputs

        usage = response.get("usage")
        history_usage = dict(usage) if isinstance(usage, dict) else {}

        hidden_params = response.get("_hidden_params")
        cost = None
        if isinstance(hidden_params, dict):
            raw_cost = hidden_params.get("response_cost")
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                cost = float(raw_cost)

        history_kwargs = {
            key: value
            for key, value in kwargs.items()
            if not str(key).startswith("api_")
        }
        self.update_history(
            {
                "prompt": prompt,
                "messages": messages,
                "kwargs": history_kwargs,
                "response": response,
                "outputs": outputs,
                "usage": history_usage,
                "cost": cost,
                "timestamp": datetime.now().isoformat(),
                "uuid": str(uuid.uuid4()),
                "model": self.model,
                "response_model": str(response.get("model") or "") or None,
                "model_type": self.model_type,
            }
        )
        return outputs

    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        kwargs = dict(kwargs)
        _ = kwargs.pop("cache", self.cache)

        messages = messages or [{"role": "user", "content": prompt}]
        merged_kwargs = {**self.kwargs, **kwargs}
        merged_kwargs.pop("rollout_id", None)

        request = build_chatgpt_responses_request(
            model=normalize_chatgpt_model_for_openai_api(self.model),
            messages=messages,
            config={
                "instructions": merged_kwargs.pop("instructions", None),
                "seed": merged_kwargs.pop("seed", None),
                "reasoning": merged_kwargs.pop("reasoning", None),
                "text": merged_kwargs.pop("text", None),
            },
        )

        raw_extra_headers = merged_kwargs.pop("extra_headers", {})
        extra_headers: dict[str, Any] = (
            {str(key): value for key, value in raw_extra_headers.items()}
            if isinstance(raw_extra_headers, dict)
            else {}
        )
        api_base = str(merged_kwargs.pop("api_base"))
        api_key = str(merged_kwargs.pop("api_key"))
        timeout = merged_kwargs.pop("timeout", None)
        _ = merged_kwargs.pop("temperature", None)
        _ = merged_kwargs.pop("max_tokens", None)
        _ = merged_kwargs.pop("max_completion_tokens", None)
        _ = merged_kwargs.pop("top_p", None)

        try:
            stream = dspy_lm_module.litellm.responses(
                input=request.input,
                instructions=request.instructions,
                # Keep the provider prefix for LiteLLM routing. LiteLLM strips it
                # before sending the model slug to the OpenAI-compatible endpoint.
                model=normalize_chatgpt_model_for_litellm(self.model),
                api_base=api_base,
                api_key=api_key,
                extra_headers=extra_headers,
                stream=True,
                store=False,
                timeout=timeout,
                seed=request.seed,
                reasoning=request.reasoning,
                text=request.text,
                num_retries=self.num_retries,
                retry_strategy="exponential_backoff_retry",
            )
        except LitellmContextWindowExceededError as exc:
            raise DspyContextWindowExceededError(model=self.model) from exc
        return drain_litellm_responses_stream(stream)


def load_openrouter_api_key() -> str:
    return str(resolve_openrouter_api_key() or "").strip()


def resolve_model_api_key(
    *,
    api_base: str,
    api_key: str | None = None,
    api_key_env: str | None = None,
    api_key_override: str | None = None,
) -> str:
    load_project_env()

    explicit_override = str(api_key_override or "").strip()
    if explicit_override:
        return explicit_override

    explicit_key = str(api_key or "").strip()

    env_name = str(api_key_env or "").strip()
    if env_name:
        env_value = resolve_secret_for_env(env_name)
        if env_value:
            return env_value
        if explicit_key:
            return explicit_key
        raise RuntimeError(
            f"Missing model API key in environment variable {env_name!r}."
        )

    if "openrouter.ai" in str(api_base).strip().lower():
        openrouter_key = load_openrouter_api_key()
        if openrouter_key:
            return openrouter_key
        if explicit_key:
            return explicit_key
        return ""

    if explicit_key:
        return explicit_key

    chatgpt_auth = resolve_chatgpt_auth(api_base=api_base)
    if chatgpt_auth is not None:
        return chatgpt_auth.access_token

    return ""


def build_lm(
    *,
    api_base: str,
    model: str,
    api_key: str,
    request_kwargs: dict[str, Any] | None = None,
    lm_transport: str | None = None,
    **extra_kwargs: Any,
) -> dspy.LM:
    install_reasoning_native_allowlist_override()

    resolved_lm_transport = str(lm_transport or "auto").strip().lower() or "auto"
    if resolved_lm_transport not in VALID_LM_TRANSPORTS:
        raise ValueError(f"lm_transport must be one of {sorted(VALID_LM_TRANSPORTS)}.")

    model_name = model if "/" in model else f"openai/{model}"
    resolved_api_key = api_key
    extra_headers = dict(extra_kwargs.pop("extra_headers", {}) or {})
    model_type = extra_kwargs.pop("model_type", "chat")
    use_chatgpt_responses_lm = False

    if is_chatgpt_official_api_base(api_base):
        raise RuntimeError(
            f"{CHATGPT_OFFICIAL_API_BASE!r} is not supported by this Python runtime. "
            f"Use {CHATGPT_CODEX_API_BASE!r} instead."
        )

    if resolved_lm_transport == "chatgpt_responses":
        if not is_chatgpt_api_base(api_base):
            raise ValueError(
                "lm_transport='chatgpt_responses' requires a ChatGPT api_base."
            )
        use_chatgpt_responses_lm = True
        model_type = "responses"

    if is_chatgpt_api_base(api_base):
        model_name = normalize_chatgpt_model_for_litellm(model_name)
        chatgpt_auth = resolve_chatgpt_auth(api_base=api_base, api_key=api_key)
        if chatgpt_auth is not None:
            resolved_api_key = chatgpt_auth.access_token
            default_headers = build_chatgpt_extra_headers(
                api_base=api_base,
                account_id=chatgpt_auth.account_id,
            )
            extra_headers = {**default_headers, **extra_headers}
        use_chatgpt_responses_lm = True
        model_type = "responses"

    kwargs: dict[str, Any] = {
        "api_base": api_base,
        "api_key": resolved_api_key,
        "cache": False,
    }
    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    if request_kwargs:
        kwargs.update(request_kwargs)
    kwargs.update(extra_kwargs)

    if use_chatgpt_responses_lm:
        kwargs["model_type"] = model_type
        return ChatGPTResponsesLM(model_name, **kwargs)

    return dspy.LM(model_name, model_type=model_type, **kwargs)
