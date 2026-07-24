"""Tool builders for the open_subtitles workload."""

from __future__ import annotations

from collections.abc import Mapping

import dspy

from rlmbenchy.datahub.workloads.support.tools import build_task_text_lookup_tool


def build_tools(source_text_by_task_id: Mapping[str, str]) -> list[dspy.Tool]:
    """Build open-subtitles tools over preloaded source texts."""

    return build_task_text_lookup_tool(
        source_text_by_task_id,
        tool_name="subtitles_get_source_text",
        description=(
            "Retrieve the source subtitle text to translate for the current task. "
            "Args: task_id (str). Returns the source text as a string."
        ),
    )
