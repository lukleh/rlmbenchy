"""Tool builders for the oolong_pairs workload."""

from __future__ import annotations

from collections.abc import Mapping

import dspy

from rlmbenchy.datahub.workloads.support.tools import build_task_text_lookup_tool


def build_tools(context_by_task_id: Mapping[str, str]) -> list[dspy.Tool]:
    """Build oolong-pairs-specific tools over preloaded context texts."""

    return build_task_text_lookup_tool(
        context_by_task_id,
        tool_name="oolong_pairs_get_context",
        description=(
            "Retrieve the full context text for an OOLONG-Pairs task. "
            "Args: task_id (str). Returns the complete context_window_text."
        ),
    )
