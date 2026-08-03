from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from legal_analysis.enums import AnalyticalRole, Confidence
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus
from legal_analysis.evidence_mapping import EvidenceMapping, EvidenceRelevance

from case_analysis.m2.evidence_matrix import build_evidence_matrix
from case_analysis_m2_helpers import evidence, make_m5_result, replace_mapping_evidence


def test_same_evidence_across_elements_preserves_distinct_roles():
    shared_a = evidence(key="shared")
    shared_b = replace(shared_a, summary="Harmless second occurrence")
    result = make_m5_result(
        "EK-001",
        evidence_by_element={
            "EK-INFORMATION": (shared_a,),
            "EK-DIRECT-KNOWLEDGE": (shared_b,),
            "EK-CONSTRUCTIVE-KNOWLEDGE": (shared_a,),
        },
        role_overrides={
            ("EK-INFORMATION", "shared"): AnalyticalRole.SUPPORTING,
            ("EK-DIRECT-KNOWLEDGE", "shared"): AnalyticalRole.NEUTRAL,
            ("EK-CONSTRUCTIVE-KNOWLEDGE", "shared"): AnalyticalRole.ADVERSE,
        },
    )

    matrix = build_evidence_matrix((result,))

    assert len(matrix) == 1
    assert [item.analytical_role for item in matrix[0].uses] == [
        AnalyticalRole.SUPPORTING,
        AnalyticalRole.NEUTRAL,
        AnalyticalRole.ADVERSE,
    ]
    assert len({item.identity for item in matrix[0].uses}) == 3


def test_same_evidence_across_issues_becomes_one_record_with_multiple_uses():
    shared = evidence(key="shared")
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-INFORMATION": (shared,)},
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"RA-KNOWLEDGE": (replace(shared, summary="RA representation"),)},
    )

    matrix = build_evidence_matrix((ra, ek))

    assert len(matrix) == 1
    assert matrix[0].evidence_key == "shared"
    assert {item.issue_analysis_id for item in matrix[0].uses} == {
        ek.issue_analysis_id,
        ra.issue_analysis_id,
    }


def test_proposition_links_preserve_complete_m4_proposition_state():
    shared = evidence(key="shared")
    other = evidence(key="other-key", document_name="other.pdf", document_id="doc-2")
    proposition = AssessedProposition(
        text="The current record supports a specific factual proposition.",
        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        confidence=Confidence.MEDIUM,
        evidence_keys=("shared", "other-key"),
        rationale="Synthetic M2 proposition rationale.",
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-INFORMATION": (shared, other)},
        proposition_overrides={"EK-INFORMATION": (proposition,)},
    )

    use = next(
        item
        for record in build_evidence_matrix((result,))
        if record.evidence_key == "shared"
        for item in record.uses
    )
    link = use.proposition_links[0]

    assert link.source_proposition_index == 0
    assert link.text == proposition.text
    assert link.status is proposition.status
    assert link.confidence is proposition.confidence
    assert link.rationale == proposition.rationale
    assert link.evidence_keys == ("shared", "other-key")


def test_incompatible_same_key_source_identity_still_fails_closed():
    shared = evidence(key="shared")
    result = make_m5_result(
        "EK-001",
        evidence_by_element={
            "EK-INFORMATION": (shared,),
            "EK-DIRECT-KNOWLEDGE": (replace(shared, summary="second"),),
        },
    )
    corrupted = replace_mapping_evidence(
        result,
        element_id="EK-DIRECT-KNOWLEDGE",
        evidence_key="shared",
        replacement=replace(shared, page=2, citation="shared.pdf, p.2"),
    )

    with pytest.raises(ValueError, match="incompatible stable evidence identity"):
        build_evidence_matrix((corrupted,))


def test_potential_m3_candidate_does_not_become_evidence_use():
    assessed = evidence(key="assessed")
    result = make_m5_result("EK-001", evidence_by_element={"EK-INFORMATION": (assessed,)})
    assessment = result.assessment_result
    mapped = assessment.mapping_result
    target = mapped.element_results[0]
    loose = evidence(key="loose")
    loose_mapping = EvidenceMapping(
        evidence=loose,
        issue_definition_id=result.issue_definition_id,
        issue_definition_version=result.issue_definition_version,
        element_id=target.element_id,
        relevance=EvidenceRelevance.POTENTIALLY_RELEVANT,
        mapping_confidence=Confidence.LOW,
        mapping_rationale="Loose M3 candidate only.",
    )
    new_target = replace(target, mappings=target.mappings + (loose_mapping,))
    new_mapped = replace(mapped, element_results=(new_target,) + mapped.element_results[1:])
    corrupted_but_valid_for_m2 = replace(
        result,
        assessment_result=replace(assessment, mapping_result=new_mapped),
    )

    matrix = build_evidence_matrix((corrupted_but_valid_for_m2,))

    assert tuple(item.evidence_key for item in matrix) == ("assessed",)


def test_matrix_build_does_not_mutate_frozen_m5_input():
    result = make_m5_result("EK-001", evidence_by_element={"EK-INFORMATION": (evidence(key="x"),)})
    before = copy.deepcopy(result)
    build_evidence_matrix((result,))
    assert result == before


def test_duplicate_exact_logical_use_collapses_but_conflicting_role_fails_closed():
    shared = evidence(key="dup")
    result = make_m5_result("EK-001", evidence_by_element={"EK-INFORMATION": (shared,)})
    assessment = result.assessment_result
    target = next(item for item in assessment.element_assessments if item.element_id == "EK-INFORMATION")
    original = target.evidence_assessments[0]

    duplicate_target = replace(
        target,
        evidence_assessments=target.evidence_assessments + (original,),
    )
    duplicate_result = replace(
        result,
        assessment_result=replace(
            assessment,
            element_assessments=tuple(
                duplicate_target if item.element_id == target.element_id else item
                for item in assessment.element_assessments
            ),
        ),
    )
    record = build_evidence_matrix((duplicate_result,))[0]
    assert len(record.uses) == 1

    conflicting = replace(
        original,
        analytical_role=(
            AnalyticalRole.ADVERSE
            if original.analytical_role is not AnalyticalRole.ADVERSE
            else AnalyticalRole.SUPPORTING
        ),
    )
    conflicting_target = replace(
        target,
        evidence_assessments=target.evidence_assessments + (conflicting,),
    )
    conflicting_result = replace(
        result,
        assessment_result=replace(
            assessment,
            element_assessments=tuple(
                conflicting_target if item.element_id == target.element_id else item
                for item in assessment.element_assessments
            ),
        ),
    )
    with pytest.raises(ValueError, match="incompatible frozen relationship state"):
        build_evidence_matrix((conflicting_result,))


def test_canonical_evidence_selection_is_independent_of_caller_order():
    from legal_analysis.enums import ProvenanceConfidence

    ek_evidence = evidence(key="canonical", provenance_confidence=ProvenanceConfidence.HIGH)
    ra_evidence = replace(
        ek_evidence,
        summary="Different runtime representation",
        provenance_confidence=ProvenanceConfidence.MEDIUM,
    )
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-INFORMATION": (ek_evidence,)},
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"RA-KNOWLEDGE": (ra_evidence,)},
    )

    forward = build_evidence_matrix((ek, ra))
    reverse = build_evidence_matrix((ra, ek))

    assert reverse == forward
    assert forward[0].provenance_confidence is ProvenanceConfidence.HIGH
