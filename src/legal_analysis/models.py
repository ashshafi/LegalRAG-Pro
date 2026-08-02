"""Typed domain models for Sprint 2.3 structured legal analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable
from uuid import UUID, uuid4

from evidence_classification import EvidenceSourceType

from .enums import (
    AnalysisStatus,
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    IssueDefinitionStatus,
    Materiality,
    ProvenanceBasis,
    ProvenanceConfidence,
)

ISSUE_ANALYSIS_SCHEMA_VERSION = "issue-analysis-schema/1.0"
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_DEFINITION_ID_RE = re.compile(r"^[A-Z]{2,5}-\d{3}$")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _clean_required(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(cleaned for value in values if (cleaned := value.strip()))


def _ensure_timezone_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _ensure_uuid(value: str, *, field_name: str) -> None:
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _ensure_version(value: str, *, field_name: str) -> None:
    if not _VERSION_RE.fullmatch(value):
        raise ValueError(f"{field_name} must use numeric version form such as '1.0'.")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Durable reference to one item of evidence used in legal analysis.

    Sprint 2.3 reuses ``EvidenceSourceType`` from Sprint 2.2 but stores stable
    values rather than depending on Sprint 2.2's runtime retrieval objects.
    """

    document_name: str
    summary: str
    source_type: EvidenceSourceType
    evidence_status: EvidenceStatus
    analytical_role: AnalyticalRole
    citation: str
    document_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    provenance_type: EvidenceSourceType | None = None
    provenance_basis: ProvenanceBasis = ProvenanceBasis.UNKNOWN
    provenance_confidence: ProvenanceConfidence = ProvenanceConfidence.LOW
    date: date | None = None
    author: str | None = None
    parties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalise the evidence reference."""

        object.__setattr__(
            self,
            "document_name",
            _clean_required(self.document_name, field_name="document_name"),
        )
        object.__setattr__(
            self,
            "summary",
            _clean_required(self.summary, field_name="summary"),
        )
        object.__setattr__(
            self,
            "citation",
            _clean_required(self.citation, field_name="citation"),
        )
        object.__setattr__(self, "document_id", _clean_optional(self.document_id))
        object.__setattr__(self, "chunk_id", _clean_optional(self.chunk_id))
        object.__setattr__(self, "author", _clean_optional(self.author))
        object.__setattr__(self, "parties", _clean_strings(self.parties))
        if not isinstance(self.source_type, EvidenceSourceType):
            raise ValueError("source_type must be an EvidenceSourceType.")
        if not isinstance(self.evidence_status, EvidenceStatus):
            raise ValueError("evidence_status must be an EvidenceStatus.")
        if not isinstance(self.analytical_role, AnalyticalRole):
            raise ValueError("analytical_role must be an AnalyticalRole.")
        if not isinstance(self.provenance_basis, ProvenanceBasis):
            raise ValueError("provenance_basis must be a ProvenanceBasis.")
        if not isinstance(self.provenance_confidence, ProvenanceConfidence):
            raise ValueError("provenance_confidence must be a ProvenanceConfidence.")
        if self.page is not None and self.page < 1:
            raise ValueError("page must be 1 or greater when supplied.")
        if self.provenance_type is None:
            object.__setattr__(self, "provenance_type", self.source_type)
        elif not isinstance(self.provenance_type, EvidenceSourceType):
            raise ValueError("provenance_type must be an EvidenceSourceType.")


@dataclass(frozen=True, slots=True)
class Proposition:
    """Represent a proposition being tested, supported or disputed."""

    text: str
    status: EvidenceStatus
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...] = ()
    proposition_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate proposition identity and content."""

        _ensure_uuid(self.proposition_id, field_name="proposition_id")
        object.__setattr__(
            self, "text", _clean_required(self.text, field_name="proposition text")
        )
        if not isinstance(self.status, EvidenceStatus):
            raise ValueError("Proposition.status must be an EvidenceStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("Proposition.confidence must be a Confidence.")
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True, slots=True)
class DisputedMatter:
    """Represent a conflict that the current evidence does not resolve."""

    proposition: str
    claimant_position: str | None = None
    respondent_position: str | None = None
    claimant_evidence: tuple[EvidenceReference, ...] = ()
    respondent_evidence: tuple[EvidenceReference, ...] = ()
    contemporaneous_evidence: tuple[EvidenceReference, ...] = ()
    presently_established: str | None = None
    remains_unresolved: str | None = None
    disputed_matter_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate disputed-matter content."""

        _ensure_uuid(self.disputed_matter_id, field_name="disputed_matter_id")
        object.__setattr__(
            self,
            "proposition",
            _clean_required(self.proposition, field_name="disputed proposition"),
        )
        for name in (
            "claimant_position",
            "respondent_position",
            "presently_established",
            "remains_unresolved",
        ):
            object.__setattr__(self, name, _clean_optional(getattr(self, name)))
        object.__setattr__(self, "claimant_evidence", tuple(self.claimant_evidence))
        object.__setattr__(self, "respondent_evidence", tuple(self.respondent_evidence))
        object.__setattr__(
            self, "contemporaneous_evidence", tuple(self.contemporaneous_evidence)
        )
        if not any(
            (
                self.claimant_position,
                self.respondent_position,
                self.claimant_evidence,
                self.respondent_evidence,
                self.contemporaneous_evidence,
                self.presently_established,
                self.remains_unresolved,
            )
        ):
            raise ValueError("A disputed matter must contain at least one position or evidence item.")


@dataclass(frozen=True, slots=True)
class EvidentialGap:
    """Represent material evidence missing from the current analysis."""

    description: str
    related_element_id: str
    materiality: Materiality
    reason: str
    suggested_evidence_target: str | None = None
    gap_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate evidential-gap content."""

        _ensure_uuid(self.gap_id, field_name="gap_id")
        object.__setattr__(
            self,
            "description",
            _clean_required(self.description, field_name="gap description"),
        )
        object.__setattr__(
            self,
            "related_element_id",
            _clean_required(self.related_element_id, field_name="related_element_id"),
        )
        object.__setattr__(
            self, "reason", _clean_required(self.reason, field_name="gap reason")
        )
        object.__setattr__(
            self,
            "suggested_evidence_target",
            _clean_optional(self.suggested_evidence_target),
        )
        if not isinstance(self.materiality, Materiality):
            raise ValueError("materiality must be a Materiality.")


@dataclass(frozen=True, slots=True)
class ElementAnalysis:
    """Structured analysis of one controlled legal element."""

    element_id: str
    element_name: str
    question_to_determine: str
    propositions: tuple[Proposition, ...] = ()
    supporting_evidence: tuple[EvidenceReference, ...] = ()
    adverse_evidence: tuple[EvidenceReference, ...] = ()
    corroborative_evidence: tuple[EvidenceReference, ...] = ()
    neutral_evidence: tuple[EvidenceReference, ...] = ()
    conflicting_evidence: tuple[EvidenceReference, ...] = ()
    disputed_matters: tuple[DisputedMatter, ...] = ()
    inferences: tuple[Proposition, ...] = ()
    evidential_gaps: tuple[EvidentialGap, ...] = ()
    respondent_position: tuple[str, ...] = ()
    legal_analysis: str | None = None
    assessment: str | None = None
    confidence: Confidence | None = None

    def __post_init__(self) -> None:
        """Validate element identity and internal references."""

        object.__setattr__(
            self, "element_id", _clean_required(self.element_id, field_name="element_id")
        )
        object.__setattr__(
            self,
            "element_name",
            _clean_required(self.element_name, field_name="element_name"),
        )
        object.__setattr__(
            self,
            "question_to_determine",
            _clean_required(
                self.question_to_determine,
                field_name="question_to_determine",
            ),
        )
        object.__setattr__(
            self, "respondent_position", _clean_strings(self.respondent_position)
        )
        object.__setattr__(self, "legal_analysis", _clean_optional(self.legal_analysis))
        object.__setattr__(self, "assessment", _clean_optional(self.assessment))
        for name in (
            "propositions",
            "supporting_evidence",
            "adverse_evidence",
            "corroborative_evidence",
            "neutral_evidence",
            "conflicting_evidence",
            "disputed_matters",
            "inferences",
            "evidential_gaps",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if self.confidence is not None and not isinstance(self.confidence, Confidence):
            raise ValueError("ElementAnalysis.confidence must be a Confidence when supplied.")
        role_buckets = (
            (self.supporting_evidence, AnalyticalRole.SUPPORTING, "supporting_evidence"),
            (self.adverse_evidence, AnalyticalRole.ADVERSE, "adverse_evidence"),
            (self.corroborative_evidence, AnalyticalRole.CORROBORATIVE, "corroborative_evidence"),
            (self.neutral_evidence, AnalyticalRole.NEUTRAL, "neutral_evidence"),
            (self.conflicting_evidence, AnalyticalRole.CONFLICTING, "conflicting_evidence"),
        )
        for evidence_items, expected_role, field_name in role_buckets:
            if any(item.analytical_role is not expected_role for item in evidence_items):
                raise ValueError(
                    f"{field_name} may contain only evidence with analytical_role={expected_role.value}."
                )
        for gap in self.evidential_gaps:
            if gap.related_element_id != self.element_id:
                raise ValueError(
                    "EvidentialGap.related_element_id must match its ElementAnalysis.element_id."
                )


@dataclass(frozen=True, slots=True)
class IssueElementDefinition:
    """Controlled definition of one legal question within an issue."""

    element_id: str
    name: str
    question_to_determine: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate legal-element definition."""

        object.__setattr__(
            self, "element_id", _clean_required(self.element_id, field_name="element_id")
        )
        object.__setattr__(self, "name", _clean_required(self.name, field_name="name"))
        object.__setattr__(
            self,
            "question_to_determine",
            _clean_required(
                self.question_to_determine,
                field_name="question_to_determine",
            ),
        )
        object.__setattr__(self, "notes", _clean_strings(self.notes))


@dataclass(frozen=True, slots=True)
class IssueDefinition:
    """Versioned controlled legal-domain definition."""

    definition_id: str
    name: str
    version: str
    legal_framework: tuple[str, ...]
    description: str
    elements: tuple[IssueElementDefinition, ...]
    status: IssueDefinitionStatus = IssueDefinitionStatus.ACTIVE
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the controlled issue definition."""

        definition_id = _clean_required(self.definition_id, field_name="definition_id")
        if not _DEFINITION_ID_RE.fullmatch(definition_id):
            raise ValueError("definition_id must use a stable form such as 'RA-001'.")
        object.__setattr__(self, "definition_id", definition_id)
        object.__setattr__(self, "name", _clean_required(self.name, field_name="name"))
        version = _clean_required(self.version, field_name="version")
        _ensure_version(version, field_name="version")
        object.__setattr__(self, "version", version)
        object.__setattr__(
            self,
            "description",
            _clean_required(self.description, field_name="description"),
        )
        object.__setattr__(self, "legal_framework", _clean_strings(self.legal_framework))
        object.__setattr__(self, "notes", _clean_strings(self.notes))
        object.__setattr__(self, "elements", tuple(self.elements))
        if not isinstance(self.status, IssueDefinitionStatus):
            raise ValueError("IssueDefinition.status must be an IssueDefinitionStatus.")
        if not self.legal_framework:
            raise ValueError("IssueDefinition.legal_framework must not be empty.")
        if not self.elements:
            raise ValueError("IssueDefinition.elements must not be empty.")
        element_ids = [element.element_id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("IssueDefinition element IDs must be unique within a version.")

    @property
    def key(self) -> tuple[str, str]:
        """Return the immutable registry key for this definition version."""

        return (self.definition_id, self.version)


@dataclass(frozen=True, slots=True)
class IssueAnalysis:
    """Durable structured legal analysis record independent of prose output."""

    case_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    user_question: str
    legal_framework: tuple[str, ...]
    elements: tuple[ElementAnalysis, ...]
    analysis_status: AnalysisStatus = AnalysisStatus.PRELIMINARY
    issue_analysis_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    schema_version: str = ISSUE_ANALYSIS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate the durable analysis record."""

        _ensure_uuid(self.issue_analysis_id, field_name="issue_analysis_id")
        _ensure_uuid(self.case_id, field_name="case_id")
        definition_id = _clean_required(
            self.issue_definition_id, field_name="issue_definition_id"
        )
        if not _DEFINITION_ID_RE.fullmatch(definition_id):
            raise ValueError("issue_definition_id must use a form such as 'RA-001'.")
        object.__setattr__(self, "issue_definition_id", definition_id)
        version = _clean_required(
            self.issue_definition_version, field_name="issue_definition_version"
        )
        _ensure_version(version, field_name="issue_definition_version")
        object.__setattr__(self, "issue_definition_version", version)
        object.__setattr__(
            self, "issue_name", _clean_required(self.issue_name, field_name="issue_name")
        )
        object.__setattr__(
            self,
            "user_question",
            _clean_required(self.user_question, field_name="user_question"),
        )
        object.__setattr__(self, "legal_framework", _clean_strings(self.legal_framework))
        object.__setattr__(self, "elements", tuple(self.elements))
        if not isinstance(self.analysis_status, AnalysisStatus):
            raise ValueError("analysis_status must be an AnalysisStatus.")
        if not self.legal_framework:
            raise ValueError("IssueAnalysis.legal_framework must not be empty.")
        if not self.elements:
            raise ValueError("IssueAnalysis.elements must not be empty.")
        element_ids = [element.element_id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("IssueAnalysis element IDs must be unique.")
        _ensure_timezone_aware(self.created_at, field_name="created_at")
        schema_version = _clean_required(self.schema_version, field_name="schema_version")
        if not schema_version.startswith("issue-analysis-schema/"):
            raise ValueError("schema_version must identify the issue-analysis schema.")
        object.__setattr__(self, "schema_version", schema_version)

    @classmethod
    def from_definition(
        cls,
        *,
        case_id: str,
        user_question: str,
        definition: IssueDefinition,
        analysis_status: AnalysisStatus = AnalysisStatus.PRELIMINARY,
    ) -> "IssueAnalysis":
        """Create an empty analysis record from one controlled definition."""

        elements = tuple(
            ElementAnalysis(
                element_id=element.element_id,
                element_name=element.name,
                question_to_determine=element.question_to_determine,
            )
            for element in definition.elements
        )
        return cls(
            case_id=case_id,
            issue_definition_id=definition.definition_id,
            issue_definition_version=definition.version,
            issue_name=definition.name,
            user_question=user_question,
            legal_framework=definition.legal_framework,
            elements=elements,
            analysis_status=analysis_status,
        )
