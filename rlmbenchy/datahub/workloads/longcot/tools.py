"""Tool builders for the longcot workload."""

from __future__ import annotations

import dspy


def build_tools() -> list[dspy.Tool]:
    """longcot has no dataset-specific tools; the prompt is self-contained."""

    return []
