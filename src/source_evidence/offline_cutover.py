"""PFCR3 offline-cutover eligibility planning.

PFCR3 Milestone 1 is deliberately non-mutating.  It validates the frozen
PFCR2 production-shadow result and produces a deterministic immutable plan
describing the state that a later, separately authorised offline-cutover
implementation would be permitted to consume.

This module does not activate, replace, rename, delete, retire, open, or
write any Chroma database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from source_evidence.identity import canonical_uuid, validate_sha256_id


OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION = "offline-cutover-plan/1.0"
PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION = (
    "production-shadow-build-report/1.0"
)


class OfflineCutoverPlanningError(RuntimeError):
    """Raised when PFCR3 eligibility cannot be established safely."""

    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = tuple(blockers)
        message = (
            "PFCR3 offline cutover is not eligible: "
            + ", ".join(self.blockers)
        )
        super().__init__(message)


class OfflineCutoverBlocker(StrEnum):
    """Deterministic PFCR3 planning blockers."""

    REPORT_FIELD_MISSING = "report_field_missing"
    REPORT_SCHEMA_MISMATCH = "report_schema_mismatch"
    CASE_ID_INVALID = "case_id_invalid"
    REPORT_ID_INVALID = "report_id_invalid"
    TREE_ID_INVALID = "tree_id_invalid"
    REPORT_HAS_BLOCKERS = "report_has_blockers"
    BACKUP_NOT_VERIFIED = "backup_not_verified"
    BACKUP_TREE_MISMATCH = "backup_tree_mismatch"
    DOCUMENTS_NOT_VERIFIED = "documents_not_verified"
    SHADOW_NOT_EXACT = "shadow_not_exact"
    SHADOW_NOT_PFCR3_READY = "shadow_not_pfcr3_ready"
    SHADOW_ROW_COUNT_INVALID = "shadow_row_count_invalid"
    SHADOW_ROW_COUNT_MISMATCH = "shadow_row_count_mismatch"
    SHADOW_MISSING_ROW = "shadow_missing_row"
    SHADOW_CONFLICTING_ROW = "shadow_conflicting_row"
    SHADOW_UNEXPECTED_ROW = "shadow_unexpected_row"
    SHADOW_LEGACY_ROW = "shadow_legacy_row"
    SOURCE_STORE_PREEXISTING_MODIFIED = (
        "source_store_preexisting_modified"
    )
    SOURCE_STORE_PREEXISTING_DELETED = (
        "source_store_preexisting_deleted"
    )
    ANALYSIS_RECEIPT_CREATED = "analysis_receipt_created"
    PROJECTION_BINDING_CREATED = "projection_binding_created"


@dataclass(frozen=True, slots=True)
class OfflineCutoverPlan:
    """Immutable PFCR3 eligibility result.

    The plan is descriptive only.  Possessing a plan does not authorise or
    perform a production cutover.
    """

    schema_version: str
    case_id: str
    production_shadow_build_report_id: str
    active_db_pre_tree_sha256: str
    active_db_backup_tree_sha256: str
    source_store_post_tree_sha256: str
    shadow_tree_sha256: str
    expected_shadow_row_count: int


_REQUIRED_FIELDS = (
    "schema_version",
    "case_id",
    "production_shadow_build_report_id",
    "active_db_pre_tree_sha256",
    "active_db_backup_tree_sha256",
    "source_store_post_tree_sha256",
    "shadow_tree_sha256",
    "production_prospective_row_count",
    "shadow_exact_row_count",
    "shadow_missing_row_count",
    "shadow_conflicting_row_count",
    "shadow_unexpected_row_count",
    "shadow_legacy_row_count",
    "backup_verified",
    "all_documents_production_verified",
    "shadow_exact_set_verified",
    "shadow_complete_for_pfcr3",
    "modified_preexisting_source_store_file_count",
    "deleted_preexisting_source_store_file_count",
    "new_analysis_receipt_count",
    "new_projection_binding_count",
    "blockers",
)


def _integer_field(
    report: object,
    name: str,
    blockers: list[str],
) -> int | None:
    """Return one non-negative integer report field."""

    value = getattr(report, name)

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        blockers.append(
            f"{OfflineCutoverBlocker.SHADOW_ROW_COUNT_INVALID.value}:{name}"
        )
        return None

    return value


def _validate_tree_id(
    value: object,
    *,
    field_name: str,
    blockers: list[str],
) -> str | None:
    """Validate one deterministic tree SHA-256 identifier."""

    try:
        return validate_sha256_id(
            str(value),
            field_name=field_name,
        )
    except Exception:
        blockers.append(
            f"{OfflineCutoverBlocker.TREE_ID_INVALID.value}:{field_name}"
        )
        return None


def prepare_offline_cutover_plan(
    *,
    report: object,
) -> OfflineCutoverPlan:
    """Validate PFCR2 completion and construct a non-mutating PFCR3 plan.

    Args:
        report: Frozen PFCR2 ``ProductionShadowBuildReport``-compatible
            object.

    Returns:
        Immutable PFCR3 eligibility plan.

    Raises:
        OfflineCutoverPlanningError: If any governed prerequisite cannot be
            established exactly.
    """

    missing = tuple(
        name
        for name in _REQUIRED_FIELDS
        if not hasattr(report, name)
    )

    if missing:
        raise OfflineCutoverPlanningError(
            tuple(
                f"{OfflineCutoverBlocker.REPORT_FIELD_MISSING.value}:{name}"
                for name in missing
            )
        )

    blockers: list[str] = []

    if (
        report.schema_version
        != PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION
    ):
        blockers.append(
            OfflineCutoverBlocker.REPORT_SCHEMA_MISMATCH.value
        )

    try:
        case_id = canonical_uuid(
            str(report.case_id),
            field_name="case_id",
        )
    except Exception:
        case_id = str(report.case_id)
        blockers.append(
            OfflineCutoverBlocker.CASE_ID_INVALID.value
        )

    try:
        report_id = validate_sha256_id(
            str(report.production_shadow_build_report_id),
            field_name="production_shadow_build_report_id",
        )
    except Exception:
        report_id = str(report.production_shadow_build_report_id)
        blockers.append(
            OfflineCutoverBlocker.REPORT_ID_INVALID.value
        )

    active_pre = _validate_tree_id(
        report.active_db_pre_tree_sha256,
        field_name="active_db_pre_tree_sha256",
        blockers=blockers,
    )

    backup_tree = _validate_tree_id(
        report.active_db_backup_tree_sha256,
        field_name="active_db_backup_tree_sha256",
        blockers=blockers,
    )

    store_post = _validate_tree_id(
        report.source_store_post_tree_sha256,
        field_name="source_store_post_tree_sha256",
        blockers=blockers,
    )

    shadow_tree = _validate_tree_id(
        report.shadow_tree_sha256,
        field_name="shadow_tree_sha256",
        blockers=blockers,
    )

    report_blockers = tuple(report.blockers)

    if report_blockers:
        blockers.append(
            OfflineCutoverBlocker.REPORT_HAS_BLOCKERS.value
        )

    if report.backup_verified is not True:
        blockers.append(
            OfflineCutoverBlocker.BACKUP_NOT_VERIFIED.value
        )

    if (
        active_pre is not None
        and backup_tree is not None
        and active_pre != backup_tree
    ):
        blockers.append(
            OfflineCutoverBlocker.BACKUP_TREE_MISMATCH.value
        )

    if report.all_documents_production_verified is not True:
        blockers.append(
            OfflineCutoverBlocker.DOCUMENTS_NOT_VERIFIED.value
        )

    if report.shadow_exact_set_verified is not True:
        blockers.append(
            OfflineCutoverBlocker.SHADOW_NOT_EXACT.value
        )

    if report.shadow_complete_for_pfcr3 is not True:
        blockers.append(
            OfflineCutoverBlocker.SHADOW_NOT_PFCR3_READY.value
        )

    expected_rows = _integer_field(
        report,
        "production_prospective_row_count",
        blockers,
    )

    exact_rows = _integer_field(
        report,
        "shadow_exact_row_count",
        blockers,
    )

    missing_rows = _integer_field(
        report,
        "shadow_missing_row_count",
        blockers,
    )

    conflicting_rows = _integer_field(
        report,
        "shadow_conflicting_row_count",
        blockers,
    )

    unexpected_rows = _integer_field(
        report,
        "shadow_unexpected_row_count",
        blockers,
    )

    legacy_rows = _integer_field(
        report,
        "shadow_legacy_row_count",
        blockers,
    )

    modified_preexisting = _integer_field(
        report,
        "modified_preexisting_source_store_file_count",
        blockers,
    )

    deleted_preexisting = _integer_field(
        report,
        "deleted_preexisting_source_store_file_count",
        blockers,
    )

    analysis_receipts = _integer_field(
        report,
        "new_analysis_receipt_count",
        blockers,
    )

    projection_bindings = _integer_field(
        report,
        "new_projection_binding_count",
        blockers,
    )

    if (
        expected_rows is not None
        and exact_rows is not None
        and expected_rows != exact_rows
    ):
        blockers.append(
            OfflineCutoverBlocker.SHADOW_ROW_COUNT_MISMATCH.value
        )

    if missing_rows not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SHADOW_MISSING_ROW.value
        )

    if conflicting_rows not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SHADOW_CONFLICTING_ROW.value
        )

    if unexpected_rows not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SHADOW_UNEXPECTED_ROW.value
        )

    if legacy_rows not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SHADOW_LEGACY_ROW.value
        )

    if modified_preexisting not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SOURCE_STORE_PREEXISTING_MODIFIED.value
        )

    if deleted_preexisting not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.SOURCE_STORE_PREEXISTING_DELETED.value
        )

    if analysis_receipts not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.ANALYSIS_RECEIPT_CREATED.value
        )

    if projection_bindings not in (None, 0):
        blockers.append(
            OfflineCutoverBlocker.PROJECTION_BINDING_CREATED.value
        )

    if blockers:
        raise OfflineCutoverPlanningError(tuple(blockers))

    assert active_pre is not None
    assert backup_tree is not None
    assert store_post is not None
    assert shadow_tree is not None
    assert expected_rows is not None

    return OfflineCutoverPlan(
        schema_version=OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
        case_id=case_id,
        production_shadow_build_report_id=report_id,
        active_db_pre_tree_sha256=active_pre,
        active_db_backup_tree_sha256=backup_tree,
        source_store_post_tree_sha256=store_post,
        shadow_tree_sha256=shadow_tree,
        expected_shadow_row_count=expected_rows,
    )


__all__ = [
    "OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION",
    "OfflineCutoverBlocker",
    "OfflineCutoverPlan",
    "OfflineCutoverPlanningError",
    "prepare_offline_cutover_plan",
]
