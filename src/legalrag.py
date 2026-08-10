"""Evidence-grounded answer generation for LegalRAG Pro."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from config import openai_client
from evidence_answer import (
    EVIDENCE_ROLE_BASIS_KEY,
    EVIDENCE_ROLE_KEY,
    EVIDENCE_ROLE_RULE_KEY,
    GOVERNED_DISCOVERY_RANK_KEY,
    GOVERNED_SEARCH_MODE_KEY,
    GovernedAnswerEvidenceError,
    build_governed_answer_prompt,
    prepare_governed_answer_evidence,
)
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


LOGGER = logging.getLogger(__name__)
_GOVERNED_FAILURE_ANSWER = (
    "I could not establish a complete governed evidence set for this question. "
    "No corpus-level negative finding has been made."
)


def ask(
    question: str,
    selected_documents: Sequence[str] | None = None,
    *,
    case_id: str | None = None,
) -> dict:
    """Ask a legal question using evidence from the requested case.

    Case-scoped questions use U8 governed retrieval: semantic search discovers
    source-bound documents, then every governed page/chunk in those documents is
    completely expanded and classified before the answer prompt is built.
    Legacy/global questions with no case ID retain the pre-U8 retrieval path.
    """

    governed_evidence = None

    if case_id is not None:
        try:
            governed_evidence = prepare_governed_answer_evidence(
                question=question,
                selected_documents=selected_documents,
                case_id=case_id,
            )
        except GovernedAnswerEvidenceError:
            LOGGER.exception(
                "Governed U8 answer retrieval failed for case %s.",
                case_id,
            )
            return {
                "answer": _GOVERNED_FAILURE_ANSWER,
                "sources": [],
                "search_results": {
                    "ids": [[]],
                    "documents": [[]],
                    "metadatas": [[]],
                },
                "retrieval_mode": "governed_failed_closed",
                "semantic_discovery_receipt": None,
                "evidence_search_receipt": None,
            }

        results = enrich_evidence_semantics(governed_evidence.answer_results)
        prompt = build_governed_answer_prompt(
            question=question,
            evidence=governed_evidence,
            enriched_results=results,
        )
    else:
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

    sources = _build_sources(results)

    payload = {
        "answer": response.output_text,
        "sources": sources,
        "search_results": results,
    }
    if governed_evidence is not None:
        payload.update(
            {
                "retrieval_mode": governed_evidence.search_mode.value,
                "semantic_discovery_receipt": governed_evidence.semantic_receipt,
                "evidence_search_receipt": governed_evidence.search_result.receipt,
            }
        )
    return payload


def _build_sources(results: dict) -> list[dict]:
    sources = []
    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))

    for index, text in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}

        sources.append(
            {
                "file": metadata.get("file", "Unknown document"),
                "page": metadata.get("page", "?"),
                "text": text,
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
                "evidence_role": metadata.get(
                    EVIDENCE_ROLE_KEY,
                    "",
                ),
                "evidence_role_rule": metadata.get(
                    EVIDENCE_ROLE_RULE_KEY,
                    "",
                ),
                "evidence_role_basis": metadata.get(
                    EVIDENCE_ROLE_BASIS_KEY,
                    "",
                ),
                "semantic_discovery_rank": metadata.get(
                    GOVERNED_DISCOVERY_RANK_KEY,
                ),
                "governed_search_mode": metadata.get(
                    GOVERNED_SEARCH_MODE_KEY,
                    "",
                ),
                "source_document_instance_id": metadata.get(
                    "source_document_instance_id",
                    "",
                ),
                "evidence_key": (
                    _first_query_row(results.get("ids"))[index]
                    if index < len(_first_query_row(results.get("ids")))
                    else ""
                ),
            }
        )

    return sources


def _first_query_row(value) -> list:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
