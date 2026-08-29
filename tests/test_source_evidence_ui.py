from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.models import BindingClass, ExtractionMethod, ProjectionBindingCoverage
from source_evidence.resolver import ResolvedSourceEvidence, SourceEvidenceResolverError


class FakeSidebar:
    def __init__(self, owner):
        self.owner = owner
        self.buttons: dict[str, bool] = {}

    def title(self, *args, **kwargs): pass
    def subheader(self, *args, **kwargs): pass
    def caption(self, *args, **kwargs): self.owner.calls.append(("sidebar_caption", args))
    def warning(self, *args, **kwargs): self.owner.calls.append(("sidebar_warning", args))
    def info(self, *args, **kwargs): self.owner.calls.append(("sidebar_info", args))
    def success(self, *args, **kwargs): self.owner.calls.append(("sidebar_success", args))
    def error(self, *args, **kwargs): self.owner.calls.append(("sidebar_error", args))
    def divider(self): pass
    def checkbox(self, *args, **kwargs): return True
    def file_uploader(self, *args, **kwargs): return None
    def button(self, label, **kwargs): return self.buttons.get(label, False)
    def expander(self, *args, **kwargs): return self

    def __enter__(self): return self
    def __exit__(self, *args): return False


class FakeStreamlit:
    def __init__(self):
        self.session_state: dict[str, object] = {}
        self.calls: list[tuple] = []
        self.sidebar = FakeSidebar(self)

    def title(self, *args, **kwargs): self.calls.append(("title", args))
    def subheader(self, *args, **kwargs): self.calls.append(("subheader", args))
    def caption(self, *args, **kwargs): self.calls.append(("caption", args))
    def info(self, *args, **kwargs): self.calls.append(("info", args))
    def error(self, *args, **kwargs): self.calls.append(("error", args))
    def file_uploader(self, *args, **kwargs): return None
    def checkbox(self, *args, **kwargs): return False
    def text(self, *args, **kwargs): self.calls.append(("text", args))
    def code(self, body, **kwargs): self.calls.append(("code", body, kwargs))
    def download_button(self, label, **kwargs): self.calls.append(("download", label, kwargs)); return False
    def rerun(self): self.calls.append(("rerun",))

    def selectbox(self, label, *, options, index=0, format_func=None, key=None, **kwargs):
        value = options[index]
        if key is not None:
            self.session_state[key] = value
        self.calls.append(("selectbox", label, tuple(options), value))
        return value


CASE_ID = "12345678-1234-4234-8234-123456789abc"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
MANIFEST_ID = "22222222-2222-4222-8222-222222222222"
PROJECTION_SHA = "a" * 64


def _citation(key="chunk-1", name="evidence.pdf", page=1):
    return SimpleNamespace(
        citation_id=key,
        evidence_key=key,
        document_name=name,
        page=page,
        document_id=None,
        chunk_id=key,
    )


def _projection(citations=(_citation(),)):
    citations = tuple(citations)
    return SimpleNamespace(
        case_header=SimpleNamespace(case_id=CASE_ID),
        report_projection_id=REPORT_ID,
        projection_payload_sha256=PROJECTION_SHA,
        citations=citations,
        manifest=SimpleNamespace(
            manifest_id=MANIFEST_ID,
            ordered_citation_ids=tuple(item.citation_id for item in citations),
        ),
    )


def _resolved(binding_class=BindingClass.FULL_CHAIN_BOUND, *, text="exact chunk"):
    full = binding_class is BindingClass.FULL_CHAIN_BOUND
    return ResolvedSourceEvidence(
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_evidence_binding_manifest_id="sha256:" + "1" * 64,
        projection_binding_coverage=(
            ProjectionBindingCoverage.FULLY_SOURCE_BOUND
            if full else ProjectionBindingCoverage.MIXED_BINDING
        ),
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=binding_class,
        evidence_binding_id=None if binding_class is BindingClass.UNBOUND else "sha256:" + "2" * 64,
        source_bound_analysis_receipt_id=("sha256:" + "3" * 64) if full else None,
        document_name="evidence.pdf",
        document_id=None,
        page=1,
        chunk_id="chunk-1",
        chunk_ordinal=0 if full else None,
        source_document_instance_id="12345678-1234-4234-8234-123456789abd" if full else None,
        source_snapshot_id=("sha256:" + "4" * 64) if full else None,
        bound_text_role=None,
        bound_text_sha256=("5" * 64) if binding_class is not BindingClass.UNBOUND else None,
        original_blob_sha256=("6" * 64) if full else None,
        page_text_sha256=("7" * 64) if full else None,
        chunk_text_sha256=("8" * 64) if full else None,
        extraction_profile_id="pdf-page-extraction/1.0" if full else None,
        chunking_profile_id="recursive-character-text-splitter/1.0" if full else None,
        extraction_method=ExtractionMethod.PYPDF_TEXT if full else None,
        exact_bound_text=None if binding_class is BindingClass.UNBOUND else text,
        exact_page_text="exact page" if full else None,
        original_pdf_bytes=b"%PDF exact" if full else None,
        original_filename="evidence.pdf" if full else None,
    )


def _install_fake_streamlit(monkeypatch, target_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(target_module, "st", fake)
    return fake


def test_session_identity_change_resets_only_m7_state(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    fake.session_state.update({
        "m7_source_evidence_view": True,
        "m7_source_evidence_citation_id": "old",
        "m55_main_view": "reports",
        "m6_workspace_view": "people",
    })
    assert ui.synchronise_source_evidence_session_state(CASE_ID, _projection()) is True
    assert fake.session_state["m7_source_evidence_view"] is False
    assert "m7_source_evidence_citation_id" not in fake.session_state
    assert fake.session_state["m55_main_view"] == "reports"
    assert fake.session_state["m6_workspace_view"] == "people"
    assert ui.synchronise_source_evidence_session_state(CASE_ID, _projection()) is False


def test_no_case_and_no_projection_are_informational(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    ui.show_source_evidence(None, None)
    assert any(call[0] == "info" for call in fake.calls)

    fake.calls.clear()
    ui.show_source_evidence(CASE_ID, None)
    assert any(call[0] == "info" for call in fake.calls)


def test_citation_selector_uses_exact_manifest_order(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda value: None)
    monkeypatch.setattr(ui, "resolve_projection_citation_source", lambda *args, **kwargs: _resolved())
    projection = _projection((_citation("chunk-2", "two.pdf", 2), _citation("chunk-1")))
    ui.show_source_evidence(CASE_ID, projection)
    select = next(call for call in fake.calls if call[0] == "selectbox")
    assert select[2] == ("chunk-2", "chunk-1")


def test_missing_m6_manifest_reports_unavailable_not_error(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda value: None)
    monkeypatch.setattr(ui, "resolve_projection_citation_source", lambda *args, **kwargs: None)
    ui.show_source_evidence(CASE_ID, _projection())
    assert any(call[0] == "info" and "report remains valid" in call[1][0] for call in fake.calls)
    assert not any(call[0] == "error" for call in fake.calls)


def test_unbound_renders_no_source_text(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda value: None)
    monkeypatch.setattr(
        ui,
        "resolve_projection_citation_source",
        lambda *args, **kwargs: _resolved(BindingClass.UNBOUND),
    )
    ui.show_source_evidence(CASE_ID, _projection())
    assert any(call[0] == "info" and "unavailable" in call[1][0] for call in fake.calls)
    assert not any(call[0] == "code" for call in fake.calls)


@pytest.mark.parametrize(
    "binding_class",
    [BindingClass.ANALYTICAL_TEXT_BOUND, BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT],
)
def test_weaker_classes_render_exact_text_with_limitations(monkeypatch, binding_class):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda value: None)
    monkeypatch.setattr(
        ui,
        "resolve_projection_citation_source",
        lambda *args, **kwargs: _resolved(binding_class, text="<unsafe> exact text"),
    )
    ui.show_source_evidence(CASE_ID, _projection())
    assert any(call[0] == "code" and call[1] == "<unsafe> exact text" for call in fake.calls)
    assert any(call[0] == "info" for call in fake.calls)
    assert not any(call[0] == "download" for call in fake.calls)


def test_full_chain_renders_hostile_source_inertly_and_downloads_exact_pdf(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    hostile = "<script>alert(1)</script>\n# heading\n[link](https://example.test)"
    value = _resolved(text=hostile)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda projection: None)
    monkeypatch.setattr(ui, "resolve_projection_citation_source", lambda *args, **kwargs: value)
    ui.show_source_evidence(CASE_ID, _projection())
    assert any(call[0] == "code" and call[1] == hostile for call in fake.calls)
    download = next(call for call in fake.calls if call[0] == "download")
    assert download[2]["data"] == b"%PDF exact"
    assert download[2]["file_name"] == "evidence.pdf"
    assert download[2]["mime"] == "application/pdf"


def test_resolver_failure_displays_generic_error_without_exception_or_source(monkeypatch):
    import ui.source_evidence as ui

    fake = _install_fake_streamlit(monkeypatch, ui)
    monkeypatch.setattr(ui, "validate_case_report_projection", lambda value: None)
    monkeypatch.setattr(
        ui,
        "resolve_projection_citation_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SourceEvidenceResolverError("SECRET SOURCE TEXT SHOULD NOT DISPLAY")
        ),
    )
    ui.show_source_evidence(CASE_ID, _projection())
    rendered = repr(fake.calls)
    assert "SECRET SOURCE TEXT SHOULD NOT DISPLAY" not in rendered
    assert "No source text has been displayed" in rendered


def _document_manager_module():
    module = types.ModuleType("document_manager")
    module.get_documents = lambda active_case_id=None: ["doc.pdf"]
    return module


def test_sidebar_source_route_and_other_tool_exclusivity(monkeypatch):
    import ui.sidebar as sidebar

    fake = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", fake)
    monkeypatch.setitem(sys.modules, "document_manager", _document_manager_module())

    fake.sidebar.buttons["🔗 Sources & Provenance"] = True
    sidebar.show_sidebar(active_case_id=CASE_ID, reports_available=True)
    assert fake.session_state["m7_source_evidence_view"] is True
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["m55_main_view"] == "assistant"

    fake.sidebar.buttons.clear()
    fake.sidebar.buttons["📄 Reports"] = True
    sidebar.show_sidebar(active_case_id=CASE_ID, reports_available=True)
    assert fake.session_state["m7_source_evidence_view"] is False
    assert fake.session_state["m55_main_view"] == "reports"


def test_app_routes_source_view_before_workspace_and_reports() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "app.py"
    source = path.read_text(encoding="utf-8")
    assert "synchronise_source_evidence_session_state(active_case_id, report_projection)" in source
    source_index = source.index('if st.session_state.get("m7_source_evidence_view", False):')
    workspace_index = source.index('elif st.session_state.get("m6_workspace_view")')
    reports_index = source.index('elif st.session_state.get("m55_main_view", "assistant") == "reports"')
    assert source_index < workspace_index < reports_index


def test_source_ui_contains_no_unsafe_html_or_source_markdown_rendering() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "ui" / "source_evidence.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "html" not in calls
    assert "markdown" not in calls
    assert "unsafe_allow_html" not in source
    assert "st.code" in source
