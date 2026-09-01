from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/ui/matter_analysis_ledger.py"

def call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return call.func.value.id + "." + call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None

def label(call: ast.Call) -> str | None:
    if (
        call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        return call.args[0].value
    return None

def parents(tree: ast.AST):
    result = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            result[child] = parent
    return result

def inside_entry_form(node: ast.AST, parent_map) -> bool:
    current = node
    while current in parent_map:
        current = parent_map[current]
        if isinstance(current, ast.With):
            for item in current.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and call_name(expr) == "_matter_entry_form"
                ):
                    return True
    return False

def test_relationship_fields_are_staged_into_forms():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    pmap = parents(tree)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    for wanted in (
        "Relationship",
        "Evidence A role",
        "Evidence B role",
        "Evidence item A",
        "Evidence item B",
        "Why are these evidence items related?",
    ):
        calls = [
            node
            for node in ast.walk(helper)
            if isinstance(node, ast.Call)
            and label(node) == wanted
            and call_name(node) in {
                "st.selectbox",
                "st.text_area",
            }
        ]
        assert len(calls) == 1, wanted
        assert inside_entry_form(calls[0], pmap), wanted

def test_relationship_has_exact_staging_submits():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    labels = [
        label(node)
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and call_name(node) == "_matter_form_submit_button"
    ]

    assert labels.count("SET RELATIONSHIP TYPE") == 1
    assert labels.count("SET EVIDENCE ROLES") == 1
    assert labels.count("PROPOSE RELATIONSHIP") == 1

def test_main_renderer_uses_helper_and_preserves_governed_write():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    helper_calls = [
        node
        for node in ast.walk(ledger)
        if isinstance(node, ast.Call)
        and call_name(node) == "_matter_relationship_proposal_editor"
    ]
    assert len(helper_calls) == 1

    proposal_calls = [
        node
        for node in ast.walk(ledger)
        if isinstance(node, ast.Call)
        and call_name(node) == "propose_relationship"
    ]
    assert len(proposal_calls) == 1

def test_existing_no_grey_and_fragment_boundaries_remain():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "def _matter_entry_form(" in source
    assert "def _matter_form_submit_button(" in source
    assert '"Work-product statement or proposition"' in source
    assert '"Proposed analytical status"' in source

    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    if "_matter_ledger_fragment" in source:
        decorators = [
            node.id
            for node in ledger.decorator_list
            if isinstance(node, ast.Name)
        ]
        assert decorators == ["_matter_ledger_fragment"]

def test_no_openai_or_network_calls_added():
    source = UI.read_text(encoding="utf-8").casefold()
    assert "responses.create" not in source
    assert "embeddings.create" not in source
    assert "requests." not in source
    assert "httpx." not in source
