from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from case_reporting import CaseReportMetadata, dumps_case_report_projection
from test_case_reporting_projection import sources_and_projection
import ui.reports as reports


class _FakeStreamlit:
    def __init__(self, *, buttons=None):
        self.session_state: dict[str, object] = {}
        self.buttons = set(buttons or ())
        self.text_calls: list[str] = []
        self.title_calls: list[str] = []
        self.header_calls: list[str] = []
        self.subheader_calls: list[str] = []
        self.info_calls: list[str] = []
        self.error_calls: list[str] = []
        self.downloads: list[dict[str, object]] = []
        self.rerun_called = False

    def button(self, label, **kwargs):
        return label in self.buttons

    def selectbox(self, label, *, options, key, format_func=None, **kwargs):
        value = self.session_state.get(key, options[0])
        if value not in options:
            value = options[0]
            self.session_state[key] = value
        return value

    def text(self, value):
        self.text_calls.append(str(value))

    def title(self, value):
        self.title_calls.append(str(value))

    def header(self, value):
        self.header_calls.append(str(value))

    def subheader(self, value):
        self.subheader_calls.append(str(value))

    def info(self, value):
        self.info_calls.append(str(value))

    def error(self, value):
        self.error_calls.append(str(value))

    def divider(self):
        return None

    def download_button(self, label, **kwargs):
        self.downloads.append({"label": label, **kwargs})
        return False

    def rerun(self):
        self.rerun_called = True
        raise RuntimeError("rerun")


def _projection(*, higher_order=False, case_name="Case"):
    metadata = CaseReportMetadata(
        case_name=case_name,
        case_number="2207441/2025",
        claimant="Claimant",
        respondent="Respondent",
        case_status="Active",
        court_or_tribunal="London Central Employment Tribunal",
    )
    return sources_and_projection(higher_order=higher_order, metadata=metadata)[4]


def _bind(fake: _FakeStreamlit, projection):
    reports.st = fake
    reports.synchronise_report_session_state(
        projection.case_header.case_id,
        projection,
    )


def test_session_binding_uses_exact_four_part_identity_and_preserves_chat_state(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    projection = _projection()
    fake.session_state["last_question"] = "preserve me"
    fake.session_state["last_result"] = {"answer": "preserve me"}

    changed = reports.synchronise_report_session_state(
        projection.case_header.case_id,
        projection,
    )

    assert changed is True
    assert fake.session_state["m55_report_case_id"] == projection.case_header.case_id
    assert fake.session_state["m55_report_projection_id"] == projection.report_projection_id
    assert (
        fake.session_state["m55_report_projection_payload_sha256"]
        == projection.projection_payload_sha256
    )
    assert fake.session_state["m55_report_manifest_id"] == projection.manifest.manifest_id
    assert fake.session_state["m55_report_section_id"] == "report_header"
    assert fake.session_state["m55_report_export_format"] == "markdown"
    assert fake.session_state["m55_report_artifact_cache"] == {}
    assert fake.session_state["last_question"] == "preserve me"
    assert fake.session_state["last_result"] == {"answer": "preserve me"}


def test_same_binding_preserves_prepared_state(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    projection = _projection()
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_report_section_id"] = "issues"
    fake.session_state["m55_report_export_format"] = "pdf"
    fake.session_state["m55_report_artifact_cache"] = {("x",): object()}

    changed = reports.synchronise_report_session_state(
        projection.case_header.case_id,
        projection,
    )

    assert changed is False
    assert fake.session_state["m55_report_section_id"] == "issues"
    assert fake.session_state["m55_report_export_format"] == "pdf"
    assert fake.session_state["m55_report_artifact_cache"]


def test_case_or_projection_change_invalidates_only_m55_report_state(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    first = _projection(case_name="First")
    second = _projection(case_name="Second")
    reports.synchronise_report_session_state(first.case_header.case_id, first)
    fake.session_state["m55_report_section_id"] = "all"
    fake.session_state["m55_report_export_format"] = "html"
    fake.session_state["m55_report_artifact_cache"] = {("old",): object()}
    fake.session_state["last_question"] = "still here"

    changed = reports.synchronise_report_session_state(
        second.case_header.case_id,
        second,
    )

    assert changed is True
    assert fake.session_state["m55_report_section_id"] == "report_header"
    assert fake.session_state["m55_report_export_format"] == "markdown"
    assert fake.session_state["m55_report_artifact_cache"] == {}
    assert fake.session_state["last_question"] == "still here"


def test_no_projection_clears_stale_artifacts_without_global_fallback(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    projection = _projection()
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_report_artifact_cache"] = {("old",): object()}

    reports.synchronise_report_session_state(projection.case_header.case_id, None)

    assert fake.session_state["m55_report_case_id"] == projection.case_header.case_id
    assert fake.session_state["m55_report_projection_id"] is None
    assert fake.session_state["m55_report_projection_payload_sha256"] is None
    assert fake.session_state["m55_report_manifest_id"] is None
    assert fake.session_state["m55_report_artifact_cache"] == {}


def test_unknown_route_section_and_format_reset_to_frozen_defaults(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    projection = _projection()
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_main_view"] = "unknown"
    fake.session_state["m55_report_section_id"] = "unknown"
    fake.session_state["m55_report_export_format"] = "unknown"

    reports.synchronise_report_session_state(projection.case_header.case_id, projection)

    assert fake.session_state["m55_main_view"] == "assistant"
    assert fake.session_state["m55_report_section_id"] == "report_header"
    assert fake.session_state["m55_report_export_format"] == "markdown"


def test_full_projection_preflight_accepts_valid_full_audit_projection():
    reports._preflight_native_presentation(_projection(higher_order=True))


def test_preflight_fails_if_manifest_item_coverage_is_changed():
    projection = _projection()
    issues_section = next(
        item for item in projection.manifest.sections if item.section_key == "issues"
    )
    changed_section = replace(
        issues_section,
        ordered_item_ids=issues_section.ordered_item_ids[:-1],
    )
    changed_manifest = replace(
        projection.manifest,
        sections=tuple(
            changed_section if item.section_key == "issues" else item
            for item in projection.manifest.sections
        ),
    )
    changed_projection = replace(projection, manifest=changed_manifest)

    with pytest.raises(ValueError):
        reports._preflight_native_presentation(changed_projection)


def test_preflight_fails_if_manifest_section_citation_inventory_is_changed():
    projection = _projection(higher_order=True)
    issues_section = next(
        item for item in projection.manifest.sections if item.section_key == "issues"
    )
    changed_section = replace(
        issues_section,
        ordered_citation_ids=(*issues_section.ordered_citation_ids, "synthetic-citation"),
    )
    changed_manifest = replace(
        projection.manifest,
        sections=tuple(
            changed_section if item.section_key == "issues" else item
            for item in projection.manifest.sections
        ),
    )
    changed_projection = replace(projection, manifest=changed_manifest)

    with pytest.raises(ValueError):
        reports._preflight_native_presentation(changed_projection)


def test_preflight_accounts_for_every_statement_once_and_every_citation_in_order():
    projection = _projection(higher_order=True)
    reports._preflight_native_presentation(projection)
    statement_ids = reports._all_statement_ids(projection)
    assert len(statement_ids) == len(set(statement_ids))
    assert tuple(item.citation_id for item in projection.citations) == (
        projection.manifest.ordered_citation_ids
    )


def test_show_report_viewer_fails_closed_for_no_case_no_projection_and_provider_error(monkeypatch):
    projection = _projection()

    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.show_report_viewer(None, None)
    assert fake.info_calls == [
        "Select an active case to view a frozen report projection."
    ]

    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.show_report_viewer(projection.case_header.case_id, None)
    assert fake.info_calls == [
        "No frozen report projection is available for this case."
    ]

    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.show_report_viewer(
        projection.case_header.case_id,
        None,
        provider_error=RuntimeError("private detail"),
    )
    assert fake.error_calls == [reports.INVALID_PROJECTION_TEXT]
    assert "private detail" not in fake.error_calls[0]


def test_cross_case_projection_fails_before_semantic_report_output(monkeypatch):
    projection = _projection()
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)

    reports.show_report_viewer(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        projection,
    )

    assert fake.error_calls == [reports.INVALID_PROJECTION_TEXT]
    assert not fake.title_calls
    assert not fake.header_calls
    assert not fake.text_calls
    assert not fake.downloads


def test_hostile_projection_text_is_emitted_only_through_inert_text(monkeypatch):
    hostile = '<script>alert(1)</script> # heading **bold** [link](https://example.invalid)'
    projection = _projection(case_name=hostile)
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert any(hostile in value for value in fake.text_calls)
    assert all(hostile not in value for value in fake.title_calls)
    assert all(hostile not in value for value in fake.header_calls)
    assert all(hostile not in value for value in fake.subheader_calls)


def test_all_sections_follow_exact_manifest_order(monkeypatch):
    projection = _projection(higher_order=True)
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_report_section_id"] = "all"

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert fake.title_calls[0] == "LegalRAG Pro — Deterministic Case Report"
    assert fake.header_calls[:11] == [
        reports._SECTION_LABELS[section_id]
        for section_id in projection.manifest.ordered_section_ids
        if section_id != "report_header"
    ]


def test_native_full_audit_exposes_required_status_and_qualification_fields(monkeypatch):
    projection = _projection(higher_order=True)
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_report_section_id"] = "all"

    reports.show_report_viewer(projection.case_header.case_id, projection)

    joined = "\n".join(fake.text_calls)
    for label in (
        "Raw value:",
        "Label:",
        "Explanation:",
        "Qualification code:",
        "Occurrence status",
        "Timing status",
        "Frozen provisional analysis:",
        "Citation text:",
        "Count qualification:",
    ):
        assert label in joined


def test_projection_is_not_mutated_by_preflight_or_native_render(monkeypatch):
    projection = _projection(higher_order=True)
    before = dumps_case_report_projection(projection)
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    fake.session_state["m55_report_section_id"] = "all"

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert dumps_case_report_projection(projection) == before



def test_artifact_cache_key_contains_exact_frozen_identity_components():
    projection = _projection()
    case_id = projection.case_header.case_id
    key = reports._cache_key(case_id, projection, "pdf")
    assert key == (
        case_id,
        projection.report_projection_id,
        projection.projection_payload_sha256,
        projection.manifest.manifest_id,
        "case-report-pdf-renderer/1.0",
        "full-audit/1.0",
        "pdf",
    )

@pytest.mark.parametrize(
    ("output_format", "attribute", "mime", "extension", "renderer_version"),
    [
        (
            "markdown",
            "markdown",
            "text/markdown; charset=utf-8",
            "md",
            "case-report-markdown-renderer/1.0",
        ),
        (
            "html",
            "html",
            "text/html; charset=utf-8",
            "html",
            "case-report-html-renderer/1.0",
        ),
        (
            "pdf",
            "pdf",
            "application/pdf",
            "pdf",
            "case-report-pdf-renderer/1.0",
        ),
    ],
)
def test_frozen_artifacts_preserve_exact_binding_and_exact_download_bytes(
    output_format,
    attribute,
    mime,
    extension,
    renderer_version,
):
    projection = _projection(higher_order=True)
    artifact = reports._render_artifact(projection, output_format)
    reports._validate_artifact(artifact, projection, output_format)

    expected = getattr(artifact, attribute)
    if isinstance(expected, str):
        expected = expected.encode("utf-8")
    assert reports._artifact_bytes(artifact, output_format) == expected
    assert artifact.renderer_version == renderer_version
    assert artifact.output_profile == reports.OUTPUT_PROFILE
    assert artifact.report_projection_id == projection.report_projection_id
    assert artifact.manifest_id == projection.manifest.manifest_id
    assert artifact.projection_payload_sha256 == projection.projection_payload_sha256
    assert artifact.report_manifest == projection.manifest
    assert reports._MIME_TYPES[output_format] == mime
    assert reports._EXTENSIONS[output_format] == extension


def test_export_is_not_generated_until_explicit_prepare(monkeypatch):
    projection = _projection()
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    calls = []
    monkeypatch.setattr(
        reports,
        "_render_artifact",
        lambda projection, output_format: calls.append(output_format),
    )

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert calls == []
    assert fake.downloads == []


def test_explicit_prepare_calls_only_selected_renderer_and_downloads_exact_bytes(monkeypatch):
    projection = _projection()
    fake = _FakeStreamlit(buttons={"Prepare Markdown download"})
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    artifact = SimpleNamespace(
        report_projection_id=projection.report_projection_id,
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        report_manifest=projection.manifest,
        output_profile=reports.OUTPUT_PROFILE,
        renderer_version="case-report-markdown-renderer/1.0",
        markdown="exact\n",
    )
    calls = []

    def render(selected_projection, output_format):
        calls.append((selected_projection, output_format))
        return artifact

    monkeypatch.setattr(reports, "_render_artifact", render)

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert calls == [(projection, "markdown")]
    assert len(fake.downloads) == 1
    download = fake.downloads[0]
    assert download["data"] == b"exact\n"
    assert download["mime"] == "text/markdown; charset=utf-8"
    assert download["file_name"] == (
        f"legalrag-report-{projection.report_projection_id}.md"
    )


def test_mismatching_cached_artifact_is_rejected_and_removed(monkeypatch):
    projection = _projection()
    fake = _FakeStreamlit()
    monkeypatch.setattr(reports, "st", fake)
    reports.synchronise_report_session_state(projection.case_header.case_id, projection)
    key = reports._cache_key(
        projection.case_header.case_id,
        projection,
        "markdown",
    )
    fake.session_state["m55_report_artifact_cache"][key] = SimpleNamespace(
        report_projection_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        manifest_id=projection.manifest.manifest_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        report_manifest=projection.manifest,
        output_profile=reports.OUTPUT_PROFILE,
        renderer_version="case-report-markdown-renderer/1.0",
        markdown="bad",
    )

    reports.show_report_viewer(projection.case_header.case_id, projection)

    assert key not in fake.session_state["m55_report_artifact_cache"]
    assert fake.error_calls == [reports.EXPORT_FAILURE_TEXT]
    assert fake.downloads == []


def test_back_to_assistant_changes_only_route_and_reruns(monkeypatch):
    projection = _projection()
    fake = _FakeStreamlit(buttons={"Back to AI Assistant"})
    fake.session_state["m55_main_view"] = "reports"
    fake.session_state["last_question"] = "preserve"
    monkeypatch.setattr(reports, "st", fake)

    with pytest.raises(RuntimeError, match="rerun"):
        reports.show_report_viewer(projection.case_header.case_id, projection)

    assert fake.session_state["m55_main_view"] == "assistant"
    assert fake.session_state["last_question"] == "preserve"
