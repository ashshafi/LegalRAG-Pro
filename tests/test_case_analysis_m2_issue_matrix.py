from __future__ import annotations

from legal_analysis.enums import AnalyticalRole, EvidenceStatus
from evidence_classification import EvidenceSourceType

from case_analysis.m2.issue_matrix import build_issue_matrix
from case_analysis_m2_helpers import evidence, make_m5_result


def test_issue_matrix_preserves_exact_m5_status_confidence_and_element_order():
    result = make_m5_result("RA-001")
    matrix = build_issue_matrix((result,))
    record = matrix[0]

    assert tuple(item.element_id for item in record.element_records) == tuple(
        item.element_id for item in result.element_analyses
    )
    for projected, source in zip(record.element_records, result.element_analyses, strict=True):
        assert projected.analysis_status is source.provisional_status
        assert projected.analysis_confidence is source.analysis_confidence
        assert projected.legal_question == source.legal_question
        assert projected.legal_significance == source.legal_significance
        assert projected.provisional_analysis == source.provisional_analysis


def test_issue_matrix_role_buckets_come_from_m4_and_preserve_adverse_and_source_assertion():
    assertion = evidence(
        key="assertion",
        summary="Appendix asserts that CACI knew of the recommendation.",
        source_type=EvidenceSourceType.MIXED_CORRESPONDENCE,
        evidence_status=EvidenceStatus.SOURCE_ASSERTION,
    )
    respondent = evidence(
        key="respondent",
        document_name="ET3.pdf",
        summary="The respondent denies knowledge of the specific recommendation.",
        source_type=EvidenceSourceType.RESPONDENT_SUBMISSION,
        evidence_status=EvidenceStatus.RESPONDENT_EVIDENCE,
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-DIRECT-KNOWLEDGE": (assertion, respondent)},
        role_overrides={
            ("EK-DIRECT-KNOWLEDGE", "assertion"): AnalyticalRole.SUPPORTING,
            ("EK-DIRECT-KNOWLEDGE", "respondent"): AnalyticalRole.ADVERSE,
        },
    )
    element = next(
        item
        for item in build_issue_matrix((result,))[0].element_records
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )

    assert element.supporting_evidence_keys == ("assertion",)
    assert element.adverse_evidence_keys == ("respondent",)
    assert element.source_assertions
    assert element.source_assertions[0].evidence_keys == ("assertion",)


def test_issue_matrix_preserves_gap_and_dispute_source_ids_without_consolidation():
    result = make_m5_result("LIM-001")
    record = build_issue_matrix((result,))[0]

    for projected, source in zip(record.element_records, result.element_analyses, strict=True):
        assert projected.evidential_gap_ids == tuple(item.gap_id for item in source.evidential_gaps)
        assert projected.disputed_matter_ids == tuple(
            item.disputed_matter_id for item in source.disputed_matters
        )
        assert projected.unresolved_matters == source.unresolved_matters


def test_issue_matrix_copies_distinct_m5_statuses_without_reinterpretation():
    from dataclasses import replace
    from legal_analysis.legal_analysis import ElementAnalysisStatus

    result = make_m5_result("EK-001")
    statuses = (
        ElementAnalysisStatus.PARTIALLY_SUPPORTED,
        ElementAnalysisStatus.UNRESOLVED,
        ElementAnalysisStatus.DISPUTED,
    )
    changed_elements = tuple(
        replace(item, provisional_status=statuses[index] if index < 3 else item.provisional_status)
        for index, item in enumerate(result.element_analyses)
    )
    changed = replace(result, element_analyses=changed_elements)

    record = build_issue_matrix((changed,))[0]

    assert tuple(item.analysis_status for item in record.element_records[:3]) == statuses
