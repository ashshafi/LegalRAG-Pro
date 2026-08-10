"""Deterministic orchestration models for governed evidence search.

U8D sits above the already complete U8B document inspection and U8C evidence-
role classification layers.  The models record exactly what search scope was
inspected and whether a negative finding is permitted for that scope.  They do
not redefine source-evidence identities, legal-analysis semantics, or Chroma
retrieval behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidence_retrieval.models import DocumentEvidenceChunk
from evidence_roles.models import (
    DocumentEvidenceRoleInspection,
    EvidenceRole,
    EvidenceRoleClassification,
)


class EvidenceSearchMode(StrEnum):
    """Canonical retrieval/search modes recognised by the U8 boundary."""

    SEMANTIC_DISCOVERY = "semantic_discovery"
    DOCUMENT_COMPLETE = "document_complete"
    CHRONOLOGY = "chronology"
    PERSON = "person"
    EXHAUSTIVE_EVIDENCE = "exhaustive_evidence"


class EvidenceSearchCompletion(StrEnum):
    """Coverage state of one evidence-search receipt."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceTextMatchMode(StrEnum):
    """Deterministic text filtering applied after complete inspection."""

    ALL_EVIDENCE = "all_evidence"
    EXACT_PHRASE = "exact_phrase"
    ALL_TERMS = "all_terms"
    ANY_TERM = "any_term"


class NegativeFindingScope(StrEnum):
    """Largest corpus for which a negative finding is justified."""

    NONE = "none"
    SEARCHED_SCOPE = "searched_scope"
    CASE_CORPUS = "case_corpus"


@dataclass(frozen=True, slots=True)
class EvidenceSearchMatch:
    """One matched governed chunk, preserving exact U8B/U8C objects."""

    source_document_instance_id: str
    original_filename: str
    chunk: DocumentEvidenceChunk
    classification: EvidenceRoleClassification


@dataclass(frozen=True, slots=True)
class EvidenceSearchReceipt:
    """Deterministic coverage receipt for one governed evidence search."""

    schema_version: str
    case_id: str
    search_mode: EvidenceSearchMode
    query_sha256: str
    case_document_count: int
    case_page_count: int
    case_chunk_count: int
    scope_document_count: int
    scope_page_count: int
    scope_chunk_count: int
    documents_completely_expanded: int
    pages_inspected: int
    chunks_inspected: int
    candidate_document_ids: tuple[str, ...]
    searched_document_ids: tuple[str, ...]
    filters_applied: tuple[str, ...]
    matched_evidence_keys: tuple[str, ...]
    completion: EvidenceSearchCompletion
    case_corpus_complete: bool
    negative_finding_scope: NegativeFindingScope
    negative_finding_permitted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_document_ids", tuple(self.candidate_document_ids))
        object.__setattr__(self, "searched_document_ids", tuple(self.searched_document_ids))
        object.__setattr__(self, "filters_applied", tuple(self.filters_applied))
        object.__setattr__(self, "matched_evidence_keys", tuple(self.matched_evidence_keys))
        self._validate()

    def _validate(self) -> None:
        counts = (
            self.case_document_count,
            self.case_page_count,
            self.case_chunk_count,
            self.scope_document_count,
            self.scope_page_count,
            self.scope_chunk_count,
            self.documents_completely_expanded,
            self.pages_inspected,
            self.chunks_inspected,
        )
        if any(value < 0 for value in counts):
            raise ValueError("Evidence-search receipt counts must be non-negative.")
        if self.scope_document_count > self.case_document_count:
            raise ValueError("Search scope cannot contain more documents than the case corpus.")
        if self.scope_page_count > self.case_page_count:
            raise ValueError("Search scope cannot contain more pages than the case corpus.")
        if self.scope_chunk_count > self.case_chunk_count:
            raise ValueError("Search scope cannot contain more chunks than the case corpus.")
        if self.documents_completely_expanded > self.scope_document_count:
            raise ValueError("Expanded-document count exceeds the intended search scope.")
        if self.pages_inspected > self.scope_page_count:
            raise ValueError("Inspected-page count exceeds the intended search scope.")
        if self.chunks_inspected > self.scope_chunk_count:
            raise ValueError("Inspected-chunk count exceeds the intended search scope.")

        negative_expected = self.negative_finding_scope is not NegativeFindingScope.NONE
        if self.negative_finding_permitted is not negative_expected:
            raise ValueError("Negative-finding flag and scope are inconsistent.")
        if self.completion is not EvidenceSearchCompletion.COMPLETE and negative_expected:
            raise ValueError("Incomplete searches cannot permit negative findings.")
        if self.case_corpus_complete:
            if self.completion is not EvidenceSearchCompletion.COMPLETE:
                raise ValueError("A complete case corpus requires COMPLETE search status.")
            if self.negative_finding_scope is not NegativeFindingScope.CASE_CORPUS:
                raise ValueError("Complete case-corpus searches must use CASE_CORPUS scope.")
            if self.scope_document_count != self.case_document_count:
                raise ValueError("Case-corpus completeness requires every case document in scope.")
            if self.scope_page_count != self.case_page_count:
                raise ValueError("Case-corpus completeness requires every case page in scope.")
            if self.scope_chunk_count != self.case_chunk_count:
                raise ValueError("Case-corpus completeness requires every case chunk in scope.")
        if self.completion is EvidenceSearchCompletion.COMPLETE:
            if self.documents_completely_expanded != self.scope_document_count:
                raise ValueError("Complete searches must fully expand every scoped document.")
            if self.pages_inspected != self.scope_page_count:
                raise ValueError("Complete searches must inspect every scoped page.")
            if self.chunks_inspected != self.scope_chunk_count:
                raise ValueError("Complete searches must inspect every scoped chunk.")


@dataclass(frozen=True, slots=True)
class CaseEvidenceSearchResult:
    """Complete searched document surfaces, deterministic matches, and receipt."""

    case_id: str
    query: str
    search_mode: EvidenceSearchMode
    documents: tuple[DocumentEvidenceRoleInspection, ...]
    matches: tuple[EvidenceSearchMatch, ...]
    receipt: EvidenceSearchReceipt

    def __post_init__(self) -> None:
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "matches", tuple(self.matches))


__all__ = [
    "CaseEvidenceSearchResult",
    "EvidenceSearchCompletion",
    "EvidenceSearchMatch",
    "EvidenceSearchMode",
    "EvidenceSearchReceipt",
    "EvidenceTextMatchMode",
    "NegativeFindingScope",
    "EvidenceRole",
]
