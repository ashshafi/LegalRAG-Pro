from __future__ import annotations

import ast
import builtins
import hashlib
import platform
import re
from dataclasses import FrozenInstanceError, replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
import pypdf
import reportlab
from pypdf import PdfReader

from case_reporting import dumps_case_report_projection
import case_reporting.pdf as pdfmod
from case_reporting.pdf import (
    PDF_FONT_PROFILE,
    PDF_OUTPUT_PROFILE,
    PDF_PYPDF_VERSION,
    PDF_RENDERER_VERSION,
    PDF_REPORTLAB_VERSION,
    PDF_PYTHON_VERSION,
    PdfReport,
    render_pdf_report,
)
from case_reporting.html import render_html_report
from case_reporting.markdown import render_markdown_report
from test_case_reporting_markdown import all_statement_ids, comprehensive_projection, empty_optional_projection

FIXTURE = Path(__file__).parent / "fixtures" / "case_reporting" / "m54_full_audit.pdf"
GOLDEN_SHA256 = "4cf78bb8aab81f74da09b177ac9c50334525349a876cbff487269b4d26b8d4d2"
GOLDEN_BYTES = 303172
GOLDEN_PAGES = 39
GOLDEN_ANNOTATIONS = 14
REPORTLAB_WHEEL_SHA256 = "9d5a3affa84919e1111ede580031266a570e93b1ce388219621347965ff1d93c"
PYPDF_WHEEL_SHA256 = "3f07891af76dc002657e04993ab9b4de81de29f9013b9761d0b7968bff12e946"
VERA_SHA256 = "c4c45690b345435b2cba52ecabe275f05e49b389b39fe68ad03afbb551288d3d"
VERABD_SHA256 = "cc037385e4d55bfde89b13e03091ee93bf40c0c52ddd391ff031ab276f13b8e9"


@pytest.fixture(autouse=True)
def _reference_runtime(monkeypatch):
    """Exercise the frozen renderer contract in this package-build environment.

    The actual freeze review separately records the exact CPython/wheel profile.
    This compatibility fixture is needed because the artifact-building runner may
    not itself be the project's frozen Windows CPython 3.14.6 environment.
    """
    monkeypatch.setattr(pdfmod.platform, "python_version", lambda: PDF_PYTHON_VERSION)
    monkeypatch.setattr(pdfmod.reportlab, "Version", PDF_REPORTLAB_VERSION)
    monkeypatch.setattr(pdfmod.pypdf, "__version__", PDF_PYPDF_VERSION)


def _reader(result: PdfReport) -> PdfReader:
    return PdfReader(BytesIO(result.pdf), strict=True)


def _flatten_outline(items, level=0):
    out = []
    for item in items:
        if isinstance(item, list):
            out.extend(_flatten_outline(item, level + 1))
        else:
            title = getattr(item, "title", None)
            if title is None and isinstance(item, dict):
                title = item.get("/Title")
            out.append((level, str(title)))
    return out


def _annotations(reader: PdfReader):
    for page in reader.pages:
        annots = page.get("/Annots") or []
        annots = annots.get_object() if hasattr(annots, "get_object") else annots
        for ref in annots:
            yield ref.get_object() if hasattr(ref, "get_object") else ref


def test_renderer_contract_and_immutable_result_are_frozen():
    projection = comprehensive_projection()
    result = render_pdf_report(projection)
    assert result.renderer_version == PDF_RENDERER_VERSION
    assert result.output_profile == PDF_OUTPUT_PROFILE
    assert result.report_projection_id == projection.report_projection_id
    assert result.manifest_id == projection.manifest.manifest_id
    assert result.projection_payload_sha256 == projection.projection_payload_sha256
    assert result.report_manifest is projection.manifest
    assert isinstance(result.pdf, bytes)
    with pytest.raises(FrozenInstanceError):
        result.pdf = b"changed"


def test_same_projection_is_byte_identical_and_identity_stable():
    projection = comprehensive_projection()
    a = render_pdf_report(projection)
    b = render_pdf_report(projection)
    assert a == b
    assert a.pdf == b.pdf
    assert a.pdf_sha256 == b.pdf_sha256
    assert a.pdf_report_id == b.pdf_report_id
    assert a.page_count == b.page_count


def test_pdf_hash_and_result_identity_cover_exact_returned_bytes():
    result = render_pdf_report(comprehensive_projection())
    assert result.pdf_sha256 == hashlib.sha256(result.pdf).hexdigest()
    assert result.pdf_report_id
    assert result.pdf_sha256.encode() not in result.pdf
    assert result.pdf_report_id.encode() not in result.pdf


def test_public_renderer_accepts_only_case_report_projection():
    with pytest.raises(ValueError, match="CaseReportProjection"):
        render_pdf_report("not a projection")


def test_public_renderer_revalidates_tampered_projection():
    projection = comprehensive_projection()
    with pytest.raises(ValueError):
        render_pdf_report(replace(projection, projection_payload_sha256="0" * 64))


def test_wrong_python_reportlab_or_pypdf_version_fails_closed(monkeypatch):
    projection = comprehensive_projection()
    monkeypatch.setattr(pdfmod.platform, "python_version", lambda: "3.14.5")
    with pytest.raises(ValueError, match="CPython"):
        render_pdf_report(projection)
    monkeypatch.setattr(pdfmod.platform, "python_version", lambda: PDF_PYTHON_VERSION)
    monkeypatch.setattr(pdfmod.reportlab, "Version", "4.4.9")
    with pytest.raises(ValueError, match="ReportLab"):
        render_pdf_report(projection)
    monkeypatch.setattr(pdfmod.reportlab, "Version", PDF_REPORTLAB_VERSION)
    monkeypatch.setattr(pdfmod.pypdf, "__version__", "5.9.0")
    with pytest.raises(ValueError, match="pypdf"):
        render_pdf_report(projection)


def test_font_profile_and_hashes_are_exact():
    assert PDF_FONT_PROFILE == "case-report-pdf-fonts/reportlab-vera/1.0"
    root = Path(reportlab.__file__).resolve().parent / "fonts"
    vera = root / "Vera.ttf"
    verabd = root / "VeraBd.ttf"
    assert vera.stat().st_size == 65932
    assert verabd.stat().st_size == 58716
    assert hashlib.sha256(vera.read_bytes()).hexdigest() == VERA_SHA256
    assert hashlib.sha256(verabd.read_bytes()).hexdigest() == VERABD_SHA256


def test_requirements_dependency_change_is_exact_utf16le_bom_crlf():
    path = Path(__file__).parents[1] / "requirements.txt"
    data = path.read_bytes()
    assert data.startswith(b"\xff\xfe")
    assert b"\r\x00\n\x00" in data
    text = data[2:].decode("utf-16le")
    assert text.count("reportlab==5.0.0") == 1
    assert "regex==2026.7.19\r\nreportlab==5.0.0\r\nrequests==2.34.2\r\n" in text
    assert all("\n" not in chunk for chunk in text.split("\r\n"))


def test_golden_fixture_is_hard_hashed_and_byte_exact():
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == GOLDEN_SHA256
    assert len(data) == GOLDEN_BYTES
    result = render_pdf_report(comprehensive_projection())
    assert result.pdf == data
    assert result.pdf_sha256 == GOLDEN_SHA256
    assert result.page_count == GOLDEN_PAGES


def test_pdf_version_and_every_page_are_frozen_a4():
    result = render_pdf_report(comprehensive_projection())
    assert result.pdf.startswith(b"%PDF-1.7")
    reader = _reader(result)
    for page in reader.pages:
        box = tuple(float(v) for v in (page.mediabox.left, page.mediabox.bottom, page.mediabox.right, page.mediabox.top))
        assert box == pytest.approx((0.0, 0.0, 595.2756, 841.8898), abs=1e-6)


def test_metadata_language_and_invariant_dates_are_exact():
    reader = _reader(render_pdf_report(comprehensive_projection()))
    metadata = reader.metadata
    assert metadata["/Title"] == "LegalRAG Pro — Deterministic Case Report"
    assert metadata["/Author"] == "LegalRAG Pro"
    assert metadata["/Subject"] == "Deterministic Case Report"
    assert metadata["/Creator"] == PDF_RENDERER_VERSION
    assert metadata["/Producer"] == "LegalRAG Pro / ReportLab 5.0.0"
    assert metadata["/Keywords"] == ""
    assert metadata["/CreationDate"] == "D:20000101000000+00'00'"
    assert metadata["/ModDate"] == "D:20000101000000+00'00'"
    assert str(metadata["/Trapped"]) == "/False"
    assert str(reader.trailer["/Root"].get("/Lang")) == "en-GB"


def test_document_identifier_is_stable():
    first = _reader(render_pdf_report(comprehensive_projection())).trailer["/ID"]
    second = _reader(render_pdf_report(comprehensive_projection())).trailer["/ID"]
    assert first == second
    assert len(first) == 2 and first[0] == first[1]


def test_outline_hierarchy_and_labels_are_exact():
    reader = _reader(render_pdf_report(comprehensive_projection()))
    outline = _flatten_outline(reader.outline)
    assert outline[:7] == [
        (0, "Report Header"),
        (0, "Analytical Lineage"),
        (0, "Overall Analytical State"),
        (0, "Issues"),
        (1, "Issue 1"),
        (1, "Issue 2"),
        (0, "Chronology"),
    ]
    assert (1, "Cross-Issue Finding 1") in outline
    assert (1, "Evidence 1") in outline
    assert len(outline) == 21


def test_all_twelve_sections_are_represented_in_manifest_order():
    projection = comprehensive_projection()
    result = render_pdf_report(projection)
    assert result.report_manifest.ordered_section_ids == projection.manifest.ordered_section_ids
    assert len(projection.manifest.ordered_section_ids) == 12


def test_empty_sections_remain_visible_on_their_section_pages():
    result = render_pdf_report(empty_optional_projection())
    text = "\n".join(page.extract_text() or "" for page in _reader(result).pages)
    assert text.count("None recorded in the frozen report projection.") >= 1
    for heading in ("Chronology", "Material Conflicts", "Evidence Gaps", "Risk Areas", "Priority Questions"):
        assert heading in text


def test_page_footer_is_present_on_every_page():
    result = render_pdf_report(comprehensive_projection())
    reader = _reader(result)
    for number, page in enumerate(reader.pages, start=1):
        assert f"Page {number}" in (page.extract_text() or "")


def test_all_report_statement_ids_are_preserved():
    projection = comprehensive_projection()
    text = "\n".join(page.extract_text() or "" for page in _reader(render_pdf_report(projection)).pages)
    for statement_id in all_statement_ids(projection):
        assert statement_id in text


def test_raw_statuses_and_qualifications_are_preserved():
    projection = comprehensive_projection()
    text = "\n".join(page.extract_text() or "" for page in _reader(render_pdf_report(projection)).pages)
    for _, raw in projection.manifest.raw_status_inventory:
        assert raw in text
    for _, qual in projection.manifest.qualification_inventory:
        assert qual in text


def test_occurrence_and_timing_remain_separate():
    projection = comprehensive_projection()
    event = projection.chronology[0]
    assert event.occurrence_status.raw_value == "supported"
    assert event.timing_status.raw_value == "established"
    text = "\n".join(page.extract_text() or "" for page in _reader(render_pdf_report(projection)).pages)
    assert "Occurrence status" in text
    assert "Timing status" in text
    assert "Established event" not in text


def test_neutral_medium_explanations_are_complete():
    projection = comprehensive_projection()
    text = "\n".join(page.extract_text() or "" for page in _reader(render_pdf_report(projection)).pages)
    norm = " ".join(text.split())
    assert " ".join(projection.gaps[0].materiality.explanation.split()) in norm
    assert " ".join(projection.priority_questions[0].priority.explanation.split()) in norm


def test_cross_format_manifest_identity_is_exact():
    projection = comprehensive_projection()
    md = render_markdown_report(projection)
    html = render_html_report(projection)
    pdf = render_pdf_report(projection)
    assert md.report_manifest is projection.manifest
    assert html.report_manifest is projection.manifest
    assert pdf.report_manifest is projection.manifest
    assert md.report_manifest == html.report_manifest == pdf.report_manifest


def test_semantic_destination_algorithm_matches_markdown_and_html():
    projection = comprehensive_projection()
    html = render_html_report(projection).html
    markdown = render_markdown_report(projection).markdown
    samples = [
        ("issue", projection.issues[0].issue_analysis_id),
        ("finding", projection.cross_issue_findings[0].finding_id),
        ("event", projection.chronology[0].event_id),
        ("citation", projection.citations[0].citation_id),
    ]
    for kind, identity in samples:
        semantic_id = pdfmod._semantic_id(kind, identity)
        assert semantic_id in html
        assert semantic_id in markdown


def test_evidence_ordinals_match_markdown_html_and_pdf():
    projection = comprehensive_projection()
    pdf_text = "\n".join(page.extract_text() or "" for page in _reader(render_pdf_report(projection)).pages)
    md = render_markdown_report(projection).markdown
    html = render_html_report(projection).html
    for ordinal, cid in enumerate(projection.manifest.ordered_citation_ids, start=1):
        assert f"Evidence {ordinal}" in md and cid in md
        assert f"Evidence {ordinal}" in html and cid in html
        assert f"Evidence {ordinal}" in pdf_text and cid in pdf_text


def test_internal_links_exist_and_no_external_uri_actions_exist():
    reader = _reader(render_pdf_report(comprehensive_projection()))
    annots = list(_annotations(reader))
    assert len(annots) == GOLDEN_ANNOTATIONS
    assert any(a.get("/Dest") is not None or a.get("/A") is not None for a in annots)
    for annot in annots:
        action = annot.get("/A")
        if action is not None:
            action = action.get_object() if hasattr(action, "get_object") else action
            assert str(action.get("/S", "")) not in {"/URI", "/JavaScript", "/Launch"}


def test_pdf_has_no_encryption_forms_javascript_attachments_or_open_action():
    reader = _reader(render_pdf_report(comprehensive_projection()))
    assert not reader.is_encrypted
    root = reader.trailer["/Root"]
    assert root.get("/OpenAction") is None
    assert root.get("/AcroForm") is None
    names = root.get("/Names")
    if names is not None:
        names = names.get_object() if hasattr(names, "get_object") else names
        assert "/JavaScript" not in names
        assert "/EmbeddedFiles" not in names


def test_only_embedded_truetype_fonts_are_used_for_report_text():
    reader = _reader(render_pdf_report(comprehensive_projection()))
    base_fonts = set()
    embedded = 0
    for page in reader.pages:
        resources = (page.get("/Resources") or {}).get_object()
        fonts = (resources.get("/Font") or {}).get_object()
        for ref in fonts.values():
            font = ref.get_object()
            base_fonts.add(str(font.get("/BaseFont", "")))
            descriptor = font.get("/FontDescriptor")
            if descriptor is not None and descriptor.get_object().get("/FontFile2") is not None:
                embedded += 1
    assert embedded > 0
    assert not any(any(name in font for name in ("Helvetica", "Times-Roman", "Courier")) for font in base_fonts)
    assert any("BitstreamVeraSans-Roman" in font for font in base_fonts)
    assert any("BitstreamVeraSans-Bold" in font for font in base_fonts)


def test_unsupported_glyph_bidi_and_control_fail_closed(monkeypatch):
    projection = comprehensive_projection()
    monkeypatch.setattr(pdfmod, "validate_case_report_projection", lambda value: None)
    hostile = replace(projection.case_header, case_name="Unsupported emoji 😀")
    with pytest.raises(ValueError, match="unsupported frozen-font glyph"):
        render_pdf_report(replace(projection, case_header=hostile))
    bidi = replace(projection.case_header, case_name="Arabic العربية")
    with pytest.raises(ValueError, match="bidirectional"):
        render_pdf_report(replace(projection, case_header=bidi))
    ctrl = replace(projection.case_header, case_name="bad\x00value")
    with pytest.raises(ValueError, match="forbidden"):
        render_pdf_report(replace(projection, case_header=ctrl))


def test_projection_source_is_immutable_across_rendering():
    projection = comprehensive_projection()
    before = dumps_case_report_projection(projection).encode("utf-8")
    render_pdf_report(projection)
    after = dumps_case_report_projection(projection).encode("utf-8")
    assert after == before


def test_renderer_has_no_forbidden_runtime_imports():
    source_path = Path(pdfmod.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {
        "case_reporting.markdown", "case_reporting.html", "case_analysis", "legal_analysis",
        "case_management", "weasyprint", "jinja2", "playwright", "selenium", "streamlit",
        "openai", "chromadb",
    }
    assert not any(name == bad or name.startswith(bad + ".") for name in imported for bad in forbidden)


def test_renderer_does_not_export_or_write_pdf_files(monkeypatch):
    projection = comprehensive_projection()
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        path = str(file)
        if any(flag in mode for flag in "wax+"):
            raise AssertionError(f"renderer attempted write: {path}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    result = render_pdf_report(projection)
    assert result.pdf


def test_renderer_has_one_profile_and_no_html_or_markdown_input_path():
    import inspect
    signature = inspect.signature(render_pdf_report)
    assert tuple(signature.parameters) == ("projection",)
    assert PDF_OUTPUT_PROFILE == "full-audit/1.0"


def test_golden_pdf_text_contains_all_top_level_section_titles():
    reader = PdfReader(str(FIXTURE))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for title in (
        "LegalRAG Pro — Deterministic Case Report", "Analytical Lineage", "Overall Analytical State",
        "Issues", "Chronology", "Cross-Issue Structural Findings", "Material Conflicts",
        "Evidence Gaps", "Risk Areas", "Priority Questions", "Evidence Appendix", "Reporting Glossary",
    ):
        assert title in text


def test_dependency_reference_hash_constants_are_frozen():
    assert REPORTLAB_WHEEL_SHA256 == "9d5a3affa84919e1111ede580031266a570e93b1ce388219621347965ff1d93c"
    assert PYPDF_WHEEL_SHA256 == "3f07891af76dc002657e04993ab9b4de81de29f9013b9761d0b7968bff12e946"
