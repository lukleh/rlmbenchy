"""Shared parsing helpers for workload options."""

from __future__ import annotations

from typing import Any


def parse_option_args(option_args: list[str]) -> dict[str, str]:
    """Parse a list of ``key=value`` strings into a dict."""

    parsed: dict[str, str] = {}
    for item in option_args:
        if "=" not in item:
            raise ValueError(f"Expected option in key=value form, got: {item!r}")
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def build_workload_options(
    *,
    option_args: list[str],
    explicit_options: dict[str, Any],
) -> dict[str, Any]:
    options: dict[str, Any] = dict(parse_option_args(option_args))
    for key, value in explicit_options.items():
        if value is not None:
            options[str(key)] = value
    return options


__all__ = ["build_workload_options", "parse_option_args"]
