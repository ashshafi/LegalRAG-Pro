from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "app.py"
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _imports() -> list[str]:
    result: list[str] = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                result.append(f"{node.module}.{alias.name}")
    return result


def _calls(name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(TREE)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_app_imports_new_binding_manager_without_direct_activation_authority():
    imports = _imports()
    assert imports.count(
        "ui.finance_binding_manager.show_finance_binding_manager"
    ) == 1
    assert not any("activation" in item for item in imports)
    assert "activate_finance_case_binding" not in SOURCE


def test_unbound_finance_branch_preserves_p13_fail_closed_message_then_offers_manager():
    expected = (
        'if finance_binding is None:\n'
        '            st.info("No active Finance workspace is bound to this matter.")\n'
        '            show_finance_binding_manager(case_id=active_case_id)'
    )
    assert expected in SOURCE
    assert "list_finance" not in SOURCE
    assert "discover" not in SOURCE.lower()


def test_manager_receives_case_identity_only_and_never_derives_workspace_from_case():
    calls = _calls("show_finance_binding_manager")
    assert len(calls) == 1
    call = calls[0]
    assert call.args == []
    assert len(call.keywords) == 1
    kw = call.keywords[0]
    assert kw.arg == "case_id"
    assert isinstance(kw.value, ast.Name)
    assert kw.value.id == "active_case_id"

    assert "workspace_id=active_case_id" not in SOURCE.replace(" ", "")
    assert "workspace_id = active_case_id" not in SOURCE
