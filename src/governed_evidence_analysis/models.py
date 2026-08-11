"""Immutable U9C-B1 models for governed evidential provenance and quality observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION = "governed-evidential-analysis-schema/1.0"
GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION = "governed-evidential-analysis-identity/1.0"


class GovernedEvidenceObservationType(StrEnum):
    """Deterministic observations that are losslessly provable from frozen U9B state."""

    ANALYTICALLY_BOUND = "analytically_bound"
    ANALYTICALLY_UNMAPPED = "analytically_unmapped"
    PRIMARY_SOURCE_BOUND = "primary_source_bound"
    PRIMARY_SOURCE_UNMAPPED = "primary_source_unmapped"
    ADVERSE_ROLE_PRESENT = "adverse_role_present"
    CONFLICTING_ROLE_PRESENT = "conflicting_role_present"


@dataclass(frozen=True, slots=True, order=True)
class GovernedEvidenceUseCoordinate:
    """Natural frozen identity of one U9B analytical evidence use."""

    issue_analysis_id: str
    element_id: str
    evidence_key: str


@dataclass(frozen=True, slots=True)
class GovernedEvidenceObservation:
    """One source-bound U9C observation; no evidential weighting or legal inference."""

    observation_type: GovernedEvidenceObservationType
    use_coordinate: GovernedEvidenceUseCoordinate | None = None


@dataclass(frozen=True, slots=True)
class GovernedEvidenceAssessment:
    """Complete U9C structural assessment for one U9B evidence key."""

    evidence_key: str
    use_coordinates: tuple[GovernedEvidenceUseCoordinate, ...]
    observations: tuple[GovernedEvidenceObservation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "use_coordinates", tuple(self.use_coordinates))
        object.__setattr__(self, "observations", tuple(self.observations))


@dataclass(frozen=True, slots=True)
class GovernedEvidentialAnalysis:
    """Case-level U9C overlay bound exactly to one canonical frozen U9B map."""

    schema_version: str
    identity_version: str
    case_id: str
    source_u9b_sha256: str
    analysis_id: str
    evidence_assessments: tuple[GovernedEvidenceAssessment, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_assessments", tuple(self.evidence_assessments))


__all__ = [
    "GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION",
    "GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION",
    "GovernedEvidenceAssessment",
    "GovernedEvidenceObservation",
    "GovernedEvidenceObservationType",
    "GovernedEvidenceUseCoordinate",
    "GovernedEvidentialAnalysis",
]
