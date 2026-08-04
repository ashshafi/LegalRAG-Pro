import json

from case_analysis.m4.serialization import (
    case_synthesis_to_dict,
    dumps_case_synthesis,
    loads_case_synthesis,
)
from case_analysis_m4_helpers import make_case_synthesis


def test_case_synthesis_round_trip_is_exact():
    _, _, _, synthesis, _ = make_case_synthesis()
    payload = dumps_case_synthesis(synthesis)
    assert loads_case_synthesis(payload) == synthesis


def test_case_synthesis_json_is_byte_stable_after_round_trip():
    _, _, _, synthesis, _ = make_case_synthesis()
    first = dumps_case_synthesis(synthesis)
    second = dumps_case_synthesis(loads_case_synthesis(first))
    assert first == second


def test_case_synthesis_uses_existing_canonical_json_convention():
    _, _, _, synthesis, _ = make_case_synthesis()
    expected = json.dumps(
        case_synthesis_to_dict(synthesis),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert dumps_case_synthesis(synthesis) == expected


def test_serialization_preserves_exact_typed_provenance_coordinates():
    _, _, _, synthesis, refs = make_case_synthesis()
    payload = case_synthesis_to_dict(synthesis)
    restored = loads_case_synthesis(dumps_case_synthesis(synthesis))
    assert restored == synthesis
    finding_ref = payload["findings"][0]["provenance_refs"][0]
    assert finding_ref["reference_type"] == "proposition"
    assert finding_ref["reference"]["evidence_key"] == refs["ek_use"].target.evidence_key
    assert finding_ref["reference"]["source_proposition_index"] == 0


def test_serialization_preserves_identity_only_upstream_gap_and_dispute_refs_without_payload_invention():
    _, _, _, synthesis, _ = make_case_synthesis()
    data = case_synthesis_to_dict(synthesis)
    gap_ref = data["gaps"][0]["provenance_refs"][0]
    dispute_ref = data["conflicts"][0]["side_b_refs"][0]
    assert set(gap_ref["reference"]) == {"issue_analysis_id", "element_id", "gap_id"}
    assert set(dispute_ref["reference"]) == {
        "issue_analysis_id",
        "element_id",
        "disputed_matter_id",
    }


def test_equivalent_caller_order_canonicalizes_to_identical_serialization():
    _, _, _, synthesis, _ = make_case_synthesis()
    reordered = type(synthesis)(
        case_id=synthesis.case_id,
        synthesis_id=synthesis.synthesis_id,
        source_lineage=synthesis.source_lineage,
        issue_positions=tuple(reversed(synthesis.issue_positions)),
        findings=tuple(reversed(synthesis.findings)),
        conflicts=tuple(reversed(synthesis.conflicts)),
        gaps=tuple(reversed(synthesis.gaps)),
        risks=tuple(reversed(synthesis.risks)),
        priority_questions=tuple(reversed(synthesis.priority_questions)),
        overall_state=synthesis.overall_state,
    )
    assert dumps_case_synthesis(reordered) == dumps_case_synthesis(synthesis)


def test_validation_and_serialization_do_not_mutate_frozen_sources():
    from case_analysis.serialization import dumps_case_analysis_foundation
    from case_analysis.m2.matrix_serialization import dumps_case_matrices
    from case_analysis.m3.chronology_serialization import dumps_case_chronology
    from case_analysis.m4.validation import validate_case_synthesis

    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    before = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    validate_case_synthesis(
        synthesis,
        foundation=foundation,
        matrices=matrices,
        chronology=chronology,
    )
    dumps_case_synthesis(synthesis)
    after = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    assert after == before
