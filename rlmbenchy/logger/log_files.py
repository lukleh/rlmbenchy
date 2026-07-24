"""Shared log-file discovery helpers."""

from __future__ import annotations

from pathlib import Path

LOG_FILE_GLOB = "rlm*.jsonl"


def find_log_files(log_dir: Path | str) -> list[Path]:
    """Return rlmbenchy JSONL log files newest first."""
    root = Path(log_dir)
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.glob(LOG_FILE_GLOB) if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )


def find_latest_log_file(log_dir: Path | str) -> Path | None:
    """Return the newest rlmbenchy JSONL log file in a directory."""
    files = find_log_files(log_dir)
    return files[0] if files else None


__all__ = ["LOG_FILE_GLOB", "find_latest_log_file", "find_log_files"]
