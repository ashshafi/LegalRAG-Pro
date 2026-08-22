from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src" / "ui" / "finance_binding_manager.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _imports() -> set[str]:
    found: set[str] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_binding_manager_is_the_separate_explicit_activation_ui_boundary():
    imports = _imports()
    assert "finance_case_binding.activation" in imports
    assert "finance_workspace_catalog" in imports
    assert "streamlit" in imports

    forbidden = {
        "finance_runtime_activation",
        "finance_report_projection_publication",
        "finance_data.provider_selection",
        "ui.finance_workspace",
        "ui.finance_workspace_entrypoint",
    }
    assert imports.isdisjoint(forbidden)


def test_binding_manager_does_not_publish_recalculate_or_render_finance_analysis():
    forbidden_fragments = (
        "publish_finance_report_projection",
        "activate_finance_runtime",
        "build_finance_runtime_projection",
        "render_finance_workspace",
        "show_finance_workspace",
    )
    for fragment in forbidden_fragments:
        assert fragment not in SOURCE


def test_activation_is_guarded_by_explicit_button_intent():
    functions = {
        node.name: node
        for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    show = functions["show_finance_binding_manager"]
    calls = [
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "activate_finance_case_binding"
    ]
    assert len(calls) == 1
    assert 'st.button("Bind Finance workspace", type="primary")' in SOURCE
