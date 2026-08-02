"""Controlled enums for Sprint 2.3 structured legal analysis."""

from __future__ import annotations

from enum import StrEnum

from evidence_classification import EvidenceSourceType


class AnalysisStatus(StrEnum):
    """Describe analytical completeness, not prospects of success."""

    PRELIMINARY = "preliminary"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    SUBSTANTIALLY_EVIDENCED = "substantially_evidenced"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    READY_FOR_LEGAL_REVIEW = "ready_for_legal_review"


class AnalyticalRole(StrEnum):
    """Describe the role evidence plays in relation to one legal element."""

    SUPPORTING = "supporting"
    ADVERSE = "adverse"
    CORROBORATIVE = "corroborative"
    NEUTRAL = "neutral"
    CONFLICTING = "conflicting"
    MISSING = "missing"


class Confidence(StrEnum):
    """Describe evidential support for a proposition or assessment."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProvenanceBasis(StrEnum):
    """Stable provenance-basis values established by Sprint 2.2."""

    MANUAL = "manual"
    EXPLICIT_SENDER = "explicit_sender"
    SIGNATURE = "signature"
    KNOWN_DOCUMENT_AUTHOR = "known_document_author"
    CONTAINER_FALLBACK = "container_fallback"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ProvenanceConfidence(StrEnum):
    """Confidence in the attribution of an evidence source."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceStatus(StrEnum):
    """Stable evidential-status vocabulary for structured legal analysis."""

    DOCUMENTED_FACT = "documented_fact"
    SOURCE_ASSERTION = "source_assertion"
    CLAIMANT_EVIDENCE = "claimant_evidence"
    EMPLOYER_EVIDENCE = "employer_evidence"
    INDEPENDENT_MEDICAL_EVIDENCE = "independent_medical_evidence"
    OCCUPATIONAL_HEALTH_EVIDENCE = "occupational_health_evidence"
    INSURER_EVIDENCE = "insurer_evidence"
    TRIBUNAL_RECORD = "tribunal_record"
    RESPONDENT_EVIDENCE = "respondent_evidence"
    INFERENCE = "inference"
    LEGAL_ARGUMENT = "legal_argument"
    DISPUTED_MATTER = "disputed_matter"
    EVIDENCE_GAP = "evidence_gap"


class Materiality(StrEnum):
    """Describe the importance of an evidential gap to an issue."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueDefinitionStatus(StrEnum):
    """Lifecycle state of versioned controlled legal-domain data."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"


__all__ = [
    "AnalysisStatus",
    "AnalyticalRole",
    "Confidence",
    "EvidenceSourceType",
    "EvidenceStatus",
    "IssueDefinitionStatus",
    "Materiality",
    "ProvenanceBasis",
    "ProvenanceConfidence",
]
