"""Deterministic chronology event identity and conservative aggregation."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid5

from case_analysis.m2.matrices import CaseEvidenceRecord

from .models import (
    CASE_CHRONOLOGY_BUILDER_VERSION,
    CASE_CHRONOLOGY_SCHEMA_VERSION,
    CaseEvent,
    EventAssertion,
    EventStatus,
    PartialDate,
    TemporalExtent,
    TemporalKind,
    TimingStatus,
)

_EVENT_NAMESPACE = UUID("40cdab13-fca0-4a73-ab48-cf196f2f4a91")
_STATUS_RANK = {
    EventStatus.ESTABLISHED: 0,
    EventStatus.SUPPORTED: 1,
    EventStatus.DISPUTED: 2,
    EventStatus.UNRESOLVED: 3,
}
_GENERIC_CORES = {
    "meeting",
    "letter",
    "email",
    "decision",
    "event",
    "act",
    "omission",
    "communication",
    "request",
    "proposal",
}


def _specific_core(value: str) -> bool:
    tokens = value.split()
    return len(tokens) >= 4 and value not in _GENERIC_CORES


def _can_join(group: list[EventAssertion], candidate: EventAssertion) -> bool:
    first = group[0]
    if candidate.event_type is not first.event_type:
        return False
    if candidate.normalized_event_core != first.normalized_event_core:
        return False

    # The same frozen chunk may contain several separate events. Cross-issue
    # uses of the same extracted occurrence share the extraction ordinal;
    # different ordinals remain separate.
    same_evidence = [item for item in group if item.evidence_key == candidate.evidence_key]
    if same_evidence:
        return all(item.extraction_ordinal == candidate.extraction_ordinal for item in same_evidence)

    # Calibration v1.1: different evidence records never collapse solely
    # because their normalized descriptions match. Automatic cross-evidence
    # grouping requires sufficiently specific exact content *and* compatible
    # explicit timing. Unknown or incompatible timing deliberately remains
    # separate to avoid silently reconciling competing source assertions.
    if not _specific_core(candidate.normalized_event_core):
        return False
    if candidate.temporal_extent is None:
        return False
    for item in group:
        if item.temporal_extent is None:
            return False
        if not _extents_compatible(item.temporal_extent, candidate.temporal_extent):
            return False
    return True


def group_assertions(
    case_id: str,
    assertions: Iterable[EventAssertion],
    evidence_records: Iterable[CaseEvidenceRecord],
) -> tuple[CaseEvent, ...]:
    """Group assertions conservatively and build deterministic CaseEvents."""

    citations = {item.evidence_key: item.citation for item in evidence_records}
    groups: list[list[EventAssertion]] = []
    for assertion in sorted(tuple(assertions), key=lambda item: item.source_coordinate):
        for group in groups:
            if _can_join(group, assertion):
                group.append(assertion)
                break
        else:
            groups.append([assertion])

    events = tuple(_event_from_group(case_id, tuple(group), citations) for group in groups)
    return tuple(sorted(events, key=lambda item: item.sort_key))


def event_id_for(
    case_id: str,
    event_type: str,
    normalized_event_core: str,
    assertion_ids: tuple[str, ...],
) -> str:
    """Return deterministic event identity for one exact assertion group."""

    material = "|".join(
        (
            case_id,
            event_type,
            normalized_event_core,
            ",".join(sorted(assertion_ids)),
            CASE_CHRONOLOGY_SCHEMA_VERSION,
            CASE_CHRONOLOGY_BUILDER_VERSION,
        )
    )
    return str(uuid5(_EVENT_NAMESPACE, material))


def _event_from_group(
    case_id: str,
    assertions: tuple[EventAssertion, ...],
    citations: dict[str, str],
) -> CaseEvent:
    ordered = tuple(sorted(assertions, key=lambda item: item.source_coordinate))
    first = ordered[0]
    event_status = aggregate_event_status(ordered)
    temporal, timing_status = aggregate_timing(ordered)
    if event_status is EventStatus.DISPUTED:
        description = f"Disputed event concerning {first.normalized_event_core}."
    else:
        preferred = min(
            ordered,
            key=lambda item: (
                _STATUS_RANK[item.event_status],
                len(item.description),
                item.assertion_id,
            ),
        )
        description = preferred.description

    evidence_keys = tuple(sorted({item.evidence_key for item in ordered}))
    missing = [key for key in evidence_keys if key not in citations]
    if missing:
        raise ValueError(f"Chronology assertions reference unknown M2 evidence keys: {missing!r}.")

    assertion_ids = tuple(item.assertion_id for item in ordered)
    return CaseEvent(
        event_id=event_id_for(
            case_id,
            first.event_type.value,
            first.normalized_event_core,
            assertion_ids,
        ),
        description=description,
        normalized_event_core=first.normalized_event_core,
        event_type=first.event_type,
        event_status=event_status,
        timing_status=timing_status,
        canonical_temporal_extent=temporal,
        assertions=ordered,
        evidence_keys=evidence_keys,
        citations=tuple(dict.fromkeys(citations[key] for key in evidence_keys)),
        related_issue_analysis_ids=tuple(sorted({item.issue_analysis_id for item in ordered})),
        related_issue_definition_ids=tuple(sorted({item.issue_definition_id for item in ordered})),
        related_element_ids=tuple(sorted({item.element_id for item in ordered})),
        participants=tuple(sorted({party for item in ordered for party in item.participants})),
    )


def aggregate_event_status(assertions: tuple[EventAssertion, ...]) -> EventStatus:
    """Aggregate without averaging or voting across source assertions."""

    statuses = {item.event_status for item in assertions}
    if EventStatus.DISPUTED in statuses:
        return EventStatus.DISPUTED
    if EventStatus.ESTABLISHED in statuses:
        return EventStatus.ESTABLISHED
    if EventStatus.SUPPORTED in statuses:
        return EventStatus.SUPPORTED
    return EventStatus.UNRESOLVED


def _precision_score(value: PartialDate) -> int:
    return {"year": 1, "month": 2, "exact": 3}[value.precision.value]


def _date_bounds(value: PartialDate) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if value.precision.value == "exact":
        point = (value.year, value.month or 1, value.day or 1)
        return point, point
    if value.precision.value == "month":
        from calendar import monthrange

        return (
            (value.year, value.month or 1, 1),
            (value.year, value.month or 1, monthrange(value.year, value.month or 1)[1]),
        )
    return (value.year, 1, 1), (value.year, 12, 31)


def _extent_bounds(value: TemporalExtent) -> tuple[tuple[int, int, int], tuple[int, int, int] | None]:
    start_min, start_max = _date_bounds(value.start)
    if value.kind is TemporalKind.POINT:
        return start_min, start_max
    if value.end is None:
        return start_min, None
    _, end_max = _date_bounds(value.end)
    return start_min, end_max


def _extents_compatible(left: TemporalExtent, right: TemporalExtent) -> bool:
    left_start, left_end = _extent_bounds(left)
    right_start, right_end = _extent_bounds(right)
    if left_end is None or right_end is None:
        return left.kind is right.kind and (
            left.start.contains(right.start) or right.start.contains(left.start)
        )
    return left_start <= right_end and right_start <= left_end


def _extent_specificity(value: TemporalExtent) -> tuple[int, int, int]:
    return (
        1 if value.kind is TemporalKind.POINT else 0,
        _precision_score(value.start),
        _precision_score(value.end) if value.end is not None else 0,
    )


def aggregate_timing(
    assertions: tuple[EventAssertion, ...],
) -> tuple[TemporalExtent | None, TimingStatus]:
    """Preserve unknown/conflicting timing and choose precision only if compatible."""

    timed = tuple(item for item in assertions if item.temporal_extent is not None)
    if not timed:
        return None, TimingStatus.UNKNOWN
    if any(item.timing_status is TimingStatus.DISPUTED for item in timed):
        return None, TimingStatus.DISPUTED

    extents = tuple(item.temporal_extent for item in timed if item.temporal_extent is not None)
    first = extents[0]
    if any(not _extents_compatible(first, candidate) for candidate in extents[1:]):
        return None, TimingStatus.DISPUTED

    canonical = max(extents, key=lambda item: (_extent_specificity(item), item.original_text))
    status = (
        TimingStatus.ESTABLISHED
        if all(item.timing_status is TimingStatus.ESTABLISHED for item in timed)
        else TimingStatus.SUPPORTED
    )
    return canonical, status


__all__ = [
    "aggregate_event_status",
    "aggregate_timing",
    "event_id_for",
    "group_assertions",
]
