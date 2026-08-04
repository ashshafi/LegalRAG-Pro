"""Immutable reporting models for M5.1 deterministic report projection.

These models are reporting artifacts only. They copy, resolve and qualify frozen
M1-M4.5 analytical state without changing or extending that analytical state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

REPORT_PROJECTION_SCHEMA_VERSION: Final[str] = "case-report-projection-schema/1.0"
REPORT_PROJECTOR_VERSION: Final[str] = "case-report-projector/1.0"
REPORT_MANIFEST_SCHEMA_VERSION: Final[str] = "case-report-manifest-schema/1.0"
REPORT_MANIFEST_BUILDER_VERSION: Final[str] = "case-report-manifest-builder/1.0"

SECTION_KEYS: Final[tuple[str, ...]] = (
    "report_header",
    "analytical_lineage",
    "overall_state",
    "issues",
    "chronology",
    "cross_issue_findings",
    "conflicts",
    "evidence_gaps",
    "risk_areas",
    "priority_questions",
    "evidence_appendix",
    "glossary",
)
MANDATORY_SECTION_KEYS: Final[frozenset[str]] = frozenset(
    {"report_header", "analytical_lineage", "overall_state", "issues", "glossary"}
)


def _required(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _sha(value: str | None, *, field_name: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    cleaned = _required(str(value), field_name=field_name)
    if len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return cleaned


def _unique(values: tuple[str, ...], *, field_name: str, sort: bool = False) -> tuple[str, ...]:
    cleaned = tuple(_required(item, field_name=field_name) for item in values)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must contain unique values.")
    return tuple(sorted(cleaned)) if sort else cleaned


@dataclass(frozen=True, slots=True)
class CaseReportMetadata:
    """Optional exact non-analytical case-display metadata."""

    case_name: str | None = None
    case_number: str | None = None
    claimant: str | None = None
    respondent: str | None = None
    case_status: str | None = None
    court_or_tribunal: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "case_name",
            "case_number",
            "claimant",
            "respondent",
            "case_status",
            "court_or_tribunal",
        ):
            object.__setattr__(self, name, _optional(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class StatusView:
    """Raw authoritative enum value plus controlled reporting explanation."""

    raw_value: str
    label: str
    explanation: str
    qualification_code: str

    def __post_init__(self) -> None:
        for name in ("raw_value", "label", "explanation", "qualification_code"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))


@dataclass(frozen=True, slots=True)
class CaseHeaderReport:
    case_id: str
    case_name: str | None = None
    case_number: str | None = None
    claimant: str | None = None
    respondent: str | None = None
    case_status: str | None = None
    court_or_tribunal: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _uuid(self.case_id, field_name="case_id"))
        for name in (
            "case_name",
            "case_number",
            "claimant",
            "respondent",
            "case_status",
            "court_or_tribunal",
        ):
            object.__setattr__(self, name, _optional(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class AnalyticalLineageReport:
    foundation_synthesis_id: str
    foundation_schema_version: str
    foundation_synthesiser_version: str
    matrices_schema_version: str
    matrices_builder_version: str
    chronology_schema_version: str
    chronology_builder_version: str
    synthesis_schema_version: str
    synthesis_builder_version: str
    source_analysis_ids: tuple[str, ...]
    issue_definition_lineage: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "foundation_synthesis_id",
            _uuid(self.foundation_synthesis_id, field_name="foundation_synthesis_id"),
        )
        for name in (
            "foundation_schema_version",
            "foundation_synthesiser_version",
            "matrices_schema_version",
            "matrices_builder_version",
            "chronology_schema_version",
            "chronology_builder_version",
            "synthesis_schema_version",
            "synthesis_builder_version",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "source_analysis_ids",
            _unique(self.source_analysis_ids, field_name="source_analysis_ids", sort=True),
        )
        lineage = tuple(
            (
                _uuid(item[0], field_name="issue_analysis_id"),
                _required(item[1], field_name="issue_definition_id"),
                _required(item[2], field_name="issue_definition_version"),
            )
            for item in self.issue_definition_lineage
        )
        if len(lineage) != len(set(lineage)):
            raise ValueError("issue_definition_lineage must be unique.")
        object.__setattr__(self, "issue_definition_lineage", lineage)


@dataclass(frozen=True, slots=True)
class ReportStatement:
    report_statement_id: str
    category: str
    text: str
    evidence_keys: tuple[str, ...] = ()
    citation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_statement_id",
            _uuid(self.report_statement_id, field_name="report_statement_id"),
        )
        object.__setattr__(self, "category", _required(self.category, field_name="category"))
        object.__setattr__(self, "text", _required(self.text, field_name="text"))
        object.__setattr__(
            self,
            "evidence_keys",
            _unique(self.evidence_keys, field_name="evidence_keys", sort=True),
        )
        object.__setattr__(
            self,
            "citation_ids",
            _unique(self.citation_ids, field_name="citation_ids", sort=True),
        )


@dataclass(frozen=True, slots=True)
class CitationRecord:
    citation_id: str
    evidence_key: str
    citation: str
    document_name: str
    source_type: str
    evidence_status: str
    provenance_type: str
    provenance_basis: str
    provenance_confidence: str
    evidence_use_coordinates: tuple[tuple[str, str, str], ...]
    document_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    date: str | None = None
    author: str | None = None
    parties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "citation_id",
            "evidence_key",
            "citation",
            "document_name",
            "source_type",
            "evidence_status",
            "provenance_type",
            "provenance_basis",
            "provenance_confidence",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        if self.citation_id != self.evidence_key:
            raise ValueError("citation_id must equal evidence_key.")
        object.__setattr__(self, "document_id", _optional(self.document_id))
        object.__setattr__(self, "chunk_id", _optional(self.chunk_id))
        object.__setattr__(self, "date", _optional(self.date))
        object.__setattr__(self, "author", _optional(self.author))
        if self.page is not None and self.page < 1:
            raise ValueError("page must be 1 or greater.")
        object.__setattr__(self, "parties", _unique(self.parties, field_name="parties"))
        coords = tuple(
            (
                _uuid(item[0], field_name="issue_analysis_id"),
                _required(item[1], field_name="element_id"),
                _required(item[2], field_name="evidence_key"),
            )
            for item in self.evidence_use_coordinates
        )
        if len(coords) != len(set(coords)):
            raise ValueError("evidence_use_coordinates must be unique.")
        if any(item[2] != self.evidence_key for item in coords):
            raise ValueError("All evidence-use coordinates must use CitationRecord.evidence_key.")
        object.__setattr__(self, "evidence_use_coordinates", coords)


@dataclass(frozen=True, slots=True)
class ResolvedProvenance:
    provenance_type: str
    identity: tuple[str, ...]
    display_label: str
    citation_ids: tuple[str, ...] = ()
    raw_role_or_status: str | None = None
    identity_only: bool = False
    qualification_text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provenance_type",
            _required(self.provenance_type, field_name="provenance_type"),
        )
        object.__setattr__(
            self,
            "identity",
            _unique(self.identity, field_name="identity") if len(set(self.identity)) == len(self.identity) else tuple(
                _required(item, field_name="identity") for item in self.identity
            ),
        )
        if not self.identity:
            raise ValueError("ResolvedProvenance.identity must not be empty.")
        object.__setattr__(
            self,
            "display_label",
            _required(self.display_label, field_name="display_label"),
        )
        object.__setattr__(
            self,
            "citation_ids",
            _unique(self.citation_ids, field_name="citation_ids", sort=True),
        )
        object.__setattr__(self, "raw_role_or_status", _optional(self.raw_role_or_status))
        object.__setattr__(self, "qualification_text", str(self.qualification_text).strip())


@dataclass(frozen=True, slots=True)
class FindingReport:
    finding_id: str
    finding_type: str
    scope: str
    analytical_bases: tuple[str, ...]
    status: StatusView
    confidence: StatusView
    summary: str
    origin: str
    category: str
    issue_ids: tuple[str, ...]
    element_coordinates: tuple[tuple[str, str], ...]
    related_finding_ids: tuple[str, ...]
    provenance: tuple[ResolvedProvenance, ...]
    citation_ids: tuple[str, ...]
    controlled_explanation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _uuid(self.finding_id, field_name="finding_id"))
        for name in ("finding_type", "scope", "summary", "origin", "category"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "analytical_bases",
            _unique(self.analytical_bases, field_name="analytical_bases", sort=True),
        )
        object.__setattr__(
            self,
            "issue_ids",
            _unique(self.issue_ids, field_name="issue_ids", sort=True),
        )
        coords = tuple(
            (_uuid(item[0], field_name="issue_analysis_id"), _required(item[1], field_name="element_id"))
            for item in self.element_coordinates
        )
        if len(coords) != len(set(coords)):
            raise ValueError("element_coordinates must be unique.")
        object.__setattr__(self, "element_coordinates", tuple(sorted(coords)))
        object.__setattr__(
            self,
            "related_finding_ids",
            _unique(self.related_finding_ids, field_name="related_finding_ids", sort=True),
        )
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(
            self,
            "citation_ids",
            _unique(self.citation_ids, field_name="citation_ids", sort=True),
        )
        object.__setattr__(self, "controlled_explanation", str(self.controlled_explanation).strip())


@dataclass(frozen=True, slots=True)
class ElementReport:
    issue_analysis_id: str
    element_id: str
    element_name: str
    legal_question: str
    analysis_status: StatusView
    analysis_confidence: StatusView
    established_matters: tuple[ReportStatement, ...]
    supported_matters: tuple[ReportStatement, ...]
    not_supported_matters: tuple[ReportStatement, ...]
    source_assertions: tuple[ReportStatement, ...]
    unresolved_matters: tuple[str, ...]
    legal_significance: str
    provisional_analysis: str
    linked_direct_finding_ids: tuple[str, ...]
    linked_higher_order_finding_ids: tuple[str, ...]
    linked_gap_ids: tuple[str, ...]
    linked_risk_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        for name in ("element_id", "element_name", "legal_question", "legal_significance", "provisional_analysis"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        for name in (
            "established_matters",
            "supported_matters",
            "not_supported_matters",
            "source_assertions",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(
            self,
            "unresolved_matters",
            _unique(self.unresolved_matters, field_name="unresolved_matters"),
        )
        for name in (
            "linked_direct_finding_ids",
            "linked_higher_order_finding_ids",
            "linked_gap_ids",
            "linked_risk_ids",
        ):
            object.__setattr__(self, name, _unique(getattr(self, name), field_name=name, sort=True))


@dataclass(frozen=True, slots=True)
class IssueReport:
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    original_user_question: str
    issue_summary: str
    position_status: StatusView
    confidence: StatusView
    material_finding_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    risk_ids: tuple[str, ...]
    elements: tuple[ElementReport, ...]
    direct_findings: tuple[FindingReport, ...]
    higher_order_findings: tuple[FindingReport, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        for name in (
            "issue_definition_id",
            "issue_definition_version",
            "issue_name",
            "original_user_question",
            "issue_summary",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        for name in ("material_finding_ids", "conflict_ids", "gap_ids", "risk_ids"):
            object.__setattr__(self, name, _unique(getattr(self, name), field_name=name, sort=True))
        object.__setattr__(self, "elements", tuple(self.elements))
        object.__setattr__(self, "direct_findings", tuple(self.direct_findings))
        object.__setattr__(self, "higher_order_findings", tuple(self.higher_order_findings))


@dataclass(frozen=True, slots=True)
class TemporalExtentReport:
    kind: str
    start_year: int
    start_month: int | None
    start_day: int | None
    start_precision: str
    end_year: int | None
    end_month: int | None
    end_day: int | None
    end_precision: str | None
    display_text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _required(self.kind, field_name="kind"))
        object.__setattr__(self, "start_precision", _required(self.start_precision, field_name="start_precision"))
        object.__setattr__(self, "end_precision", _optional(self.end_precision))
        object.__setattr__(self, "display_text", _required(self.display_text, field_name="display_text"))


@dataclass(frozen=True, slots=True)
class EventAssertionReport:
    event_id: str
    assertion_id: str
    description: str
    issue_analysis_id: str
    element_id: str
    evidence_key: str
    citation_id: str
    source_proposition_index: int
    occurrence_status: StatusView
    timing_status: StatusView
    confidence: StatusView
    temporal_extent: TemporalExtentReport | None
    extraction_basis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid(self.event_id, field_name="event_id"))
        object.__setattr__(self, "assertion_id", _uuid(self.assertion_id, field_name="assertion_id"))
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        for name in ("description", "element_id", "evidence_key", "citation_id", "extraction_basis"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        if self.source_proposition_index < 0:
            raise ValueError("source_proposition_index must be zero or greater.")


@dataclass(frozen=True, slots=True)
class EventReport:
    event_id: str
    description: str
    normalized_event_core: str
    event_type: str
    occurrence_status: StatusView
    timing_status: StatusView
    confidence: StatusView
    canonical_temporal_extent: TemporalExtentReport | None
    participants: tuple[str, ...]
    evidence_keys: tuple[str, ...]
    citation_ids: tuple[str, ...]
    related_issue_ids: tuple[str, ...]
    related_element_coordinates: tuple[tuple[str, str], ...]
    assertions: tuple[EventAssertionReport, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid(self.event_id, field_name="event_id"))
        for name in ("description", "normalized_event_core", "event_type"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        object.__setattr__(self, "participants", _unique(self.participants, field_name="participants"))
        object.__setattr__(self, "evidence_keys", _unique(self.evidence_keys, field_name="evidence_keys"))
        object.__setattr__(self, "citation_ids", _unique(self.citation_ids, field_name="citation_ids"))
        object.__setattr__(
            self,
            "related_issue_ids",
            _unique(self.related_issue_ids, field_name="related_issue_ids", sort=True),
        )
        coords = tuple(
            (_uuid(item[0], field_name="issue_analysis_id"), _required(item[1], field_name="element_id"))
            for item in self.related_element_coordinates
        )
        if len(coords) != len(set(coords)):
            raise ValueError("related_element_coordinates must be unique.")
        object.__setattr__(self, "related_element_coordinates", tuple(sorted(coords)))
        object.__setattr__(self, "assertions", tuple(self.assertions))


@dataclass(frozen=True, slots=True)
class ConflictReport:
    conflict_id: str
    conflict_type: str
    scope: str
    subject: str
    status: StatusView
    materiality: StatusView
    side_a: tuple[ResolvedProvenance, ...]
    side_b: tuple[ResolvedProvenance, ...]
    related_issue_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "conflict_id", _uuid(self.conflict_id, field_name="conflict_id"))
        for name in ("conflict_type", "scope", "subject"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        object.__setattr__(self, "side_a", tuple(self.side_a))
        object.__setattr__(self, "side_b", tuple(self.side_b))
        object.__setattr__(
            self,
            "related_issue_ids",
            _unique(self.related_issue_ids, field_name="related_issue_ids", sort=True),
        )
        object.__setattr__(self, "citation_ids", _unique(self.citation_ids, field_name="citation_ids", sort=True))


@dataclass(frozen=True, slots=True)
class GapReport:
    gap_id: str
    gap_type: str
    scope: str
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    element_id: str | None
    description: str
    materiality: StatusView
    unresolved_question: str
    provenance: tuple[ResolvedProvenance, ...]
    citation_ids: tuple[str, ...]
    related_finding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "gap_id", _uuid(self.gap_id, field_name="gap_id"))
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        for name in (
            "gap_type",
            "scope",
            "issue_definition_id",
            "issue_definition_version",
            "description",
            "unresolved_question",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        object.__setattr__(self, "element_id", _optional(self.element_id))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(self, "citation_ids", _unique(self.citation_ids, field_name="citation_ids", sort=True))
        object.__setattr__(
            self,
            "related_finding_ids",
            _unique(self.related_finding_ids, field_name="related_finding_ids", sort=True),
        )


@dataclass(frozen=True, slots=True)
class RiskReport:
    risk_id: str
    risk_type: str
    scope: str
    materiality: StatusView
    description: str
    classification_explanation: str
    basis_finding_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    affected_issue_ids: tuple[str, ...]
    provenance: tuple[ResolvedProvenance, ...]
    citation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_id", _uuid(self.risk_id, field_name="risk_id"))
        for name in ("risk_type", "scope", "description", "classification_explanation"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))
        for name in ("basis_finding_ids", "conflict_ids", "gap_ids", "affected_issue_ids", "citation_ids"):
            object.__setattr__(self, name, _unique(getattr(self, name), field_name=name, sort=True))
        object.__setattr__(self, "provenance", tuple(self.provenance))


@dataclass(frozen=True, slots=True)
class PriorityQuestionReport:
    question_id: str
    question: str
    priority: StatusView
    basis_type: str
    affected_issue_ids: tuple[str, ...]
    affected_element_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    provenance: tuple[ResolvedProvenance, ...]
    citation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _uuid(self.question_id, field_name="question_id"))
        object.__setattr__(self, "question", _required(self.question, field_name="question"))
        object.__setattr__(self, "basis_type", _required(self.basis_type, field_name="basis_type"))
        for name in (
            "affected_issue_ids",
            "affected_element_ids",
            "finding_ids",
            "gap_ids",
            "conflict_ids",
            "citation_ids",
        ):
            object.__setattr__(self, name, _unique(getattr(self, name), field_name=name, sort=True))
        object.__setattr__(self, "provenance", tuple(self.provenance))


@dataclass(frozen=True, slots=True)
class OverallStateReport:
    state: StatusView
    issue_count: int
    element_count: int
    event_count: int
    finding_count: int
    conflict_count: int
    gap_count: int
    risk_count: int
    priority_question_count: int
    citation_count: int
    count_qualification: str

    def __post_init__(self) -> None:
        for name in (
            "issue_count",
            "element_count",
            "event_count",
            "finding_count",
            "conflict_count",
            "gap_count",
            "risk_count",
            "priority_question_count",
            "citation_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative.")
        object.__setattr__(
            self,
            "count_qualification",
            _required(self.count_qualification, field_name="count_qualification"),
        )


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    code: str
    label: str
    explanation: str

    def __post_init__(self) -> None:
        for name in ("code", "label", "explanation"):
            object.__setattr__(self, name, _required(getattr(self, name), field_name=name))


@dataclass(frozen=True, slots=True)
class ManifestSection:
    section_id: str
    section_key: str
    ordinal: int
    ordered_item_ids: tuple[str, ...]
    ordered_citation_ids: tuple[str, ...]
    raw_status_values: tuple[str, ...]
    qualification_codes: tuple[str, ...]
    is_mandatory: bool
    is_empty: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_id", _required(self.section_id, field_name="section_id"))
        object.__setattr__(self, "section_key", _required(self.section_key, field_name="section_key"))
        if self.section_key not in SECTION_KEYS:
            raise ValueError(f"Unknown section key {self.section_key!r}.")
        if self.section_id != self.section_key:
            raise ValueError("section_id must equal the controlled section_key.")
        if self.ordinal < 0:
            raise ValueError("ordinal must not be negative.")
        for name in (
            "ordered_item_ids",
            "ordered_citation_ids",
            "raw_status_values",
            "qualification_codes",
        ):
            object.__setattr__(self, name, tuple(_required(item, field_name=name) for item in getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ReportManifest:
    manifest_id: str
    report_projection_id: str
    projection_payload_sha256: str
    ordered_section_ids: tuple[str, ...]
    sections: tuple[ManifestSection, ...]
    ordered_issue_ids: tuple[str, ...]
    ordered_element_coordinates: tuple[str, ...]
    ordered_finding_ids: tuple[str, ...]
    ordered_event_ids: tuple[str, ...]
    ordered_event_assertion_coordinates: tuple[str, ...]
    ordered_conflict_ids: tuple[str, ...]
    ordered_gap_ids: tuple[str, ...]
    ordered_risk_ids: tuple[str, ...]
    ordered_question_ids: tuple[str, ...]
    ordered_citation_ids: tuple[str, ...]
    raw_status_inventory: tuple[tuple[str, str], ...]
    qualification_inventory: tuple[tuple[str, str], ...]
    schema_version: str = REPORT_MANIFEST_SCHEMA_VERSION
    builder_version: str = REPORT_MANIFEST_BUILDER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_id", _uuid(self.manifest_id, field_name="manifest_id"))
        object.__setattr__(
            self,
            "report_projection_id",
            _uuid(self.report_projection_id, field_name="report_projection_id"),
        )
        object.__setattr__(
            self,
            "projection_payload_sha256",
            _sha(self.projection_payload_sha256, field_name="projection_payload_sha256"),
        )
        if self.schema_version != REPORT_MANIFEST_SCHEMA_VERSION:
            raise ValueError("Unsupported report manifest schema version.")
        if self.builder_version != REPORT_MANIFEST_BUILDER_VERSION:
            raise ValueError("Unsupported report manifest builder version.")
        object.__setattr__(self, "ordered_section_ids", tuple(self.ordered_section_ids))
        object.__setattr__(self, "sections", tuple(self.sections))
        for name in (
            "ordered_issue_ids",
            "ordered_element_coordinates",
            "ordered_finding_ids",
            "ordered_event_ids",
            "ordered_event_assertion_coordinates",
            "ordered_conflict_ids",
            "ordered_gap_ids",
            "ordered_risk_ids",
            "ordered_question_ids",
            "ordered_citation_ids",
        ):
            object.__setattr__(self, name, tuple(_required(item, field_name=name) for item in getattr(self, name)))
        object.__setattr__(self, "raw_status_inventory", tuple(self.raw_status_inventory))
        object.__setattr__(self, "qualification_inventory", tuple(self.qualification_inventory))


@dataclass(frozen=True, slots=True)
class CaseReportProjection:
    report_projection_id: str
    source_synthesis_id: str
    source_foundation_sha256: str
    source_matrices_sha256: str
    source_chronology_sha256: str
    source_synthesis_sha256: str
    source_metadata_sha256: str | None
    projection_payload_sha256: str
    case_header: CaseHeaderReport
    lineage: AnalyticalLineageReport
    overall_state: OverallStateReport
    issues: tuple[IssueReport, ...]
    chronology: tuple[EventReport, ...]
    cross_issue_findings: tuple[FindingReport, ...]
    conflicts: tuple[ConflictReport, ...]
    gaps: tuple[GapReport, ...]
    risks: tuple[RiskReport, ...]
    priority_questions: tuple[PriorityQuestionReport, ...]
    citations: tuple[CitationRecord, ...]
    glossary: tuple[GlossaryEntry, ...]
    manifest: ReportManifest
    schema_version: str = REPORT_PROJECTION_SCHEMA_VERSION
    projector_version: str = REPORT_PROJECTOR_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_projection_id",
            _uuid(self.report_projection_id, field_name="report_projection_id"),
        )
        object.__setattr__(
            self,
            "source_synthesis_id",
            _uuid(self.source_synthesis_id, field_name="source_synthesis_id"),
        )
        for name in (
            "source_foundation_sha256",
            "source_matrices_sha256",
            "source_chronology_sha256",
            "source_synthesis_sha256",
            "projection_payload_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), field_name=name))
        object.__setattr__(
            self,
            "source_metadata_sha256",
            _sha(self.source_metadata_sha256, field_name="source_metadata_sha256", allow_none=True),
        )
        if self.schema_version != REPORT_PROJECTION_SCHEMA_VERSION:
            raise ValueError("Unsupported report projection schema version.")
        if self.projector_version != REPORT_PROJECTOR_VERSION:
            raise ValueError("Unsupported report projector version.")
        for name in (
            "issues",
            "chronology",
            "cross_issue_findings",
            "conflicts",
            "gaps",
            "risks",
            "priority_questions",
            "citations",
            "glossary",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))


__all__ = [
    "MANDATORY_SECTION_KEYS",
    "REPORT_MANIFEST_BUILDER_VERSION",
    "REPORT_MANIFEST_SCHEMA_VERSION",
    "REPORT_PROJECTION_SCHEMA_VERSION",
    "REPORT_PROJECTOR_VERSION",
    "SECTION_KEYS",
    "AnalyticalLineageReport",
    "CaseHeaderReport",
    "CaseReportMetadata",
    "CaseReportProjection",
    "CitationRecord",
    "ConflictReport",
    "ElementReport",
    "EventAssertionReport",
    "EventReport",
    "FindingReport",
    "GapReport",
    "GlossaryEntry",
    "ManifestSection",
    "OverallStateReport",
    "PriorityQuestionReport",
    "ReportManifest",
    "ReportStatement",
    "ResolvedProvenance",
    "RiskReport",
    "StatusView",
    "TemporalExtentReport",
]
