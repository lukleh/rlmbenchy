from __future__ import annotations

import json
from pathlib import Path

import pytest

import rlmbenchy.datahub.cli as datahub_cli
import rlmbenchy.workbench.cli as workbench_cli
from rlmbenchy import cli
from rlmbenchy.runtime_paths import resolve_runtime_paths


def test_main_delegates_args_to_parser(monkeypatch) -> None:
    called: dict[str, list[str] | None] = {}

    def _fake_parse(self, argv):
        called["argv"] = argv
        raise SystemExit(0)

    monkeypatch.setattr(
        cli, "_build_parser", lambda: type("P", (), {"parse_args": _fake_parse})()
    )

    try:
        cli.main(["workloads"])
    except SystemExit:
        pass

    assert called["argv"] == ["workloads"]


def test_main_runs_workloads_command_without_subcommand(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _cmd_workloads(args) -> None:
        called["command"] = "list"
        called["json"] = args.json

    monkeypatch.setattr(datahub_cli, "cmd_workloads", _cmd_workloads)

    cli.main(["workloads"])

    assert called == {"command": "list", "json": False}


def test_main_run_delegates_to_workbench_run_from_config_path(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_run_from_config_path(config_path, *, task_id, seed, repl_backend):
        called["config_path"] = config_path
        called["task_id"] = task_id
        called["seed"] = seed
        called["repl_backend"] = repl_backend

    monkeypatch.setattr(
        workbench_cli, "run_from_config_path", _fake_run_from_config_path
    )

    cli.main(
        [
            "run",
            "--config",
            "/tmp/run.toml",
            "--task-id",
            "t1",
            "--seed",
            "7",
            "--repl-backend",
            "local",
        ]
    )

    assert called == {
        "config_path": Path("/tmp/run.toml"),
        "task_id": "t1",
        "seed": 7,
        "repl_backend": "local",
    }


def test_main_run_requires_config() -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--task-id", "t1"])


def test_main_runs_paths_command(monkeypatch, capsys, tmp_path: Path) -> None:
    runtime_paths = resolve_runtime_paths(
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        share_dir=tmp_path / "share",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(cli, "resolve_runtime_paths", lambda: runtime_paths)

    cli.main(["paths"])
    out = capsys.readouterr().out

    assert f"config_dir={runtime_paths.config_dir}" in out
    assert f"share_dir={runtime_paths.share_dir}" in out
    assert f"rlm_log_dir={runtime_paths.rlm_log_dir}" in out


def test_main_runs_paths_json(monkeypatch, capsys, tmp_path: Path) -> None:
    runtime_paths = resolve_runtime_paths(
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        share_dir=tmp_path / "share",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(cli, "resolve_runtime_paths", lambda: runtime_paths)

    cli.main(["paths", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["config_dir"] == str(runtime_paths.config_dir)
    assert payload["rlm_log_dir"] == str(runtime_paths.rlm_log_dir)
