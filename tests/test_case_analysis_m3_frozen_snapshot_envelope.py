from __future__ import annotations

import copy
import json

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m3_frozen_snapshot_envelope import (
    FROZEN_SNAPSHOT_SCHEMA_VERSION,
    build_frozen_snapshot,
    dumps_frozen_snapshot,
    loads_frozen_snapshot,
    validate_frozen_snapshot,
)
from case_analysis_m3_frozen_m5_serialization import (
    structured_legal_analysis_result_to_dict,
)

LEGACY_SHA = "8" * 64


def _native_inputs():
    shared = evidence(
        key="shared-h2-evidence",
        document_name="shared-h2.pdf",
        summary="The employer and claimant exchanged return-to-work information.",
    )
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="11111111-1111-4111-8111-111111111101",
        evidence_by_element={"EK-DIRECT-KNOWLEDGE": (shared,)},
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="11111111-1111-4111-8111-111111111102",
        evidence_by_element={"RA-KNOWLEDGE": (shared,)},
    )
    results = (ra, ek)  # Deliberately non-canonical caller order.
    foundation = build_case_analysis_foundation(results)
    matrices = build_case_matrices(foundation, results)
    return results, foundation, matrices


def _snapshot(*, captured_at: str = "2026-08-03T12:00:00+01:00", results=None):
    base_results, foundation, matrices = _native_inputs()
    return build_frozen_snapshot(
        results=results or base_results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at=captured_at,
        source_checkpoint="synthetic-h2-checkpoint",
    )


def test_snapshot_round_trip_and_canonical_bytes_are_stable():
    original = _snapshot()
    first = dumps_frozen_snapshot(original)
    restored = loads_frozen_snapshot(first, expected_legacy_fixture_sha256=LEGACY_SHA)
    second = dumps_frozen_snapshot(restored)

    assert restored == original
    assert second == first
    assert first == json.dumps(
        json.loads(first),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_analytical_identity_is_stable_under_reversed_outer_m5_order():
    results, foundation, matrices = _native_inputs()
    first = build_frozen_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h2-checkpoint",
    )
    second = build_frozen_snapshot(
        results=tuple(reversed(results)),
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h2-checkpoint",
    )

    assert first["analytical_state_sha256"] == second["analytical_state_sha256"]
    assert first["component_hashes"] == second["component_hashes"]
    assert dumps_frozen_snapshot(first) == dumps_frozen_snapshot(second)


def test_capture_metadata_does_not_change_analytical_identity():
    results, foundation, matrices = _native_inputs()
    common = dict(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        source_checkpoint="synthetic-h2-checkpoint",
    )
    first = build_frozen_snapshot(
        **common,
        captured_at="2026-08-03T12:00:00+01:00",
    )
    second = build_frozen_snapshot(
        **common,
        captured_at="2027-01-01T00:00:00+00:00",
    )

    assert first["analytical_state_sha256"] == second["analytical_state_sha256"]
    assert first["component_hashes"] == second["component_hashes"]
    assert dumps_frozen_snapshot(first) != dumps_frozen_snapshot(second)


def test_snapshot_reuses_exact_existing_m1_m2_and_h1_serializations():
    results, foundation, matrices = _native_inputs()
    snapshot = build_frozen_snapshot(
        results=results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name="shafi_chronology_live_v1_0.json",
        legacy_fixture_version="shafi-chronology-live-fixture/1.0",
        legacy_fixture_sha256=LEGACY_SHA,
        captured_at="2026-08-03T12:00:00+01:00",
        source_checkpoint="synthetic-h2-checkpoint",
    )

    assert snapshot["components"]["foundation"] == json.loads(
        dumps_case_analysis_foundation(foundation)
    )
    assert snapshot["components"]["matrices"] == json.loads(dumps_case_matrices(matrices))
    expected_m5 = sorted(
        (structured_legal_analysis_result_to_dict(item) for item in results),
        key=lambda item: (
            item["assessment_result"]["assessed_analysis"]["issue_definition_id"],
            item["assessment_result"]["assessed_analysis"]["issue_definition_version"],
            item["assessment_result"]["assessed_analysis"]["issue_analysis_id"],
        ),
    )
    assert snapshot["components"]["m5_results"] == expected_m5


@pytest.mark.parametrize("component_name", ["m5_results", "foundation", "matrices"])
def test_tampered_component_payload_fails_hash_verification(component_name):
    snapshot = copy.deepcopy(_snapshot())
    component = snapshot["components"][component_name]
    if component_name == "m5_results":
        component[0]["overall_limitations"].append("tampered")
    elif component_name == "foundation":
        component["synthesiser_version"] = "tampered"
    else:
        component["matrix_builder_version"] = "tampered"

    with pytest.raises(ValueError, match="component hash verification failed"):
        validate_frozen_snapshot(snapshot)


def test_tampered_analytical_state_hash_fails_closed():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["analytical_state_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="analytical-state hash verification failed"):
        validate_frozen_snapshot(snapshot)


def test_tampered_manifest_relationship_fails_closed_even_with_valid_components():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["manifest"]["case_id"] = "22222222-2222-4222-8222-222222222222"

    with pytest.raises(ValueError, match="manifest case_id"):
        validate_frozen_snapshot(snapshot)


def test_incorrect_expected_legacy_fixture_sha_fails_closed():
    snapshot = _snapshot()

    with pytest.raises(ValueError, match="legacy-fixture SHA does not match"):
        validate_frozen_snapshot(
            snapshot,
            expected_legacy_fixture_sha256="9" * 64,
        )


def test_invalid_legacy_fixture_sha_shape_fails_closed():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["manifest"]["legacy_fixture"]["sha256"] = "not-a-sha"

    with pytest.raises(ValueError, match="must be a lowercase SHA-256 hex digest"):
        validate_frozen_snapshot(snapshot)


def test_unsupported_snapshot_schema_is_rejected():
    snapshot = copy.deepcopy(_snapshot())
    snapshot["schema_version"] = "m3-frozen-analytical-snapshot/9.9"

    with pytest.raises(ValueError, match="Unsupported frozen snapshot schema"):
        validate_frozen_snapshot(snapshot)


def test_supported_schema_is_explicit_and_stable():
    assert FROZEN_SNAPSHOT_SCHEMA_VERSION == "m3-frozen-analytical-snapshot/1.0"
