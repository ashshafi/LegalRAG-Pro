"""Vector retrieval for LegalRAG Pro."""

from __future__ import annotations

from collections.abc import Sequence

from case_management.retrieval_scope import build_retrieval_filter
from config import collection, openai_client
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

    expanded_query = expand_query(question)

    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=expanded_query,
    )
    question_embedding = response.data[0].embedding

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

    raw_results = collection.query(**query_kwargs)
    classified_results = enrich_retrieval_metadata(raw_results)
    provenance_results = enrich_chunk_provenance(classified_results)
    reranked_results = rerank_for_primary_sources(provenance_results)

    return improve_retrieval_results(
        reranked_results,
        n_results=n_results,
    )
