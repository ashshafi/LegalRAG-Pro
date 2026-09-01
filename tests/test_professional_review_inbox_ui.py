from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "src" / "ui" / "professional_review_inbox.py"
APP_PATH = ROOT / "src" / "app.py"


def test_prw2_ui_has_only_prw1_review_write_boundary():
    source = UI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    assert "review_agent_observation" in imported_names
    assert "publish_professional_review_event" in imported_names
    assert "load_professional_review_inbox" in imported_names

    forbidden = (
        "propose_analytical_change",
        "review_analytical_change",
        "governed_authority_revision",
        "activate_governed_analytical_authority",
        "publish_governed_analytical_authority",
    )
    for value in forbidden:
        assert value not in source


def test_prw2_ui_uses_exact_professional_review_decision_enum():
    source = UI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "ProfessionalReviewDecision" in names
    assert "DEFER" in attributes
    assert "ACCEPT_FOR_MAL1_CONSIDERATION" in attributes
    assert "REJECT" in attributes
    assert "RECORD PROFESSIONAL REVIEW" in source
    assert "does not create a MAL1 proposal" in source


def test_app_places_prw2_between_legal_issue_dashboard_and_matter_ledger():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "ui.professional_review_inbox"
    ]
    assert len(imports) == 1
    assert [alias.name for alias in imports[0].names] == [
        "show_professional_review_inbox"
    ]

    dashboard_call = source.index(
        "show_legal_issue_dashboard(active_case_id)"
    )
    inbox_call = source.index(
        "show_professional_review_inbox(active_case_id)"
    )
    ledger_call = source.index(
        "show_matter_analysis_ledger(active_case_id)"
    )

    assert dashboard_call < inbox_call < ledger_call
