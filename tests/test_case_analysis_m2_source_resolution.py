from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrix_validation import resolve_foundation_results
from case_analysis.models import CaseAnalysisFoundation
from case_analysis_m2_helpers import make_m5_result


def test_resolves_exact_frozen_source_set_independent_of_caller_order():
    ek = make_m5_result("EK-001", issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    ra = make_m5_result("RA-001", issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    foundation = build_case_analysis_foundation((ra, ek))

    resolved = resolve_foundation_results(foundation, (ra, ek))

    assert tuple(item.issue_definition_id for item in resolved) == ("EK-001", "RA-001")


def test_missing_source_analysis_fails_closed():
    ek = make_m5_result("EK-001")
    ra = make_m5_result("RA-001")
    foundation = build_case_analysis_foundation((ek, ra))

    with pytest.raises(ValueError, match="match the CaseAnalysisFoundation exactly"):
        resolve_foundation_results(foundation, (ek,))


def test_extra_source_analysis_fails_closed():
    ek = make_m5_result("EK-001")
    foundation = build_case_analysis_foundation((ek,))
    ra = make_m5_result("RA-001")

    with pytest.raises(ValueError, match="extra"):
        resolve_foundation_results(foundation, (ek, ra))


def test_duplicate_source_analysis_fails_closed():
    ek = make_m5_result("EK-001")
    foundation = build_case_analysis_foundation((ek,))

    with pytest.raises(ValueError, match="Duplicate issue_analysis_id"):
        resolve_foundation_results(foundation, (ek, ek))


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("issue_definition_id", "RA-001"),
        ("issue_definition_version", "9.9"),
        ("mapper_version", "element-mapper/9.9"),
        ("assessor_version", "element-assessor/9.9"),
        ("analyser_version", "legal-analyser/9.9"),
    ),
)
def test_lineage_mismatch_fails_closed(field_name: str, value: str):
    ek = make_m5_result("EK-001")
    foundation = build_case_analysis_foundation((ek,))
    ref = foundation.source_analyses[0]
    bad_ref = replace(ref, **{field_name: value})
    bad_foundation = CaseAnalysisFoundation(
        synthesis_id=foundation.synthesis_id,
        case_id=foundation.case_id,
        source_analyses=(bad_ref,),
        created_at=foundation.created_at,
    )

    with pytest.raises(ValueError, match="frozen foundation lineage"):
        resolve_foundation_results(bad_foundation, (ek,))
