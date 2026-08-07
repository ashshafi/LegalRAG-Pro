from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.offline_cutover import (
    OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
    OfflineCutoverPlanningError,
    prepare_offline_cutover_plan,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"


def sha(char: str) -> str:
    return "sha256:" + char * 64


def ready_report() -> SimpleNamespace:
    return SimpleNamespace(
        schema_version="production-shadow-build-report/1.0",
        case_id=CASE_ID,
        production_shadow_build_report_id=sha("1"),
        active_db_pre_tree_sha256=sha("2"),
        active_db_backup_tree_sha256=sha("2"),
        source_store_post_tree_sha256=sha("3"),
        shadow_tree_sha256=sha("4"),
        production_prospective_row_count=393,
        shadow_exact_row_count=393,
        shadow_missing_row_count=0,
        shadow_conflicting_row_count=0,
        shadow_unexpected_row_count=0,
        shadow_legacy_row_count=0,
        backup_verified=True,
        all_documents_production_verified=True,
        shadow_exact_set_verified=True,
        shadow_complete_for_pfcr3=True,
        modified_preexisting_source_store_file_count=0,
        deleted_preexisting_source_store_file_count=0,
        new_analysis_receipt_count=0,
        new_projection_binding_count=0,
        blockers=(),
    )


def changed(report: SimpleNamespace, **values: object) -> SimpleNamespace:
    data = vars(report).copy()
    data.update(values)
    return SimpleNamespace(**data)


def test_ready_pfcr2_report_produces_non_mutating_cutover_plan() -> None:
    plan = prepare_offline_cutover_plan(report=ready_report())

    assert plan.schema_version == OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION
    assert plan.case_id == CASE_ID
    assert plan.expected_shadow_row_count == 393
    assert plan.active_db_pre_tree_sha256 == sha("2")
    assert plan.active_db_backup_tree_sha256 == sha("2")
    assert plan.source_store_post_tree_sha256 == sha("3")
    assert plan.shadow_tree_sha256 == sha("4")


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    (
        ("backup_verified", False, "backup_not_verified"),
        (
            "all_documents_production_verified",
            False,
            "documents_not_verified",
        ),
        ("shadow_exact_set_verified", False, "shadow_not_exact"),
        (
            "shadow_complete_for_pfcr3",
            False,
            "shadow_not_pfcr3_ready",
        ),
    ),
)
def test_required_readiness_flag_fails_closed(
    field: str,
    value: object,
    blocker: str,
) -> None:
    report = changed(ready_report(), **{field: value})

    with pytest.raises(
        OfflineCutoverPlanningError,
        match=blocker,
    ):
        prepare_offline_cutover_plan(report=report)


def test_backup_must_match_frozen_active_database_tree() -> None:
    report = changed(
        ready_report(),
        active_db_backup_tree_sha256=sha("5"),
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match="backup_tree_mismatch",
    ):
        prepare_offline_cutover_plan(report=report)


def test_shadow_exact_count_must_equal_prospective_population() -> None:
    report = changed(
        ready_report(),
        shadow_exact_row_count=392,
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match="shadow_row_count_mismatch",
    ):
        prepare_offline_cutover_plan(report=report)


@pytest.mark.parametrize(
    ("field", "blocker"),
    (
        ("shadow_missing_row_count", "shadow_missing_row"),
        ("shadow_conflicting_row_count", "shadow_conflicting_row"),
        ("shadow_unexpected_row_count", "shadow_unexpected_row"),
        ("shadow_legacy_row_count", "shadow_legacy_row"),
    ),
)
def test_any_shadow_population_defect_blocks_pfcr3(
    field: str,
    blocker: str,
) -> None:
    report = changed(
        ready_report(),
        **{field: 1},
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match=blocker,
    ):
        prepare_offline_cutover_plan(report=report)


@pytest.mark.parametrize(
    ("field", "blocker"),
    (
        (
            "modified_preexisting_source_store_file_count",
            "source_store_preexisting_modified",
        ),
        (
            "deleted_preexisting_source_store_file_count",
            "source_store_preexisting_deleted",
        ),
        (
            "new_analysis_receipt_count",
            "analysis_receipt_created",
        ),
        (
            "new_projection_binding_count",
            "projection_binding_created",
        ),
    ),
)
def test_forbidden_pfcr2_side_effect_blocks_pfcr3(
    field: str,
    blocker: str,
) -> None:
    report = changed(
        ready_report(),
        **{field: 1},
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match=blocker,
    ):
        prepare_offline_cutover_plan(report=report)


def test_upstream_pfcr2_blocker_blocks_pfcr3() -> None:
    report = changed(
        ready_report(),
        blockers=("shadow_missing_row",),
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match="report_has_blockers",
    ):
        prepare_offline_cutover_plan(report=report)


def test_missing_report_field_fails_closed() -> None:
    report = ready_report()
    delattr(report, "shadow_tree_sha256")

    with pytest.raises(
        OfflineCutoverPlanningError,
        match="report_field_missing:shadow_tree_sha256",
    ):
        prepare_offline_cutover_plan(report=report)


def test_invalid_integer_field_fails_closed() -> None:
    report = changed(
        ready_report(),
        shadow_exact_row_count=True,
    )

    with pytest.raises(
        OfflineCutoverPlanningError,
        match="shadow_row_count_invalid:shadow_exact_row_count",
    ):
        prepare_offline_cutover_plan(report=report)


def test_pfcr3_m1_module_has_no_database_mutation_capability() -> None:
    module = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "source_evidence"
        / "offline_cutover.py"
    )

    text = module.read_text(encoding="utf-8")

    forbidden = (
        "chromadb",
        "PersistentClient",
        "os.replace",
        "os.rename",
        "Path.replace",
        "Path.rename",
        "shutil.move",
        "shutil.rmtree",
        "unlink(",
        "remove(",
        "rmdir(",
    )

    for token in forbidden:
        assert token not in text


def test_pfcr3_m1_public_api_is_planning_only() -> None:
    import source_evidence.offline_cutover as module

    assert module.__all__ == [
        "OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION",
        "OfflineCutoverBlocker",
        "OfflineCutoverPlan",
        "OfflineCutoverPlanningError",
        "prepare_offline_cutover_plan",
    ]
