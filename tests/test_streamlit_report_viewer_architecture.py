from __future__ import annotations

import ast
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "src" / "report_projection_provider.py"
REPORTS = ROOT / "src" / "ui" / "reports.py"
SIDEBAR = ROOT / "src" / "ui" / "sidebar.py"
APP = ROOT / "src" / "app.py"
BASELINE = "25013b7"
APPROVED_SESSION_KEYS = {
    "m55_main_view",
    "m55_report_case_id",
    "m55_report_projection_id",
    "m55_report_projection_payload_sha256",
    "m55_report_manifest_id",
    "m55_report_section_id",
    "m55_report_export_format",
    "m55_report_artifact_cache",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result.add(node.module)
    return result


def _session_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    tree = _tree(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        if not (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "st"
            and node.value.attr == "session_state"
        ):
            continue
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value.startswith("m55_"):
                keys.add(node.slice.value)
    return keys


def test_provider_dependency_boundary_is_narrow_and_non_streamlit():
    imports = _imports(PROVIDER)
    allowed_prefixes = (
        "__future__",
        "pathlib",
        "stat",
        "uuid",
        "case_reporting.models",
        "case_reporting.serialization",
        "case_reporting.validation",
    )
    assert all(name.startswith(allowed_prefixes) for name in imports)
    forbidden = {
        "streamlit",
        "case_analysis",
        "legal_analysis",
        "case_management",
        "document_manager",
        "retrieval_scope",
        "retriever",
        "retrieval_quality",
        "query_expander",
        "chromadb",
        "openai",
        "config",
    }
    assert not any(name.split(".")[0] in forbidden for name in imports)


def test_native_viewer_has_only_approved_dependency_direction():
    imports = _imports(REPORTS)
    forbidden = {
        "case_analysis",
        "legal_analysis",
        "case_management",
        "document_manager",
        "retrieval_scope",
        "retriever",
        "retrieval_quality",
        "query_expander",
        "chromadb",
        "openai",
        "config",
    }
    assert not any(name.split(".")[0] in forbidden for name in imports)
    assert "streamlit" in imports
    assert "case_reporting.models" in imports
    assert "case_reporting.validation" in imports
    assert "case_reporting.markdown" in imports
    assert "case_reporting.html" in imports
    assert "case_reporting.pdf" in imports


def test_native_viewer_contains_no_unapproved_embedded_content_or_global_cache_api():
    source = REPORTS.read_text(encoding="utf-8")
    prohibited = (
        "unsafe_allow_html",
        "components.html",
        "st.iframe",
        "st.pdf",
        "base64",
        "st.cache_data",
        "st.cache_resource",
        "functools.cache",
    )
    for token in prohibited:
        assert token not in source


def test_provider_contains_no_scan_latest_or_projection_build_path():
    source = PROVIDER.read_text(encoding="utf-8")
    prohibited = (
        ".glob(",
        ".rglob(",
        "getmtime",
        "st_mtime",
        "build_case_report_projection",
        "CaseRepository",
        "chromadb",
        "openai",
    )
    for token in prohibited:
        assert token not in source
    assert '"report_projections"' in source
    assert '"active.json"' in source


def test_exact_public_provider_api_is_frozen():
    tree = _tree(PROVIDER)
    public_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    public_classes = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    }
    assert public_functions == {"load_active_case_report_projection"}
    assert public_classes == {"ReportProjectionProviderError"}


def test_m55_uses_only_the_frozen_explicit_session_state_keys():
    keys = set()
    for path in (REPORTS, SIDEBAR, APP):
        keys.update(_session_keys(path))
    assert keys == APPROVED_SESSION_KEYS


def test_sidebar_preserves_two_value_contract_and_adds_only_keyword_reports_availability():
    tree = _tree(SIDEBAR)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar"
    )
    assert [item.arg for item in function.args.args] == ["active_case_id"]
    assert [item.arg for item in function.args.kwonlyargs] == ["reports_available"]
    source = SIDEBAR.read_text(encoding="utf-8")
    assert '"📄 Reports"' in source
    assert "disabled=not reports_available" in source
    assert 'st.session_state["m55_main_view"] = "reports"' in source
    assert 'st.session_state["m55_main_view"] = "assistant"' in source
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    assert any(
        isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2
        for node in returns
    )


def test_app_loads_provider_before_sidebar_and_routes_only_assistant_or_reports():
    source = APP.read_text(encoding="utf-8")
    provider_call = source.index("load_active_case_report_projection(active_case_id)")
    sync_call = source.index("synchronise_report_session_state(active_case_id, report_projection)")
    sidebar_call = source.index("show_sidebar(")
    assert provider_call < sync_call < sidebar_call
    assert '== "reports"' in source
    assert "show_report_viewer(" in source
    assert "show_chat(" in source


def test_report_availability_is_projection_based_not_document_count_based():
    source = APP.read_text(encoding="utf-8")
    start = source.index("reports_available = (")
    end = source.index(")\n\nselected_documents", start) + 1
    expression = source[start:end]
    assert "report_projection is not None" in expression
    assert "report_provider_error is None" in expression
    assert "documents" not in expression
    assert "docs" not in expression


def test_renderers_are_sibling_inputs_from_projection_not_chained_artifacts():
    source = REPORTS.read_text(encoding="utf-8")
    assert "render_markdown_report(projection)" in source
    assert "render_html_report(projection)" in source
    assert "render_pdf_report(projection)" in source
    assert "render_html_report(render_markdown" not in source
    assert "render_pdf_report(render_html" not in source
    assert "render_pdf_report(render_markdown" not in source


def test_requirements_and_frozen_reporting_tree_are_unchanged_from_m54_baseline():
    subprocess.run(
        ["git", "diff", "--exit-code", BASELINE, "--", "requirements.txt"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    frozen_paths = [
        "src/case_analysis",
        "src/case_reporting",
        "tests/fixtures/case_reporting/m52_full_audit.md",
        "tests/fixtures/case_reporting/m53_full_audit.html",
        "tests/fixtures/case_reporting/m54_full_audit.pdf",
    ]
    subprocess.run(
        ["git", "diff", "--exit-code", BASELINE, "--", *frozen_paths],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    # U9C-B15-EQ4 is an expressly governed corrective exception to
    # the historical M5.4 legal-analysis freeze.  Preserve the
    # freeze for every other legal-analysis path.
    allowed_eq4_legal_analysis = {
        "src/legal_analysis/evidence_mapper.py",
        "src/legal_analysis/search_profiles.py",
    }
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            BASELINE,
            "--",
            "src/legal_analysis",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = {
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    }
    assert observed == allowed_eq4_legal_analysis
