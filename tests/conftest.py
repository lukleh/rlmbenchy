from __future__ import annotations

import sys

import pytest

_PYTEST_CONFIG: pytest.Config | None = None


def pytest_configure(config: pytest.Config) -> None:
    global _PYTEST_CONFIG
    _PYTEST_CONFIG = config


def _write_live_line(
    message: str,
    *,
    config: pytest.Config | None = None,
    leading_newline: bool = False,
) -> None:
    prefix = "\n" if leading_newline else ""
    capture_manager = (
        (config or _PYTEST_CONFIG).pluginmanager.get_plugin("capturemanager")
        if (config or _PYTEST_CONFIG) is not None
        else None
    )
    if capture_manager is None:
        sys.__stdout__.write(f"{prefix}{message}\n")
        sys.__stdout__.flush()
        return

    capture_manager.suspend_global_capture(in_=False)
    try:
        sys.__stdout__.write(f"{prefix}{message}\n")
        sys.__stdout__.flush()
    finally:
        capture_manager.resume_global_capture()


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("live_llm") is None:
        return

    _write_live_line(
        f"[live_llm] starting {item.nodeid}",
        config=item.config,
        leading_newline=True,
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call" or "live_llm" not in report.keywords:
        return

    _write_live_line(
        f"[live_llm] {report.outcome} {report.nodeid} ({report.duration:.1f}s)",
        leading_newline=True,
    )
