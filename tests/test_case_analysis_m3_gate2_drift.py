from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m3_frozen_snapshot_envelope import build_frozen_snapshot
from case_analysis_m3_gate2_drift import (
    DriftCategory,
    compare_gate2_analytical_state,
)
from case_analysis_m3_helpers import proposition
from legal_analysis.enums import Confidence
from legal_analysis.legal_analysis import ElementAnalysisStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus

LEGACY_SHA = "8" * 64
CASE_ID = "11111111-1111-4111-8111-111111111111"
EK_ID = "11111111-1111-4111-8111-111111111201"
LIM_ID = "11111111-1111-4111-8111-111111111202"
BASE_TIME = datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc)


def _state(*results):
    results = tuple(results)
    foundation = build_case_analysis_foundation(results)
    matrices = build_case_matrices(foundation, results)
    return results, foundation, matrices


def _snapshot(results, foundation, matrices):
    return build_frozen_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h4-checkpoint",
    )


def _compare(snapshot, state):
    results, foundation, matrices = state
    return compare_gate2_analytical_state(
        snapshot,
        current_results=results,
        current_foundation=foundation,
        current_matrices=matrices,
        expected_legacy_fixture_sha256=LEGACY_SHA,
    )


def _base_shared(summary: str = "The claimant requested copies of payslips and P60s."):
    return evidence(
        key="appendix-d-p1",
        document_id="appendix-d",
        document_name="Appendix D.pdf",
        page=1,
        summary=summary,
        citation="Appendix D, p.1",
    )


def _ek_lim_state(*, add_lim_mapping: bool, ek_id: str = EK_ID, lim_id: str = LIM_ID, created_at=BASE_TIME):
    shared = _base_shared()
    ek = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        issue_analysis_id=ek_id,
        created_at=created_at,
        evidence_by_element={"EK-UNRESOLVED": (shared,)},
    )
    lim = make_m5_result(
        "LIM-001",
        case_id=CASE_ID,
        issue_analysis_id=lim_id,
        created_at=created_at,
        evidence_by_element={"LIM-DATES": (shared,)} if add_lim_mapping else {},
    )
    return _state(ek, lim)


def test_h4_identical_native_state_is_strict_and_semantic_match():
    state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*state)

    report = _compare(snapshot, state)

    assert report.strict_native_match is True
    assert report.semantic_analytical_match is True
    assert report.drifts == ()
    assert report.frozen_analytical_state_sha256 == report.current_analytical_state_sha256


def test_h4_different_issue_uuids_and_timestamps_can_remain_semantically_identical():
    frozen_state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*frozen_state)
    current_state = _ek_lim_state(
        add_lim_mapping=False,
        ek_id="22222222-2222-4222-8222-222222222201",
        lim_id="22222222-2222-4222-8222-222222222202",
        created_at=BASE_TIME + timedelta(hours=2),
    )

    report = _compare(snapshot, current_state)

    assert report.strict_native_match is False
    assert report.semantic_analytical_match is True
    assert report.categories == (DriftCategory.RUN_INSTANCE_IDENTITY_DRIFT,)


def test_h4_appendix_d_pattern_detects_added_lim_dates_mapping():
    frozen_state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*frozen_state)
    current_state = _ek_lim_state(add_lim_mapping=True)

    report = _compare(snapshot, current_state)

    assert report.strict_native_match is False
    assert report.semantic_analytical_match is False
    assert DriftCategory.ELEMENT_MAPPING_DRIFT in report.categories
    assert DriftCategory.MATRIX_DRIFT in report.categories
    mapping_drift = next(
        item for item in report.drifts if item.category is DriftCategory.ELEMENT_MAPPING_DRIFT
    )
    assert ("LIM-DATES", "appendix-d-p1") in mapping_drift.current
    assert ("LIM-DATES", "appendix-d-p1") not in mapping_drift.frozen


def test_h4_evidence_summary_drift_is_reported_for_same_mapping_identity():
    frozen_evidence = _base_shared("Frozen payslip summary.")
    current_evidence = _base_shared("Current payslip summary changed.")
    frozen = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-UNRESOLVED": (frozen_evidence,)},
    )
    current = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-UNRESOLVED": (current_evidence,)},
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert report.semantic_analytical_match is False
    assert DriftCategory.EVIDENCE_SUMMARY_DRIFT in report.categories


def test_h4_m4_occurrence_order_drift_is_reported_without_mapping_set_drift():
    one = evidence(key="occ-a", document_name="a.pdf", summary="First occurrence.")
    two = evidence(key="occ-b", document_name="b.pdf", summary="Second occurrence.")
    frozen = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-TIMING": (one, two)},
    )
    current = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-TIMING": (two, one)},
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert report.semantic_analytical_match is False
    assert DriftCategory.M4_OCCURRENCE_DRIFT in report.categories
    # The same two semantic relationships still exist; only their occurrence order changed.
    assert not any(
        item.category is DriftCategory.ELEMENT_MAPPING_DRIFT for item in report.drifts
    )


def test_h4_proposition_status_and_confidence_drift_are_separate():
    ev = evidence(key="prop-evidence")
    frozen_prop = proposition(
        "A dated communication is documented.",
        ("prop-evidence",),
        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        confidence=Confidence.MEDIUM,
    )
    current_prop = proposition(
        "A dated communication is documented.",
        ("prop-evidence",),
        status=PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
        confidence=Confidence.HIGH,
    )
    frozen = make_m5_result(
        "LIM-001",
        issue_analysis_id=LIM_ID,
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={"LIM-DATES": (frozen_prop,)},
    )
    current = make_m5_result(
        "LIM-001",
        issue_analysis_id=LIM_ID,
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={"LIM-DATES": (current_prop,)},
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert DriftCategory.PROPOSITION_STATUS_DRIFT in report.categories
    assert DriftCategory.PROPOSITION_CONFIDENCE_DRIFT in report.categories
    assert report.semantic_analytical_match is False


def test_h4_mapping_confidence_and_role_drift_are_reported():
    ev = evidence(key="role-evidence")
    frozen = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-TIMING": (ev,)},
    )
    # Build current from the same frozen result then alter only frozen M4 relationship state.
    element = frozen.assessment_result.element_assessments[8]
    assessment = element.evidence_assessments[0]
    changed_mapping = replace(assessment.mapping, mapping_confidence=Confidence.MEDIUM)
    changed_assessment = replace(
        assessment,
        mapping=changed_mapping,
        analytical_role=assessment.analytical_role.__class__.NEUTRAL,
    )
    changed_element = replace(element, evidence_assessments=(changed_assessment,))
    changed_elements = list(frozen.assessment_result.element_assessments)
    changed_elements[8] = changed_element
    changed_mapping_result_element = frozen.assessment_result.mapping_result.element_results[8]
    changed_mapping_result = replace(
        frozen.assessment_result.mapping_result,
        element_results=tuple(
            replace(item, mappings=(changed_mapping,)) if idx == 8 else item
            for idx, item in enumerate(frozen.assessment_result.mapping_result.element_results)
        ),
    )
    changed_result = replace(
        frozen,
        assessment_result=replace(
            frozen.assessment_result,
            mapping_result=changed_mapping_result,
            element_assessments=tuple(changed_elements),
        ),
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(changed_result))

    assert DriftCategory.MAPPING_CONFIDENCE_DRIFT in report.categories
    assert DriftCategory.ROLE_DRIFT in report.categories


def test_h4_current_cross_component_state_is_validated_before_comparison():
    state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*state)
    results, foundation, matrices = state
    bad_matrices = replace(matrices, source_analysis_ids=tuple(reversed(matrices.source_analysis_ids)))

    with pytest.raises(ValueError):
        compare_gate2_analytical_state(
            snapshot,
            current_results=results,
            current_foundation=foundation,
            current_matrices=bad_matrices,
        )


def test_h4_comparator_does_not_mutate_frozen_or_current_inputs():
    state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*state)
    before_snapshot = repr(snapshot)
    before_state = repr(state)

    _compare(snapshot, state)

    assert repr(snapshot) == before_snapshot
    assert repr(state) == before_state



def test_h4_reversed_outer_m5_caller_order_is_not_drift():
    state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*state)
    results, foundation, matrices = state

    report = compare_gate2_analytical_state(
        snapshot,
        current_results=tuple(reversed(results)),
        current_foundation=foundation,
        current_matrices=matrices,
    )

    assert report.strict_native_match is True
    assert report.semantic_analytical_match is True
    assert report.drifts == ()


def test_h4_added_semantic_issue_is_source_set_drift():
    frozen_state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*frozen_state)
    ek, lim = frozen_state[0]
    ra = make_m5_result(
        "RA-001",
        case_id=CASE_ID,
        issue_analysis_id="11111111-1111-4111-8111-111111111203",
        created_at=BASE_TIME,
    )

    report = _compare(snapshot, _state(ek, lim, ra))

    assert report.semantic_analytical_match is False
    assert DriftCategory.SOURCE_SET_DRIFT in report.categories


def test_h4_version_drift_is_reported_separately():
    ev = evidence(key="version-evidence")
    frozen = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-TIMING": (ev,)},
    )
    current = replace(
        frozen,
        element_analyses=tuple(
            replace(item, analyser_version="legal-analyser/1.1-test")
            for item in frozen.element_analyses
        ),
        analyser_version="legal-analyser/1.1-test",
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert report.semantic_analytical_match is False
    assert DriftCategory.VERSION_DRIFT in report.categories


def test_h4_m4_assessment_confidence_drift_is_reported():
    ev = evidence(key="assessment-confidence")
    frozen = make_m5_result(
        "EK-001",
        issue_analysis_id=EK_ID,
        evidence_by_element={"EK-TIMING": (ev,)},
    )
    elements = list(frozen.assessment_result.element_assessments)
    target = elements[8]
    changed_assessment = replace(
        target.evidence_assessments[0],
        assessment_confidence=Confidence.MEDIUM,
    )
    elements[8] = replace(target, evidence_assessments=(changed_assessment,))
    current = replace(
        frozen,
        assessment_result=replace(
            frozen.assessment_result,
            element_assessments=tuple(elements),
        ),
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert DriftCategory.ASSESSMENT_CONFIDENCE_DRIFT in report.categories


def test_h4_m5_status_and_confidence_drift_are_reported():
    frozen = make_m5_result("EK-001", issue_analysis_id=EK_ID)
    first = frozen.element_analyses[0]
    current = replace(
        frozen,
        element_analyses=(
            replace(
                first,
                provisional_status=ElementAnalysisStatus.UNRESOLVED,
                analysis_confidence=Confidence.MEDIUM,
            ),
            *frozen.element_analyses[1:],
        ),
    )
    frozen_state = _state(frozen)
    snapshot = _snapshot(*frozen_state)

    report = _compare(snapshot, _state(current))

    assert DriftCategory.M5_STATUS_DRIFT in report.categories
    assert DriftCategory.M5_CONFIDENCE_DRIFT in report.categories
    assert report.semantic_analytical_match is False


def test_h4_comparator_does_not_regenerate_upstream_pipeline(monkeypatch):
    state = _ek_lim_state(add_lim_mapping=False)
    snapshot = _snapshot(*state)

    def forbidden(*args, **kwargs):
        raise AssertionError("H4 comparator must not regenerate upstream analytical state")

    import case_analysis.foundation as foundation_module
    import case_analysis.m2.matrices as matrices_module
    import legal_analysis.element_assessor as assessor_module
    import legal_analysis.evidence_mapper as mapper_module
    import legal_analysis.legal_analysis_renderer as renderer_module

    monkeypatch.setattr(foundation_module, "build_case_analysis_foundation", forbidden)
    monkeypatch.setattr(matrices_module, "build_case_matrices", forbidden)
    monkeypatch.setattr(mapper_module.ElementEvidenceMapper, "map_primary_issue", forbidden)
    monkeypatch.setattr(assessor_module.ElementEvidenceAssessor, "assess", forbidden)
    monkeypatch.setattr(renderer_module.StructuredLegalAnalysisRenderer, "render", forbidden)

    report = _compare(snapshot, state)
    assert report.semantic_analytical_match is True
