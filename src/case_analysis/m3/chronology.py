"""Top-level Sprint 2.4 Milestone 3 chronology construction."""

from __future__ import annotations

from collections.abc import Iterable

from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis.models import CaseAnalysisFoundation
from case_analysis.m2.matrices import CaseMatrices

from .chronology_validation import resolve_chronology_inputs, validate_case_chronology
from .event_extraction import extract_event_assertions
from .event_identity import group_assertions
from .models import CaseChronology


def build_case_chronology(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
) -> CaseChronology:
    """Build a deterministic proposition-led chronology from frozen inputs."""

    supplied = tuple(results)
    resolved = resolve_chronology_inputs(foundation, matrices, supplied)
    assertions = extract_event_assertions(matrices, resolved)
    events = group_assertions(foundation.case_id, assertions, matrices.evidence_matrix)
    value = CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=events,
    )
    validate_case_chronology(
        value,
        foundation=foundation,
        matrices=matrices,
        results=resolved,
    )
    return value


def format_chronology_diagnostics(value: CaseChronology) -> str:
    """Return deterministic evidence-traceable chronology diagnostics."""

    lines = [
        f"Case: {value.case_id}",
        f"Synthesis: {value.synthesis_id}",
        f"Schema: {value.schema_version}",
        f"Builder: {value.chronology_builder_version}",
        f"Events: {len(value.events)}",
        "",
    ]
    for event in value.events:
        timing = (
            event.canonical_temporal_extent.display_text
            if event.canonical_temporal_extent is not None
            else "Timing disputed" if event.timing_status.value == "disputed" else "Date unknown"
        )
        lines.extend(
            (
                f"{timing} — {event.description}",
                f"  Type: {event.event_type.value}",
                f"  Event status: {event.event_status.value}",
                f"  Timing status: {event.timing_status.value}",
                f"  Evidence: {', '.join(event.evidence_keys)}",
                f"  Issues: {', '.join(event.related_issue_definition_ids)}",
                f"  Elements: {', '.join(event.related_element_ids)}",
                f"  Assertions: {len(event.assertions)}",
                "",
            )
        )
    return "\n".join(lines).rstrip()


__all__ = ["build_case_chronology", "format_chronology_diagnostics"]
