"""Sprint 2.3 M3 bridge to the frozen Sprint 2.2 evidence pipeline.

This adapter intentionally sits outside ``src/legal_analysis`` so the durable M1
analysis package remains independent of OpenAI/Chroma imports.  It composes the
existing frozen retriever with the existing post-retrieval evidence-semantic
enrichment; it does not alter either implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from evidence_semantics import enrich_evidence_semantics
from retriever import retrieve


def retrieve_for_legal_analysis(
    question: str,
    selected_documents: Sequence[str] | None = None,
    n_results: int = 10,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve case-scoped evidence and add the frozen M4 semantic metadata."""

    results = retrieve(
        question,
        selected_documents,
        n_results=n_results,
        case_id=case_id,
    )
    return enrich_evidence_semantics(results)


__all__ = ["retrieve_for_legal_analysis"]
