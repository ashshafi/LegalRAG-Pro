from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "app.py"
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""

def _imports() -> list[str]:
    rows: list[str] = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            rows.extend(alias.name for alias in node.names)
    return rows

def _calls(name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(TREE)
        if isinstance(node, ast.Call) and _dotted(node.func).endswith(name)
    ]

def test_app_imports_only_the_published_finance_resolution_and_render_boundaries() -> None:
    imports = _imports()
    assert imports.count(
        "finance_case_binding.provider.load_active_finance_case_binding"
    ) == 1
    assert imports.count(
        "ui.finance_workspace_entrypoint.show_finance_workspace"
    ) == 1
    assert not any("activation" in item for item in imports)

def test_finance_navigation_is_dispatched_through_the_existing_main_view_channel() -> None:
    assert (
        'elif st.session_state.get("m55_main_view", "assistant") == "finance":'
        in SOURCE
    )

def test_app_resolves_case_to_workspace_only_through_the_published_active_binding_provider() -> None:
    calls = _calls("load_active_finance_case_binding")
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 1
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == "active_case_id"
    assert call.keywords == []

def test_finance_provider_resolution_is_guarded_by_an_active_case() -> None:
    import ast

    tree = ast.parse(SOURCE)
    parents: dict[ast.AST, tuple[ast.AST, str]] = {}
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            values = value if isinstance(value, list) else [value]
            for child in values:
                if isinstance(child, ast.AST):
                    parents[child] = (parent, field)

    calls = [
        candidate
        for candidate in ast.walk(tree)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id == "load_active_finance_case_binding"
    ]
    assert len(calls) == 1
    assert len(calls[0].args) == 1
    assert isinstance(calls[0].args[0], ast.Name)
    assert calls[0].args[0].id == "active_case_id"

    guarded = False
    current: ast.AST = calls[0]
    while current in parents:
        parent, relation = parents[current]
        if isinstance(parent, ast.If) and relation == "orelse":
            test = parent.test
            if (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Is)
                and len(test.comparators) == 1
                and isinstance(test.left, ast.Name)
                and test.left.id == "active_case_id"
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is None
            ):
                guarded = True
        current = parent

    assert guarded


def test_absent_active_binding_fails_closed_without_workspace_discovery() -> None:
    assert "if finance_binding is None:" in SOURCE
    assert 'st.info("No active Finance workspace is bound to this matter.")' in SOURCE
    assert "list_finance" not in SOURCE
    assert "discover" not in SOURCE.lower()

def test_valid_binding_renders_only_with_the_bound_workspace_id() -> None:
    calls = _calls("show_finance_workspace")
    assert len(calls) == 1
    call = calls[0]
    assert call.args == []
    assert len(call.keywords) == 1
    kw = call.keywords[0]
    assert kw.arg == "workspace_id"
    assert isinstance(kw.value, ast.Attribute)
    assert isinstance(kw.value.value, ast.Name)
    assert kw.value.value.id == "finance_binding"
    assert kw.value.attr == "workspace_id"

def test_app_does_not_activate_bindings_or_derive_workspace_identity_from_case_identity() -> None:
    assert "activate_finance_case_binding" not in SOURCE
    assert "workspace_id=active_case_id" not in SOURCE.replace(" ", "")
    assert "workspace_id = active_case_id" not in SOURCE
