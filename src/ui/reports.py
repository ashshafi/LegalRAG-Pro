"""Native Streamlit presentation for one frozen M5.1 case report projection."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Final, Iterable

import streamlit as st

from case_reporting.html import render_html_report
from case_reporting.markdown import render_markdown_report
from case_reporting.models import (
    SECTION_KEYS,
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
    ResolvedProvenance,
    RiskReport,
    StatusView,
    TemporalExtentReport,
)
from case_reporting.pdf import render_pdf_report
from case_reporting.validation import validate_case_report_projection


LOGGER = logging.getLogger(__name__)

VIEWER_VERSION: Final = "case-report-streamlit-viewer/1.0"
OUTPUT_PROFILE: Final = "full-audit/1.0"
ABSENT_VALUE_TEXT: Final = "Not recorded in the frozen report projection."
EMPTY_SECTION_TEXT: Final = "None recorded in the frozen report projection."
INVALID_PROJECTION_TEXT: Final = (
    "The stored report projection for this case could not be validated. "
    "No report has been displayed."
)
EXPORT_FAILURE_TEXT: Final = (
    "The requested report artifact could not be generated or validated. "
    "No download has been prepared."
)

_SECTION_LABELS: Final = {
    "report_header": "Report Header",
    "analytical_lineage": "Analytical Lineage",
    "overall_state": "Overall Analytical State",
    "issues": "Issues",
    "chronology": "Chronology",
    "cross_issue_findings": "Cross-Issue Structural Findings",
    "conflicts": "Material Conflicts",
    "evidence_gaps": "Evidence Gaps",
    "risk_areas": "Risk Areas",
    "priority_questions": "Priority Questions",
    "evidence_appendix": "Evidence Appendix",
    "glossary": "Reporting Glossary",
}
_NAV_LABELS: Final = {"all": "All sections (full report)", **_SECTION_LABELS}
_RENDERER_VERSIONS: Final = {
    "markdown": "case-report-markdown-renderer/1.0",
    "html": "case-report-html-renderer/1.0",
    "pdf": "case-report-pdf-renderer/1.0",
}
_FORMAT_LABELS: Final = {
    "markdown": "Markdown",
    "html": "HTML",
    "pdf": "PDF",
}
_MIME_TYPES: Final = {
    "markdown": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
}
_EXTENSIONS: Final = {"markdown": "md", "html": "html", "pdf": "pdf"}
_VALID_ROUTES: Final = ("assistant", "reports")
_VALID_EXPORT_FORMATS: Final = ("markdown", "html", "pdf")
_VALID_SECTION_IDS: Final = ("all", *SECTION_KEYS)


@dataclass(slots=True)
class _PresentationAudit:
    """Ephemeral presentation-conformance bookkeeping only."""

    section_order: list[str] = field(default_factory=list)
    section_item_sets: dict[str, set[str]] = field(default_factory=dict)
    section_statuses: dict[str, list[str]] = field(default_factory=dict)
    section_qualifications: dict[str, list[str]] = field(default_factory=dict)
    global_statuses: dict[str, str] = field(default_factory=dict)
    global_qualifications: dict[str, str] = field(default_factory=dict)
    statement_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)

    def start_section(self, section_id: str) -> None:
        self.section_order.append(section_id)
        self.section_item_sets.setdefault(section_id, set())
        self.section_statuses.setdefault(section_id, [])
        self.section_qualifications.setdefault(section_id, [])

    def represent(self, section_id: str, item_id: str) -> None:
        self.section_item_sets.setdefault(section_id, set()).add(item_id)

    def status(
        self,
        section_id: str,
        item_id: str,
        index: int,
        value: StatusView,
        *,
        global_item: bool = True,
    ) -> None:
        self.section_statuses.setdefault(section_id, []).append(value.raw_value)
        self.section_qualifications.setdefault(section_id, []).append(
            value.qualification_code
        )
        if not global_item:
            return
        key = f"{item_id}:{index}"
        prior_status = self.global_statuses.get(key)
        prior_qualification = self.global_qualifications.get(key)
        if prior_status is not None and prior_status != value.raw_value:
            raise ValueError("Conflicting status representation in native report preflight.")
        if (
            prior_qualification is not None
            and prior_qualification != value.qualification_code
        ):
            raise ValueError(
                "Conflicting qualification representation in native report preflight."
            )
        self.global_statuses[key] = value.raw_value
        self.global_qualifications[key] = value.qualification_code


def synchronise_report_session_state(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> bool:
    """Synchronise transient M5.5 state to the exact active report binding."""

    route = st.session_state.get("m55_main_view", "assistant")
    if route not in _VALID_ROUTES:
        st.session_state["m55_main_view"] = "assistant"
    elif "m55_main_view" not in st.session_state:
        st.session_state["m55_main_view"] = "assistant"

    if projection is None:
        binding = (active_case_id, None, None, None)
    else:
        binding = (
            active_case_id,
            projection.report_projection_id,
            projection.projection_payload_sha256,
            projection.manifest.manifest_id,
        )

    previous = (
        st.session_state.get("m55_report_case_id"),
        st.session_state.get("m55_report_projection_id"),
        st.session_state.get("m55_report_projection_payload_sha256"),
        st.session_state.get("m55_report_manifest_id"),
    )
    changed = previous != binding

    (
        st.session_state["m55_report_case_id"],
        st.session_state["m55_report_projection_id"],
        st.session_state["m55_report_projection_payload_sha256"],
        st.session_state["m55_report_manifest_id"],
    ) = binding

    if changed:
        st.session_state["m55_report_section_id"] = "report_header"
        st.session_state["m55_report_export_format"] = "markdown"
        st.session_state["m55_report_artifact_cache"] = {}
    else:
        if st.session_state.get("m55_report_section_id") not in _VALID_SECTION_IDS:
            st.session_state["m55_report_section_id"] = "report_header"
        if st.session_state.get("m55_report_export_format") not in _VALID_EXPORT_FORMATS:
            st.session_state["m55_report_export_format"] = "markdown"
        if not isinstance(st.session_state.get("m55_report_artifact_cache"), dict):
            st.session_state["m55_report_artifact_cache"] = {}

    return changed


def _all_statement_ids(projection: CaseReportProjection) -> tuple[str, ...]:
    return tuple(
        statement.report_statement_id
        for issue in projection.issues
        for element in issue.elements
        for statement in (
            *element.established_matters,
            *element.supported_matters,
            *element.not_supported_matters,
            *element.source_assertions,
        )
    )


def _all_findings_by_id(projection: CaseReportProjection) -> dict[str, FindingReport]:
    result: dict[str, FindingReport] = {}
    for issue in projection.issues:
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            existing = result.get(finding.finding_id)
            if existing is not None and existing != finding:
                raise ValueError("A finding ID resolves to inconsistent projected objects.")
            result[finding.finding_id] = finding
    return result


def _section_citation_inventory(
    projection: CaseReportProjection,
) -> dict[str, tuple[str, ...]]:
    """Derive the frozen section citation inventories from projection state."""

    return {
        "report_header": (),
        "analytical_lineage": (),
        "overall_state": (),
        "issues": tuple(
            sorted(
                {
                    citation_id
                    for issue in projection.issues
                    for finding in (*issue.direct_findings, *issue.higher_order_findings)
                    for citation_id in finding.citation_ids
                }
            )
        ),
        "chronology": tuple(
            sorted(
                {
                    citation_id
                    for event in projection.chronology
                    for citation_id in event.citation_ids
                }
            )
        ),
        "cross_issue_findings": tuple(
            sorted(
                {
                    citation_id
                    for finding in projection.cross_issue_findings
                    for citation_id in finding.citation_ids
                }
            )
        ),
        "conflicts": tuple(
            sorted(
                {
                    citation_id
                    for item in projection.conflicts
                    for citation_id in item.citation_ids
                }
            )
        ),
        "evidence_gaps": tuple(
            sorted(
                {
                    citation_id
                    for item in projection.gaps
                    for citation_id in item.citation_ids
                }
            )
        ),
        "risk_areas": tuple(
            sorted(
                {
                    citation_id
                    for item in projection.risks
                    for citation_id in item.citation_ids
                }
            )
        ),
        "priority_questions": tuple(
            sorted(
                {
                    citation_id
                    for item in projection.priority_questions
                    for citation_id in item.citation_ids
                }
            )
        ),
        "evidence_appendix": tuple(item.citation_id for item in projection.citations),
        "glossary": (),
    }


def _preflight_statuses(projection: CaseReportProjection, audit: _PresentationAudit) -> None:
    audit.status("overall_state", "overall_state", 0, projection.overall_state.state)

    cross_ids = {item.finding_id for item in projection.cross_issue_findings}
    for issue in projection.issues:
        audit.status("issues", issue.issue_analysis_id, 0, issue.position_status)
        audit.status("issues", issue.issue_analysis_id, 1, issue.confidence)
        for element in issue.elements:
            coordinate = f"{issue.issue_analysis_id}|{element.element_id}"
            audit.status("issues", coordinate, 0, element.analysis_status)
            audit.status("issues", coordinate, 1, element.analysis_confidence)
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            is_cross = finding.finding_id in cross_ids
            audit.status(
                "issues", finding.finding_id, 0, finding.status, global_item=not is_cross
            )
            audit.status(
                "issues",
                finding.finding_id,
                1,
                finding.confidence,
                global_item=not is_cross,
            )

    for event in projection.chronology:
        audit.status("chronology", event.event_id, 0, event.occurrence_status)
        audit.status("chronology", event.event_id, 1, event.timing_status)
        audit.status("chronology", event.event_id, 2, event.confidence)
        for assertion in event.assertions:
            audit.status("chronology", assertion.assertion_id, 0, assertion.occurrence_status)
            audit.status("chronology", assertion.assertion_id, 1, assertion.timing_status)
            audit.status("chronology", assertion.assertion_id, 2, assertion.confidence)

    for finding in projection.cross_issue_findings:
        audit.status(
            "cross_issue_findings", finding.finding_id, 0, finding.status
        )
        audit.status(
            "cross_issue_findings", finding.finding_id, 1, finding.confidence
        )
    for conflict in projection.conflicts:
        audit.status("conflicts", conflict.conflict_id, 0, conflict.status)
        audit.status("conflicts", conflict.conflict_id, 1, conflict.materiality)
    for gap in projection.gaps:
        audit.status("evidence_gaps", gap.gap_id, 0, gap.materiality)
    for risk in projection.risks:
        audit.status("risk_areas", risk.risk_id, 0, risk.materiality)
    for question in projection.priority_questions:
        audit.status("priority_questions", question.question_id, 0, question.priority)


def _preflight_native_presentation(projection: CaseReportProjection) -> None:
    """Prove full native presentation coverage before emitting report-body content."""

    manifest = projection.manifest
    audit = _PresentationAudit()
    for section_id in manifest.ordered_section_ids:
        if section_id not in _SECTION_LABELS:
            raise ValueError("The manifest contains an unsupported native report section.")
        audit.start_section(section_id)

    audit.represent("report_header", projection.case_header.case_id)
    audit.represent("analytical_lineage", projection.lineage.foundation_synthesis_id)
    audit.represent("overall_state", "overall_state")

    all_findings = _all_findings_by_id(projection)
    for issue in projection.issues:
        audit.represent("issues", issue.issue_analysis_id)
        for element in issue.elements:
            audit.represent("issues", f"{issue.issue_analysis_id}|{element.element_id}")
            for statement in (
                *element.established_matters,
                *element.supported_matters,
                *element.not_supported_matters,
                *element.source_assertions,
            ):
                audit.statement_ids.append(statement.report_statement_id)
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            audit.represent("issues", finding.finding_id)

    for event in projection.chronology:
        audit.represent("chronology", event.event_id)
        for assertion in event.assertions:
            audit.represent("chronology", f"{event.event_id}|{assertion.assertion_id}")

    for finding in projection.cross_issue_findings:
        audit.represent("cross_issue_findings", finding.finding_id)
    for conflict in projection.conflicts:
        audit.represent("conflicts", conflict.conflict_id)
    for gap in projection.gaps:
        audit.represent("evidence_gaps", gap.gap_id)
    for risk in projection.risks:
        audit.represent("risk_areas", risk.risk_id)
    for question in projection.priority_questions:
        audit.represent("priority_questions", question.question_id)

    citations_by_id = {item.citation_id: item for item in projection.citations}
    if len(citations_by_id) != len(projection.citations):
        raise ValueError("Citation IDs are not unique.")
    for citation_id in manifest.ordered_citation_ids:
        if citation_id not in citations_by_id:
            raise ValueError("Manifest citation does not resolve in projection catalogue.")
        audit.represent("evidence_appendix", citation_id)
        audit.citation_ids.append(citation_id)

    for entry in projection.glossary:
        audit.represent("glossary", entry.code)
        audit.section_qualifications["glossary"].append(entry.code)

    _preflight_statuses(projection, audit)

    if tuple(audit.section_order) != manifest.ordered_section_ids:
        raise ValueError("Native report section order does not match ReportManifest.")

    section_citations = _section_citation_inventory(projection)
    if set(section_citations) != set(manifest.ordered_section_ids):
        raise ValueError("Native report section citation inventory is incomplete.")

    for section in manifest.sections:
        represented = audit.section_item_sets.get(section.section_key, set())
        if represented != set(section.ordered_item_ids):
            raise ValueError(
                "Native report section "
                f"{section.section_key!r} does not account for its manifest items."
            )
        if section_citations[section.section_key] != section.ordered_citation_ids:
            raise ValueError(
                f"Native report section {section.section_key!r} changed citation inventory."
            )
        if tuple(audit.section_statuses.get(section.section_key, ())) != section.raw_status_values:
            raise ValueError(
                f"Native report section {section.section_key!r} changed raw status inventory."
            )
        if (
            tuple(audit.section_qualifications.get(section.section_key, ()))
            != section.qualification_codes
        ):
            raise ValueError(
                f"Native report section {section.section_key!r} changed qualification inventory."
            )

    if audit.global_statuses != dict(manifest.raw_status_inventory):
        raise ValueError("Native report does not account for manifest raw-status inventory.")
    if audit.global_qualifications != dict(manifest.qualification_inventory):
        raise ValueError(
            "Native report does not account for manifest qualification inventory."
        )

    statement_ids = tuple(audit.statement_ids)
    if statement_ids != _all_statement_ids(projection):
        raise ValueError("Native report does not account for every ReportStatement ID in order.")
    if len(statement_ids) != len(set(statement_ids)):
        raise ValueError("Native report statement primary representations are not unique.")
    if tuple(audit.citation_ids) != manifest.ordered_citation_ids:
        raise ValueError("Native report citation appendix does not preserve manifest order.")

    if tuple(issue.issue_analysis_id for issue in projection.issues) != manifest.ordered_issue_ids:
        raise ValueError("Native report issue source order does not match ReportManifest.")
    element_coordinates = tuple(
        f"{issue.issue_analysis_id}|{element.element_id}"
        for issue in projection.issues
        for element in issue.elements
    )
    if element_coordinates != manifest.ordered_element_coordinates:
        raise ValueError("Native report element source order does not match ReportManifest.")
    if set(manifest.ordered_finding_ids) != set(all_findings):
        raise ValueError("Native report finding inventory does not match ReportManifest.")
    if len(manifest.ordered_finding_ids) != len(set(manifest.ordered_finding_ids)):
        raise ValueError("Manifest finding order contains duplicate identities.")
    if tuple(event.event_id for event in projection.chronology) != manifest.ordered_event_ids:
        raise ValueError("Native report event source order does not match ReportManifest.")
    assertion_coordinates = tuple(
        f"{event.event_id}|{assertion.assertion_id}"
        for event in projection.chronology
        for assertion in event.assertions
    )
    if assertion_coordinates != manifest.ordered_event_assertion_coordinates:
        raise ValueError("Native report assertion source order does not match ReportManifest.")
    if tuple(item.conflict_id for item in projection.conflicts) != manifest.ordered_conflict_ids:
        raise ValueError("Native report conflict order does not match ReportManifest.")
    if tuple(item.gap_id for item in projection.gaps) != manifest.ordered_gap_ids:
        raise ValueError("Native report gap order does not match ReportManifest.")
    if tuple(item.risk_id for item in projection.risks) != manifest.ordered_risk_ids:
        raise ValueError("Native report risk order does not match ReportManifest.")
    if (
        tuple(item.question_id for item in projection.priority_questions)
        != manifest.ordered_question_ids
    ):
        raise ValueError("Native report question order does not match ReportManifest.")
    if tuple(item.citation_id for item in projection.citations) != manifest.ordered_citation_ids:
        raise ValueError("Native report citation source order does not match ReportManifest.")


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return ABSENT_VALUE_TEXT
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _field(label: str, value: Any) -> None:
    st.text(f"{label}: {_display_value(value)}")


def _values(label: str, values: Iterable[Any]) -> None:
    items = tuple(values)
    st.text(f"{label}:")
    if not items:
        st.text(EMPTY_SECTION_TEXT)
        return
    for value in items:
        st.text(f"- {_display_value(value)}")


def _coordinates(label: str, coordinates: Iterable[Iterable[Any]]) -> None:
    items = tuple(tuple(item) for item in coordinates)
    st.text(f"{label}:")
    if not items:
        st.text(EMPTY_SECTION_TEXT)
        return
    for item in items:
        st.text("- " + " | ".join(_display_value(part) for part in item))


def _status_block(title: str, value: StatusView) -> None:
    st.text(title)
    _field("Raw value", value.raw_value)
    _field("Label", value.label)
    _field("Explanation", value.explanation)
    _field("Qualification code", value.qualification_code)


def _citation_references(
    label: str,
    citation_ids: Iterable[str],
    ordinals: dict[str, int],
) -> None:
    ids = tuple(citation_ids)
    st.text(f"{label}:")
    if not ids:
        st.text(EMPTY_SECTION_TEXT)
        return
    for citation_id in ids:
        if citation_id not in ordinals:
            raise ValueError("Citation reference does not resolve in evidence appendix.")
        st.text(f"- Evidence {ordinals[citation_id]} — {citation_id}")


def _provenance(
    title: str,
    provenance: tuple[ResolvedProvenance, ...],
    citation_ordinals: dict[str, int],
) -> None:
    st.text(f"{title}:")
    if not provenance:
        st.text(EMPTY_SECTION_TEXT)
        return
    for index, item in enumerate(provenance, start=1):
        st.text(f"Provenance {index}")
        _field("Type", item.provenance_type)
        _values("Identity", item.identity)
        _field("Display label", item.display_label)
        _field("Raw role or status", item.raw_role_or_status)
        _field("Identity only", item.identity_only)
        _field("Qualification", item.qualification_text or None)
        _citation_references("Citations", item.citation_ids, citation_ordinals)


def _temporal_extent(title: str, value: TemporalExtentReport | None) -> None:
    st.text(title)
    if value is None:
        st.text(ABSENT_VALUE_TEXT)
        return
    _field("Kind", value.kind)
    _field("Start year", value.start_year)
    _field("Start month", value.start_month)
    _field("Start day", value.start_day)
    _field("Start precision", value.start_precision)
    _field("End year", value.end_year)
    _field("End month", value.end_month)
    _field("End day", value.end_day)
    _field("End precision", value.end_precision)
    _field("Display text", value.display_text)


def _statement(
    statement: ReportStatement,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.text(f"Statement {ordinal}")
    _field("Statement ID", statement.report_statement_id)
    _field("Category", statement.category)
    _field("Text", statement.text)
    _values("Evidence keys", statement.evidence_keys)
    _citation_references("Citations", statement.citation_ids, citation_ordinals)


def _statement_collection(
    title: str,
    statements: tuple[ReportStatement, ...],
    citation_ordinals: dict[str, int],
) -> None:
    st.text(title)
    if not statements:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, statement in enumerate(statements, start=1):
        _statement(statement, ordinal, citation_ordinals)


def _finding(
    finding: FindingReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    *,
    heading: str = "Finding",
) -> None:
    st.text(f"{heading} {ordinal}")
    _field("Finding ID", finding.finding_id)
    _field("Finding type", finding.finding_type)
    _field("Scope", finding.scope)
    _field("Category", finding.category)
    _field("Origin", finding.origin)
    _values("Analytical bases", finding.analytical_bases)
    _status_block("Finding status", finding.status)
    _status_block("Finding confidence", finding.confidence)
    _field("Summary", finding.summary)
    _field("Controlled explanation", finding.controlled_explanation or None)
    _values("Issue IDs", finding.issue_ids)
    _coordinates("Element coordinates", finding.element_coordinates)
    _values("Related finding IDs", finding.related_finding_ids)
    _provenance("Resolved provenance", finding.provenance, citation_ordinals)
    _citation_references("Citations", finding.citation_ids, citation_ordinals)


def _cross_issue_reference(finding: FindingReport) -> None:
    st.text("Cross-Issue Finding reference")
    _field("Finding ID", finding.finding_id)
    _field("Raw finding status", finding.status.raw_value)
    _field("Raw finding confidence", finding.confidence.raw_value)
    _field("Status qualification", finding.status.qualification_code)
    _field("Confidence qualification", finding.confidence.qualification_code)


def _element(
    element: ElementReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.text(f"Element {ordinal}")
    _field("Issue analysis ID", element.issue_analysis_id)
    _field("Element ID", element.element_id)
    _field("Element name", element.element_name)
    _field("Legal question", element.legal_question)
    _status_block("Analysis status", element.analysis_status)
    _status_block("Analysis confidence", element.analysis_confidence)
    _statement_collection(
        "Established matters", element.established_matters, citation_ordinals
    )
    _statement_collection(
        "Supported matters", element.supported_matters, citation_ordinals
    )
    _statement_collection(
        "Not-supported matters", element.not_supported_matters, citation_ordinals
    )
    _statement_collection(
        "Source assertions", element.source_assertions, citation_ordinals
    )
    _values("Unresolved matters", element.unresolved_matters)
    _field("Legal significance", element.legal_significance)
    _field("Frozen provisional analysis", element.provisional_analysis)
    _values("Linked direct finding IDs", element.linked_direct_finding_ids)
    _values(
        "Linked higher-order finding IDs", element.linked_higher_order_finding_ids
    )
    _values("Linked gap IDs", element.linked_gap_ids)
    _values("Linked risk IDs", element.linked_risk_ids)


def _issue(
    issue: IssueReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    cross_issue_ids: set[str],
) -> None:
    st.subheader(f"Issue {ordinal}")
    _field("Issue analysis ID", issue.issue_analysis_id)
    _field("Issue-definition ID", issue.issue_definition_id)
    _field("Issue-definition version", issue.issue_definition_version)
    _field("Issue name", issue.issue_name)
    _field("Original user question", issue.original_user_question)
    _field("Issue summary", issue.issue_summary)
    _status_block("Position status", issue.position_status)
    _status_block("Position confidence", issue.confidence)
    _values("Material finding IDs", issue.material_finding_ids)
    _values("Conflict IDs", issue.conflict_ids)
    _values("Gap IDs", issue.gap_ids)
    _values("Risk IDs", issue.risk_ids)

    st.text("Elements")
    if not issue.elements:
        st.text(EMPTY_SECTION_TEXT)
    for element_ordinal, element in enumerate(issue.elements, start=1):
        _element(element, element_ordinal, citation_ordinals)

    st.text("Direct Findings")
    if not issue.direct_findings:
        st.text(EMPTY_SECTION_TEXT)
    for finding_ordinal, finding in enumerate(issue.direct_findings, start=1):
        if finding.finding_id in cross_issue_ids:
            _cross_issue_reference(finding)
        else:
            _finding(finding, finding_ordinal, citation_ordinals)

    st.text("Higher-Order Findings")
    if not issue.higher_order_findings:
        st.text(EMPTY_SECTION_TEXT)
    for finding_ordinal, finding in enumerate(issue.higher_order_findings, start=1):
        if finding.finding_id in cross_issue_ids:
            _cross_issue_reference(finding)
        else:
            _finding(finding, finding_ordinal, citation_ordinals)


def _event_assertion(
    assertion: EventAssertionReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.text(f"Event Assertion {ordinal}")
    _field("Event ID", assertion.event_id)
    _field("Assertion ID", assertion.assertion_id)
    _field("Description", assertion.description)
    _field("Issue analysis ID", assertion.issue_analysis_id)
    _field("Element ID", assertion.element_id)
    _field("Source proposition index", assertion.source_proposition_index)
    _field("Evidence key", assertion.evidence_key)
    _citation_references("Citation", (assertion.citation_id,), citation_ordinals)
    _status_block("Occurrence status", assertion.occurrence_status)
    _status_block("Timing status", assertion.timing_status)
    _status_block("Confidence", assertion.confidence)
    _temporal_extent("Temporal extent", assertion.temporal_extent)
    _field("Extraction basis", assertion.extraction_basis)


def _event(
    event: EventReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.subheader(f"Event {ordinal}")
    _field("Event ID", event.event_id)
    _field("Event type", event.event_type)
    _field("Description", event.description)
    _field("Normalised event core", event.normalized_event_core)
    _temporal_extent("Date or period", event.canonical_temporal_extent)
    _status_block("Occurrence status", event.occurrence_status)
    _status_block("Timing status", event.timing_status)
    _status_block("Confidence", event.confidence)
    _values("Participants", event.participants)
    _values("Evidence keys", event.evidence_keys)
    _citation_references("Citations", event.citation_ids, citation_ordinals)
    _values("Related issue IDs", event.related_issue_ids)
    _coordinates("Related element coordinates", event.related_element_coordinates)
    st.text("Event Assertions")
    if not event.assertions:
        st.text(EMPTY_SECTION_TEXT)
    for assertion_ordinal, assertion in enumerate(event.assertions, start=1):
        _event_assertion(assertion, assertion_ordinal, citation_ordinals)


def _conflict(
    conflict: ConflictReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.subheader(f"Conflict {ordinal}")
    _field("Conflict ID", conflict.conflict_id)
    _field("Conflict type", conflict.conflict_type)
    _field("Scope", conflict.scope)
    _field("Subject", conflict.subject)
    _status_block("Status", conflict.status)
    _status_block("Materiality", conflict.materiality)
    _provenance("Side A resolved provenance", conflict.side_a, citation_ordinals)
    _provenance("Side B resolved provenance", conflict.side_b, citation_ordinals)
    _values("Related issue IDs", conflict.related_issue_ids)
    _citation_references("Citations", conflict.citation_ids, citation_ordinals)


def _gap(gap: GapReport, ordinal: int, citation_ordinals: dict[str, int]) -> None:
    st.subheader(f"Gap {ordinal}")
    _field("Gap ID", gap.gap_id)
    _field("Gap type", gap.gap_type)
    _field("Scope", gap.scope)
    _field("Issue analysis ID", gap.issue_analysis_id)
    _field("Element ID", gap.element_id)
    _field("Description", gap.description)
    _status_block("Materiality", gap.materiality)
    _field("Unresolved question", gap.unresolved_question)
    _provenance("Resolved provenance", gap.provenance, citation_ordinals)
    _citation_references("Citations", gap.citation_ids, citation_ordinals)
    _values("Related finding IDs", gap.related_finding_ids)


def _risk(risk: RiskReport, ordinal: int, citation_ordinals: dict[str, int]) -> None:
    st.subheader(f"Risk {ordinal}")
    _field("Risk ID", risk.risk_id)
    _field("Risk type", risk.risk_type)
    _field("Scope", risk.scope)
    _status_block("Materiality", risk.materiality)
    _field("Description", risk.description)
    _field("Classification explanation", risk.classification_explanation)
    _values("Basis finding IDs", risk.basis_finding_ids)
    _values("Conflict IDs", risk.conflict_ids)
    _values("Gap IDs", risk.gap_ids)
    _values("Affected issue IDs", risk.affected_issue_ids)
    _provenance("Resolved provenance", risk.provenance, citation_ordinals)
    _citation_references("Citations", risk.citation_ids, citation_ordinals)


def _question(
    question: PriorityQuestionReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
) -> None:
    st.subheader(f"Question {ordinal}")
    _field("Question ID", question.question_id)
    _field("Exact question text", question.question)
    _status_block("Priority", question.priority)
    _field("Basis type", question.basis_type)
    _values("Affected issue IDs", question.affected_issue_ids)
    _values("Affected element IDs", question.affected_element_ids)
    _values("Finding IDs", question.finding_ids)
    _values("Gap IDs", question.gap_ids)
    _values("Conflict IDs", question.conflict_ids)
    _provenance("Resolved provenance", question.provenance, citation_ordinals)
    _citation_references("Citations", question.citation_ids, citation_ordinals)


def _citation(citation: CitationRecord, ordinal: int) -> None:
    st.subheader(f"Evidence {ordinal}")
    _field("Display ordinal", ordinal)
    _field("Canonical citation ID", citation.citation_id)
    _field("Evidence key", citation.evidence_key)
    _field("Citation text", citation.citation)
    _field("Document name", citation.document_name)
    _field("Document ID", citation.document_id)
    _field("Page", citation.page)
    _field("Chunk ID", citation.chunk_id)
    _field("Date", citation.date)
    _field("Author", citation.author)
    _values("Parties", citation.parties)
    _field("Source type", citation.source_type)
    _field("Evidence status", citation.evidence_status)
    _field("Provenance type", citation.provenance_type)
    _field("Provenance basis", citation.provenance_basis)
    _field("Provenance confidence", citation.provenance_confidence)
    _coordinates("EvidenceUse coordinates", citation.evidence_use_coordinates)


def _citation_ordinals(projection: CaseReportProjection) -> dict[str, int]:
    return {
        citation_id: ordinal
        for ordinal, citation_id in enumerate(
            projection.manifest.ordered_citation_ids, start=1
        )
    }


def _render_report_header(projection: CaseReportProjection) -> None:
    st.title("LegalRAG Pro — Deterministic Case Report")
    _field("Viewer version", VIEWER_VERSION)
    _field("Output profile", OUTPUT_PROFILE)
    _field("Report projection ID", projection.report_projection_id)
    _field("Manifest ID", projection.manifest.manifest_id)
    _field("Projection payload SHA-256", projection.projection_payload_sha256)
    _field("Projection schema version", projection.schema_version)
    _field("Projector version", projection.projector_version)
    _field("Case ID", projection.case_header.case_id)
    _field("Case name", projection.case_header.case_name)
    _field("Case number", projection.case_header.case_number)
    _field("Claimant", projection.case_header.claimant)
    _field("Respondent", projection.case_header.respondent)
    _field("Case status", projection.case_header.case_status)
    _field("Court or tribunal", projection.case_header.court_or_tribunal)


def _render_lineage(projection: CaseReportProjection) -> None:
    st.header("Analytical Lineage")
    lineage = projection.lineage
    _field("Foundation synthesis ID", lineage.foundation_synthesis_id)
    _field("Foundation schema version", lineage.foundation_schema_version)
    _field("Foundation synthesiser version", lineage.foundation_synthesiser_version)
    _field("Matrices schema version", lineage.matrices_schema_version)
    _field("Matrices builder version", lineage.matrices_builder_version)
    _field("Chronology schema version", lineage.chronology_schema_version)
    _field("Chronology builder version", lineage.chronology_builder_version)
    _field("Synthesis schema version", lineage.synthesis_schema_version)
    _field("Synthesis builder version", lineage.synthesis_builder_version)
    _values("Source analysis IDs", lineage.source_analysis_ids)
    _coordinates("Issue-definition lineage", lineage.issue_definition_lineage)
    _field("Foundation SHA-256", projection.source_foundation_sha256)
    _field("Matrices SHA-256", projection.source_matrices_sha256)
    _field("Chronology SHA-256", projection.source_chronology_sha256)
    _field("Synthesis SHA-256", projection.source_synthesis_sha256)
    _field("Metadata SHA-256", projection.source_metadata_sha256)


def _render_overall(projection: CaseReportProjection) -> None:
    st.header("Overall Analytical State")
    value = projection.overall_state
    _status_block("Overall state", value.state)
    _field("Issue count", value.issue_count)
    _field("Element count", value.element_count)
    _field("Event count", value.event_count)
    _field("Finding count", value.finding_count)
    _field("Conflict count", value.conflict_count)
    _field("Gap count", value.gap_count)
    _field("Risk count", value.risk_count)
    _field("Priority-question count", value.priority_question_count)
    _field("Citation count", value.citation_count)
    _field("Count qualification", value.count_qualification)


def _render_issues(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Issues")
    if not projection.issues:
        st.text(EMPTY_SECTION_TEXT)
        return
    cross_ids = {item.finding_id for item in projection.cross_issue_findings}
    for ordinal, issue in enumerate(projection.issues, start=1):
        _issue(issue, ordinal, ordinals, cross_ids)


def _render_chronology(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Chronology")
    if not projection.chronology:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, event in enumerate(projection.chronology, start=1):
        _event(event, ordinal, ordinals)


def _render_cross_issue(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Cross-Issue Structural Findings")
    if not projection.cross_issue_findings:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, finding in enumerate(projection.cross_issue_findings, start=1):
        _finding(
            finding,
            ordinal,
            ordinals,
            heading="Cross-Issue Finding",
        )


def _render_conflicts(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Material Conflicts")
    if not projection.conflicts:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, conflict in enumerate(projection.conflicts, start=1):
        _conflict(conflict, ordinal, ordinals)


def _render_gaps(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Evidence Gaps")
    if not projection.gaps:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, gap in enumerate(projection.gaps, start=1):
        _gap(gap, ordinal, ordinals)


def _render_risks(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Risk Areas")
    if not projection.risks:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, risk in enumerate(projection.risks, start=1):
        _risk(risk, ordinal, ordinals)


def _render_questions(projection: CaseReportProjection, ordinals: dict[str, int]) -> None:
    st.header("Priority Questions")
    if not projection.priority_questions:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, question in enumerate(projection.priority_questions, start=1):
        _question(question, ordinal, ordinals)


def _render_evidence(projection: CaseReportProjection) -> None:
    st.header("Evidence Appendix")
    if not projection.manifest.ordered_citation_ids:
        st.text(EMPTY_SECTION_TEXT)
        return
    by_id = {item.citation_id: item for item in projection.citations}
    for ordinal, citation_id in enumerate(
        projection.manifest.ordered_citation_ids, start=1
    ):
        _citation(by_id[citation_id], ordinal)


def _render_glossary(projection: CaseReportProjection) -> None:
    st.header("Reporting Glossary")
    if not projection.glossary:
        st.text(EMPTY_SECTION_TEXT)
        return
    for ordinal, entry in enumerate(projection.glossary, start=1):
        st.subheader(f"Glossary Entry {ordinal}")
        _field("Code", entry.code)
        _field("Label", entry.label)
        _field("Explanation", entry.explanation)


def _render_section(
    section_id: str,
    projection: CaseReportProjection,
    citation_ordinals: dict[str, int],
) -> None:
    if section_id == "report_header":
        _render_report_header(projection)
    elif section_id == "analytical_lineage":
        _render_lineage(projection)
    elif section_id == "overall_state":
        _render_overall(projection)
    elif section_id == "issues":
        _render_issues(projection, citation_ordinals)
    elif section_id == "chronology":
        _render_chronology(projection, citation_ordinals)
    elif section_id == "cross_issue_findings":
        _render_cross_issue(projection, citation_ordinals)
    elif section_id == "conflicts":
        _render_conflicts(projection, citation_ordinals)
    elif section_id == "evidence_gaps":
        _render_gaps(projection, citation_ordinals)
    elif section_id == "risk_areas":
        _render_risks(projection, citation_ordinals)
    elif section_id == "priority_questions":
        _render_questions(projection, citation_ordinals)
    elif section_id == "evidence_appendix":
        _render_evidence(projection)
    elif section_id == "glossary":
        _render_glossary(projection)
    else:
        raise ValueError("Unsupported native report section.")


def _cache_key(
    active_case_id: str,
    projection: CaseReportProjection,
    output_format: str,
) -> tuple[str, str, str, str, str, str, str]:
    return (
        active_case_id,
        projection.report_projection_id,
        projection.projection_payload_sha256,
        projection.manifest.manifest_id,
        _RENDERER_VERSIONS[output_format],
        OUTPUT_PROFILE,
        output_format,
    )


def _validate_artifact(
    artifact: Any,
    projection: CaseReportProjection,
    output_format: str,
) -> None:
    if artifact.report_projection_id != projection.report_projection_id:
        raise ValueError("Artifact report projection ID mismatch.")
    if artifact.manifest_id != projection.manifest.manifest_id:
        raise ValueError("Artifact manifest ID mismatch.")
    if artifact.projection_payload_sha256 != projection.projection_payload_sha256:
        raise ValueError("Artifact projection payload SHA mismatch.")
    if artifact.report_manifest != projection.manifest:
        raise ValueError("Artifact report manifest mismatch.")
    if artifact.output_profile != OUTPUT_PROFILE:
        raise ValueError("Artifact output profile mismatch.")
    if artifact.renderer_version != _RENDERER_VERSIONS[output_format]:
        raise ValueError("Artifact renderer version mismatch.")


def _render_artifact(projection: CaseReportProjection, output_format: str) -> Any:
    if output_format == "markdown":
        return render_markdown_report(projection)
    if output_format == "html":
        return render_html_report(projection)
    if output_format == "pdf":
        return render_pdf_report(projection)
    raise ValueError("Unsupported report export format.")


def _artifact_bytes(artifact: Any, output_format: str) -> bytes:
    if output_format == "markdown":
        return artifact.markdown.encode("utf-8")
    if output_format == "html":
        return artifact.html.encode("utf-8")
    if output_format == "pdf":
        return artifact.pdf
    raise ValueError("Unsupported report export format.")


def _export_panel(active_case_id: str, projection: CaseReportProjection) -> None:
    st.divider()
    st.header("Report Downloads")
    output_format = st.selectbox(
        "Export format",
        options=_VALID_EXPORT_FORMATS,
        key="m55_report_export_format",
        format_func=lambda value: _FORMAT_LABELS[value],
    )
    key = _cache_key(active_case_id, projection, output_format)
    cache = st.session_state["m55_report_artifact_cache"]

    if st.button(
        f"Prepare {_FORMAT_LABELS[output_format]} download",
    ):
        try:
            artifact = _render_artifact(projection, output_format)
            _validate_artifact(artifact, projection, output_format)
            cache[key] = artifact
        except Exception as exc:
            cache.pop(key, None)
            LOGGER.error(
                "M5.5 report export preparation failed for case %s projection %s "
                "format %s error %s.",
                active_case_id,
                projection.report_projection_id,
                output_format,
                type(exc).__name__,
            )
            st.error(EXPORT_FAILURE_TEXT)

    artifact = cache.get(key)
    if artifact is None:
        return

    try:
        _validate_artifact(artifact, projection, output_format)
        data = _artifact_bytes(artifact, output_format)
    except Exception as exc:
        cache.pop(key, None)
        LOGGER.error(
            "M5.5 cached report artifact validation failed for case %s projection %s "
            "format %s error %s.",
            active_case_id,
            projection.report_projection_id,
            output_format,
            type(exc).__name__,
        )
        st.error(EXPORT_FAILURE_TEXT)
        return

    extension = _EXTENSIONS[output_format]
    filename = f"legalrag-report-{projection.report_projection_id}.{extension}"
    st.download_button(
        f"Download {_FORMAT_LABELS[output_format]}",
        data=data,
        file_name=filename,
        mime=_MIME_TYPES[output_format],
    )


def show_report_viewer(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
    *,
    provider_error: Exception | None = None,
) -> None:
    """Present one active-case-bound deterministic report using native Streamlit."""

    if st.button("Back to AI Assistant"):
        st.session_state["m55_main_view"] = "assistant"
        st.rerun()

    if active_case_id is None:
        st.info("Select an active case to view a frozen report projection.")
        return
    if provider_error is not None:
        st.error(INVALID_PROJECTION_TEXT)
        return
    if projection is None:
        st.info("No frozen report projection is available for this case.")
        return

    try:
        validate_case_report_projection(projection)
        if projection.case_header.case_id != active_case_id:
            raise ValueError("Report projection case ID does not match active case ID.")
        _preflight_native_presentation(projection)
    except Exception as exc:
        LOGGER.error(
            "M5.5 native report validation/preflight failed for case %s error %s.",
            active_case_id,
            type(exc).__name__,
        )
        st.error(INVALID_PROJECTION_TEXT)
        return

    options = ("all", *projection.manifest.ordered_section_ids)
    selected_section = st.selectbox(
        "Report section",
        options=options,
        key="m55_report_section_id",
        format_func=lambda value: _NAV_LABELS[value],
    )
    citation_ordinals = _citation_ordinals(projection)

    if selected_section == "all":
        for index, section_id in enumerate(
            projection.manifest.ordered_section_ids
        ):
            if index:
                st.divider()
            _render_section(section_id, projection, citation_ordinals)
    else:
        _render_section(selected_section, projection, citation_ordinals)

    _export_panel(active_case_id, projection)
