"""Tool builders for the s_niah workload."""

from __future__ import annotations

from collections.abc import Mapping

import dspy

from rlmbenchy.datahub.workloads.support.tools import build_task_text_lookup_tool


def build_tools(haystack_by_task_id: Mapping[str, str]) -> list[dspy.Tool]:
    """Build S-NIAH-specific tools over preloaded haystack data."""

    return build_task_text_lookup_tool(
        haystack_by_task_id,
        tool_name="s_niah_get_haystack",
        description=(
            "Retrieve the full haystack text containing records for an S-NIAH task. "
            "Args: task_id (str). Returns the haystack as a multi-line string."
        ),
    )
