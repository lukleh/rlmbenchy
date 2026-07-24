"""Tool builders for the tasks_v0 workload."""

from __future__ import annotations

import dspy


def build_tools() -> list[dspy.Tool]:
    """tasks_v0 has no dataset-specific tools."""

    return []
