"""Helpers for deriving semantic step fields from telemetry events."""

from __future__ import annotations

import re
from typing import Any


def extract_code_from_response(entry: dict[str, Any]) -> str:
    """Extract fenced Python code from an LLM response event."""
    msg = entry.get("response_message")
    if isinstance(msg, dict):
        content = str(msg.get("content") or "").strip()
        if content:
            fence = re.search(r"```(?:python|py)?\s*\n(.*?)\n```", content, re.DOTALL)
            if fence:
                return fence.group(1).strip()

    resp_text = entry.get("response_text")
    if isinstance(resp_text, str):
        fence = re.search(r"```(?:python|py)?\s*\n(.*?)\n```", resp_text, re.DOTALL)
        if fence:
            return fence.group(1).strip()
    return ""


__all__ = ["extract_code_from_response"]
