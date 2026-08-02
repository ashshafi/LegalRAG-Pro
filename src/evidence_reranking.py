"""Bounded primary-source reranking for LegalRAG retrieval candidates."""

from __future__ import annotations

from typing import Any, Final

from chunk_provenance import PRIMARY_SOURCE_TIER_KEY

RETRIEVAL_ORIGINAL_RANK_KEY: Final[str] = "retrieval_original_rank"
RETRIEVAL_RERANK_RANK_KEY: Final[str] = "retrieval_rerank_rank"
RETRIEVAL_PROMOTION_KEY: Final[str] = "retrieval_primary_source_promotion"

# A primary source may move only a small number of vector-rank positions. This
# keeps semantic relevance dominant while allowing a nearby direct record to
# outrank a retrospective or secondary source addressing the same issue.
_PROMOTION_BY_TIER: Final[dict[int, int]] = {
    4: 4,
    3: 3,
    2: 1,
    1: 0,
    0: 0,
}

_RESULT_FIELDS: Final[tuple[str, ...]] = (
    "ids",
    "documents",
    "metadatas",
    "distances",
    "embeddings",
    "uris",
    "data",
)


def rerank_for_primary_sources(results: dict[str, Any]) -> dict[str, Any]:
    """Prefer nearby primary/direct evidence without replacing vector search.

    The vector store's original order remains the dominant signal. Each source
    tier receives only a bounded rank credit, so a weakly relevant direct record
    cannot leap from the bottom of the over-fetched pool to the top merely
    because of provenance.
    """

    metadatas = _first_query_row(results.get("metadatas"))
    documents = _first_query_row(results.get("documents"))
    if not documents:
        return results

    indices = list(range(len(documents)))

    def sort_key(index: int) -> tuple[int, int]:
        # Preserve Chroma's strongest semantic hit. Primary-source preference
        # operates below rank 1, preventing provenance from displacing the
        # single best vector match.
        if index == 0:
            return (-10_000, index)

        metadata = _metadata_at(metadatas, index)
        tier = _safe_tier(metadata.get(PRIMARY_SOURCE_TIER_KEY))
        promotion = _PROMOTION_BY_TIER[tier]
        return (index - promotion, index)

    reranked_indices = sorted(indices, key=sort_key)
    reranked = _select_indices(results, reranked_indices)

    reranked_metadatas = _first_query_row(reranked.get("metadatas"))
    for new_index, metadata in enumerate(reranked_metadatas):
        if not isinstance(metadata, dict):
            continue
        original_index = reranked_indices[new_index]
        original_rank = original_index + 1
        rerank_rank = new_index + 1
        metadata[RETRIEVAL_ORIGINAL_RANK_KEY] = original_rank
        metadata[RETRIEVAL_RERANK_RANK_KEY] = rerank_rank
        metadata[RETRIEVAL_PROMOTION_KEY] = max(0, original_rank - rerank_rank)

    return reranked


def _safe_tier(value: Any) -> int:
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return 0
    return tier if tier in _PROMOTION_BY_TIER else 0


def _metadata_at(metadatas: list[Any], index: int) -> dict[str, Any]:
    if index < len(metadatas) and isinstance(metadatas[index], dict):
        return metadatas[index]
    return {}


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


def _select_indices(results: dict[str, Any], indices: list[int]) -> dict[str, Any]:
    selected = dict(results)
    for field in _RESULT_FIELDS:
        value = results.get(field)
        if value is None:
            continue
        row = _first_query_row(value)
        if not row and value != [[]]:
            continue
        selected[field] = [[row[index] for index in indices if index < len(row)]]
    return selected
