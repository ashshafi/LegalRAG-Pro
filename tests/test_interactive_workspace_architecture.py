from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "workspace_index.py"
WORKSPACE = ROOT / "src" / "ui" / "workspace.py"
APP = ROOT / "src" / "app.py"
SIDEBAR = ROOT / "src" / "ui" / "sidebar.py"
M55_ARCH = ROOT / "tests" / "test_streamlit_report_viewer_architecture.py"
M6_BASELINE = "528c669"
REQUIREMENTS_BASELINE = "b5a3f838e158c2ac5eab81e007e2b1ac416d1edc"
RP1_PROJECTION_SHA256 = "f0aaf1ac2a04a4e2667e4a74647e8b5870c1c0999257de2b8a1b0e0fa8e76fd7"
PERF1_REPORT_PROVIDER_SHA256 = "9d69fea3fc22f61d23042f543782d249623cfeee9a2d3a2524d537b79efa9b57"
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
        "legal_issue_dashboard",
        "ui.solicitor_tasks",
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
    assert "show_workspace(" in source
    assert "evidential_dashboard=evidential_dashboard" in source


def test_sidebar_signature_and_two_value_contract_remain_frozen():
    tree = _tree(SIDEBAR)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar")
    assert [arg.arg for arg in function.args.args] == ["active_case_id"]
    assert [arg.arg for arg in function.args.kwonlyargs] == ["reports_available"]
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    assert any(isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2 for node in returns)
    source = SIDEBAR.read_text(encoding="utf-8")
    for label in ("📚 Matter workspace", "🔎 Evidence", "👥 People"):
        assert label in source
    assert 'st.session_state["m6_workspace_view"] = "review"' in source
    assert 'st.session_state["m6_workspace_view"] = "evidence"' in source
    assert 'st.session_state["m6_workspace_view"] = "people"' in source
    workspace = WORKSPACE.read_text(encoding="utf-8")
    assert "Compare evidence use" in workspace
    assert "📑 Compare Documents" not in source


def test_m55_milestone_local_worktree_assertion_only_is_retired():
    source = M55_ARCH.read_text(encoding="utf-8")
    assert "AUTHORIZED_PATHS" not in source
    assert "test_worktree_delta_is_confined_to_seven_authorised_paths" not in source
    assert 'BASELINE = "25013b7"' in source
    assert "test_requirements_and_frozen_reporting_tree_are_unchanged_from_m54_baseline" in source
    assert "test_provider_dependency_boundary_is_narrow_and_non_streamlit" in source
    assert "test_native_viewer_has_only_approved_dependency_direction" in source


def test_requirements_and_frozen_semantic_reporting_boundaries_remain_governed():
    subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            REQUIREMENTS_BASELINE,
            "--",
            "requirements.txt",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    # RP1 is an expressly governed report-projection compatibility repair.
    # Preserve the historical M6 semantic boundary everywhere else, and permit
    # exactly one case-reporting path at its exact accepted content identity.
    semantic_protected_except_rp1_and_perf1 = [
        "src/ui/reports.py",
        "src/case_analysis",
        "tests/fixtures/case_reporting/m52_full_audit.md",
        "tests/fixtures/case_reporting/m53_full_audit.html",
        "tests/fixtures/case_reporting/m54_full_audit.pdf",
    ]
    subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            M6_BASELINE,
            "--",
            *semantic_protected_except_rp1_and_perf1,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    # PERF1 is an expressly governed performance-only exception for the
    # read-only report-projection provider.  Its exact accepted bytes are sealed
    # independently; no report-projection semantic or publication path is widened.
    assert (
        hashlib.sha256(
            (ROOT / "src" / "report_projection_provider.py").read_bytes()
        ).hexdigest()
        == PERF1_REPORT_PROVIDER_SHA256
    )

    rp1_result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            M6_BASELINE,
            "--",
            "src/case_reporting",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    rp1_observed = {
        line.strip().replace("\\", "/")
        for line in rp1_result.stdout.splitlines()
        if line.strip()
    }
    assert rp1_observed == {"src/case_reporting/projection.py"}
    assert (
        hashlib.sha256(
            (ROOT / "src" / "case_reporting" / "projection.py").read_bytes()
        ).hexdigest()
        == RP1_PROJECTION_SHA256
    )

    # U9C-B15-EQ4 is an expressly governed corrective exception to
    # the historical M6 legal-analysis freeze.  The exception is
    # exact: no legal-analysis path other than these two may differ.
    allowed_eq4_legal_analysis = {
        "src/legal_analysis/evidence_mapper.py",
        "src/legal_analysis/search_profiles.py",
    }
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            M6_BASELINE,
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

def test_ierw_issue_review_is_an_m6_projection_only_view():
    app = APP.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    route = app.index('elif st.session_state.get("m6_workspace_view")')
    show = app.index("evidential_dashboard=evidential_dashboard", route)
    reports = app.index('elif st.session_state.get("m55_main_view", "assistant") == "reports"')
    assert route < show < reports
    assert '"review", "traceability", "evidence", "chronology", "people", "comparison"' in app

    assert '"review": "Legal issue review"' in workspace
    assert 'if view == "review":' in workspace
    assert "_render_issue_review(index, evidential_dashboard)" in workspace
    assert '"ierw_review_issue_id"' in workspace
    assert 'st.session_state["m6_evidence_issue_ids"] = [selected_issue_id]' in workspace
    assert 'st.session_state["m6_chronology_issue_ids"] = [selected_issue_id]' in workspace
    assert 'st.session_state["m6_trace_kind"] = "issue"' in workspace

    for prohibited in (
        "route_question_to_active_authority",
        "build_runtime_authority_context",
        "ask_with_reference_findings",
        "resolve_projection_citation_source",
        "load_active_governed_analytical_authority",
        "GovernedAnalyticalAuthorityProviderError",
        "build_legal_issue_dashboard",
    ):
        assert prohibited not in workspace


def test_ierw_evidential_position_composition_is_read_only_at_app_root():
    app = APP.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    route = app.index('elif st.session_state.get("m6_workspace_view")')
    provider = app.index("load_active_governed_analytical_authority(active_case_id)", route)
    builder = app.index("build_legal_issue_dashboard(", provider)
    show = app.index("evidential_dashboard=evidential_dashboard", builder)
    reports = app.index('elif st.session_state.get("m55_main_view", "assistant") == "reports"')
    assert route < provider < builder < show < reports

    assert "from legal_issue_dashboard import LegalIssueDashboard" in workspace
    assert "evidential_dashboard: LegalIssueDashboard | None = None" in workspace
    assert "load_active_governed_analytical_authority" not in workspace
    assert "GovernedAnalyticalAuthorityProviderError" not in workspace
    assert "build_legal_issue_dashboard" not in workspace
    for token in (
        "supporting_evidence_keys", "adverse_evidence_keys", "corroborative_evidence_keys",
        "neutral_evidence_keys", "conflicting_evidence_keys",
    ):
        assert token in workspace
    assert "Unresolved evidence" not in workspace


def test_mw1_i4_chronology_to_task_uses_frozen_event_identity_and_exact_issue_binding():
    source = WORKSPACE.read_text(encoding="utf-8")
    assert "def _render_chronology(active_case_id: str, index: WorkspaceIndex)" in source
    assert "origin_chronology_event_id=event.event_id" in source
    assert "event.related_issue_ids" in source
    assert "index.issues_by_id" in source
    assert "related_issues=related_issues" in source
    assert 'origin="chronology"' in source
    assert "show_issue_task_creator(" in source
    assert "_render_chronology(active_case_id, index)" in source


def test_mw1_i4_chronology_to_task_fails_closed_without_exact_issue_identity():
    source = WORKSPACE.read_text(encoding="utf-8")
    assert "if not related_ids:" in source
    assert "if any(issue_id not in index.issues_by_id for issue_id in related_ids):" in source
    assert "Create task unavailable because this chronology event has no exact related legal issue." in source
    assert "cannot be resolved exactly" in source


def test_mw1_i4_chronology_task_does_not_copy_event_or_evidence_content():
    source = WORKSPACE.read_text(encoding="utf-8")
    creator_start = source.index("def _render_chronology_task_creator(")
    chronology_start = source.index("def _render_chronology(", creator_start)
    creator = source[creator_start:chronology_start]
    for forbidden in (
        "event.description",
        "event.assertions",
        "event.evidence_keys",
        "event.citations",
        "citation_ids",
    ):
        assert forbidden not in creator


def test_mw1_i4_does_not_use_legacy_timeline_or_analytical_mutation_paths():
    source = WORKSPACE.read_text(encoding="utf-8")
    imports = _imports(WORKSPACE)
    assert "features.timeline" not in imports
    assert "ui.timeline" not in imports
    for forbidden in (
        "governed_authority_revision",
        "matter_analysis_change",
        "controlled_agentic",
        "chromadb",
        "openai",
    ):
        assert forbidden not in source.lower()


def test_mw1_i4_multi_issue_selection_is_batched_inside_task_form():
    workspace = WORKSPACE.read_text(encoding="utf-8")
    task_ui = (ROOT / "src" / "ui" / "solicitor_tasks.py").read_text(encoding="utf-8")
    assert "related_issues=related_issues" in workspace
    assert 'resolved_issue_id = st.selectbox(' in task_ui
    form = task_ui.index("with st.form(")
    related = task_ui.index('resolved_issue_id = st.selectbox(', form)
    submit = task_ui.index('st.form_submit_button(', related)
    assert form < related < submit


def test_uxr1_working_workspace_prefers_legal_language_and_keeps_audit_available():
    workspace = WORKSPACE.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")

    assert '"review": "Legal issue review"' in workspace
    assert '"evidence": "Evidence"' in workspace
    assert '"chronology": "Chronology"' in workspace
    assert '"people": "People"' in workspace
    assert '"comparison": "Compare evidence use"' in workspace
    assert '"traceability": "Audit / traceability"' in workspace
    assert '_VIEW_ORDER = (\n    "review",' in workspace
    assert 'st.title("Matter workspace")' in workspace
    assert 'st.header("Audit / traceability")' in workspace
    assert 'with st.expander("Audit details", expanded=False):' in workspace

    assert '"📚 Matter workspace"' in sidebar
    assert 'st.session_state["m6_workspace_view"] = "review"' in sidebar


def test_uxr1_chronology_keeps_event_identity_in_audit_not_heading():
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert 'st.subheader(_chronology_event_heading(event))' in workspace
    assert 'st.subheader(f"Event · {event.event_id}")' not in workspace
    assert '_text("Event ID", event.event_id)' in workspace
    assert 'with st.expander("Audit details", expanded=False):' in workspace
    assert 'st.text("Event assertions")' in workspace


def test_uxr1_preserves_i4_chronology_task_origin_identity():
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "origin_chronology_event_id=event.event_id" in workspace
    assert "event.related_issue_ids" in workspace
    assert "related_issues=related_issues" in workspace
    assert 'origin="chronology"' in workspace
    assert "show_issue_task_creator(" in workspace
