from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/ui/matter_analysis_ledger.py"


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return call.func.value.id + "." + call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _label(call: ast.Call) -> str | None:
    if (
        call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        return call.args[0].value
    return None


def _parents(tree: ast.AST):
    result = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            result[child] = parent
    return result


def _inside_entry_form(node: ast.AST, parents) -> bool:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.With):
            for item in current.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and _call_name(expr) == "_matter_entry_form"
                ):
                    return True
    return False


def test_work_product_and_analytical_change_fields_are_submit_only():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = _parents(tree)

    labels = (
        "Work-product statement or proposition",
        "Status expressed by the work product",
        "Confidence expressed by the work product",
        "Governed evidence cited",
        "Proposed analytical status",
        "Proposed confidence",
        "Why should the analytical position change?",
    )

    for wanted in labels:
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _label(node) == wanted
            and _call_name(node) in {
                "st.text_area",
                "st.selectbox",
                "st.multiselect",
            }
        ]
        assert len(calls) == 1, wanted
        assert _inside_entry_form(calls[0], parents), wanted


def test_work_product_check_uses_form_submit():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _label(node) == "CHECK AGAINST CURRENT AUTHORITY"
    ]

    assert len(calls) == 1
    assert _call_name(calls[0]) == "_matter_form_submit_button"


def test_visibility_toggles_and_relationship_editor_remain_dynamic():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = _parents(tree)

    for wanted in ("+ Check work product", "+ Propose analytical change"):
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _label(node) == wanted
            and _call_name(node) == "st.toggle"
        ]
        assert len(calls) == 1
        assert not _inside_entry_form(calls[0], parents)

    # Relationship workflow intentionally remains dynamic in this release.
    for wanted in (
        "Relationship",
        "Evidence A role",
        "Evidence item A",
        "Evidence B role",
        "Evidence item B",
        "Why are these evidence items related?",
    ):
        assert wanted in source


def test_form_helpers_fail_compatibly_for_legacy_test_doubles():
    source = UI.read_text(encoding="utf-8")
    assert 'getattr(st, "form", None)' in source
    assert 'getattr(st, "form_submit_button", None)' in source
    assert "return st.button(label, **kwargs)" in source


def test_existing_fragment_decorator_remains_attached_to_ledger_renderer():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    decorators = [
        node.id
        for node in ledger.decorator_list
        if isinstance(node, ast.Name)
    ]

    if "_matter_ledger_fragment" in source:
        assert decorators == ["_matter_ledger_fragment"]


def test_no_new_openai_or_network_calls():
    source = UI.read_text(encoding="utf-8").casefold()
    assert "responses.create" not in source
    assert "embeddings.create" not in source
    assert "requests." not in source
    assert "httpx." not in source
