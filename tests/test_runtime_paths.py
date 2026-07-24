from __future__ import annotations

import importlib
from pathlib import Path

import rlmbenchy.workbench.config as workbench_config_module
from rlmbenchy.runtime_paths import resolve_runtime_paths


def test_resolve_runtime_paths_uses_env_overrides(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    share_dir = tmp_path / "share"
    cache_dir = tmp_path / "cache"

    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("RLMBENCHY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("RLMBENCHY_SHARE_DIR", str(share_dir))
    monkeypatch.setenv("RLMBENCHY_CACHE_DIR", str(cache_dir))

    runtime_paths = resolve_runtime_paths()

    assert runtime_paths.config_dir == config_dir
    assert runtime_paths.state_dir == state_dir
    assert runtime_paths.share_dir == share_dir
    assert runtime_paths.cache_dir == cache_dir
    assert runtime_paths.lm_profiles_dir == config_dir / "lm_profiles"
    assert runtime_paths.secrets_file == config_dir / "secrets.toml"
    assert runtime_paths.transcripts_config_file == config_dir / "transcripts.toml"
    assert runtime_paths.rlm_log_dir == state_dir / "logs" / "rlm"
    assert runtime_paths.datasets_dir == share_dir / "datasets"
    assert runtime_paths.workloads_dir == share_dir / "workloads"
    assert (
        runtime_paths.transcripts_root
        == share_dir / "datasets" / "transcripts" / "transcripts"
    )
    assert (
        runtime_paths.transcripts_tasks_path
        == share_dir / "workloads" / "transcripts" / "tasks.json"
    )


def test_resolve_runtime_paths_uses_xdg_defaults(monkeypatch, tmp_path: Path) -> None:
    xdg_config = tmp_path / "xdg-config"
    xdg_state = tmp_path / "xdg-state"
    xdg_share = tmp_path / "xdg-share"
    xdg_cache = tmp_path / "xdg-cache"
    monkeypatch.delenv("RLMBENCHY_CONFIG_DIR", raising=False)
    monkeypatch.delenv("RLMBENCHY_STATE_DIR", raising=False)
    monkeypatch.delenv("RLMBENCHY_SHARE_DIR", raising=False)
    monkeypatch.delenv("RLMBENCHY_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg_state))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_share))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))

    runtime_paths = resolve_runtime_paths()

    assert runtime_paths.config_dir == xdg_config / "lukleh" / "rlmbenchy"
    assert runtime_paths.state_dir == xdg_state / "lukleh" / "rlmbenchy"
    assert runtime_paths.share_dir == xdg_share / "lukleh" / "rlmbenchy"
    assert runtime_paths.cache_dir == xdg_cache / "lukleh" / "rlmbenchy"


def test_runtime_paths_ensure_directories_creates_derived_paths(tmp_path: Path) -> None:
    runtime_paths = resolve_runtime_paths(
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        share_dir=tmp_path / "share",
        cache_dir=tmp_path / "cache",
    )

    runtime_paths.ensure_directories()

    assert runtime_paths.config_dir.is_dir()
    assert runtime_paths.state_dir.is_dir()
    assert runtime_paths.share_dir.is_dir()
    assert runtime_paths.cache_dir.is_dir()
    assert runtime_paths.lm_profiles_dir.is_dir()
    assert runtime_paths.rlm_log_dir.is_dir()
    assert runtime_paths.datasets_dir.is_dir()
    assert runtime_paths.workloads_dir.is_dir()
    assert runtime_paths.transcripts_root.parent.is_dir()
    assert runtime_paths.transcripts_tasks_path.parent.is_dir()


def test_workbench_config_prefers_user_profile_dir(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    share_dir = tmp_path / "share"
    cache_dir = tmp_path / "cache"
    profile_dir = config_dir / "lm_profiles"
    profile_dir.mkdir(parents=True)
    override_path = profile_dir / "model-openrouter-openai-gpt-oss-20b_high.toml"
    override_path.write_text('[lm]\nmodel = "override/model"\n', encoding="utf-8")

    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("RLMBENCHY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("RLMBENCHY_SHARE_DIR", str(share_dir))
    monkeypatch.setenv("RLMBENCHY_CACHE_DIR", str(cache_dir))

    reloaded = importlib.reload(workbench_config_module)

    assert reloaded.DEFAULT_CONFIG_DIR == profile_dir
    assert reloaded.DEFAULT_LOG_DIR == state_dir / "logs" / "rlm"
    assert (
        reloaded.resolve_lm_profile_path("model-openrouter-openai-gpt-oss-20b_high")
        == override_path.resolve()
    )
