from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.py"
UI = ROOT / "src" / "ui" / "document_register.py"

PROHIBITED_IMPORTS = {
    "chromadb",
    "config",
    "source_evidence",
    "case_management",
    "document_manager",
    "document_upload",
    "index_documents",
    "ocr",
    "retriever",
    "legalrag",
    "legal_analysis",
    "case_analysis",
    "case_reporting",
    "workspace_index",
}

FORBIDDEN_CALLS = {
    "put_blob",
    "publish_document_manifest",
    "publish_evidence_binding",
    "publish_analysis_receipt",
    "publish_projection_binding",
    "read_blob",
    "write_bytes",
    "write_text",
    "unlink",
    "rename",
    "replace",
    "mkdir",
    "rmdir",
    "remove",
    "delete",
    "upsert",
    "add",
    "rerun",
    "experimental_rerun",
    "html",
    "markdown",
}


def _roots(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".", 1)[0])
    return found


def _attribute_calls(tree: ast.AST) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }


def test_register_dependency_boundary_is_thin_and_read_only():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    imported = _roots(tree)
    assert imported.isdisjoint(PROHIBITED_IMPORTS)
    assert "streamlit" in imported
    assert "document_catalog" in imported
    assert _attribute_calls(tree).isdisjoint(FORBIDDEN_CALLS)


def test_register_has_no_generic_file_access_or_dynamic_execution():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }
    assert names.isdisjoint({"open", "exec", "eval"})


def test_register_catches_only_document_catalog_error():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    handlers = [
        handler
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].type, ast.Name)
    assert handlers[0].type.id == "DocumentCatalogError"


def test_register_contains_no_rerun_unsafe_html_or_markdown():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = _attribute_calls(tree)
    assert "rerun" not in calls
    assert "experimental_rerun" not in calls
    assert "html" not in calls
    assert "markdown" not in calls
    assert "unsafe_allow_html" not in source


def test_app_composition_is_case_upload_details_register_then_sidebar():
    source = APP.read_text(encoding="utf-8")
    assert "from ui.document_register import show_document_register" in source

    case_i = source.index("active_case = show_case_selector()")
    upload_i = source.index("show_document_upload(active_case_id)")
    details_i = source.index("show_document_details(active_case_id)")
    register_i = source.index("show_document_register(active_case_id)")
    sidebar_i = source.index("selected_documents, timeline_clicked = show_sidebar(")

    assert case_i < upload_i < details_i < register_i < sidebar_i


def test_existing_source_workspace_report_route_order_remains():
    source = APP.read_text(encoding="utf-8")
    source_i = source.index(
        'if st.session_state.get("m7_source_evidence_view", False):'
    )
    workspace_i = source.index(
        'elif st.session_state.get("m6_workspace_view")'
    )
    reports_i = source.index(
        'elif st.session_state.get("m55_main_view", "assistant") == "reports"'
    )
    assert source_i < workspace_i < reports_i
