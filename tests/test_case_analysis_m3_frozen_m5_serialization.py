from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m3_frozen_m5_serialization import (
    dumps_structured_legal_analysis_result,
    loads_structured_legal_analysis_result,
    structured_legal_analysis_result_from_dict,
    structured_legal_analysis_result_to_dict,
)
from legal_analysis.enums import AnalyticalRole, Confidence, Materiality
from legal_analysis.evidence_assessment import (
    AssessedProposition,
    PropositionAssessmentStatus,
)
from legal_analysis.legal_analysis import EvidenceBackedStatement
from legal_analysis.models import DisputedMatter, EvidentialGap


def _representative_result():
    employer = replace(
        evidence(
            key="hr-email",
            document_name="hr-email.pdf",
            summary="From HR: We received and discussed the return-to-work information.",
            author="HR Director",
            parties=("CACI", "Claimant"),
        ),
        date=date(2025, 9, 6),
    )
    claimant = evidence(
        key="claimant-statement",
        document_name="statement.pdf",
        summary="The claimant states that the events caused a relapse.",
        author="Claimant",
        parties=("Claimant",),
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={
            "EK-DIRECT-KNOWLEDGE": (employer, claimant),
        },
        proposition_overrides={
            "EK-DIRECT-KNOWLEDGE": (
                AssessedProposition(
                    text="The employer received return-to-work information.",
                    status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
                    confidence=Confidence.MEDIUM,
                    evidence_keys=("hr-email", "claimant-statement"),
                    rationale="The current record supports receipt but does not resolve every disputed detail.",
                ),
                AssessedProposition(
                    text="A communication occurred on 6 September 2025.",
                    status=PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
                    confidence=Confidence.HIGH,
                    evidence_keys=("hr-email",),
                    rationale="The dated email directly establishes the communication date.",
                ),
            )
        },
        role_overrides={
            ("EK-DIRECT-KNOWLEDGE", "claimant-statement"): AnalyticalRole.SUPPORTING,
        },
    )

    target_m4 = next(
        item
        for item in result.assessment_result.element_assessments
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    disputed = DisputedMatter(
        proposition="Whether the employer had the asserted level of knowledge.",
        claimant_position="The claimant says knowledge was direct.",
        respondent_position="The respondent disputes the extent of knowledge.",
        claimant_evidence=(claimant,),
        respondent_evidence=(employer,),
        contemporaneous_evidence=(employer,),
        presently_established="A dated communication occurred.",
        remains_unresolved="The legal significance of the communication remains unresolved.",
    )
    gap = EvidentialGap(
        description="Further contemporaneous records may clarify the extent of knowledge.",
        related_element_id="EK-DIRECT-KNOWLEDGE",
        materiality=Materiality.MEDIUM,
        reason="The present evidence does not resolve the whole disputed issue.",
        suggested_evidence_target="Contemporaneous HR/OH correspondence.",
    )
    amended_m4 = replace(
        target_m4,
        disputed_matters=(disputed,),
        evidential_gaps=(gap,),
        presently_established=("A dated communication occurred.",),
        unresolved_matters=("The extent of knowledge remains unresolved.",),
    )
    assessment = replace(
        result.assessment_result,
        element_assessments=tuple(
            amended_m4 if item.element_id == amended_m4.element_id else item
            for item in result.assessment_result.element_assessments
        ),
    )

    target_m5 = next(
        item for item in result.element_analyses if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    statement = EvidenceBackedStatement(
        text="The dated HR email records receipt of return-to-work information.",
        evidence_keys=("hr-email",),
        citations=("hr-email.pdf, p.1",),
    )
    amended_m5 = replace(
        target_m5,
        established_matters=(statement,),
        supported_matters=(statement,),
        not_supported_matters=(statement,),
        source_assertions=(statement,),
        adverse_material=(statement,),
        corroborative_material=(statement,),
        contextual_material=(statement,),
        conflicting_material=(statement,),
        disputed_matters=(disputed,),
        evidential_gaps=(gap,),
        limitations=("Synthetic limitation retained for serialization coverage.",),
        unresolved_matters=("Synthetic unresolved matter retained for serialization coverage.",),
    )
    return replace(
        result,
        assessment_result=assessment,
        element_analyses=tuple(
            amended_m5 if item.element_id == amended_m5.element_id else item
            for item in result.element_analyses
        ),
        overall_limitations=(
            "Synthetic overall limitation retained for serialization coverage.",
        ),
    )


def test_complete_structured_legal_analysis_result_round_trips_exactly():
    original = _representative_result()

    restored = loads_structured_legal_analysis_result(
        dumps_structured_legal_analysis_result(original)
    )

    assert restored == original


def test_dict_round_trip_is_exact_for_complete_graph():
    original = _representative_result()

    restored = structured_legal_analysis_result_from_dict(
        structured_legal_analysis_result_to_dict(original)
    )

    assert restored == original


def test_canonical_bytes_are_stable_after_round_trip():
    original = _representative_result()
    first = dumps_structured_legal_analysis_result(original)
    restored = loads_structured_legal_analysis_result(first)
    second = dumps_structured_legal_analysis_result(restored)

    assert second == first
    assert first.encode("utf-8") == second.encode("utf-8")


def test_canonical_json_uses_sorted_keys_and_compact_separators():
    payload = dumps_structured_legal_analysis_result(_representative_result())

    reparsed = json.loads(payload)
    expected = json.dumps(
        reparsed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert payload == expected


def test_m4_evidence_assessment_order_is_preserved():
    original = _representative_result()
    target = next(
        item
        for item in original.assessment_result.element_assessments
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    assert len(target.evidence_assessments) == 2

    restored = loads_structured_legal_analysis_result(
        dumps_structured_legal_analysis_result(original)
    )
    restored_target = next(
        item
        for item in restored.assessment_result.element_assessments
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )

    assert tuple(item.mapping.evidence_key for item in restored_target.evidence_assessments) == (
        "hr-email",
        "claimant-statement",
    )


def test_assessed_proposition_order_is_preserved():
    original = _representative_result()
    target = next(
        item
        for item in original.assessment_result.element_assessments
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    assert len(target.assessed_propositions) == 2

    restored = loads_structured_legal_analysis_result(
        dumps_structured_legal_analysis_result(original)
    )
    restored_target = next(
        item
        for item in restored.assessment_result.element_assessments
        if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )

    assert tuple(item.text for item in restored_target.assessed_propositions) == tuple(
        item.text for item in target.assessed_propositions
    )


def test_serialization_does_not_mutate_source_result():
    original = _representative_result()
    before = original

    dumps_structured_legal_analysis_result(original)
    structured_legal_analysis_result_to_dict(original)

    assert original == before


def test_non_object_payload_fails_closed():
    try:
        loads_structured_legal_analysis_result("[]")
    except ValueError as exc:
        assert "must contain an object" in str(exc)
    else:
        raise AssertionError("Expected invalid non-object payload to fail closed.")
