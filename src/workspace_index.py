"""Deterministic projection-only navigation index for the M6 workspace."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Iterable, Mapping
import unicodedata

from case_reporting.models import (
    CaseReportProjection,
    CitationRecord,
    ConflictReport,
    ElementReport,
    EventAssertionReport,
    EventReport,
    FindingReport,
    GapReport,
    IssueReport,
    PriorityQuestionReport,
    ReportStatement,
    RiskReport,
)
from case_reporting.validation import validate_case_report_projection

WORKSPACE_INDEX_VERSION: Final[str] = "case-workspace-index/1.0"
_ALLOWED_KINDS: Final[frozenset[str]] = frozenset(
    {
        "issue",
        "element",
        "statement",
        "finding",
        "event",
        "assertion",
        "conflict",
        "gap",
        "risk",
        "question",
        "citation",
    }
)
_STATEMENT_FIELDS: Final[tuple[str, ...]] = (
    "established_matters",
    "supported_matters",
    "not_supported_matters",
    "source_assertions",
)


class WorkspaceIndexError(ValueError):
    """Raised when deterministic workspace navigation integrity fails."""


@dataclass(frozen=True, slots=True, order=True)
class WorkspaceObjectKey:
    """Exact navigation identity for one frozen projected object."""

    kind: str
    primary_id: str
    secondary_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unsupported workspace object kind {self.kind!r}.")
        if not str(self.primary_id).strip():
            raise ValueError("primary_id must not be empty.")
        if self.secondary_id is not None and not str(self.secondary_id).strip():
            raise ValueError("secondary_id must not be empty when provided.")
        if self.kind in {"element", "assertion"} and self.secondary_id is None:
            raise ValueError(f"{self.kind} requires a secondary_id.")
        if self.kind not in {"element", "assertion"} and self.secondary_id is not None:
            raise ValueError(f"{self.kind} must not use a secondary_id.")


@dataclass(frozen=True, slots=True)
class WorkspaceBacklink:
    """Mechanical reversal of one explicit frozen source field."""

    source: WorkspaceObjectKey
    source_field: str

    def __post_init__(self) -> None:
        if not str(self.source_field).strip():
            raise ValueError("source_field must not be empty.")


@dataclass(frozen=True, slots=True, order=True)
class DocumentGroupKey:
    """Exact frozen document grouping identity."""

    document_name: str
    document_id: str | None

    def __post_init__(self) -> None:
        if not str(self.document_name).strip():
            raise ValueError("document_name must not be empty.")


@dataclass(frozen=True, slots=True)
class RecordedNameOccurrence:
    """One exact recorded party/name occurrence in the frozen projection."""

    value: str
    context: str
    target: WorkspaceObjectKey | None

    def __post_init__(self) -> None:
        if not str(self.value).strip():
            raise ValueError("value must not be empty.")
        if self.context not in {
            "case_header.claimant",
            "case_header.respondent",
            "event.participants",
            "citation.author",
            "citation.parties",
        }:
            raise ValueError(f"Unsupported recorded-name context {self.context!r}.")


@dataclass(frozen=True, slots=True)
class WorkspaceIndex:
    """Immutable ephemeral identity/backlink index over one report projection."""

    version: str
    issues_by_id: Mapping[str, IssueReport]
    elements_by_coordinate: Mapping[tuple[str, str], ElementReport]
    statements_by_id: Mapping[str, ReportStatement]
    findings_by_id: Mapping[str, FindingReport]
    events_by_id: Mapping[str, EventReport]
    assertions_by_coordinate: Mapping[tuple[str, str], EventAssertionReport]
    conflicts_by_id: Mapping[str, ConflictReport]
    gaps_by_id: Mapping[str, GapReport]
    risks_by_id: Mapping[str, RiskReport]
    questions_by_id: Mapping[str, PriorityQuestionReport]
    citations_by_id: Mapping[str, CitationRecord]
    object_by_key: Mapping[WorkspaceObjectKey, object]
    outgoing: Mapping[WorkspaceObjectKey, tuple[tuple[str, WorkspaceObjectKey], ...]]
    backlinks: Mapping[WorkspaceObjectKey, tuple[WorkspaceBacklink, ...]]
    issue_keys: tuple[WorkspaceObjectKey, ...]
    element_keys: tuple[WorkspaceObjectKey, ...]
    statement_keys: tuple[WorkspaceObjectKey, ...]
    finding_keys: tuple[WorkspaceObjectKey, ...]
    event_keys: tuple[WorkspaceObjectKey, ...]
    assertion_keys: tuple[WorkspaceObjectKey, ...]
    conflict_keys: tuple[WorkspaceObjectKey, ...]
    gap_keys: tuple[WorkspaceObjectKey, ...]
    risk_keys: tuple[WorkspaceObjectKey, ...]
    question_keys: tuple[WorkspaceObjectKey, ...]
    citation_keys: tuple[WorkspaceObjectKey, ...]
    elements_by_element_id: Mapping[str, tuple[tuple[str, str], ...]]
    unresolved_priority_element_ids: Mapping[str, tuple[str, ...]]
    document_groups: Mapping[DocumentGroupKey, tuple[CitationRecord, ...]]
    document_group_keys: tuple[DocumentGroupKey, ...]
    recorded_names: Mapping[str, tuple[RecordedNameOccurrence, ...]]
    recorded_name_values: tuple[str, ...]


def _readonly(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(mapping))


def _normalise_literal(value: object) -> str:
    return unicodedata.normalize("NFC", str(value)).casefold()


def _candidate_strings(values: Iterable[object]) -> Iterable[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, tuple):
            yield from _candidate_strings(value)
            continue
        yield str(value)


def literal_query_matches(query: str, candidate_values: Iterable[object]) -> bool:
    """Return whether a stripped NFC/casefolded literal query matches any value."""

    prepared = unicodedata.normalize("NFC", str(query).strip()).casefold()
    if not prepared:
        return True
    return any(prepared in _normalise_literal(value) for value in _candidate_strings(candidate_values))


def _parse_coordinate(value: str, *, field_name: str) -> tuple[str, str]:
    parts = value.split("|", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise WorkspaceIndexError(f"{field_name} contains an invalid coordinate {value!r}.")
    return parts[0], parts[1]


def _add_unique(mapping: dict, key, value, *, field_name: str) -> None:
    if key in mapping:
        raise WorkspaceIndexError(f"Duplicate {field_name}: {key!r}.")
    mapping[key] = value


def _register_finding(mapping: dict[str, FindingReport], value: FindingReport) -> None:
    current = mapping.get(value.finding_id)
    if current is None:
        mapping[value.finding_id] = value
    elif current != value:
        raise WorkspaceIndexError(
            f"Finding ID {value.finding_id!r} resolves to inconsistent frozen objects."
        )


def _provenance_citations(provenance) -> Iterable[tuple[int, str]]:
    for index, item in enumerate(provenance):
        for citation_id in item.citation_ids:
            yield index, citation_id


def build_workspace_index(projection: CaseReportProjection) -> WorkspaceIndex:
    """Build and validate deterministic M6 navigation indexes from one projection."""

    validate_case_report_projection(projection)

    issues: dict[str, IssueReport] = {}
    elements: dict[tuple[str, str], ElementReport] = {}
    statements: dict[str, ReportStatement] = {}
    findings: dict[str, FindingReport] = {}
    events: dict[str, EventReport] = {}
    assertions: dict[tuple[str, str], EventAssertionReport] = {}
    conflicts: dict[str, ConflictReport] = {}
    gaps: dict[str, GapReport] = {}
    risks: dict[str, RiskReport] = {}
    questions: dict[str, PriorityQuestionReport] = {}
    citations: dict[str, CitationRecord] = {}

    statement_keys: list[WorkspaceObjectKey] = []
    elements_by_element_id: dict[str, list[tuple[str, str]]] = {}

    for issue in projection.issues:
        _add_unique(issues, issue.issue_analysis_id, issue, field_name="issue_analysis_id")
        for element in issue.elements:
            coordinate = (issue.issue_analysis_id, element.element_id)
            if element.issue_analysis_id != issue.issue_analysis_id:
                raise WorkspaceIndexError("Element issue_analysis_id does not match its owning issue.")
            _add_unique(elements, coordinate, element, field_name="element coordinate")
            elements_by_element_id.setdefault(element.element_id, []).append(coordinate)
            for field_name in _STATEMENT_FIELDS:
                for statement in getattr(element, field_name):
                    _add_unique(
                        statements,
                        statement.report_statement_id,
                        statement,
                        field_name="report_statement_id",
                    )
                    statement_keys.append(
                        WorkspaceObjectKey("statement", statement.report_statement_id)
                    )
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            _register_finding(findings, finding)
    for finding in projection.cross_issue_findings:
        _register_finding(findings, finding)

    for event in projection.chronology:
        _add_unique(events, event.event_id, event, field_name="event_id")
        for assertion in event.assertions:
            if assertion.event_id != event.event_id:
                raise WorkspaceIndexError("Assertion event_id does not match its owning event.")
            _add_unique(
                assertions,
                (event.event_id, assertion.assertion_id),
                assertion,
                field_name="event assertion coordinate",
            )

    for value in projection.conflicts:
        _add_unique(conflicts, value.conflict_id, value, field_name="conflict_id")
    for value in projection.gaps:
        _add_unique(gaps, value.gap_id, value, field_name="gap_id")
    for value in projection.risks:
        _add_unique(risks, value.risk_id, value, field_name="risk_id")
    for value in projection.priority_questions:
        _add_unique(questions, value.question_id, value, field_name="question_id")
    for value in projection.citations:
        _add_unique(citations, value.citation_id, value, field_name="citation_id")

    issue_keys = tuple(WorkspaceObjectKey("issue", item) for item in projection.manifest.ordered_issue_ids)
    element_keys = tuple(
        WorkspaceObjectKey("element", *(_parse_coordinate(item, field_name="ordered_element_coordinates")))
        for item in projection.manifest.ordered_element_coordinates
    )
    finding_keys = tuple(WorkspaceObjectKey("finding", item) for item in projection.manifest.ordered_finding_ids)
    event_keys = tuple(WorkspaceObjectKey("event", item) for item in projection.manifest.ordered_event_ids)
    assertion_keys = tuple(
        WorkspaceObjectKey("assertion", *(_parse_coordinate(item, field_name="ordered_event_assertion_coordinates")))
        for item in projection.manifest.ordered_event_assertion_coordinates
    )
    conflict_keys = tuple(WorkspaceObjectKey("conflict", item) for item in projection.manifest.ordered_conflict_ids)
    gap_keys = tuple(WorkspaceObjectKey("gap", item) for item in projection.manifest.ordered_gap_ids)
    risk_keys = tuple(WorkspaceObjectKey("risk", item) for item in projection.manifest.ordered_risk_ids)
    question_keys = tuple(WorkspaceObjectKey("question", item) for item in projection.manifest.ordered_question_ids)
    citation_keys = tuple(WorkspaceObjectKey("citation", item) for item in projection.manifest.ordered_citation_ids)

    expected_maps = (
        (issue_keys, issues, "issue"),
        (element_keys, elements, "element"),
        (finding_keys, findings, "finding"),
        (event_keys, events, "event"),
        (assertion_keys, assertions, "assertion"),
        (conflict_keys, conflicts, "conflict"),
        (gap_keys, gaps, "gap"),
        (risk_keys, risks, "risk"),
        (question_keys, questions, "question"),
        (citation_keys, citations, "citation"),
    )
    for keys, mapping, label in expected_maps:
        lookup_ids = {
            (key.primary_id, key.secondary_id) if key.secondary_id is not None else key.primary_id
            for key in keys
        }
        if lookup_ids != set(mapping):
            raise WorkspaceIndexError(f"Manifest {label} inventory does not match projection objects.")

    object_by_key: dict[WorkspaceObjectKey, object] = {}
    for key in issue_keys:
        object_by_key[key] = issues[key.primary_id]
    for key in element_keys:
        object_by_key[key] = elements[(key.primary_id, key.secondary_id)]
    for key in statement_keys:
        object_by_key[key] = statements[key.primary_id]
    for key in finding_keys:
        object_by_key[key] = findings[key.primary_id]
    for key in event_keys:
        object_by_key[key] = events[key.primary_id]
    for key in assertion_keys:
        object_by_key[key] = assertions[(key.primary_id, key.secondary_id)]
    for key in conflict_keys:
        object_by_key[key] = conflicts[key.primary_id]
    for key in gap_keys:
        object_by_key[key] = gaps[key.primary_id]
    for key in risk_keys:
        object_by_key[key] = risks[key.primary_id]
    for key in question_keys:
        object_by_key[key] = questions[key.primary_id]
    for key in citation_keys:
        object_by_key[key] = citations[key.primary_id]

    outgoing: dict[WorkspaceObjectKey, list[tuple[str, WorkspaceObjectKey]]] = {
        key: [] for key in object_by_key
    }
    backlinks: dict[WorkspaceObjectKey, list[WorkspaceBacklink]] = {
        key: [] for key in object_by_key
    }

    def link(source: WorkspaceObjectKey, field: str, target: WorkspaceObjectKey) -> None:
        if source not in object_by_key:
            raise WorkspaceIndexError(f"Unknown workspace link source {source!r}.")
        if target not in object_by_key:
            raise WorkspaceIndexError(
                f"Frozen field {field} targets unknown workspace object {target!r}."
            )
        pair = (field, target)
        if pair not in outgoing[source]:
            outgoing[source].append(pair)
        backlink = WorkspaceBacklink(source=source, source_field=field)
        if backlink not in backlinks[target]:
            backlinks[target].append(backlink)

    for issue in projection.issues:
        source = WorkspaceObjectKey("issue", issue.issue_analysis_id)
        for element in issue.elements:
            link(source, "IssueReport.elements", WorkspaceObjectKey("element", issue.issue_analysis_id, element.element_id))
        for finding in issue.direct_findings:
            link(source, "IssueReport.direct_findings", WorkspaceObjectKey("finding", finding.finding_id))
        for finding in issue.higher_order_findings:
            link(source, "IssueReport.higher_order_findings", WorkspaceObjectKey("finding", finding.finding_id))
        for finding_id in issue.material_finding_ids:
            link(source, "IssueReport.material_finding_ids", WorkspaceObjectKey("finding", finding_id))
        for item in issue.conflict_ids:
            link(source, "IssueReport.conflict_ids", WorkspaceObjectKey("conflict", item))
        for item in issue.gap_ids:
            link(source, "IssueReport.gap_ids", WorkspaceObjectKey("gap", item))
        for item in issue.risk_ids:
            link(source, "IssueReport.risk_ids", WorkspaceObjectKey("risk", item))
        for element in issue.elements:
            element_key = WorkspaceObjectKey("element", issue.issue_analysis_id, element.element_id)
            for field_name in _STATEMENT_FIELDS:
                for statement in getattr(element, field_name):
                    statement_key = WorkspaceObjectKey("statement", statement.report_statement_id)
                    link(element_key, f"ElementReport.{field_name}", statement_key)
                    for citation_id in statement.citation_ids:
                        link(statement_key, "ReportStatement.citation_ids", WorkspaceObjectKey("citation", citation_id))
            for finding_id in element.linked_direct_finding_ids:
                link(element_key, "ElementReport.linked_direct_finding_ids", WorkspaceObjectKey("finding", finding_id))
            for finding_id in element.linked_higher_order_finding_ids:
                link(element_key, "ElementReport.linked_higher_order_finding_ids", WorkspaceObjectKey("finding", finding_id))
            for gap_id in element.linked_gap_ids:
                link(element_key, "ElementReport.linked_gap_ids", WorkspaceObjectKey("gap", gap_id))
            for risk_id in element.linked_risk_ids:
                link(element_key, "ElementReport.linked_risk_ids", WorkspaceObjectKey("risk", risk_id))

    for finding in findings.values():
        source = WorkspaceObjectKey("finding", finding.finding_id)
        for issue_id in finding.issue_ids:
            link(source, "FindingReport.issue_ids", WorkspaceObjectKey("issue", issue_id))
        for issue_id, element_id in finding.element_coordinates:
            link(source, "FindingReport.element_coordinates", WorkspaceObjectKey("element", issue_id, element_id))
        for finding_id in finding.related_finding_ids:
            link(source, "FindingReport.related_finding_ids", WorkspaceObjectKey("finding", finding_id))
        for citation_id in finding.citation_ids:
            link(source, "FindingReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for p_index, citation_id in _provenance_citations(finding.provenance):
            link(source, f"FindingReport.provenance[{p_index}].citation_ids", WorkspaceObjectKey("citation", citation_id))

    for event in projection.chronology:
        source = WorkspaceObjectKey("event", event.event_id)
        for assertion in event.assertions:
            assertion_key = WorkspaceObjectKey("assertion", event.event_id, assertion.assertion_id)
            link(source, "EventReport.assertions", assertion_key)
            link(assertion_key, "EventAssertionReport.citation_id", WorkspaceObjectKey("citation", assertion.citation_id))
            link(
                assertion_key,
                "EventAssertionReport.issue_analysis_id/element_id",
                WorkspaceObjectKey("element", assertion.issue_analysis_id, assertion.element_id),
            )
        for citation_id in event.citation_ids:
            link(source, "EventReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for issue_id in event.related_issue_ids:
            link(source, "EventReport.related_issue_ids", WorkspaceObjectKey("issue", issue_id))
        for issue_id, element_id in event.related_element_coordinates:
            link(source, "EventReport.related_element_coordinates", WorkspaceObjectKey("element", issue_id, element_id))

    for conflict in projection.conflicts:
        source = WorkspaceObjectKey("conflict", conflict.conflict_id)
        for issue_id in conflict.related_issue_ids:
            link(source, "ConflictReport.related_issue_ids", WorkspaceObjectKey("issue", issue_id))
        for citation_id in conflict.citation_ids:
            link(source, "ConflictReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for side_name, side in (("side_a", conflict.side_a), ("side_b", conflict.side_b)):
            for p_index, citation_id in _provenance_citations(side):
                link(source, f"ConflictReport.{side_name}[{p_index}].citation_ids", WorkspaceObjectKey("citation", citation_id))

    for gap in projection.gaps:
        source = WorkspaceObjectKey("gap", gap.gap_id)
        link(source, "GapReport.issue_analysis_id", WorkspaceObjectKey("issue", gap.issue_analysis_id))
        if gap.element_id is not None:
            link(source, "GapReport.issue_analysis_id/element_id", WorkspaceObjectKey("element", gap.issue_analysis_id, gap.element_id))
        for finding_id in gap.related_finding_ids:
            link(source, "GapReport.related_finding_ids", WorkspaceObjectKey("finding", finding_id))
        for citation_id in gap.citation_ids:
            link(source, "GapReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for p_index, citation_id in _provenance_citations(gap.provenance):
            link(source, f"GapReport.provenance[{p_index}].citation_ids", WorkspaceObjectKey("citation", citation_id))

    for risk in projection.risks:
        source = WorkspaceObjectKey("risk", risk.risk_id)
        for finding_id in risk.basis_finding_ids:
            link(source, "RiskReport.basis_finding_ids", WorkspaceObjectKey("finding", finding_id))
        for conflict_id in risk.conflict_ids:
            link(source, "RiskReport.conflict_ids", WorkspaceObjectKey("conflict", conflict_id))
        for gap_id in risk.gap_ids:
            link(source, "RiskReport.gap_ids", WorkspaceObjectKey("gap", gap_id))
        for issue_id in risk.affected_issue_ids:
            link(source, "RiskReport.affected_issue_ids", WorkspaceObjectKey("issue", issue_id))
        for citation_id in risk.citation_ids:
            link(source, "RiskReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for p_index, citation_id in _provenance_citations(risk.provenance):
            link(source, f"RiskReport.provenance[{p_index}].citation_ids", WorkspaceObjectKey("citation", citation_id))

    unresolved_priority_elements: dict[str, tuple[str, ...]] = {}
    for question in projection.priority_questions:
        source = WorkspaceObjectKey("question", question.question_id)
        for issue_id in question.affected_issue_ids:
            link(source, "PriorityQuestionReport.affected_issue_ids", WorkspaceObjectKey("issue", issue_id))
        unresolved: list[str] = []
        for element_id in question.affected_element_ids:
            coordinates = elements_by_element_id.get(element_id, [])
            if len(coordinates) == 1:
                issue_id, resolved_element_id = coordinates[0]
                link(source, "PriorityQuestionReport.affected_element_ids", WorkspaceObjectKey("element", issue_id, resolved_element_id))
            else:
                unresolved.append(element_id)
        unresolved_priority_elements[question.question_id] = tuple(unresolved)
        for finding_id in question.finding_ids:
            link(source, "PriorityQuestionReport.finding_ids", WorkspaceObjectKey("finding", finding_id))
        for gap_id in question.gap_ids:
            link(source, "PriorityQuestionReport.gap_ids", WorkspaceObjectKey("gap", gap_id))
        for conflict_id in question.conflict_ids:
            link(source, "PriorityQuestionReport.conflict_ids", WorkspaceObjectKey("conflict", conflict_id))
        for citation_id in question.citation_ids:
            link(source, "PriorityQuestionReport.citation_ids", WorkspaceObjectKey("citation", citation_id))
        for p_index, citation_id in _provenance_citations(question.provenance):
            link(source, f"PriorityQuestionReport.provenance[{p_index}].citation_ids", WorkspaceObjectKey("citation", citation_id))

    for citation in projection.citations:
        source = WorkspaceObjectKey("citation", citation.citation_id)
        for issue_id, element_id, _evidence_key in citation.evidence_use_coordinates:
            link(source, "CitationRecord.evidence_use_coordinates", WorkspaceObjectKey("element", issue_id, element_id))

    document_groups_mut: dict[DocumentGroupKey, list[CitationRecord]] = {}
    document_group_order: list[DocumentGroupKey] = []
    for citation_id in projection.manifest.ordered_citation_ids:
        citation = citations[citation_id]
        key = DocumentGroupKey(citation.document_name, citation.document_id)
        if key not in document_groups_mut:
            document_groups_mut[key] = []
            document_group_order.append(key)
        document_groups_mut[key].append(citation)

    name_occurrences_mut: dict[str, list[RecordedNameOccurrence]] = {}
    name_order: list[str] = []

    def add_name(value: str | None, context: str, target: WorkspaceObjectKey | None) -> None:
        if value is None:
            return
        if value not in name_occurrences_mut:
            name_occurrences_mut[value] = []
            name_order.append(value)
        name_occurrences_mut[value].append(RecordedNameOccurrence(value, context, target))

    add_name(projection.case_header.claimant, "case_header.claimant", None)
    add_name(projection.case_header.respondent, "case_header.respondent", None)
    for event_id in projection.manifest.ordered_event_ids:
        event = events[event_id]
        event_key = WorkspaceObjectKey("event", event_id)
        for participant in event.participants:
            add_name(participant, "event.participants", event_key)
    for citation_id in projection.manifest.ordered_citation_ids:
        citation = citations[citation_id]
        citation_key = WorkspaceObjectKey("citation", citation_id)
        add_name(citation.author, "citation.author", citation_key)
        for party in citation.parties:
            add_name(party, "citation.parties", citation_key)

    return WorkspaceIndex(
        version=WORKSPACE_INDEX_VERSION,
        issues_by_id=_readonly(issues),
        elements_by_coordinate=_readonly(elements),
        statements_by_id=_readonly(statements),
        findings_by_id=_readonly(findings),
        events_by_id=_readonly(events),
        assertions_by_coordinate=_readonly(assertions),
        conflicts_by_id=_readonly(conflicts),
        gaps_by_id=_readonly(gaps),
        risks_by_id=_readonly(risks),
        questions_by_id=_readonly(questions),
        citations_by_id=_readonly(citations),
        object_by_key=_readonly(object_by_key),
        outgoing=_readonly({key: tuple(value) for key, value in outgoing.items()}),
        backlinks=_readonly({key: tuple(value) for key, value in backlinks.items()}),
        issue_keys=issue_keys,
        element_keys=element_keys,
        statement_keys=tuple(statement_keys),
        finding_keys=finding_keys,
        event_keys=event_keys,
        assertion_keys=assertion_keys,
        conflict_keys=conflict_keys,
        gap_keys=gap_keys,
        risk_keys=risk_keys,
        question_keys=question_keys,
        citation_keys=citation_keys,
        elements_by_element_id=_readonly({key: tuple(value) for key, value in elements_by_element_id.items()}),
        unresolved_priority_element_ids=_readonly(unresolved_priority_elements),
        document_groups=_readonly({key: tuple(value) for key, value in document_groups_mut.items()}),
        document_group_keys=tuple(document_group_order),
        recorded_names=_readonly({key: tuple(value) for key, value in name_occurrences_mut.items()}),
        recorded_name_values=tuple(name_order),
    )


__all__ = [
    "WORKSPACE_INDEX_VERSION",
    "WorkspaceIndexError",
    "WorkspaceObjectKey",
    "WorkspaceBacklink",
    "DocumentGroupKey",
    "RecordedNameOccurrence",
    "WorkspaceIndex",
    "build_workspace_index",
    "literal_query_matches",
]
