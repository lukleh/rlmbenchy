"""OpenSubtitles workload loader with tool-based source text access."""

from typing import Any

import dspy

from rlmbenchy.datahub.workloads.support.task_filters import (
    apply_task_filters,
    filter_payload_by_tasks,
)
from rlmbenchy.datahub.workloads.support.task_selection import (
    assert_unique_task_ids,
    normalize_task_id_filter,
    put_unique_payload,
)
from rlmbenchy.datahub.workloads.open_subtitles.source import (
    DEFAULT_CONFIG,
    DEFAULT_SPLIT,
    _parse_open_subtitles_config,
    iter_open_subtitles_tasks,
)
from rlmbenchy.datahub.workloads.open_subtitles.tools import build_tools
from rlmbenchy.datahub.types import (
    WorkloadBundle,
    WorkloadTask,
)

WORKLOAD_NAME = "open_subtitles"


class OpenSubtitlesSignature(dspy.Signature):
    """Translate the subtitle text between languages.
    Use subtitles_get_source_text(task_id) to retrieve the source text to translate."""

    task_id: str = dspy.InputField(
        desc="Task identifier for subtitles_get_source_text tool."
    )
    source_lang: str = dspy.InputField(desc="Source language code.")
    target_lang: str = dspy.InputField(desc="Target language code.")
    answer: str = dspy.OutputField(desc="The translated text.")


def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle:
    """Load OpenSubtitles tasks with source text behind a tool."""

    config = str(options.get("config", DEFAULT_CONFIG)).strip()
    split = str(options.get("split", DEFAULT_SPLIT)).strip()
    direction = str(options.get("direction", "forward")).strip().lower()
    score_kind = str(options.get("score_kind", "exact")).strip()
    task_id_filter = normalize_task_id_filter(task_id)
    max_rows = options.get("max_rows", 50)
    if max_rows is not None:
        max_rows = int(max_rows)
    timeout_s = float(options.get("timeout_s", 60.0))
    retries = int(options.get("retries", 3))

    if direction not in {"forward", "reverse"}:
        raise ValueError("direction must be either 'forward' or 'reverse'.")

    lang1, lang2 = _parse_open_subtitles_config(config)
    source_lang, target_lang = (lang1, lang2)
    if direction == "reverse":
        source_lang, target_lang = (lang2, lang1)

    task_payloads = iter_open_subtitles_tasks(
        config=config,
        split=split,
        direction=direction,
        score_kind=score_kind,
        max_rows=max_rows,
        timeout_s=timeout_s,
        retries=retries,
        task_id=task_id_filter,
    )

    tasks: list[WorkloadTask] = []
    source_text_by_task_id: dict[str, str] = {}

    for task_payload in task_payloads:
        raw_id = str(task_payload["task_id"])
        query = str(task_payload["query"])
        source_text = query.split("\n\n", 1)[1] if "\n\n" in query else query
        metadata = task_payload.get("dataset_meta")
        put_unique_payload(
            source_text_by_task_id,
            raw_id,
            source_text,
            scope="open_subtitles",
        )

        tasks.append(
            WorkloadTask(
                id=raw_id,
                inputs={
                    "task_id": raw_id,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                },
                answer=task_payload.get("expected"),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        )

    if not tasks and task_id_filter is None:
        raise RuntimeError("No OpenSubtitles tasks were loaded.")

    tasks = apply_task_filters(tasks, task_id=task_id_filter, task_limit=task_limit)
    assert_unique_task_ids(tasks, scope="open_subtitles")
    source_text_by_task_id = filter_payload_by_tasks(source_text_by_task_id, tasks)

    return WorkloadBundle(
        workload_name=WORKLOAD_NAME,
        tasks=tasks,
        tools=build_tools(source_text_by_task_id),
        signature=OpenSubtitlesSignature,
        metadata={
            "source": "opus_archive",
            "config": config,
            "split": split,
            "direction": direction,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "loaded_tasks": len(tasks),
            "task_limit": task_limit,
            "task_id_filter": task_id_filter,
        },
    )
