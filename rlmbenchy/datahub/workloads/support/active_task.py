"""Active-task context-variable used by workload tools that dispatch per-task.

Some workloads bind tools over per-task inputs but cannot pass the task id
explicitly through the LM's tool-call surface.
The runner sets the active task id around each task; tools read it via
:func:`active_task_id`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE_TASK_ID: ContextVar[str | None] = ContextVar(
    "workload_active_task_id", default=None
)


def active_task_id() -> str | None:
    return _ACTIVE_TASK_ID.get()


@contextmanager
def active_task(task_id: str) -> Iterator[None]:
    token = _ACTIVE_TASK_ID.set(str(task_id))
    try:
        yield
    finally:
        _ACTIVE_TASK_ID.reset(token)


__all__ = ["active_task", "active_task_id"]
