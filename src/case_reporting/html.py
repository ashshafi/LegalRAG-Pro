"""Deterministic M5.3 full-audit standalone HTML renderer.

The renderer consumes only a validated :class:`CaseReportProjection`. It does
not inspect analytical source objects, parse Markdown, retrieve evidence, write
files, or create reporting/analytical state. Every returned artifact is audited
against its embedded frozen M5.1 :class:`ReportManifest` before construction.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from hashlib import sha256
from html import escape as html_escape
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

HTML_RENDERER_VERSION: Final[str] = "case-report-html-renderer/1.0"
HTML_OUTPUT_PROFILE: Final[str] = "full-audit/1.0"
EMPTY_SECTION_TEXT: Final[str] = "None recorded in the frozen report projection."
ABSENT_VALUE_TEXT: Final[str] = "Not recorded in the frozen report projection."

_HTML_REPORT_NAMESPACE: Final[UUID] = UUID("9b67c871-cdc0-54d1-9d55-2609f8537f48")
_CROSS_ISSUE_FINDING_TYPE: Final[str] = "cross_issue_feature"
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
        "glossary",
    }
)
_FORBIDDEN_CONTROLS: Final[frozenset[int]] = frozenset(
    {*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20), 0x7F}
)
_STYLESHEET: Final[tuple[str, ...]] = (
    ":root { color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; line-height: 1.5; }",
    "body { margin: 0; background: #ffffff; color: #111111; }",
    ".skip-link { position: absolute; left: 0.5rem; top: -4rem; padding: 0.5rem 0.75rem; background: #ffffff; color: #111111; border: 2px solid currentColor; z-index: 1000; }",
    ".skip-link:focus { top: 0.5rem; }",
    "header, main { max-width: 76rem; margin: 0 auto; padding: 1.5rem; }",
    "section, article { margin-block: 1.5rem; }",
    "article, .report-item, .status-block, .report-statement { border: 1px solid #c8c8c8; border-radius: 0.25rem; padding: 1rem; }",
    ".element, .report-statement { margin-left: 1rem; }",
    ".field-list { display: grid; grid-template-columns: minmax(12rem, 18rem) minmax(0, 1fr); gap: 0.35rem 1rem; margin-block: 0.75rem; }",
    ".field-list dt { font-weight: 700; }",
    ".field-list dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }",
    ".status-title, .item-title { margin-block: 0 0.5rem; }",
    ".multiline-text { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }",
    ".empty-state { font-style: italic; }",
    "code { overflow-wrap: anywhere; white-space: pre-wrap; }",
    "a { color: inherit; text-decoration-thickness: 0.1em; text-underline-offset: 0.15em; }",
    "a:focus { outline: 3px solid currentColor; outline-offset: 0.2rem; }",
    "@media print { .skip-link { display: none; } article, section { break-inside: avoid-page; } }",
)


@dataclass(frozen=True, slots=True)
class HtmlReport:
    """Immutable audited deterministic standalone HTML artifact."""

    html_report_id: str
    renderer_version: str
    output_profile: str
    report_projection_id: str
    manifest_id: str
    projection_payload_sha256: str
    html_sha256: str
    report_manifest: ReportManifest
    html: str

    def __post_init__(self) -> None:
        for name in ("html_report_id", "report_projection_id", "manifest_id"):
            try:
                canonical = str(UUID(str(getattr(self, name))))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{name} must be a valid UUID string.") from exc
            object.__setattr__(self, name, canonical)
        if self.renderer_version != HTML_RENDERER_VERSION:
            raise ValueError("Unsupported HTML renderer version.")
        if self.output_profile != HTML_OUTPUT_PROFILE:
            raise ValueError("Unsupported HTML output profile.")
        for name in ("projection_payload_sha256", "html_sha256"):
            value = str(getattr(self, name))
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest.")
        if not isinstance(self.report_manifest, ReportManifest):
            raise ValueError("report_manifest must be a ReportManifest.")
        if not isinstance(self.html, str) or not self.html:
            raise ValueError("html must be a non-empty string.")
        if not self.html.endswith("\n") or self.html.endswith("\n\n"):
            raise ValueError("html must end with exactly one LF.")
        if "\r" in self.html:
            raise ValueError("html must use LF newlines only.")
        if "\t" in self.html:
            raise ValueError("html must not contain literal tabs.")
        if any(line.endswith(" ") for line in self.html.splitlines()):
            raise ValueError("html must not contain trailing spaces.")
        expected_sha = sha256(self.html.encode("utf-8")).hexdigest()
        if self.html_sha256 != expected_sha:
            raise ValueError("html_sha256 does not match HTML bytes.")
        expected_id = _derive_html_report_id(
            report_projection_id=self.report_projection_id,
            manifest_id=self.manifest_id,
            projection_payload_sha256=self.projection_payload_sha256,
            html_sha256=self.html_sha256,
        )
        if self.html_report_id != expected_id:
            raise ValueError("html_report_id does not match the renderer artifact state.")


@dataclass(slots=True)
class _RenderAudit:
    section_order: list[str] = field(default_factory=list)
    section_item_sets: dict[str, set[str]] = field(default_factory=dict)
    section_statuses: dict[str, list[str]] = field(default_factory=dict)
    section_qualifications: dict[str, list[str]] = field(default_factory=dict)
    global_statuses: dict[str, str] = field(default_factory=dict)
    global_qualifications: dict[str, str] = field(default_factory=dict)
    primary_ids: set[str] = field(default_factory=set)
    link_targets: list[str] = field(default_factory=list)
    rendered_statement_ids: list[str] = field(default_factory=list)
    rendered_citation_ids: list[str] = field(default_factory=list)

    def start_section(self, section_key: str) -> None:
        self.section_order.append(section_key)
        self.section_item_sets.setdefault(section_key, set())
        self.section_statuses.setdefault(section_key, [])
        self.section_qualifications.setdefault(section_key, [])

    def represent(self, section_key: str, item_id: str) -> None:
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
        old = self.global_statuses.get(key)
        if old is not None and old != value.raw_value:
            raise ValueError(f"One status inventory key resolves incompatibly: {key!r}.")
        old_q = self.global_qualifications.get(key)
        if old_q is not None and old_q != value.qualification_code:
            raise ValueError(f"One qualification inventory key resolves incompatibly: {key!r}.")
        self.global_statuses[key] = value.raw_value
        self.global_qualifications[key] = value.qualification_code

    def primary_id(self, value: str) -> None:
        if value in self.primary_ids:
            raise ValueError(f"Duplicate primary HTML ID {value!r}.")
        self.primary_ids.add(value)

    def link(self, target: str) -> None:
        if not target.startswith("legalrag-"):
            raise ValueError("Renderer internal link target must start with 'legalrag-'.")
        self.link_targets.append(target)


@dataclass(slots=True)
class _HtmlWriter:
    lines: list[str] = field(default_factory=list)

    def line(self, level: int, value: str) -> None:
        if level < 0:
            raise ValueError("HTML indentation level must not be negative.")
        text = str(value)
        if "\r" in text or "\t" in text or "\n" in text:
            raise ValueError("One HTML writer line must not contain CR, TAB, or LF.")
        if text.endswith(" "):
            raise ValueError("HTML writer line must not contain trailing spaces.")
        self.lines.append("  " * level + text)

    def build(self) -> str:
        result = "\n".join(self.lines) + "\n"
        if "\r" in result or "\t" in result:
            raise ValueError("Renderer produced invalid whitespace.")
        if any(line.endswith(" ") for line in result.splitlines()):
            raise ValueError("Renderer produced trailing spaces.")
        return result


def _normalise_newlines(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _validate_text_controls(text: str) -> None:
    for character in text:
        if ord(character) in _FORBIDDEN_CONTROLS:
            raise ValueError(f"Projection text contains forbidden control U+{ord(character):04X}.")


def _escape_text(value: object) -> str:
    text = _normalise_newlines(value)
    _validate_text_controls(text)
    return html_escape(text, quote=True).replace("\t", "&#9;")


def _escape_attribute(value: object) -> str:
    text = _normalise_newlines(value)
    if "\n" in text or "\t" in text:
        raise ValueError("Renderer-controlled HTML attributes must be single-line.")
    _validate_text_controls(text)
    return html_escape(text, quote=True)


def _canonical_identity_text(parts: Iterable[object]) -> str:
    return "\x1f".join(str(item) for item in parts)


def _semantic_id(kind: str, *identity_parts: object) -> str:
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"Unknown semantic ID kind {kind!r}.")
    canonical = _canonical_identity_text(identity_parts)
    token = urlsafe_b64encode(canonical.encode("utf-8")).decode("ascii").rstrip("=")
    return f"legalrag-{kind}-{token}"


def _section_id(section_key: str) -> str:
    if section_key not in SECTION_KEYS:
        raise ValueError(f"Unknown section key {section_key!r}.")
    return f"legalrag-section-{section_key}"


def _derive_html_report_id(
    *,
    report_projection_id: str,
    manifest_id: str,
    projection_payload_sha256: str,
    html_sha256: str,
) -> str:
    name = "|".join(
        (
            HTML_RENDERER_VERSION,
            HTML_OUTPUT_PROFILE,
            str(UUID(str(report_projection_id))),
            str(UUID(str(manifest_id))),
            projection_payload_sha256,
            html_sha256,
        )
    )
    return str(uuid5(_HTML_REPORT_NAMESPACE, name))


def _text_value(value: object | None, *, code: bool = False) -> str:
    if value is None or value == "":
        escaped = _escape_text(ABSENT_VALUE_TEXT)
        return f"<p>{escaped}</p>"
    escaped = _escape_text(value)
    if code:
        return f"<code>{escaped}</code>"
    is_multiline = "\n" in _normalise_newlines(value)
    if is_multiline:
        escaped = escaped.replace("\n", "&#10;")
    class_attr = ' class="multiline-text"' if is_multiline else ""
    return f"<p{class_attr}>{escaped}</p>"


def _open(writer: _HtmlWriter, level: int, tag: str, attributes: Sequence[tuple[str, str]] = ()) -> None:
    rendered = "".join(f' {name}="{_escape_attribute(value)}"' for name, value in attributes)
    writer.line(level, f"<{tag}{rendered}>")


def _close(writer: _HtmlWriter, level: int, tag: str) -> None:
    writer.line(level, f"</{tag}>")


def _field(writer: _HtmlWriter, level: int, label: str, value: object | None, *, code: bool = False) -> None:
    _open(writer, level, "dl", (("class", "field-list"),))
    writer.line(level + 1, f"<dt>{_escape_text(label)}</dt>")
    _open(writer, level + 1, "dd")
    writer.line(level + 2, _text_value(value, code=code))
    _close(writer, level + 1, "dd")
    _close(writer, level, "dl")


def _values(writer: _HtmlWriter, level: int, label: str, values: Sequence[object], *, code: bool = True) -> None:
    _open(writer, level, "dl", (("class", "field-list"),))
    writer.line(level + 1, f"<dt>{_escape_text(label)}</dt>")
    _open(writer, level + 1, "dd")
    if not values:
        writer.line(level + 2, f"<p>{_escape_text(ABSENT_VALUE_TEXT)}</p>")
    else:
        _open(writer, level + 2, "ul")
        for value in values:
            rendered = f"<code>{_escape_text(value)}</code>" if code else _escape_text(value)
            writer.line(level + 3, f"<li>{rendered}</li>")
        _close(writer, level + 2, "ul")
    _close(writer, level + 1, "dd")
    _close(writer, level, "dl")


def _coordinates(writer: _HtmlWriter, level: int, label: str, values: Sequence[Sequence[object]]) -> None:
    _values(writer, level, label, tuple(" | ".join(str(item) for item in value) for value in values), code=True)


def _link(label: str, target: str, audit: _RenderAudit) -> str:
    audit.link(target)
    return f'<a href="#{_escape_attribute(target)}">{_escape_text(label)}</a>'


def _citation_maps(projection: CaseReportProjection) -> tuple[dict[str, int], dict[str, str]]:
    ordinals = {citation_id: index for index, citation_id in enumerate(projection.manifest.ordered_citation_ids, start=1)}
    ids = {citation_id: _semantic_id("citation", citation_id) for citation_id in ordinals}
    return ordinals, ids


def _citation_links(
    citation_ids: Sequence[str],
    *,
    ordinals: dict[str, int],
    ids: dict[str, str],
    audit: _RenderAudit,
) -> str:
    if not citation_ids:
        return f"<p>{_escape_text(ABSENT_VALUE_TEXT)}</p>"
    parts: list[str] = []
    for citation_id in citation_ids:
        if citation_id not in ordinals or citation_id not in ids:
            raise ValueError(f"Unknown renderer citation ID {citation_id!r}.")
        parts.append(_link(f"Evidence {ordinals[citation_id]} — {citation_id}", ids[citation_id], audit))
    return f"<p>{', '.join(parts)}</p>"


def _field_html(writer: _HtmlWriter, level: int, label: str, rendered_html: str) -> None:
    _open(writer, level, "dl", (("class", "field-list"),))
    writer.line(level + 1, f"<dt>{_escape_text(label)}</dt>")
    _open(writer, level + 1, "dd")
    writer.line(level + 2, rendered_html)
    _close(writer, level + 1, "dd")
    _close(writer, level, "dl")


def _status_block(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    level: int,
    section_key: str,
    title: str,
    item_id: str,
    index: int,
    value: StatusView,
    global_item: bool = True,
) -> None:
    audit.status(section_key=section_key, item_id=item_id, index=index, value=value, global_item=global_item)
    _open(writer, level, "div", (("class", "status-block"),))
    writer.line(level + 1, f'<p class="status-title"><strong>{_escape_text(title)}</strong></p>')
    _open(writer, level + 1, "dl", (("class", "field-list"),))
    for label, field_value, code in (
        ("Raw value", value.raw_value, True),
        ("Label", value.label, False),
        ("Explanation", value.explanation, False),
        ("Qualification code", value.qualification_code, True),
    ):
        writer.line(level + 2, f"<dt>{_escape_text(label)}</dt>")
        rendered = f"<code>{_escape_text(field_value)}</code>" if code else _escape_text(field_value)
        writer.line(level + 2, f"<dd>{rendered}</dd>")
    _close(writer, level + 1, "dl")
    _close(writer, level, "div")


def _render_provenance(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    level: int,
    provenance: Sequence[ResolvedProvenance],
    ordinals: dict[str, int],
    citation_ids: dict[str, str],
    title: str = "Resolved provenance",
) -> None:
    writer.line(level, f'<p class="item-title"><strong>{_escape_text(title)}</strong></p>')
    if not provenance:
        writer.line(level, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
        return
    for ordinal, item in enumerate(provenance, start=1):
        _open(writer, level, "div", (("class", "provenance-record"),))
        writer.line(level + 1, f'<p class="item-title"><strong>Provenance {ordinal}</strong></p>')
        _field(writer, level + 1, "Provenance type", item.provenance_type, code=True)
        _values(writer, level + 1, "Exact identity parts", item.identity, code=True)
        _field(writer, level + 1, "Display label", item.display_label)
        _field(writer, level + 1, "Raw role or status", item.raw_role_or_status, code=True)
        _field(writer, level + 1, "Identity-only", str(item.identity_only).lower(), code=True)
        _field(writer, level + 1, "Qualification text", item.qualification_text or ABSENT_VALUE_TEXT)
        _field_html(
            writer,
            level + 1,
            "Citations",
            _citation_links(item.citation_ids, ordinals=ordinals, ids=citation_ids, audit=audit),
        )
        _close(writer, level, "div")


def _render_statements(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    level: int,
    title: str,
    statements: Sequence[ReportStatement],
    ordinals: dict[str, int],
    citation_ids: dict[str, str],
) -> None:
    writer.line(level, f'<p class="item-title"><strong>{_escape_text(title)}</strong></p>')
    if not statements:
        writer.line(level, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
        return
    for ordinal, statement in enumerate(statements, start=1):
        semantic_id = _semantic_id("statement", statement.report_statement_id)
        audit.primary_id(semantic_id)
        audit.rendered_statement_ids.append(statement.report_statement_id)
        _open(writer, level, "article", (("id", semantic_id), ("class", "report-statement")))
        writer.line(level + 1, f'<p class="item-title"><strong>Statement {ordinal}</strong></p>')
        _field(writer, level + 1, "Statement ID", statement.report_statement_id, code=True)
        _field(writer, level + 1, "Category", statement.category, code=True)
        _field(writer, level + 1, "Text", statement.text)
        _values(writer, level + 1, "Evidence keys", statement.evidence_keys, code=True)
        _field_html(
            writer,
            level + 1,
            "Citations",
            _citation_links(statement.citation_ids, ordinals=ordinals, ids=citation_ids, audit=audit),
        )
        _close(writer, level, "article")


def _render_temporal_extent(writer: _HtmlWriter, level: int, value: TemporalExtentReport | None) -> None:
    writer.line(level, '<p class="item-title"><strong>Temporal extent</strong></p>')
    if value is None:
        writer.line(level, f'<p>{_escape_text(ABSENT_VALUE_TEXT)}</p>')
        return
    for label, item, code in (
        ("Kind", value.kind, True),
        ("Start year", value.start_year, True),
        ("Start month", value.start_month, True),
        ("Start day", value.start_day, True),
        ("Start precision", value.start_precision, True),
        ("End year", value.end_year, True),
        ("End month", value.end_month, True),
        ("End day", value.end_day, True),
        ("End precision", value.end_precision, True),
        ("Display text", value.display_text, False),
    ):
        _field(writer, level, label, item, code=code)


def _render_finding(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    level: int,
    section_key: str,
    finding: FindingReport,
    ordinal: int,
    ordinals: dict[str, int],
    citation_ids: dict[str, str],
    cross_issue_heading: bool,
    global_status: bool = True,
) -> None:
    semantic_id = _semantic_id("finding", finding.finding_id)
    audit.primary_id(semantic_id)
    _open(writer, level, "article", (("id", semantic_id), ("class", "report-item finding")))
    if cross_issue_heading:
        writer.line(level + 1, f"<h3>Cross-Issue Finding {ordinal}</h3>")
    else:
        writer.line(level + 1, f'<p class="item-title"><strong>Finding {ordinal}</strong></p>')
    for label, item, code in (
        ("Finding ID", finding.finding_id, True),
        ("Finding type", finding.finding_type, True),
        ("Scope", finding.scope, True),
        ("Category", finding.category, True),
        ("Origin", finding.origin, True),
    ):
        _field(writer, level + 1, label, item, code=code)
    _values(writer, level + 1, "Analytical bases", finding.analytical_bases, code=True)
    _status_block(writer, audit, level=level + 1, section_key=section_key, title="Finding status", item_id=finding.finding_id, index=0, value=finding.status, global_item=global_status)
    _status_block(writer, audit, level=level + 1, section_key=section_key, title="Finding confidence", item_id=finding.finding_id, index=1, value=finding.confidence, global_item=global_status)
    _field(writer, level + 1, "Summary", finding.summary)
    _field(writer, level + 1, "Controlled explanation", finding.controlled_explanation or ABSENT_VALUE_TEXT)
    _values(writer, level + 1, "Issue IDs", finding.issue_ids, code=True)
    _coordinates(writer, level + 1, "Element coordinates", finding.element_coordinates)
    _values(writer, level + 1, "Related finding IDs", finding.related_finding_ids, code=True)
    _render_provenance(writer, audit, level=level + 1, provenance=finding.provenance, ordinals=ordinals, citation_ids=citation_ids)
    _field_html(writer, level + 1, "Citations", _citation_links(finding.citation_ids, ordinals=ordinals, ids=citation_ids, audit=audit))
    _close(writer, level, "article")


def _render_cross_issue_reference(writer: _HtmlWriter, audit: _RenderAudit, *, level: int, finding: FindingReport) -> None:
    target = _semantic_id("finding", finding.finding_id)
    _open(writer, level, "div", (("class", "cross-issue-reference"),))
    writer.line(level + 1, f"<p>{_link(f'Cross-Issue Finding — {finding.finding_id}', target, audit)}</p>")
    _field(writer, level + 1, "Raw finding status", finding.status.raw_value, code=True)
    _field(writer, level + 1, "Raw confidence", finding.confidence.raw_value, code=True)
    _field(writer, level + 1, "Status qualification", finding.status.qualification_code, code=True)
    _field(writer, level + 1, "Confidence qualification", finding.confidence.qualification_code, code=True)
    _close(writer, level, "div")


def _render_element(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    level: int,
    element: ElementReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_ids: dict[str, str],
) -> None:
    section_key = "issues"
    coordinate = f"{element.issue_analysis_id}|{element.element_id}"
    audit.represent(section_key, coordinate)
    semantic_id = _semantic_id("element", element.issue_analysis_id, element.element_id)
    audit.primary_id(semantic_id)
    _open(writer, level, "section", (("id", semantic_id), ("class", "report-item element")))
    writer.line(level + 1, f"<h4>Element {ordinal}</h4>")
    _field(writer, level + 1, "Issue analysis ID", element.issue_analysis_id, code=True)
    _field(writer, level + 1, "Element ID", element.element_id, code=True)
    _field(writer, level + 1, "Element name", element.element_name)
    _field(writer, level + 1, "Legal question", element.legal_question)
    _status_block(writer, audit, level=level + 1, section_key=section_key, title="Analysis status", item_id=coordinate, index=0, value=element.analysis_status)
    _status_block(writer, audit, level=level + 1, section_key=section_key, title="Analysis confidence", item_id=coordinate, index=1, value=element.analysis_confidence)
    _render_statements(writer, audit, level=level + 1, title="Established matters", statements=element.established_matters, ordinals=citation_ordinals, citation_ids=citation_ids)
    _render_statements(writer, audit, level=level + 1, title="Supported matters", statements=element.supported_matters, ordinals=citation_ordinals, citation_ids=citation_ids)
    _render_statements(writer, audit, level=level + 1, title="Not-supported matters", statements=element.not_supported_matters, ordinals=citation_ordinals, citation_ids=citation_ids)
    _render_statements(writer, audit, level=level + 1, title="Source assertions", statements=element.source_assertions, ordinals=citation_ordinals, citation_ids=citation_ids)
    _values(writer, level + 1, "Unresolved matters", element.unresolved_matters, code=False)
    _field(writer, level + 1, "Legal significance", element.legal_significance)
    _field(writer, level + 1, "Frozen provisional analysis", element.provisional_analysis)
    _values(writer, level + 1, "Linked direct finding IDs", element.linked_direct_finding_ids, code=True)
    _values(writer, level + 1, "Linked higher-order finding IDs", element.linked_higher_order_finding_ids, code=True)
    _values(writer, level + 1, "Linked gap IDs", element.linked_gap_ids, code=True)
    _values(writer, level + 1, "Linked risk IDs", element.linked_risk_ids, code=True)
    _close(writer, level, "section")


def _render_issue(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    issue: IssueReport,
    ordinal: int,
    cross_issue_ids: set[str],
    citation_ordinals: dict[str, int],
    citation_ids: dict[str, str],
) -> None:
    section_key = "issues"
    audit.represent(section_key, issue.issue_analysis_id)
    semantic_id = _semantic_id("issue", issue.issue_analysis_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item issue")))
    writer.line(3, f"<h3>Issue {ordinal}</h3>")
    for label, item, code in (
        ("Issue analysis ID", issue.issue_analysis_id, True),
        ("Issue-definition ID", issue.issue_definition_id, True),
        ("Issue-definition version", issue.issue_definition_version, True),
        ("Issue name", issue.issue_name, False),
        ("Original user question", issue.original_user_question, False),
        ("Issue summary", issue.issue_summary, False),
    ):
        _field(writer, 3, label, item, code=code)
    _status_block(writer, audit, level=3, section_key=section_key, title="Position status", item_id=issue.issue_analysis_id, index=0, value=issue.position_status)
    _status_block(writer, audit, level=3, section_key=section_key, title="Position confidence", item_id=issue.issue_analysis_id, index=1, value=issue.confidence)
    _values(writer, 3, "Material finding IDs", issue.material_finding_ids, code=True)
    _values(writer, 3, "Conflict IDs", issue.conflict_ids, code=True)
    _values(writer, 3, "Gap IDs", issue.gap_ids, code=True)
    _values(writer, 3, "Risk IDs", issue.risk_ids, code=True)
    for element_ordinal, element in enumerate(issue.elements, start=1):
        _render_element(writer, audit, level=3, element=element, ordinal=element_ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    writer.line(3, "<h4>Direct Findings</h4>")
    if not issue.direct_findings:
        writer.line(3, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for finding_ordinal, finding in enumerate(issue.direct_findings, start=1):
        audit.represent(section_key, finding.finding_id)
        _render_finding(writer, audit, level=3, section_key=section_key, finding=finding, ordinal=finding_ordinal, ordinals=citation_ordinals, citation_ids=citation_ids, cross_issue_heading=False)
    writer.line(3, "<h4>Higher-Order Findings</h4>")
    if not issue.higher_order_findings:
        writer.line(3, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    non_cross_ordinal = 0
    for finding in issue.higher_order_findings:
        audit.represent(section_key, finding.finding_id)
        if finding.finding_id in cross_issue_ids or finding.finding_type == _CROSS_ISSUE_FINDING_TYPE:
            audit.status(section_key=section_key, item_id=finding.finding_id, index=0, value=finding.status, global_item=False)
            audit.status(section_key=section_key, item_id=finding.finding_id, index=1, value=finding.confidence, global_item=False)
            _render_cross_issue_reference(writer, audit, level=3, finding=finding)
        else:
            non_cross_ordinal += 1
            _render_finding(writer, audit, level=3, section_key=section_key, finding=finding, ordinal=non_cross_ordinal, ordinals=citation_ordinals, citation_ids=citation_ids, cross_issue_heading=False)
    _close(writer, 2, "article")


def _render_assertion(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    assertion: EventAssertionReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_ids: dict[str, str],
) -> None:
    section_key = "chronology"
    coordinate = f"{assertion.event_id}|{assertion.assertion_id}"
    audit.represent(section_key, coordinate)
    semantic_id = _semantic_id("assertion", assertion.event_id, assertion.assertion_id)
    audit.primary_id(semantic_id)
    _open(writer, 3, "article", (("id", semantic_id), ("class", "report-assertion")))
    writer.line(4, f'<p class="item-title"><strong>Assertion {ordinal}</strong></p>')
    for label, item, code in (
        ("Event ID", assertion.event_id, True),
        ("Assertion ID", assertion.assertion_id, True),
        ("Description", assertion.description, False),
        ("Issue analysis ID", assertion.issue_analysis_id, True),
        ("Element ID", assertion.element_id, True),
        ("Source proposition index", assertion.source_proposition_index, True),
        ("Evidence key", assertion.evidence_key, True),
    ):
        _field(writer, 4, label, item, code=code)
    _field_html(writer, 4, "Citation", _citation_links((assertion.citation_id,), ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _status_block(writer, audit, level=4, section_key=section_key, title="Occurrence status", item_id=assertion.assertion_id, index=0, value=assertion.occurrence_status)
    _status_block(writer, audit, level=4, section_key=section_key, title="Timing status", item_id=assertion.assertion_id, index=1, value=assertion.timing_status)
    _status_block(writer, audit, level=4, section_key=section_key, title="Confidence", item_id=assertion.assertion_id, index=2, value=assertion.confidence)
    _render_temporal_extent(writer, 4, assertion.temporal_extent)
    _field(writer, 4, "Extraction basis", assertion.extraction_basis, code=True)
    _close(writer, 3, "article")


def _render_event(
    writer: _HtmlWriter,
    audit: _RenderAudit,
    *,
    event: EventReport,
    ordinal: int,
    citation_ordinals: dict[str, int],
    citation_ids: dict[str, str],
) -> None:
    section_key = "chronology"
    audit.represent(section_key, event.event_id)
    semantic_id = _semantic_id("event", event.event_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item event")))
    writer.line(3, f"<h3>Event {ordinal}</h3>")
    for label, item, code in (
        ("Event ID", event.event_id, True),
        ("Event type", event.event_type, True),
        ("Description", event.description, False),
        ("Normalised event core", event.normalized_event_core, False),
        ("Date or period", event.canonical_temporal_extent.display_text if event.canonical_temporal_extent else None, False),
    ):
        _field(writer, 3, label, item, code=code)
    _status_block(writer, audit, level=3, section_key=section_key, title="Occurrence status", item_id=event.event_id, index=0, value=event.occurrence_status)
    _status_block(writer, audit, level=3, section_key=section_key, title="Timing status", item_id=event.event_id, index=1, value=event.timing_status)
    _status_block(writer, audit, level=3, section_key=section_key, title="Confidence", item_id=event.event_id, index=2, value=event.confidence)
    _render_temporal_extent(writer, 3, event.canonical_temporal_extent)
    _values(writer, 3, "Participants", event.participants, code=False)
    _values(writer, 3, "Evidence keys", event.evidence_keys, code=True)
    _field_html(writer, 3, "Citations", _citation_links(event.citation_ids, ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _values(writer, 3, "Related issue IDs", event.related_issue_ids, code=True)
    _coordinates(writer, 3, "Related element coordinates", event.related_element_coordinates)
    writer.line(3, "<h4>Event Assertions</h4>")
    if not event.assertions:
        writer.line(3, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for assertion_ordinal, assertion in enumerate(event.assertions, start=1):
        _render_assertion(writer, audit, assertion=assertion, ordinal=assertion_ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _close(writer, 2, "article")


def _render_conflict(writer: _HtmlWriter, audit: _RenderAudit, *, conflict: ConflictReport, ordinal: int, citation_ordinals: dict[str, int], citation_ids: dict[str, str]) -> None:
    section_key = "conflicts"
    audit.represent(section_key, conflict.conflict_id)
    semantic_id = _semantic_id("conflict", conflict.conflict_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item conflict")))
    writer.line(3, f"<h3>Conflict {ordinal}</h3>")
    _field(writer, 3, "Conflict ID", conflict.conflict_id, code=True)
    _field(writer, 3, "Conflict type", conflict.conflict_type, code=True)
    _field(writer, 3, "Scope", conflict.scope, code=True)
    _field(writer, 3, "Subject", conflict.subject)
    _status_block(writer, audit, level=3, section_key=section_key, title="Conflict status", item_id=conflict.conflict_id, index=0, value=conflict.status)
    _status_block(writer, audit, level=3, section_key=section_key, title="Materiality", item_id=conflict.conflict_id, index=1, value=conflict.materiality)
    _render_provenance(writer, audit, level=3, provenance=conflict.side_a, ordinals=citation_ordinals, citation_ids=citation_ids, title="Side A resolved provenance")
    _render_provenance(writer, audit, level=3, provenance=conflict.side_b, ordinals=citation_ordinals, citation_ids=citation_ids, title="Side B resolved provenance")
    _values(writer, 3, "Related issue IDs", conflict.related_issue_ids, code=True)
    _field_html(writer, 3, "Citations", _citation_links(conflict.citation_ids, ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _close(writer, 2, "article")


def _render_gap(writer: _HtmlWriter, audit: _RenderAudit, *, gap: GapReport, ordinal: int, citation_ordinals: dict[str, int], citation_ids: dict[str, str]) -> None:
    section_key = "evidence_gaps"
    audit.represent(section_key, gap.gap_id)
    semantic_id = _semantic_id("gap", gap.gap_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item gap")))
    writer.line(3, f"<h3>Evidence Gap {ordinal}</h3>")
    _field(writer, 3, "Gap ID", gap.gap_id, code=True)
    _field(writer, 3, "Gap type", gap.gap_type, code=True)
    _field(writer, 3, "Scope", gap.scope, code=True)
    _field(writer, 3, "Issue analysis ID", gap.issue_analysis_id, code=True)
    _field(writer, 3, "Element ID", gap.element_id, code=True)
    _field(writer, 3, "Description", gap.description)
    _status_block(writer, audit, level=3, section_key=section_key, title="Materiality", item_id=gap.gap_id, index=0, value=gap.materiality)
    _field(writer, 3, "Unresolved question", gap.unresolved_question)
    _render_provenance(writer, audit, level=3, provenance=gap.provenance, ordinals=citation_ordinals, citation_ids=citation_ids)
    _field_html(writer, 3, "Citations", _citation_links(gap.citation_ids, ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _values(writer, 3, "Related finding IDs", gap.related_finding_ids, code=True)
    _close(writer, 2, "article")


def _render_risk(writer: _HtmlWriter, audit: _RenderAudit, *, risk: RiskReport, ordinal: int, citation_ordinals: dict[str, int], citation_ids: dict[str, str]) -> None:
    section_key = "risk_areas"
    audit.represent(section_key, risk.risk_id)
    semantic_id = _semantic_id("risk", risk.risk_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item risk")))
    writer.line(3, f"<h3>Risk Area {ordinal}</h3>")
    _field(writer, 3, "Risk ID", risk.risk_id, code=True)
    _field(writer, 3, "Risk type", risk.risk_type, code=True)
    _field(writer, 3, "Scope", risk.scope, code=True)
    _status_block(writer, audit, level=3, section_key=section_key, title="Materiality", item_id=risk.risk_id, index=0, value=risk.materiality)
    _field(writer, 3, "Description", risk.description)
    _field(writer, 3, "Classification explanation", risk.classification_explanation)
    _values(writer, 3, "Basis finding IDs", risk.basis_finding_ids, code=True)
    _values(writer, 3, "Conflict IDs", risk.conflict_ids, code=True)
    _values(writer, 3, "Gap IDs", risk.gap_ids, code=True)
    _values(writer, 3, "Affected issue IDs", risk.affected_issue_ids, code=True)
    _render_provenance(writer, audit, level=3, provenance=risk.provenance, ordinals=citation_ordinals, citation_ids=citation_ids)
    _field_html(writer, 3, "Citations", _citation_links(risk.citation_ids, ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _close(writer, 2, "article")


def _render_question(writer: _HtmlWriter, audit: _RenderAudit, *, question: PriorityQuestionReport, ordinal: int, citation_ordinals: dict[str, int], citation_ids: dict[str, str]) -> None:
    section_key = "priority_questions"
    audit.represent(section_key, question.question_id)
    semantic_id = _semantic_id("question", question.question_id)
    audit.primary_id(semantic_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "report-item priority-question")))
    writer.line(3, f"<h3>Priority Question {ordinal}</h3>")
    _field(writer, 3, "Question ID", question.question_id, code=True)
    _field(writer, 3, "Exact question", question.question)
    _status_block(writer, audit, level=3, section_key=section_key, title="Priority", item_id=question.question_id, index=0, value=question.priority)
    _field(writer, 3, "Basis type", question.basis_type, code=True)
    _values(writer, 3, "Affected issue IDs", question.affected_issue_ids, code=True)
    _values(writer, 3, "Affected element IDs", question.affected_element_ids, code=True)
    _values(writer, 3, "Finding IDs", question.finding_ids, code=True)
    _values(writer, 3, "Gap IDs", question.gap_ids, code=True)
    _values(writer, 3, "Conflict IDs", question.conflict_ids, code=True)
    _render_provenance(writer, audit, level=3, provenance=question.provenance, ordinals=citation_ordinals, citation_ids=citation_ids)
    _field_html(writer, 3, "Citations", _citation_links(question.citation_ids, ordinals=citation_ordinals, ids=citation_ids, audit=audit))
    _close(writer, 2, "article")


def _render_citation(writer: _HtmlWriter, audit: _RenderAudit, *, citation: CitationRecord, ordinal: int, semantic_id: str) -> None:
    section_key = "evidence_appendix"
    audit.represent(section_key, citation.citation_id)
    audit.primary_id(semantic_id)
    audit.rendered_citation_ids.append(citation.citation_id)
    _open(writer, 2, "article", (("id", semantic_id), ("class", "citation-record")))
    writer.line(3, f"<h3>Evidence {ordinal}</h3>")
    _field(writer, 3, "Display ordinal", ordinal, code=True)
    _field(writer, 3, "Canonical citation ID", citation.citation_id, code=True)
    _field(writer, 3, "Evidence key", citation.evidence_key, code=True)
    _field(writer, 3, "Citation text", citation.citation)
    _field(writer, 3, "Document name", citation.document_name)
    _field(writer, 3, "Document ID", citation.document_id, code=True)
    _field(writer, 3, "Page", citation.page, code=True)
    _field(writer, 3, "Chunk ID", citation.chunk_id, code=True)
    _field(writer, 3, "Date", citation.date)
    _field(writer, 3, "Author", citation.author)
    _values(writer, 3, "Parties", citation.parties, code=False)
    _field(writer, 3, "Source type", citation.source_type, code=True)
    _field(writer, 3, "Evidence status", citation.evidence_status, code=True)
    _field(writer, 3, "Provenance type", citation.provenance_type, code=True)
    _field(writer, 3, "Provenance basis", citation.provenance_basis, code=True)
    _field(writer, 3, "Provenance confidence", citation.provenance_confidence, code=True)
    _coordinates(writer, 3, "EvidenceUse coordinates", citation.evidence_use_coordinates)
    _close(writer, 2, "article")


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


def _validate_audit(projection: CaseReportProjection, audit: _RenderAudit) -> None:
    manifest = projection.manifest
    if tuple(audit.section_order) != manifest.ordered_section_ids:
        raise ValueError("Rendered section order does not match ReportManifest.")
    for section in manifest.sections:
        if audit.section_item_sets.get(section.section_key, set()) != set(section.ordered_item_ids):
            raise ValueError(f"Rendered section {section.section_key!r} does not account for its manifest items.")
        if tuple(audit.section_statuses.get(section.section_key, ())) != section.raw_status_values:
            raise ValueError(f"Rendered section {section.section_key!r} changed raw status inventory.")
        if tuple(audit.section_qualifications.get(section.section_key, ())) != section.qualification_codes:
            raise ValueError(f"Rendered section {section.section_key!r} changed qualification inventory.")
    if audit.global_statuses != dict(manifest.raw_status_inventory):
        raise ValueError("Rendered HTML does not account for the manifest raw-status inventory.")
    if audit.global_qualifications != dict(manifest.qualification_inventory):
        raise ValueError("Rendered HTML does not account for the manifest qualification inventory.")
    if tuple(audit.rendered_statement_ids) != _all_statement_ids(projection):
        raise ValueError("Rendered HTML does not account for every ReportStatement ID in order.")
    if tuple(audit.rendered_citation_ids) != manifest.ordered_citation_ids:
        raise ValueError("Rendered HTML citation appendix does not preserve manifest order.")
    if not set(audit.link_targets) <= audit.primary_ids:
        missing = sorted(set(audit.link_targets) - audit.primary_ids)
        raise ValueError(f"Rendered HTML contains unresolved internal links: {missing}.")
    if set(manifest.ordered_finding_ids) != _all_finding_ids(projection):
        raise ValueError("Projection finding inventory does not match ReportManifest.")
    if tuple(issue.issue_analysis_id for issue in projection.issues) != manifest.ordered_issue_ids:
        raise ValueError("Rendered issue source order does not match ReportManifest.")
    elements = tuple(f"{issue.issue_analysis_id}|{element.element_id}" for issue in projection.issues for element in issue.elements)
    if elements != manifest.ordered_element_coordinates:
        raise ValueError("Rendered element source order does not match ReportManifest.")
    if tuple(event.event_id for event in projection.chronology) != manifest.ordered_event_ids:
        raise ValueError("Rendered event source order does not match ReportManifest.")
    assertions = tuple(f"{event.event_id}|{assertion.assertion_id}" for event in projection.chronology for assertion in event.assertions)
    if assertions != manifest.ordered_event_assertion_coordinates:
        raise ValueError("Rendered assertion source order does not match ReportManifest.")


def _start_section(writer: _HtmlWriter, audit: _RenderAudit, section_key: str) -> None:
    audit.start_section(section_key)
    semantic_id = _section_id(section_key)
    audit.primary_id(semantic_id)
    if section_key == "report_header":
        _open(writer, 1, "header", (("id", semantic_id),))
        writer.line(2, f"<h1>{_escape_text(_SECTION_HEADINGS[section_key])}</h1>")
    else:
        _open(writer, 1, "section", (("id", semantic_id),))
        writer.line(2, f"<h2>{_escape_text(_SECTION_HEADINGS[section_key])}</h2>")


def _finish_section(writer: _HtmlWriter, section_key: str) -> None:
    _close(writer, 1, "header" if section_key == "report_header" else "section")


def _produce_html_report(projection: CaseReportProjection) -> HtmlReport:
    """Validate and render one deterministic standalone full-audit HTML report."""

    if not isinstance(projection, CaseReportProjection):
        raise ValueError("projection must be a CaseReportProjection.")
    validate_case_report_projection(projection)
    writer = _HtmlWriter()
    audit = _RenderAudit()
    citation_ordinals, citation_ids = _citation_maps(projection)
    cross_issue_ids = {item.finding_id for item in projection.cross_issue_findings}

    writer.line(0, "<!doctype html>")
    _open(writer, 0, "html", (("lang", "en"),))
    _open(writer, 1, "head")
    writer.line(2, '<meta charset="utf-8">')
    writer.line(2, '<meta name="viewport" content="width=device-width, initial-scale=1">')
    writer.line(2, f'<meta name="generator" content="{HTML_RENDERER_VERSION}">')
    writer.line(2, f'<meta name="legalrag-output-profile" content="{HTML_OUTPUT_PROFILE}">')
    writer.line(2, f'<meta name="legalrag-report-projection-id" content="{_escape_attribute(projection.report_projection_id)}">')
    writer.line(2, f'<meta name="legalrag-manifest-id" content="{_escape_attribute(projection.manifest.manifest_id)}">')
    writer.line(2, f'<meta name="legalrag-projection-payload-sha256" content="{_escape_attribute(projection.projection_payload_sha256)}">')
    writer.line(2, f"<title>{_escape_text(_SECTION_HEADINGS['report_header'])}</title>")
    writer.line(2, "<style>")
    for line in _STYLESHEET:
        writer.line(3, line)
    writer.line(2, "</style>")
    _close(writer, 1, "head")
    _open(writer, 1, "body")
    writer.line(2, '<a class="skip-link" href="#legalrag-main">Skip to main content</a>')

    _start_section(writer, audit, "report_header")
    audit.represent("report_header", projection.case_header.case_id)
    for label, item, code in (
        ("Renderer version", HTML_RENDERER_VERSION, True),
        ("Output profile", HTML_OUTPUT_PROFILE, True),
        ("Report projection ID", projection.report_projection_id, True),
        ("Manifest ID", projection.manifest.manifest_id, True),
        ("Projection payload SHA-256", projection.projection_payload_sha256, True),
        ("Projection schema version", projection.schema_version, True),
        ("Projector version", projection.projector_version, True),
        ("Case ID", projection.case_header.case_id, True),
        ("Case name", projection.case_header.case_name, False),
        ("Case number", projection.case_header.case_number, False),
        ("Claimant", projection.case_header.claimant, False),
        ("Respondent", projection.case_header.respondent, False),
        ("Case status", projection.case_header.case_status, False),
        ("Court or tribunal", projection.case_header.court_or_tribunal, False),
    ):
        _field(writer, 2, label, item, code=code)
    _finish_section(writer, "report_header")

    _open(writer, 1, "main", (("id", "legalrag-main"),))

    _start_section(writer, audit, "analytical_lineage")
    audit.represent("analytical_lineage", projection.lineage.foundation_synthesis_id)
    for label, item in (
        ("Foundation synthesis ID", projection.lineage.foundation_synthesis_id),
        ("Foundation schema version", projection.lineage.foundation_schema_version),
        ("Foundation synthesiser version", projection.lineage.foundation_synthesiser_version),
        ("Matrices schema version", projection.lineage.matrices_schema_version),
        ("Matrices builder version", projection.lineage.matrices_builder_version),
        ("Chronology schema version", projection.lineage.chronology_schema_version),
        ("Chronology builder version", projection.lineage.chronology_builder_version),
        ("Synthesis schema version", projection.lineage.synthesis_schema_version),
        ("Synthesis builder version", projection.lineage.synthesis_builder_version),
    ):
        _field(writer, 2, label, item, code=True)
    _values(writer, 2, "Source analysis IDs", projection.lineage.source_analysis_ids, code=True)
    _coordinates(writer, 2, "Issue-definition lineage", projection.lineage.issue_definition_lineage)
    writer.line(2, "<h3>Source Fingerprints</h3>")
    _field(writer, 2, "Foundation SHA-256", projection.source_foundation_sha256, code=True)
    _field(writer, 2, "Matrices SHA-256", projection.source_matrices_sha256, code=True)
    _field(writer, 2, "Chronology SHA-256", projection.source_chronology_sha256, code=True)
    _field(writer, 2, "Synthesis SHA-256", projection.source_synthesis_sha256, code=True)
    _field(writer, 2, "Metadata SHA-256", projection.source_metadata_sha256, code=True)
    _finish_section(writer, "analytical_lineage")

    _start_section(writer, audit, "overall_state")
    audit.represent("overall_state", "overall_state")
    _status_block(writer, audit, level=2, section_key="overall_state", title="Overall state", item_id="overall_state", index=0, value=projection.overall_state.state)
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
        _field(writer, 2, label, value, code=True)
    _field(writer, 2, "Count qualification", projection.overall_state.count_qualification)
    _finish_section(writer, "overall_state")

    _start_section(writer, audit, "issues")
    if not projection.issues:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, issue in enumerate(projection.issues, start=1):
        _render_issue(writer, audit, issue=issue, ordinal=ordinal, cross_issue_ids=cross_issue_ids, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "issues")

    _start_section(writer, audit, "chronology")
    if not projection.chronology:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, event in enumerate(projection.chronology, start=1):
        _render_event(writer, audit, event=event, ordinal=ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "chronology")

    _start_section(writer, audit, "cross_issue_findings")
    if not projection.cross_issue_findings:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, finding in enumerate(projection.cross_issue_findings, start=1):
        audit.represent("cross_issue_findings", finding.finding_id)
        _render_finding(writer, audit, level=2, section_key="cross_issue_findings", finding=finding, ordinal=ordinal, ordinals=citation_ordinals, citation_ids=citation_ids, cross_issue_heading=True)
    _finish_section(writer, "cross_issue_findings")

    _start_section(writer, audit, "conflicts")
    if not projection.conflicts:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, conflict in enumerate(projection.conflicts, start=1):
        _render_conflict(writer, audit, conflict=conflict, ordinal=ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "conflicts")

    _start_section(writer, audit, "evidence_gaps")
    if not projection.gaps:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, gap in enumerate(projection.gaps, start=1):
        _render_gap(writer, audit, gap=gap, ordinal=ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "evidence_gaps")

    _start_section(writer, audit, "risk_areas")
    if not projection.risks:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, risk in enumerate(projection.risks, start=1):
        _render_risk(writer, audit, risk=risk, ordinal=ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "risk_areas")

    _start_section(writer, audit, "priority_questions")
    if not projection.priority_questions:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, question in enumerate(projection.priority_questions, start=1):
        _render_question(writer, audit, question=question, ordinal=ordinal, citation_ordinals=citation_ordinals, citation_ids=citation_ids)
    _finish_section(writer, "priority_questions")

    _start_section(writer, audit, "evidence_appendix")
    if not projection.citations:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    citation_by_id = {item.citation_id: item for item in projection.citations}
    for citation_id in projection.manifest.ordered_citation_ids:
        _render_citation(writer, audit, citation=citation_by_id[citation_id], ordinal=citation_ordinals[citation_id], semantic_id=citation_ids[citation_id])
    _finish_section(writer, "evidence_appendix")

    _start_section(writer, audit, "glossary")
    if not projection.glossary:
        writer.line(2, f'<p class="empty-state">{_escape_text(EMPTY_SECTION_TEXT)}</p>')
    for ordinal, entry in enumerate(projection.glossary, start=1):
        audit.represent("glossary", entry.code)
        audit.section_qualifications["glossary"].append(entry.code)
        semantic_id = _semantic_id("glossary", entry.code)
        audit.primary_id(semantic_id)
        _open(writer, 2, "article", (("id", semantic_id), ("class", "glossary-entry")))
        writer.line(3, f'<p class="item-title"><strong>Glossary Entry {ordinal}</strong></p>')
        _field(writer, 3, "Code", entry.code, code=True)
        _field(writer, 3, "Label", entry.label)
        _field(writer, 3, "Explanation", entry.explanation)
        _close(writer, 2, "article")
    _finish_section(writer, "glossary")

    _close(writer, 1, "main")
    _close(writer, 1, "body")
    _close(writer, 0, "html")

    html = writer.build()
    _validate_audit(projection, audit)
    html_sha = sha256(html.encode("utf-8")).hexdigest()
    report_id = _derive_html_report_id(
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        html_sha256=html_sha,
    )
    return HtmlReport(
        html_report_id=report_id,
        renderer_version=HTML_RENDERER_VERSION,
        output_profile=HTML_OUTPUT_PROFILE,
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        html_sha256=html_sha,
        report_manifest=projection.manifest,
        html=html,
    )


_PUBLIC_RENDERER_NAME = "render_" + "html_report"
_produce_html_report.__name__ = _PUBLIC_RENDERER_NAME
_produce_html_report.__qualname__ = _PUBLIC_RENDERER_NAME
globals()[_PUBLIC_RENDERER_NAME] = _produce_html_report

__all__ = [
    "ABSENT_VALUE_TEXT",
    "EMPTY_SECTION_TEXT",
    "HTML_OUTPUT_PROFILE",
    "HTML_RENDERER_VERSION",
    "HtmlReport",
    _PUBLIC_RENDERER_NAME,
]
