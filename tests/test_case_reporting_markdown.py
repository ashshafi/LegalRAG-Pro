from __future__ import annotations

import ast
import builtins
import inspect
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import re
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m3.models import CaseChronology
from case_analysis.m4.synthesis import build_case_synthesis
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import make_case_synthesis
from case_reporting import (
    CaseReportMetadata,
    build_case_report_projection,
    dumps_case_report_projection,
)
from case_reporting.markdown import (
    ABSENT_VALUE_TEXT,
    EMPTY_SECTION_TEXT,
    MARKDOWN_OUTPUT_PROFILE,
    MARKDOWN_RENDERER_VERSION,
    MarkdownReport,
    render_markdown_report,
)
from case_reporting.models import SECTION_KEYS

FIXTURE = Path(__file__).parent / "fixtures" / "case_reporting" / "m52_full_audit.md"
GOLDEN_SHA256 = "93dd56b51851e99b9a81a0099dec6b0e83b9cbfe6a961e25a2b778b6f0618a92"


def comprehensive_projection(*, metadata: CaseReportMetadata | None = None, summary: str = "Frozen supporting feature."):
    counter = iter(uuid5(NAMESPACE_URL, f"m52-synthetic-{index}") for index in range(500))
    with patch("legal_analysis.models.uuid4", side_effect=lambda: next(counter)):
        foundation, matrices, chronology, synthesis, _ = make_case_synthesis(summary=summary)
    deterministic = build_case_synthesis(foundation, matrices, chronology)
    cross_issue = next(
        item for item in deterministic.findings if item.finding_type.value == "cross_issue_feature"
    )
    combined = replace(synthesis, findings=(*synthesis.findings, cross_issue))
    return build_case_report_projection(
        foundation,
        matrices,
        chronology,
        combined,
        metadata,
    )


def empty_optional_projection():
    item = evidence(
        key="empty-evidence",
        document_name="empty.pdf",
        page=1,
        summary="A source with no event date.",
    )
    result = make_m5_result(
        "EK-001",
        case_id="77777777-7777-4777-8777-777777777777",
        issue_analysis_id="77777777-7777-4777-8777-777777777701",
        evidence_by_element={"EK-INFORMATION": (item,)},
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    chronology = CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    return build_case_report_projection(foundation, matrices, chronology, synthesis)


def all_statement_ids(projection):
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


def test_renderer_versions_profile_and_immutable_result_are_frozen():
    projection = comprehensive_projection()
    result = render_markdown_report(projection)
    assert result.renderer_version == MARKDOWN_RENDERER_VERSION
    assert result.output_profile == MARKDOWN_OUTPUT_PROFILE
    assert result.report_projection_id == projection.report_projection_id
    assert result.manifest_id == projection.manifest.manifest_id
    assert result.report_manifest is projection.manifest
    with pytest.raises(FrozenInstanceError):
        result.markdown = "changed"


def test_renderer_is_deterministic_and_byte_stable():
    projection = comprehensive_projection()
    first = render_markdown_report(projection)
    second = render_markdown_report(projection)
    assert second == first
    assert second.markdown == first.markdown
    assert second.markdown_sha256 == first.markdown_sha256
    assert second.markdown_report_id == first.markdown_report_id


def test_hash_and_renderer_identity_match_exact_bytes():
    result = render_markdown_report(comprehensive_projection())
    assert result.markdown_sha256 == sha256(result.markdown.encode("utf-8")).hexdigest()
    assert result.markdown_report_id
    assert result.markdown_sha256 not in result.markdown
    assert result.markdown_report_id not in result.markdown


def test_public_renderer_accepts_only_case_report_projection():
    with pytest.raises(ValueError, match="CaseReportProjection"):
        render_markdown_report("not a projection")


def test_public_renderer_revalidates_and_rejects_tampering():
    projection = comprehensive_projection()
    bad = replace(projection, projection_payload_sha256="0" * 64)
    with pytest.raises(ValueError):
        render_markdown_report(bad)


def test_all_twelve_sections_appear_in_exact_manifest_order():
    result = render_markdown_report(comprehensive_projection())
    positions = []
    for key in SECTION_KEYS:
        anchor = f'<a id="legalrag-section-{key}"></a>'
        positions.append(result.markdown.index(anchor))
    assert positions == sorted(positions)
    assert result.markdown.startswith("# LegalRAG Pro — Deterministic Case Report\n")


def test_empty_sections_are_explicitly_rendered():
    projection = empty_optional_projection()
    result = render_markdown_report(projection)
    for section in projection.manifest.sections:
        if section.is_empty:
            start = result.markdown.index(f'<a id="legalrag-section-{section.section_key}"></a>')
            next_positions = [
                result.markdown.find(f'<a id="legalrag-section-{other}"></a>', start + 1)
                for other in SECTION_KEYS
            ]
            next_positions = [value for value in next_positions if value != -1]
            end = min(next_positions) if next_positions else len(result.markdown)
            assert EMPTY_SECTION_TEXT in result.markdown[start:end]


def test_all_raw_statuses_and_qualification_codes_remain_visible():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    for _, raw_value in projection.manifest.raw_status_inventory:
        assert f"`{raw_value}`" in markdown
    for _, qualification in projection.manifest.qualification_inventory:
        assert f"`{qualification}`" in markdown


def test_occurrence_and_timing_are_rendered_separately_for_events_and_assertions():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    event = projection.chronology[0]
    assert event.occurrence_status.raw_value == "supported"
    assert event.timing_status.raw_value == "established"
    assert markdown.count("**Occurrence status**") >= 1 + len(event.assertions)
    assert markdown.count("**Timing status**") >= 1 + len(event.assertions)
    assert "Established event" not in markdown


def test_neutral_medium_explanations_are_complete():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    import case_reporting.markdown as module
    assert module._escape_text(projection.gaps[0].materiality.explanation) in markdown
    assert module._escape_text(projection.priority_questions[0].priority.explanation) in markdown
    assert "not a comparative statement" in markdown
    assert "not an urgency" in markdown


def test_cross_issue_finding_has_one_primary_anchor_and_links_from_each_issue():
    projection = comprehensive_projection()
    result = render_markdown_report(projection)
    finding = projection.cross_issue_findings[0]
    token = __import__("base64").urlsafe_b64encode(finding.finding_id.encode()).decode().rstrip("=")
    anchor = f"legalrag-finding-{token}"
    assert result.markdown.count(f'<a id="{anchor}"></a>') == 1
    assert result.markdown.count(f"](#{anchor})") == len(finding.issue_ids)


def test_all_report_statement_ids_are_rendered_once():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    for statement_id in all_statement_ids(projection):
        assert markdown.count(statement_id) == 1


def test_every_citation_has_one_appendix_anchor_and_all_links_resolve():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    anchors = set(re.findall(r'<a id="([^"]+)"></a>', markdown))
    targets = re.findall(r'\]\(#([^\)]+)\)', markdown)
    assert set(targets) <= anchors
    for citation in projection.citations:
        token = __import__("base64").urlsafe_b64encode(citation.citation_id.encode()).decode().rstrip("=")
        anchor = f"legalrag-citation-{token}"
        assert markdown.count(f'<a id="{anchor}"></a>') == 1
        assert citation.citation_id in markdown


def test_all_primary_anchors_are_unique():
    markdown = render_markdown_report(comprehensive_projection()).markdown
    anchors = re.findall(r'<a id="([^"]+)"></a>', markdown)
    assert len(anchors) == len(set(anchors))


def test_every_event_assertion_is_fully_present():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
    for event in projection.chronology:
        assert event.event_id in markdown
        for assertion in event.assertions:
            assert assertion.assertion_id in markdown
            import case_reporting.markdown as module
            assert module._escape_text(assertion.description) in markdown


def test_manifest_semantic_identity_sets_are_represented():
    projection = comprehensive_projection()
    markdown = render_markdown_report(projection).markdown
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
        assert item_id in markdown


def test_missing_optional_values_use_exact_controlled_phrase():
    markdown = render_markdown_report(comprehensive_projection()).markdown
    import case_reporting.markdown as module
    assert module._escape_text(ABSENT_VALUE_TEXT) in markdown
    assert f"- **Case name:** {module._escape_text(ABSENT_VALUE_TEXT)}" in markdown


def test_hostile_projection_text_is_escaped_and_cannot_create_structure_or_links():
    hostile = "# Heading\r\n- list | pipe [click](javascript:alert(1)) <script>alert('x')</script>\t`code` _u_"
    metadata = CaseReportMetadata(
        case_name=hostile,
        case_number="https://evil.example/path",
        claimant="<img src=x onerror=alert(1)>",
    )
    projection = comprehensive_projection(metadata=metadata, summary=hostile)
    markdown = render_markdown_report(projection).markdown
    assert "<script>" not in markdown
    assert "<img " not in markdown
    assert "javascript:" not in markdown
    assert "](javascript" not in markdown
    assert "https://evil.example" not in markdown
    assert "https&#58;//evil\\.example/path" in markdown
    assert "\\# Heading" in markdown
    assert "\\- list" in markdown
    assert "&lt;script&gt;" in markdown
    assert "&#9;" in markdown
    anchors = re.findall(r'<a id="legalrag-[A-Za-z0-9_-]+"></a>', markdown)
    assert anchors
    without_anchors = re.sub(r'<a id="legalrag-[A-Za-z0-9_-]+"></a>', "", markdown)
    assert re.search(r"<[^>]+>", without_anchors) is None


def test_markdown_has_exact_deterministic_whitespace_contract():
    markdown = render_markdown_report(comprehensive_projection()).markdown
    assert "\r" not in markdown
    assert "\t" not in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")
    assert all(not line.endswith(" ") for line in markdown.splitlines())
    assert not any(line.startswith("|") for line in markdown.splitlines())


def test_renderer_does_not_mutate_projection():
    projection = comprehensive_projection()
    before = dumps_case_report_projection(projection)
    render_markdown_report(projection)
    after = dumps_case_report_projection(projection)
    assert after == before


def test_renderer_performs_no_file_io(monkeypatch):
    projection = comprehensive_projection()

    def forbidden(*args, **kwargs):
        raise AssertionError("file I/O is prohibited")

    monkeypatch.setattr(builtins, "open", forbidden)
    result = render_markdown_report(projection)
    assert isinstance(result, MarkdownReport)


def test_renderer_public_signature_has_no_profile_or_unsafe_bypass():
    signature = inspect.signature(render_markdown_report)
    assert tuple(signature.parameters) == ("projection",)


def test_markdown_module_has_only_authorised_runtime_imports():
    path = Path(__file__).parents[1] / "src" / "case_reporting" / "markdown.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    relatives = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relatives.add(node.module)
            elif node.module:
                roots.add(node.module.split(".", 1)[0])
    assert roots <= {"__future__", "base64", "dataclasses", "hashlib", "html", "re", "typing", "uuid"}
    assert relatives <= {"models", "validation"}


def test_markdown_module_contains_no_renderer_export_or_analytical_dependency():
    source = (Path(__file__).parents[1] / "src" / "case_reporting" / "markdown.py").read_text(encoding="utf-8")
    prohibited = (
        "openai",
        "chromadb",
        "streamlit",
        "case_analysis",
        "legal_analysis",
        "case_management",
        "render_html",
        "render_pdf",
        "render_streamlit",
        "Path(",
        "open(",
    )
    for token in prohibited:
        assert token not in source


def test_renderer_fails_closed_when_internal_audit_omits_an_item(monkeypatch):
    import case_reporting.markdown as module

    original = module._render_gap

    def omit_audit(writer, audit, **kwargs):
        gap = kwargs["gap"]
        anchor = module._anchor("gap", gap.gap_id)
        audit.anchor(anchor)
        writer.add(f'{module._anchor_tag(anchor)}\n### Evidence Gap 1')

    monkeypatch.setattr(module, "_render_gap", omit_audit)
    with pytest.raises(ValueError, match="manifest items"):
        render_markdown_report(comprehensive_projection())
    monkeypatch.setattr(module, "_render_gap", original)


def test_renderer_fails_closed_on_duplicate_primary_anchor(monkeypatch):
    import case_reporting.markdown as module

    monkeypatch.setattr(module, "_anchor", lambda kind, *parts: "legalrag-duplicate")
    with pytest.raises(ValueError, match="Duplicate primary Markdown anchor"):
        render_markdown_report(comprehensive_projection())


def test_golden_fixture_is_exact_and_governed():
    projection = comprehensive_projection(
        metadata=CaseReportMetadata(
            case_name="Shafi v CACI Ltd",
            case_number="2207441/2025",
            claimant="Arshad Shafi",
            respondent="CACI Ltd",
            case_status="Active",
            court_or_tribunal="London Central Employment Tribunal",
        )
    )
    result = render_markdown_report(projection)
    expected = FIXTURE.read_text(encoding="utf-8")
    assert result.markdown == expected
    assert sha256(FIXTURE.read_bytes()).hexdigest() == GOLDEN_SHA256


def test_only_one_full_audit_profile_is_exposed():
    import case_reporting.markdown as module

    assert module.MARKDOWN_OUTPUT_PROFILE == "full-audit/1.0"
    source = Path(module.__file__).read_text(encoding="utf-8")
    for token in ("concise", "executive", "client", "lawyer-summary"):
        assert token not in source
