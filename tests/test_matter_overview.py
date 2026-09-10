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
    projection = _projection()

    matter_overview.show_matter_overview(
        _case(),
        projection,
        selected_document_count=7,
    )

    assert ("Selected documents", 7) in fake.metrics
    assert ("Legal issues", len(projection.issues)) in fake.metrics
    assert ("Chronology events", len(projection.chronology)) in fake.metrics
    assert ("Evidence citations", len(projection.citations)) in fake.metrics

    labels = {label for label, _ in fake.metrics}
    assert "Material conflicts" not in labels
    assert "Evidence gaps" not in labels
    assert "Risk areas" not in labels

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
        "datetime",
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


def test_swr1_i1_attention_orders_overdue_then_high_then_unsettled():
    from datetime import date
    from types import SimpleNamespace

    def counts(**changes):
        values = {
            "disputed": 0,
            "insufficiently_evidenced": 0,
            "unresolved": 0,
            "partially_supported": 0,
            "well_supported": 0,
        }
        values.update(changes)
        return SimpleNamespace(**values)

    dashboard = SimpleNamespace(
        issues=(
            SimpleNamespace(
                issue_analysis_id="issue-overdue",
                issue_name="Overdue issue",
                synthesis_counts=counts(insufficiently_evidenced=1),
            ),
            SimpleNamespace(
                issue_analysis_id="issue-high",
                issue_name="High task issue",
                synthesis_counts=counts(disputed=1),
            ),
            SimpleNamespace(
                issue_analysis_id="issue-unsettled",
                issue_name="Unsettled issue",
                synthesis_counts=counts(unresolved=1),
            ),
        )
    )

    def task(issue_id, issue_name, title, priority, due):
        return SimpleNamespace(
            status=SimpleNamespace(value="open"),
            priority=SimpleNamespace(value=priority),
            due_date=due,
            issue_analysis_id=issue_id,
            issue_name=issue_name,
            title=title,
            why_it_matters="Recorded reason.",
        )

    rows = matter_overview._attention_rows(
        dashboard,
        (
            task(
                "issue-high",
                "High task issue",
                "High priority work",
                "high",
                "2026-09-20",
            ),
            task(
                "issue-overdue",
                "Overdue issue",
                "Overdue work",
                "medium",
                "2026-09-09",
            ),
        ),
        today=date(2026, 9, 10),
    )

    assert [row["operational_state"] for row in rows] == [
        "OVERDUE",
        "HIGH-PRIORITY TASK",
        "UNSETTLED ISSUE",
    ]
    assert [row["issue_name"] for row in rows] == [
        "Overdue issue",
        "High task issue",
        "Unsettled issue",
    ]


def test_swr1_i1_does_not_create_a_legal_risk_score():
    from pathlib import Path

    source = Path("src/ui/matter_overview.py").read_text(encoding="utf-8")
    assert "HIGH RISK" not in source
    assert "risk scores" in source
    assert "Task priority:" in source
    assert "_UNSETTLED_POSITIONS" in source


def test_swr1_i1_procedural_stage_is_truthfully_not_recorded():
    from pathlib import Path

    source = Path("src/ui/matter_overview.py").read_text(encoding="utf-8")
    assert "Procedural stage: Not recorded in the matter workspace." in source
    assert (
        "does not infer procedural stage, hearing dates or legal deadlines from document text"
        in source
    )


def test_swr1_i1_removes_ambiguous_report_attention_counters():
    from pathlib import Path

    source = Path("src/ui/matter_overview.py").read_text(encoding="utf-8")
    for label in ("Material conflicts", "Evidence gaps", "Risk areas"):
        assert label not in source
    assert "Needs attention now" in source
    assert "Matter information" in source
    assert "Quick Start" not in source


def test_swr1_i1_overview_remains_presentation_only():
    from pathlib import Path

    source = Path("src/ui/matter_overview.py").read_text(encoding="utf-8")
    for forbidden in (
        "load_active_governed_analytical_authority",
        "build_legal_issue_dashboard",
        "load_tasks",
        "create_task",
        "update_task",
        "chromadb",
        "openai",
    ):
        assert forbidden not in source


def test_swr1_i1_app_composes_read_only_issue_and_task_state():
    from pathlib import Path

    app = Path("src/app.py").read_text(encoding="utf-8")
    route = app.index("elif is_matter_overview_active(st.session_state):")
    show = app.index("    show_matter_overview(", route)
    tail = app[route : app.index("\nelse:", show)]

    assert "load_active_governed_analytical_authority(" in tail
    assert "build_legal_issue_dashboard(" in tail
    assert "load_tasks(active_case_id)" in tail
    assert "issue_dashboard=overview_issue_dashboard" in tail
    assert "tasks=overview_tasks" in tail
    assert "create_task(" not in tail
    assert "update_task(" not in tail

