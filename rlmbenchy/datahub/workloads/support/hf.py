"""Shared dataset/network helpers for DataHub sources."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from itertools import islice
from typing import Any

from rlmbenchy.runtime_config import resolve_huggingface_token

HF_API_BASE = "https://huggingface.co/api/datasets"
HF_DATASETS_SERVER_BASE = "https://datasets-server.huggingface.co"


def headers(token: str | None = None) -> dict[str, str]:
    hdrs: dict[str, str] = {"User-Agent": "datahub/dataset-adapters"}
    auth = str(resolve_huggingface_token(token) or "").strip()
    if auth:
        hdrs["Authorization"] = f"Bearer {auth}"
    return hdrs


def get_json(
    url: str,
    *,
    token: str | None = None,
    timeout_s: float = 30.0,
    retries: int = 3,
) -> tuple[int, Any]:
    last_status = 0
    last_payload: Any = {"error": "unknown"}
    for attempt in range(max(1, retries)):
        request = urllib.request.Request(url, headers=headers(token))
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                status = response.getcode()
                raw = response.read().decode("utf-8", errors="replace")
                return status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_status = int(exc.code)
            body = exc.read().decode("utf-8", errors="replace")
            try:
                last_payload = json.loads(body)
            except json.JSONDecodeError:
                last_payload = {"error": body[:400]}
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                return last_status, last_payload
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            last_status = 0
            last_payload = {"error": f"{type(exc).__name__}: {exc}"}
        time.sleep(0.5 * (attempt + 1))
    return last_status, last_payload


def rows_url(
    *,
    dataset_id: str,
    config: str,
    split: str,
    offset: int,
    length: int,
) -> str:
    query = urllib.parse.urlencode(
        {
            "dataset": dataset_id,
            "config": config,
            "split": split,
            "offset": str(offset),
            "length": str(length),
        }
    )
    return f"{HF_DATASETS_SERVER_BASE}/rows?{query}"


def dataset_info(dataset_id: str, *, token: str | None = None) -> tuple[int, Any]:
    return get_json(f"{HF_API_BASE}/{dataset_id}", token=token)


def datasets_server_splits(
    dataset_id: str,
    *,
    token: str | None = None,
) -> tuple[int, Any]:
    query = urllib.parse.urlencode({"dataset": dataset_id})
    return get_json(f"{HF_DATASETS_SERVER_BASE}/splits?{query}", token=token)


def datasets_server_rows(
    dataset_id: str,
    *,
    config: str,
    split: str,
    offset: int = 0,
    length: int = 3,
    token: str | None = None,
) -> tuple[int, Any]:
    return get_json(
        rows_url(
            dataset_id=dataset_id,
            config=config,
            split=split,
            offset=offset,
            length=length,
        ),
        token=token,
    )


def coerce_expected(answer: str, score_kind: str) -> dict[str, Any]:
    kind = str(score_kind).strip().lower()
    if kind == "contains":
        return {"kind": "contains", "value": answer}
    return {"kind": "exact", "value": answer}


def load_rows(
    *,
    dataset_id: str,
    config: str,
    split: str,
    max_rows: int | None,
    token: str | None = None,
) -> list[dict[str, Any]]:
    return list(
        iter_rows(
            dataset_id=dataset_id,
            config=config,
            split=split,
            max_rows=max_rows,
            token=token,
        )
    )


def iter_rows(
    *,
    dataset_id: str,
    config: str,
    split: str,
    max_rows: int | None,
    token: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Iterate dataset rows, caching the full split on disk.

    Uses ``streaming=False`` so that ``datasets`` writes the split's Arrow
    files into ``~/.cache/huggingface/datasets/`` on first access. Subsequent
    calls are disk-bound and support offline use. ``max_rows`` still caps the
    number of rows yielded (applied via ``islice`` after load).
    """

    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows must be >= 0 or None.")
    if max_rows == 0:
        return

    from datasets import load_dataset

    auth = resolve_huggingface_token(token)
    ds = load_dataset(
        dataset_id,
        config,
        split=split,
        token=auth,
        streaming=False,
    )

    rows_iter = islice(ds, max_rows) if max_rows is not None else ds
    for row in rows_iter:
        yield dict(row)


__all__ = [
    "HF_API_BASE",
    "HF_DATASETS_SERVER_BASE",
    "coerce_expected",
    "dataset_info",
    "datasets_server_rows",
    "datasets_server_splits",
    "get_json",
    "headers",
    "iter_rows",
    "load_rows",
    "rows_url",
]
