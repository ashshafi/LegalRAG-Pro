"""Durable Sprint 2.4 Milestone 2 issue/evidence matrix models.

Milestone 2 is a downstream projection over immutable Sprint 2.3 analyses and
an immutable Sprint 2.4 M1 foundation.  These models organise that frozen state
without changing legal-element status, evidential role, proposition status or
stable evidence identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

from evidence_classification import EvidenceSourceType
from legal_analysis.enums import (
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.evidence_mapping import EvidenceRelevance
from legal_analysis.legal_analysis import ElementAnalysisStatus, EvidenceBackedStatement

CASE_MATRICES_SCHEMA_VERSION: Final[str] = "case-matrices-schema/1.0"
CASE_MATRIX_BUILDER_VERSION: Final[str] = "case-matrix-builder/1.0"


def _required(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _unique_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    cleaned = tuple(str(item).strip() for item in values if str(item).strip())
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must contain unique values.")
    return cleaned


@dataclass(frozen=True, slots=True)
class EvidencePropositionLink:
    """Trace one M4 proposition to an evidence use without inventing identity."""

    source_proposition_index: int
    text: str
    status: PropositionAssessmentStatus
    confidence: Confidence
    rationale: str
    evidence_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.source_proposition_index < 0:
            raise ValueError("source_proposition_index must be zero or greater.")
        object.__setattr__(self, "text", _required(self.text, field_name="text"))
        object.__setattr__(self, "rationale", _required(self.rationale, field_name="rationale"))
        object.__setattr__(
            self,
            "evidence_keys",
            _unique_strings(tuple(self.evidence_keys), field_name="evidence_keys"),
        )
        if not self.evidence_keys:
            raise ValueError("EvidencePropositionLink.evidence_keys must not be empty.")
        if not isinstance(self.status, PropositionAssessmentStatus):
            raise ValueError("status must be a PropositionAssessmentStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")


@dataclass(frozen=True, slots=True)
class EvidenceUse:
    """One authoritative M4-assessed element/evidence relationship."""

    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    element_ordinal: int
    evidence_key: str
    analytical_role: AnalyticalRole
    mapping_relevance: EvidenceRelevance
    mapping_confidence: Confidence
    mapping_rationale: str
    assessment_confidence: Confidence
    assessment_rationale: str
    proposition_links: tuple[EvidencePropositionLink, ...] = ()
    citation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="EvidenceUse.issue_analysis_id"),
        )
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "evidence_key",
            "mapping_rationale",
            "assessment_rationale",
            "citation",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        if self.element_ordinal < 0:
            raise ValueError("element_ordinal must be zero or greater.")
        if not isinstance(self.analytical_role, AnalyticalRole):
            raise ValueError("analytical_role must be an AnalyticalRole.")
        if not isinstance(self.mapping_relevance, EvidenceRelevance):
            raise ValueError("mapping_relevance must be an EvidenceRelevance.")
        if not isinstance(self.mapping_confidence, Confidence):
            raise ValueError("mapping_confidence must be a Confidence.")
        if not isinstance(self.assessment_confidence, Confidence):
            raise ValueError("assessment_confidence must be a Confidence.")
        links = tuple(self.proposition_links)
        if any(self.evidence_key not in link.evidence_keys for link in links):
            raise ValueError("Every proposition link must reference EvidenceUse.evidence_key.")
        if tuple(link.source_proposition_index for link in links) != tuple(
            sorted(link.source_proposition_index for link in links)
        ):
            raise ValueError("proposition_links must preserve source proposition order.")
        object.__setattr__(self, "proposition_links", links)

    @property
    def identity(self) -> tuple[str, str, str]:
        """Return the frozen M2 logical use identity."""

        return (self.issue_analysis_id, self.element_id, self.evidence_key)


@dataclass(frozen=True, slots=True)
class CaseEvidenceRecord:
    """One canonical stable evidence identity with all assessed uses."""

    evidence_key: str
    document_name: str
    citation: str
    source_type: EvidenceSourceType
    evidence_status: EvidenceStatus
    provenance_type: EvidenceSourceType
    provenance_basis: ProvenanceBasis
    provenance_confidence: ProvenanceConfidence
    uses: tuple[EvidenceUse, ...]
    document_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    date: date | None = None
    author: str | None = None
    parties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("evidence_key", "document_name", "citation"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        object.__setattr__(self, "document_id", _optional(self.document_id))
        object.__setattr__(self, "chunk_id", _optional(self.chunk_id))
        object.__setattr__(self, "author", _optional(self.author))
        object.__setattr__(self, "parties", tuple(dict.fromkeys(str(item).strip() for item in self.parties if str(item).strip())))
        if self.page is not None and self.page < 1:
            raise ValueError("page must be 1 or greater when supplied.")
        if not isinstance(self.source_type, EvidenceSourceType):
            raise ValueError("source_type must be an EvidenceSourceType.")
        if not isinstance(self.evidence_status, EvidenceStatus):
            raise ValueError("evidence_status must be an EvidenceStatus.")
        if not isinstance(self.provenance_type, EvidenceSourceType):
            raise ValueError("provenance_type must be an EvidenceSourceType.")
        if not isinstance(self.provenance_basis, ProvenanceBasis):
            raise ValueError("provenance_basis must be a ProvenanceBasis.")
        if not isinstance(self.provenance_confidence, ProvenanceConfidence):
            raise ValueError("provenance_confidence must be a ProvenanceConfidence.")
        uses = tuple(self.uses)
        if not uses:
            raise ValueError("CaseEvidenceRecord.uses must not be empty.")
        if any(item.evidence_key != self.evidence_key for item in uses):
            raise ValueError("All evidence uses must resolve to CaseEvidenceRecord.evidence_key.")
        identities = tuple(item.identity for item in uses)
        if len(identities) != len(set(identities)):
            raise ValueError("CaseEvidenceRecord contains duplicate EvidenceUse identities.")
        object.__setattr__(self, "uses", uses)


@dataclass(frozen=True, slots=True)
class IssueElementRecord:
    """Issue-Matrix projection of one exact frozen M5 element analysis."""

    element_id: str
    element_name: str
    legal_question: str
    analysis_status: ElementAnalysisStatus
    analysis_confidence: Confidence
    established_matters: tuple[EvidenceBackedStatement, ...] = ()
    supported_matters: tuple[EvidenceBackedStatement, ...] = ()
    not_supported_matters: tuple[EvidenceBackedStatement, ...] = ()
    source_assertions: tuple[EvidenceBackedStatement, ...] = ()
    supporting_evidence_keys: tuple[str, ...] = ()
    adverse_evidence_keys: tuple[str, ...] = ()
    corroborative_evidence_keys: tuple[str, ...] = ()
    neutral_evidence_keys: tuple[str, ...] = ()
    conflicting_evidence_keys: tuple[str, ...] = ()
    disputed_matter_ids: tuple[str, ...] = ()
    evidential_gap_ids: tuple[str, ...] = ()
    unresolved_matters: tuple[str, ...] = ()
    legal_significance: str = ""
    provisional_analysis: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "element_id",
            "element_name",
            "legal_question",
            "legal_significance",
            "provisional_analysis",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        if not isinstance(self.analysis_status, ElementAnalysisStatus):
            raise ValueError("analysis_status must be an ElementAnalysisStatus.")
        if not isinstance(self.analysis_confidence, Confidence):
            raise ValueError("analysis_confidence must be a Confidence.")
        for field_name in (
            "established_matters",
            "supported_matters",
            "not_supported_matters",
            "source_assertions",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "supporting_evidence_keys",
            "adverse_evidence_keys",
            "corroborative_evidence_keys",
            "neutral_evidence_keys",
            "conflicting_evidence_keys",
            "disputed_matter_ids",
            "evidential_gap_ids",
            "unresolved_matters",
        ):
            values = tuple(str(item).strip() for item in getattr(self, field_name) if str(item).strip())
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values.")
            object.__setattr__(self, field_name, values)


@dataclass(frozen=True, slots=True)
class IssueMatrixRecord:
    """Case-wide issue-centric projection of one frozen M5 analysis."""

    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    original_user_question: str
    issue_summary: str
    element_records: tuple[IssueElementRecord, ...]
    analyser_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="IssueMatrixRecord.issue_analysis_id"),
        )
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "issue_name",
            "original_user_question",
            "issue_summary",
            "analyser_version",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        records = tuple(self.element_records)
        if not records:
            raise ValueError("IssueMatrixRecord.element_records must not be empty.")
        ids = tuple(item.element_id for item in records)
        if len(ids) != len(set(ids)):
            raise ValueError("IssueMatrixRecord.element_records must contain unique element IDs.")
        object.__setattr__(self, "element_records", records)


@dataclass(frozen=True, slots=True)
class CaseMatrices:
    """Durable M2 wrapper for deterministic issue/evidence matrix projections."""

    case_id: str
    synthesis_id: str
    source_analysis_ids: tuple[str, ...]
    issue_matrix: tuple[IssueMatrixRecord, ...]
    evidence_matrix: tuple[CaseEvidenceRecord, ...]
    schema_version: str = CASE_MATRICES_SCHEMA_VERSION
    matrix_builder_version: str = CASE_MATRIX_BUILDER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _uuid(self.case_id, field_name="CaseMatrices.case_id"))
        object.__setattr__(self, "synthesis_id", _uuid(self.synthesis_id, field_name="CaseMatrices.synthesis_id"))
        if self.schema_version != CASE_MATRICES_SCHEMA_VERSION:
            raise ValueError(f"Unsupported matrix schema {self.schema_version!r}.")
        if self.matrix_builder_version != CASE_MATRIX_BUILDER_VERSION:
            raise ValueError(f"Unsupported matrix builder {self.matrix_builder_version!r}.")
        source_ids = tuple(_uuid(item, field_name="source_analysis_id") for item in self.source_analysis_ids)
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise ValueError("source_analysis_ids must be a non-empty unique tuple.")
        object.__setattr__(self, "source_analysis_ids", source_ids)
        issue_matrix = tuple(self.issue_matrix)
        evidence_matrix = tuple(self.evidence_matrix)
        if not issue_matrix:
            raise ValueError("CaseMatrices.issue_matrix must not be empty.")
        issue_ids = tuple(item.issue_analysis_id for item in issue_matrix)
        if set(issue_ids) != set(source_ids):
            raise ValueError("Issue Matrix identities must exactly match source_analysis_ids.")
        if tuple(item.evidence_key for item in evidence_matrix) != tuple(sorted(item.evidence_key for item in evidence_matrix)):
            raise ValueError("Evidence Matrix records must use deterministic evidence-key order.")
        object.__setattr__(self, "issue_matrix", issue_matrix)
        object.__setattr__(self, "evidence_matrix", evidence_matrix)


def build_case_matrices(foundation, results) -> CaseMatrices:
    """Build both M2 matrix projections from one frozen M1 source set."""

    # Local imports avoid model/projection circular dependencies while keeping
    # the durable models in this single module.
    from .evidence_matrix import build_evidence_matrix
    from .issue_matrix import build_issue_matrix
    from .matrix_validation import resolve_foundation_results, validate_case_matrices

    resolved = resolve_foundation_results(foundation, results)
    value = CaseMatrices(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        issue_matrix=build_issue_matrix(resolved),
        evidence_matrix=build_evidence_matrix(resolved),
    )
    validate_case_matrices(value, foundation=foundation)
    return value


__all__ = [
    "CASE_MATRICES_SCHEMA_VERSION",
    "CASE_MATRIX_BUILDER_VERSION",
    "CaseEvidenceRecord",
    "CaseMatrices",
    "EvidencePropositionLink",
    "EvidenceUse",
    "IssueElementRecord",
    "IssueMatrixRecord",
    "build_case_matrices",
]
