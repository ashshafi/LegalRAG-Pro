"""Deterministic JSON serialization for Sprint 2.4 Milestone 3 chronology."""

from __future__ import annotations

import json
from typing import Any

from legal_analysis.enums import Confidence

from .models import (
    CaseChronology,
    CaseEvent,
    DatePrecision,
    EventAssertion,
    EventStatus,
    EventType,
    ExtractionBasis,
    PartialDate,
    TemporalExtent,
    TemporalKind,
    TimingStatus,
)


def _partial_to_dict(value: PartialDate) -> dict[str, Any]:
    return {
        "year": value.year,
        "month": value.month,
        "day": value.day,
        "precision": value.precision.value,
    }


def _partial_from_dict(data: dict[str, Any]) -> PartialDate:
    return PartialDate(
        year=int(data["year"]),
        month=int(data["month"]) if data.get("month") is not None else None,
        day=int(data["day"]) if data.get("day") is not None else None,
        precision=DatePrecision(data["precision"]),
    )


def _extent_to_dict(value: TemporalExtent | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "kind": value.kind.value,
        "start": _partial_to_dict(value.start),
        "end": _partial_to_dict(value.end) if value.end is not None else None,
        "original_text": value.original_text,
    }


def _extent_from_dict(data: dict[str, Any] | None) -> TemporalExtent | None:
    if data is None:
        return None
    return TemporalExtent(
        kind=TemporalKind(data["kind"]),
        start=_partial_from_dict(data["start"]),
        end=_partial_from_dict(data["end"]) if data.get("end") is not None else None,
        original_text=str(data["original_text"]),
    )


def _assertion_to_dict(value: EventAssertion) -> dict[str, Any]:
    return {
        "assertion_id": value.assertion_id,
        "issue_analysis_id": value.issue_analysis_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "element_id": value.element_id,
        "source_proposition_index": value.source_proposition_index,
        "evidence_key": value.evidence_key,
        "extraction_ordinal": value.extraction_ordinal,
        "description": value.description,
        "normalized_event_core": value.normalized_event_core,
        "event_type": value.event_type.value,
        "event_status": value.event_status.value,
        "confidence": value.confidence.value,
        "temporal_extent": _extent_to_dict(value.temporal_extent),
        "timing_status": value.timing_status.value,
        "participants": list(value.participants),
        "extraction_basis": value.extraction_basis.value,
        "profile_version": value.profile_version,
    }


def _assertion_from_dict(data: dict[str, Any]) -> EventAssertion:
    return EventAssertion(
        assertion_id=str(data["assertion_id"]),
        issue_analysis_id=str(data["issue_analysis_id"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        element_id=str(data["element_id"]),
        source_proposition_index=int(data["source_proposition_index"]),
        evidence_key=str(data["evidence_key"]),
        extraction_ordinal=int(data["extraction_ordinal"]),
        description=str(data["description"]),
        normalized_event_core=str(data["normalized_event_core"]),
        event_type=EventType(data["event_type"]),
        event_status=EventStatus(data["event_status"]),
        confidence=Confidence(data["confidence"]),
        temporal_extent=_extent_from_dict(data.get("temporal_extent")),
        timing_status=TimingStatus(data["timing_status"]),
        participants=tuple(data.get("participants", ())),
        extraction_basis=ExtractionBasis(data["extraction_basis"]),
        profile_version=str(data["profile_version"]),
    )


def _event_to_dict(value: CaseEvent) -> dict[str, Any]:
    return {
        "event_id": value.event_id,
        "description": value.description,
        "normalized_event_core": value.normalized_event_core,
        "event_type": value.event_type.value,
        "event_status": value.event_status.value,
        "timing_status": value.timing_status.value,
        "canonical_temporal_extent": _extent_to_dict(value.canonical_temporal_extent),
        "assertions": [_assertion_to_dict(item) for item in value.assertions],
        "evidence_keys": list(value.evidence_keys),
        "citations": list(value.citations),
        "related_issue_analysis_ids": list(value.related_issue_analysis_ids),
        "related_issue_definition_ids": list(value.related_issue_definition_ids),
        "related_element_ids": list(value.related_element_ids),
        "participants": list(value.participants),
        "chronology_builder_version": value.chronology_builder_version,
    }


def _event_from_dict(data: dict[str, Any]) -> CaseEvent:
    return CaseEvent(
        event_id=str(data["event_id"]),
        description=str(data["description"]),
        normalized_event_core=str(data["normalized_event_core"]),
        event_type=EventType(data["event_type"]),
        event_status=EventStatus(data["event_status"]),
        timing_status=TimingStatus(data["timing_status"]),
        canonical_temporal_extent=_extent_from_dict(data.get("canonical_temporal_extent")),
        assertions=tuple(_assertion_from_dict(item) for item in data["assertions"]),
        evidence_keys=tuple(data["evidence_keys"]),
        citations=tuple(data["citations"]),
        related_issue_analysis_ids=tuple(data["related_issue_analysis_ids"]),
        related_issue_definition_ids=tuple(data["related_issue_definition_ids"]),
        related_element_ids=tuple(data["related_element_ids"]),
        participants=tuple(data.get("participants", ())),
        chronology_builder_version=str(data["chronology_builder_version"]),
    )


def chronology_to_dict(value: CaseChronology) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "chronology_builder_version": value.chronology_builder_version,
        "case_id": value.case_id,
        "synthesis_id": value.synthesis_id,
        "source_analysis_ids": list(value.source_analysis_ids),
        "events": [_event_to_dict(item) for item in value.events],
    }


def chronology_from_dict(data: dict[str, Any]) -> CaseChronology:
    return CaseChronology(
        schema_version=str(data["schema_version"]),
        chronology_builder_version=str(data["chronology_builder_version"]),
        case_id=str(data["case_id"]),
        synthesis_id=str(data["synthesis_id"]),
        source_analysis_ids=tuple(data["source_analysis_ids"]),
        events=tuple(_event_from_dict(item) for item in data["events"]),
    )


def dumps_case_chronology(value: CaseChronology) -> str:
    return json.dumps(
        chronology_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_case_chronology(payload: str) -> CaseChronology:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("CaseChronology JSON root must be an object.")
    return chronology_from_dict(data)


__all__ = [
    "chronology_from_dict",
    "chronology_to_dict",
    "dumps_case_chronology",
    "loads_case_chronology",
]
