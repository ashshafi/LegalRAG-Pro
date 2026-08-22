from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import ui.matter_overview as matter_overview


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ui" / "matter_overview.py"


class _MetricColumn:
    def __init__(self, owner):
        self.owner = owner

    def metric(self, label, value):
        self.owner.metrics.append((str(label), value))


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.titles = []
        self.headers = []
        self.subheaders = []
        self.captions = []
        self.infos = []
        self.errors = []
        self.writes = []
        self.metrics = []
        self.column_counts = []

    def title(self, value):
        self.titles.append(str(value))

    def header(self, value):
        self.headers.append(str(value))

    def subheader(self, value):
        self.subheaders.append(str(value))

    def caption(self, value):
        self.captions.append(str(value))

    def info(self, value):
        self.infos.append(str(value))

    def error(self, value):
        self.errors.append(str(value))

    def write(self, value):
        self.writes.append(str(value))

    def columns(self, count):
        self.column_counts.append(int(count))
        return [_MetricColumn(self) for _ in range(int(count))]


def _case(case_id: str = "case-1"):
    return SimpleNamespace(
        case_id=case_id,
        name="Example v Example Ltd",
        case_number="REF-001",
        claimant="Example",
        respondent="Example Ltd",
        status="active",
    )


def _projection(case_id: str = "case-1"):
    return SimpleNamespace(
        case_header=SimpleNamespace(case_id=case_id),
        issues=(object(), object()),
        chronology=(object(), object(), object()),
        citations=(object(), object(), object(), object()),
        conflicts=(object(),),
        gaps=(object(), object()),
        risks=(object(), object(), object()),
    )


def test_no_active_matter_fails_closed_to_selection_message(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)

    matter_overview.show_matter_overview(None, None)

    assert fake.titles == ["\u2696\ufe0f Matter Overview"]
    assert fake.infos == ["Select or create a matter to open its workspace."]
    assert fake.metrics == []


def test_no_projection_shows_only_known_document_count_and_unavailable_metrics(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)

    matter_overview.show_matter_overview(
        _case(),
        None,
        selected_document_count=7,
    )

    assert ("Selected documents", 7) in fake.metrics
    assert ("Legal issues", "Not available") in fake.metrics
    assert ("Chronology events", "Not available") in fake.metrics
    assert ("Evidence citations", "Not available") in fake.metrics
    assert any("No validated frozen report projection" in value for value in fake.infos)
    assert fake.errors == []


def test_provider_error_fails_closed_before_no_projection_message(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)

    matter_overview.show_matter_overview(
        _case(),
        None,
        provider_error=RuntimeError("provider"),
        selected_document_count=2,
    )

    assert fake.metrics == [("Selected documents", 2)]
    assert len(fake.errors) == 1
    assert "stored report projection could not be validated" in fake.errors[0]
    assert fake.infos == []


def test_valid_projection_uses_only_exact_frozen_inventory_counts(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)
    monkeypatch.setattr(
        matter_overview,
        "validate_case_report_projection",
        lambda value: None,
    )

    matter_overview.show_matter_overview(
        _case(),
        _projection(),
        selected_document_count=5,
    )

    assert ("Selected documents", 5) in fake.metrics
    assert ("Legal issues", 2) in fake.metrics
    assert ("Chronology events", 3) in fake.metrics
    assert ("Evidence citations", 4) in fake.metrics
    assert ("Material conflicts", 1) in fake.metrics
    assert ("Evidence gaps", 2) in fake.metrics
    assert ("Risk areas", 3) in fake.metrics
    assert fake.errors == []
    assert any("not merits findings" in value for value in fake.captions)


def test_invalid_projection_fails_closed_before_projection_metrics(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)

    def reject(value):
        raise ValueError("invalid")

    monkeypatch.setattr(matter_overview, "validate_case_report_projection", reject)

    matter_overview.show_matter_overview(
        _case(),
        _projection(),
        selected_document_count=6,
    )

    assert fake.metrics == [("Selected documents", 6)]
    assert len(fake.errors) == 1
    assert "could not be validated" in fake.errors[0]


def test_cross_matter_projection_fails_closed_before_projection_metrics(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)
    monkeypatch.setattr(
        matter_overview,
        "validate_case_report_projection",
        lambda value: None,
    )

    matter_overview.show_matter_overview(
        _case("case-1"),
        _projection("case-2"),
        selected_document_count=3,
    )

    assert fake.metrics == [("Selected documents", 3)]
    assert len(fake.errors) == 1
    assert "different matter" in fake.errors[0]


def test_session_state_defaults_new_matter_to_overview_and_preserves_explicit_navigation():
    state = {}

    matter_overview.synchronise_matter_overview_session_state(
        "case-1",
        session_state=state,
    )
    assert matter_overview.is_matter_overview_active(state) is True

    matter_overview.set_matter_overview_view(state, False)
    matter_overview.synchronise_matter_overview_session_state(
        "case-1",
        session_state=state,
    )
    assert matter_overview.is_matter_overview_active(state) is False

    matter_overview.synchronise_matter_overview_session_state(
        "case-2",
        session_state=state,
    )
    assert matter_overview.is_matter_overview_active(state) is True

    matter_overview.synchronise_matter_overview_session_state(
        None,
        session_state=state,
    )
    assert matter_overview.is_matter_overview_active(state) is False


def test_module_dependency_boundary_is_presentation_only():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE))

    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    allowed_roots = {
        "__future__",
        "collections",
        "typing",
        "streamlit",
        "case_reporting",
    }
    assert not {
        name for name in imported
        if name.split(".", 1)[0] not in allowed_roots
    }

    forbidden_tokens = (
        "openai",
        "chromadb",
        "document_manager",
        "retriever",
        "evidence_search",
        "evidence_retrieval",
        "PdfReader",
        "convert_from_",
        "pytesseract",
        "upload_case_pdf",
        "CaseRepository",
    )
    assert not any(token in source for token in forbidden_tokens)


def test_metric_columns_use_at_most_two_columns_per_row(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(matter_overview, "st", fake)

    matter_overview._metric_columns(
        (
            ("Selected documents", 4),
            ("Legal issues", 3),
            ("Chronology events", 2),
            ("Evidence citations", 1),
        )
    )

    assert fake.column_counts == [2, 2]
    assert fake.metrics == [
        ("Selected documents", 4),
        ("Legal issues", 3),
        ("Chronology events", 2),
        ("Evidence citations", 1),
    ]
