"""Tool builders for the longbench_codeqa workload."""

from __future__ import annotations

from collections.abc import Mapping

import dspy

from rlmbenchy.datahub.workloads.support.tools import build_task_text_lookup_tool


def build_tools(code_by_task_id: Mapping[str, str]) -> list[dspy.Tool]:
    """Build LongBench-CodeQA tools over preloaded code contexts."""

    return build_task_text_lookup_tool(
        code_by_task_id,
        tool_name="longbench_get_code_context",
        description=(
            "Retrieve the full code repository context for a LongBench-CodeQA task. "
            "Args: task_id (str). Returns the complete code as a string."
        ),
    )
