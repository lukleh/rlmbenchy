"""Shared tool builders for workload packages."""

from __future__ import annotations

from collections.abc import Mapping

import dspy


def build_task_text_lookup_tool(
    text_by_task_id: Mapping[str, str],
    *,
    tool_name: str,
    description: str,
) -> list[dspy.Tool]:
    """Build a single ``task_id -> text`` lookup tool."""

    store: dict[str, str] = {
        str(task_id): str(text) for task_id, text in text_by_task_id.items()
    }

    def lookup_text(task_id: str) -> str:
        normalized = str(task_id).strip()
        if normalized not in store:
            available = sorted(store.keys())[:10]
            raise KeyError(f"Unknown task_id {normalized!r}. Available: {available}")
        return store[normalized]

    return [
        dspy.Tool(
            lookup_text,
            name=tool_name,
            desc=description,
        )
    ]


__all__ = ["build_task_text_lookup_tool"]
