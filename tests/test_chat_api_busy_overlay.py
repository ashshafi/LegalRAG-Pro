from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "src" / "chat.py"


def source_tree():
    source = CHAT.read_text(encoding="utf-8")
    return source, ast.parse(source)


def function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )


def call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def test_overlay_is_full_screen_and_blocks_input():
    source, tree = source_tree()
    helper = function(tree, "_show_chat_api_busy_overlay")
    segment = ast.get_source_segment(source, helper) or ""

    assert "position: fixed" in segment
    assert "inset: 0" in segment
    assert "pointer-events: all" in segment
    assert "cursor: wait" in segment
    assert "AI request in progress" in segment


def test_ask_is_wrapped_and_cleared_in_finally():
    _source, tree = source_tree()
    show = function(tree, "show_chat")

    calls = [
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and call_name(node) == "ask"
    ]
    assert len(calls) == 1
    assert ast.unparse(calls[0].args[0]) == "question"
    assert ast.unparse(calls[0].args[1]) == "selected_documents"

    parents = {}
    for parent in ast.walk(show):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    current: ast.AST = calls[0]
    enclosing_try = None

    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Try):
            enclosing_try = current
            break

    assert enclosing_try is not None

    final = "\n".join(
        ast.unparse(node)
        for node in enclosing_try.finalbody
    )
    assert "_chat_api_busy.empty()" in final


def test_overlay_helper_has_no_governance_or_provider_writes():
    source, tree = source_tree()
    helper = function(tree, "_show_chat_api_busy_overlay")
    segment = (ast.get_source_segment(source, helper) or "").casefold()

    for forbidden in (
        "propose_analytical_change",
        "review_analytical_change",
        "governed_authority_revision",
        "activate_governed",
        "responses.create",
        "openai",
    ):
        assert forbidden not in segment
