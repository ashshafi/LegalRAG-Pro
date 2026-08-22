from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDEBAR_PATH = ROOT / "src" / "ui" / "sidebar.py"
SOURCE = SIDEBAR_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""

def test_sidebar_exposes_one_case_scoped_finance_navigation_intent() -> None:
    matches: list[ast.Call] = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call) and _dotted(node.func) == "st.sidebar.button":
            if node.args and isinstance(node.args[0], ast.Constant):
                if node.args[0].value == "💹 Finance":
                    matches.append(node)
    assert len(matches) == 1
    disabled = [kw for kw in matches[0].keywords if kw.arg == "disabled"]
    assert len(disabled) == 1
    assert ast.unparse(disabled[0].value) == "active_case_id is None"

def test_finance_button_owns_navigation_intent_not_binding_resolution() -> None:
    assert "finance_clicked = st.sidebar.button(" in SOURCE
    assert "if finance_clicked:" in SOURCE
    assert 'st.session_state["m55_main_view"] = "finance"' in SOURCE
    assert "load_active_finance_case_binding" not in SOURCE
    assert "show_finance_workspace" not in SOURCE
    assert "activate_finance_case_binding" not in SOURCE

def test_finance_navigation_clears_competing_legal_and_matter_views() -> None:
    required = [
        "set_matter_overview_view(st.session_state, False)",
        'st.session_state["ppr3_legal_issue_dashboard_view"] = False',
        'st.session_state["u8_evidence_inspection_view"] = False',
        'st.session_state["m7_source_evidence_view"] = False',
        'st.session_state["m6_workspace_view"] = None',
        'st.session_state["m55_main_view"] = "finance"',
    ]
    for item in required:
        assert item in SOURCE

def test_sidebar_does_not_create_a_workspace_identity_or_binding() -> None:
    forbidden = [
        "workspace_id = active_case_id",
        "workspace_id=active_case_id",
        "FinanceCaseActiveBinding(",
        "activate_finance_case_binding",
    ]
    for item in forbidden:
        assert item not in SOURCE
