"""Static architecture tests for the U3 governed upload UI."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "ui" / "document_upload.py"
APP = ROOT / "src" / "app.py"

PROHIBITED = {
    "chromadb", "config", "source_evidence", "index_documents", "ocr",
    "case_management", "document_manager", "retriever", "legalrag",
    "legal_analysis", "case_analysis", "case_reporting", "workspace_index",
    "hashlib", "tempfile", "subprocess",
}


def roots(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".", 1)[0])
    return found


def test_import_boundary():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = roots(tree)
    assert imported.isdisjoint(PROHIBITED)
    assert "streamlit" in imported
    assert "document_upload" in imported


def test_no_direct_ingestion_hashing_file_process_or_rerun_boundary():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in (
        "source_evidence", "index_documents", "hashlib", "tempfile",
        "subprocess", "unsafe_allow_html",
    ):
        assert forbidden not in source
    assert "rerun" not in calls
    assert "experimental_rerun" not in calls
    assert "html" not in calls
    assert "markdown" not in calls


def test_only_document_upload_error_is_caught():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    handlers = [
        handler
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].type, ast.Name)
    assert handlers[0].type.id == "DocumentUploadError"


def test_service_call_is_after_explicit_submit_return_guard():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_document_upload"
    )
    service = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "upload_service"
    ]
    guards = [
        node for node in ast.walk(function)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "submitted"
    ]
    assert len(service) == 1
    assert len(guards) == 1
    assert any(isinstance(item, ast.Return) for item in guards[0].body)
    assert service[0].lineno > guards[0].lineno


def test_app_composition_order():
    source = APP.read_text(encoding="utf-8")
    assert "from ui.document_upload import show_document_upload" in source
    case_i = source.index("active_case = show_case_selector()")
    upload_i = source.index("show_document_upload(active_case_id)")
    sidebar_i = source.index("selected_documents, timeline_clicked = show_sidebar(")
    assert case_i < upload_i < sidebar_i


def test_existing_m7_route_order_remains():
    source = APP.read_text(encoding="utf-8")
    source_i = source.index('if st.session_state.get("m7_source_evidence_view", False):')
    workspace_i = source.index('elif st.session_state.get("m6_workspace_view")')
    reports_i = source.index(
        'elif st.session_state.get("m55_main_view", "assistant") == "reports"'
    )
    assert source_i < workspace_i < reports_i
