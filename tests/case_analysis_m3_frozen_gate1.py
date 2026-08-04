"""Harness-only H3 loader/reconstruction for frozen M3 Gate 1 acceptance.

H3 reconstructs the exact native M5/M1/M2 inputs from an already validated H2
snapshot and executes the existing M3 chronology builder entirely offline. It
never rebuilds upstream analysis or writes snapshot/fixture state.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping

from case_analysis import serialization as m1_serialization
from case_analysis.m2 import matrix_serialization as m2_serialization
from case_analysis.m2.matrices import CaseMatrices
from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.chronology_serialization import (
    dumps_case_chronology,
    loads_case_chronology,
)
from case_analysis.m3.chronology_validation import resolve_chronology_inputs
from case_analysis.m3.models import CaseChronology
from case_analysis.models import CaseAnalysisFoundation
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis_m3_frozen_m5_serialization import (
    structured_legal_analysis_result_from_dict,
    structured_legal_analysis_result_to_dict,
)
from case_analysis_m3_frozen_snapshot_envelope import loads_frozen_snapshot


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class FrozenGate1Inputs:
    """Exact native M3 inputs reconstructed from one frozen snapshot."""

    analytical_state_sha256: str
    results: tuple[StructuredLegalAnalysisResult, ...]
    foundation: CaseAnalysisFoundation
    matrices: CaseMatrices


@dataclass(frozen=True, slots=True)
class FrozenGate1Execution:
    """One deterministic offline Gate 1 chronology execution."""

    analytical_state_sha256: str
    results: tuple[StructuredLegalAnalysisResult, ...]
    foundation: CaseAnalysisFoundation
    matrices: CaseMatrices
    chronology: CaseChronology
    chronology_json: str


def _load_snapshot_payload(
    payload: str | Mapping[str, Any],
    *,
    expected_legacy_fixture_sha256: str | None,
) -> dict[str, Any]:
    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, Mapping):
        text = _canonical_json(dict(payload))
    else:
        raise ValueError("Frozen Gate 1 snapshot must be canonical JSON or an object.")
    return loads_frozen_snapshot(
        text,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )


def _reconstruct_m5(component: object) -> tuple[StructuredLegalAnalysisResult, ...]:
    if not isinstance(component, list) or not component:
        raise ValueError("Frozen Gate 1 M5 component must be a non-empty list.")
    try:
        results = tuple(
            structured_legal_analysis_result_from_dict(item)
            for item in component
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen Gate 1 M5 native reconstruction failed.") from exc

    round_trip = [structured_legal_analysis_result_to_dict(item) for item in results]
    if _canonical_json(round_trip) != _canonical_json(component):
        raise ValueError("Frozen Gate 1 M5 canonical round-trip verification failed.")
    return results


def _reconstruct_foundation(component: object) -> CaseAnalysisFoundation:
    if not isinstance(component, Mapping):
        raise ValueError("Frozen Gate 1 M1 component must contain an object.")
    frozen = _canonical_json(component)
    try:
        foundation = m1_serialization.loads_case_analysis_foundation(frozen)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen Gate 1 M1 native reconstruction failed.") from exc
    if m1_serialization.dumps_case_analysis_foundation(foundation) != frozen:
        raise ValueError("Frozen Gate 1 M1 canonical round-trip verification failed.")
    return foundation


def _reconstruct_matrices(component: object) -> CaseMatrices:
    if not isinstance(component, Mapping):
        raise ValueError("Frozen Gate 1 M2 component must contain an object.")
    frozen = _canonical_json(component)
    try:
        matrices = m2_serialization.loads_case_matrices(frozen)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen Gate 1 M2 native reconstruction failed.") from exc
    if m2_serialization.dumps_case_matrices(matrices) != frozen:
        raise ValueError("Frozen Gate 1 M2 canonical round-trip verification failed.")
    return matrices


def load_frozen_gate1_inputs(
    payload: str | Mapping[str, Any],
    *,
    expected_legacy_fixture_sha256: str | None = None,
) -> FrozenGate1Inputs:
    """Validate one H2 snapshot and reconstruct the exact native M3 inputs."""

    snapshot = _load_snapshot_payload(
        payload,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    components = snapshot["components"]
    results = _reconstruct_m5(components["m5_results"])
    foundation = _reconstruct_foundation(components["foundation"])
    matrices = _reconstruct_matrices(components["matrices"])

    # Existing production validation remains authoritative for native lineage.
    resolved = resolve_chronology_inputs(foundation, matrices, results)
    if resolved != results:
        # H2 already stores the M5 result set in canonical source order. Gate 1
        # therefore fails rather than silently accepting a differently ordered
        # reconstructed native source set.
        raise ValueError("Frozen Gate 1 native M5 source order does not match M1 lineage.")

    return FrozenGate1Inputs(
        analytical_state_sha256=str(snapshot["analytical_state_sha256"]),
        results=results,
        foundation=foundation,
        matrices=matrices,
    )


def run_frozen_gate1(
    payload: str | Mapping[str, Any],
    *,
    expected_legacy_fixture_sha256: str | None = None,
) -> FrozenGate1Execution:
    """Run deterministic M3 acceptance from one validated frozen snapshot."""

    inputs = load_frozen_gate1_inputs(
        payload,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    results_before = copy.deepcopy(inputs.results)
    foundation_before = copy.deepcopy(inputs.foundation)
    matrices_before = copy.deepcopy(inputs.matrices)

    chronology = build_case_chronology(
        inputs.foundation,
        inputs.matrices,
        inputs.results,
    )

    if inputs.results != results_before:
        raise ValueError("Frozen Gate 1 M5 inputs were mutated by M3.")
    if inputs.foundation != foundation_before:
        raise ValueError("Frozen Gate 1 M1 foundation was mutated by M3.")
    if inputs.matrices != matrices_before:
        raise ValueError("Frozen Gate 1 M2 matrices were mutated by M3.")

    chronology_json = dumps_case_chronology(chronology)
    restored = loads_case_chronology(chronology_json)
    if restored != chronology:
        raise ValueError("Frozen Gate 1 chronology round-trip verification failed.")
    if dumps_case_chronology(restored) != chronology_json:
        raise ValueError("Frozen Gate 1 chronology canonical bytes are unstable.")

    return FrozenGate1Execution(
        analytical_state_sha256=inputs.analytical_state_sha256,
        results=inputs.results,
        foundation=inputs.foundation,
        matrices=inputs.matrices,
        chronology=chronology,
        chronology_json=chronology_json,
    )


__all__ = [
    "FrozenGate1Execution",
    "FrozenGate1Inputs",
    "load_frozen_gate1_inputs",
    "run_frozen_gate1",
]
