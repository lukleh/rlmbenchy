"""Resolve runtime paths for user config, state, share, and cache files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ORG_NAMESPACE = "lukleh"
APP_NAME = "rlmbenchy"
ENV_PREFIX = "RLMBENCHY"


@dataclass(frozen=True)
class RuntimePaths:
    config_dir: Path
    state_dir: Path
    share_dir: Path
    cache_dir: Path

    @property
    def lm_profiles_dir(self) -> Path:
        return self.config_dir / "lm_profiles"

    @property
    def secrets_file(self) -> Path:
        return self.config_dir / "secrets.toml"

    @property
    def transcripts_config_file(self) -> Path:
        return self.config_dir / "transcripts.toml"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def rlm_log_dir(self) -> Path:
        return self.logs_dir / "rlm"

    @property
    def datasets_dir(self) -> Path:
        return self.share_dir / "datasets"

    @property
    def workloads_dir(self) -> Path:
        return self.share_dir / "workloads"

    @property
    def transcripts_dataset_dir(self) -> Path:
        return self.datasets_dir / "transcripts"

    @property
    def transcripts_root(self) -> Path:
        return self.transcripts_dataset_dir / "transcripts"

    @property
    def transcripts_tasks_path(self) -> Path:
        return self.workloads_dir / "transcripts" / "tasks.json"

    def render(self) -> str:
        return "\n".join(
            [
                f"config_dir={self.config_dir}",
                f"state_dir={self.state_dir}",
                f"share_dir={self.share_dir}",
                f"cache_dir={self.cache_dir}",
                f"lm_profiles_dir={self.lm_profiles_dir}",
                f"secrets_file={self.secrets_file}",
                f"transcripts_config_file={self.transcripts_config_file}",
                f"rlm_log_dir={self.rlm_log_dir}",
                f"datasets_dir={self.datasets_dir}",
                f"workloads_dir={self.workloads_dir}",
                f"transcripts_root={self.transcripts_root}",
                f"transcripts_tasks_path={self.transcripts_tasks_path}",
            ]
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "config_dir": str(self.config_dir),
            "state_dir": str(self.state_dir),
            "share_dir": str(self.share_dir),
            "cache_dir": str(self.cache_dir),
            "lm_profiles_dir": str(self.lm_profiles_dir),
            "secrets_file": str(self.secrets_file),
            "transcripts_config_file": str(self.transcripts_config_file),
            "rlm_log_dir": str(self.rlm_log_dir),
            "datasets_dir": str(self.datasets_dir),
            "workloads_dir": str(self.workloads_dir),
            "transcripts_root": str(self.transcripts_root),
            "transcripts_tasks_path": str(self.transcripts_tasks_path),
        }

    def ensure_directories(self) -> None:
        for path in (
            self.config_dir,
            self.state_dir,
            self.share_dir,
            self.cache_dir,
            self.lm_profiles_dir,
            self.logs_dir,
            self.rlm_log_dir,
            self.datasets_dir,
            self.workloads_dir,
            self.transcripts_dataset_dir,
            self.transcripts_tasks_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _xdg_home(env_name: str, fallback: Path) -> Path:
    return _expand_path(os.getenv(env_name) or fallback)


def _default_config_dir() -> Path:
    return (
        _xdg_home("XDG_CONFIG_HOME", Path.home() / ".config") / ORG_NAMESPACE / APP_NAME
    )


def _default_state_dir() -> Path:
    return (
        _xdg_home("XDG_STATE_HOME", Path.home() / ".local" / "state")
        / ORG_NAMESPACE
        / APP_NAME
    )


def _default_share_dir() -> Path:
    return (
        _xdg_home("XDG_DATA_HOME", Path.home() / ".local" / "share")
        / ORG_NAMESPACE
        / APP_NAME
    )


def _default_cache_dir() -> Path:
    return (
        _xdg_home("XDG_CACHE_HOME", Path.home() / ".cache") / ORG_NAMESPACE / APP_NAME
    )


def resolve_runtime_paths(
    config_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    share_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> RuntimePaths:
    resolved_config_dir = _expand_path(
        config_dir or os.getenv(f"{ENV_PREFIX}_CONFIG_DIR") or _default_config_dir()
    )
    resolved_state_dir = _expand_path(
        state_dir or os.getenv(f"{ENV_PREFIX}_STATE_DIR") or _default_state_dir()
    )
    resolved_share_dir = _expand_path(
        share_dir or os.getenv(f"{ENV_PREFIX}_SHARE_DIR") or _default_share_dir()
    )
    resolved_cache_dir = _expand_path(
        cache_dir or os.getenv(f"{ENV_PREFIX}_CACHE_DIR") or _default_cache_dir()
    )

    return RuntimePaths(
        config_dir=resolved_config_dir,
        state_dir=resolved_state_dir,
        share_dir=resolved_share_dir,
        cache_dir=resolved_cache_dir,
    )


__all__ = [
    "APP_NAME",
    "ENV_PREFIX",
    "ORG_NAMESPACE",
    "RuntimePaths",
    "resolve_runtime_paths",
]
