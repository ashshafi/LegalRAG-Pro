"""M5-local structured legal-analysis models.

Sprint 2.3 Milestone 5 interprets the immutable M4 evidential state without
modifying evidence mappings, evidential roles, proposition assessments,
disputes or gaps.  These models therefore wrap the frozen M4 result rather than
extending the durable M1 schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .enums import Confidence
from .evidence_assessment import EvidenceAssessmentResult
from .models import DisputedMatter, EvidentialGap

LEGAL_ANALYSER_VERSION: Final[str] = "legal-analyser/1.0"


class ElementAnalysisStatus(StrEnum):
    """Describe provisional analytical state, never final legal merits."""

    WELL_SUPPORTED_ON_CURRENT_RECORD = "well_supported_on_current_record"
    PARTIALLY_SUPPORTED = "partially_supported"
    DISPUTED = "disputed"
    INSUFFICIENTLY_EVIDENCED = "insufficiently_evidenced"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class EvidenceBackedStatement:
    """One factual statement traceable to immutable M3/M4 evidence keys."""

    text: str
    evidence_keys: tuple[str, ...]
    citations: tuple[str, ...]

    def __post_init__(self) -> None:
        text = self.text.strip()
        if not text:
            raise ValueError("EvidenceBackedStatement.text must not be empty.")
        keys = tuple(dict.fromkeys(key.strip() for key in self.evidence_keys if key.strip()))
        citations = tuple(dict.fromkeys(item.strip() for item in self.citations if item.strip()))
        if not keys:
            raise ValueError("EvidenceBackedStatement must retain at least one evidence key.")
        if not citations:
            raise ValueError("EvidenceBackedStatement must retain at least one citation.")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "evidence_keys", keys)
        object.__setattr__(self, "citations", citations)


@dataclass(frozen=True, slots=True)
class ElementLegalAnalysis:
    """Structured provisional legal analysis of one frozen M4 element."""

    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    legal_question: str
    current_evidential_position: str
    established_matters: tuple[EvidenceBackedStatement, ...]
    supported_matters: tuple[EvidenceBackedStatement, ...]
    not_supported_matters: tuple[EvidenceBackedStatement, ...]
    source_assertions: tuple[EvidenceBackedStatement, ...]
    adverse_material: tuple[EvidenceBackedStatement, ...]
    corroborative_material: tuple[EvidenceBackedStatement, ...]
    contextual_material: tuple[EvidenceBackedStatement, ...]
    conflicting_material: tuple[EvidenceBackedStatement, ...]
    disputed_matters: tuple[DisputedMatter, ...]
    legal_significance: str
    limitations: tuple[str, ...]
    unresolved_matters: tuple[str, ...]
    evidential_gaps: tuple[EvidentialGap, ...]
    provisional_status: ElementAnalysisStatus
    provisional_analysis: str
    analysis_confidence: Confidence
    analyser_version: str = LEGAL_ANALYSER_VERSION

    def __post_init__(self) -> None:
        for name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "legal_question",
            "current_evidential_position",
            "legal_significance",
            "provisional_analysis",
            "analyser_version",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty.")
            object.__setattr__(self, name, value)
        for name in (
            "established_matters",
            "supported_matters",
            "not_supported_matters",
            "source_assertions",
            "adverse_material",
            "corroborative_material",
            "contextual_material",
            "conflicting_material",
            "disputed_matters",
            "limitations",
            "unresolved_matters",
            "evidential_gaps",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(
            self,
            "limitations",
            tuple(dict.fromkeys(item.strip() for item in self.limitations if item.strip())),
        )
        object.__setattr__(
            self,
            "unresolved_matters",
            tuple(dict.fromkeys(item.strip() for item in self.unresolved_matters if item.strip())),
        )
        if not isinstance(self.provisional_status, ElementAnalysisStatus):
            raise ValueError("provisional_status must be an ElementAnalysisStatus.")
        if not isinstance(self.analysis_confidence, Confidence):
            raise ValueError("analysis_confidence must be a Confidence.")
        if any(gap.related_element_id != self.element_id for gap in self.evidential_gaps):
            raise ValueError("All M5 evidential gaps must remain in their frozen M4 element.")


@dataclass(frozen=True, slots=True)
class IssueLevelSynthesis:
    """Mechanical issue-level aggregation of element analytical states."""

    well_supported_elements: tuple[str, ...] = ()
    partially_supported_elements: tuple[str, ...] = ()
    disputed_elements: tuple[str, ...] = ()
    insufficiently_evidenced_elements: tuple[str, ...] = ()
    unresolved_elements: tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        for name in (
            "well_supported_elements",
            "partially_supported_elements",
            "disputed_elements",
            "insufficiently_evidenced_elements",
            "unresolved_elements",
        ):
            object.__setattr__(
                self,
                name,
                tuple(dict.fromkeys(item.strip() for item in getattr(self, name) if item.strip())),
            )
        summary = self.summary.strip()
        if not summary:
            raise ValueError("IssueLevelSynthesis.summary must not be empty.")
        object.__setattr__(self, "summary", summary)


@dataclass(frozen=True, slots=True)
class StructuredLegalAnalysisResult:
    """M5 result wrapper retaining the exact immutable M4 assessment result."""

    assessment_result: EvidenceAssessmentResult
    element_analyses: tuple[ElementLegalAnalysis, ...]
    issue_synthesis: IssueLevelSynthesis
    overall_limitations: tuple[str, ...]
    analyser_version: str = LEGAL_ANALYSER_VERSION

    def __post_init__(self) -> None:
        version = self.analyser_version.strip()
        if not version:
            raise ValueError("analyser_version must not be empty.")
        object.__setattr__(self, "analyser_version", version)
        object.__setattr__(self, "element_analyses", tuple(self.element_analyses))
        object.__setattr__(
            self,
            "overall_limitations",
            tuple(dict.fromkeys(item.strip() for item in self.overall_limitations if item.strip())),
        )
        expected = tuple(
            item.element_id for item in self.assessment_result.element_assessments
        )
        actual = tuple(item.element_id for item in self.element_analyses)
        if expected != actual:
            raise ValueError("M5 must preserve exact frozen M4 element order.")
        analysis = self.assessment_result.assessed_analysis
        for item in self.element_analyses:
            if item.issue_definition_id != analysis.issue_definition_id:
                raise ValueError("M5 element analysis changed the issue-definition ID.")
            if item.issue_definition_version != analysis.issue_definition_version:
                raise ValueError("M5 element analysis changed the issue-definition version.")
            if item.analyser_version != version:
                raise ValueError("All M5 element analyses must use the result analyser version.")

    @property
    def case_id(self) -> str:
        return self.assessment_result.assessed_analysis.case_id

    @property
    def issue_analysis_id(self) -> str:
        return self.assessment_result.assessed_analysis.issue_analysis_id

    @property
    def issue_definition_id(self) -> str:
        return self.assessment_result.assessed_analysis.issue_definition_id

    @property
    def issue_definition_version(self) -> str:
        return self.assessment_result.assessed_analysis.issue_definition_version


__all__ = [
    "ElementAnalysisStatus",
    "ElementLegalAnalysis",
    "EvidenceBackedStatement",
    "IssueLevelSynthesis",
    "LEGAL_ANALYSER_VERSION",
    "StructuredLegalAnalysisResult",
]
