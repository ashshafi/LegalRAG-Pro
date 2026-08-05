from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace as NS

import pytest


class _StreamlitPlaceholder:
    pass


sys.modules.setdefault("streamlit", _StreamlitPlaceholder())
workspace = importlib.import_module("ui.workspace")

CASE_ID = "11111111-1111-4111-8111-111111111111"


class _FakeStreamlit:
    def __init__(self, *, buttons=()):
        self.session_state: dict[str, object] = {}
        self.buttons = set(buttons)
        self.info_calls: list[str] = []
        self.error_calls: list[str] = []
        self.title_calls: list[str] = []
        self.header_calls: list[str] = []
        self.subheader_calls: list[str] = []
        self.text_calls: list[str] = []
        self.caption_calls: list[str] = []
        self.rerun_called = False

    def info(self, value): self.info_calls.append(str(value))
    def error(self, value): self.error_calls.append(str(value))
    def title(self, value): self.title_calls.append(str(value))
    def header(self, value): self.header_calls.append(str(value))
    def subheader(self, value): self.subheader_calls.append(str(value))
    def text(self, value): self.text_calls.append(str(value))
    def caption(self, value): self.caption_calls.append(str(value))
    def button(self, label, **kwargs): return label in self.buttons
    def text_input(self, label, *, key, **kwargs): return self.session_state.get(key, "")
    def multiselect(self, label, options, *, key, **kwargs): return self.session_state.get(key, [])
    def selectbox(self, label, options, *, key, format_func=None, **kwargs):
        current = self.session_state.get(key)
        if current not in options:
            current = options[0]
            self.session_state[key] = current
        return current
    def columns(self, number): return tuple(_NullContext() for _ in range(number))
    def rerun(self):
        self.rerun_called = True
        raise RuntimeError("rerun")


class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *args): return False


def _projection(*, case_id=CASE_ID, projection_id="22222222-2222-4222-8222-222222222222", sha="a" * 64, manifest_id="33333333-3333-4333-8333-333333333333"):
    return NS(
        case_header=NS(case_id=case_id),
        report_projection_id=projection_id,
        projection_payload_sha256=sha,
        manifest=NS(manifest_id=manifest_id),
    )


def _index():
    return NS(
        issue_keys=(), element_keys=(), statement_keys=(), finding_keys=(), event_keys=(), assertion_keys=(),
        conflict_keys=(), gap_keys=(), risk_keys=(), question_keys=(), citation_keys=(),
        object_by_key={}, outgoing={}, backlinks={}, unresolved_priority_element_ids={},
        citations_by_id={}, events_by_id={}, recorded_name_values=(), recorded_names={},
        document_group_keys=(), document_groups={},
    )


def test_session_binding_uses_exact_four_part_identity_and_preserves_sibling_state(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    projection = _projection()
    fake.session_state["last_question"] = "preserve"
    fake.session_state["m55_main_view"] = "reports"
    fake.session_state["m55_report_section_id"] = "issues"
    changed = workspace.synchronise_workspace_session_state(CASE_ID, projection)
    assert changed is True
    assert tuple(fake.session_state[key] for key in workspace._BINDING_KEYS) == (
        CASE_ID, projection.report_projection_id, projection.projection_payload_sha256, projection.manifest.manifest_id
    )
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["last_question"] == "preserve"
    assert fake.session_state["m55_main_view"] == "reports"
    assert fake.session_state["m55_report_section_id"] == "issues"


def test_same_binding_preserves_workspace_state_but_new_binding_resets_only_m6(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    first = _projection()
    workspace.synchronise_workspace_session_state(CASE_ID, first)
    fake.session_state["m6_workspace_view"] = "evidence"
    fake.session_state["m6_evidence_query"] = "smith"
    fake.session_state["last_result"] = {"answer": "preserve"}
    assert workspace.synchronise_workspace_session_state(CASE_ID, first) is False
    assert fake.session_state["m6_workspace_view"] == "evidence"
    second = _projection(projection_id="44444444-4444-4444-8444-444444444444")
    assert workspace.synchronise_workspace_session_state(CASE_ID, second) is True
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["m6_evidence_query"] == ""
    assert fake.session_state["last_result"] == {"answer": "preserve"}


def test_unknown_workspace_view_and_trace_kind_reset_to_neutral_defaults(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    projection = _projection()
    workspace.synchronise_workspace_session_state(CASE_ID, projection)
    fake.session_state["m6_workspace_view"] = "unknown"
    fake.session_state["m6_trace_kind"] = "unknown"
    workspace.synchronise_workspace_session_state(CASE_ID, projection)
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["m6_trace_kind"] == "issue"
    assert fake.session_state["m6_trace_selected_key"] is None


def test_show_workspace_fails_closed_before_semantic_output(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    workspace.show_workspace(None, None)
    assert fake.info_calls == [workspace._NO_CASE_TEXT]
    assert not fake.title_calls

    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    workspace.show_workspace(CASE_ID, None)
    assert fake.info_calls == [workspace._NO_PROJECTION_TEXT]
    assert not fake.title_calls

    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    monkeypatch.setattr(workspace, "validate_case_report_projection", lambda projection: (_ for _ in ()).throw(ValueError("private")))
    workspace.show_workspace(CASE_ID, _projection())
    assert fake.error_calls == [workspace._INVALID_WORKSPACE_TEXT]
    assert not fake.title_calls
    assert not fake.text_calls


def test_cross_case_projection_fails_closed(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    monkeypatch.setattr(workspace, "validate_case_report_projection", lambda projection: None)
    monkeypatch.setattr(workspace, "build_workspace_index", lambda projection: _index())
    workspace.show_workspace(CASE_ID, _projection(case_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
    assert fake.error_calls == [workspace._INVALID_WORKSPACE_TEXT]
    assert not fake.title_calls


def test_close_workspace_preserves_underlying_m55_route(monkeypatch):
    fake = _FakeStreamlit(buttons={"Close Workspace"})
    fake.session_state["m6_workspace_view"] = "traceability"
    fake.session_state["m55_main_view"] = "reports"
    monkeypatch.setattr(workspace, "st", fake)
    monkeypatch.setattr(workspace, "validate_case_report_projection", lambda projection: None)
    monkeypatch.setattr(workspace, "build_workspace_index", lambda projection: _index())
    with pytest.raises(RuntimeError, match="rerun"):
        workspace.show_workspace(CASE_ID, _projection())
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["m55_main_view"] == "reports"


def test_hostile_citation_text_is_rendered_only_as_inert_text(monkeypatch):
    hostile = '<script>alert(1)</script> # heading **bold** [link](https://example.invalid)'
    citation = NS(
        citation_id="chunk-1", evidence_key="chunk-1", citation=hostile, document_name="Doc.pdf",
        document_id=None, page=1, chunk_id="chunk-1", date=None, author=None, parties=(),
        source_type="primary", evidence_status="primary", provenance_type="source",
        provenance_basis="exact", provenance_confidence="high", evidence_use_coordinates=(),
    )
    key = workspace.WorkspaceObjectKey("citation", "chunk-1")
    index = NS(backlinks={key: ()})
    fake = _FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    workspace._render_citation(index, citation)
    assert any(hostile in value for value in fake.text_calls)
    assert all(hostile not in value for value in fake.subheader_calls)


def test_comparison_and_people_qualifications_are_non_analytical():
    source = workspace.__file__
    text = open(source, encoding="utf-8").read()
    assert "No entity resolution, alias matching or person/organisation classification is performed." in text
    assert "It does not perform a full-text or merits comparison of the underlying documents." in text
    for prohibited in ("stronger document", "weaker document", "win probability", "recommended evidence"):
        assert prohibited not in text
