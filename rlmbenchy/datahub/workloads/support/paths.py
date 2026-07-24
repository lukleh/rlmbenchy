"""Shared path resolution helpers for workload-local file options."""

from __future__ import annotations

from pathlib import Path


def resolve_path_from_cwd(raw_path: str | Path) -> Path:
    """Resolve a path relative to the current working directory when needed."""

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_option_path_from_cwd(
    raw_path: str | Path | None,
    *,
    default_path: str | Path,
) -> Path:
    """Resolve an explicit option path, or fall back to the default absolute path."""

    if raw_path is None or not str(raw_path).strip():
        return Path(default_path).expanduser().resolve()
    return resolve_path_from_cwd(str(raw_path).strip())


__all__ = ["resolve_option_path_from_cwd", "resolve_path_from_cwd"]
