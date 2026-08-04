"""Explicit local H5 capture entry point for the governed Shafi M3 snapshot.

This is intentionally not a pytest test and is never invoked by Gate 1/2. Run it
only as the authorised H5 capture operation on the user's local LegalRAG case
state. It performs one live four-question upstream run, then hands the resulting
atomic M5/M1/M2 objects to the governed write-once capture helper.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from case_management.repository import CaseRepository
from legal_analysis.selector import DeterministicIssueSelector
from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices

from case_analysis_m3_governed_snapshot_capture import (
    APPROVED_FOUR_QUESTIONS,
    REQUIRED_LEGACY_FIXTURE_SHA256,
    SnapshotProvenanceClassification,
    write_governed_snapshot_once,
)

LEGACY_PATH = Path("tests/fixtures/shafi_chronology_live_v1_0.json")
TARGET_PATH = Path("tests/fixtures/shafi_m3_frozen_analytical_snapshot_v1_0.json")


def main() -> None:
    case = next(
        item
        for item in CaseRepository().list_all()
        if item.name.casefold() == "shafi v caci ltd".casefold()
    )

    selector = DeterministicIssueSelector()
    mapper = ElementEvidenceMapper()
    assessor = ElementEvidenceAssessor()
    renderer = StructuredLegalAnalysisRenderer()

    results = []
    for question in APPROVED_FOUR_QUESTIONS:
        selection = selector.select(question, case_id=case.case_id)
        mapped = mapper.map_primary_issue(
            case_id=case.case_id,
            user_question=question,
            selection=selection,
        )
        assessed = assessor.assess(mapped)
        results.append(renderer.render(assessed))
    frozen_results = tuple(results)
    foundation = build_case_analysis_foundation(frozen_results)
    matrices = build_case_matrices(foundation, frozen_results)

    report = write_governed_snapshot_once(
        target_path=TARGET_PATH,
        results=frozen_results,
        foundation=foundation,
        matrices=matrices,
        legacy_fixture_path=LEGACY_PATH,
        captured_at=datetime.now().astimezone().isoformat(),
        source_checkpoint="sprint-2.4-m3-h5-new-governed-state-uncommitted",
        provenance_classification=SnapshotProvenanceClassification.NEW_GOVERNED_FROZEN_STATE,
        provenance_rationale=(
            "The historical shafi_chronology_live_v1_0.json preserves only a partial "
            "M2/M4 boundary and no persisted complete original M5/M1/M2 capture state "
            "was available. This is therefore a new atomic governed four-question "
            "analytical state, not a reconstruction of the original capture run."
        ),
        expected_legacy_fixture_sha256=REQUIRED_LEGACY_FIXTURE_SHA256,
    )

    print("SNAPSHOT PROVENANCE:", report.provenance_classification.value)
    print("SNAPSHOT PATH:", report.snapshot_path)
    print("SNAPSHOT SHA256:", report.snapshot_file_sha256)
    print("ANALYTICAL STATE SHA256:", report.analytical_state_sha256)
    print("M5 SHA256:", report.m5_sha256)
    print("M1 SHA256:", report.m1_sha256)
    print("M2 SHA256:", report.m2_sha256)
    print("LEGACY SHA BEFORE:", report.legacy_fixture_sha_before)
    print("LEGACY SHA AFTER:", report.legacy_fixture_sha_after)
    print("LEGACY SEMANTIC MATCH:", report.legacy_fixture_compatibility.semantic_match)
    for drift in report.legacy_fixture_compatibility.drifts:
        print("LEGACY DRIFT:", drift)
    print("GATE 1 RECONSTRUCTION:", report.gate1_reconstruction_passed)
    print("GATE 1 DETERMINISTIC:", report.gate1_deterministic)
    print("CHRONOLOGY ROUND TRIP:", report.chronology_round_trip_identical)
    print("EVENTS:", report.chronology_event_count)
    print("DATED EVENTS:", report.dated_event_count)
    print("MULTI-ISSUE EVENTS:", report.multi_issue_event_count)


if __name__ == "__main__":
    main()
