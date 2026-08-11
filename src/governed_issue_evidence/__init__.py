"""Governed U8-to-existing-analysis evidence binding for LegalRAG Pro U9B."""

from .binding import (
    GovernedIssueEvidenceBindingError,
    build_governed_issue_evidence_map,
)
from .models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedPropositionLink,
    GovernedSearchCoverage,
)
from .serialization import (
    dumps_governed_issue_evidence_map,
    loads_governed_issue_evidence_map,
)
from .validation import (
    GovernedIssueEvidenceValidationError,
    validate_governed_issue_evidence_map,
)

__all__ = [
    "GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION",
    "GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION",
    "GovernedEvidenceRef",
    "GovernedEvidenceUse",
    "GovernedEvidenceUseBinding",
    "GovernedIssueEvidenceBindingError",
    "GovernedIssueEvidenceMap",
    "GovernedIssueEvidenceValidationError",
    "GovernedPropositionLink",
    "GovernedSearchCoverage",
    "build_governed_issue_evidence_map",
    "dumps_governed_issue_evidence_map",
    "loads_governed_issue_evidence_map",
    "validate_governed_issue_evidence_map",
]
