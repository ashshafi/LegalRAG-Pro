"""Evidence-grounded answer generation for LegalRAG Pro."""

from __future__ import annotations

from collections.abc import Sequence

from config import openai_client
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)
from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_TIER_KEY,
)
from evidence_reranking import (
    RETRIEVAL_ORIGINAL_RANK_KEY,
    RETRIEVAL_PROMOTION_KEY,
    RETRIEVAL_RERANK_RANK_KEY,
)
from evidence_semantics import (
    KNOWLEDGE_SIGNAL_KEY,
    KNOWLEDGE_SIGNAL_LABEL_KEY,
    PROVENANCE_BASIS_KEY,
    PROVENANCE_CONFIDENCE_KEY,
    PROVENANCE_WARNING_KEY,
    SEMANTIC_SOURCE_LABEL_KEY,
    SEMANTIC_SOURCE_TYPE_KEY,
    enrich_evidence_semantics,
)
from semantic_reasoning import (
    build_semantic_context,
    build_semantic_legal_prompt,
)
from models import CHAT_MODEL
from retriever import retrieve


def ask(
    question: str,
    selected_documents: Sequence[str] | None = None,
    *,
    case_id: str | None = None,
) -> dict:
    """Ask a legal question using evidence from the requested case."""

    results = retrieve(
        question,
        selected_documents,
        n_results=10,
        case_id=case_id,
    )

    # Milestone 4 runs strictly after the frozen retrieval/reranking pipeline.
    # It enriches the already-selected evidence without changing order or scope.
    results = enrich_evidence_semantics(results)
    context = build_semantic_context(results)
    prompt = build_semantic_legal_prompt(question=question, context=context)

    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )

    sources = []

    for i in range(len(results["documents"][0])):
        metadata = results["metadatas"][0][i]

        sources.append(
            {
                "file": metadata["file"],
                "page": metadata["page"],
                "text": results["documents"][0][i],
                "source_type": metadata.get(
                    EVIDENCE_SOURCE_TYPE_KEY,
                    "other",
                ),
                "source_label": metadata.get(
                    EVIDENCE_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "classification_method": metadata.get(
                    EVIDENCE_CLASSIFICATION_METHOD_KEY,
                    "unknown",
                ),
                "chunk_source_type": metadata.get(
                    CHUNK_SOURCE_TYPE_KEY,
                    "other",
                ),
                "chunk_source_label": metadata.get(
                    CHUNK_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "chunk_provenance_method": metadata.get(
                    CHUNK_PROVENANCE_METHOD_KEY,
                    "unknown",
                ),
                "primary_source_tier": metadata.get(
                    PRIMARY_SOURCE_TIER_KEY,
                    0,
                ),
                "primary_source_label": metadata.get(
                    PRIMARY_SOURCE_LABEL_KEY,
                    "Unclassified source",
                ),
                "original_rank": metadata.get(
                    RETRIEVAL_ORIGINAL_RANK_KEY,
                ),
                "rerank_rank": metadata.get(
                    RETRIEVAL_RERANK_RANK_KEY,
                ),
                "primary_source_promotion": metadata.get(
                    RETRIEVAL_PROMOTION_KEY,
                    0,
                ),
                "semantic_source_type": metadata.get(
                    SEMANTIC_SOURCE_TYPE_KEY,
                    "other",
                ),
                "semantic_source_label": metadata.get(
                    SEMANTIC_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "provenance_basis": metadata.get(
                    PROVENANCE_BASIS_KEY,
                    "unknown",
                ),
                "provenance_confidence": metadata.get(
                    PROVENANCE_CONFIDENCE_KEY,
                    "low",
                ),
                "provenance_warning": metadata.get(
                    PROVENANCE_WARNING_KEY,
                    "",
                ),
                "knowledge_signal": metadata.get(
                    KNOWLEDGE_SIGNAL_KEY,
                    "none",
                ),
                "knowledge_signal_label": metadata.get(
                    KNOWLEDGE_SIGNAL_LABEL_KEY,
                    "No explicit knowledge indicator detected",
                ),
            }
        )

    return {
        "answer": response.output_text,
        "sources": sources,
        "search_results": results,
    }
