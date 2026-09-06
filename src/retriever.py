"""Vector retrieval for LegalRAG Pro."""

from __future__ import annotations

from collections.abc import Sequence
import os
import time

from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    assert_ai_processing_allowed,
)
from case_management.retrieval_scope import build_retrieval_filter
import config as _config
from config import openai_client
from chunk_provenance import enrich_chunk_provenance
from evidence_classification import enrich_retrieval_metadata
from evidence_reranking import rerank_for_primary_sources
from models import EMBEDDING_MODEL
from query_expander import expand_query
from retrieval_quality import improve_retrieval_results, overfetch_count


def retrieve(
    question: str,
    selected_documents: Sequence[str] | None = None,
    n_results: int = 10,
    *,
    case_id: str | None = None,
    expand_search_query: bool = True,
) -> dict:
    """Retrieve relevant chunks within the requested case scope.

    Args:
        question: User's legal question.
        selected_documents: Optional filenames selected by the user.
        n_results: Maximum number of vector results.
        case_id: Active internal case ID. When supplied, Chroma is strictly
            filtered to chunks belonging to that case. When omitted, legacy
            global retrieval behaviour is preserved.
    """

    _timing_enabled = os.getenv("LEGALRAG_ASSISTANT_TIMING") == "1"
    _retrieval_started = time.perf_counter() if _timing_enabled else 0.0
    _query_prep_started = time.perf_counter() if _timing_enabled else 0.0
    expanded_query = expand_query(question) if expand_search_query else question
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING QUERY_PREPARATION_MS="
            f"{(time.perf_counter() - _query_prep_started) * 1000:.1f}"
        )

    _embedding_started = time.perf_counter() if _timing_enabled else 0.0
    assert_ai_processing_allowed(
        provider="openai",
        purpose=AIProcessingPurpose.RETRIEVAL_EMBEDDING,
        data_classification=AIDataClassification.PRIVILEGED,
        model=EMBEDDING_MODEL,
    )
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=expanded_query,
    )
    question_embedding = response.data[0].embedding
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING EMBEDDING_MS="
            f"{(time.perf_counter() - _embedding_started) * 1000:.1f}"
        )

    where = build_retrieval_filter(
        case_id=case_id,
        selected_documents=selected_documents,
    )

    query_kwargs = {
        "query_embeddings": [question_embedding],
        "n_results": overfetch_count(n_results),
    }
    if where is not None:
        query_kwargs["where"] = where

    get_collection = getattr(_config, "get_collection", None)
    collection = get_collection() if callable(get_collection) else _config.collection

    _chroma_rerank_started = time.perf_counter() if _timing_enabled else 0.0
    raw_results = collection.query(**query_kwargs)
    classified_results = enrich_retrieval_metadata(raw_results)
    provenance_results = enrich_chunk_provenance(classified_results)
    reranked_results = rerank_for_primary_sources(provenance_results)
    improved_results = improve_retrieval_results(
        reranked_results,
        n_results=n_results,
    )
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING CHROMA_RERANK_MS="
            f"{(time.perf_counter() - _chroma_rerank_started) * 1000:.1f}"
        )
        print(
            "LEGALRAG_TIMING RETRIEVER_TOTAL_MS="
            f"{(time.perf_counter() - _retrieval_started) * 1000:.1f}"
        )

    return improved_results
