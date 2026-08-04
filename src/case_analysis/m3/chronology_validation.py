"""Fail-closed validation for Sprint 2.4 Milestone 3 chronology."""

from __future__ import annotations

from collections.abc import Iterable

from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis.models import CaseAnalysisFoundation
from case_analysis.validation import validate_foundation
from case_analysis.m2.matrices import CaseMatrices, EvidenceUse
from case_analysis.m2.matrix_validation import resolve_foundation_results, validate_case_matrices

from .event_extraction import assertion_id_for, profile_for
from .event_identity import aggregate_event_status, aggregate_timing, event_id_for
from .models import (
    CASE_CHRONOLOGY_BUILDER_VERSION,
    CASE_CHRONOLOGY_SCHEMA_VERSION,
    CHRONOLOGY_PROFILE_VERSION,
    CaseChronology,
)


def resolve_chronology_inputs(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[StructuredLegalAnalysisResult, ...]:
    """Resolve the exact frozen source set required for chronology building."""

    validate_foundation(foundation)
    validate_case_matrices(matrices, foundation=foundation)
    resolved = resolve_foundation_results(foundation, tuple(results))
    if matrices.case_id != foundation.case_id:
        raise ValueError("CaseMatrices.case_id does not match the M1 foundation.")
    if matrices.synthesis_id != foundation.synthesis_id:
        raise ValueError("CaseMatrices.synthesis_id does not match the M1 foundation.")
    if matrices.source_analysis_ids != foundation.source_issue_analysis_ids:
        raise ValueError("CaseMatrices source set does not match the M1 foundation.")
    return resolved


def _use_lookup(matrices: CaseMatrices) -> dict[tuple[str, str, str], EvidenceUse]:
    values: dict[tuple[str, str, str], EvidenceUse] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.identity in values:
                raise ValueError(f"Duplicate M2 EvidenceUse identity {use.identity!r}.")
            values[use.identity] = use
    return values


def validate_case_chronology(
    value: CaseChronology,
    *,
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
) -> None:
    """Validate chronology identity, traceability and frozen source alignment."""

    if not isinstance(value, CaseChronology):
        raise ValueError("value must be a CaseChronology instance.")
    resolved = resolve_chronology_inputs(foundation, matrices, tuple(results))
    if value.schema_version != CASE_CHRONOLOGY_SCHEMA_VERSION:
        raise ValueError("Unsupported CaseChronology schema version.")
    if value.chronology_builder_version != CASE_CHRONOLOGY_BUILDER_VERSION:
        raise ValueError("Unsupported chronology builder version.")
    if value.case_id != foundation.case_id or value.synthesis_id != foundation.synthesis_id:
        raise ValueError("CaseChronology identity does not match the frozen foundation.")
    if value.source_analysis_ids != foundation.source_issue_analysis_ids:
        raise ValueError("CaseChronology source set does not match the frozen foundation.")

    evidence_by_key = {item.evidence_key: item for item in matrices.evidence_matrix}
    uses = _use_lookup(matrices)
    result_ids = {item.issue_analysis_id for item in resolved}
    seen_assertions: set[str] = set()

    for event in value.events:
        if event.event_id != event_id_for(
            value.case_id,
            event.event_type.value,
            event.normalized_event_core,
            tuple(item.assertion_id for item in event.assertions),
        ):
            raise ValueError(f"CaseEvent {event.event_id!r} has an invalid deterministic identity.")
        expected_status = aggregate_event_status(event.assertions)
        expected_temporal, expected_timing = aggregate_timing(event.assertions)
        if event.event_status is not expected_status:
            raise ValueError("CaseEvent event status does not match its source assertions.")
        if event.timing_status is not expected_timing or event.canonical_temporal_extent != expected_temporal:
            raise ValueError("CaseEvent timing does not match its source assertions.")

        expected_citations = tuple(
            dict.fromkeys(evidence_by_key[key].citation for key in event.evidence_keys)
        )
        if event.citations != expected_citations:
            raise ValueError("CaseEvent citations do not match canonical M2 evidence identity.")

        for assertion in event.assertions:
            if assertion.assertion_id in seen_assertions:
                raise ValueError("One EventAssertion must not appear in multiple CaseEvents.")
            seen_assertions.add(assertion.assertion_id)
            if assertion.issue_analysis_id not in result_ids:
                raise ValueError("EventAssertion references an analysis outside the frozen source set.")
            identity = (
                assertion.issue_analysis_id,
                assertion.element_id,
                assertion.evidence_key,
            )
            try:
                use = uses[identity]
            except KeyError as exc:
                raise ValueError(f"EventAssertion source relationship {identity!r} does not resolve in M2.") from exc
            try:
                link = next(
                    item
                    for item in use.proposition_links
                    if item.source_proposition_index == assertion.source_proposition_index
                )
            except StopIteration as exc:
                raise ValueError("EventAssertion source proposition coordinate does not resolve in M2.") from exc
            expected_id = assertion_id_for(use, link, assertion.extraction_ordinal)
            if assertion.assertion_id != expected_id:
                raise ValueError("EventAssertion deterministic identity is invalid.")
            profile = profile_for(
                assertion.issue_definition_id,
                assertion.issue_definition_version,
                assertion.element_id,
            )
            if assertion.profile_version != CHRONOLOGY_PROFILE_VERSION:
                raise ValueError("EventAssertion profile version is not supported.")
            if assertion.profile_version != profile.profile_version:
                raise ValueError("EventAssertion does not match its exact extraction profile version.")
            if assertion.evidence_key not in evidence_by_key:
                raise ValueError("EventAssertion evidence key does not resolve to canonical M2 evidence.")


__all__ = ["resolve_chronology_inputs", "validate_case_chronology"]
