"""BrowseComp-Plus source helpers shared by the workload and local entrypoints."""

from typing import Any

from rlmbenchy.datahub.workloads.support.hf import coerce_expected, load_rows
from rlmbenchy.datahub.workloads.support.task_selection import canonical_task_id

DEFAULT_DATASET_ID = "Tevatron/browsecomp-plus"
DEFAULT_CONFIG = "default"
DEFAULT_SPLIT = "test"


def _doc_to_text(doc: Any) -> str:
    if isinstance(doc, str):
        return doc.strip()
    if isinstance(doc, dict):
        title = str(doc.get("title") or "").strip()
        text = str(doc.get("text") or doc.get("contents") or "").strip()
        if title and text:
            return f"{title}\n{text}"
        if text:
            return text
        return title
    return str(doc).strip()


def collect_docs(row: dict[str, Any], *, max_docs: int | None = None) -> list[str]:
    docs_raw: list[Any] = []
    for field in ("gold_docs", "evidence_docs", "negative_docs"):
        values = row.get(field)
        if isinstance(values, list):
            docs_raw.extend(values)
    docs = [text for text in (_doc_to_text(item) for item in docs_raw) if text]
    if max_docs is not None and max_docs > 0:
        docs = docs[:max_docs]
    return docs


def extract_query_id(row: dict[str, Any], *, index: int) -> str:
    return str(row.get("query_id") or "").strip() or f"row_{index + 1:05d}"


def task_id_for_query_id(
    query_id: str,
    *,
    config: str,
    split: str,
    index: int,
) -> str:
    return canonical_task_id(
        "browsecomp_plus",
        config,
        split,
        f"row_{index:05d}",
        query_id,
    )


def extract_expected_answer(row: dict[str, Any]) -> Any | None:
    value = row.get("answer")
    if value is None or not str(value).strip():
        return None
    return value


def browsecomp_row_to_task(
    row: dict[str, Any],
    *,
    index: int,
    config: str = DEFAULT_CONFIG,
    split: str,
    max_docs: int | None = None,
    score_kind: str = "contains",
) -> dict[str, Any] | None:
    query = str(row.get("query") or "").strip()
    answer = extract_expected_answer(row)
    answer_text = str(answer).strip() if answer is not None else ""
    if not query or not answer:
        return None

    docs = collect_docs(row, max_docs=max_docs)
    context = "\n\n".join([f"[DOC {idx + 1}]\n{text}" for idx, text in enumerate(docs)])
    if not context:
        context = "No documents were available in this row."

    query_id = extract_query_id(row, index=index)
    return {
        "task_id": task_id_for_query_id(
            query_id,
            config=config,
            split=split,
            index=index,
        ),
        "category": "browsecomp_plus",
        "query": query,
        "context": context,
        "expected": coerce_expected(answer_text, score_kind),
        "dataset_meta": {
            "source": "browsecomp_plus",
            "config": config,
            "split": split,
            "row_index": index,
            "source_query_id": query_id,
            "doc_count": len(docs),
        },
    }


def load_browsecomp_plus_tasks(
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    config: str = DEFAULT_CONFIG,
    split: str = DEFAULT_SPLIT,
    score_kind: str = "contains",
    max_docs: int | None = None,
    max_rows: int | None = 20,
    token: str | None = None,
) -> list[dict[str, Any]]:
    rows = load_rows(
        dataset_id=dataset_id,
        config=config,
        split=split,
        max_rows=max_rows,
        token=token,
    )
    tasks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        task = browsecomp_row_to_task(
            row,
            index=index,
            config=config,
            split=split,
            max_docs=max_docs,
            score_kind=score_kind,
        )
        if task is not None:
            tasks.append(task)
    if not tasks:
        raise RuntimeError("No BrowseComp-Plus tasks were loaded.")
    return tasks


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_DATASET_ID",
    "DEFAULT_SPLIT",
    "browsecomp_row_to_task",
    "collect_docs",
    "extract_expected_answer",
    "extract_query_id",
    "load_browsecomp_plus_tasks",
    "task_id_for_query_id",
]
