"""Sprint 2.3 M3 bridge to the frozen Sprint 2.2 evidence pipeline.

This adapter intentionally sits outside ``src/legal_analysis`` so the durable M1
analysis package remains independent of OpenAI/Chroma imports.  It composes the
existing frozen retriever with the existing post-retrieval evidence-semantic
enrichment; it does not alter either implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from source_evidence.identity import canonical_uuid
from source_evidence.verified_retrieval import (
    SourceBoundRetrievalVerificationError,
    verify_source_bound_retrieval_results,
)


def retrieve_for_legal_analysis(
    question: str,
    selected_documents: Sequence[str] | None = None,
    n_results: int = 10,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve case-scoped evidence and admit only fully source-verified candidates."""
    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")  # type: ignore[arg-type]
    except (TypeError, ValueError, AttributeError) as exc:
        raise SourceBoundRetrievalVerificationError(
            "Structured legal-analysis retrieval requires a canonical case_id."
        ) from exc

    from evidence_semantics import enrich_evidence_semantics
    from retriever import retrieve

    results = retrieve(
        question,
        selected_documents,
        n_results=n_results,
        case_id=canonical_case_id,
    )
    enriched = enrich_evidence_semantics(results)
    return verify_source_bound_retrieval_results(
        enriched,
        case_id=canonical_case_id,
    )


__all__ = ["retrieve_for_legal_analysis"]
