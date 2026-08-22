# Regression tests for truthful sidebar provider-status presentation.

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIDEBAR = ROOT / "src" / "ui" / "sidebar.py"


def _source() -> str:
    return SIDEBAR.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_source(), filename=str(SIDEBAR))


def _show_sidebar() -> ast.FunctionDef:
    return next(
        node
        for node in _tree().body
        if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar"
    )


def _sidebar_calls(method: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != method:
            continue
        sidebar = func.value
        if not isinstance(sidebar, ast.Attribute) or sidebar.attr != "sidebar":
            continue
        owner = sidebar.value
        if isinstance(owner, ast.Name) and owner.id == "st":
            calls.append(node)
    return calls


def test_sidebar_does_not_claim_unverified_provider_connectivity() -> None:
    source = _source()

    assert "OpenAI Connected" not in source
    assert "Chroma Connected" not in source
    assert "Connected" not in source


def test_sidebar_does_not_add_provider_or_health_probe_dependencies() -> None:
    tree = _tree()

    imported_modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden_roots = {"openai", "chromadb", "config", "requests", "httpx", "urllib"}
    assert not {
        module
        for module in imported_modules
        if module.split(".", 1)[0] in forbidden_roots
    }

    source = _source()
    forbidden_probe_tokens = (
        "heartbeat(",
        ".health(",
        "responses.create(",
        "embeddings.create(",
        "PersistentClient(",
        "get_or_create_collection(",
    )
    assert not any(token in source for token in forbidden_probe_tokens)


def test_sidebar_preserves_truthful_status_heading_and_document_counts() -> None:
    source = _source()
    expected_status_title = chr(0x1F4CA) + " Status"

    title_values = [
        call.args[0].value
        for call in _sidebar_calls("title")
        if call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ]

    assert expected_status_title in title_values
    assert 'st.sidebar.info(f"{len(docs)} document(s) in active matter")' in source
    assert 'st.sidebar.info(f"{len(docs)} document(s) indexed")' in source


def test_show_sidebar_signature_and_two_value_return_contract_are_preserved() -> None:
    function = _show_sidebar()

    assert [arg.arg for arg in function.args.args] == ["active_case_id"]
    assert [arg.arg for arg in function.args.kwonlyargs] == ["reports_available"]

    returns = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert len(returns) == 1

    value = returns[0].value
    assert isinstance(value, ast.Tuple)
    assert [
        element.id
        for element in value.elts
        if isinstance(element, ast.Name)
    ] == ["selected_documents", "timeline_clicked"]
