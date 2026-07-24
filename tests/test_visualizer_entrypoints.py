from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_web_visualizer_module_help() -> None:
    result = _run_module("rlmbenchy.visualizers.web", "--help")

    assert result.returncode == 0
    assert "Serve the rlmbenchy log visualizer." in result.stdout
    assert "--log-dir" in result.stdout


def test_tui_visualizer_module_help() -> None:
    result = _run_module("rlmbenchy.visualizers.tui", "--help")

    assert result.returncode == 0
    assert "TUI log viewer for rlmbenchy RLM runs." in result.stdout
    assert "--log-dir" in result.stdout
