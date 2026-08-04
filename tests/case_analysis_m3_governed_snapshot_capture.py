"""Harness-only H5 governed capture for the Shafi M3 frozen analytical state.

H5 is the only harness milestone authorised to write a complete frozen analytical
snapshot.  It never regenerates analysis itself: callers must supply one atomic
native M5/M1/M2 state.  Before writing, it verifies the immutable legacy fixture,
validates/reconstructs the H2/H3 snapshot entirely in memory, and proves repeated
Gate 1 chronology determinism.  The target snapshot is write-once.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from case_analysis.m2.matrices import CaseMatrices
from case_analysis.models import CaseAnalysisFoundation
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis_m3_frozen_gate1 import (
    FrozenGate1Execution,
    load_frozen_gate1_inputs,
    run_frozen_gate1,
)
from case_analysis_m3_frozen_m5_serialization import (
    structured_legal_analysis_result_to_dict,
)
from case_analysis_m3_frozen_snapshot_envelope import (
    build_frozen_snapshot,
    dumps_frozen_snapshot,
    loads_frozen_snapshot,
    validate_frozen_snapshot,
)
from case_analysis_m3_live_fixture_capture import build_live_fixture_payload

GOVERNED_CAPTURE_PURPOSE = "Sprint 2.4 M3 deterministic Gate 1 acceptance"
LEGACY_FIXTURE_NAME = "shafi_chronology_live_v1_0.json"
LEGACY_FIXTURE_VERSION = "shafi-chronology-live-fixture/1.0"
REQUIRED_LEGACY_FIXTURE_SHA256 = (
    "833124866a8afec8d071d94c6c973890cf45a4a8c26c9451706d51cc3c18965c"
)
TARGET_SNAPSHOT_NAME = "shafi_m3_frozen_analytical_snapshot_v1_0.json"
APPROVED_FOUR_QUESTIONS = (
    "What evidence shows CACI knew about my disability?",
    "Should CACI have allowed me to work from home because of my disability?",
    "Is my claim out of time if the failures continued?",
    "Was I treated unfavourably because of something arising from my disability?",
)


class SnapshotProvenanceClassification(StrEnum):
    ORIGINAL_CAPTURE_STATE = "ORIGINAL_CAPTURE_STATE"
    NEW_GOVERNED_FROZEN_STATE = "NEW_GOVERNED_FROZEN_STATE"


@dataclass(frozen=True, slots=True)
class LegacyFixtureCompatibility:
    semantic_match: bool
    drifts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GovernedSnapshotCaptureReport:
    provenance_classification: SnapshotProvenanceClassification
    provenance_rationale: str
    snapshot_path: str
    snapshot_file_sha256: str
    analytical_state_sha256: str
    m5_sha256: str
    m1_sha256: str
    m2_sha256: str
    legacy_fixture_sha_before: str
    legacy_fixture_sha_after: str
    legacy_fixture_compatibility: LegacyFixtureCompatibility
    gate1_reconstruction_passed: bool
    gate1_deterministic: bool
    chronology_round_trip_identical: bool
    chronology_event_count: int
    dated_event_count: int
    multi_issue_event_count: int


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_results(
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[StructuredLegalAnalysisResult, ...]:
    resolved = tuple(results)
    return tuple(
        sorted(
            resolved,
            key=lambda item: (
                item.assessment_result.assessed_analysis.issue_definition_id,
                item.assessment_result.assessed_analysis.issue_definition_version,
                item.assessment_result.assessed_analysis.issue_analysis_id,
            ),
        )
    )


def _semantic_use(use: Mapping[str, object]) -> dict[str, object]:
    return {
        "issue_definition_id": use.get("issue_definition_id"),
        "issue_definition_version": use.get("issue_definition_version"),
        "element_id": use.get("element_id"),
        "element_ordinal": use.get("element_ordinal"),
        "analytical_role": use.get("analytical_role"),
        "mapping_relevance": use.get("mapping_relevance"),
        "mapping_confidence": use.get("mapping_confidence"),
        "assessment_confidence": use.get("assessment_confidence"),
        "proposition_links": [
            {
                "source_proposition_index": link.get("source_proposition_index"),
                "text": link.get("text"),
                "status": link.get("status"),
                "confidence": link.get("confidence"),
                "rationale": link.get("rationale"),
                "evidence_keys": link.get("evidence_keys"),
            }
            for link in use.get("proposition_links", ())
            if isinstance(link, Mapping)
        ],
    }


def compare_candidate_to_legacy_fixture(
    legacy_payload: Mapping[str, object],
    *,
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
) -> LegacyFixtureCompatibility:
    """Compare fields the historical partial fixture actually froze.

    Run-instance issue_analysis_id/synthesis_id/source_analysis_ids are deliberately
    excluded from semantic compatibility because fresh analytical runs create new
    native identities.  This comparison never mutates either side.
    """

    candidate = build_live_fixture_payload(matrices, tuple(results))
    drifts: list[str] = []
    if str(legacy_payload.get("case_id")) != str(candidate.get("case_id")):
        drifts.append("CASE_ID_DRIFT")

    legacy_records = {
        str(item["evidence_key"]): item
        for item in legacy_payload.get("evidence", ())
        if isinstance(item, Mapping) and "evidence_key" in item
    }
    candidate_records = {
        str(item["evidence_key"]): item
        for item in candidate.get("evidence", ())
        if isinstance(item, Mapping) and "evidence_key" in item
    }
    if set(legacy_records) != set(candidate_records):
        drifts.append("EVIDENCE_SET_DRIFT")

    for evidence_key in sorted(set(legacy_records) & set(candidate_records)):
        frozen = legacy_records[evidence_key]
        current = candidate_records[evidence_key]
        stable_fields = (
            "document_id",
            "document_name",
            "page",
            "chunk_id",
            "citation",
            "summary",
            "summary_sha256",
            "date",
            "author",
            "parties",
        )
        if any(frozen.get(field) != current.get(field) for field in stable_fields):
            drifts.append(f"EVIDENCE_CONTENT_DRIFT:{evidence_key}")

        frozen_uses = sorted(
            (_semantic_use(item) for item in frozen.get("uses", ()) if isinstance(item, Mapping)),
            key=_canonical_json,
        )
        current_uses = sorted(
            (_semantic_use(item) for item in current.get("uses", ()) if isinstance(item, Mapping)),
            key=_canonical_json,
        )
        if frozen_uses != current_uses:
            drifts.append(f"EVIDENCE_USE_DRIFT:{evidence_key}")

    return LegacyFixtureCompatibility(
        semantic_match=not drifts,
        drifts=tuple(drifts),
    )


def _validate_provenance_classification(
    classification: SnapshotProvenanceClassification,
    *,
    original_complete_state_verified: bool,
    rationale: str,
) -> None:
    if not rationale.strip():
        raise ValueError("Governed snapshot provenance rationale must not be empty.")
    if (
        classification is SnapshotProvenanceClassification.ORIGINAL_CAPTURE_STATE
        and not original_complete_state_verified
    ):
        raise ValueError(
            "ORIGINAL_CAPTURE_STATE requires independent verification of the exact "
            "complete original M5/M1/M2 state."
        )


def prepare_governed_snapshot(
    *,
    results: Iterable[StructuredLegalAnalysisResult],
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    legacy_fixture_path: str | Path,
    captured_at: str,
    source_checkpoint: str,
    provenance_classification: SnapshotProvenanceClassification,
    provenance_rationale: str,
    approved_questions: Sequence[str] = APPROVED_FOUR_QUESTIONS,
    original_complete_state_verified: bool = False,
    expected_legacy_fixture_sha256: str = REQUIRED_LEGACY_FIXTURE_SHA256,
) -> tuple[dict[str, object], FrozenGate1Execution, LegacyFixtureCompatibility, str]:
    """Prepare and fully validate a governed snapshot entirely in memory."""

    _validate_provenance_classification(
        provenance_classification,
        original_complete_state_verified=original_complete_state_verified,
        rationale=provenance_rationale,
    )
    questions = tuple(str(item) for item in approved_questions)
    if questions != APPROVED_FOUR_QUESTIONS:
        raise ValueError("Governed Shafi snapshot must use the exact approved four questions.")

    legacy_path = Path(legacy_fixture_path)
    if not legacy_path.is_file():
        raise ValueError("Immutable legacy fixture is missing.")
    legacy_sha = _sha256_file(legacy_path)
    if legacy_sha != expected_legacy_fixture_sha256:
        raise ValueError("Immutable legacy fixture SHA-256 does not match the governed value.")
    try:
        legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Immutable legacy fixture cannot be parsed.") from exc
    if not isinstance(legacy_payload, Mapping):
        raise ValueError("Immutable legacy fixture must contain an object.")

    snapshot = build_frozen_snapshot(
        results=tuple(results),
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_name=LEGACY_FIXTURE_NAME,
        legacy_fixture_version=LEGACY_FIXTURE_VERSION,
        legacy_fixture_sha256=legacy_sha,
        captured_at=captured_at,
        source_checkpoint=source_checkpoint,
    )
    snapshot["manifest"]["capture_governance"] = {
        "capture_purpose": GOVERNED_CAPTURE_PURPOSE,
        "approved_questions": list(questions),
        "provenance_classification": provenance_classification.value,
        "provenance_rationale": provenance_rationale.strip(),
        "original_complete_state_verified": bool(original_complete_state_verified),
    }
    validate_frozen_snapshot(
        snapshot,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )

    # H3 reconstruction must exactly reproduce the supplied native analytical state
    # modulo H2's explicitly canonical outer M5 result ordering.
    reconstructed = load_frozen_gate1_inputs(
        snapshot,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    expected_results = _canonical_results(tuple(results))
    if reconstructed.results != expected_results:
        raise ValueError("Governed snapshot M5 reconstruction differs from capture input.")
    if reconstructed.foundation != foundation:
        raise ValueError("Governed snapshot M1 reconstruction differs from capture input.")
    if reconstructed.matrices != matrices:
        raise ValueError("Governed snapshot M2 reconstruction differs from capture input.")

    # Canonical bytes are proven by H2/H3; repeat Gate 1 twice here so capture itself
    # fails closed if chronology execution is not deterministic.
    first = run_frozen_gate1(
        snapshot,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    second = run_frozen_gate1(
        dumps_frozen_snapshot(snapshot),
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    if first.chronology != second.chronology or first.chronology_json != second.chronology_json:
        raise ValueError("Governed snapshot Gate 1 chronology is nondeterministic.")

    compatibility = compare_candidate_to_legacy_fixture(
        legacy_payload,
        matrices=matrices,
        results=expected_results,
    )
    return snapshot, first, compatibility, legacy_sha


def write_governed_snapshot_once(
    *,
    target_path: str | Path,
    results: Iterable[StructuredLegalAnalysisResult],
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    legacy_fixture_path: str | Path,
    captured_at: str,
    source_checkpoint: str,
    provenance_classification: SnapshotProvenanceClassification,
    provenance_rationale: str,
    approved_questions: Sequence[str] = APPROVED_FOUR_QUESTIONS,
    original_complete_state_verified: bool = False,
    expected_legacy_fixture_sha256: str = REQUIRED_LEGACY_FIXTURE_SHA256,
) -> GovernedSnapshotCaptureReport:
    """Write one governed snapshot after all pre-write checks pass, then verify it."""

    destination = Path(target_path)
    if destination.exists():
        raise ValueError("Governed snapshot target already exists; overwrite is prohibited.")

    legacy_path = Path(legacy_fixture_path)
    snapshot, first, compatibility, legacy_before = prepare_governed_snapshot(
        results=tuple(results),
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=legacy_path,
        captured_at=captured_at,
        source_checkpoint=source_checkpoint,
        provenance_classification=provenance_classification,
        provenance_rationale=provenance_rationale,
        approved_questions=approved_questions,
        original_complete_state_verified=original_complete_state_verified,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )

    canonical_payload = dumps_frozen_snapshot(snapshot)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_payload.encode("utf-8"))

    file_sha = _sha256_file(destination)
    reloaded = loads_frozen_snapshot(
        destination.read_text(encoding="utf-8"),
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    post = run_frozen_gate1(
        reloaded,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    if post.chronology != first.chronology or post.chronology_json != first.chronology_json:
        raise ValueError("Post-write Gate 1 chronology differs from the in-memory capture.")

    legacy_after = _sha256_file(legacy_path)
    if legacy_after != legacy_before:
        raise ValueError("Immutable legacy fixture changed during governed snapshot capture.")

    hashes = snapshot["component_hashes"]
    chronology = post.chronology
    return GovernedSnapshotCaptureReport(
        provenance_classification=provenance_classification,
        provenance_rationale=provenance_rationale.strip(),
        snapshot_path=str(destination),
        snapshot_file_sha256=file_sha,
        analytical_state_sha256=str(snapshot["analytical_state_sha256"]),
        m5_sha256=str(hashes["m5_results_sha256"]),
        m1_sha256=str(hashes["foundation_sha256"]),
        m2_sha256=str(hashes["matrices_sha256"]),
        legacy_fixture_sha_before=legacy_before,
        legacy_fixture_sha_after=legacy_after,
        legacy_fixture_compatibility=compatibility,
        gate1_reconstruction_passed=True,
        gate1_deterministic=True,
        chronology_round_trip_identical=True,
        chronology_event_count=len(chronology.events),
        dated_event_count=sum(
            event.canonical_temporal_extent is not None for event in chronology.events
        ),
        multi_issue_event_count=sum(
            len(event.related_issue_definition_ids) > 1 for event in chronology.events
        ),
    )


__all__ = [
    "APPROVED_FOUR_QUESTIONS",
    "GOVERNED_CAPTURE_PURPOSE",
    "LEGACY_FIXTURE_NAME",
    "LEGACY_FIXTURE_VERSION",
    "REQUIRED_LEGACY_FIXTURE_SHA256",
    "TARGET_SNAPSHOT_NAME",
    "GovernedSnapshotCaptureReport",
    "LegacyFixtureCompatibility",
    "SnapshotProvenanceClassification",
    "compare_candidate_to_legacy_fixture",
    "prepare_governed_snapshot",
    "write_governed_snapshot_once",
]
