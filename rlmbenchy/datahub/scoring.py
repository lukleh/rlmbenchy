"""Answer scoring utilities for RLM task evaluation."""

from __future__ import annotations

import re
from typing import Any

_PAIR_PATTERN = re.compile(r"\(\s*([^,\s()]+)\s*,\s*([^,\s()]+)\s*\)")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _extract_first_number(text: str) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text or "")
    if match is None:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _normalize_pair(a: str, b: str) -> tuple[str, str]:
    first, second = sorted((_normalize_text(a), _normalize_text(b)))
    return first, second


def _parse_expected_pairs(values: Any) -> set[tuple[str, str]] | None:
    if not isinstance(values, list):
        return None
    parsed: set[tuple[str, str]] = set()
    for item in values:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            parsed.add(_normalize_pair(str(item[0]), str(item[1])))
            continue
        if isinstance(item, str) and "," in item:
            left, right = item.split(",", 1)
            parsed.add(_normalize_pair(left, right))
            continue
        return None
    return parsed


def _parse_observed_pairs(answer_text: str) -> set[tuple[str, str]]:
    parsed: set[tuple[str, str]] = set()
    for match in _PAIR_PATTERN.finditer(answer_text):
        parsed.add(_normalize_pair(match.group(1), match.group(2)))
    if parsed:
        return parsed

    for raw_line in answer_text.splitlines():
        line = raw_line.strip().strip("()")
        if not line or "," not in line:
            continue
        left, right = line.split(",", 1)
        parsed.add(_normalize_pair(left, right))
    return parsed


def _one_of_values(expected: dict[str, Any]) -> list[Any] | None:
    values = expected.get("values")
    if isinstance(values, list):
        return values
    options = expected.get("options")
    if isinstance(options, list):
        return options
    return None


def score_answer(
    answer: str | None, expected: dict[str, Any] | None
) -> tuple[float, bool, str]:
    """Score an answer against an expected specification.

    Returns (score_0_to_100, is_correct, detail_string).
    """
    if expected is None:
        return 0.0, False, "no_expected"

    kind = str(expected.get("kind") or "").strip().lower()
    answer_text = str(answer or "")

    if kind == "numeric":
        target = float(expected["value"])
        tolerance = float(expected["tolerance"]) if "tolerance" in expected else 0.0
        parsed = _extract_first_number(answer_text)
        if parsed is None:
            return 0.0, False, "no_numeric_value"
        ok = abs(parsed - target) <= tolerance
        return (
            (100.0 if ok else 0.0),
            ok,
            f"parsed={parsed}, target={target}, tolerance={tolerance}",
        )

    if kind == "exact":
        observed = _normalize_text(answer_text)
        target = _normalize_text(str(expected.get("value") or ""))
        ok = observed == target
        return (100.0 if ok else 0.0), ok, f"observed={observed!r}, target={target!r}"

    if kind == "contains":
        observed = _normalize_text(answer_text)
        target = _normalize_text(str(expected.get("value") or ""))
        ok = target in observed
        return (
            (100.0 if ok else 0.0),
            ok,
            f"observed={observed!r}, target_substring={target!r}",
        )

    if kind == "one_of":
        options_raw = _one_of_values(expected)
        if not isinstance(options_raw, list):
            return 0.0, False, "values_or_options_missing"
        options = {_normalize_text(str(item)) for item in options_raw}
        observed = _normalize_text(answer_text)
        ok = observed in options
        return (
            (100.0 if ok else 0.0),
            ok,
            f"observed={observed!r}, options={sorted(options)!r}",
        )

    if kind == "set_match":
        expected_pairs = _parse_expected_pairs(expected.get("values"))
        if expected_pairs is None:
            return 0.0, False, "values_missing_or_invalid"
        observed_pairs = _parse_observed_pairs(answer_text)
        ok = observed_pairs == expected_pairs
        if ok:
            return 100.0, True, f"pair_count={len(expected_pairs)}"
        missing = sorted(expected_pairs - observed_pairs)
        extra = sorted(observed_pairs - expected_pairs)
        detail = (
            f"missing={missing[:6]!r}, extra={extra[:6]!r}, "
            f"expected_count={len(expected_pairs)}, observed_count={len(observed_pairs)}"
        )
        return 0.0, False, detail

    return 0.0, False, f"unsupported_kind={kind!r}"
