"""Failure taxonomy and run-result contracts for the RLM loop.

These types are decided once and changed rarely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Stop reasons (failure taxonomy from L8)
# ---------------------------------------------------------------------------


class StopReason(str, Enum):
    """Why the RLM loop terminated."""

    SUCCESS = "success"
    """Model provided a final answer via SUBMIT."""

    PARSE_FAILURE = "parse_failure"
    """Consecutive parse failures exhausted recovery attempts."""

    EXECUTION_ERROR = "execution_error"
    """Consecutive REPL execution errors exhausted recovery attempts."""

    NO_FINAL = "no_final"
    """Max iterations reached without the model producing a final answer."""


@dataclass
class LoopRunResult:
    stop_reason: StopReason
    iterations: int
    final_outputs: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class RLMRunConfig:
    api_base: str
    model: str
    api_key: str
    adapter_mode: str = "auto"
    request_kwargs: dict[str, Any] = field(default_factory=dict)
    num_retries: int = 0
    lm_transport: str = "auto"


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    status: str
    stop_reason: str
    elapsed_ms: int
    latency_s: float
    observed: str
    finalized: bool
    final_outputs: dict[str, Any] | None
    reasoning: str
    code: str
    error: str | None
    loop_result: LoopRunResult


__all__ = [
    "LoopRunResult",
    "RLMRunConfig",
    "StopReason",
    "TaskRunResult",
]
