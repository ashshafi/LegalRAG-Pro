from __future__ import annotations

import builtins
import copy
import json
from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m3.chronology_serialization import (
    dumps_case_chronology,
    loads_case_chronology,
)
from case_analysis.m3.chronology_validation import resolve_chronology_inputs
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m3_frozen_gate1 import (
    load_frozen_gate1_inputs,
    run_frozen_gate1,
)
from case_analysis_m3_frozen_m5_serialization import (
    structured_legal_analysis_result_to_dict,
)
from case_analysis_m3_frozen_snapshot_envelope import (
    _analytical_state_sha256,
    _component_hashes,
    build_frozen_snapshot,
    dumps_frozen_snapshot,
)
from case_analysis_m3_helpers import proposition

LEGACY_SHA = "8" * 64
_GENERIC = "The mapped evidence contains factual material relevant to this element."


def _native_inputs():
    shared = evidence(
        key="gate1-shared",
        document_id="gate1-doc",
        document_name="gate1-return-to-work.pdf",
        summary=(
            "From: HR <hr@example.com> Sent: 14 June 2005 "
            "Subject: Return to work The employer sent an email concerning "
            "return-to-work arrangements."
        ),
    )
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="11111111-1111-4111-8111-111111111101",
        evidence_by_element={"EK-TIMING": (shared,)},
        proposition_overrides={
            "EK-TIMING": (proposition(_GENERIC, ("gate1-shared",)),)
        },
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="11111111-1111-4111-8111-111111111102",
        evidence_by_element={"RA-TIMING": (shared,)},
        proposition_overrides={
            "RA-TIMING": (proposition(_GENERIC, ("gate1-shared",)),)
        },
    )
    results = (ek, ra)
    foundation = build_case_analysis_foundation(results)
    matrices = build_case_matrices(foundation, results)
    return results, foundation, matrices


def _snapshot_with_inputs():
    results, foundation, matrices = _native_inputs()
    snapshot = build_frozen_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h3-checkpoint",
    )
    return snapshot, results, foundation, matrices


def _snapshot():
    return _snapshot_with_inputs()[0]



def _refresh_h2_hashes(snapshot):
    snapshot["component_hashes"] = _component_hashes(snapshot["components"])
    snapshot["analytical_state_sha256"] = _analytical_state_sha256(
        snapshot["component_hashes"]
    )
    return snapshot

def test_gate1_reconstructs_exact_native_m5_m1_m2_inputs():
    snapshot, expected_results, expected_foundation, expected_matrices = _snapshot_with_inputs()
    inputs = load_frozen_gate1_inputs(snapshot, expected_legacy_fixture_sha256=LEGACY_SHA)

    assert inputs.results == expected_results
    assert inputs.foundation == expected_foundation
    assert inputs.matrices == expected_matrices
    assert inputs.analytical_state_sha256 == snapshot["analytical_state_sha256"]


def test_gate1_m5_component_round_trip_matches_frozen_component_exactly():
    snapshot = _snapshot()
    inputs = load_frozen_gate1_inputs(snapshot)

    assert [structured_legal_analysis_result_to_dict(item) for item in inputs.results] == snapshot[
        "components"
    ]["m5_results"]


def test_gate1_m1_component_round_trip_matches_frozen_component_exactly():
    snapshot = _snapshot()
    inputs = load_frozen_gate1_inputs(snapshot)

    assert json.loads(dumps_case_analysis_foundation(inputs.foundation)) == snapshot[
        "components"
    ]["foundation"]


def test_gate1_m2_component_round_trip_matches_frozen_component_exactly():
    snapshot = _snapshot()
    inputs = load_frozen_gate1_inputs(snapshot)

    assert json.loads(dumps_case_matrices(inputs.matrices)) == snapshot["components"]["matrices"]


def test_gate1_reconstructed_inputs_pass_existing_chronology_resolution():
    inputs = load_frozen_gate1_inputs(_snapshot())

    assert resolve_chronology_inputs(inputs.foundation, inputs.matrices, inputs.results) == inputs.results


def test_gate1_repeated_execution_is_deterministic_for_same_snapshot():
    payload = dumps_frozen_snapshot(_snapshot())
    first = run_frozen_gate1(payload, expected_legacy_fixture_sha256=LEGACY_SHA)
    second = run_frozen_gate1(payload, expected_legacy_fixture_sha256=LEGACY_SHA)

    assert first.analytical_state_sha256 == second.analytical_state_sha256
    assert first.chronology == second.chronology
    assert first.chronology_json == second.chronology_json
    assert len(first.chronology.events) == 1
    assert first.chronology.events[0].related_issue_definition_ids == ("EK-001", "RA-001")


def test_gate1_chronology_serialization_round_trip_is_exact():
    execution = run_frozen_gate1(_snapshot())

    restored = loads_case_chronology(execution.chronology_json)
    assert restored == execution.chronology
    assert dumps_case_chronology(restored) == execution.chronology_json


def test_gate1_does_not_mutate_reconstructed_source_objects():
    snapshot = _snapshot()
    inputs = load_frozen_gate1_inputs(snapshot)
    results_before = copy.deepcopy(inputs.results)
    foundation_before = copy.deepcopy(inputs.foundation)
    matrices_before = copy.deepcopy(inputs.matrices)

    execution = run_frozen_gate1(snapshot)

    assert execution.results == results_before
    assert execution.foundation == foundation_before
    assert execution.matrices == matrices_before


def test_gate1_succeeds_when_live_pipeline_entry_points_are_unavailable(monkeypatch):
    snapshot = _snapshot()

    def forbidden(*args, **kwargs):
        raise AssertionError("live/upstream pathway must not be called by frozen Gate 1")

    import case_analysis.foundation as foundation_module
    import case_analysis.m2.matrices as matrices_module
    import case_management.repository as repository_module
    import legal_analysis.element_assessor as assessor_module
    import legal_analysis.evidence_mapper as mapper_module
    import legal_analysis.legal_analysis_renderer as renderer_module
    import legal_analysis.selector as selector_module

    monkeypatch.setattr(foundation_module, "build_case_analysis_foundation", forbidden)
    monkeypatch.setattr(matrices_module, "build_case_matrices", forbidden)
    monkeypatch.setattr(selector_module.DeterministicIssueSelector, "select", forbidden)
    monkeypatch.setattr(mapper_module.ElementEvidenceMapper, "map_primary_issue", forbidden)
    monkeypatch.setattr(assessor_module.ElementEvidenceAssessor, "assess", forbidden)
    monkeypatch.setattr(renderer_module.StructuredLegalAnalysisRenderer, "render", forbidden)
    monkeypatch.setattr(repository_module.CaseRepository, "list_all", forbidden)

    original_import = builtins.__import__
    blocked_roots = {
        "retriever",
        "query_expander",
        "legal_analysis_retrieval_adapter",
        "openai",
        "chromadb",
    }

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split(".", 1)[0] in blocked_roots:
            raise AssertionError(f"Gate 1 attempted forbidden live import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    execution = run_frozen_gate1(snapshot)
    assert execution.chronology.events


@pytest.mark.parametrize("component", ["m5_results", "foundation", "matrices"])
def test_gate1_tampered_component_fails_before_chronology(component):
    snapshot = copy.deepcopy(_snapshot())
    if component == "m5_results":
        snapshot["components"][component][0]["overall_limitations"].append("tamper")
    elif component == "foundation":
        snapshot["components"][component]["synthesiser_version"] = "tamper"
    else:
        snapshot["components"][component]["matrix_builder_version"] = "tamper"

    with pytest.raises(ValueError, match="component hash verification failed"):
        run_frozen_gate1(snapshot)


def test_gate1_tampered_analytical_state_hash_fails_before_chronology():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["analytical_state_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="analytical-state hash verification failed"):
        run_frozen_gate1(snapshot)


def test_gate1_h2_valid_but_invalid_native_m5_fails_deserialization():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["components"]["m5_results"][0].pop("issue_synthesis")
    _refresh_h2_hashes(snapshot)

    with pytest.raises(ValueError, match="M5 native reconstruction failed"):
        run_frozen_gate1(snapshot)


def test_gate1_h2_valid_native_normalization_difference_fails_round_trip():
    snapshot = copy.deepcopy(_snapshot())
    item = snapshot["components"]["m5_results"][0]
    item["overall_limitations"][0] = item["overall_limitations"][0] + "  "
    _refresh_h2_hashes(snapshot)

    with pytest.raises(ValueError, match="M5 canonical round-trip verification failed"):
        run_frozen_gate1(snapshot)


def test_gate1_cross_component_identity_mismatch_fails_native_validation():
    snapshot = _snapshot()
    # Build a new H2-valid snapshot whose M5 keeps the same issue IDs/case ID but
    # changes a source-analysis field checked by M1 lineage validation.
    results, foundation, matrices = _native_inputs()
    changed_analysis = replace(
        results[0].assessment_result.assessed_analysis,
        issue_name="Different frozen issue name",
    )
    changed_assessment = replace(
        results[0].assessment_result,
        assessed_analysis=changed_analysis,
    )
    changed_result = replace(results[0], assessment_result=changed_assessment)
    inconsistent = build_frozen_snapshot(
        results=(changed_result, results[1]),
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h3-checkpoint",
    )

    with pytest.raises(ValueError):
        run_frozen_gate1(inconsistent)
