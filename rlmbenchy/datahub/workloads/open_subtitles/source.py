"""OpenSubtitles source helpers shared by the workload and local entrypoints."""

import hashlib
import io
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from rlmbenchy.datahub.workloads.support.hf import coerce_expected
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_payload_ids,
    canonical_task_id,
    normalize_task_id_filter,
    task_id_matches,
)
from rlmbenchy.runtime_paths import resolve_runtime_paths

OPEN_SUBTITLES_DATASET_ID = "Helsinki-NLP/open_subtitles"
OPEN_SUBTITLES_BASE_URL = (
    "https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2018/moses/{config}.txt.zip"
)
DEFAULT_CONFIG = "en-hi"
DEFAULT_SPLIT = "train"


def _cache_dir() -> Path:
    return resolve_runtime_paths().cache_dir / "datahub" / "open_subtitles"


def _parse_open_subtitles_config(config: str) -> tuple[str, str]:
    value = str(config).strip().lower()
    if "-" not in value:
        raise ValueError(
            "OpenSubtitles config must look like '<lang1>-<lang2>' (for example: 'en-hi')."
        )
    lang1, lang2 = value.split("-", 1)
    if not lang1 or not lang2:
        raise ValueError(
            "OpenSubtitles config must include two language codes separated by '-'."
        )
    return lang1, lang2


def _parse_open_subtitles_ref(value: str) -> tuple[int | None, int | None, int | None]:
    text = str(value or "").strip()
    text = text.removesuffix(".xml.gz")
    parts = text.split("/")
    if len(parts) != 4:
        return None, None, None
    try:
        year = int(parts[1])
        imdb_id = int(parts[2])
        subtitle_id = int(parts[3])
    except ValueError:
        return None, None, None
    return year, imdb_id, subtitle_id


def _parse_open_subtitles_sentence_ids(value: str) -> list[int]:
    result: list[int] = []
    for token in str(value or "").split():
        try:
            result.append(int(token))
        except ValueError:
            continue
    return result


def _cached_zip_path(url: str, config: str) -> Path:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return _cache_dir() / f"{config}_{url_hash}.zip"


def _ensure_cached_zip(
    url: str,
    config: str,
    *,
    timeout_s: float,
    retries: int,
) -> Path:
    cached = _cached_zip_path(url, config)
    if cached.exists():
        return cached

    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cached.with_suffix(".tmp")

    download_error = "unknown"
    for attempt in range(max(1, retries)):
        request = urllib.request.Request(
            url, headers={"User-Agent": "datahub/dataset-adapters"}
        )
        try:
            with (
                urllib.request.urlopen(request, timeout=timeout_s) as response,
                open(tmp_path, "wb") as fout,
            ):
                shutil.copyfileobj(response, fout)
            tmp_path.rename(cached)
            return cached
        except urllib.error.HTTPError as exc:
            download_error = f"HTTP {exc.code}"
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Failed to download OpenSubtitles archive for config '{config}': {download_error}"
                ) from exc
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            download_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5 * (attempt + 1))

    tmp_path.unlink(missing_ok=True)
    raise RuntimeError(
        f"Failed to download OpenSubtitles archive for config '{config}': {download_error}"
    )


def _iter_open_subtitles_rows(
    *,
    config: str,
    max_rows: int | None,
    timeout_s: float,
    retries: int,
) -> Iterator[dict[str, Any]]:
    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows must be >= 0 or None.")
    if max_rows == 0:
        return
    lang1, lang2 = _parse_open_subtitles_config(config)
    base_name = f"OpenSubtitles.{lang1}-{lang2}"
    left_file = f"{base_name}.{lang1}"
    right_file = f"{base_name}.{lang2}"
    ids_file = f"{base_name}.ids"
    url = OPEN_SUBTITLES_BASE_URL.format(config=f"{lang1}-{lang2}")

    cached = _ensure_cached_zip(url, config, timeout_s=timeout_s, retries=retries)

    emitted_rows = 0
    try:
        with (
            zipfile.ZipFile(cached) as archive,
            archive.open(left_file) as raw_left,
            archive.open(right_file) as raw_right,
            archive.open(ids_file) as raw_ids,
            io.TextIOWrapper(raw_left, encoding="utf-8", errors="replace") as left_rows,
            io.TextIOWrapper(
                raw_right, encoding="utf-8", errors="replace"
            ) as right_rows,
            io.TextIOWrapper(raw_ids, encoding="utf-8", errors="replace") as id_rows,
        ):
            for line_index, (left, right, ids) in enumerate(
                zip(left_rows, right_rows, id_rows)
            ):
                if max_rows is not None and emitted_rows >= max_rows:
                    break
                left_text = left.strip()
                right_text = right.strip()
                if not left_text or not right_text:
                    continue

                cols = ids.strip().split("\t")
                left_ref = cols[0] if len(cols) > 0 else ""
                right_ref = cols[1] if len(cols) > 1 else ""
                left_sentence_ids = (
                    _parse_open_subtitles_sentence_ids(cols[2]) if len(cols) > 2 else []
                )
                right_sentence_ids = (
                    _parse_open_subtitles_sentence_ids(cols[3]) if len(cols) > 3 else []
                )
                left_year, left_imdb, left_subtitle_id = _parse_open_subtitles_ref(
                    left_ref
                )
                right_year, right_imdb, right_subtitle_id = _parse_open_subtitles_ref(
                    right_ref
                )
                year = left_year if left_year is not None else right_year
                imdb_id = left_imdb if left_imdb is not None else right_imdb

                emitted_rows += 1
                yield {
                    "id": str(line_index),
                    "meta": {
                        "year": year,
                        "imdbId": imdb_id,
                        "subtitleId": {
                            lang1: left_subtitle_id,
                            lang2: right_subtitle_id,
                        },
                        "sentenceIds": {
                            lang1: left_sentence_ids,
                            lang2: right_sentence_ids,
                        },
                    },
                    "translation": {
                        lang1: left_text,
                        lang2: right_text,
                    },
                }
    except KeyError as exc:
        raise RuntimeError(
            "OpenSubtitles archive layout was not recognized for "
            f"config '{config}'. Expected files: {left_file}, {right_file}, {ids_file}."
        ) from exc


def _load_open_subtitles_rows(
    *,
    config: str,
    max_rows: int | None,
    timeout_s: float,
    retries: int,
) -> list[dict[str, Any]]:
    return list(
        _iter_open_subtitles_rows(
            config=config,
            max_rows=max_rows,
            timeout_s=timeout_s,
            retries=retries,
        )
    )


def task_id_for_row(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
    direction: str,
) -> str:
    source_id = str(row.get("id") or "").strip()
    parts = [
        "open_subtitles",
        config,
        split,
        direction,
        f"row_{index:05d}",
    ]
    if source_id:
        parts.append(source_id)
    return canonical_task_id(*parts)


def open_subtitles_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str,
    split: str,
    direction: str = "forward",
    score_kind: str = "exact",
) -> dict[str, Any] | None:
    lang1, lang2 = _parse_open_subtitles_config(config)
    resolved_direction = str(direction).strip().lower()
    if resolved_direction not in {"forward", "reverse"}:
        raise ValueError("direction must be either 'forward' or 'reverse'.")

    translation = row.get("translation")
    if not isinstance(translation, dict):
        return None

    source_lang, target_lang = (lang1, lang2)
    if resolved_direction == "reverse":
        source_lang, target_lang = (lang2, lang1)

    source_text = str(translation.get(source_lang) or "").strip()
    target_text = str(translation.get(target_lang) or "").strip()
    if not source_text or not target_text:
        return None

    task_id = task_id_for_row(
        row,
        index=index,
        config=config,
        split=split,
        direction=resolved_direction,
    )
    source_id = str(row.get("id") or "").strip() or None
    raw_meta = row.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    year = meta.get("year")
    imdb_id = meta.get("imdbId")
    context_lines = [
        "Domain: movie/TV subtitles",
        f"Source language: {source_lang}",
        f"Target language: {target_lang}",
    ]
    if isinstance(year, int):
        context_lines.append(f"Year: {year}")
    if isinstance(imdb_id, int):
        context_lines.append(f"IMDb ID: {imdb_id}")

    query = (
        f"Translate the subtitle text from {source_lang} to {target_lang}. "
        "Return only the translated text.\n\n"
        f"{source_text}"
    )
    return {
        "task_id": task_id,
        "category": "open_subtitles",
        "query": query,
        "context": "\n".join(context_lines),
        "expected": coerce_expected(target_text, score_kind),
        "dataset_meta": {
            "source": "open_subtitles",
            "dataset_id": OPEN_SUBTITLES_DATASET_ID,
            "config": config,
            "split": split,
            "row_index": index,
            "source_id": source_id,
            "direction": resolved_direction,
            "source_lang": source_lang,
            "target_lang": target_lang,
        },
    }


def iter_open_subtitles_tasks(
    *,
    dataset_id: str = OPEN_SUBTITLES_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    direction: str = "forward",
    score_kind: str = "exact",
    max_rows: int | None = 50,
    timeout_s: float = 60.0,
    retries: int = 3,
    task_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    if str(dataset_id).strip() != OPEN_SUBTITLES_DATASET_ID:
        raise ValueError(
            "OpenSubtitles adapter currently supports dataset_id='Helsinki-NLP/open_subtitles' only."
        )
    resolved_split = str(split).strip().lower()
    if resolved_split != DEFAULT_SPLIT:
        raise ValueError("OpenSubtitles adapter currently supports split='train' only.")
    task_id_filter = normalize_task_id_filter(task_id)
    rows = _iter_open_subtitles_rows(
        config=config,
        max_rows=None if task_id_filter else max_rows,
        timeout_s=timeout_s,
        retries=retries,
    )
    for index, row in enumerate(rows):
        resolved_direction = str(direction).strip().lower()
        raw_task_id = task_id_for_row(
            row,
            index=index,
            config=config,
            split=resolved_split,
            direction=resolved_direction,
        )
        if not task_id_matches(raw_task_id, task_id_filter):
            continue
        task = open_subtitles_row_to_task(
            row,
            index=index,
            config=config,
            split=resolved_split,
            direction=direction,
            score_kind=score_kind,
        )
        if task is not None:
            yield task
            if task_id_filter:
                break


def load_open_subtitles_tasks(
    *,
    dataset_id: str = OPEN_SUBTITLES_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    direction: str = "forward",
    score_kind: str = "exact",
    max_rows: int | None = 50,
    timeout_s: float = 60.0,
    retries: int = 3,
) -> list[dict[str, Any]]:
    tasks = list(
        iter_open_subtitles_tasks(
            dataset_id=dataset_id,
            config=config,
            split=split,
            direction=direction,
            score_kind=score_kind,
            max_rows=max_rows,
            timeout_s=timeout_s,
            retries=retries,
        )
    )
    if not tasks:
        raise RuntimeError("No OpenSubtitles tasks were loaded.")
    assert_unique_task_payload_ids(tasks, scope="open_subtitles")
    return tasks
