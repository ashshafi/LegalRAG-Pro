from __future__ import annotations

import ast
import builtins
import inspect
import re
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from case_reporting import CaseReportMetadata, dumps_case_report_projection
from case_reporting.html import (
    ABSENT_VALUE_TEXT,
    EMPTY_SECTION_TEXT,
    HTML_OUTPUT_PROFILE,
    HTML_RENDERER_VERSION,
    HtmlReport,
    render_html_report,
)
from case_reporting.markdown import render_markdown_report
from case_reporting.models import SECTION_KEYS
from test_case_reporting_markdown import (
    all_statement_ids,
    comprehensive_projection,
    empty_optional_projection,
)

FIXTURE = Path(__file__).parent / "fixtures" / "case_reporting" / "m53_full_audit.html"
GOLDEN_SHA256 = "637a61164b877f6a1254002821d7bc42bdaf76c0029421931306bd972db33241"
_ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "a", "header", "main",
    "section", "article", "div", "h1", "h2", "h3", "h4", "p", "dl", "dt",
    "dd", "ul", "li", "code", "strong", "span",
}


class _Inspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.attrs: list[tuple[str, str, str | None]] = []
        self.h1_count = 0
        self.style_count = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "h1":
            self.h1_count += 1
        if tag == "style":
            self.style_count += 1
        for name, value in attrs:
            self.attrs.append((tag, name, value))
            if name == "id" and value is not None:
                self.ids.append(value)
            if name == "href" and value is not None:
                self.hrefs.append(value)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def _inspect(html: str) -> _Inspector:
    parser = _Inspector()
    parser.feed(html)
    parser.close()
    return parser


def _semantic_ids(text: str) -> set[str]:
    return {
        value
        for value in re.findall(r'id="(legalrag-[A-Za-z0-9_-]+)"', text)
        if value != "legalrag-main"
    }


def _citation_ordinals(text: str) -> tuple[tuple[str, str], ...]:
    return tuple((ordinal, citation_id.replace("\\", "")) for ordinal, citation_id in re.findall(r"Evidence (\d+) — ([A-Za-z0-9._:/\\-]+)", text))


def test_renderer_versions_profile_and_immutable_result_are_frozen():
    projection = comprehensive_projection()
    result = render_html_report(projection)
    assert result.renderer_version == HTML_RENDERER_VERSION
    assert result.output_profile == HTML_OUTPUT_PROFILE
    assert result.report_projection_id == projection.report_projection_id
    assert result.manifest_id == projection.manifest.manifest_id
    assert result.projection_payload_sha256 == projection.projection_payload_sha256
    assert result.report_manifest is projection.manifest
    with pytest.raises(FrozenInstanceError):
        result.html = "changed"


def test_renderer_is_deterministic_and_byte_stable():
    projection = comprehensive_projection()
    first = render_html_report(projection)
    second = render_html_report(projection)
    assert second == first
    assert second.html == first.html
    assert second.html_sha256 == first.html_sha256
    assert second.html_report_id == first.html_report_id


def test_hash_and_renderer_identity_match_exact_bytes():
    result = render_html_report(comprehensive_projection())
    assert result.html_sha256 == sha256(result.html.encode("utf-8")).hexdigest()
    assert result.html_report_id
    assert result.html_sha256 not in result.html
    assert result.html_report_id not in result.html


def test_public_renderer_accepts_only_case_report_projection():
    with pytest.raises(ValueError, match="CaseReportProjection"):
        render_html_report("not a projection")


def test_public_renderer_revalidates_and_rejects_tampering():
    projection = comprehensive_projection()
    with pytest.raises(ValueError):
        render_html_report(replace(projection, projection_payload_sha256="0" * 64))


def test_standalone_html5_structure_and_head_metadata_are_exact():
    result = render_html_report(comprehensive_projection())
    html = result.html
    assert html.startswith('<!doctype html>\n<html lang="en">\n  <head>\n')
    expected = (
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="generator" content="case-report-html-renderer/1.0">',
        '<meta name="legalrag-output-profile" content="full-audit/1.0">',
        '<meta name="legalrag-report-projection-id"',
        '<meta name="legalrag-manifest-id"',
        '<meta name="legalrag-projection-payload-sha256"',
        '<title>LegalRAG Pro — Deterministic Case Report</title>',
        '<style>',
    )
    positions = [html.index(item) for item in expected]
    assert positions == sorted(positions)
    parser = _inspect(html)
    assert parser.h1_count == 1
    assert parser.style_count == 1
    assert html.endswith('</html>\n')


def test_all_twelve_sections_appear_in_exact_manifest_order():
    html = render_html_report(comprehensive_projection()).html
    positions = [html.index(f'id="legalrag-section-{key}"') for key in SECTION_KEYS]
    assert positions == sorted(positions)


def test_empty_sections_are_explicitly_rendered():
    projection = empty_optional_projection()
    html = render_html_report(projection).html
    for section in projection.manifest.sections:
        if section.is_empty:
            start = html.index(f'id="legalrag-section-{section.section_key}"')
            later = [html.find(f'id="legalrag-section-{key}"', start + 1) for key in SECTION_KEYS]
            later = [item for item in later if item != -1]
            end = min(later) if later else len(html)
            assert f'<p class="empty-state">{EMPTY_SECTION_TEXT}</p>' in html[start:end]


def test_all_raw_statuses_labels_explanations_and_qualifications_are_visible():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    for _, raw_value in projection.manifest.raw_status_inventory:
        assert f"<code>{raw_value}</code>" in html
    for _, qualification in projection.manifest.qualification_inventory:
        assert f"<code>{qualification}</code>" in html
    assert "<dt>Label</dt>" in html
    assert "<dt>Explanation</dt>" in html


def test_occurrence_and_timing_are_separate_for_events_and_assertions():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    event = projection.chronology[0]
    assert event.occurrence_status.raw_value == "supported"
    assert event.timing_status.raw_value == "established"
    assert html.count("<strong>Occurrence status</strong>") >= 1 + len(event.assertions)
    assert html.count("<strong>Timing status</strong>") >= 1 + len(event.assertions)
    assert "Established event" not in html


def test_neutral_medium_explanations_are_complete():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    assert projection.gaps[0].materiality.explanation in html
    assert projection.priority_questions[0].priority.explanation in html
    assert "not a comparative statement" in html
    assert "not an urgency" in html


def test_cross_issue_finding_has_one_primary_id_and_links_from_each_issue():
    projection = comprehensive_projection()
    result = render_html_report(projection)
    finding = projection.cross_issue_findings[0]
    token = __import__("base64").urlsafe_b64encode(finding.finding_id.encode()).decode().rstrip("=")
    semantic_id = f"legalrag-finding-{token}"
    assert result.html.count(f'id="{semantic_id}"') == 1
    assert result.html.count(f'href="#{semantic_id}"') == len(finding.issue_ids)


def test_all_report_statement_ids_are_rendered_once():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    for statement_id in all_statement_ids(projection):
        assert html.count(statement_id) == 1


def test_every_citation_has_one_primary_id_and_all_internal_links_resolve():
    result = render_html_report(comprehensive_projection())
    parser = _inspect(result.html)
    assert len(parser.ids) == len(set(parser.ids))
    assert all(href.startswith("#legalrag-") for href in parser.hrefs)
    targets = {href[1:] for href in parser.hrefs}
    assert targets <= set(parser.ids)
    for citation_id in result.report_manifest.ordered_citation_ids:
        token = __import__("base64").urlsafe_b64encode(citation_id.encode()).decode().rstrip("=")
        semantic_id = f"legalrag-citation-{token}"
        assert parser.ids.count(semantic_id) == 1
        assert citation_id in result.html


def test_every_event_assertion_is_fully_present():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    for event in projection.chronology:
        assert event.event_id in html
        for assertion in event.assertions:
            assert assertion.assertion_id in html
            assert assertion.description in html


def test_manifest_semantic_identity_sets_are_represented():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    manifest = projection.manifest
    for item_id in (
        *manifest.ordered_issue_ids,
        *manifest.ordered_finding_ids,
        *manifest.ordered_event_ids,
        *manifest.ordered_conflict_ids,
        *manifest.ordered_gap_ids,
        *manifest.ordered_risk_ids,
        *manifest.ordered_question_ids,
        *manifest.ordered_citation_ids,
    ):
        assert item_id in html


def test_missing_optional_values_use_exact_controlled_phrase():
    html = render_html_report(comprehensive_projection()).html
    assert ABSENT_VALUE_TEXT in html
    assert "<dt>Case name</dt>" in html


def test_html_escaping_and_injection_resistance_are_canonical():
    hostile = "# Heading\r\n<script>alert('x' & \"y\")</script> <img src=x onerror=alert(1)> javascript:\tΩ"
    metadata = CaseReportMetadata(case_name=hostile, claimant="<!-- injected -->")
    projection = comprehensive_projection(metadata=metadata, summary=hostile)
    html = render_html_report(projection).html
    assert "<script>alert" not in html
    assert "<img src" not in html
    assert "<!-- injected -->" not in html
    assert "&lt;script&gt;" in html
    assert "&#x27;x&#x27;" in html
    assert "&quot;y&quot;" in html
    assert "&amp;" in html
    assert "&#9;" in html
    assert "Ω" in html
    parser = _inspect(html)
    assert set(parser.tags) <= _ALLOWED_TAGS
    for _, name, value in parser.attrs:
        if value:
            assert hostile not in value
            assert "<script" not in value


def test_forbidden_control_characters_fail_closed():
    projection = comprehensive_projection(metadata=CaseReportMetadata(case_name="bad\x00value"))
    with pytest.raises(ValueError, match="forbidden control"):
        render_html_report(projection)


def test_allowed_html_vocabulary_and_no_external_resources():
    html = render_html_report(comprehensive_projection()).html
    parser = _inspect(html)
    assert set(parser.tags) <= _ALLOWED_TAGS
    assert all(href.startswith("#legalrag-") for href in parser.hrefs)
    prohibited = {"script", "iframe", "object", "embed", "form", "input", "button", "link", "img", "svg", "table", "details"}
    assert not prohibited & set(parser.tags)
    assert "@import" not in html
    assert "url(" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_stylesheet_is_fixed_accessible_and_does_not_hide_content():
    html = render_html_report(comprehensive_projection()).html
    style = html.split("<style>\n", 1)[1].split("\n    </style>", 1)[0]
    assert ".skip-link:focus" in style
    assert "white-space: pre-wrap" in style
    assert "display: none" in style  # print-only skip-link rule
    assert style.count("display: none") == 1
    assert "@media print" in style
    assert "content:" not in style


def test_deterministic_whitespace_contract():
    html = render_html_report(comprehensive_projection()).html
    assert "\r" not in html
    assert "\t" not in html
    assert html.endswith("\n")
    assert not html.endswith("\n\n")
    assert all(not line.endswith(" ") for line in html.splitlines())
    for line in html.splitlines():
        leading = len(line) - len(line.lstrip(" "))
        assert leading % 2 == 0


def test_renderer_does_not_mutate_projection():
    projection = comprehensive_projection()
    before = dumps_case_report_projection(projection)
    render_html_report(projection)
    assert dumps_case_report_projection(projection) == before


def test_renderer_performs_no_file_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("file I/O is prohibited")

    monkeypatch.setattr(builtins, "open", forbidden)
    assert isinstance(render_html_report(comprehensive_projection()), HtmlReport)


def test_renderer_public_signature_has_no_profile_fragment_or_unsafe_bypass():
    assert tuple(inspect.signature(render_html_report).parameters) == ("projection",)


def test_html_module_has_only_authorised_runtime_imports():
    path = Path(__file__).parents[1] / "src" / "case_reporting" / "html.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    relatives: set[str | None] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relatives.add(node.module)
            elif node.module:
                roots.add(node.module.split(".", 1)[0])
    assert roots <= {"__future__", "base64", "dataclasses", "hashlib", "html", "typing", "uuid"}
    assert relatives <= {"models", "validation"}


def test_html_module_contains_no_prohibited_dependencies_or_export_logic():
    path = Path(__file__).parents[1] / "src" / "case_reporting" / "html.py"
    source = path.read_text(encoding="utf-8")
    prohibited = (
        "case_reporting.markdown", "case_analysis", "legal_analysis", "case_management",
        "openai", "chromadb", "streamlit", "jinja", "BeautifulSoup", "lxml", "html5lib",
        "reportlab", "Path(", "write_text", "write_bytes",
    )
    for token in prohibited:
        assert token not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open"}


def test_renderer_fails_closed_when_internal_audit_omits_an_item(monkeypatch):
    import case_reporting.html as module

    original = module._RenderAudit.represent
    omitted = {"done": False}

    def skip_one(self, section_key, item_id):
        if section_key == "issues" and not omitted["done"]:
            omitted["done"] = True
            return None
        return original(self, section_key, item_id)

    monkeypatch.setattr(module._RenderAudit, "represent", skip_one)
    with pytest.raises(ValueError, match="manifest items"):
        render_html_report(comprehensive_projection())


def test_renderer_fails_closed_on_duplicate_primary_ids(monkeypatch):
    import case_reporting.html as module

    monkeypatch.setattr(module, "_semantic_id", lambda kind, *parts: "legalrag-duplicate")
    with pytest.raises(ValueError, match="Duplicate primary HTML ID"):
        render_html_report(comprehensive_projection())


def test_renderer_fails_closed_on_unresolved_internal_target(monkeypatch):
    import case_reporting.html as module

    original = module._link

    def broken(label, target, audit):
        return original(label, "legalrag-missing-target", audit)

    monkeypatch.setattr(module, "_link", broken)
    with pytest.raises(ValueError, match="unresolved internal links"):
        render_html_report(comprehensive_projection())


def test_cross_renderer_manifest_identity_anchor_and_citation_parity():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection)
    html = render_html_report(projection)
    assert markdown.report_manifest == html.report_manifest == projection.manifest
    assert _semantic_ids(markdown.markdown) == _semantic_ids(html.html)
    assert _citation_ordinals(markdown.markdown) == _citation_ordinals(html.html)
    assert markdown.report_manifest.raw_status_inventory == html.report_manifest.raw_status_inventory
    assert markdown.report_manifest.qualification_inventory == html.report_manifest.qualification_inventory


def test_golden_full_audit_fixture_is_governed_and_byte_exact():
    expected = FIXTURE.read_text(encoding="utf-8")
    actual = render_html_report(comprehensive_projection()).html
    assert sha256(expected.encode("utf-8")).hexdigest() == GOLDEN_SHA256
    assert actual == expected


def test_fixture_is_not_generated_or_written_by_the_test_suite():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"write_text", "write_bytes"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open"
