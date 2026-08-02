"""Post-process vector search results for evidence quality and diversity."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Final

OVERFETCH_MULTIPLIER: Final[int] = 4
DEFAULT_MAX_RESULTS_PER_DOCUMENT: Final[int] = 2
NEAR_DUPLICATE_THRESHOLD: Final[float] = 0.94

_RESULT_FIELDS: Final[tuple[str, ...]] = (
    "ids",
    "documents",
    "metadatas",
    "distances",
    "embeddings",
    "uris",
    "data",
)


def overfetch_count(n_results: int) -> int:
    """Return the candidate pool size used before quality filtering.

    Over-retrieving gives the quality layer enough alternatives to suppress
    duplicate chunks without unnecessarily reducing the final evidence set.
    """

    if n_results <= 0:
        raise ValueError("n_results must be greater than zero.")

    return n_results * OVERFETCH_MULTIPLIER


def improve_retrieval_results(
    results: dict[str, Any],
    *,
    n_results: int,
    max_results_per_document: int = DEFAULT_MAX_RESULTS_PER_DOCUMENT,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> dict[str, Any]:
    """Suppress duplicate evidence and diversify the remaining results.

    Candidate order is assumed to be the vector store's relevance order. The
    function preserves that order while applying three safeguards:

    1. exact and near-duplicate text is removed;
    2. only one chunk per document page is returned;
    3. the first pass caps results per document so several independent sources
       can surface before additional pages from a dominant document are used.

    The document cap is relaxed in a second pass when fewer independent
    documents are available. Case scoping is not modified: metadata and all
    other returned fields are copied from the already-scoped Chroma response.
    """

    if n_results <= 0:
        raise ValueError("n_results must be greater than zero.")
    if max_results_per_document <= 0:
        raise ValueError("max_results_per_document must be greater than zero.")
    if not 0.0 <= near_duplicate_threshold <= 1.0:
        raise ValueError("near_duplicate_threshold must be between 0 and 1.")

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))

    if not documents:
        return _select_indices(results, [])

    deduplicated_indices: list[int] = []
    accepted_texts: list[tuple[str, str]] = []

    for index, document in enumerate(documents):
        text = "" if document is None else str(document)
        normalised = _normalise_text(text)
        file_name, _ = _source_key(metadatas, index)

        if not normalised:
            continue
        if _is_duplicate(
            normalised,
            file_name=file_name,
            accepted=accepted_texts,
            threshold=near_duplicate_threshold,
        ):
            continue

        deduplicated_indices.append(index)
        accepted_texts.append((normalised, file_name))

    selected: list[int] = []
    selected_set: set[int] = set()
    selected_pages: set[tuple[str, str]] = set()
    document_counts: dict[str, int] = {}

    # First pass: retain Chroma relevance order, but prevent one document from
    # consuming most of the evidence slots.
    for index in deduplicated_indices:
        file_name, page = _source_key(metadatas, index)
        page_key = (file_name, page)

        if page_key in selected_pages:
            continue
        if document_counts.get(file_name, 0) >= max_results_per_document:
            continue

        _accept_index(
            index=index,
            file_name=file_name,
            page_key=page_key,
            selected=selected,
            selected_set=selected_set,
            selected_pages=selected_pages,
            document_counts=document_counts,
        )
        if len(selected) >= n_results:
            return _select_indices(results, selected)

    # Second pass: relax only the per-document cap. The one-result-per-page
    # rule remains in force so repeated chunks from the same page never consume
    # multiple final evidence slots.
    for index in deduplicated_indices:
        if index in selected_set:
            continue

        file_name, page = _source_key(metadatas, index)
        page_key = (file_name, page)
        if page_key in selected_pages:
            continue

        _accept_index(
            index=index,
            file_name=file_name,
            page_key=page_key,
            selected=selected,
            selected_set=selected_set,
            selected_pages=selected_pages,
            document_counts=document_counts,
        )
        if len(selected) >= n_results:
            break

    return _select_indices(results, selected)


def _normalise_text(text: str) -> str:
    """Return a stable representation for duplicate comparison."""

    lowered = text.casefold()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _is_duplicate(
    candidate: str,
    *,
    file_name: str,
    accepted: list[tuple[str, str]],
    threshold: float,
) -> bool:
    """Return whether candidate text duplicates an already accepted chunk.

    Exact duplicates are suppressed globally. Near-duplicate matching is kept
    within the same source document so independently retrieved documents with
    very similar wording can still provide corroboration.
    """

    for existing, existing_file in accepted:
        if candidate == existing:
            return True
        if file_name != existing_file:
            continue

        shorter = min(len(candidate), len(existing))
        longer = max(len(candidate), len(existing))
        if longer == 0:
            continue

        # Avoid expensive comparisons where text lengths are too different to
        # plausibly represent the same chunk.
        if shorter / longer < threshold:
            continue

        if SequenceMatcher(None, candidate, existing).ratio() >= threshold:
            return True

    return False


def _source_key(
    metadatas: list[Any],
    index: int,
) -> tuple[str, str]:
    """Return a stable document/page key for one result row."""

    metadata: dict[str, Any] = {}
    if index < len(metadatas) and isinstance(metadatas[index], dict):
        metadata = metadatas[index]

    file_name = str(metadata.get("file") or f"__unknown_file_{index}")
    page = str(metadata.get("page") or f"__unknown_page_{index}")
    return file_name, page


def _accept_index(
    *,
    index: int,
    file_name: str,
    page_key: tuple[str, str],
    selected: list[int],
    selected_set: set[int],
    selected_pages: set[tuple[str, str]],
    document_counts: dict[str, int],
) -> None:
    """Record one selected candidate in all tracking collections."""

    selected.append(index)
    selected_set.add(index)
    selected_pages.add(page_key)
    document_counts[file_name] = document_counts.get(file_name, 0) + 1


def _first_query_row(value: Any) -> list[Any]:
    """Return the first query row from a Chroma-style nested result field."""

    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


def _select_indices(results: dict[str, Any], indices: list[int]) -> dict[str, Any]:
    """Return a Chroma-compatible response containing only selected rows."""

    filtered = dict(results)

    for field in _RESULT_FIELDS:
        value = results.get(field)
        if value is None:
            continue

        row = _first_query_row(value)
        if not row and value != [[]]:
            continue

        filtered[field] = [
            [row[index] for index in indices if index < len(row)]
        ]

    return filtered
