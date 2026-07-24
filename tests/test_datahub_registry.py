from __future__ import annotations

from pathlib import Path

from rlmbenchy.datahub.registry import AVAILABLE_WORKLOADS, load_workload
from rlmbenchy.datahub.workloads.catalog_builtins import builtin_workload_loaders


def test_available_workloads_matches_builtin_loaders() -> None:
    assert tuple(sorted(builtin_workload_loaders())) == AVAILABLE_WORKLOADS


def test_load_workload_tasks_v0_returns_bundle() -> None:
    bundle = load_workload("tasks_v0", task_limit=1)

    assert bundle.workload_name == "tasks_v0"
    assert bundle.tasks
    assert [str(name) for name in bundle.signature.input_fields] == ["task"]
    assert [str(name) for name in bundle.signature.output_fields] == ["answer"]


def test_every_builtin_workload_has_readme_and_setup_docs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workloads_root = repo_root / "rlmbenchy" / "datahub" / "workloads"

    for workload_name in builtin_workload_loaders():
        workload_dir = workloads_root / workload_name
        assert (workload_dir / "README.md").is_file(), workload_name
        assert (workload_dir / "setup.md").is_file(), workload_name
