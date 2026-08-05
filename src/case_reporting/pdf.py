"""Deterministic M5.4 full-audit PDF renderer.

This module is a presentation-only sibling of the frozen Markdown and HTML
renderers.  It consumes only a validated :class:`CaseReportProjection` and
returns immutable PDF bytes.  ReportLab produces the final byte stream;
pypdf is used only for read-only structural validation.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass, field, fields, is_dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import platform
from typing import Final, Iterable, Sequence
from unicodedata import bidirectional
from uuid import UUID, uuid5

import importlib

pypdf = importlib.import_module("pypdf")
reportlab = importlib.import_module("reportlab")
PdfReader = getattr(pypdf, "PdfReader")
_rl_enums = importlib.import_module("reportlab.lib.enums")
_rl_pagesizes = importlib.import_module("reportlab.lib.pagesizes")
_rl_styles = importlib.import_module("reportlab.lib.styles")
_rl_pdfdoc = importlib.import_module("reportlab.pdfbase.pdfdoc")
_rl_pdfmetrics = importlib.import_module("reportlab.pdfbase.pdfmetrics")
_rl_ttfonts = importlib.import_module("reportlab.pdfbase.ttfonts")
_rl_canvas = importlib.import_module("reportlab.pdfgen.canvas")
_rl_platypus = importlib.import_module("reportlab.platypus")
TA_CENTER = _rl_enums.TA_CENTER
A4 = _rl_pagesizes.A4
ParagraphStyle = _rl_styles.ParagraphStyle
pdfdoc = _rl_pdfdoc
pdfmetrics = _rl_pdfmetrics
TTFont = _rl_ttfonts.TTFont
Canvas = _rl_canvas.Canvas
BaseDocTemplate = _rl_platypus.BaseDocTemplate
Flowable = _rl_platypus.Flowable
Frame = _rl_platypus.Frame
PageBreak = _rl_platypus.PageBreak
PageTemplate = _rl_platypus.PageTemplate
Paragraph = _rl_platypus.Paragraph
Spacer = _rl_platypus.Spacer

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

PDF_RENDERER_VERSION: Final[str] = "case-report-pdf-renderer/1.0"
PDF_OUTPUT_PROFILE: Final[str] = "full-audit/1.0"
PDF_PYTHON_VERSION: Final[str] = "3.14.6"
PDF_REPORTLAB_VERSION: Final[str] = "5.0.0"
PDF_PYPDF_VERSION: Final[str] = "6.14.2"
PDF_FONT_PROFILE: Final[str] = "case-report-pdf-fonts/reportlab-vera/1.0"
EMPTY_SECTION_TEXT: Final[str] = "None recorded in the frozen report projection."
ABSENT_VALUE_TEXT: Final[str] = "Not recorded in the frozen report projection."

_PDF_REPORT_NAMESPACE: Final[UUID] = UUID("8a5061ca-f6ce-5b30-9d0f-7478ecf68543")
_CROSS_ISSUE_FINDING_TYPE: Final[str] = "cross_issue_feature"
_REGULAR_FONT_NAME: Final[str] = "LegalRAGVera"
_BOLD_FONT_NAME: Final[str] = "LegalRAGVeraBold"
_REGULAR_FONT_FILE: Final[str] = "Vera.ttf"
_BOLD_FONT_FILE: Final[str] = "VeraBd.ttf"
_REGULAR_FONT_SIZE: Final[int] = 65932
_BOLD_FONT_SIZE: Final[int] = 58716
_REGULAR_FONT_SHA256: Final[str] = "c4c45690b345435b2cba52ecabe275f05e49b389b39fe68ad03afbb551288d3d"
_BOLD_FONT_SHA256: Final[str] = "cc037385e4d55bfde89b13e03091ee93bf40c0c52ddd391ff031ab276f13b8e9"
_PAGE_WIDTH: Final[float] = 595.2755905511812
_PAGE_HEIGHT: Final[float] = 841.8897637795277
_LEFT_MARGIN: Final[float] = 51.0236220472441
_RIGHT_MARGIN: Final[float] = 51.0236220472441
_TOP_MARGIN: Final[float] = 56.69291338582678
_BOTTOM_MARGIN: Final[float] = 56.69291338582678
_FRAME_WIDTH: Final[float] = 493.2283464566930
_FRAME_HEIGHT: Final[float] = 728.5039370078742
_FOOTER_Y: Final[float] = 28.34645669291339

_SECTION_TITLES: Final[dict[str, str]] = {
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
_OUTLINE_SECTION_TITLES: Final[dict[str, str]] = {
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
_ALLOWED_KINDS: Final[frozenset[str]] = frozenset(
    {
        "issue", "element", "statement", "finding", "event", "assertion",
        "conflict", "gap", "risk", "question", "citation", "glossary",
    }
)
_FORBIDDEN_CONTROLS: Final[frozenset[int]] = frozenset(
    {*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20), 0x7F}
)
_BASE14_NAMES: Final[tuple[str, ...]] = (
    "Helvetica", "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
)


@dataclass(frozen=True, slots=True)
class PdfReport:
    """Immutable audited deterministic PDF artifact."""

    pdf_report_id: str
    renderer_version: str
    output_profile: str
    report_projection_id: str
    manifest_id: str
    projection_payload_sha256: str
    pdf_sha256: str
    page_count: int
    report_manifest: ReportManifest
    pdf: bytes

    def __post_init__(self) -> None:
        for name in ("pdf_report_id", "report_projection_id", "manifest_id"):
            try:
                canonical = str(UUID(str(getattr(self, name))))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{name} must be a valid UUID string.") from exc
            object.__setattr__(self, name, canonical)
        if self.renderer_version != PDF_RENDERER_VERSION:
            raise ValueError("Unsupported PDF renderer version.")
        if self.output_profile != PDF_OUTPUT_PROFILE:
            raise ValueError("Unsupported PDF output profile.")
        for name in ("projection_payload_sha256", "pdf_sha256"):
            value = str(getattr(self, name))
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest.")
        if not isinstance(self.report_manifest, ReportManifest):
            raise ValueError("report_manifest must be a ReportManifest.")
        if not isinstance(self.pdf, bytes) or not self.pdf:
            raise ValueError("pdf must be non-empty immutable bytes.")
        if self.page_count < 1:
            raise ValueError("page_count must be at least 1.")
        if sha256(self.pdf).hexdigest() != self.pdf_sha256:
            raise ValueError("pdf_sha256 does not match PDF bytes.")
        expected_id = _derive_pdf_report_id(
            report_projection_id=self.report_projection_id,
            manifest_id=self.manifest_id,
            projection_payload_sha256=self.projection_payload_sha256,
            pdf_sha256=self.pdf_sha256,
        )
        if self.pdf_report_id != expected_id:
            raise ValueError("pdf_report_id does not match renderer artifact state.")


@dataclass(slots=True)
class _RenderAudit:
    section_order: list[str] = field(default_factory=list)
    section_item_sets: dict[str, set[str]] = field(default_factory=dict)
    section_statuses: dict[str, list[str]] = field(default_factory=dict)
    section_qualifications: dict[str, list[str]] = field(default_factory=dict)
    global_statuses: dict[str, str] = field(default_factory=dict)
    global_qualifications: dict[str, str] = field(default_factory=dict)
    primary_destinations: set[str] = field(default_factory=set)
    internal_targets: list[str] = field(default_factory=list)
    rendered_statement_ids: list[str] = field(default_factory=list)
    rendered_citation_ids: list[str] = field(default_factory=list)
    outline_plan: list[tuple[int, str, str]] = field(default_factory=list)

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
        previous = self.global_statuses.get(key)
        if previous is not None and previous != value.raw_value:
            raise ValueError(f"One status key resolves incompatibly: {key!r}.")
        previous_q = self.global_qualifications.get(key)
        if previous_q is not None and previous_q != value.qualification_code:
            raise ValueError(f"One qualification key resolves incompatibly: {key!r}.")
        self.global_statuses[key] = value.raw_value
        self.global_qualifications[key] = value.qualification_code

    def destination(self, value: str, *, outline_label: str | None = None, outline_level: int | None = None) -> None:
        if value in self.primary_destinations:
            raise ValueError(f"Duplicate primary PDF destination {value!r}.")
        self.primary_destinations.add(value)
        if outline_label is not None:
            if outline_level not in (0, 1):
                raise ValueError("PDF outline level must be 0 or 1.")
            self.outline_plan.append((int(outline_level), outline_label, value))

    def link(self, target: str) -> None:
        if not target.startswith("legalrag-"):
            raise ValueError("Renderer internal target must start with 'legalrag-'.")
        self.internal_targets.append(target)


class _DestinationMarker(Flowable):
    """Zero-height deterministic destination/outline marker."""

    def __init__(self, destination: str, outline_label: str | None = None, outline_level: int | None = None) -> None:
        super().__init__()
        self.destination = destination
        self.outline_label = outline_label
        self.outline_level = outline_level
        self.width = 0
        self.height = 0

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return (0, 0)

    def draw(self) -> None:
        self.canv.bookmarkPage(self.destination)
        if self.outline_label is not None:
            self.canv.addOutlineEntry(
                self.outline_label,
                self.destination,
                level=int(self.outline_level or 0),
                closed=False,
            )


class _InvariantCanvas(Canvas):
    """Canvas with the exact frozen M5.4 PDF writer profile."""

    def __init__(self, filename, pagesize=A4, **kwargs) -> None:
        kwargs.pop("pageCompression", None)
        kwargs.pop("invariant", None)
        kwargs.pop("pdfVersion", None)
        kwargs.pop("encrypt", None)
        kwargs.pop("bottomup", None)
        kwargs.pop("verbosity", None)
        super().__init__(
            filename,
            pagesize=pagesize,
            bottomup=1,
            pageCompression=0,
            invariant=1,
            verbosity=0,
            encrypt=None,
            pdfVersion=(1, 7),
            **kwargs,
        )
        self.setTitle("LegalRAG Pro — Deterministic Case Report")
        self.setAuthor("LegalRAG Pro")
        self.setSubject("Deterministic Case Report")
        self.setCreator(PDF_RENDERER_VERSION)
        self.setProducer("LegalRAG Pro / ReportLab 5.0.0")
        self.setKeywords("")
        self._doc.info.trapped = "False"
        self._doc.Catalog.Lang = pdfdoc.PDFString("en-GB")


class _PdfDocTemplate(BaseDocTemplate):
    def __init__(self, fileobj: BytesIO) -> None:
        super().__init__(
            fileobj,
            pagesize=(_PAGE_WIDTH, _PAGE_HEIGHT),
            leftMargin=_LEFT_MARGIN,
            rightMargin=_RIGHT_MARGIN,
            topMargin=_TOP_MARGIN,
            bottomMargin=_BOTTOM_MARGIN,
            allowSplitting=1,
            title="LegalRAG Pro — Deterministic Case Report",
            author="LegalRAG Pro",
            subject="Deterministic Case Report",
            creator=PDF_RENDERER_VERSION,
            producer="LegalRAG Pro / ReportLab 5.0.0",
            keywords="",
            invariant=1,
            pageCompression=0,
            lang="en-GB",
            initialFontName=_REGULAR_FONT_NAME,
            initialFontSize=9,
            initialLeading=12,
        )
        frame = Frame(
            _LEFT_MARGIN,
            _BOTTOM_MARGIN,
            _FRAME_WIDTH,
            _FRAME_HEIGHT,
            leftPadding=0,
            bottomPadding=0,
            rightPadding=0,
            topPadding=0,
            id="legalrag-main-frame",
            showBoundary=0,
        )
        self.addPageTemplates(
            PageTemplate(
                id="legalrag-page-template",
                pagesize=(_PAGE_WIDTH, _PAGE_HEIGHT),
                frames=(frame,),
                onPage=_draw_footer,
            )
        )


def _draw_footer(canvas: Canvas, doc: BaseDocTemplate) -> None:
    canvas.saveState()
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(_REGULAR_FONT_NAME, 8)
    canvas.drawCentredString(_PAGE_WIDTH / 2.0, _FOOTER_Y, f"Page {doc.page}")
    canvas.restoreState()


def _derive_pdf_report_id(*, report_projection_id: str, manifest_id: str, projection_payload_sha256: str, pdf_sha256: str) -> str:
    name = "\x1f".join(
        (
            PDF_RENDERER_VERSION,
            PDF_OUTPUT_PROFILE,
            str(UUID(str(report_projection_id))),
            str(UUID(str(manifest_id))),
            projection_payload_sha256,
            pdf_sha256,
        )
    )
    return str(uuid5(_PDF_REPORT_NAMESPACE, name))


def _canonical_identity_text(parts: Iterable[object]) -> str:
    return "\x1f".join(str(item) for item in parts)


def _semantic_id(kind: str, *identity_parts: object) -> str:
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"Unknown semantic ID kind {kind!r}.")
    token = urlsafe_b64encode(_canonical_identity_text(identity_parts).encode("utf-8")).decode("ascii").rstrip("=")
    return f"legalrag-{kind}-{token}"


def _section_id(section_key: str) -> str:
    if section_key not in SECTION_KEYS:
        raise ValueError(f"Unknown section key {section_key!r}.")
    return f"legalrag-section-{section_key}"


def _verify_runtime_versions() -> None:
    if platform.python_version() != PDF_PYTHON_VERSION:
        raise ValueError(f"M5.4 requires CPython {PDF_PYTHON_VERSION}; found {platform.python_version()}.")
    if str(getattr(reportlab, "Version", "")) != PDF_REPORTLAB_VERSION:
        raise ValueError(f"M5.4 requires ReportLab {PDF_REPORTLAB_VERSION}.")
    if str(getattr(pypdf, "__version__", "")) != PDF_PYPDF_VERSION:
        raise ValueError(f"M5.4 requires pypdf {PDF_PYPDF_VERSION}.")


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _register_and_verify_fonts() -> tuple[frozenset[int], frozenset[int]]:
    root = Path(reportlab.__file__).resolve().parent / "fonts"
    regular = root / _REGULAR_FONT_FILE
    bold = root / _BOLD_FONT_FILE
    for path, expected_size, expected_hash in (
        (regular, _REGULAR_FONT_SIZE, _REGULAR_FONT_SHA256),
        (bold, _BOLD_FONT_SIZE, _BOLD_FONT_SHA256),
    ):
        if not path.is_file():
            raise ValueError(f"Required frozen ReportLab font is missing: {path.name}.")
        if path.stat().st_size != expected_size:
            raise ValueError(f"Frozen ReportLab font size mismatch: {path.name}.")
        if _file_sha256(path) != expected_hash:
            raise ValueError(f"Frozen ReportLab font SHA-256 mismatch: {path.name}.")
    pdfmetrics.registerFont(TTFont(_REGULAR_FONT_NAME, str(regular)))
    pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(bold)))
    regular_chars = frozenset(pdfmetrics.getFont(_REGULAR_FONT_NAME).face.charWidths)
    bold_chars = frozenset(pdfmetrics.getFont(_BOLD_FONT_NAME).face.charWidths)
    return regular_chars, bold_chars


def _normalise_text(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")


def _validate_text(value: str, cmap: frozenset[int]) -> None:
    for ch in value:
        cp = ord(ch)
        if cp == 0 or cp == 0x7F or cp in _FORBIDDEN_CONTROLS or 0xD800 <= cp <= 0xDFFF:
            raise ValueError(f"Projection text contains forbidden code point U+{cp:04X}.")
        if ch == "\n":
            continue
        if bidirectional(ch) in {"R", "AL", "AN"}:
            raise ValueError(f"Projection text requires unsupported bidirectional shaping U+{cp:04X}.")
        if cp not in cmap:
            raise ValueError(f"Projection text contains unsupported frozen-font glyph U+{cp:04X}.")


def _iter_strings(value: object) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, bytes):
        return
    if is_dataclass(value):
        for item in fields(value):
            yield from _iter_strings(getattr(value, item.name))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            yield from _iter_strings(item)


def _preflight_projection(projection: CaseReportProjection, regular_chars: frozenset[int], bold_chars: frozenset[int]) -> None:
    for text in _iter_strings(projection):
        _validate_text(_normalise_text(text), regular_chars)
    controlled = tuple(_SECTION_TITLES.values()) + tuple(_OUTLINE_SECTION_TITLES.values()) + (
        "Renderer version", "Output profile", "Report projection ID", "Manifest ID",
        "Projection payload SHA-256", "Projection schema version", "Projector version",
        "Case ID", "Case name", "Case number", "Claimant", "Respondent", "Case status",
        "Court or tribunal", "Raw value", "Label", "Explanation", "Qualification code",
        "Direct Findings", "Higher-Order Findings", "Event Assertions", "Source Fingerprints",
    )
    for text in controlled:
        _validate_text(text, bold_chars)


def _escape_paragraph_text(value: object) -> str:
    text = _normalise_text(value)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("legalrag-title", fontName=_BOLD_FONT_NAME, fontSize=18, leading=22, spaceBefore=0, spaceAfter=12, keepWithNext=1, textColor="black"),
        "section": ParagraphStyle("legalrag-section", fontName=_BOLD_FONT_NAME, fontSize=14, leading=18, spaceBefore=0, spaceAfter=10, keepWithNext=1, textColor="black"),
        "item": ParagraphStyle("legalrag-item", fontName=_BOLD_FONT_NAME, fontSize=11.5, leading=14, spaceBefore=0, spaceAfter=6, keepWithNext=1, textColor="black"),
        "sub": ParagraphStyle("legalrag-sub", fontName=_BOLD_FONT_NAME, fontSize=10.5, leading=13, spaceBefore=2, spaceAfter=5, keepWithNext=1, textColor="black"),
        "label": ParagraphStyle("legalrag-label", fontName=_BOLD_FONT_NAME, fontSize=8.5, leading=11, spaceBefore=4, spaceAfter=1, keepWithNext=1, textColor="black"),
        "body": ParagraphStyle("legalrag-body", fontName=_REGULAR_FONT_NAME, fontSize=9, leading=12, spaceBefore=0, spaceAfter=4, allowWidows=0, allowOrphans=0, textColor="black"),
        "compact": ParagraphStyle("legalrag-compact", fontName=_REGULAR_FONT_NAME, fontSize=8, leading=10, spaceBefore=0, spaceAfter=3, textColor="black"),
        "empty": ParagraphStyle("legalrag-empty", fontName=_REGULAR_FONT_NAME, fontSize=9, leading=12, spaceBefore=0, spaceAfter=4, textColor="black"),
        "footer": ParagraphStyle("legalrag-footer", fontName=_REGULAR_FONT_NAME, fontSize=8, leading=10, alignment=TA_CENTER),
    }


class _Story:
    def __init__(self, projection: CaseReportProjection, audit: _RenderAudit) -> None:
        self.projection = projection
        self.audit = audit
        self.story: list[Flowable] = []
        self.styles = _styles()
        self.citation_ordinals = {cid: i for i, cid in enumerate(projection.manifest.ordered_citation_ids, start=1)}
        self.citation_destinations = {cid: _semantic_id("citation", cid) for cid in self.citation_ordinals}
        self.cross_issue_ids = {item.finding_id for item in projection.cross_issue_findings}

    def add(self, flowable: Flowable) -> None:
        self.story.append(flowable)

    def marker(self, destination: str, *, outline_label: str | None = None, outline_level: int | None = None) -> None:
        self.audit.destination(destination, outline_label=outline_label, outline_level=outline_level)
        self.add(_DestinationMarker(destination, outline_label, outline_level))

    def heading(self, text: str, level: str) -> None:
        self.add(Paragraph(_escape_paragraph_text(text), self.styles[level]))

    def field(self, label: str, value: object | None, *, compact: bool = False) -> None:
        self.add(Paragraph(_escape_paragraph_text(label), self.styles["label"]))
        rendered = ABSENT_VALUE_TEXT if value is None or value == "" else _normalise_text(value)
        self.add(Paragraph(_escape_paragraph_text(rendered), self.styles["compact" if compact else "body"]))

    def values(self, label: str, values: Sequence[object], *, compact: bool = True) -> None:
        self.add(Paragraph(_escape_paragraph_text(label), self.styles["label"]))
        if not values:
            self.add(Paragraph(_escape_paragraph_text(ABSENT_VALUE_TEXT), self.styles["body"]))
            return
        for value in values:
            self.add(Paragraph(_escape_paragraph_text(f"- {value}"), self.styles["compact" if compact else "body"]))

    def coordinates(self, label: str, values: Sequence[Sequence[object]]) -> None:
        self.values(label, tuple(" | ".join(str(item) for item in value) for value in values), compact=True)

    def empty(self) -> None:
        self.add(Paragraph(_escape_paragraph_text(EMPTY_SECTION_TEXT), self.styles["empty"]))

    def links(self, label: str, citation_ids: Sequence[str]) -> None:
        self.add(Paragraph(_escape_paragraph_text(label), self.styles["label"]))
        if not citation_ids:
            self.add(Paragraph(_escape_paragraph_text(ABSENT_VALUE_TEXT), self.styles["body"]))
            return
        links: list[str] = []
        for cid in citation_ids:
            if cid not in self.citation_ordinals:
                raise ValueError(f"Unknown renderer citation ID {cid!r}.")
            target = self.citation_destinations[cid]
            self.audit.link(target)
            label_text = _escape_paragraph_text(f"Evidence {self.citation_ordinals[cid]} — {cid}")
            links.append(f'<link href="#{target}">{label_text}</link>')
        self.add(Paragraph(", ".join(links), self.styles["body"]))

    def internal_reference(self, label: str, target: str) -> None:
        self.audit.link(target)
        self.add(Paragraph(f'<link href="#{target}">{_escape_paragraph_text(label)}</link>', self.styles["body"]))

    def status(self, *, section_key: str, title: str, item_id: str, index: int, value: StatusView, global_item: bool = True) -> None:
        self.audit.status(section_key=section_key, item_id=item_id, index=index, value=value, global_item=global_item)
        self.heading(title, "sub")
        self.field("Raw value", value.raw_value, compact=True)
        self.field("Label", value.label)
        self.field("Explanation", value.explanation)
        self.field("Qualification code", value.qualification_code, compact=True)

    def provenance(self, values: Sequence[ResolvedProvenance], *, title: str = "Resolved provenance") -> None:
        self.heading(title, "sub")
        if not values:
            self.empty()
            return
        for ordinal, item in enumerate(values, start=1):
            self.heading(f"Provenance {ordinal}", "label")
            self.field("Provenance type", item.provenance_type, compact=True)
            self.values("Exact identity parts", item.identity, compact=True)
            self.field("Display label", item.display_label)
            self.field("Raw role or status", item.raw_role_or_status, compact=True)
            self.field("Identity-only", str(item.identity_only).lower(), compact=True)
            self.field("Qualification text", item.qualification_text or ABSENT_VALUE_TEXT)
            self.links("Citations", item.citation_ids)

    def statements(self, title: str, statements: Sequence[ReportStatement]) -> None:
        self.heading(title, "sub")
        if not statements:
            self.empty()
            return
        for ordinal, statement in enumerate(statements, start=1):
            dest = _semantic_id("statement", statement.report_statement_id)
            self.marker(dest)
            self.audit.rendered_statement_ids.append(statement.report_statement_id)
            self.heading(f"Statement {ordinal}", "label")
            self.field("Statement ID", statement.report_statement_id, compact=True)
            self.field("Category", statement.category, compact=True)
            self.field("Text", statement.text)
            self.values("Evidence keys", statement.evidence_keys, compact=True)
            self.links("Citations", statement.citation_ids)

    def temporal_extent(self, value: TemporalExtentReport | None) -> None:
        self.heading("Temporal extent", "sub")
        if value is None:
            self.field("Temporal extent", None)
            return
        for label, item, compact in (
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
            self.field(label, item, compact=compact)

    def finding(self, finding: FindingReport, *, ordinal: int, section_key: str, cross_issue_heading: bool, global_status: bool = True) -> None:
        dest = _semantic_id("finding", finding.finding_id)
        outline_label = f"Cross-Issue Finding {ordinal}" if cross_issue_heading else None
        self.marker(dest, outline_label=outline_label, outline_level=1 if outline_label else None)
        self.heading(outline_label or f"Finding {ordinal}", "item" if cross_issue_heading else "sub")
        for label, item in (
            ("Finding ID", finding.finding_id),
            ("Finding type", finding.finding_type),
            ("Scope", finding.scope),
            ("Category", finding.category),
            ("Origin", finding.origin),
        ):
            self.field(label, item, compact=True)
        self.values("Analytical bases", finding.analytical_bases, compact=True)
        self.status(section_key=section_key, title="Finding status", item_id=finding.finding_id, index=0, value=finding.status, global_item=global_status)
        self.status(section_key=section_key, title="Finding confidence", item_id=finding.finding_id, index=1, value=finding.confidence, global_item=global_status)
        self.field("Summary", finding.summary)
        self.field("Controlled explanation", finding.controlled_explanation or ABSENT_VALUE_TEXT)
        self.values("Issue IDs", finding.issue_ids, compact=True)
        self.coordinates("Element coordinates", finding.element_coordinates)
        self.values("Related finding IDs", finding.related_finding_ids, compact=True)
        self.provenance(finding.provenance)
        self.links("Citations", finding.citation_ids)

    def cross_issue_reference(self, finding: FindingReport) -> None:
        target = _semantic_id("finding", finding.finding_id)
        self.internal_reference(f"Cross-Issue Finding — {finding.finding_id}", target)
        self.field("Raw finding status", finding.status.raw_value, compact=True)
        self.field("Raw confidence", finding.confidence.raw_value, compact=True)
        self.field("Status qualification", finding.status.qualification_code, compact=True)
        self.field("Confidence qualification", finding.confidence.qualification_code, compact=True)

    def element(self, element: ElementReport, ordinal: int) -> None:
        section_key = "issues"
        coordinate = f"{element.issue_analysis_id}|{element.element_id}"
        self.audit.represent(section_key, coordinate)
        self.marker(_semantic_id("element", element.issue_analysis_id, element.element_id))
        self.heading(f"Element {ordinal}", "sub")
        self.field("Issue analysis ID", element.issue_analysis_id, compact=True)
        self.field("Element ID", element.element_id, compact=True)
        self.field("Element name", element.element_name)
        self.field("Legal question", element.legal_question)
        self.status(section_key=section_key, title="Analysis status", item_id=coordinate, index=0, value=element.analysis_status)
        self.status(section_key=section_key, title="Analysis confidence", item_id=coordinate, index=1, value=element.analysis_confidence)
        self.statements("Established matters", element.established_matters)
        self.statements("Supported matters", element.supported_matters)
        self.statements("Not-supported matters", element.not_supported_matters)
        self.statements("Source assertions", element.source_assertions)
        self.values("Unresolved matters", element.unresolved_matters, compact=False)
        self.field("Legal significance", element.legal_significance)
        self.field("Frozen provisional analysis", element.provisional_analysis)
        self.values("Linked direct finding IDs", element.linked_direct_finding_ids, compact=True)
        self.values("Linked higher-order finding IDs", element.linked_higher_order_finding_ids, compact=True)
        self.values("Linked gap IDs", element.linked_gap_ids, compact=True)
        self.values("Linked risk IDs", element.linked_risk_ids, compact=True)

    def issue(self, issue: IssueReport, ordinal: int) -> None:
        section_key = "issues"
        self.audit.represent(section_key, issue.issue_analysis_id)
        self.marker(_semantic_id("issue", issue.issue_analysis_id), outline_label=f"Issue {ordinal}", outline_level=1)
        self.heading(f"Issue {ordinal}", "item")
        for label, item, compact in (
            ("Issue analysis ID", issue.issue_analysis_id, True),
            ("Issue-definition ID", issue.issue_definition_id, True),
            ("Issue-definition version", issue.issue_definition_version, True),
            ("Issue name", issue.issue_name, False),
            ("Original user question", issue.original_user_question, False),
            ("Issue summary", issue.issue_summary, False),
        ):
            self.field(label, item, compact=compact)
        self.status(section_key=section_key, title="Position status", item_id=issue.issue_analysis_id, index=0, value=issue.position_status)
        self.status(section_key=section_key, title="Position confidence", item_id=issue.issue_analysis_id, index=1, value=issue.confidence)
        self.values("Material finding IDs", issue.material_finding_ids, compact=True)
        self.values("Conflict IDs", issue.conflict_ids, compact=True)
        self.values("Gap IDs", issue.gap_ids, compact=True)
        self.values("Risk IDs", issue.risk_ids, compact=True)
        for idx, element in enumerate(issue.elements, start=1):
            self.element(element, idx)
        self.heading("Direct Findings", "sub")
        if not issue.direct_findings:
            self.empty()
        for idx, finding in enumerate(issue.direct_findings, start=1):
            self.audit.represent(section_key, finding.finding_id)
            self.finding(finding, ordinal=idx, section_key=section_key, cross_issue_heading=False)
        self.heading("Higher-Order Findings", "sub")
        if not issue.higher_order_findings:
            self.empty()
        non_cross = 0
        for finding in issue.higher_order_findings:
            self.audit.represent(section_key, finding.finding_id)
            if finding.finding_id in self.cross_issue_ids or finding.finding_type == _CROSS_ISSUE_FINDING_TYPE:
                self.audit.status(section_key=section_key, item_id=finding.finding_id, index=0, value=finding.status, global_item=False)
                self.audit.status(section_key=section_key, item_id=finding.finding_id, index=1, value=finding.confidence, global_item=False)
                self.cross_issue_reference(finding)
            else:
                non_cross += 1
                self.finding(finding, ordinal=non_cross, section_key=section_key, cross_issue_heading=False)

    def assertion(self, assertion: EventAssertionReport, ordinal: int) -> None:
        section_key = "chronology"
        coordinate = f"{assertion.event_id}|{assertion.assertion_id}"
        self.audit.represent(section_key, coordinate)
        self.marker(_semantic_id("assertion", assertion.event_id, assertion.assertion_id))
        self.heading(f"Assertion {ordinal}", "label")
        for label, item, compact in (
            ("Event ID", assertion.event_id, True),
            ("Assertion ID", assertion.assertion_id, True),
            ("Description", assertion.description, False),
            ("Issue analysis ID", assertion.issue_analysis_id, True),
            ("Element ID", assertion.element_id, True),
            ("Source proposition index", assertion.source_proposition_index, True),
            ("Evidence key", assertion.evidence_key, True),
        ):
            self.field(label, item, compact=compact)
        self.links("Citation", (assertion.citation_id,))
        self.status(section_key=section_key, title="Occurrence status", item_id=assertion.assertion_id, index=0, value=assertion.occurrence_status)
        self.status(section_key=section_key, title="Timing status", item_id=assertion.assertion_id, index=1, value=assertion.timing_status)
        self.status(section_key=section_key, title="Confidence", item_id=assertion.assertion_id, index=2, value=assertion.confidence)
        self.temporal_extent(assertion.temporal_extent)
        self.field("Extraction basis", assertion.extraction_basis, compact=True)

    def event(self, event: EventReport, ordinal: int) -> None:
        section_key = "chronology"
        self.audit.represent(section_key, event.event_id)
        self.marker(_semantic_id("event", event.event_id), outline_label=f"Event {ordinal}", outline_level=1)
        self.heading(f"Event {ordinal}", "item")
        for label, item, compact in (
            ("Event ID", event.event_id, True),
            ("Event type", event.event_type, True),
            ("Description", event.description, False),
            ("Normalised event core", event.normalized_event_core, False),
            ("Date or period", event.canonical_temporal_extent.display_text if event.canonical_temporal_extent else None, False),
        ):
            self.field(label, item, compact=compact)
        self.status(section_key=section_key, title="Occurrence status", item_id=event.event_id, index=0, value=event.occurrence_status)
        self.status(section_key=section_key, title="Timing status", item_id=event.event_id, index=1, value=event.timing_status)
        self.status(section_key=section_key, title="Confidence", item_id=event.event_id, index=2, value=event.confidence)
        self.temporal_extent(event.canonical_temporal_extent)
        self.values("Participants", event.participants, compact=False)
        self.values("Evidence keys", event.evidence_keys, compact=True)
        self.links("Citations", event.citation_ids)
        self.values("Related issue IDs", event.related_issue_ids, compact=True)
        self.coordinates("Related element coordinates", event.related_element_coordinates)
        self.heading("Event Assertions", "sub")
        if not event.assertions:
            self.empty()
        for idx, assertion in enumerate(event.assertions, start=1):
            self.assertion(assertion, idx)

    def conflict(self, conflict: ConflictReport, ordinal: int) -> None:
        key = "conflicts"
        self.audit.represent(key, conflict.conflict_id)
        self.marker(_semantic_id("conflict", conflict.conflict_id), outline_label=f"Conflict {ordinal}", outline_level=1)
        self.heading(f"Conflict {ordinal}", "item")
        self.field("Conflict ID", conflict.conflict_id, compact=True)
        self.field("Conflict type", conflict.conflict_type, compact=True)
        self.field("Scope", conflict.scope, compact=True)
        self.field("Subject", conflict.subject)
        self.status(section_key=key, title="Conflict status", item_id=conflict.conflict_id, index=0, value=conflict.status)
        self.status(section_key=key, title="Materiality", item_id=conflict.conflict_id, index=1, value=conflict.materiality)
        self.provenance(conflict.side_a, title="Side A resolved provenance")
        self.provenance(conflict.side_b, title="Side B resolved provenance")
        self.values("Related issue IDs", conflict.related_issue_ids, compact=True)
        self.links("Citations", conflict.citation_ids)

    def gap(self, gap: GapReport, ordinal: int) -> None:
        key = "evidence_gaps"
        self.audit.represent(key, gap.gap_id)
        self.marker(_semantic_id("gap", gap.gap_id), outline_label=f"Gap {ordinal}", outline_level=1)
        self.heading(f"Evidence Gap {ordinal}", "item")
        self.field("Gap ID", gap.gap_id, compact=True)
        self.field("Gap type", gap.gap_type, compact=True)
        self.field("Scope", gap.scope, compact=True)
        self.field("Issue analysis ID", gap.issue_analysis_id, compact=True)
        self.field("Element ID", gap.element_id, compact=True)
        self.field("Description", gap.description)
        self.status(section_key=key, title="Materiality", item_id=gap.gap_id, index=0, value=gap.materiality)
        self.field("Unresolved question", gap.unresolved_question)
        self.provenance(gap.provenance)
        self.links("Citations", gap.citation_ids)
        self.values("Related finding IDs", gap.related_finding_ids, compact=True)

    def risk(self, risk: RiskReport, ordinal: int) -> None:
        key = "risk_areas"
        self.audit.represent(key, risk.risk_id)
        self.marker(_semantic_id("risk", risk.risk_id), outline_label=f"Risk {ordinal}", outline_level=1)
        self.heading(f"Risk Area {ordinal}", "item")
        self.field("Risk ID", risk.risk_id, compact=True)
        self.field("Risk type", risk.risk_type, compact=True)
        self.field("Scope", risk.scope, compact=True)
        self.status(section_key=key, title="Materiality", item_id=risk.risk_id, index=0, value=risk.materiality)
        self.field("Description", risk.description)
        self.field("Classification explanation", risk.classification_explanation)
        self.values("Basis finding IDs", risk.basis_finding_ids, compact=True)
        self.values("Conflict IDs", risk.conflict_ids, compact=True)
        self.values("Gap IDs", risk.gap_ids, compact=True)
        self.values("Affected issue IDs", risk.affected_issue_ids, compact=True)
        self.provenance(risk.provenance)
        self.links("Citations", risk.citation_ids)

    def question(self, question: PriorityQuestionReport, ordinal: int) -> None:
        key = "priority_questions"
        self.audit.represent(key, question.question_id)
        self.marker(_semantic_id("question", question.question_id), outline_label=f"Question {ordinal}", outline_level=1)
        self.heading(f"Priority Question {ordinal}", "item")
        self.field("Question ID", question.question_id, compact=True)
        self.field("Exact question", question.question)
        self.status(section_key=key, title="Priority", item_id=question.question_id, index=0, value=question.priority)
        self.field("Basis type", question.basis_type, compact=True)
        self.values("Affected issue IDs", question.affected_issue_ids, compact=True)
        self.values("Affected element IDs", question.affected_element_ids, compact=True)
        self.values("Finding IDs", question.finding_ids, compact=True)
        self.values("Gap IDs", question.gap_ids, compact=True)
        self.values("Conflict IDs", question.conflict_ids, compact=True)
        self.provenance(question.provenance)
        self.links("Citations", question.citation_ids)

    def citation(self, citation: CitationRecord, ordinal: int) -> None:
        key = "evidence_appendix"
        self.audit.represent(key, citation.citation_id)
        dest = self.citation_destinations[citation.citation_id]
        self.marker(dest, outline_label=f"Evidence {ordinal}", outline_level=1)
        self.audit.rendered_citation_ids.append(citation.citation_id)
        self.heading(f"Evidence {ordinal}", "item")
        self.field("Display ordinal", ordinal, compact=True)
        self.field("Canonical citation ID", citation.citation_id, compact=True)
        self.field("Evidence key", citation.evidence_key, compact=True)
        self.field("Citation text", citation.citation)
        self.field("Document name", citation.document_name)
        self.field("Document ID", citation.document_id, compact=True)
        self.field("Page", citation.page, compact=True)
        self.field("Chunk ID", citation.chunk_id, compact=True)
        self.field("Date", citation.date)
        self.field("Author", citation.author)
        self.values("Parties", citation.parties, compact=False)
        self.field("Source type", citation.source_type, compact=True)
        self.field("Evidence status", citation.evidence_status, compact=True)
        self.field("Provenance type", citation.provenance_type, compact=True)
        self.field("Provenance basis", citation.provenance_basis, compact=True)
        self.field("Provenance confidence", citation.provenance_confidence, compact=True)
        self.coordinates("EvidenceUse coordinates", citation.evidence_use_coordinates)

    def start_section(self, key: str) -> None:
        if self.story:
            self.add(PageBreak())
        self.audit.start_section(key)
        dest = _section_id(key)
        self.marker(dest, outline_label=_OUTLINE_SECTION_TITLES[key], outline_level=0)
        self.heading(_SECTION_TITLES[key], "title" if key == "report_header" else "section")


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
        raise ValueError("Rendered PDF section order does not match ReportManifest.")
    for section in manifest.sections:
        if audit.section_item_sets.get(section.section_key, set()) != set(section.ordered_item_ids):
            raise ValueError(f"Rendered PDF section {section.section_key!r} does not account for manifest items.")
        if tuple(audit.section_statuses.get(section.section_key, ())) != section.raw_status_values:
            raise ValueError(f"Rendered PDF section {section.section_key!r} changed raw status inventory.")
        if tuple(audit.section_qualifications.get(section.section_key, ())) != section.qualification_codes:
            raise ValueError(f"Rendered PDF section {section.section_key!r} changed qualification inventory.")
    if audit.global_statuses != dict(manifest.raw_status_inventory):
        raise ValueError("Rendered PDF does not account for manifest raw-status inventory.")
    if audit.global_qualifications != dict(manifest.qualification_inventory):
        raise ValueError("Rendered PDF does not account for manifest qualification inventory.")
    if tuple(audit.rendered_statement_ids) != _all_statement_ids(projection):
        raise ValueError("Rendered PDF does not account for every ReportStatement ID in order.")
    if tuple(audit.rendered_citation_ids) != manifest.ordered_citation_ids:
        raise ValueError("Rendered PDF evidence appendix does not preserve manifest order.")
    if not set(audit.internal_targets) <= audit.primary_destinations:
        missing = sorted(set(audit.internal_targets) - audit.primary_destinations)
        raise ValueError(f"Rendered PDF contains unresolved internal targets: {missing}.")
    if set(manifest.ordered_finding_ids) != _all_finding_ids(projection):
        raise ValueError("Projection finding inventory does not match ReportManifest.")
    if tuple(issue.issue_analysis_id for issue in projection.issues) != manifest.ordered_issue_ids:
        raise ValueError("Rendered PDF issue source order does not match ReportManifest.")
    elements = tuple(f"{issue.issue_analysis_id}|{element.element_id}" for issue in projection.issues for element in issue.elements)
    if elements != manifest.ordered_element_coordinates:
        raise ValueError("Rendered PDF element source order does not match ReportManifest.")
    if tuple(event.event_id for event in projection.chronology) != manifest.ordered_event_ids:
        raise ValueError("Rendered PDF event source order does not match ReportManifest.")
    assertions = tuple(f"{event.event_id}|{assertion.assertion_id}" for event in projection.chronology for assertion in event.assertions)
    if assertions != manifest.ordered_event_assertion_coordinates:
        raise ValueError("Rendered PDF assertion source order does not match ReportManifest.")


def _build_story(projection: CaseReportProjection, audit: _RenderAudit) -> list[Flowable]:
    b = _Story(projection, audit)

    b.start_section("report_header")
    audit.represent("report_header", projection.case_header.case_id)
    for label, item, compact in (
        ("Renderer version", PDF_RENDERER_VERSION, True),
        ("Output profile", PDF_OUTPUT_PROFILE, True),
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
        b.field(label, item, compact=compact)

    b.start_section("analytical_lineage")
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
        b.field(label, item, compact=True)
    b.values("Source analysis IDs", projection.lineage.source_analysis_ids, compact=True)
    b.coordinates("Issue-definition lineage", projection.lineage.issue_definition_lineage)
    b.heading("Source Fingerprints", "sub")
    b.field("Foundation SHA-256", projection.source_foundation_sha256, compact=True)
    b.field("Matrices SHA-256", projection.source_matrices_sha256, compact=True)
    b.field("Chronology SHA-256", projection.source_chronology_sha256, compact=True)
    b.field("Synthesis SHA-256", projection.source_synthesis_sha256, compact=True)
    b.field("Metadata SHA-256", projection.source_metadata_sha256, compact=True)

    b.start_section("overall_state")
    audit.represent("overall_state", "overall_state")
    b.status(section_key="overall_state", title="Overall state", item_id="overall_state", index=0, value=projection.overall_state.state)
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
        b.field(label, value, compact=True)
    b.field("Count qualification", projection.overall_state.count_qualification)

    b.start_section("issues")
    if not projection.issues:
        b.empty()
    for idx, issue in enumerate(projection.issues, start=1):
        b.issue(issue, idx)

    b.start_section("chronology")
    if not projection.chronology:
        b.empty()
    for idx, event in enumerate(projection.chronology, start=1):
        b.event(event, idx)

    b.start_section("cross_issue_findings")
    if not projection.cross_issue_findings:
        b.empty()
    for idx, finding in enumerate(projection.cross_issue_findings, start=1):
        audit.represent("cross_issue_findings", finding.finding_id)
        b.finding(finding, ordinal=idx, section_key="cross_issue_findings", cross_issue_heading=True)

    b.start_section("conflicts")
    if not projection.conflicts:
        b.empty()
    for idx, conflict in enumerate(projection.conflicts, start=1):
        b.conflict(conflict, idx)

    b.start_section("evidence_gaps")
    if not projection.gaps:
        b.empty()
    for idx, gap in enumerate(projection.gaps, start=1):
        b.gap(gap, idx)

    b.start_section("risk_areas")
    if not projection.risks:
        b.empty()
    for idx, risk in enumerate(projection.risks, start=1):
        b.risk(risk, idx)

    b.start_section("priority_questions")
    if not projection.priority_questions:
        b.empty()
    for idx, question in enumerate(projection.priority_questions, start=1):
        b.question(question, idx)

    b.start_section("evidence_appendix")
    if not projection.citations:
        b.empty()
    by_id = {item.citation_id: item for item in projection.citations}
    for cid in projection.manifest.ordered_citation_ids:
        b.citation(by_id[cid], b.citation_ordinals[cid])

    b.start_section("glossary")
    if not projection.glossary:
        b.empty()
    for idx, entry in enumerate(projection.glossary, start=1):
        audit.represent("glossary", entry.code)
        audit.section_qualifications["glossary"].append(entry.code)
        b.marker(_semantic_id("glossary", entry.code))
        b.heading(f"Glossary Entry {idx}", "item")
        b.field("Code", entry.code, compact=True)
        b.field("Label", entry.label)
        b.field("Explanation", entry.explanation)

    return b.story


def _page_ref_keys(reader: PdfReader) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for page in reader.pages:
        ref = getattr(page, "indirect_reference", None)
        if ref is not None:
            out.add((int(ref.idnum), int(ref.generation)))
    return out


def _walk_actions(value: object, seen: set[int] | None = None) -> Iterable[dict]:
    if seen is None:
        seen = set()
    obj_id = id(value)
    if obj_id in seen:
        return
    seen.add(obj_id)
    try:
        resolved = value.get_object() if hasattr(value, "get_object") else value
    except Exception:
        resolved = value
    if isinstance(resolved, dict):
        yield resolved
        for item in resolved.values():
            yield from _walk_actions(item, seen)
    elif isinstance(resolved, (list, tuple)):
        for item in resolved:
            yield from _walk_actions(item, seen)


def _flatten_outline(outline: Sequence[object], level: int = 0) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    current_parent_level = level
    for item in outline:
        if isinstance(item, list):
            result.extend(_flatten_outline(item, current_parent_level + 1))
        else:
            title = getattr(item, "title", None)
            if title is None and isinstance(item, dict):
                title = item.get("/Title")
            result.append((level, str(title)))
            current_parent_level = level
    return result


def _validate_pdf_structure(pdf_bytes: bytes, *, expected_outline: Sequence[tuple[int, str, str]]) -> int:
    reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    if reader.is_encrypted:
        raise ValueError("M5.4 PDF must not be encrypted.")
    page_count = len(reader.pages)
    if page_count < 1:
        raise ValueError("M5.4 PDF must contain at least one page.")
    tolerance = 1e-4
    for page in reader.pages:
        box = page.mediabox
        values = tuple(float(x) for x in (box.left, box.bottom, box.right, box.top))
        expected = (0.0, 0.0, _PAGE_WIDTH, _PAGE_HEIGHT)
        if any(abs(a - b) > tolerance for a, b in zip(values, expected)):
            raise ValueError(f"PDF page MediaBox is not frozen A4: {values!r}.")

    metadata = reader.metadata or {}
    expected_metadata = {
        "/Title": "LegalRAG Pro — Deterministic Case Report",
        "/Author": "LegalRAG Pro",
        "/Subject": "Deterministic Case Report",
        "/Creator": PDF_RENDERER_VERSION,
        "/Producer": "LegalRAG Pro / ReportLab 5.0.0",
        "/Keywords": "",
        "/CreationDate": "D:20000101000000+00'00'",
        "/ModDate": "D:20000101000000+00'00'",
    }
    for key, value in expected_metadata.items():
        if str(metadata.get(key, "")) != value:
            raise ValueError(f"PDF metadata mismatch for {key}.")
    root = reader.trailer["/Root"]
    if str(root.get("/Lang", "")) != "en-GB":
        raise ValueError("PDF catalog /Lang must be en-GB.")
    for forbidden in ("/OpenAction", "/AcroForm"):
        if root.get(forbidden) is not None:
            raise ValueError(f"Forbidden PDF catalog entry present: {forbidden}.")
    names = root.get("/Names")
    if names is not None:
        names_obj = names.get_object() if hasattr(names, "get_object") else names
        if any(key in names_obj for key in ("/JavaScript", "/EmbeddedFiles")):
            raise ValueError("PDF must not contain JavaScript or embedded files.")

    expected_outline_simple = [(level, label) for level, label, _ in expected_outline]
    actual_outline = _flatten_outline(reader.outline)
    if actual_outline != expected_outline_simple:
        raise ValueError(f"PDF outline mismatch: {actual_outline!r} != {expected_outline_simple!r}.")

    page_refs = _page_ref_keys(reader)
    embedded_true_type = False
    unapproved_font = False
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        fonts = resources.get("/Font") or {}
        fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
        for font_ref in fonts.values():
            font = font_ref.get_object() if hasattr(font_ref, "get_object") else font_ref
            base = str(font.get("/BaseFont", ""))
            if any(name in base for name in _BASE14_NAMES):
                unapproved_font = True
            descriptor = font.get("/FontDescriptor")
            if descriptor is not None:
                descriptor = descriptor.get_object() if hasattr(descriptor, "get_object") else descriptor
                if descriptor.get("/FontFile2") is not None:
                    embedded_true_type = True
        annots = page.get("/Annots") or []
        annots = annots.get_object() if hasattr(annots, "get_object") else annots
        for annot_ref in annots:
            annot = annot_ref.get_object() if hasattr(annot_ref, "get_object") else annot_ref
            action = annot.get("/A")
            if action is not None:
                action = action.get_object() if hasattr(action, "get_object") else action
                if str(action.get("/S", "")) in {"/URI", "/JavaScript", "/Launch"}:
                    raise ValueError("PDF contains a forbidden external/executable link action.")
                dest = action.get("/D")
            else:
                dest = annot.get("/Dest")
            if dest is not None:
                dest = dest.get_object() if hasattr(dest, "get_object") else dest
                if isinstance(dest, (list, tuple)) and dest:
                    page_ref = dest[0]
                    if hasattr(page_ref, "idnum") and (int(page_ref.idnum), int(page_ref.generation)) not in page_refs:
                        raise ValueError("PDF internal link destination does not resolve to a valid page.")
    if not embedded_true_type:
        raise ValueError("PDF does not contain embedded TrueType font resources.")
    if unapproved_font:
        raise ValueError("PDF contains forbidden Base-14 font fallback.")

    for obj in _walk_actions(root):
        action_type = str(obj.get("/S", "")) if isinstance(obj, dict) else ""
        if action_type in {"/URI", "/JavaScript", "/Launch"}:
            raise ValueError("PDF contains forbidden action type.")
    return page_count


def _produce_pdf_report(projection: CaseReportProjection) -> PdfReport:
    if not isinstance(projection, CaseReportProjection):
        raise ValueError("projection must be a CaseReportProjection.")
    validate_case_report_projection(projection)
    _verify_runtime_versions()
    regular_chars, bold_chars = _register_and_verify_fonts()
    _preflight_projection(projection, regular_chars, bold_chars)

    audit = _RenderAudit()
    story = _build_story(projection, audit)
    _validate_audit(projection, audit)

    buffer = BytesIO()
    doc = _PdfDocTemplate(buffer)
    doc.build(story, canvasmaker=_InvariantCanvas)
    pdf_bytes = buffer.getvalue()
    if not pdf_bytes.startswith(b"%PDF-1.7"):
        raise ValueError("Generated PDF does not use frozen PDF 1.7 header.")
    page_count = _validate_pdf_structure(pdf_bytes, expected_outline=audit.outline_plan)
    pdf_hash = sha256(pdf_bytes).hexdigest()
    report_id = _derive_pdf_report_id(
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        pdf_sha256=pdf_hash,
    )
    return PdfReport(
        pdf_report_id=report_id,
        renderer_version=PDF_RENDERER_VERSION,
        output_profile=PDF_OUTPUT_PROFILE,
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        pdf_sha256=pdf_hash,
        page_count=page_count,
        report_manifest=projection.manifest,
        pdf=pdf_bytes,
    )


_PUBLIC_RENDERER_NAME = "render_" + "pdf_report"
_produce_pdf_report.__name__ = _PUBLIC_RENDERER_NAME
_produce_pdf_report.__qualname__ = _PUBLIC_RENDERER_NAME
globals()[_PUBLIC_RENDERER_NAME] = _produce_pdf_report

__all__ = [
    "ABSENT_VALUE_TEXT",
    "EMPTY_SECTION_TEXT",
    "PDF_FONT_PROFILE",
    "PDF_OUTPUT_PROFILE",
    "PDF_PYPDF_VERSION",
    "PDF_RENDERER_VERSION",
    "PDF_REPORTLAB_VERSION",
    "PDF_PYTHON_VERSION",
    "PdfReport",
    _PUBLIC_RENDERER_NAME,
]
