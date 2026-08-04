from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m3_frozen_gate1 import run_frozen_gate1
from case_analysis_m3_governed_snapshot_capture import (
    APPROVED_FOUR_QUESTIONS,
    SnapshotProvenanceClassification,
    compare_candidate_to_legacy_fixture,
    prepare_governed_snapshot,
    write_governed_snapshot_once,
)
from case_analysis_m3_live_fixture_capture import (
    build_live_fixture_payload,
    dumps_live_fixture,
)
from case_analysis_m3_helpers import proposition

_GENERIC = "The mapped evidence contains factual material relevant to this element."


def _native_inputs():
    shared = evidence(
        key="h5-shared",
        document_id="h5-doc",
        document_name="h5-return-to-work.pdf",
        summary=(
            "From: HR <hr@example.com> Sent: 14 June 2005 "
            "Subject: Return to work The employer sent an email concerning "
            "return-to-work arrangements."
        ),
    )
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="55555555-5555-4555-8555-555555555501",
        evidence_by_element={"EK-TIMING": (shared,)},
        proposition_overrides={
            "EK-TIMING": (proposition(_GENERIC, ("h5-shared",)),)
        },
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="55555555-5555-4555-8555-555555555502",
        evidence_by_element={"RA-TIMING": (shared,)},
        proposition_overrides={
            "RA-TIMING": (proposition(_GENERIC, ("h5-shared",)),)
        },
    )
    results = (ek, ra)
    foundation = build_case_analysis_foundation(results)
    matrices = build_case_matrices(foundation, results)
    return results, foundation, matrices


def _write_legacy(path: Path, results, matrices, *, mutate=None) -> str:
    payload = build_live_fixture_payload(matrices, results)
    if mutate is not None:
        mutate(payload)
    path.write_text(dumps_live_fixture(payload) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare(tmp_path: Path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)
    snapshot, execution, compatibility, before = prepare_governed_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy,
        captured_at="2026-08-03T23:00:00+01:00",
        source_checkpoint="synthetic-h5-checkpoint",
        provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
        provenance_rationale="Synthetic governed H5 capture test.",
        expected_legacy_fixture_sha256=legacy_sha,
    )
    return snapshot, execution, compatibility, before, results, foundation, matrices, legacy, legacy_sha


def test_h5_prepares_valid_new_governed_snapshot_in_memory(tmp_path):
    snapshot, execution, compatibility, before, results, foundation, matrices, legacy, legacy_sha = _prepare(tmp_path)

    governance = snapshot["manifest"]["capture_governance"]
    assert governance["provenance_classification"] == "NEW_GOVERNED_FROZEN_STATE"
    assert tuple(governance["approved_questions"]) == APPROVED_FOUR_QUESTIONS
    assert execution.results == tuple(sorted(results, key=lambda item: (
        item.assessment_result.assessed_analysis.issue_definition_id,
        item.assessment_result.assessed_analysis.issue_definition_version,
        item.assessment_result.assessed_analysis.issue_analysis_id,
    )))
    assert execution.foundation == foundation
    assert execution.matrices == matrices
    assert compatibility.semantic_match is True
    assert before == legacy_sha
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == legacy_sha


def test_h5_rejects_original_capture_classification_without_exact_original_proof(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)

    with pytest.raises(ValueError, match="ORIGINAL_CAPTURE_STATE requires independent verification"):
        prepare_governed_snapshot(
            results=results,
            foundation=foundation,
            matrices=matrices,
            legacy_fixture_path=legacy,
            captured_at="2026-08-03T23:00:00+01:00",
            source_checkpoint="synthetic-h5-checkpoint",
            provenance_classification=SnapshotProvenanceClassification.ORIGINAL_CAPTURE_STATE,
            provenance_rationale="Claimed original without proof.",
            expected_legacy_fixture_sha256=legacy_sha,
        )


def test_h5_original_capture_classification_requires_explicit_verified_proof(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)

    snapshot, _, _, _ = prepare_governed_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy,
        captured_at="2026-08-03T23:00:00+01:00",
        source_checkpoint="synthetic-h5-checkpoint",
        provenance_classification=SnapshotProvenanceClassification.ORIGINAL_CAPTURE_STATE,
        provenance_rationale="Synthetic exact original state proof for harness test.",
        original_complete_state_verified=True,
        expected_legacy_fixture_sha256=legacy_sha,
    )

    assert snapshot["manifest"]["capture_governance"]["original_complete_state_verified"] is True


def test_h5_rejects_any_question_scope_other_than_exact_four_approved_questions(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)

    with pytest.raises(ValueError, match="exact approved four questions"):
        prepare_governed_snapshot(
            results=results,
            foundation=foundation,
            matrices=matrices,
            legacy_fixture_path=legacy,
            captured_at="2026-08-03T23:00:00+01:00",
            source_checkpoint="synthetic-h5-checkpoint",
            provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
            provenance_rationale="Wrong scope test.",
            approved_questions=APPROVED_FOUR_QUESTIONS[:3],
            expected_legacy_fixture_sha256=legacy_sha,
        )


def test_h5_rejects_legacy_fixture_sha_mismatch_before_capture(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    _write_legacy(legacy, results, matrices)

    with pytest.raises(ValueError, match="legacy fixture SHA-256"):
        prepare_governed_snapshot(
            results=results,
            foundation=foundation,
            matrices=matrices,
            legacy_fixture_path=legacy,
            captured_at="2026-08-03T23:00:00+01:00",
            source_checkpoint="synthetic-h5-checkpoint",
            provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
            provenance_rationale="SHA mismatch test.",
            expected_legacy_fixture_sha256="0" * 64,
        )


def test_h5_legacy_compatibility_detects_element_mapping_drift(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"

    def remove_ra(payload):
        payload["evidence"][0]["uses"] = [
            use for use in payload["evidence"][0]["uses"]
            if use["issue_definition_id"] != "RA-001"
        ]

    _write_legacy(legacy, results, matrices, mutate=remove_ra)
    frozen = json.loads(legacy.read_text(encoding="utf-8"))
    compatibility = compare_candidate_to_legacy_fixture(
        frozen,
        matrices=matrices,
        results=results,
    )

    assert compatibility.semantic_match is False
    assert any(item.startswith("EVIDENCE_USE_DRIFT:") for item in compatibility.drifts)


def test_h5_write_once_reloads_through_h3_and_preserves_legacy_fixture(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)
    target = tmp_path / "shafi_m3_frozen_analytical_snapshot_v1_0.json"

    report = write_governed_snapshot_once(
        target_path=target,
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy,
        captured_at="2026-08-03T23:00:00+01:00",
        source_checkpoint="synthetic-h5-checkpoint",
        provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
        provenance_rationale="Synthetic governed write-once test.",
        expected_legacy_fixture_sha256=legacy_sha,
    )

    assert target.is_file()
    assert report.snapshot_file_sha256 == hashlib.sha256(target.read_bytes()).hexdigest()
    assert report.legacy_fixture_sha_before == legacy_sha
    assert report.legacy_fixture_sha_after == legacy_sha
    assert report.gate1_reconstruction_passed is True
    assert report.gate1_deterministic is True
    assert report.chronology_round_trip_identical is True
    disk_execution = run_frozen_gate1(
        target.read_text(encoding="utf-8"),
        expected_legacy_fixture_sha256=legacy_sha,
    )
    assert dumps_case_chronology(disk_execution.chronology) == disk_execution.chronology_json


def test_h5_governed_snapshot_is_never_overwritten(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)
    target = tmp_path / "shafi_m3_frozen_analytical_snapshot_v1_0.json"
    target.write_text("already frozen", encoding="utf-8")

    with pytest.raises(ValueError, match="overwrite is prohibited"):
        write_governed_snapshot_once(
            target_path=target,
            results=results,
            foundation=foundation,
            matrices=matrices,
            legacy_fixture_path=legacy,
            captured_at="2026-08-03T23:00:00+01:00",
            source_checkpoint="synthetic-h5-checkpoint",
            provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
            provenance_rationale="Overwrite guard test.",
            expected_legacy_fixture_sha256=legacy_sha,
        )


def test_h5_invalid_cross_component_state_fails_before_target_write(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)
    target = tmp_path / "shafi_m3_frozen_analytical_snapshot_v1_0.json"
    shared = evidence(
        key="h5-alt-shared",
        document_id="h5-alt-doc",
        document_name="h5-alt.pdf",
        summary="Alternative valid case evidence.",
    )
    alt_results = (
        make_m5_result(
            "EK-001",
            case_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            evidence_by_element={"EK-TIMING": (shared,)},
            proposition_overrides={
                "EK-TIMING": (proposition(_GENERIC, ("h5-alt-shared",)),)
            },
        ),
    )
    # Build an independently valid matrix set for a different case; combining it
    # with the original M5/M1 state must fail before any target write.
    alt_foundation = build_case_analysis_foundation(alt_results)
    alt_matrices = build_case_matrices(alt_foundation, alt_results)

    with pytest.raises(ValueError):
        write_governed_snapshot_once(
            target_path=target,
            results=results,
            foundation=foundation,
            matrices=alt_matrices,
            legacy_fixture_path=legacy,
            captured_at="2026-08-03T23:00:00+01:00",
            source_checkpoint="synthetic-h5-checkpoint",
            provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
            provenance_rationale="Cross-component validation test.",
            expected_legacy_fixture_sha256=legacy_sha,
        )
    assert not target.exists()


def test_h5_capture_metadata_does_not_change_analytical_identity(tmp_path):
    results, foundation, matrices = _native_inputs()
    legacy = tmp_path / "shafi_chronology_live_v1_0.json"
    legacy_sha = _write_legacy(legacy, results, matrices)

    first, *_ = prepare_governed_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy,
        captured_at="2026-08-03T23:00:00+01:00",
        source_checkpoint="checkpoint-a",
        provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
        provenance_rationale="Capture A.",
        expected_legacy_fixture_sha256=legacy_sha,
    )
    second, *_ = prepare_governed_snapshot(
        results=tuple(reversed(results)),
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy,
        captured_at="2026-08-04T01:00:00+01:00",
        source_checkpoint="checkpoint-b",
        provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
        provenance_rationale="Capture B with different metadata and caller order.",
        expected_legacy_fixture_sha256=legacy_sha,
    )

    assert first["analytical_state_sha256"] == second["analytical_state_sha256"]
    assert first["component_hashes"] == second["component_hashes"]


def test_h5_snapshot_manifest_contains_required_capture_provenance(tmp_path):
    snapshot, *_ = _prepare(tmp_path)
    governance = snapshot["manifest"]["capture_governance"]

    assert governance["capture_purpose"]
    assert governance["approved_questions"] == list(APPROVED_FOUR_QUESTIONS)
    assert governance["provenance_classification"] == "NEW_GOVERNED_FROZEN_STATE"
    assert governance["provenance_rationale"]
    assert snapshot["manifest"]["legacy_fixture"]["name"] == "shafi_chronology_live_v1_0.json"
