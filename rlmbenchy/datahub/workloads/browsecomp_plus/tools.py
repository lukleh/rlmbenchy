"""Tool builders for the BrowseComp-Plus workload."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import dspy


def build_tools(
    docs_by_query_id: Mapping[str, Sequence[str]],
    default_max_docs: int | None = None,
) -> list[dspy.Tool]:
    """Build BrowseComp-specific tools over preloaded dataset rows."""

    docs_index: dict[str, list[str]] = {
        str(query_id): [str(doc).strip() for doc in docs if str(doc).strip()]
        for query_id, docs in docs_by_query_id.items()
    }

    def browsecomp_get_docs(
        query_id: str,
        offset: int = 0,
        max_docs: int | None = default_max_docs,
    ) -> list[str]:
        query_id_normalized = str(query_id).strip()
        docs = docs_index[query_id_normalized]
        offset_i = int(offset)

        offset_i = max(0, offset_i)
        if offset_i >= len(docs):
            return []

        if max_docs is None:
            return docs[offset_i:]

        max_docs_i = max(0, int(max_docs))
        if max_docs_i == 0:
            return []
        end = min(offset_i + max_docs_i, len(docs))
        return docs[offset_i:end]

    return [
        dspy.Tool(
            browsecomp_get_docs,
            name="browsecomp_get_docs",
            desc=(
                "Fetch BrowseComp documents by query_id in paged chunks. Returns list[str]. "
                "Args: query_id (str), offset (int, default 0), "
                "max_docs (int, optional, default all remaining docs)."
            ),
        )
    ]
