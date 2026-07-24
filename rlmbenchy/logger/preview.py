"""Display-oriented helpers for normalized logger read models."""

from __future__ import annotations

import json
from typing import Any

from rlmbenchy.logger.coerce import coerce_int_or


def snippet(text: Any, max_chars: int = 140) -> str:
    content = str(text or "").strip()
    if len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}...[+{len(content) - max_chars} chars]"


def preview_value(value: Any, *, max_chars: int = 220) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    compact = " ".join(str(text).split())
    return snippet(compact, max_chars=max_chars)


def call_request_preview(kind: str, entry: dict[str, Any]) -> str:
    if kind == "lm":
        prompt = str(entry.get("prompt") or "").strip()
        if prompt:
            return snippet(prompt, max_chars=220)
        messages = entry.get("messages")
        if isinstance(messages, list):
            parts: list[str] = []
            for item in messages:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "message")
                content_preview = preview_value(item.get("content"), max_chars=90)
                if content_preview:
                    parts.append(f"{role}: {content_preview}")
            if parts:
                return snippet(" | ".join(parts), max_chars=220)
        return preview_value(entry.get("request_kwargs"), max_chars=220)
    if kind == "tool":
        payload: dict[str, Any] = {}
        if entry.get("args") not in (None, [], ()):
            payload["args"] = entry.get("args")
        if entry.get("kwargs") not in (None, {}):
            payload["kwargs"] = entry.get("kwargs")
        return preview_value(payload, max_chars=220)
    return preview_value(entry.get("prompt"), max_chars=220)


def call_response_preview(kind: str, entry: dict[str, Any]) -> str:
    event_type = str(entry.get("event_type") or "").strip()
    error = entry.get("error_message")
    if kind == "lm":
        return preview_value(
            entry.get("response_preview") or entry.get("response_text") or error,
            max_chars=220,
        )
    if kind == "tool":
        return preview_value(
            entry.get("result") if event_type.endswith(".response") else error,
            max_chars=220,
        )
    return preview_value(
        entry.get("response") if event_type.endswith(".response") else error,
        max_chars=220,
    )


def build_narrative_sections(
    step: dict[str, Any],
    *,
    task_prompt: str = "",
) -> list[dict[str, str]]:
    """Build ordered sections consumed by text, TUI, and web viewers."""
    sections: list[dict[str, str]] = []

    prompt = task_prompt.strip() if task_prompt else ""
    if prompt:
        sections.append({"label": "Task", "kind": "text", "content": prompt})

    reasoning = str(step.get("reasoning") or "").strip()
    if reasoning:
        sections.append({"label": "Reasoning", "kind": "text", "content": reasoning})

    code = str(step.get("code") or "").strip()
    if code:
        sections.append({"label": "Code", "kind": "text", "content": code})

    observed_raw = step.get("observed")
    observed = str(observed_raw or "").strip() if observed_raw not in (None, "") else ""
    if observed:
        sections.append({"label": "Output", "kind": "text", "content": observed})

    exec_error = str(step.get("exec_error") or "").strip()
    if exec_error:
        sections.append({"label": "Error", "kind": "error", "content": exec_error})

    final_outputs = step.get("final_outputs")
    if bool(step.get("finalized")) and final_outputs is not None:
        if isinstance(final_outputs, str):
            content = final_outputs
        else:
            try:
                content = json.dumps(final_outputs, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                content = str(final_outputs)
        sections.append({"label": "Final Outputs", "kind": "final", "content": content})

    call_summary = step.get("call_summary")
    if isinstance(call_summary, dict):
        parts: list[str] = []
        lm = coerce_int_or(call_summary.get("lm"), default=0)
        tool = coerce_int_or(call_summary.get("tool"), default=0)
        llm_query = coerce_int_or(call_summary.get("llm_query"), default=0)
        if lm:
            parts.append(f"{lm} LM")
        if tool:
            parts.append(f"{tool} tool")
        if llm_query:
            parts.append(f"{llm_query} query")
        if parts:
            sections.append(
                {"label": "Calls", "kind": "call_summary", "content": ", ".join(parts)}
            )

    return sections


__all__ = [
    "build_narrative_sections",
    "call_request_preview",
    "call_response_preview",
    "preview_value",
    "snippet",
]
