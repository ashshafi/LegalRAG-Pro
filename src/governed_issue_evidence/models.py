"""Immutable U9B models binding governed U8 evidence to frozen analytical coordinates."""

from __future__ import annotations

from dataclasses import dataclass


GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION = "governed-issue-evidence-schema/1.0"
GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION = "governed-issue-evidence-builder/1.0"


@dataclass(frozen=True, slots=True)
class GovernedSearchCoverage:
    """Exact U8 search-coverage facts consumed by one U9B binding."""

    schema_version: str
    search_mode: str
    text_match_mode: str
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
    completion: str
    case_corpus_complete: bool
    negative_finding_scope: str
    negative_finding_permitted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_document_ids", tuple(self.candidate_document_ids))
        object.__setattr__(self, "searched_document_ids", tuple(self.searched_document_ids))
        object.__setattr__(self, "filters_applied", tuple(self.filters_applied))
        object.__setattr__(self, "matched_evidence_keys", tuple(self.matched_evidence_keys))


@dataclass(frozen=True, slots=True)
class GovernedEvidenceRef:
    """One exact immutable U8 evidence coordinate plus its separate U8 role."""

    evidence_key: str
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    original_blob_sha256: str
    extraction_profile_id: str
    chunking_profile_id: str
    page_number: int
    page_text_sha256: str
    extraction_method: str
    chunk_ordinal: int
    chunk_id: str
    evidence_binding_id: str
    binding_class: str
    bound_text_role: str
    chunk_text_sha256: str
    chunk_text_byte_length: int
    citation: str
    evidence_role: str
    role_rule_id: str
    role_basis: str
    source_type: str
    source_label: str
    provenance_method: str
    primary_tier: int
    primary_label: str


@dataclass(frozen=True, slots=True)
class GovernedPropositionLink:
    """Exact frozen proposition payload already attached to an EvidenceUse."""

    source_proposition_index: int
    text: str
    status: str
    confidence: str
    rationale: str
    evidence_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_keys", tuple(self.evidence_keys))


@dataclass(frozen=True, slots=True)
class GovernedEvidenceUse:
    """One existing analytical relationship; U9B does not infer this relationship."""

    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    element_ordinal: int
    evidence_key: str
    analytical_role: str
    mapping_relevance: str
    mapping_confidence: str
    mapping_rationale: str
    assessment_confidence: str
    assessment_rationale: str
    citation: str
    proposition_links: tuple[GovernedPropositionLink, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposition_links", tuple(self.proposition_links))

    @property
    def identity(self) -> tuple[str, str, str]:
        """Return the frozen native EvidenceUse identity."""

        return (self.issue_analysis_id, self.element_id, self.evidence_key)


@dataclass(frozen=True, slots=True)
class GovernedEvidenceUseBinding:
    """Exact bridge between one U8 evidence reference and one frozen EvidenceUse."""

    evidence: GovernedEvidenceRef
    use: GovernedEvidenceUse


@dataclass(frozen=True, slots=True)
class GovernedIssueEvidenceMap:
    """Deterministic case-level U8-to-existing-analysis evidence binding."""

    schema_version: str
    builder_version: str
    case_id: str
    source_synthesis_id: str
    source_matrices_schema_version: str
    source_matrix_builder_version: str
    source_analysis_ids: tuple[str, ...]
    coverage: GovernedSearchCoverage
    bindings: tuple[GovernedEvidenceUseBinding, ...]
    unmapped_evidence: tuple[GovernedEvidenceRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_analysis_ids", tuple(self.source_analysis_ids))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "unmapped_evidence", tuple(self.unmapped_evidence))

    @property
    def bound_evidence_keys(self) -> tuple[str, ...]:
        """Return canonical unique evidence keys having at least one analytical use."""

        return tuple(sorted({item.evidence.evidence_key for item in self.bindings}))

    @property
    def unmapped_evidence_keys(self) -> tuple[str, ...]:
        """Return U8 evidence keys having no existing analytical relationship."""

        return tuple(item.evidence_key for item in self.unmapped_evidence)


__all__ = [
    "GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION",
    "GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION",
    "GovernedEvidenceRef",
    "GovernedEvidenceUse",
    "GovernedEvidenceUseBinding",
    "GovernedIssueEvidenceMap",
    "GovernedPropositionLink",
    "GovernedSearchCoverage",
]
