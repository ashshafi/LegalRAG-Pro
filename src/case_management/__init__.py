"""Case management domain and persistence components."""

from case_management.access import (
    MatterAccessContext,
    MatterMembership,
    MatterRole,
    MembershipStatus,
    UserIdentity,
)
from case_management.document_context import (
    CASE_ID_METADATA_KEY,
    build_chunk_metadata,
    build_document_id,
    document_names_from_metadatas,
    normalise_case_id,
)
from case_management.migration import (
    LegacyAssignmentPlan,
    apply_legacy_assignment,
    assign_legacy_document,
    build_legacy_assignment_plan,
    list_legacy_documents,
)
from case_management.models import Case
from case_management.repository import CaseNotFoundError, CaseRepository, MatterAccessError
from case_management.retrieval_scope import build_retrieval_filter

__all__ = [
    "CASE_ID_METADATA_KEY",
    "Case",
    "CaseNotFoundError",
    "CaseRepository",
    "MatterAccessError",
    "LegacyAssignmentPlan",
    "MatterAccessContext",
    "MatterMembership",
    "MatterRole",
    "MembershipStatus",
    "apply_legacy_assignment",
    "assign_legacy_document",
    "build_chunk_metadata",
    "build_document_id",
    "document_names_from_metadatas",
    "build_legacy_assignment_plan",
    "build_retrieval_filter",
    "list_legacy_documents",
    "normalise_case_id",
    "UserIdentity",
]
