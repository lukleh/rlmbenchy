"""transcripts source helpers shared by the workload-local entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rlmbenchy.datahub.workloads.transcripts import load_workload


def _read_segments(transcript_path: Path) -> list[str]:
    with transcript_path.open("r", encoding="utf-8", errors="replace") as handle:
        return [line.strip() for line in handle if line.strip()]


def _build_context(root: Path, hash_ids: list[str]) -> str:
    blocks: list[str] = []
    for hash_id in hash_ids:
        transcript_path = root / hash_id / "transcript.txt"
        segments = _read_segments(transcript_path)
        if not segments:
            continue
        blocks.append(f"[{hash_id}]\n" + "\n".join(segments))
    return "\n\n".join(blocks).strip()


def load_transcripts_tasks(
    *,
    root: str | None = None,
    tasks_path: str | None = None,
    task_id: str | None = None,
    max_rows: int | None = 1,
) -> list[dict[str, Any]]:
    options: dict[str, Any] = {}
    if root is not None:
        options["root"] = root
    if tasks_path is not None:
        options["tasks_path"] = tasks_path

    bundle = load_workload(task_limit=max_rows, task_id=task_id, options=options)
    root_path = Path(str(bundle.metadata["root"])).expanduser().resolve()
    tasks_path_value = str(bundle.metadata["tasks_path"])

    tasks: list[dict[str, Any]] = []
    for index, task in enumerate(bundle.tasks):
        task_data = (
            task.metadata.get("task_data", {})
            if isinstance(task.metadata, dict)
            else {}
        )
        hash_ids = [str(value) for value in task_data.get("hash_ids", [])]
        tasks.append(
            {
                "task_id": str(task.id),
                "category": "transcripts",
                "query": str(task.inputs.get("question") or ""),
                "context": _build_context(root_path, hash_ids),
                "expected": task.answer,
                "dataset_meta": {
                    "source": "transcripts",
                    "root": str(root_path),
                    "tasks_path": tasks_path_value,
                    "row_index": index,
                    "hash_ids": hash_ids,
                    "transcripts_count": len(hash_ids),
                },
            }
        )

    if not tasks:
        raise RuntimeError("No transcripts tasks were loaded.")
    return tasks


__all__ = ["load_transcripts_tasks"]
