"""M4-local evidential assessment models.

These types assess the significance of frozen Sprint 2.3 M3 mappings without
changing the durable M1 schema or mutating M3 evidence relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .enums import AnalyticalRole, Confidence
from .evidence_mapping import EvidenceMapping, MappedIssueAnalysis
from .models import DisputedMatter, EvidentialGap, IssueAnalysis

ELEMENT_ASSESSOR_VERSION: Final[str] = "element-assessor/1.0"


class PropositionAssessmentStatus(StrEnum):
    """Describe the current evidential state of a factual proposition."""

    ESTABLISHED_BY_CURRENT_EVIDENCE = "established_by_current_evidence"
    SUPPORTED_BUT_NOT_ESTABLISHED = "supported_but_not_established"
    DISPUTED = "disputed"
    UNRESOLVED = "unresolved"
    NOT_SUPPORTED_BY_CURRENT_EVIDENCE = "not_supported_by_current_evidence"


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """Assess one immutable M3 evidence mapping within its existing element."""

    mapping: EvidenceMapping
    analytical_role: AnalyticalRole
    assessment_confidence: Confidence
    assessment_rationale: str

    def __post_init__(self) -> None:
        rationale = self.assessment_rationale.strip()
        if not rationale:
            raise ValueError("assessment_rationale must not be empty.")
        object.__setattr__(self, "assessment_rationale", rationale)
        if self.analytical_role is AnalyticalRole.MISSING:
            raise ValueError("MISSING is represented by EvidentialGap, not EvidenceAssessment.")
        if not isinstance(self.assessment_confidence, Confidence):
            raise ValueError("assessment_confidence must be a Confidence.")


@dataclass(frozen=True, slots=True)
class AssessedProposition:
    """M4-local assessment of a factual proposition."""

    text: str
    status: PropositionAssessmentStatus
    confidence: Confidence
    evidence_keys: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        text = self.text.strip()
        rationale = self.rationale.strip()
        if not text:
            raise ValueError("AssessedProposition.text must not be empty.")
        if not rationale:
            raise ValueError("AssessedProposition.rationale must not be empty.")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "evidence_keys", tuple(dict.fromkeys(self.evidence_keys)))
        if not isinstance(self.status, PropositionAssessmentStatus):
            raise ValueError("status must be a PropositionAssessmentStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")


@dataclass(frozen=True, slots=True)
class ElementEvidenceAssessment:
    """Structured M4 evidential assessment for one existing legal element."""

    element_id: str
    evidence_assessments: tuple[EvidenceAssessment, ...] = ()
    assessed_propositions: tuple[AssessedProposition, ...] = ()
    disputed_matters: tuple[DisputedMatter, ...] = ()
    evidential_gaps: tuple[EvidentialGap, ...] = ()
    presently_established: tuple[str, ...] = ()
    unresolved_matters: tuple[str, ...] = ()
    assessment_confidence: Confidence = Confidence.LOW
    assessment_rationale: str = "No relevant mapped evidence was available for assessment."

    def __post_init__(self) -> None:
        element_id = self.element_id.strip()
        rationale = self.assessment_rationale.strip()
        if not element_id:
            raise ValueError("element_id must not be empty.")
        if not rationale:
            raise ValueError("assessment_rationale must not be empty.")
        object.__setattr__(self, "element_id", element_id)
        object.__setattr__(self, "assessment_rationale", rationale)
        for field_name in (
            "evidence_assessments",
            "assessed_propositions",
            "disputed_matters",
            "evidential_gaps",
            "presently_established",
            "unresolved_matters",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        if not isinstance(self.assessment_confidence, Confidence):
            raise ValueError("assessment_confidence must be a Confidence.")
        if any(item.mapping.element_id != self.element_id for item in self.evidence_assessments):
            raise ValueError("All evidence assessments must remain in their M3 element.")
        if any(gap.related_element_id != self.element_id for gap in self.evidential_gaps):
            raise ValueError("All evidential gaps must belong to this element.")

    def by_role(self, role: AnalyticalRole) -> tuple[EvidenceAssessment, ...]:
        return tuple(item for item in self.evidence_assessments if item.analytical_role is role)


@dataclass(frozen=True, slots=True)
class EvidenceAssessmentResult:
    """M4 result wrapper preserving the immutable M3 mapping result."""

    mapping_result: MappedIssueAnalysis
    assessed_analysis: IssueAnalysis
    element_assessments: tuple[ElementEvidenceAssessment, ...]
    assessor_version: str = ELEMENT_ASSESSOR_VERSION

    def __post_init__(self) -> None:
        version = self.assessor_version.strip()
        if not version:
            raise ValueError("assessor_version must not be empty.")
        object.__setattr__(self, "assessor_version", version)
        object.__setattr__(self, "element_assessments", tuple(self.element_assessments))
        original = self.mapping_result.analysis
        assessed = self.assessed_analysis
        identity_fields = (
            "issue_analysis_id",
            "case_id",
            "issue_definition_id",
            "issue_definition_version",
            "schema_version",
            "created_at",
        )
        for field_name in identity_fields:
            if getattr(original, field_name) != getattr(assessed, field_name):
                raise ValueError(f"M4 must preserve IssueAnalysis.{field_name}.")
        expected = tuple(item.element_id for item in original.elements)
        assessed_ids = tuple(item.element_id for item in assessed.elements)
        result_ids = tuple(item.element_id for item in self.element_assessments)
        if expected != assessed_ids or expected != result_ids:
            raise ValueError("M4 must preserve exact M3 element order.")


__all__ = [
    "AssessedProposition",
    "ELEMENT_ASSESSOR_VERSION",
    "ElementEvidenceAssessment",
    "EvidenceAssessment",
    "EvidenceAssessmentResult",
    "PropositionAssessmentStatus",
]
