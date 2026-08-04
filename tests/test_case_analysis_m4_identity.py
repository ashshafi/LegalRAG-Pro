from dataclasses import replace
import hashlib

from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m4.identity import (
    derive_case_synthesis_id,
    derive_conflict_id,
    derive_finding_id,
    derive_priority_question_id,
    fingerprint_case_chronology,
    fingerprint_case_matrices,
)
from case_analysis.m4.models import (
    AnalyticalBasis,
    ConflictType,
    FindingScope,
    FindingType,
    PriorityBasis,
)
from case_analysis_m4_helpers import make_case_synthesis


def test_m2_and_m3_fingerprints_are_sha256_of_existing_canonical_serializers():
    _, matrices, chronology, _, _ = make_case_synthesis()
    assert fingerprint_case_matrices(matrices) == hashlib.sha256(
        dumps_case_matrices(matrices).encode("utf-8")
    ).hexdigest()
    assert fingerprint_case_chronology(chronology) == hashlib.sha256(
        dumps_case_chronology(chronology).encode("utf-8")
    ).hexdigest()


def test_top_level_synthesis_identity_is_deterministic_for_exact_source_artifacts():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    actual = derive_case_synthesis_id(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        source_matrices_sha256=fingerprint_case_matrices(matrices),
        source_chronology_sha256=fingerprint_case_chronology(chronology),
    )
    assert actual == synthesis.synthesis_id
    assert actual == derive_case_synthesis_id(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        source_matrices_sha256=fingerprint_case_matrices(matrices),
        source_chronology_sha256=fingerprint_case_chronology(chronology),
    )


def test_changing_frozen_m3_content_changes_source_fingerprint_and_m4_identity():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    event = chronology.events[0]
    changed_event = replace(event, description=event.description + " Additional synthetic wording.")
    changed_chronology = replace(chronology, events=(changed_event,))
    changed_sha = fingerprint_case_chronology(changed_chronology)
    assert changed_sha != synthesis.source_lineage.source_chronology_sha256
    assert derive_case_synthesis_id(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        source_matrices_sha256=fingerprint_case_matrices(matrices),
        source_chronology_sha256=changed_sha,
    ) != synthesis.synthesis_id


def test_finding_identity_is_provenance_order_independent_and_not_prose_based():
    _, _, _, synthesis, refs = make_case_synthesis()
    provenance = (refs["ek_prop"], refs["ek_use"])
    left = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        scope=FindingScope.ELEMENT,
        analytical_bases=(AnalyticalBasis.SUPPORTED_PROPOSITION, AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE),
        provenance_refs=provenance,
    )
    right = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        scope=FindingScope.ELEMENT,
        analytical_bases=(AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE, AnalyticalBasis.SUPPORTED_PROPOSITION),
        provenance_refs=tuple(reversed(provenance)),
    )
    assert left == right


def test_conflict_identity_is_side_order_independent():
    _, _, _, synthesis, refs = make_case_synthesis()
    left = derive_conflict_id(
        synthesis_id=synthesis.synthesis_id,
        conflict_type=ConflictType.SOURCE_POSITION_CONFLICT,
        scope=FindingScope.ISSUE,
        side_a_refs=(refs["ek_prop"],),
        side_b_refs=(refs["upstream_dispute"],),
    )
    right = derive_conflict_id(
        synthesis_id=synthesis.synthesis_id,
        conflict_type=ConflictType.SOURCE_POSITION_CONFLICT,
        scope=FindingScope.ISSUE,
        side_a_refs=(refs["upstream_dispute"],),
        side_b_refs=(refs["ek_prop"],),
    )
    assert left == right


def test_priority_question_identity_does_not_depend_on_question_wording_or_input_order():
    _, _, _, synthesis, refs = make_case_synthesis()
    issue_ids = tuple(item.issue_analysis_id for item in synthesis.issue_positions)
    left = derive_priority_question_id(
        synthesis_id=synthesis.synthesis_id,
        basis_type=PriorityBasis.CROSS_ISSUE_DEPENDENCY,
        affected_issue_ids=issue_ids,
        affected_element_ids=("RA-KNOWLEDGE", "EK-INFORMATION"),
        provenance_refs=(refs["event"],),
    )
    right = derive_priority_question_id(
        synthesis_id=synthesis.synthesis_id,
        basis_type=PriorityBasis.CROSS_ISSUE_DEPENDENCY,
        affected_issue_ids=tuple(reversed(issue_ids)),
        affected_element_ids=("EK-INFORMATION", "RA-KNOWLEDGE"),
        provenance_refs=(refs["event"],),
    )
    assert left == right


def test_top_level_identity_rejects_non_sha_source_fingerprints():
    foundation, _, _, _, _ = make_case_synthesis()
    import pytest

    with pytest.raises(ValueError, match="SHA-256"):
        derive_case_synthesis_id(
            case_id=foundation.case_id,
            foundation_synthesis_id=foundation.synthesis_id,
            source_matrices_sha256="not-a-hash",
            source_chronology_sha256="0" * 64,
        )
