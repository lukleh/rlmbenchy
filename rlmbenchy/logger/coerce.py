"""Small scalar coercion helpers for logger read/write paths."""

from __future__ import annotations

from typing import Any


def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def coerce_int_or(value: Any, default: int = 0) -> int:
    coerced = coerce_int(value)
    return default if coerced is None else coerced


def coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


__all__ = ["coerce_float", "coerce_int", "coerce_int_or"]
