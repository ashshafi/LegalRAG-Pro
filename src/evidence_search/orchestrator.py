"""Fail-closed orchestration for complete governed evidence search.

U8D does not perform semantic retrieval itself.  Existing semantic discovery may
supply governed document identities, after which this module expands those
identities completely through U8B and classifies every governed chunk through
U8C.  Exhaustive mode instead enumerates the full governed case catalog first.

A returned ``EvidenceSearchReceipt`` proves search *coverage*.  Its
``negative_finding_permitted`` flag does not itself decide whether evidence
supports a legal proposition; it only records whether the stated search scope
was completely inspected so a downstream component can phrase any negative
finding with an auditable scope.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from document_catalog import DocumentCatalogEntry, DocumentCatalogError, list_case_documents
from evidence_retrieval import DocumentCompleteRetrievalError, inspect_document_complete
from evidence_roles import (
    EvidenceRole,
    EvidenceRoleClassificationError,
    classify_document_evidence_roles,
)

from .models import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchMatch,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    EvidenceTextMatchMode,
    NegativeFindingScope,
)


_RECEIPT_SCHEMA_VERSION = "1.0"
_TERM_PATTERN = re.compile(r"\w+", re.UNICODE)


class EvidenceSearchError(RuntimeError):
    """Raised when governed search scope or complete inspection cannot be proved."""


def record_semantic_discovery(
    *,
    case_id: str,
    query: str,
    candidate_document_ids: Iterable[str],
    store: Any | None = None,
) -> EvidenceSearchReceipt:
    """Record externally discovered document candidates without claiming coverage.

    Semantic discovery remains the existing Chroma/retriever responsibility and
    is intentionally not imported or executed here.  This receipt verifies that
    supplied candidate document identities belong to the governed case catalog,
    but because no document-complete expansion occurs, the receipt is PARTIAL
    and never permits a negative finding.
    """

    case = _canonical_uuid(case_id, field_name="case_id")
    catalog = _load_catalog(case, store=store)
    catalog_by_id = {entry.source_document_instance_id: entry for entry in catalog}
    candidate_ids = _canonical_candidate_ids(candidate_document_ids)
    _require_known_candidates(candidate_ids, catalog_by_id)
    candidate_entries = _entries_in_catalog_order(catalog, candidate_ids)

    return EvidenceSearchReceipt(
        schema_version=_RECEIPT_SCHEMA_VERSION,
        case_id=case,
        search_mode=EvidenceSearchMode.SEMANTIC_DISCOVERY,
        query_sha256=_query_sha256(query),
        case_document_count=len(catalog),
        case_page_count=sum(entry.page_count for entry in catalog),
        case_chunk_count=sum(entry.evidence_chunk_count for entry in catalog),
        scope_document_count=len(candidate_entries),
        scope_page_count=sum(entry.page_count for entry in candidate_entries),
        scope_chunk_count=sum(entry.evidence_chunk_count for entry in candidate_entries),
        documents_completely_expanded=0,
        pages_inspected=0,
        chunks_inspected=0,
        candidate_document_ids=tuple(entry.source_document_instance_id for entry in candidate_entries),
        searched_document_ids=(),
        filters_applied=("discovery=external_semantic_candidates",),
        matched_evidence_keys=(),
        completion=EvidenceSearchCompletion.PARTIAL,
        case_corpus_complete=False,
        negative_finding_scope=NegativeFindingScope.NONE,
        negative_finding_permitted=False,
    )


def search_case_evidence(
    *,
    case_id: str,
    query: str,
    mode: EvidenceSearchMode,
    candidate_document_ids: Iterable[str] = (),
    text_match_mode: EvidenceTextMatchMode = EvidenceTextMatchMode.ALL_EVIDENCE,
    roles: Iterable[EvidenceRole] = (),
    store: Any | None = None,
) -> CaseEvidenceSearchResult:
    """Inspect a selected or exhaustive governed evidence scope completely.

    Args:
        case_id: Case UUID whose immutable catalog defines the corpus.
        query: Original user/search query retained by hash and used only by the
            optional deterministic text matcher.  ``ALL_EVIDENCE`` deliberately
            returns every inspected chunk regardless of query wording.
        mode: ``DOCUMENT_COMPLETE`` for externally discovered candidate
            documents or ``EXHAUSTIVE_EVIDENCE`` for the full case corpus.
        candidate_document_ids: Governed document identities supplied by an
            earlier discovery step.  Required for ``DOCUMENT_COMPLETE`` and
            forbidden for ``EXHAUSTIVE_EVIDENCE``.
        text_match_mode: Deterministic post-inspection text filter.
        roles: Optional U8C role filter applied to matches only.  It never
            reduces the document/page/chunk inspection counts.
        store: Optional read-only source-evidence store dependency forwarded to
            the frozen catalog/U8B boundaries.

    Returns:
        Complete classified document surfaces, deterministic matches, and an
        auditable coverage receipt.

    Raises:
        EvidenceSearchError: If scope, identity, complete expansion, role
            classification, or receipt counts cannot be proved exactly.
    """

    case = _canonical_uuid(case_id, field_name="case_id")
    search_mode = _search_mode(mode)
    match_mode = _text_match_mode(text_match_mode)
    role_filter = _canonical_roles(roles)
    catalog = _load_catalog(case, store=store)
    catalog_by_id = {entry.source_document_instance_id: entry for entry in catalog}

    if search_mode is EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        supplied = tuple(candidate_document_ids)
        if supplied:
            raise EvidenceSearchError(
                "EXHAUSTIVE_EVIDENCE derives its scope from the governed case catalog; "
                "candidate_document_ids must be empty."
            )
        target_entries = catalog
        candidate_ids: tuple[str, ...] = ()
    elif search_mode is EvidenceSearchMode.DOCUMENT_COMPLETE:
        supplied_candidate_ids = _canonical_candidate_ids(candidate_document_ids)
        if not supplied_candidate_ids:
            raise EvidenceSearchError(
                "DOCUMENT_COMPLETE requires at least one governed candidate document."
            )
        _require_known_candidates(supplied_candidate_ids, catalog_by_id)
        target_entries = _entries_in_catalog_order(catalog, supplied_candidate_ids)
        candidate_ids = tuple(
            entry.source_document_instance_id for entry in target_entries
        )
    elif search_mode is EvidenceSearchMode.SEMANTIC_DISCOVERY:
        raise EvidenceSearchError(
            "SEMANTIC_DISCOVERY is external to U8D; use record_semantic_discovery() "
            "and then DOCUMENT_COMPLETE for returned governed document identities."
        )
    else:
        raise EvidenceSearchError(
            f"Search mode {search_mode.value!r} is recognised but not executable in U8D."
        )

    _validate_query_match_mode(query=query, match_mode=match_mode)

    documents = []
    matches: list[EvidenceSearchMatch] = []
    pages_inspected = 0
    chunks_inspected = 0

    try:
        for entry in target_entries:
            inspection = inspect_document_complete(
                case_id=case,
                source_document_instance_id=entry.source_document_instance_id,
                store=store,
            )
            _require_catalog_reconciliation(entry, inspection)
            classified = classify_document_evidence_roles(inspection)
            _require_classified_reconciliation(entry, classified)
            documents.append(classified)

            pages_inspected += len(classified.pages)
            for page in classified.pages:
                chunks_inspected += len(page.chunks)
                for item in page.chunks:
                    if role_filter and item.classification.role not in role_filter:
                        continue
                    if not _text_matches(
                        item.chunk.text,
                        query=query,
                        match_mode=match_mode,
                    ):
                        continue
                    matches.append(
                        EvidenceSearchMatch(
                            source_document_instance_id=entry.source_document_instance_id,
                            original_filename=entry.original_filename,
                            chunk=item.chunk,
                            classification=item.classification,
                        )
                    )
    except EvidenceSearchError:
        raise
    except (
        DocumentCompleteRetrievalError,
        EvidenceRoleClassificationError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise EvidenceSearchError(
            "Governed evidence search could not completely inspect and classify its intended scope: "
            f"{exc}"
        ) from exc

    scope_page_count = sum(entry.page_count for entry in target_entries)
    scope_chunk_count = sum(entry.evidence_chunk_count for entry in target_entries)

    if len(documents) != len(target_entries):
        raise EvidenceSearchError("Search did not completely expand every scoped document.")
    if pages_inspected != scope_page_count:
        raise EvidenceSearchError("Search did not inspect every governed page in scope.")
    if chunks_inspected != scope_chunk_count:
        raise EvidenceSearchError("Search did not inspect every governed chunk in scope.")

    case_document_ids = tuple(entry.source_document_instance_id for entry in catalog)
    searched_document_ids = tuple(entry.source_document_instance_id for entry in target_entries)
    case_corpus_complete = searched_document_ids == case_document_ids
    negative_scope = (
        NegativeFindingScope.CASE_CORPUS
        if case_corpus_complete
        else NegativeFindingScope.SEARCHED_SCOPE
    )

    receipt = EvidenceSearchReceipt(
        schema_version=_RECEIPT_SCHEMA_VERSION,
        case_id=case,
        search_mode=search_mode,
        query_sha256=_query_sha256(query),
        case_document_count=len(catalog),
        case_page_count=sum(entry.page_count for entry in catalog),
        case_chunk_count=sum(entry.evidence_chunk_count for entry in catalog),
        scope_document_count=len(target_entries),
        scope_page_count=scope_page_count,
        scope_chunk_count=scope_chunk_count,
        documents_completely_expanded=len(documents),
        pages_inspected=pages_inspected,
        chunks_inspected=chunks_inspected,
        candidate_document_ids=candidate_ids,
        searched_document_ids=searched_document_ids,
        filters_applied=_filters(match_mode=match_mode, roles=role_filter),
        matched_evidence_keys=tuple(match.chunk.evidence_key for match in matches),
        completion=EvidenceSearchCompletion.COMPLETE,
        case_corpus_complete=case_corpus_complete,
        negative_finding_scope=negative_scope,
        negative_finding_permitted=True,
    )

    return CaseEvidenceSearchResult(
        case_id=case,
        query=query,
        search_mode=search_mode,
        documents=tuple(documents),
        matches=tuple(matches),
        receipt=receipt,
    )


def _load_catalog(case_id: str, *, store: Any | None) -> tuple[DocumentCatalogEntry, ...]:
    try:
        return list_case_documents(case_id, store=store)
    except (DocumentCatalogError, OSError, TypeError, UnicodeError, ValueError) as exc:
        raise EvidenceSearchError(
            "Governed case-document catalog could not be read safely."
        ) from exc


def _canonical_uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvidenceSearchError(f"{field_name} must be a valid UUID.") from exc


def _canonical_candidate_ids(values: Iterable[str]) -> tuple[str, ...]:
    try:
        canonical = tuple(
            _canonical_uuid(value, field_name="source_document_instance_id")
            for value in values
        )
    except TypeError as exc:
        raise EvidenceSearchError("candidate_document_ids must be iterable UUID strings.") from exc
    return tuple(dict.fromkeys(canonical))


def _require_known_candidates(
    candidate_ids: tuple[str, ...],
    catalog_by_id: dict[str, DocumentCatalogEntry],
) -> None:
    unknown = tuple(item for item in candidate_ids if item not in catalog_by_id)
    if unknown:
        raise EvidenceSearchError(
            "Candidate document is not present in the governed case catalog: "
            + ", ".join(unknown)
        )


def _entries_in_catalog_order(
    catalog: tuple[DocumentCatalogEntry, ...],
    candidate_ids: tuple[str, ...],
) -> tuple[DocumentCatalogEntry, ...]:
    selected = set(candidate_ids)
    return tuple(entry for entry in catalog if entry.source_document_instance_id in selected)


def _search_mode(value: EvidenceSearchMode) -> EvidenceSearchMode:
    try:
        return EvidenceSearchMode(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceSearchError("Unsupported evidence search mode.") from exc


def _text_match_mode(value: EvidenceTextMatchMode) -> EvidenceTextMatchMode:
    try:
        return EvidenceTextMatchMode(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceSearchError("Unsupported deterministic evidence text-match mode.") from exc


def _canonical_roles(values: Iterable[EvidenceRole]) -> tuple[EvidenceRole, ...]:
    try:
        selected = {EvidenceRole(value) for value in values}
    except (TypeError, ValueError) as exc:
        raise EvidenceSearchError("Unknown U8C evidence role filter.") from exc
    return tuple(role for role in EvidenceRole if role in selected)


def _validate_query_match_mode(*, query: str, match_mode: EvidenceTextMatchMode) -> None:
    if not isinstance(query, str):
        raise EvidenceSearchError("Evidence search query must be text.")
    if match_mode is EvidenceTextMatchMode.ALL_EVIDENCE:
        return
    if not _normalise(query):
        raise EvidenceSearchError(
            f"{match_mode.value} requires a non-empty deterministic text query."
        )
    if match_mode in {EvidenceTextMatchMode.ALL_TERMS, EvidenceTextMatchMode.ANY_TERM}:
        if not _terms(query):
            raise EvidenceSearchError(
                f"{match_mode.value} query contains no searchable terms."
            )


def _text_matches(text: str, *, query: str, match_mode: EvidenceTextMatchMode) -> bool:
    if match_mode is EvidenceTextMatchMode.ALL_EVIDENCE:
        return True

    haystack = _normalise(text)
    if match_mode is EvidenceTextMatchMode.EXACT_PHRASE:
        return _normalise(query) in haystack

    terms = _terms(query)
    haystack_terms = frozenset(_terms(text))
    if match_mode is EvidenceTextMatchMode.ALL_TERMS:
        return all(term in haystack_terms for term in terms)
    if match_mode is EvidenceTextMatchMode.ANY_TERM:
        return any(term in haystack_terms for term in terms)
    raise EvidenceSearchError("Unhandled deterministic text-match mode.")


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _terms(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_TERM_PATTERN.findall(value.casefold())))


def _query_sha256(query: str) -> str:
    if not isinstance(query, str):
        raise EvidenceSearchError("Evidence search query must be text.")
    return "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()


def _filters(
    *,
    match_mode: EvidenceTextMatchMode,
    roles: tuple[EvidenceRole, ...],
) -> tuple[str, ...]:
    result = [f"text_match={match_mode.value}"]
    result.extend(f"role={role.value}" for role in roles)
    return tuple(result)


def _require_catalog_reconciliation(entry: DocumentCatalogEntry, inspection: Any) -> None:
    expected = {
        "source_document_instance_id": entry.source_document_instance_id,
        "original_filename": entry.original_filename,
        "original_blob_sha256": entry.original_blob_sha256,
        "original_byte_length": entry.original_byte_length,
        "source_snapshot_id": entry.source_snapshot_id,
        "page_count": entry.page_count,
        "evidence_chunk_count": entry.evidence_chunk_count,
        "extraction_profile_id": entry.extraction_profile_id,
        "chunking_profile_id": entry.chunking_profile_id,
    }
    for field_name, expected_value in expected.items():
        if getattr(inspection, field_name) != expected_value:
            raise EvidenceSearchError(
                f"U8B inspection field {field_name!r} does not reconcile with the governed catalog."
            )


def _require_classified_reconciliation(entry: DocumentCatalogEntry, classified: Any) -> None:
    if classified.document.source_document_instance_id != entry.source_document_instance_id:
        raise EvidenceSearchError("U8C classification changed the governed document identity.")
    if len(classified.pages) != entry.page_count:
        raise EvidenceSearchError("U8C classification changed the governed page count.")
    classified_chunks = sum(len(page.chunks) for page in classified.pages)
    if classified_chunks != entry.evidence_chunk_count:
        raise EvidenceSearchError("U8C classification changed the governed chunk count.")


__all__ = [
    "EvidenceSearchError",
    "record_semantic_discovery",
    "search_case_evidence",
]
