from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.py"
REGISTER = ROOT / "src" / "ui" / "document_register.py"
VIEWER = ROOT / "src" / "ui" / "evidence_inspection.py"

PROHIBITED_VIEWER_IMPORTS = {
    "chromadb",
    "openai",
    "retriever",
    "legalrag",
    "document_manager",
    "document_upload",
    "index_documents",
    "ocr",
    "case_analysis",
    "legal_analysis",
    "case_reporting",
    "workspace_index",
    "document_catalog",
}

FORBIDDEN_CALLS = {
    "put_blob",
    "publish_document_manifest",
    "publish_evidence_binding",
    "publish_analysis_receipt",
    "publish_projection_binding",
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

APPROVED_U8_KEYS = {
    "u8_evidence_inspection_case_id",
    "u8_evidence_inspection_view",
    "u8_evidence_inspection_document_id",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


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
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _u8_literals(path: Path) -> set[str]:
    return {
        node.value
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("u8_evidence_inspection_")
        and "::" not in node.value
    }


def test_evidence_viewer_has_only_approved_dependency_direction():
    tree = _tree(VIEWER)
    roots = _roots(tree)
    assert "streamlit" in roots
    assert "evidence_search" in roots
    assert "evidence_roles" in roots
    assert "source_evidence" not in roots
    assert roots.isdisjoint(PROHIBITED_VIEWER_IMPORTS)
    assert _attribute_calls(tree).isdisjoint(FORBIDDEN_CALLS)


def test_evidence_viewer_has_no_generic_file_or_dynamic_execution():
    tree = _tree(VIEWER)
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert names.isdisjoint({"open", "exec", "eval"})


def test_viewer_catches_only_evidence_search_error_at_service_boundary():
    tree = _tree(VIEWER)
    handlers = [
        handler
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].type, ast.Name)
    assert handlers[0].type.id == "EvidenceSearchError"


def test_register_remains_catalog_only_and_never_imports_u8_services():
    tree = _tree(REGISTER)
    roots = _roots(tree)
    assert "document_catalog" in roots
    assert "evidence_search" not in roots
    assert "evidence_retrieval" not in roots
    assert "evidence_roles" not in roots
    assert "source_evidence" not in roots
    assert _attribute_calls(tree).isdisjoint(FORBIDDEN_CALLS)


def test_u8_navigation_namespace_is_isolated():
    keys = set()
    for path in (REGISTER, VIEWER, APP):
        keys.update(_u8_literals(path))
    assert keys == APPROVED_U8_KEYS


def test_app_synchronises_u8_before_register_and_routes_u8_before_existing_overlays():
    source = APP.read_text(encoding="utf-8")
    assert (
        "from ui.evidence_inspection import (\n"
        "    show_evidence_inspection,\n"
        "    synchronise_evidence_inspection_session_state,\n"
        ")"
    ) in source

    case_i = source.index("active_case = show_case_selector()")
    sync_i = source.index("synchronise_evidence_inspection_session_state(active_case_id)")
    register_i = source.index("show_document_register(active_case_id)")
    u8_route_i = source.index('if st.session_state.get("u8_evidence_inspection_view", False):')
    u8_show_i = source.index("show_evidence_inspection(active_case_id)")
    m7_route_i = source.index('elif st.session_state.get("m7_source_evidence_view", False):')
    workspace_i = source.index('elif st.session_state.get("m6_workspace_view")')
    reports_i = source.index('elif st.session_state.get("m55_main_view", "assistant") == "reports"')

    assert case_i < sync_i < register_i
    assert u8_route_i < u8_show_i < m7_route_i < workspace_i < reports_i


def test_u8_ui_contains_no_rerun_or_unsafe_embedded_content():
    for path in (REGISTER, VIEWER):
        source = path.read_text(encoding="utf-8")
        calls = _attribute_calls(_tree(path))
        assert "rerun" not in calls
        assert "experimental_rerun" not in calls
        assert "html" not in calls
        assert "markdown" not in calls
        assert "unsafe_allow_html" not in source
