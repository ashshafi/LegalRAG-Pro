from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.models import CaseAnalysisFoundation
from case_analysis.validation import source_reference_from_result
from case_analysis_m1_helpers import make_m5_result


def test_mixed_case_ids_fail_closed():
    first = make_m5_result(
        "EK-001",
        case_id="11111111-1111-4111-8111-111111111111",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    second = make_m5_result(
        "RA-001",
        case_id="22222222-2222-4222-8222-222222222222",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )

    with pytest.raises(ValueError, match="exactly one case_id"):
        build_case_analysis_foundation((first, second))


def test_duplicate_issue_analysis_id_fails_closed():
    shared_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    first = make_m5_result("EK-001", issue_analysis_id=shared_id)
    second = make_m5_result("RA-001", issue_analysis_id=shared_id)

    with pytest.raises(ValueError, match="Duplicate issue_analysis_id"):
        build_case_analysis_foundation((first, second))


def test_empty_source_set_fails_closed():
    with pytest.raises(ValueError, match="At least one"):
        build_case_analysis_foundation(())


def test_source_projection_preserves_m5_element_order():
    result = make_m5_result(
        "LIM-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    source = source_reference_from_result(result)

    assert source.element_ids == tuple(item.element_id for item in result.element_analyses)


def test_foundation_rejects_wrong_deterministic_synthesis_id():
    result = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    source = source_reference_from_result(result)

    with pytest.raises(ValueError, match="does not match"):
        CaseAnalysisFoundation(
            synthesis_id="99999999-9999-4999-8999-999999999999",
            case_id=result.case_id,
            source_analyses=(source,),
            created_at=source.issue_created_at,
        )


def test_source_reference_rejects_non_issue_schema():
    result = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    source = source_reference_from_result(result)

    with pytest.raises(ValueError, match="issue-analysis schema"):
        replace(source, issue_analysis_schema_version="other-schema/1.0")
