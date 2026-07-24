"""S-NIAH synthetic task helpers shared by the workload and local entrypoints."""

import random
from typing import Any

from rlmbenchy.datahub.workloads.support.task_selection import canonical_task_id

DEFAULT_SEED = 1
DEFAULT_HAYSTACK_LINES = 120
DEFAULT_NEEDLE_KEY = "account_id"


def build_s_niah_synthetic_task(
    *,
    seed: int = DEFAULT_SEED,
    haystack_lines: int = DEFAULT_HAYSTACK_LINES,
    needle_key: str = DEFAULT_NEEDLE_KEY,
) -> dict[str, Any]:
    if haystack_lines < 8:
        raise ValueError("haystack_lines must be >= 8.")
    rng = random.Random(seed)
    needle_position = rng.randint(3, haystack_lines - 3)
    needle_value = f"{rng.randint(10_000, 99_999)}"

    lines: list[str] = []
    for index in range(haystack_lines):
        if index == needle_position:
            lines.append(f"record_{index:04d}: {needle_key}={needle_value}")
        else:
            fake_a = rng.randint(100, 999)
            fake_b = rng.randint(100, 999)
            lines.append(f"record_{index:04d}: token_a={fake_a}; token_b={fake_b}")

    return {
        "task_id": canonical_task_id(
            "s_niah",
            "synthetic",
            f"seed_{seed}",
            f"lines_{haystack_lines}",
            needle_key,
        ),
        "category": "s_niah_synthetic",
        "query": f"What is the value of {needle_key}? Return only the value.",
        "context": "\n".join(lines),
        "expected": {"kind": "exact", "value": needle_value},
        "dataset_meta": {
            "source": "s_niah_synthetic",
            "seed": seed,
            "haystack_lines": haystack_lines,
            "needle_position": needle_position,
            "needle_key": needle_key,
        },
    }


__all__ = [
    "DEFAULT_HAYSTACK_LINES",
    "DEFAULT_NEEDLE_KEY",
    "DEFAULT_SEED",
    "build_s_niah_synthetic_task",
]
