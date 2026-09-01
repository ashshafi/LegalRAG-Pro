from __future__ import annotations

import ast
from pathlib import Path

UI = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "ui"
    / "professional_review_inbox.py"
)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_mal1_consideration_is_terminal_accept_only_and_current_authority():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = _function(tree, "_mal1_consideration_controls")
    segment = ast.get_source_segment(source, helper)

    assert "ACCEPTED_FOR_MAL1_CONSIDERATION" in segment
    assert "item.run.active_authority_id" in segment
    assert "current_authority_id" in segment
    assert "prior governed authority" in segment


def test_mal1_consideration_inputs_are_batched_in_one_form():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = _function(tree, "_mal1_consideration_controls")

    calls = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
    ]
    names = [_call_name(node) for node in calls]

    assert names.count("form") == 1
    assert names.count("form_submit_button") == 1
    assert names.count("selectbox") == 2
    assert names.count("text_area") == 1
    assert names.count("toggle") == 1
    assert "button" not in names


def test_mal1_bridge_is_called_exactly_once_and_only_after_submit():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = _function(tree, "_mal1_consideration_controls")

    bridge_calls = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_propose_mal1_from_prw"
    ]
    assert len(bridge_calls) == 1

    call = bridge_calls[0]
    keywords = {item.arg: item.value for item in call.keywords}
    assert "professional_review_events" in keywords
    assert ast.unparse(
        keywords["professional_review_events"]
    ) == "tuple(item.review_events)"

    submitted_guards = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.If)
        and "submitted" in ast.unparse(node.test)
    ]
    assert submitted_guards
    assert max(node.lineno for node in submitted_guards) < call.lineno


def test_rendering_inbox_binds_mal1_helper_to_terminal_reviewed_items():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    show = _function(tree, "show_professional_review_inbox")

    calls = [
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_mal1_consideration_controls"
    ]
    assert len(calls) == 1
    assert source.count("CREATE MAL1 PROPOSAL") == 1

    terminal_loops = [
        node
        for node in ast.walk(show)
        if isinstance(node, ast.For)
        and (
            "terminal" in ast.unparse(node.iter).casefold()
            or "reviewed" in ast.unparse(node.iter).casefold()
        )
    ]
    assert len(terminal_loops) == 1
    assert calls[0] in set(ast.walk(terminal_loops[0]))



def test_mal1_consideration_has_no_approval_gar1_activation_or_openai():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = _function(tree, "_mal1_consideration_controls")
    segment = (ast.get_source_segment(source, helper) or "").casefold()

    for forbidden in (
        "review_analytical_change",
        "governed_authority_revision",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
        "responses.create",
        "openai",
    ):
        assert forbidden not in segment


def test_ordinary_matter_ledger_mal1_ui_is_not_reimplemented_here():
    source = UI.read_text(encoding="utf-8")

    assert "_propose_mal1_from_prw" in source
    assert "propose_analytical_change(" not in source
    assert "review_analytical_change(" not in source
