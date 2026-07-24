"""Transcript workload loader with predefined local task definitions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import dspy

from rlmbenchy.datahub.workloads.transcripts.tools import build_tools
from rlmbenchy.datahub.types import WorkloadBundle, WorkloadTask
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
)
from rlmbenchy.runtime_config import (
    default_transcripts_root,
    default_transcripts_tasks_path,
    load_transcripts_config,
    resolve_path,
    transcripts_config_file,
)

WORKLOAD_NAME = "transcripts"

HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class TranscriptsSignature(dspy.Signature):
    """Answer the question about the selected transcripts.
    Use list_transcripts, get_segments, get_segment, and segment_count tools to access transcript data."""

    question: str = dspy.InputField(
        desc="The question or task to perform over the transcripts."
    )
    transcripts_count: int = dspy.InputField(
        desc="Number of selected transcript files."
    )
    answer: str = dspy.OutputField(desc="The answer to the question.")


def _configured_workload_values() -> tuple[str | None, str | None]:
    payload = load_transcripts_config()
    configured_root = str(payload.get("root") or "").strip() or None
    configured_tasks_path = str(payload.get("tasks_path") or "").strip() or None
    return configured_root, configured_tasks_path


def _resolve_root(options: dict[str, Any]) -> Path:
    root_raw = options.get("root")
    if root_raw is not None:
        if not isinstance(root_raw, str):
            raise SystemExit("transcripts option `root` must be a string path.")
        root_path = resolve_path(root_raw.strip(), Path.cwd())
    else:
        configured_root, _ = _configured_workload_values()
        if configured_root:
            root_path = Path(configured_root).expanduser().resolve()
        else:
            root_path = default_transcripts_root().resolve()

    if not root_path.exists():
        raise SystemExit(
            "Transcript root does not exist: "
            f"{root_path}. Pass root=, configure `root` in {transcripts_config_file()}, "
            "or populate the default share path."
        )
    return root_path


def _resolve_tasks_path(options: dict[str, Any]) -> Path:
    tasks_path_raw = options.get("tasks_path")
    if tasks_path_raw is not None:
        tasks_path = resolve_path(str(tasks_path_raw), Path.cwd())
    else:
        _, configured_tasks_path = _configured_workload_values()
        if configured_tasks_path:
            tasks_path = Path(configured_tasks_path).expanduser().resolve()
        else:
            tasks_path = default_transcripts_tasks_path().resolve()

    if not tasks_path.exists() or not tasks_path.is_file():
        raise RuntimeError(
            "Tasks file does not exist: "
            f"{tasks_path}. Pass tasks_path=, configure `tasks_path` in {transcripts_config_file()}, "
            "or populate the default share path."
        )
    return tasks_path


def _extract_query(row: dict[str, Any], index: int) -> str:
    query_raw = row.get("query")
    if isinstance(query_raw, str) and query_raw.strip():
        return query_raw.strip()
    raise RuntimeError(f"Transcript task at row {index + 1} is missing `query`.")


def _load_task_rows(tasks_path: Path) -> list[dict[str, Any]]:
    rows = json.loads(tasks_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError(f"Expected list of tasks in {tasks_path}")

    task_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        typed_row = cast(dict[str, Any], row)
        _validate_task_row_shape(typed_row, index=index)
        task_id = str(
            typed_row.get("id") or f"transcripts_task_{index + 1:03d}"
        ).strip()
        query = _extract_query(typed_row, index)
        selector = _extract_selector(typed_row, index=index)
        raw_metadata: Any = typed_row.get("metadata")
        metadata = dict(raw_metadata or {})

        task_rows.append(
            {
                "id": task_id,
                "query": query,
                "selector": selector,
                "answer": typed_row.get("answer"),
                "metadata": metadata,
                "row_index": index,
            }
        )

    return task_rows


def _has_any_segment(transcript_path: Path) -> bool:
    with transcript_path.open("r", encoding="utf-8", errors="replace") as handle:
        return any(line.strip() for line in handle)


def _index_transcript_files(root: Path) -> dict[str, Path]:
    hash_dirs = sorted(
        path for path in root.iterdir() if path.is_dir() and HASH_RE.match(path.name)
    )
    result: dict[str, Path] = {}
    for hash_dir in hash_dirs:
        transcript_path = hash_dir / "transcript.txt"
        if not transcript_path.is_file():
            continue
        if not _has_any_segment(transcript_path):
            continue
        result[hash_dir.name] = transcript_path
    return result


def _coerce_hash_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError("Transcript selector HASH_IDS must use a list `value`.")
    hash_ids = [str(item).strip() for item in value if str(item).strip()]
    if not hash_ids:
        raise RuntimeError(
            "Transcript selector HASH_IDS must include at least one hash id."
        )
    return hash_ids


def _extract_selector(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    data = row.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Transcript task at row {index + 1} is missing `data.selector`."
        )
    if set(data) != {"selector"}:
        raise RuntimeError(
            f"Transcript task at row {index + 1} only supports `data.selector`."
        )
    selector = data.get("selector")
    if not isinstance(selector, dict):
        raise RuntimeError(
            f"Transcript task at row {index + 1} is missing `data.selector`."
        )
    return _normalize_selector(selector)


def _normalize_selector(value: dict[str, Any]) -> dict[str, Any]:
    mode = str(value.get("mode") or "").strip().upper()
    if mode == "ALL":
        if value.get("value") != "ALL":
            raise RuntimeError('Transcript selector ALL must use `value = "ALL"`.')
        return {"mode": "ALL", "value": "ALL"}
    if mode == "FILE_COUNT":
        count = value.get("value")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise RuntimeError(
                "Transcript selector FILE_COUNT must use an integer `value >= 0`."
            )
        return {"mode": "FILE_COUNT", "value": count}
    if mode == "HASH_IDS":
        return {"mode": "HASH_IDS", "value": _coerce_hash_ids(value.get("value"))}
    raise RuntimeError(f"Unsupported transcript selector mode: {mode or '<missing>'}")


def _select_hash_ids_for_selector(
    selector: dict[str, Any],
    available_paths_by_hash: dict[str, Path],
) -> list[str]:
    available_hash_ids = sorted(available_paths_by_hash)
    mode = str(selector.get("mode") or "").upper()

    if mode == "ALL":
        return available_hash_ids

    if mode == "FILE_COUNT":
        count = int(selector.get("value", 0))
        if count < 0:
            raise RuntimeError("Transcript selector FILE_COUNT must be >= 0")
        return available_hash_ids[:count]

    if mode == "HASH_IDS":
        hash_ids = _coerce_hash_ids(selector.get("value"))
        missing = [
            hash_id for hash_id in hash_ids if hash_id not in available_paths_by_hash
        ]
        if missing:
            raise RuntimeError(f"Unknown transcript hash_ids: {', '.join(missing)}")
        return hash_ids

    raise RuntimeError(f"Unsupported transcript selector mode: {mode}")


def _build_task_data_payload(
    *,
    selector: dict[str, Any],
    hash_ids: list[str],
) -> dict[str, Any]:
    return {
        "selector": dict(selector),
        "hash_ids": list(hash_ids),
        "transcripts_count": len(hash_ids),
    }


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load predefined transcript tasks and attach transcript tools."""

    root = _resolve_root(options)
    tasks_path = _resolve_tasks_path(options)

    task_rows = _load_task_rows(tasks_path)
    task_id_filter = normalize_task_id_filter(task_id) or ""
    if task_id_filter:
        task_rows = [row for row in task_rows if row["id"] == task_id_filter]
    if task_limit is not None and not task_id_filter:
        task_rows = task_rows[: max(0, int(task_limit))]

    all_paths_by_hash = _index_transcript_files(root)
    if not all_paths_by_hash:
        raise RuntimeError(f"No transcript files were found under: {root}")

    tasks: list[WorkloadTask] = []
    union_hash_ids: set[str] = set()

    for index, row in enumerate(task_rows):
        selector = dict(row["selector"])
        selected_hash_ids = _select_hash_ids_for_selector(selector, all_paths_by_hash)
        if not selected_hash_ids:
            raise RuntimeError(
                f"Task `{row['id']}` resolved to zero transcripts with selector {selector}."
            )

        union_hash_ids.update(selected_hash_ids)
        task_data = _build_task_data_payload(
            selector=selector,
            hash_ids=selected_hash_ids,
        )

        task_metadata = dict(row.get("metadata") or {})
        task_metadata.update(
            {
                "tasks_path": str(tasks_path),
                "row_index": int(row.get("row_index", index)),
            }
        )

        tasks.append(
            WorkloadTask(
                id=row["id"],
                inputs={
                    "question": row["query"],
                    "transcripts_count": len(selected_hash_ids),
                },
                answer=row.get("answer"),
                metadata={**task_metadata, "task_data": task_data},
            )
        )

    assert_unique_task_ids(tasks, scope="transcripts")

    selected_paths_by_hash = {
        hash_id: all_paths_by_hash[hash_id]
        for hash_id in sorted(union_hash_ids)
        if hash_id in all_paths_by_hash
    }

    hash_ids_by_task_id = {
        task.id: list(task.metadata["task_data"]["hash_ids"]) for task in tasks
    }

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(
            selected_paths_by_hash,
            hash_ids_by_task_id=hash_ids_by_task_id,
        ),
        signature=TranscriptsSignature,
        metadata={
            "source": "transcripts",
            "dataset": "transcripts",
            "root": str(root),
            "tasks_path": str(tasks_path),
            "task_limit": task_limit,
            "task_id_filter": task_id_filter or None,
            "loaded_tasks": len(tasks),
            "tools_hash_ids_count": len(selected_paths_by_hash),
            "tools_hash_ids": sorted(selected_paths_by_hash),
        },
    )


def _validate_task_row_shape(row: dict[str, Any], *, index: int) -> None:
    if "task_id" in row:
        raise RuntimeError(
            f"Transcript task at row {index + 1} uses unsupported `task_id`. Use `id`."
        )
    if "query_lines" in row:
        raise RuntimeError(
            f"Transcript task at row {index + 1} uses unsupported `query_lines`. "
            "Use `query`."
        )
    data = row.get("data")
    if not isinstance(data, dict):
        return
    for legacy_name in ("hash_ids", "file_count", "data_keyword", "keyword"):
        if legacy_name in data:
            raise RuntimeError(
                f"Transcript task at row {index + 1} uses unsupported `data.{legacy_name}`. "
                "Use `data.selector`."
            )
