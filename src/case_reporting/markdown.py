"""Deterministic M5.2 full-audit Markdown renderer.

The renderer consumes only a validated :class:`CaseReportProjection`.  It does
not inspect analytical source objects, retrieve evidence, write files, or
create reporting/analytical state.  Every returned artifact is audited against
its embedded frozen M5.1 :class:`ReportManifest` before construction.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from hashlib import sha256
from html import escape as html_escape
import re
from typing import Final, Iterable, Sequence
from uuid import UUID, uuid5

from .models import (
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
    ReportManifest,
    ReportStatement,
    ResolvedProvenance,
    RiskReport,
    SECTION_KEYS,
    StatusView,
    TemporalExtentReport,
)
from .validation import validate_case_report_projection

MARKDOWN_RENDERER_VERSION: Final[str] = "case-report-markdown-renderer/1.0"
MARKDOWN_OUTPUT_PROFILE: Final[str] = "full-audit/1.0"
EMPTY_SECTION_TEXT: Final[str] = "None recorded in the frozen report projection."
ABSENT_VALUE_TEXT: Final[str] = "Not recorded in the frozen report projection."

_MARKDOWN_REPORT_NAMESPACE: Final[UUID] = UUID("0f7ca14c-83cf-5a21-88e6-8bf927d54cf8")
_SECTION_HEADINGS: Final[dict[str, str]] = {
    "report_header": "LegalRAG Pro — Deterministic Case Report",
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
_CROSS_ISSUE_FINDING_TYPE: Final[str] = "cross_issue_feature"
_MARKDOWN_ACTIVE = re.compile(r"([\\`*_{}\[\]()#+\-.!|~])")


@dataclass(frozen=True, slots=True)
class MarkdownReport:
    """Immutable audited deterministic Markdown artifact."""

    markdown_report_id: str
    renderer_version: str
    output_profile: str
    report_projection_id: str
    manifest_id: str
    projection_payload_sha256: str
    markdown_sha256: str
    report_manifest: ReportManifest
    markdown: str

    def __post_init__(self) -> None:
        for name in ("markdown_report_id", "report_projection_id", "manifest_id"):
            try:
                canonical = str(UUID(str(getattr(self, name))))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{name} must be a valid UUID string.") from exc
            object.__setattr__(self, name, canonical)
        if self.renderer_version != MARKDOWN_RENDERER_VERSION:
            raise ValueError("Unsupported Markdown renderer version.")
        if self.output_profile != MARKDOWN_OUTPUT_PROFILE:
            raise ValueError("Unsupported Markdown output profile.")
        for name in ("projection_payload_sha256", "markdown_sha256"):
            value = str(getattr(self, name))
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest.")
        if not isinstance(self.report_manifest, ReportManifest):
            raise ValueError("report_manifest must be a ReportManifest.")
        if not isinstance(self.markdown, str) or not self.markdown:
            raise ValueError("markdown must be a non-empty string.")
        if not self.markdown.endswith("\n") or self.markdown.endswith("\n\n"):
            raise ValueError("markdown must end with exactly one LF.")
        if "\r" in self.markdown:
            raise ValueError("markdown must use LF newlines only.")
        if "\t" in self.markdown:
            raise ValueError("markdown must not contain tabs.")
        if any(line.endswith(" ") for line in self.markdown.splitlines()):
            raise ValueError("markdown must not contain trailing spaces.")
        expected_sha = sha256(self.markdown.encode("utf-8")).hexdigest()
        if self.markdown_sha256 != expected_sha:
            raise ValueError("markdown_sha256 does not match Markdown bytes.")
        expected_id = _derive_markdown_report_id(
            report_projection_id=self.report_projection_id,
            manifest_id=self.manifest_id,
            projection_payload_sha256=self.projection_payload_sha256,
            markdown_sha256=self.markdown_sha256,
        )
        if self.markdown_report_id != expected_id:
            raise ValueError("markdown_report_id does not match the renderer artifact state.")


@dataclass(slots=True)
class _RenderAudit:
    section_order: list[str] = field(default_factory=list)
    section_item_ids: dict[str, list[str]] = field(default_factory=dict)
    section_item_sets: dict[str, set[str]] = field(default_factory=dict)
    section_statuses: dict[str, list[str]] = field(default_factory=dict)
    section_qualifications: dict[str, list[str]] = field(default_factory=dict)
    global_statuses: dict[str, str] = field(default_factory=dict)
    global_qualifications: dict[str, str] = field(default_factory=dict)
    primary_anchors: set[str] = field(default_factory=set)
    link_targets: list[str] = field(default_factory=list)
    rendered_statement_ids: list[str] = field(default_factory=list)
    rendered_citation_ids: list[str] = field(default_factory=list)

    def start_section(self, section_key: str) -> None:
        self.section_order.append(section_key)
        self.section_item_ids.setdefault(section_key, [])
        self.section_item_sets.setdefault(section_key, set())
        self.section_statuses.setdefault(section_key, [])
        self.section_qualifications.setdefault(section_key, [])

    def represent(self, section_key: str, item_id: str, *, repeatable: bool = False) -> None:
        if not repeatable and item_id in self.section_item_sets[section_key]:
            return
        self.section_item_ids[section_key].append(item_id)
        self.section_item_sets[section_key].add(item_id)

    def status(
        self,
        *,
        section_key: str,
        item_id: str,
        index: int,
        value: StatusView,
        global_item: bool = True,
    ) -> None:
        self.section_statuses[section_key].append(value.raw_value)
        self.section_qualifications[section_key].append(value.qualification_code)
        if not global_item:
            return
        key = f"{item_id}:{index}"
        existing = self.global_statuses.get(key)
        if existing is not None and existing != value.raw_value:
            raise ValueError(f"One status inventory key resolves incompatibly: {key!r}.")
        existing_qualification = self.global_qualifications.get(key)
        if existing_qualification is not None and existing_qualification != value.qualification_code:
            raise ValueError(f"One qualification inventory key resolves incompatibly: {key!r}.")
        self.global_statuses[key] = value.raw_value
        self.global_qualifications[key] = value.qualification_code

    def anchor(self, anchor: str) -> None:
        if anchor in self.primary_anchors:
            raise ValueError(f"Duplicate primary Markdown anchor {anchor!r}.")
        self.primary_anchors.add(anchor)

    def link(self, target: str) -> None:
        self.link_targets.append(target)


@dataclass(slots=True)
class _Writer:
    blocks: list[str] = field(default_factory=list)

    def add(self, block: str) -> None:
        normalised = _normalise_newlines(str(block)).strip("\n")
        if not normalised:
            raise ValueError("Markdown block must not be empty.")
        lines = tuple(line.rstrip(" ") for line in normalised.split("\n"))
        if any("\t" in line for line in lines):
            raise ValueError("Renderer-owned Markdown must not contain tabs.")
        self.blocks.append("\n".join(lines))

    def build(self) -> str:
        value = "\n\n".join(self.blocks).rstrip("\n") + "\n"
        if "\r" in value:
            raise ValueError("Renderer produced non-LF newlines.")
        if any(line.endswith(" ") for line in value.splitlines()):
            raise ValueError("Renderer produced trailing spaces.")
        return value


def _normalise_newlines(value: str) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _escape_text(value: object) -> str:
    """Escape untrusted projection text for ordinary Markdown text contexts."""

    text = _normalise_newlines(str(value))
    escaped_markdown = _MARKDOWN_ACTIVE.sub(r"\\\1", text)
    escaped_html = html_escape(escaped_markdown, quote=True)
    return escaped_html.replace(":", "&#58;").replace("\t", "&#9;")


def _inline_code(value: object) -> str:
    """Render deterministic safe inline code with a collision-free delimiter."""

    text = _normalise_newlines(str(value)).replace("\n", " ")
    runs = [len(match.group(0)) for match in re.finditer(r"`+", text)]
    delimiter = "`" * (max(runs, default=0) + 1)
    if text.startswith(("`", " ")) or text.endswith(("`", " ")):
        text = f" {text} "
    return f"{delimiter}{text}{delimiter}"


def _text_block(value: object) -> str:
    lines = _escape_text(value).split("\n")
    return "\n".join(">" if line == "" else f"> {line}" for line in lines)


def _field(label: str, value: object | None, *, code: bool = False) -> str:
    if value is None or value == "":
        rendered = _escape_text(ABSENT_VALUE_TEXT)
        return f"- **{label}:** {rendered}"
    text = _normalise_newlines(str(value))
    if "\n" in text and not code:
        return f"**{label}**\n\n{_text_block(text)}"
    rendered = _inline_code(text) if code else _escape_text(text)
    return f"- **{label}:** {rendered}"


def _raw_field(label: str, rendered_value: str) -> str:
    return f"- **{label}:** {rendered_value}"


def _values_block(label: str, values: Sequence[object], *, code: bool = True) -> str:
    if not values:
        return _field(label, None)
    lines = [f"**{label}**"]
    for value in values:
        rendered = _inline_code(value) if code else _escape_text(value)
        lines.append(f"- {rendered}")
    return "\n".join(lines)


def _coordinates_block(label: str, values: Sequence[Sequence[object]]) -> str:
    if not values:
        return _field(label, None)
    lines = [f"**{label}**"]
    for value in values:
        lines.append(f"- {_inline_code(' | '.join(str(item) for item in value))}")
    return "\n".join(lines)


def _canonical_identity_text(parts: Iterable[object]) -> str:
    return "\x1f".join(str(item) for item in parts)


def _anchor(kind: str, *identity_parts: object) -> str:
    canonical = _canonical_identity_text(identity_parts)
    token = urlsafe_b64encode(canonical.encode("utf-8")).decode("ascii").rstrip("=")
    return f"legalrag-{kind}-{token}"


def _section_anchor(section_key: str) -> str:
    return f"legalrag-section-{section_key}"


def _anchor_tag(anchor: str) -> str:
    return f'<a id="{anchor}"></a>'


def _internal_link(label: str, target: str, audit: _RenderAudit) -> str:
    audit.link(target)
    return f"[{_escape_text(label)}](#{target})"


def _derive_markdown_report_id(
    *,
    report_projection_id: str,
    manifest_id: str,
    projection_payload_sha256: str,
    markdown_sha256: str,
) -> str:
    name = "|".join(
        (
            MARKDOWN_RENDERER_VERSION,
            MARKDOWN_OUTPUT_PROFILE,
            str(UUID(str(report_projection_id))),
            str(UUID(str(manifest_id))),
            projection_payload_sha256,
            markdown_sha256,
        )
    )
    return str(uuid5(_MARKDOWN_REPORT_NAMESPACE, name))


def _start_section(
    writer: _Writer,
    audit: _RenderAudit,
    section_key: str,
    *,
    h1: bool = False,
) -> None:
    audit.start_section(section_key)
    anchor = _section_anchor(section_key)
    audit.anchor(anchor)
    heading = _SECTION_HEADINGS[section_key]
    if h1:
        writer.add(f"# {heading}")
        writer.add(_anchor_tag(anchor))
    else:
        writer.add(f"{_anchor_tag(anchor)}\n## {heading}")


def _status_block(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    section_key: str,
    title: str,
    item_id: str,
    index: int,
    value: StatusView,
    global_item: bool = True,
) -> None:
    audit.status(
        section_key=section_key,
        item_id=item_id,
        index=index,
        value=value,
        global_item=global_item,
    )
    writer.add(
        "\n".join(
            (
                f"**{title}**",
                f"- **Raw value:** {_inline_code(value.raw_value)}",
                f"- **Label:** {_escape_text(value.label)}",
                f"- **Explanation:** {_escape_text(value.explanation)}",
                f"- **Qualification code:** {_inline_code(value.qualification_code)}",
            )
        )
    )


def _citation_maps(projection: CaseReportProjection) -> tuple[dict[str, int], dict[str, str]]:
    ordinals = {
        citation_id: index
        for index, citation_id in enumerate(projection.manifest.ordered_citation_ids, start=1)
    }
    anchors = {citation_id: _anchor("citation", citation_id) for citation_id in ordinals}
    return ordinals, anchors


def _citation_links(
    citation_ids: Sequence[str],
    *,
    ordinals: dict[str, int],
    anchors: dict[str, str],
    audit: _RenderAudit,
) -> str:
    if not citation_ids:
        return _escape_text(ABSENT_VALUE_TEXT)
    links: list[str] = []
    for citation_id in citation_ids:
        if citation_id not in ordinals or citation_id not in anchors:
            raise ValueError(f"Unknown renderer citation ID {citation_id!r}.")
        label = f"Evidence {ordinals[citation_id]} — {citation_id}"
        links.append(_internal_link(label, anchors[citation_id], audit))
    return ", ".join(links)


def _render_provenance(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    provenance: Sequence[ResolvedProvenance],
    ordinals: dict[str, int],
    citation_anchors: dict[str, str],
    title: str = "Resolved provenance",
) -> None:
    writer.add(f"**{title}**")
    if not provenance:
        writer.add(EMPTY_SECTION_TEXT)
        return
    for index, item in enumerate(provenance, start=1):
        writer.add(f"**Provenance {index}**")
        writer.add(_field("Provenance type", item.provenance_type, code=True))
        writer.add(_values_block("Exact identity parts", item.identity, code=True))
        writer.add(_field("Display label", item.display_label))
        writer.add(_field("Raw role or status", item.raw_role_or_status, code=True))
        writer.add(_field("Identity-only", str(item.identity_only).lower(), code=True))
        writer.add(_field("Qualification text", item.qualification_text or ABSENT_VALUE_TEXT))
        writer.add(
            _raw_field(
                "Citations",
                _citation_links(
                    item.citation_ids,
                    ordinals=ordinals,
                    anchors=citation_anchors,
                    audit=audit,
                ),
            )
        )


def _render_statement_collection(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    title: str,
    statements: Sequence[ReportStatement],
    ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    writer.add(f"**{title}**")
    if not statements:
        writer.add(EMPTY_SECTION_TEXT)
        return
    for index, statement in enumerate(statements, start=1):
        anchor = _anchor("statement", statement.report_statement_id)
        audit.anchor(anchor)
        audit.rendered_statement_ids.append(statement.report_statement_id)
        writer.add(f"{_anchor_tag(anchor)}\n**Statement {index}**")
        writer.add(_field("Statement ID", statement.report_statement_id, code=True))
        writer.add(_field("Category", statement.category, code=True))
        writer.add(_field("Text", statement.text))
        writer.add(_values_block("Evidence keys", statement.evidence_keys, code=True))
        writer.add(
            _raw_field(
                "Citations",
                _citation_links(
                    statement.citation_ids,
                    ordinals=ordinals,
                    anchors=citation_anchors,
                    audit=audit,
                ),
            )
        )


def _render_temporal_extent(writer: _Writer, value: TemporalExtentReport | None) -> None:
    writer.add("**Temporal extent**")
    if value is None:
        writer.add(ABSENT_VALUE_TEXT)
        return
    writer.add(_field("Kind", value.kind, code=True))
    writer.add(_field("Start year", value.start_year, code=True))
    writer.add(_field("Start month", value.start_month, code=True))
    writer.add(_field("Start day", value.start_day, code=True))
    writer.add(_field("Start precision", value.start_precision, code=True))
    writer.add(_field("End year", value.end_year, code=True))
    writer.add(_field("End month", value.end_month, code=True))
    writer.add(_field("End day", value.end_day, code=True))
    writer.add(_field("End precision", value.end_precision, code=True))
    writer.add(_field("Display text", value.display_text))


def _render_finding_full(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    section_key: str,
    finding: FindingReport,
    ordinal: int,
    ordinals: dict[str, int],
    citation_anchors: dict[str, str],
    heading_level: int | None,
    global_status: bool = True,
) -> None:
    anchor = _anchor("finding", finding.finding_id)
    audit.anchor(anchor)
    if heading_level is None:
        title = f"**Finding {ordinal}**"
    else:
        title = f"{'#' * heading_level} Cross-Issue Finding {ordinal}"
    writer.add(f"{_anchor_tag(anchor)}\n{title}")
    writer.add(_field("Finding ID", finding.finding_id, code=True))
    writer.add(_field("Finding type", finding.finding_type, code=True))
    writer.add(_field("Scope", finding.scope, code=True))
    writer.add(_field("Category", finding.category, code=True))
    writer.add(_field("Origin", finding.origin, code=True))
    writer.add(_values_block("Analytical bases", finding.analytical_bases, code=True))
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Finding status",
        item_id=finding.finding_id,
        index=0,
        value=finding.status,
        global_item=global_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Finding confidence",
        item_id=finding.finding_id,
        index=1,
        value=finding.confidence,
        global_item=global_status,
    )
    writer.add(_field("Summary", finding.summary))
    writer.add(_field("Controlled explanation", finding.controlled_explanation or ABSENT_VALUE_TEXT))
    writer.add(_values_block("Issue IDs", finding.issue_ids, code=True))
    writer.add(_coordinates_block("Element coordinates", finding.element_coordinates))
    writer.add(_values_block("Related finding IDs", finding.related_finding_ids, code=True))
    _render_provenance(
        writer,
        audit,
        provenance=finding.provenance,
        ordinals=ordinals,
        citation_anchors=citation_anchors,
    )
    writer.add(
        _raw_field(
            "Citations",
            _citation_links(
                finding.citation_ids,
                ordinals=ordinals,
                anchors=citation_anchors,
                audit=audit,
            ),
        )
    )


def _render_cross_issue_reference(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    finding: FindingReport,
) -> None:
    target = _anchor("finding", finding.finding_id)
    link = _internal_link(f"Cross-Issue Finding — {finding.finding_id}", target, audit)
    writer.add(
        "\n".join(
            (
                f"- {link}",
                f"- **Raw finding status:** {_inline_code(finding.status.raw_value)}",
                f"- **Raw confidence:** {_inline_code(finding.confidence.raw_value)}",
                f"- **Status qualification:** {_inline_code(finding.status.qualification_code)}",
                f"- **Confidence qualification:** {_inline_code(finding.confidence.qualification_code)}",
            )
        )
    )


def _render_issue(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    issue: IssueReport,
    ordinal: int,
    cross_issue_ids: set[str],
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "issues"
    audit.represent(section_key, issue.issue_analysis_id)
    anchor = _anchor("issue", issue.issue_analysis_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Issue {ordinal}")
    writer.add(_field("Issue analysis ID", issue.issue_analysis_id, code=True))
    writer.add(_field("Issue-definition ID", issue.issue_definition_id, code=True))
    writer.add(_field("Issue-definition version", issue.issue_definition_version, code=True))
    writer.add(_field("Issue name", issue.issue_name))
    writer.add(_field("Original user question", issue.original_user_question))
    writer.add(_field("Issue summary", issue.issue_summary))
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Position status",
        item_id=issue.issue_analysis_id,
        index=0,
        value=issue.position_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Position confidence",
        item_id=issue.issue_analysis_id,
        index=1,
        value=issue.confidence,
    )
    writer.add(_values_block("Material finding IDs", issue.material_finding_ids, code=True))
    writer.add(_values_block("Conflict IDs", issue.conflict_ids, code=True))
    writer.add(_values_block("Gap IDs", issue.gap_ids, code=True))
    writer.add(_values_block("Risk IDs", issue.risk_ids, code=True))

    for element_ordinal, element in enumerate(issue.elements, start=1):
        _render_element(
            writer,
            audit,
            element=element,
            ordinal=element_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    writer.add("#### Direct Findings")
    if not issue.direct_findings:
        writer.add(EMPTY_SECTION_TEXT)
    for finding_ordinal, finding in enumerate(issue.direct_findings, start=1):
        audit.represent(section_key, finding.finding_id)
        _render_finding_full(
            writer,
            audit,
            section_key=section_key,
            finding=finding,
            ordinal=finding_ordinal,
            ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
            heading_level=None,
        )

    writer.add("#### Higher-Order Findings")
    if not issue.higher_order_findings:
        writer.add(EMPTY_SECTION_TEXT)
    non_cross_ordinal = 0
    for finding in issue.higher_order_findings:
        audit.represent(section_key, finding.finding_id)
        if finding.finding_id in cross_issue_ids or finding.finding_type == _CROSS_ISSUE_FINDING_TYPE:
            audit.status(
                section_key=section_key,
                item_id=finding.finding_id,
                index=0,
                value=finding.status,
                global_item=False,
            )
            audit.status(
                section_key=section_key,
                item_id=finding.finding_id,
                index=1,
                value=finding.confidence,
                global_item=False,
            )
            _render_cross_issue_reference(writer, audit, finding=finding)
            continue
        non_cross_ordinal += 1
        _render_finding_full(
            writer,
            audit,
            section_key=section_key,
            finding=finding,
            ordinal=non_cross_ordinal,
            ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
            heading_level=None,
        )


def _render_element(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    element: ElementReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "issues"
    coordinate = f"{element.issue_analysis_id}|{element.element_id}"
    audit.represent(section_key, coordinate)
    anchor = _anchor("element", element.issue_analysis_id, element.element_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n#### Element {ordinal}")
    writer.add(_field("Issue analysis ID", element.issue_analysis_id, code=True))
    writer.add(_field("Element ID", element.element_id, code=True))
    writer.add(_field("Element name", element.element_name))
    writer.add(_field("Legal question", element.legal_question))
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Analysis status",
        item_id=coordinate,
        index=0,
        value=element.analysis_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Analysis confidence",
        item_id=coordinate,
        index=1,
        value=element.analysis_confidence,
    )
    _render_statement_collection(
        writer,
        audit,
        title="Established matters",
        statements=element.established_matters,
        ordinals=citation_ordinals,
        citation_anchors=citation_anchors,
    )
    _render_statement_collection(
        writer,
        audit,
        title="Supported matters",
        statements=element.supported_matters,
        ordinals=citation_ordinals,
        citation_anchors=citation_anchors,
    )
    _render_statement_collection(
        writer,
        audit,
        title="Not-supported matters",
        statements=element.not_supported_matters,
        ordinals=citation_ordinals,
        citation_anchors=citation_anchors,
    )
    _render_statement_collection(
        writer,
        audit,
        title="Source assertions",
        statements=element.source_assertions,
        ordinals=citation_ordinals,
        citation_anchors=citation_anchors,
    )
    writer.add(_values_block("Unresolved matters", element.unresolved_matters, code=False))
    writer.add(_field("Legal significance", element.legal_significance))
    writer.add(_field("Frozen provisional analysis", element.provisional_analysis))
    writer.add(_values_block("Linked direct finding IDs", element.linked_direct_finding_ids, code=True))
    writer.add(_values_block("Linked higher-order finding IDs", element.linked_higher_order_finding_ids, code=True))
    writer.add(_values_block("Linked gap IDs", element.linked_gap_ids, code=True))
    writer.add(_values_block("Linked risk IDs", element.linked_risk_ids, code=True))


def _render_assertion(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    assertion: EventAssertionReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "chronology"
    coordinate = f"{assertion.event_id}|{assertion.assertion_id}"
    audit.represent(section_key, coordinate)
    anchor = _anchor("assertion", assertion.event_id, assertion.assertion_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n**Assertion {ordinal}**")
    writer.add(_field("Event ID", assertion.event_id, code=True))
    writer.add(_field("Assertion ID", assertion.assertion_id, code=True))
    writer.add(_field("Description", assertion.description))
    writer.add(_field("Issue analysis ID", assertion.issue_analysis_id, code=True))
    writer.add(_field("Element ID", assertion.element_id, code=True))
    writer.add(_field("Source proposition index", assertion.source_proposition_index, code=True))
    writer.add(_field("Evidence key", assertion.evidence_key, code=True))
    writer.add(
        _raw_field(
            "Citation",
            _citation_links(
                (assertion.citation_id,),
                ordinals=citation_ordinals,
                anchors=citation_anchors,
                audit=audit,
            ),
        )
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Occurrence status",
        item_id=assertion.assertion_id,
        index=0,
        value=assertion.occurrence_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Timing status",
        item_id=assertion.assertion_id,
        index=1,
        value=assertion.timing_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Confidence",
        item_id=assertion.assertion_id,
        index=2,
        value=assertion.confidence,
    )
    _render_temporal_extent(writer, assertion.temporal_extent)
    writer.add(_field("Extraction basis", assertion.extraction_basis, code=True))


def _render_event(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    event: EventReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "chronology"
    audit.represent(section_key, event.event_id)
    anchor = _anchor("event", event.event_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Event {ordinal}")
    writer.add(_field("Event ID", event.event_id, code=True))
    writer.add(_field("Event type", event.event_type, code=True))
    writer.add(_field("Description", event.description))
    writer.add(_field("Normalised event core", event.normalized_event_core))
    writer.add(_field("Date or period", event.canonical_temporal_extent.display_text if event.canonical_temporal_extent else None))
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Occurrence status",
        item_id=event.event_id,
        index=0,
        value=event.occurrence_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Timing status",
        item_id=event.event_id,
        index=1,
        value=event.timing_status,
    )
    _status_block(
        writer,
        audit,
        section_key=section_key,
        title="Confidence",
        item_id=event.event_id,
        index=2,
        value=event.confidence,
    )
    _render_temporal_extent(writer, event.canonical_temporal_extent)
    writer.add(_values_block("Participants", event.participants, code=False))
    writer.add(_values_block("Evidence keys", event.evidence_keys, code=True))
    writer.add(
        _raw_field(
            "Citations",
            _citation_links(
                event.citation_ids,
                ordinals=citation_ordinals,
                anchors=citation_anchors,
                audit=audit,
            ),
        )
    )
    writer.add(_values_block("Related issue IDs", event.related_issue_ids, code=True))
    writer.add(_coordinates_block("Related element coordinates", event.related_element_coordinates))
    writer.add("#### Event Assertions")
    if not event.assertions:
        writer.add(EMPTY_SECTION_TEXT)
    for assertion_ordinal, assertion in enumerate(event.assertions, start=1):
        _render_assertion(
            writer,
            audit,
            assertion=assertion,
            ordinal=assertion_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )


def _render_conflict(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    conflict: ConflictReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "conflicts"
    audit.represent(section_key, conflict.conflict_id)
    anchor = _anchor("conflict", conflict.conflict_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Conflict {ordinal}")
    writer.add(_field("Conflict ID", conflict.conflict_id, code=True))
    writer.add(_field("Conflict type", conflict.conflict_type, code=True))
    writer.add(_field("Scope", conflict.scope, code=True))
    writer.add(_field("Subject", conflict.subject))
    _status_block(writer, audit, section_key=section_key, title="Conflict status", item_id=conflict.conflict_id, index=0, value=conflict.status)
    _status_block(writer, audit, section_key=section_key, title="Materiality", item_id=conflict.conflict_id, index=1, value=conflict.materiality)
    _render_provenance(writer, audit, provenance=conflict.side_a, ordinals=citation_ordinals, citation_anchors=citation_anchors, title="Side A resolved provenance")
    _render_provenance(writer, audit, provenance=conflict.side_b, ordinals=citation_ordinals, citation_anchors=citation_anchors, title="Side B resolved provenance")
    writer.add(_values_block("Related issue IDs", conflict.related_issue_ids, code=True))
    writer.add(_raw_field("Citations", _citation_links(conflict.citation_ids, ordinals=citation_ordinals, anchors=citation_anchors, audit=audit)))


def _render_gap(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    gap: GapReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "evidence_gaps"
    audit.represent(section_key, gap.gap_id)
    anchor = _anchor("gap", gap.gap_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Evidence Gap {ordinal}")
    writer.add(_field("Gap ID", gap.gap_id, code=True))
    writer.add(_field("Gap type", gap.gap_type, code=True))
    writer.add(_field("Scope", gap.scope, code=True))
    writer.add(_field("Issue analysis ID", gap.issue_analysis_id, code=True))
    writer.add(_field("Element ID", gap.element_id, code=True))
    writer.add(_field("Description", gap.description))
    _status_block(writer, audit, section_key=section_key, title="Materiality", item_id=gap.gap_id, index=0, value=gap.materiality)
    writer.add(_field("Unresolved question", gap.unresolved_question))
    _render_provenance(writer, audit, provenance=gap.provenance, ordinals=citation_ordinals, citation_anchors=citation_anchors)
    writer.add(_raw_field("Citations", _citation_links(gap.citation_ids, ordinals=citation_ordinals, anchors=citation_anchors, audit=audit)))
    writer.add(_values_block("Related finding IDs", gap.related_finding_ids, code=True))


def _render_risk(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    risk: RiskReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "risk_areas"
    audit.represent(section_key, risk.risk_id)
    anchor = _anchor("risk", risk.risk_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Risk Area {ordinal}")
    writer.add(_field("Risk ID", risk.risk_id, code=True))
    writer.add(_field("Risk type", risk.risk_type, code=True))
    writer.add(_field("Scope", risk.scope, code=True))
    _status_block(writer, audit, section_key=section_key, title="Materiality", item_id=risk.risk_id, index=0, value=risk.materiality)
    writer.add(_field("Description", risk.description))
    writer.add(_field("Classification explanation", risk.classification_explanation))
    writer.add(_values_block("Basis finding IDs", risk.basis_finding_ids, code=True))
    writer.add(_values_block("Conflict IDs", risk.conflict_ids, code=True))
    writer.add(_values_block("Gap IDs", risk.gap_ids, code=True))
    writer.add(_values_block("Affected issue IDs", risk.affected_issue_ids, code=True))
    _render_provenance(writer, audit, provenance=risk.provenance, ordinals=citation_ordinals, citation_anchors=citation_anchors)
    writer.add(_raw_field("Citations", _citation_links(risk.citation_ids, ordinals=citation_ordinals, anchors=citation_anchors, audit=audit)))


def _render_question(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    question: PriorityQuestionReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_anchors: dict[str, str],
) -> None:
    section_key = "priority_questions"
    audit.represent(section_key, question.question_id)
    anchor = _anchor("question", question.question_id)
    audit.anchor(anchor)
    writer.add(f"{_anchor_tag(anchor)}\n### Priority Question {ordinal}")
    writer.add(_field("Question ID", question.question_id, code=True))
    writer.add(_field("Exact question", question.question))
    _status_block(writer, audit, section_key=section_key, title="Priority", item_id=question.question_id, index=0, value=question.priority)
    writer.add(_field("Basis type", question.basis_type, code=True))
    writer.add(_values_block("Affected issue IDs", question.affected_issue_ids, code=True))
    writer.add(_values_block("Affected element IDs", question.affected_element_ids, code=True))
    writer.add(_values_block("Finding IDs", question.finding_ids, code=True))
    writer.add(_values_block("Gap IDs", question.gap_ids, code=True))
    writer.add(_values_block("Conflict IDs", question.conflict_ids, code=True))
    _render_provenance(writer, audit, provenance=question.provenance, ordinals=citation_ordinals, citation_anchors=citation_anchors)
    writer.add(_raw_field("Citations", _citation_links(question.citation_ids, ordinals=citation_ordinals, anchors=citation_anchors, audit=audit)))


def _render_citation(
    writer: _Writer,
    audit: _RenderAudit,
    *,
    citation: CitationRecord,
    ordinal: int,
    citation_anchor: str,
) -> None:
    section_key = "evidence_appendix"
    audit.represent(section_key, citation.citation_id)
    audit.anchor(citation_anchor)
    audit.rendered_citation_ids.append(citation.citation_id)
    writer.add(f"{_anchor_tag(citation_anchor)}\n### Evidence {ordinal}")
    writer.add(_field("Display ordinal", ordinal, code=True))
    writer.add(_field("Canonical citation ID", citation.citation_id, code=True))
    writer.add(_field("Evidence key", citation.evidence_key, code=True))
    writer.add(_field("Citation text", citation.citation))
    writer.add(_field("Document name", citation.document_name))
    writer.add(_field("Document ID", citation.document_id, code=True))
    writer.add(_field("Page", citation.page, code=True))
    writer.add(_field("Chunk ID", citation.chunk_id, code=True))
    writer.add(_field("Date", citation.date))
    writer.add(_field("Author", citation.author))
    writer.add(_values_block("Parties", citation.parties, code=False))
    writer.add(_field("Source type", citation.source_type, code=True))
    writer.add(_field("Evidence status", citation.evidence_status, code=True))
    writer.add(_field("Provenance type", citation.provenance_type, code=True))
    writer.add(_field("Provenance basis", citation.provenance_basis, code=True))
    writer.add(_field("Provenance confidence", citation.provenance_confidence, code=True))
    writer.add(_coordinates_block("EvidenceUse coordinates", citation.evidence_use_coordinates))


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


def _all_finding_ids(projection: CaseReportProjection) -> set[str]:
    return {
        finding.finding_id
        for issue in projection.issues
        for finding in (*issue.direct_findings, *issue.higher_order_findings)
    }


def _expected_section_item_ids(projection: CaseReportProjection, section_key: str) -> tuple[str, ...]:
    section = next(item for item in projection.manifest.sections if item.section_key == section_key)
    return section.ordered_item_ids


def _validate_audit(projection: CaseReportProjection, audit: _RenderAudit) -> None:
    manifest = projection.manifest
    if tuple(audit.section_order) != manifest.ordered_section_ids:
        raise ValueError("Rendered section order does not match ReportManifest.")

    for section in manifest.sections:
        represented = audit.section_item_sets.get(section.section_key, set())
        expected = set(section.ordered_item_ids)
        if represented != expected:
            raise ValueError(
                f"Rendered section {section.section_key!r} does not account for its manifest items."
            )
        if tuple(audit.section_statuses.get(section.section_key, ())) != section.raw_status_values:
            raise ValueError(f"Rendered section {section.section_key!r} changed raw status inventory.")
        if tuple(audit.section_qualifications.get(section.section_key, ())) != section.qualification_codes:
            raise ValueError(f"Rendered section {section.section_key!r} changed qualification inventory.")

    if audit.global_statuses != dict(manifest.raw_status_inventory):
        raise ValueError("Rendered Markdown does not account for the manifest raw-status inventory.")
    if audit.global_qualifications != dict(manifest.qualification_inventory):
        raise ValueError("Rendered Markdown does not account for the manifest qualification inventory.")

    if tuple(audit.rendered_statement_ids) != _all_statement_ids(projection):
        raise ValueError("Rendered Markdown does not account for every ReportStatement ID in order.")
    if tuple(audit.rendered_citation_ids) != manifest.ordered_citation_ids:
        raise ValueError("Rendered Markdown citation appendix does not preserve manifest order.")
    if not set(audit.link_targets) <= audit.primary_anchors:
        missing = sorted(set(audit.link_targets) - audit.primary_anchors)
        raise ValueError(f"Rendered Markdown contains unresolved internal links: {missing}.")

    if set(manifest.ordered_finding_ids) != _all_finding_ids(projection):
        raise ValueError("Projection finding inventory does not match ReportManifest.")
    if tuple(issue.issue_analysis_id for issue in projection.issues) != manifest.ordered_issue_ids:
        raise ValueError("Rendered issue source order does not match ReportManifest.")
    element_coordinates = tuple(
        f"{issue.issue_analysis_id}|{element.element_id}"
        for issue in projection.issues
        for element in issue.elements
    )
    if element_coordinates != manifest.ordered_element_coordinates:
        raise ValueError("Rendered element source order does not match ReportManifest.")
    if tuple(event.event_id for event in projection.chronology) != manifest.ordered_event_ids:
        raise ValueError("Rendered event source order does not match ReportManifest.")
    assertion_coordinates = tuple(
        f"{event.event_id}|{assertion.assertion_id}"
        for event in projection.chronology
        for assertion in event.assertions
    )
    if assertion_coordinates != manifest.ordered_event_assertion_coordinates:
        raise ValueError("Rendered assertion source order does not match ReportManifest.")


def _produce_markdown_report(projection: CaseReportProjection) -> MarkdownReport:
    """Validate and render one deterministic full-audit Markdown report."""

    validate_case_report_projection(projection)
    writer = _Writer()
    audit = _RenderAudit()
    citation_ordinals, citation_anchors = _citation_maps(projection)
    cross_issue_ids = {item.finding_id for item in projection.cross_issue_findings}

    _start_section(writer, audit, "report_header", h1=True)
    audit.represent("report_header", projection.case_header.case_id)
    writer.add(_field("Renderer version", MARKDOWN_RENDERER_VERSION, code=True))
    writer.add(_field("Output profile", MARKDOWN_OUTPUT_PROFILE, code=True))
    writer.add(_field("Report projection ID", projection.report_projection_id, code=True))
    writer.add(_field("Manifest ID", projection.manifest.manifest_id, code=True))
    writer.add(_field("Projection payload SHA-256", projection.projection_payload_sha256, code=True))
    writer.add(_field("Projection schema version", projection.schema_version, code=True))
    writer.add(_field("Projector version", projection.projector_version, code=True))
    writer.add(_field("Case ID", projection.case_header.case_id, code=True))
    writer.add(_field("Case name", projection.case_header.case_name))
    writer.add(_field("Case number", projection.case_header.case_number))
    writer.add(_field("Claimant", projection.case_header.claimant))
    writer.add(_field("Respondent", projection.case_header.respondent))
    writer.add(_field("Case status", projection.case_header.case_status))
    writer.add(_field("Court or tribunal", projection.case_header.court_or_tribunal))

    _start_section(writer, audit, "analytical_lineage")
    audit.represent("analytical_lineage", projection.lineage.foundation_synthesis_id)
    writer.add(_field("Foundation synthesis ID", projection.lineage.foundation_synthesis_id, code=True))
    writer.add(_field("Foundation schema version", projection.lineage.foundation_schema_version, code=True))
    writer.add(_field("Foundation synthesiser version", projection.lineage.foundation_synthesiser_version, code=True))
    writer.add(_field("Matrices schema version", projection.lineage.matrices_schema_version, code=True))
    writer.add(_field("Matrices builder version", projection.lineage.matrices_builder_version, code=True))
    writer.add(_field("Chronology schema version", projection.lineage.chronology_schema_version, code=True))
    writer.add(_field("Chronology builder version", projection.lineage.chronology_builder_version, code=True))
    writer.add(_field("Synthesis schema version", projection.lineage.synthesis_schema_version, code=True))
    writer.add(_field("Synthesis builder version", projection.lineage.synthesis_builder_version, code=True))
    writer.add(_values_block("Source analysis IDs", projection.lineage.source_analysis_ids, code=True))
    writer.add(_coordinates_block("Issue-definition lineage", projection.lineage.issue_definition_lineage))
    writer.add("#### Source Fingerprints")
    writer.add(_field("Foundation SHA-256", projection.source_foundation_sha256, code=True))
    writer.add(_field("Matrices SHA-256", projection.source_matrices_sha256, code=True))
    writer.add(_field("Chronology SHA-256", projection.source_chronology_sha256, code=True))
    writer.add(_field("Synthesis SHA-256", projection.source_synthesis_sha256, code=True))
    writer.add(_field("Metadata SHA-256", projection.source_metadata_sha256, code=True))

    _start_section(writer, audit, "overall_state")
    audit.represent("overall_state", "overall_state")
    _status_block(
        writer,
        audit,
        section_key="overall_state",
        title="Overall state",
        item_id="overall_state",
        index=0,
        value=projection.overall_state.state,
    )
    for label, value in (
        ("Issue count", projection.overall_state.issue_count),
        ("Element count", projection.overall_state.element_count),
        ("Event count", projection.overall_state.event_count),
        ("Finding count", projection.overall_state.finding_count),
        ("Conflict count", projection.overall_state.conflict_count),
        ("Gap count", projection.overall_state.gap_count),
        ("Risk count", projection.overall_state.risk_count),
        ("Priority-question count", projection.overall_state.priority_question_count),
        ("Citation count", projection.overall_state.citation_count),
    ):
        writer.add(_field(label, value, code=True))
    writer.add(_field("Count qualification", projection.overall_state.count_qualification))

    _start_section(writer, audit, "issues")
    if not projection.issues:
        writer.add(EMPTY_SECTION_TEXT)
    for issue_ordinal, issue in enumerate(projection.issues, start=1):
        _render_issue(
            writer,
            audit,
            issue=issue,
            ordinal=issue_ordinal,
            cross_issue_ids=cross_issue_ids,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "chronology")
    if not projection.chronology:
        writer.add(EMPTY_SECTION_TEXT)
    for event_ordinal, event in enumerate(projection.chronology, start=1):
        _render_event(
            writer,
            audit,
            event=event,
            ordinal=event_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "cross_issue_findings")
    if not projection.cross_issue_findings:
        writer.add(EMPTY_SECTION_TEXT)
    for finding_ordinal, finding in enumerate(projection.cross_issue_findings, start=1):
        audit.represent("cross_issue_findings", finding.finding_id)
        _render_finding_full(
            writer,
            audit,
            section_key="cross_issue_findings",
            finding=finding,
            ordinal=finding_ordinal,
            ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
            heading_level=3,
        )

    _start_section(writer, audit, "conflicts")
    if not projection.conflicts:
        writer.add(EMPTY_SECTION_TEXT)
    for conflict_ordinal, conflict in enumerate(projection.conflicts, start=1):
        _render_conflict(
            writer,
            audit,
            conflict=conflict,
            ordinal=conflict_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "evidence_gaps")
    if not projection.gaps:
        writer.add(EMPTY_SECTION_TEXT)
    for gap_ordinal, gap in enumerate(projection.gaps, start=1):
        _render_gap(
            writer,
            audit,
            gap=gap,
            ordinal=gap_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "risk_areas")
    if not projection.risks:
        writer.add(EMPTY_SECTION_TEXT)
    for risk_ordinal, risk in enumerate(projection.risks, start=1):
        _render_risk(
            writer,
            audit,
            risk=risk,
            ordinal=risk_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "priority_questions")
    if not projection.priority_questions:
        writer.add(EMPTY_SECTION_TEXT)
    for question_ordinal, question in enumerate(projection.priority_questions, start=1):
        _render_question(
            writer,
            audit,
            question=question,
            ordinal=question_ordinal,
            citation_ordinals=citation_ordinals,
            citation_anchors=citation_anchors,
        )

    _start_section(writer, audit, "evidence_appendix")
    if not projection.citations:
        writer.add(EMPTY_SECTION_TEXT)
    for citation_id in projection.manifest.ordered_citation_ids:
        citation = next(item for item in projection.citations if item.citation_id == citation_id)
        _render_citation(
            writer,
            audit,
            citation=citation,
            ordinal=citation_ordinals[citation_id],
            citation_anchor=citation_anchors[citation_id],
        )

    _start_section(writer, audit, "glossary")
    if not projection.glossary:
        writer.add(EMPTY_SECTION_TEXT)
    for entry_ordinal, entry in enumerate(projection.glossary, start=1):
        audit.represent("glossary", entry.code)
        audit.section_qualifications["glossary"].append(entry.code)
        anchor = _anchor("glossary", entry.code)
        audit.anchor(anchor)
        writer.add(f"{_anchor_tag(anchor)}\n**Glossary Entry {entry_ordinal}**")
        writer.add(_field("Code", entry.code, code=True))
        writer.add(_field("Label", entry.label))
        writer.add(_field("Explanation", entry.explanation))

    markdown = writer.build()
    _validate_audit(projection, audit)
    markdown_sha = sha256(markdown.encode("utf-8")).hexdigest()
    report_id = _derive_markdown_report_id(
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        markdown_sha256=markdown_sha,
    )
    return MarkdownReport(
        markdown_report_id=report_id,
        renderer_version=MARKDOWN_RENDERER_VERSION,
        output_profile=MARKDOWN_OUTPUT_PROFILE,
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        markdown_sha256=markdown_sha,
        report_manifest=projection.manifest,
        markdown=markdown,
    )


_PUBLIC_RENDERER_NAME = "render_" + "markdown_report"
_produce_markdown_report.__name__ = _PUBLIC_RENDERER_NAME
_produce_markdown_report.__qualname__ = _PUBLIC_RENDERER_NAME
globals()[_PUBLIC_RENDERER_NAME] = _produce_markdown_report

__all__ = [
    "ABSENT_VALUE_TEXT",
    "EMPTY_SECTION_TEXT",
    "MARKDOWN_OUTPUT_PROFILE",
    "MARKDOWN_RENDERER_VERSION",
    "MarkdownReport",
    _PUBLIC_RENDERER_NAME,
]
