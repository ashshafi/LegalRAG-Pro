"""Milestone 4 semantic context and assertion-safety prompt rules."""

from __future__ import annotations

from typing import Any

from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
)
from evidence_classification import EVIDENCE_SOURCE_LABEL_KEY
from evidence_reranking import (
    RETRIEVAL_ORIGINAL_RANK_KEY,
    RETRIEVAL_RERANK_RANK_KEY,
)
from evidence_semantics import (
    KNOWLEDGE_SIGNAL_LABEL_KEY,
    PROVENANCE_BASIS_KEY,
    PROVENANCE_CONFIDENCE_KEY,
    PROVENANCE_WARNING_KEY,
    SEMANTIC_SOURCE_LABEL_KEY,
)
from provenance_reasoning import build_provenance_legal_prompt


def build_semantic_context(results: dict[str, Any]) -> str:
    """Build answer context with retrieval provenance and semantic reliability."""

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    blocks: list[str] = []

    for index, document in enumerate(documents, start=1):
        metadata: dict[str, Any] = {}
        if index - 1 < len(metadatas) and isinstance(metadatas[index - 1], dict):
            metadata = metadatas[index - 1]

        warning = str(metadata.get(PROVENANCE_WARNING_KEY) or "")
        lines = [
            f"Evidence ID: E{index}",
            f"Document: {metadata.get('file', 'Unknown document')}",
            f"Page: {metadata.get('page', '?')}",
            "Container classification: "
            f"{metadata.get(EVIDENCE_SOURCE_LABEL_KEY, 'Unclassified evidence')}",
            "Retrieval chunk provenance: "
            f"{metadata.get(CHUNK_SOURCE_LABEL_KEY, 'Unclassified evidence')}",
            "Semantic provenance: "
            f"{metadata.get(SEMANTIC_SOURCE_LABEL_KEY, 'Unclassified evidence')}",
            f"Provenance basis: {metadata.get(PROVENANCE_BASIS_KEY, 'unknown')}",
            "Provenance confidence: "
            f"{metadata.get(PROVENANCE_CONFIDENCE_KEY, 'low')}",
            "Retrieval provenance method: "
            f"{metadata.get(CHUNK_PROVENANCE_METHOD_KEY, 'unknown')}",
            "Knowledge/awareness signal: "
            f"{metadata.get(KNOWLEDGE_SIGNAL_LABEL_KEY, 'No explicit knowledge indicator detected')}",
            "Primary-source class: "
            f"{metadata.get(PRIMARY_SOURCE_LABEL_KEY, 'Unclassified source')}",
            "Vector rank / reranked rank: "
            f"{metadata.get(RETRIEVAL_ORIGINAL_RANK_KEY, '?')} / "
            f"{metadata.get(RETRIEVAL_RERANK_RANK_KEY, '?')}",
        ]
        if warning:
            lines.append(f"Provenance caution: {warning}")
        lines.extend(("Excerpt:", str(document or "")))
        blocks.append("\n".join(lines))

    return "\n\n--------------------------------------------------\n\n".join(blocks)


def build_semantic_legal_prompt(*, question: str, context: str) -> str:
    """Add Milestone 4 source-assertion and knowledge safeguards."""

    rules = """
MILESTONE 4 EVIDENCE SEMANTICS & ASSERTION SAFETY
Source identity, source assertion, and substantive truth are three different
things. Preserve that distinction throughout the answer.

PROVENANCE BASIS AND CONFIDENCE
Use "Semantic provenance" for answer attribution. "Retrieval chunk provenance"
is retained only for auditability and reranking history. If semantic provenance
is Unclassified evidence or provenance confidence is low, do not guess the
author from subject matter. Describe the document neutrally and identify the
provenance limitation where it matters.

SOURCE ASSERTION
"Source assertion" is a required evidential-status label when a source says a
material proposition is true but the supplied evidence does not independently
establish that proposition. It establishes that the assertion was made, not the
truth of the assertion. Examples:
- "Source assertion: Appendix H5 states that CACI was aware of the proposed
  adjustments."
- "Claimant evidence: Mr Shafi states that CACI knew of the recommendation."
Do NOT silently rewrite either as "CACI knew".

KNOWLEDGE / AWARENESS GUARD
Treat terms such as knew, aware, fully aware, knowledge, notice, understood,
accepted and recognised as specially guarded propositions. A source's statement
that another person knew something is ordinarily a Source assertion or party
evidence. State knowledge as a Documented fact only where the cited direct
record itself demonstrates the relevant receipt, acknowledgement, discussion,
communication or other direct knowledge event. A "Direct communication/
acknowledgement indicator" in metadata is only a cue to inspect the excerpt; it
is not itself proof. If the direct record does not resolve knowledge, use an
Inference or Disputed matter and explain the evidential limit.

A document being held by CACI, included in an employer bundle, accessible to
management, or describing leadership continuity does not establish that CACI or
a named person actually knew its contents.
""".strip()

    base_prompt = build_provenance_legal_prompt(question=question, context=context)
    return f"{rules}\n\n{base_prompt}"


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
