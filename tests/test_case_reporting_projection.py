from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path

import pytest

import case_reporting.projection as projection_module
from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m3.models import CaseChronology
from case_analysis.m4.serialization import dumps_case_synthesis
from case_analysis.m4.synthesis import build_case_synthesis
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import make_case_synthesis, synthetic_sources
from legal_analysis.enums import AnalyticalRole, Confidence
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus
from case_reporting import (
    CaseReportMetadata,
    build_case_report_projection,
    dumps_case_report_projection,
    loads_case_report_projection,
    validate_case_report_projection,
)
from case_reporting.models import (
    REPORT_MANIFEST_BUILDER_VERSION,
    REPORT_MANIFEST_SCHEMA_VERSION,
    REPORT_PROJECTION_SCHEMA_VERSION,
    REPORT_PROJECTOR_VERSION,
    SECTION_KEYS,
)


def sources_and_projection(*, higher_order: bool = False, metadata=None):
    if higher_order:
        foundation, matrices, chronology = synthetic_sources()
        synthesis = build_case_synthesis(foundation, matrices, chronology)
    else:
        foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    projection = build_case_report_projection(
        foundation,
        matrices,
        chronology,
        synthesis,
        metadata,
    )
    return foundation, matrices, chronology, synthesis, projection


def test_projection_versions_and_first_class_manifest_are_frozen():
    _, _, _, _, value = sources_and_projection()
    assert value.schema_version == REPORT_PROJECTION_SCHEMA_VERSION
    assert value.projector_version == REPORT_PROJECTOR_VERSION
    assert value.manifest.schema_version == REPORT_MANIFEST_SCHEMA_VERSION
    assert value.manifest.builder_version == REPORT_MANIFEST_BUILDER_VERSION
    assert value.manifest.report_projection_id == value.report_projection_id
    assert value.manifest.projection_payload_sha256 == value.projection_payload_sha256


def test_projection_is_deterministic_and_byte_stable():
    foundation, matrices, chronology, synthesis, first = sources_and_projection()
    second = build_case_report_projection(foundation, matrices, chronology, synthesis)
    assert second == first
    assert second.report_projection_id == first.report_projection_id
    assert second.manifest.manifest_id == first.manifest.manifest_id
    assert dumps_case_report_projection(second) == dumps_case_report_projection(first)


def test_exact_metadata_changes_projection_identity_and_is_copied_without_inference():
    foundation, matrices, chronology, synthesis, without = sources_and_projection()
    metadata = CaseReportMetadata(
        case_name="Shafi v CACI Ltd",
        case_number="2207441/2025",
        claimant="Arshad Shafi",
        respondent="CACI Ltd",
        case_status="Active",
        court_or_tribunal="London Central Employment Tribunal",
    )
    with_metadata = build_case_report_projection(foundation, matrices, chronology, synthesis, metadata)
    assert with_metadata.report_projection_id != without.report_projection_id
    assert with_metadata.source_metadata_sha256 is not None
    assert with_metadata.case_header.case_name == "Shafi v CACI Ltd"
    assert without.case_header.case_name is None


def test_canonical_json_round_trip_is_exact():
    _, _, _, _, value = sources_and_projection(metadata=CaseReportMetadata(case_name="Case"))
    payload = dumps_case_report_projection(value)
    restored = loads_case_report_projection(payload)
    assert restored == value
    assert dumps_case_report_projection(restored) == payload


def test_source_fingerprints_match_exact_frozen_canonical_serializers():
    foundation, matrices, chronology, synthesis, value = sources_and_projection()
    assert value.source_foundation_sha256 == sha256(dumps_case_analysis_foundation(foundation).encode()).hexdigest()
    assert value.source_matrices_sha256 == sha256(dumps_case_matrices(matrices).encode()).hexdigest()
    assert value.source_chronology_sha256 == sha256(dumps_case_chronology(chronology).encode()).hexdigest()
    assert value.source_synthesis_sha256 == sha256(dumps_case_synthesis(synthesis).encode()).hexdigest()


def test_projection_does_not_mutate_any_source_object():
    foundation, matrices, chronology, synthesis, _ = sources_and_projection()
    before = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
        dumps_case_synthesis(synthesis),
    )
    build_case_report_projection(foundation, matrices, chronology, synthesis)
    after = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
        dumps_case_synthesis(synthesis),
    )
    assert after == before


def test_projection_and_manifest_are_immutable():
    _, _, _, _, value = sources_and_projection()
    with pytest.raises(FrozenInstanceError):
        value.report_projection_id = "changed"
    with pytest.raises(FrozenInstanceError):
        value.manifest.manifest_id = "changed"


def test_citation_catalogue_has_one_stable_record_per_evidence_key():
    _, matrices, _, _, value = sources_and_projection()
    assert tuple(item.citation_id for item in value.citations) == tuple(
        item.evidence_key for item in matrices.evidence_matrix
    )
    assert all(item.citation_id == item.evidence_key for item in value.citations)
    assert len(value.citations) == len({item.citation_id for item in value.citations})


def test_occurrence_and_timing_remain_independent_in_projection_and_manifest():
    _, _, _, _, value = sources_and_projection()
    event = value.chronology[0]
    assert event.occurrence_status.raw_value == "supported"
    assert event.timing_status.raw_value == "established"
    assert event.occurrence_status.raw_value != event.timing_status.raw_value
    raw = dict(value.manifest.raw_status_inventory)
    assert "supported" in raw.values()
    assert "established" in raw.values()
    assert "Established Event" not in dumps_case_report_projection(value)


def test_event_projection_deduplicates_element_coordinates_without_dropping_assertions():
    _, matrices, chronology, _, _ = sources_and_projection()
    event = chronology.events[0]
    first = event.assertions[0]
    second = replace(
        first,
        assertion_id="00000000-0000-4000-8000-000000000001",
        extraction_ordinal=first.extraction_ordinal + 1,
    )
    repeated_coordinate_event = replace(
        event,
        assertions=(*event.assertions, second),
    )
    evidence_by_key = {item.evidence_key: item for item in matrices.evidence_matrix}

    report = projection_module._event_report(repeated_coordinate_event, evidence_by_key)

    assert report.related_element_coordinates == tuple(
        sorted(
            {
                (item.issue_analysis_id, item.element_id)
                for item in repeated_coordinate_event.assertions
            }
        )
    )
    assert len(report.related_element_coordinates) < len(repeated_coordinate_event.assertions)
    assert len(report.assertions) == len(repeated_coordinate_event.assertions)
    assert tuple(item.assertion_id for item in report.assertions) == tuple(
        item.assertion_id for item in repeated_coordinate_event.assertions
    )


def test_neutral_medium_explanations_do_not_create_importance_or_urgency():
    _, _, _, _, value = sources_and_projection()
    gap = value.gaps[0]
    question = value.priority_questions[0]
    assert "neutral classification" in gap.materiality.explanation
    assert "not a comparative statement" in gap.materiality.explanation
    assert "neutral M4.4 value" in question.priority.explanation
    assert "not an urgency" in question.priority.explanation


def test_manifest_has_exact_frozen_section_order_and_all_sections():
    _, _, _, _, value = sources_and_projection()
    assert value.manifest.ordered_section_ids == SECTION_KEYS
    assert tuple(item.section_id for item in value.manifest.sections) == SECTION_KEYS
    assert tuple(item.ordinal for item in value.manifest.sections) == tuple(range(len(SECTION_KEYS)))


def test_issue_and_element_order_follow_frozen_sources():
    _, matrices, _, synthesis, value = sources_and_projection()
    assert tuple(item.issue_analysis_id for item in value.issues) == tuple(
        item.issue_analysis_id for item in synthesis.issue_positions
    )
    by_issue = {item.issue_analysis_id: item for item in matrices.issue_matrix}
    for issue in value.issues:
        assert tuple(item.element_id for item in issue.elements) == tuple(
            item.element_id for item in by_issue[issue.issue_analysis_id].element_records
        )


def test_projection_preserves_all_analytical_object_counts_and_ids():
    _, _, chronology, synthesis, value = sources_and_projection()
    projected_findings = {
        item.finding_id
        for issue in value.issues
        for item in (*issue.direct_findings, *issue.higher_order_findings)
    }
    assert projected_findings == {item.finding_id for item in synthesis.findings}
    assert tuple(item.event_id for item in value.chronology) == tuple(item.event_id for item in chronology.events)
    assert tuple(item.conflict_id for item in value.conflicts) == tuple(item.conflict_id for item in synthesis.conflicts)
    assert tuple(item.gap_id for item in value.gaps) == tuple(item.gap_id for item in synthesis.gaps)
    assert tuple(item.risk_id for item in value.risks) == tuple(item.risk_id for item in synthesis.risks)
    assert tuple(item.question_id for item in value.priority_questions) == tuple(
        item.question_id for item in synthesis.priority_questions
    )
    assert value.overall_state.state.raw_value == synthesis.overall_state.value


def test_material_finding_ids_are_preserved_and_higher_order_findings_are_separate():
    _, _, _, synthesis, value = sources_and_projection(higher_order=True)
    positions = {item.issue_analysis_id: item for item in synthesis.issue_positions}
    assert any(issue.higher_order_findings for issue in value.issues)
    for issue in value.issues:
        assert issue.material_finding_ids == positions[issue.issue_analysis_id].material_finding_ids
        assert tuple(item.finding_id for item in issue.direct_findings) == issue.material_finding_ids
        assert not set(issue.material_finding_ids) & {
            item.finding_id for item in issue.higher_order_findings
        }


def _single_issue_projection(*, propositions, evidence_keys=("e1",), roles=None):
    items = tuple(
        evidence(key=key, document_name=f"{key}.pdf", page=index + 1, summary=f"Source {key}.")
        for index, key in enumerate(evidence_keys)
    )
    result = make_m5_result(
        "EK-001",
        case_id="77777777-7777-4777-8777-777777777777",
        issue_analysis_id="77777777-7777-4777-8777-777777777701",
        evidence_by_element={"EK-INFORMATION": items},
        proposition_overrides={"EK-INFORMATION": propositions},
        role_overrides=roles,
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    chronology = CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    return build_case_report_projection(foundation, matrices, chronology, synthesis)


def _prop(text, status, keys):
    return AssessedProposition(
        text=text,
        status=status,
        confidence=Confidence.MEDIUM,
        evidence_keys=keys,
        rationale=f"Rationale for {text}",
    )


def test_higher_order_explanations_preserve_all_six_narrow_m45_meanings():
    multiple = _single_issue_projection(
        propositions=(
            _prop("First.", PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED, ("e1",)),
            _prop("Second.", PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED, ("e1",)),
        )
    )
    corroborated = _single_issue_projection(
        propositions=(
            _prop("Shared.", PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED, ("e1", "e2")),
        ),
        evidence_keys=("e1", "e2"),
        roles={
            ("EK-INFORMATION", "e1"): AnalyticalRole.SUPPORTING,
            ("EK-INFORMATION", "e2"): AnalyticalRole.CORROBORATIVE,
        },
    )
    adverse = _single_issue_projection(
        propositions=(
            _prop("Adverse.", PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED, ("e1",)),
        ),
        roles={("EK-INFORMATION", "e1"): AnalyticalRole.ADVERSE},
    )
    conflicting = _single_issue_projection(
        propositions=(
            _prop("Conflicting.", PropositionAssessmentStatus.DISPUTED, ("e1",)),
        ),
        roles={("EK-INFORMATION", "e1"): AnalyticalRole.CONFLICTING},
    )
    _, _, _, _, shared = sources_and_projection(higher_order=True)
    findings = {}
    for projection in (multiple, corroborated, adverse, conflicting, shared):
        for issue in projection.issues:
            for finding in issue.higher_order_findings:
                for basis in finding.analytical_bases:
                    findings[basis] = finding.controlled_explanation
    assert "proposition breadth" in findings["multiple_supporting_propositions"]
    assert "source multiplicity" in findings["corroborated_evidence"]
    assert "does not decide" in findings["adverse_evidence"]
    assert "does not reconstruct the conflict sides" in findings["conflicting_evidence"]
    assert "not issue dependency" in findings["cross_issue_coverage"]
    assert "not a global claim" in findings["dependency_on_single_evidence_source"]


def test_identity_only_provenance_remains_identity_only():
    _, _, _, _, value = sources_and_projection()
    gap_ref = value.gaps[0].provenance[0]
    assert gap_ref.provenance_type == "evidential_gap"
    assert gap_ref.identity_only is True
    assert "not reconstructed" in gap_ref.qualification_text
    conflict_ref = value.conflicts[0].side_b[0]
    assert conflict_ref.provenance_type == "disputed_matter"
    assert conflict_ref.identity_only is True
    assert "not reconstructed" in conflict_ref.qualification_text


def test_manifest_inventory_contains_all_canonical_id_sets():
    _, _, chronology, synthesis, value = sources_and_projection()
    manifest = value.manifest
    assert manifest.ordered_issue_ids == tuple(item.issue_analysis_id for item in value.issues)
    assert manifest.ordered_event_ids == tuple(item.event_id for item in chronology.events)
    assert manifest.ordered_conflict_ids == tuple(item.conflict_id for item in synthesis.conflicts)
    assert manifest.ordered_gap_ids == tuple(item.gap_id for item in synthesis.gaps)
    assert manifest.ordered_risk_ids == tuple(item.risk_id for item in synthesis.risks)
    assert manifest.ordered_question_ids == tuple(item.question_id for item in synthesis.priority_questions)
    assert manifest.ordered_citation_ids == tuple(item.citation_id for item in value.citations)


def test_manifest_omission_or_reordering_fails_closed():
    _, _, _, _, value = sources_and_projection()
    bad_manifest = replace(
        value.manifest,
        ordered_section_ids=tuple(reversed(value.manifest.ordered_section_ids)),
    )
    with pytest.raises(ValueError, match="canonical projection manifest|section order"):
        validate_case_report_projection(replace(value, manifest=bad_manifest))


def test_payload_tampering_fails_closed():
    _, _, _, _, value = sources_and_projection()
    bad_overall = replace(value.overall_state, count_qualification="Tampered count meaning.")
    with pytest.raises(ValueError, match="projection_payload_sha256"):
        validate_case_report_projection(replace(value, overall_state=bad_overall))


def test_json_loading_regenerates_manifest_and_rejects_independent_manifest_tampering():
    _, _, _, _, value = sources_and_projection()
    data = json.loads(dumps_case_report_projection(value))
    data["manifest"]["ordered_issue_ids"] = []
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError, match="canonical projection manifest"):
        loads_case_report_projection(payload)


def test_unknown_citation_link_fails_closed():
    _, _, _, _, value = sources_and_projection()
    event = value.chronology[0]
    assertion = replace(event.assertions[0], citation_id="missing-evidence")
    changed_event = replace(event, assertions=(assertion, *event.assertions[1:]))
    with pytest.raises(ValueError):
        validate_case_report_projection(replace(value, chronology=(changed_event, *value.chronology[1:])))


def test_incoherent_frozen_source_bundle_fails_before_projection():
    foundation, matrices, chronology, synthesis, _ = sources_and_projection()
    bad_chronology = replace(
        chronology,
        source_analysis_ids=("99999999-9999-4999-8999-999999999999",),
    )
    with pytest.raises(ValueError):
        build_case_report_projection(foundation, matrices, bad_chronology, synthesis)


def test_report_statement_identity_is_stable_for_same_frozen_statement():
    _, _, _, _, first = sources_and_projection()
    _, _, _, _, second = sources_and_projection()
    first_statement = next(
        statement
        for issue in first.issues
        for element in issue.elements
        for statement in element.supported_matters
    )
    second_statement = next(
        statement
        for issue in second.issues
        for element in issue.elements
        for statement in element.supported_matters
    )
    assert first_statement.report_statement_id == second_statement.report_statement_id


def test_case_reporting_package_has_no_prohibited_runtime_imports():
    prohibited = {
        "openai",
        "chromadb",
        "streamlit",
        "retriever",
        "query_expander",
        "PyPDF2",
        "pypdf",
        "reportlab",
    }
    package = Path(__file__).parents[1] / "src" / "case_reporting"
    imported: set[str] = set()
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert not prohibited & imported


def test_m51_contains_no_renderer_entry_points():
    package = Path(__file__).parents[1] / "src" / "case_reporting"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for forbidden in ("render_markdown", "render_html", "render_pdf", "render_streamlit"):
        assert forbidden not in source


def test_projection_has_no_wall_clock_or_generation_timestamp_field():
    _, _, _, _, value = sources_and_projection()
    data = json.loads(dumps_case_report_projection(value))
    assert "generated_at" not in data
    assert "created_at" not in data


def test_validator_accepts_untampered_projection():
    _, _, _, _, value = sources_and_projection(higher_order=True)
    validate_case_report_projection(value)
