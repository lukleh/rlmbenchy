"""Builtin DataHub workload registry — single entry point for workload loading."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from rlmbenchy.datahub.types import WorkloadBundle, WorkloadLoader
from rlmbenchy.datahub.workloads.catalog_builtins import builtin_workload_loaders

WORKLOAD_TASKS_V0 = "tasks_v0"
WORKLOAD_BROWSECOMP_PLUS = "browsecomp_plus"
WORKLOAD_CHECK_CONTRACT = "check_contract"
WORKLOAD_CHECK_ADAPTER_MATRIX = "check_adapter_matrix"
WORKLOAD_OOLONG = "oolong"
WORKLOAD_OOLONG_PAIRS = "oolong_pairs"
WORKLOAD_OPEN_SUBTITLES = "open_subtitles"
WORKLOAD_LONGBENCH_CODEQA = "longbench_codeqa"
WORKLOAD_LONGCOT = "longcot"
WORKLOAD_S_NIAH = "s_niah"
WORKLOAD_TRANSCRIPTS = "transcripts"


@lru_cache(maxsize=1)
def _workload_loaders() -> Mapping[str, WorkloadLoader]:
    return MappingProxyType(dict(builtin_workload_loaders()))


def _available_workload_names() -> tuple[str, ...]:
    return tuple(sorted(_workload_loaders()))


def _get_loader(workload_name: str) -> WorkloadLoader:
    normalized_name = str(workload_name).strip()
    loaders = _workload_loaders()
    loader = loaders.get(normalized_name)
    if loader is None:
        known = ", ".join(sorted(loaders))
        raise ValueError(f"Unknown workload: {normalized_name!r}. Available: {known}")
    return loader


AVAILABLE_WORKLOADS = _available_workload_names()


def load_workload(
    workload_name: str,
    *,
    task_limit: int | None = None,
    task_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> WorkloadBundle:
    loader = _get_loader(workload_name)
    return loader(task_limit, task_id, dict(options or {}))


__all__ = [
    "AVAILABLE_WORKLOADS",
    "WORKLOAD_BROWSECOMP_PLUS",
    "WORKLOAD_CHECK_ADAPTER_MATRIX",
    "WORKLOAD_CHECK_CONTRACT",
    "WORKLOAD_LONGBENCH_CODEQA",
    "WORKLOAD_LONGCOT",
    "WORKLOAD_OOLONG",
    "WORKLOAD_OOLONG_PAIRS",
    "WORKLOAD_OPEN_SUBTITLES",
    "WORKLOAD_S_NIAH",
    "WORKLOAD_TASKS_V0",
    "WORKLOAD_TRANSCRIPTS",
    "WorkloadBundle",
    "WorkloadLoader",
    "load_workload",
]
