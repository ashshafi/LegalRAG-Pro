from __future__ import annotations

import copy
from datetime import datetime, timezone

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.models import (
    CASE_SYNTHESIS_SCHEMA_VERSION,
    CASE_SYNTHESISER_VERSION,
    derive_synthesis_id,
)
from case_analysis.serialization import dumps_case_analysis_foundation

from case_analysis_m1_helpers import DEFAULT_CASE_ID, make_m5_result


def test_foundation_builds_from_one_completed_m5_analysis():
    result = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    foundation = build_case_analysis_foundation((result,))

    assert foundation.case_id == DEFAULT_CASE_ID
    assert foundation.source_issue_analysis_ids == (result.issue_analysis_id,)
    assert foundation.schema_version == CASE_SYNTHESIS_SCHEMA_VERSION
    assert foundation.synthesiser_version == CASE_SYNTHESISER_VERSION


def test_foundation_supports_partial_case_source_sets():
    ek = make_m5_result("EK-001", issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    ra = make_m5_result("RA-001", issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

    foundation = build_case_analysis_foundation((ek, ra))

    assert len(foundation.source_analyses) == 2
    assert {item.issue_definition_id for item in foundation.source_analyses} == {
        "EK-001",
        "RA-001",
    }


def test_foundation_preserves_complete_sprint_23_lineage_reference():
    result = make_m5_result(
        "DA-001",
        issue_analysis_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )

    foundation = build_case_analysis_foundation((result,))
    source = foundation.source_analyses[0]
    assessed = result.assessment_result.assessed_analysis

    assert source.case_id == result.case_id
    assert source.issue_analysis_id == result.issue_analysis_id
    assert source.issue_definition_id == result.issue_definition_id
    assert source.issue_definition_version == result.issue_definition_version
    assert source.issue_name == assessed.issue_name
    assert source.issue_analysis_schema_version == assessed.schema_version
    assert source.issue_created_at == assessed.created_at
    assert source.element_ids == tuple(item.element_id for item in result.element_analyses)
    assert source.mapper_version == result.assessment_result.mapping_result.mapper_version
    assert source.assessor_version == result.assessment_result.assessor_version
    assert source.analyser_version == result.analyser_version


def test_source_order_does_not_change_identity_or_default_serialized_output():
    ek = make_m5_result("EK-001", issue_analysis_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    ra = make_m5_result("RA-001", issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    lim = make_m5_result("LIM-001", issue_analysis_id="ffffffff-ffff-4fff-8fff-ffffffffffff")

    first = build_case_analysis_foundation((ek, ra, lim))
    second = build_case_analysis_foundation((lim, ek, ra))

    assert first == second
    assert first.synthesis_id == second.synthesis_id
    assert dumps_case_analysis_foundation(first) == dumps_case_analysis_foundation(second)
    assert first.source_issue_analysis_ids == tuple(sorted(first.source_issue_analysis_ids))


def test_synthesis_id_uses_only_immutable_source_set_not_created_at_metadata():
    result = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    earlier = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)

    first = build_case_analysis_foundation((result,), created_at=earlier)
    second = build_case_analysis_foundation((result,), created_at=later)

    assert first.synthesis_id == second.synthesis_id
    assert first.created_at != second.created_at
    assert first.synthesis_id == derive_synthesis_id(
        case_id=DEFAULT_CASE_ID,
        source_issue_analysis_ids=(result.issue_analysis_id,),
    )


def test_foundation_construction_does_not_mutate_frozen_m5_inputs():
    results = (
        make_m5_result("EK-001", issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        make_m5_result("RA-001", issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    before = copy.deepcopy(results)

    build_case_analysis_foundation(results)

    assert results == before
