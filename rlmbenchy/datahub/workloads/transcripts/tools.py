"""Tool builders for the transcripts workload."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import dspy

from rlmbenchy.datahub.workloads.support.active_task import active_task_id


def _read_segments(transcript_path: Path) -> list[str]:
    segments: list[str] = []
    with transcript_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            segment = line.strip()
            if not segment:
                continue
            segments.append(segment)
    return segments


def _normalize_hash_ids(hash_ids: Sequence[str]) -> list[str]:
    return [str(hash_id).strip() for hash_id in hash_ids if str(hash_id).strip()]


def build_tools(
    transcript_paths_by_hash: Mapping[str, Path | str],
    *,
    hash_ids_by_task_id: Mapping[str, Sequence[str]] | None = None,
) -> list[dspy.Tool]:
    """Build transcript access tools over selected transcript files.

    ``hash_ids_by_task_id`` restricts which transcripts each task can see.
    When ``None`` every task sees all transcripts. Routing relies on the
    active-task context variable set by the runner around each task.
    """

    transcript_index: dict[str, Path] = {
        str(hash_id).strip(): Path(transcript_path)
        for hash_id, transcript_path in transcript_paths_by_hash.items()
    }
    segments_by_hash: dict[str, list[str]] = {}
    combined_segments_cache_by_scope: dict[tuple[str, ...], list[tuple[str, str]]] = {}

    task_allowed_hash_ids: dict[str, list[str]] = {}
    if hash_ids_by_task_id is not None:
        for task_id, hash_ids in hash_ids_by_task_id.items():
            task_allowed_hash_ids[str(task_id)] = list(_normalize_hash_ids(hash_ids))

    def _segments_for_hash(hash_id: str) -> list[str]:
        hash_normalized = str(hash_id).strip()
        if hash_normalized not in segments_by_hash:
            segments_by_hash[hash_normalized] = _read_segments(
                transcript_index[hash_normalized]
            )
        return segments_by_hash[hash_normalized]

    def _allowed_hash_ids() -> list[str]:
        if hash_ids_by_task_id is None:
            return sorted(transcript_index)
        task_id = active_task_id() or ""
        allowed = set(task_allowed_hash_ids.get(task_id, []))
        return [hash_id for hash_id in sorted(transcript_index) if hash_id in allowed]

    def _combined_segments(allowed_hash_ids: Sequence[str]) -> list[tuple[str, str]]:
        cache_key = tuple(allowed_hash_ids)
        if cache_key in combined_segments_cache_by_scope:
            return combined_segments_cache_by_scope[cache_key]
        merged: list[tuple[str, str]] = []
        for hash_id in allowed_hash_ids:
            for segment in _segments_for_hash(hash_id):
                merged.append((hash_id, segment))
        combined_segments_cache_by_scope[cache_key] = merged
        return merged

    def list_transcripts() -> list[dict[str, str | int]]:
        return [
            {"hash_id": hash_id, "segment_count": len(_segments_for_hash(hash_id))}
            for hash_id in _allowed_hash_ids()
        ]

    def get_segments(hash_id: str) -> list[str]:
        hash_normalized = str(hash_id).strip()
        if hash_normalized not in transcript_index or hash_normalized not in set(
            _allowed_hash_ids()
        ):
            raise KeyError(hash_normalized)
        return list(_segments_for_hash(hash_normalized))

    def segment_count() -> int:
        return len(_combined_segments(_allowed_hash_ids()))

    def get_segment(position: int) -> str:
        position_i = int(position)
        if position_i <= 0:
            return ""
        combined = _combined_segments(_allowed_hash_ids())
        if position_i > len(combined):
            return ""
        hash_id, segment = combined[position_i - 1]
        return f"[{hash_id}] {segment}"

    return [
        dspy.Tool(
            segment_count,
            name="segment_count",
            desc=(
                "Return total number of merged segments across all selected transcripts. "
                "Use this to determine valid 1-based positions for get_segment (1..count)."
            ),
        ),
        dspy.Tool(
            get_segment,
            name="get_segment",
            desc=(
                "Return one merged segment by 1-based position. "
                "Output format: '[<hash_id>] <segment_text>'. Returns empty string when out of range."
            ),
        ),
        dspy.Tool(
            list_transcripts,
            name="list_transcripts",
            desc=(
                "Return metadata for selected transcripts as list[dict] sorted by hash_id. "
                "Each row contains keys: hash_id (str) and segment_count (int)."
            ),
        ),
        dspy.Tool(
            get_segments,
            name="get_segments",
            desc=(
                "Return all segments for one transcript hash_id as ordered list[str]. "
                "Use hash_id values returned by list_transcripts."
            ),
        ),
    ]
