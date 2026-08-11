"""Immutable transport and lifecycle models for governed analytical authorities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from case_analysis.m2.matrices import CaseMatrices
from governed_evidence_analysis.models import GovernedEvidentialAnalysis
from governed_issue_evidence.models import GovernedIssueEvidenceMap
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult


GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION = (
    "governed-active-analytical-authority-manifest/1.0"
)
GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION = (
    "governed-active-analytical-authority-identity/1.0"
)
GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION = (
    "governed-active-analytical-authority-pointer/1.0"
)
GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION = (
    "governed-active-analytical-authority-activation/1.0"
)
GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME = "governed_analytical_authorities"


class GovernedAnalyticalAuthorityActivationAction(StrEnum):
    """Non-substantive lifecycle actions for an active authority pointer."""

    ACTIVATE = "ACTIVATE"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class GovernedAnalyticalAuthorityManifest:
    """Content manifest binding exactly four substantive analytical components."""

    schema_version: str
    identity_version: str
    case_id: str
    structured_legal_analysis_results_sha256: str
    case_matrices_sha256: str
    governed_issue_evidence_map_sha256: str
    governed_evidential_analysis_sha256: str
    source_analysis_ids: tuple[str, ...]
    authority_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_analysis_ids", tuple(self.source_analysis_ids))


@dataclass(frozen=True, slots=True)
class GovernedAnalyticalAuthorityActivePointer:
    """Tiny case-specific pointer selecting one already-published authority."""

    schema_version: str
    case_id: str
    authority_id: str
    authority_manifest_sha256: str
    activation_id: str


@dataclass(frozen=True, slots=True)
class GovernedAnalyticalAuthorityActivationReceipt:
    """Immutable lifecycle provenance for one explicit active-pointer transition."""

    schema_version: str
    case_id: str
    activation_id: str
    action: GovernedAnalyticalAuthorityActivationAction
    previous_activation_id: str | None
    previous_authority_id: str | None
    new_authority_id: str
    previous_active_pointer_sha256: str | None
    new_active_pointer_sha256: str


@dataclass(frozen=True, slots=True)
class GovernedRuntimeAnalyticalAuthority:
    """Read-only runtime envelope; it introduces no new analytical state."""

    manifest: GovernedAnalyticalAuthorityManifest
    structured_legal_analysis_results: tuple[StructuredLegalAnalysisResult, ...]
    case_matrices: CaseMatrices
    governed_issue_evidence_map: GovernedIssueEvidenceMap
    governed_evidential_analysis: GovernedEvidentialAnalysis
    active_pointer: GovernedAnalyticalAuthorityActivePointer
    activation_receipt: GovernedAnalyticalAuthorityActivationReceipt

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "structured_legal_analysis_results",
            tuple(self.structured_legal_analysis_results),
        )


__all__ = [
    "GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME",
    "GovernedAnalyticalAuthorityActivationAction",
    "GovernedAnalyticalAuthorityActivationReceipt",
    "GovernedAnalyticalAuthorityActivePointer",
    "GovernedAnalyticalAuthorityManifest",
    "GovernedRuntimeAnalyticalAuthority",
]
