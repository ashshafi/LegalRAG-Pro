"""Durable Sprint 2.4 Milestone 3 chronology models.

Chronology is a downstream, evidence-traceable representation of event
assertions already present in frozen Sprint 2.3 analyses.  These models keep
occurrence status separate from timing status and preserve partial-date
precision without inventing missing calendar components.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from legal_analysis.enums import Confidence

CASE_CHRONOLOGY_SCHEMA_VERSION: Final[str] = "case-chronology-schema/1.0"
CASE_CHRONOLOGY_BUILDER_VERSION: Final[str] = "case-chronology-builder/1.1"
CHRONOLOGY_PROFILE_VERSION: Final[str] = "chronology-profile/1.1"


class DatePrecision(StrEnum):
    """Precision actually supplied by the frozen source text."""

    EXACT = "exact"
    MONTH = "month"
    YEAR = "year"


class TemporalKind(StrEnum):
    """Whether timing identifies a point or an evidenced period."""

    POINT = "point"
    PERIOD = "period"


class EventStatus(StrEnum):
    """Evidential status of the event occurrence/content."""

    ESTABLISHED = "established"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    UNRESOLVED = "unresolved"


class TimingStatus(StrEnum):
    """Independent status of the timing attributed to an event."""

    ESTABLISHED = "established"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    """Controlled factual event categories; never legal-liability labels."""

    COMMUNICATION = "communication"
    MEDICAL = "medical"
    EMPLOYMENT = "employment"
    RETURN_TO_WORK = "return_to_work"
    ADJUSTMENT_PROPOSAL = "adjustment_proposal"
    ABSENCE = "absence"
    CAPABILITY = "capability"
    BENEFIT = "benefit"
    TRIBUNAL_PROCEDURAL = "tribunal_procedural"
    OTHER = "other"


class ExtractionBasis(StrEnum):
    """How a source proposition became one chronology assertion."""

    PROPOSITION = "proposition"
    PROPOSITION_WITH_EVIDENCE_ENRICHMENT = "proposition_with_evidence_enrichment"


def _required(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _unique(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    cleaned = tuple(str(item).strip() for item in values if str(item).strip())
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must contain unique values.")
    return cleaned


@dataclass(frozen=True, slots=True)
class PartialDate:
    """Calendar date preserving only the precision actually evidenced."""

    year: int
    month: int | None = None
    day: int | None = None
    precision: DatePrecision = DatePrecision.YEAR

    def __post_init__(self) -> None:
        if not 1 <= self.year <= 9999:
            raise ValueError("PartialDate.year must be between 1 and 9999.")
        if not isinstance(self.precision, DatePrecision):
            raise ValueError("PartialDate.precision must be a DatePrecision.")
        if self.precision is DatePrecision.YEAR:
            if self.month is not None or self.day is not None:
                raise ValueError("YEAR precision must not supply month or day.")
        elif self.precision is DatePrecision.MONTH:
            if self.month is None or not 1 <= self.month <= 12:
                raise ValueError("MONTH precision requires a valid month.")
            if self.day is not None:
                raise ValueError("MONTH precision must not supply a day.")
        else:
            if self.month is None or self.day is None:
                raise ValueError("EXACT precision requires month and day.")
            # Local import keeps the model free of parser dependencies.
            from datetime import date

            try:
                date(self.year, self.month, self.day)
            except ValueError as exc:
                raise ValueError("EXACT precision must be a valid calendar date.") from exc

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        """Return a non-rendered deterministic chronological ordering key."""

        precision_rank = {
            DatePrecision.YEAR: 0,
            DatePrecision.MONTH: 1,
            DatePrecision.EXACT: 2,
        }[self.precision]
        return (self.year, self.month or 0, self.day or 0, precision_rank)

    def contains(self, other: "PartialDate") -> bool:
        """Return whether this less/equal precise value contains ``other``."""

        if self.year != other.year:
            return False
        if self.precision is DatePrecision.YEAR:
            return True
        if self.month != other.month:
            return False
        if self.precision is DatePrecision.MONTH:
            return True
        return self.day == other.day

    @property
    def display_text(self) -> str:
        """Render only evidenced components; never fabricate month/day."""

        if self.precision is DatePrecision.YEAR:
            return str(self.year)
        month_name = (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )[self.month - 1]
        if self.precision is DatePrecision.MONTH:
            return f"{month_name} {self.year}"
        return f"{self.day} {month_name} {self.year}"


@dataclass(frozen=True, slots=True)
class TemporalExtent:
    """An explicit source-level point or period with boundary precision."""

    kind: TemporalKind
    start: PartialDate
    original_text: str
    end: PartialDate | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TemporalKind):
            raise ValueError("TemporalExtent.kind must be a TemporalKind.")
        if not isinstance(self.start, PartialDate):
            raise ValueError("TemporalExtent.start must be a PartialDate.")
        object.__setattr__(self, "original_text", _required(self.original_text, field_name="original_text"))
        if self.kind is TemporalKind.POINT and self.end is not None:
            raise ValueError("POINT temporal extents must not supply an end boundary.")
        if self.kind is TemporalKind.PERIOD and self.end is not None:
            if not isinstance(self.end, PartialDate):
                raise ValueError("TemporalExtent.end must be a PartialDate when supplied.")
            if self.end.sort_key[:3] < self.start.sort_key[:3]:
                raise ValueError("TemporalExtent.end must not precede start.")

    @property
    def sort_key(self) -> tuple[int, int, int, int, int]:
        kind_rank = 0 if self.kind is TemporalKind.POINT else 1
        return (*self.start.sort_key, kind_rank)

    @property
    def display_text(self) -> str:
        """Prefer exact source wording so approximate dates remain approximate."""

        return self.original_text


@dataclass(frozen=True, slots=True)
class EventAssertion:
    """One proposition-linked source assertion concerning a candidate event."""

    assertion_id: str
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    source_proposition_index: int
    evidence_key: str
    extraction_ordinal: int
    description: str
    normalized_event_core: str
    event_type: EventType
    event_status: EventStatus
    confidence: Confidence
    timing_status: TimingStatus
    extraction_basis: ExtractionBasis
    profile_version: str
    temporal_extent: TemporalExtent | None = None
    participants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "assertion_id", _uuid(self.assertion_id, field_name="assertion_id"))
        object.__setattr__(self, "issue_analysis_id", _uuid(self.issue_analysis_id, field_name="issue_analysis_id"))
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "evidence_key",
            "description",
            "normalized_event_core",
            "profile_version",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        if self.source_proposition_index < 0:
            raise ValueError("source_proposition_index must be zero or greater.")
        if self.extraction_ordinal < 0:
            raise ValueError("extraction_ordinal must be zero or greater.")
        if not isinstance(self.event_type, EventType):
            raise ValueError("event_type must be an EventType.")
        if not isinstance(self.event_status, EventStatus):
            raise ValueError("event_status must be an EventStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")
        if not isinstance(self.timing_status, TimingStatus):
            raise ValueError("timing_status must be a TimingStatus.")
        if not isinstance(self.extraction_basis, ExtractionBasis):
            raise ValueError("extraction_basis must be an ExtractionBasis.")
        if self.temporal_extent is None and self.timing_status is not TimingStatus.UNKNOWN:
            raise ValueError("Assertions without temporal information must have UNKNOWN timing.")
        if self.temporal_extent is not None and self.timing_status is TimingStatus.UNKNOWN:
            raise ValueError("Assertions with temporal information must not have UNKNOWN timing.")
        object.__setattr__(self, "participants", _unique(tuple(self.participants), field_name="participants"))

    @property
    def source_coordinate(self) -> tuple[str, str, int, str, int]:
        return (
            self.issue_analysis_id,
            self.element_id,
            self.source_proposition_index,
            self.evidence_key,
            self.extraction_ordinal,
        )


@dataclass(frozen=True, slots=True)
class CaseEvent:
    """Canonical event grouping compatible proposition-linked assertions."""

    event_id: str
    description: str
    normalized_event_core: str
    event_type: EventType
    event_status: EventStatus
    timing_status: TimingStatus
    assertions: tuple[EventAssertion, ...]
    evidence_keys: tuple[str, ...]
    citations: tuple[str, ...]
    related_issue_analysis_ids: tuple[str, ...]
    related_issue_definition_ids: tuple[str, ...]
    related_element_ids: tuple[str, ...]
    participants: tuple[str, ...] = ()
    canonical_temporal_extent: TemporalExtent | None = None
    chronology_builder_version: str = CASE_CHRONOLOGY_BUILDER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid(self.event_id, field_name="event_id"))
        for field_name in ("description", "normalized_event_core", "chronology_builder_version"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        if not isinstance(self.event_type, EventType):
            raise ValueError("event_type must be an EventType.")
        if not isinstance(self.event_status, EventStatus):
            raise ValueError("event_status must be an EventStatus.")
        if not isinstance(self.timing_status, TimingStatus):
            raise ValueError("timing_status must be a TimingStatus.")
        assertions = tuple(self.assertions)
        if not assertions:
            raise ValueError("CaseEvent.assertions must not be empty.")
        assertion_ids = tuple(item.assertion_id for item in assertions)
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("CaseEvent assertions must be unique.")
        if any(item.event_type is not self.event_type for item in assertions):
            raise ValueError("All assertions must share CaseEvent.event_type.")
        if any(item.normalized_event_core != self.normalized_event_core for item in assertions):
            raise ValueError("All assertions must share CaseEvent.normalized_event_core.")
        object.__setattr__(self, "assertions", assertions)
        for field_name in (
            "evidence_keys",
            "citations",
            "related_issue_analysis_ids",
            "related_issue_definition_ids",
            "related_element_ids",
            "participants",
        ):
            object.__setattr__(self, field_name, _unique(tuple(getattr(self, field_name)), field_name=field_name))
        if set(self.evidence_keys) != {item.evidence_key for item in assertions}:
            raise ValueError("CaseEvent.evidence_keys must exactly cover its assertions.")
        if set(self.related_issue_analysis_ids) != {item.issue_analysis_id for item in assertions}:
            raise ValueError("CaseEvent issue-analysis links must exactly cover its assertions.")
        if set(self.related_issue_definition_ids) != {item.issue_definition_id for item in assertions}:
            raise ValueError("CaseEvent issue-definition links must exactly cover its assertions.")
        if set(self.related_element_ids) != {item.element_id for item in assertions}:
            raise ValueError("CaseEvent element links must exactly cover its assertions.")
        if self.canonical_temporal_extent is None and self.timing_status not in {
            TimingStatus.UNKNOWN,
            TimingStatus.DISPUTED,
        }:
            raise ValueError("Events without canonical timing must be UNKNOWN or DISPUTED.")
        if self.canonical_temporal_extent is not None and self.timing_status is TimingStatus.UNKNOWN:
            raise ValueError("Events with canonical timing must not have UNKNOWN timing.")

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, str, str]:
        if self.canonical_temporal_extent is None:
            temporal = (9999, 12, 31, 9, 9)
        else:
            temporal = self.canonical_temporal_extent.sort_key
        return (*temporal, self.event_type.value, self.event_id)


@dataclass(frozen=True, slots=True)
class CaseChronology:
    """Deterministic chronology for one frozen M1/M2 analytical source set."""

    case_id: str
    synthesis_id: str
    source_analysis_ids: tuple[str, ...]
    events: tuple[CaseEvent, ...]
    schema_version: str = CASE_CHRONOLOGY_SCHEMA_VERSION
    chronology_builder_version: str = CASE_CHRONOLOGY_BUILDER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _uuid(self.case_id, field_name="case_id"))
        object.__setattr__(self, "synthesis_id", _uuid(self.synthesis_id, field_name="synthesis_id"))
        for field_name in ("schema_version", "chronology_builder_version"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name=field_name))
        object.__setattr__(
            self,
            "source_analysis_ids",
            _unique(tuple(self.source_analysis_ids), field_name="source_analysis_ids"),
        )
        events = tuple(self.events)
        ids = tuple(item.event_id for item in events)
        if len(ids) != len(set(ids)):
            raise ValueError("CaseChronology.events must have unique event IDs.")
        if tuple(item.sort_key for item in events) != tuple(sorted(item.sort_key for item in events)):
            raise ValueError("CaseChronology.events must be in deterministic chronological order.")
        object.__setattr__(self, "events", events)


__all__ = [
    "CASE_CHRONOLOGY_BUILDER_VERSION",
    "CASE_CHRONOLOGY_SCHEMA_VERSION",
    "CHRONOLOGY_PROFILE_VERSION",
    "CaseChronology",
    "CaseEvent",
    "DatePrecision",
    "EventAssertion",
    "EventStatus",
    "EventType",
    "ExtractionBasis",
    "PartialDate",
    "TemporalExtent",
    "TemporalKind",
    "TimingStatus",
]
