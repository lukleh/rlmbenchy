"""Shared workload types and contracts for rlmbenchy runners."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import dspy


@dataclass(frozen=True)
class WorkloadTask:
    """Single RLM unit of work.

    ``inputs`` maps signature field names to their values — the keys must
    match the input fields of the workload's ``dspy.Signature``.
    """

    id: str
    inputs: dict[str, Any]
    answer: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: type[dspy.Signature] | None = None


@dataclass(frozen=True)
class WorkloadBundle:
    """Loaded workload payload consumed by a benchmark runner."""

    workload_name: str
    tasks: list[WorkloadTask]
    tools: list[dspy.Tool]
    signature: type[dspy.Signature]
    metadata: dict[str, Any]


WorkloadLoader = Callable[[int | None, str | None, dict[str, Any]], WorkloadBundle]
