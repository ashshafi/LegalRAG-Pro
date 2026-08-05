from __future__ import annotations

import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "workspace_index.py"
WORKSPACE = ROOT / "src" / "ui" / "workspace.py"
APP = ROOT / "src" / "app.py"
SIDEBAR = ROOT / "src" / "ui" / "sidebar.py"
M55_ARCH = ROOT / "tests" / "test_streamlit_report_viewer_architecture.py"
M6_BASELINE = "528c669"
APPROVED_M6_KEYS = {
    "m6_workspace_case_id",
    "m6_workspace_projection_id",
    "m6_workspace_projection_payload_sha256",
    "m6_workspace_manifest_id",
    "m6_workspace_view",
    "m6_trace_kind",
    "m6_trace_query",
    "m6_trace_selected_key",
    "m6_evidence_query",
    "m6_evidence_documents",
    "m6_evidence_source_types",
    "m6_evidence_statuses",
    "m6_evidence_provenance_types",
    "m6_evidence_provenance_confidences",
    "m6_evidence_authors",
    "m6_evidence_parties",
    "m6_evidence_issue_ids",
    "m6_chronology_query",
    "m6_chronology_event_types",
    "m6_chronology_participants",
    "m6_chronology_occurrence_statuses",
    "m6_chronology_timing_statuses",
    "m6_chronology_confidences",
    "m6_chronology_issue_ids",
    "m6_people_query",
    "m6_people_contexts",
    "m6_people_selected_value",
    "m6_compare_left_key",
    "m6_compare_right_key",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _m6_constants(path: Path) -> set[str]:
    return {
        node.value
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("m6_")
        and not node.value.endswith("_")
    }


def test_workspace_index_public_api_and_dependency_direction_are_frozen():
    tree = _tree(INDEX)
    public_functions = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    public_classes = {
        node.name for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    }
    assert public_functions == {"build_workspace_index", "literal_query_matches"}
    assert public_classes == {
        "WorkspaceIndexError",
        "WorkspaceObjectKey",
        "WorkspaceBacklink",
        "DocumentGroupKey",
        "RecordedNameOccurrence",
        "WorkspaceIndex",
    }
    imports = _imports(INDEX)
    allowed = {"__future__", "dataclasses", "types", "typing", "unicodedata", "case_reporting.models", "case_reporting.validation"}
    assert imports <= allowed


def test_workspace_ui_dependency_direction_and_source_access_are_narrow():
    imports = _imports(WORKSPACE)
    allowed = {
        "__future__",
        "dataclasses",
        "typing",
        "streamlit",
        "case_reporting.models",
        "case_reporting.validation",
        "workspace_index",
    }
    assert imports <= allowed
    forbidden_roots = {
        "report_projection_provider", "case_analysis", "legal_analysis", "case_management",
        "document_manager", "retriever", "legalrag", "chromadb", "openai", "features",
    }
    assert not any(name.split(".")[0] in forbidden_roots for name in imports)


def test_workspace_contains_no_unsafe_html_cache_retrieval_or_source_read_api():
    source = INDEX.read_text(encoding="utf-8") + "\n" + WORKSPACE.read_text(encoding="utf-8")
    prohibited = (
        "unsafe_allow_html",
        "components.html",
        "st.iframe",
        "st.cache_data",
        "st.cache_resource",
        "functools.cache",
        "chromadb",
        "openai",
        "build_case_report_projection",
        "legalrag.ask",
        "features.timeline",
        "document_manager",
        "PdfReader",
        "open(",
    )
    for token in prohibited:
        assert token not in source


def test_m6_uses_exact_approved_session_key_namespace_only():
    keys: set[str] = set()
    for path in (WORKSPACE, SIDEBAR, APP):
        keys.update(_m6_constants(path))
    assert keys == APPROVED_M6_KEYS


def test_m55_route_meaning_is_not_extended_by_m6():
    workspace = WORKSPACE.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "m55_main_view" not in workspace
    assert 'st.session_state["m55_main_view"] = "assistant"' in sidebar
    assert 'st.session_state["m55_main_view"] = "reports"' in sidebar
    assert 'st.session_state["m55_main_view"] = "workspace"' not in sidebar


def test_app_uses_single_provider_result_and_m6_overlay_precedes_m55_route():
    source = APP.read_text(encoding="utf-8")
    assert source.count("load_active_case_report_projection(active_case_id)") == 1
    report_sync = source.index("synchronise_report_session_state(active_case_id, report_projection)")
    workspace_sync = source.index("synchronise_workspace_session_state(active_case_id, report_projection)")
    sidebar = source.index("show_sidebar(")
    overlay = source.index('if st.session_state.get("m6_workspace_view")')
    reports = source.index('elif st.session_state.get("m55_main_view", "assistant") == "reports"')
    assert report_sync < workspace_sync < sidebar
    assert overlay < reports
    assert "show_workspace(active_case_id, report_projection)" in source


def test_sidebar_signature_and_two_value_contract_remain_frozen():
    tree = _tree(SIDEBAR)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar")
    assert [arg.arg for arg in function.args.args] == ["active_case_id"]
    assert [arg.arg for arg in function.args.kwonlyargs] == ["reports_available"]
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    assert any(isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2 for node in returns)
    source = SIDEBAR.read_text(encoding="utf-8")
    for label in ("🧭 Workspace", "📚 Evidence Explorer", "👤 People Explorer", "📑 Compare Documents"):
        assert label in source
    assert 'st.session_state["m6_workspace_view"] = "traceability"' in source
    assert 'st.session_state["m6_workspace_view"] = "evidence"' in source
    assert 'st.session_state["m6_workspace_view"] = "people"' in source
    assert 'st.session_state["m6_workspace_view"] = "comparison"' in source


def test_m55_milestone_local_worktree_assertion_only_is_retired():
    source = M55_ARCH.read_text(encoding="utf-8")
    assert "AUTHORIZED_PATHS" not in source
    assert "test_worktree_delta_is_confined_to_seven_authorised_paths" not in source
    assert 'BASELINE = "25013b7"' in source
    assert "test_requirements_and_frozen_reporting_tree_are_unchanged_from_m54_baseline" in source
    assert "test_provider_dependency_boundary_is_narrow_and_non_streamlit" in source
    assert "test_native_viewer_has_only_approved_dependency_direction" in source


def test_requirements_and_frozen_semantic_reporting_boundary_are_unchanged_from_m6_baseline():
    protected = [
        "requirements.txt",
        "src/report_projection_provider.py",
        "src/ui/reports.py",
        "src/case_reporting",
        "src/case_analysis",
        "src/legal_analysis",
        "tests/fixtures/case_reporting/m52_full_audit.md",
        "tests/fixtures/case_reporting/m53_full_audit.html",
        "tests/fixtures/case_reporting/m54_full_audit.pdf",
    ]
    subprocess.run(
        ["git", "diff", "--exit-code", M6_BASELINE, "--", *protected],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
