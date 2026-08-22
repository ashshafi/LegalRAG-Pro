from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.py"
SIDEBAR = ROOT / "src" / "ui" / "sidebar.py"
HEADER = ROOT / "src" / "ui" / "header.py"
CASES = ROOT / "src" / "ui" / "cases.py"
OVERVIEW = ROOT / "src" / "ui" / "matter_overview.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_product_header_is_general_legal_platform_identity():
    source = _source(HEADER)

    assert "LegalRAG Pro" in source
    assert "Auditable Case Intelligence" in source
    assert "AI Employment Tribunal Assistant" not in source


def test_case_selector_uses_matter_language_without_changing_persistence_contract():
    source = _source(CASES)

    for required in (
        "\U0001f5c2 Matters",
        "No matters yet. Create your first matter below.",
        "Active matter",
        "Reference: ",
        "\u2795 Create matter",
        "\u270f\ufe0f Edit active matter",
        "Matter name",
        "Create matter",
        "Matter updated.",
        "Assign to active matter",
    ):
        assert required in source

    for internal_contract in (
        "CaseRepository",
        "Case.create(",
        "case.case_id",
        "case.case_number",
        "claimant=claimant",
        "respondent=respondent",
    ):
        assert internal_contract in source

    assert 'st.text_input("Claimant"' in source
    assert 'st.text_input("Respondent"' in source


def test_sidebar_exposes_new_workspace_hierarchy_and_preserves_frozen_controls():
    source = _source(SIDEBAR)

    for section in ("MATTER", "CASE INTELLIGENCE", "LEGAL WORK", "AUDIT"):
        assert section in source

    for required in (
        "\u25a3 Overview",
        "\U0001f552 Chronology",
        "\U0001f50e Evidence",
        "\U0001f465 People",
        "\u2696\ufe0f Legal Issues",
        "\U0001f9e0 Analysis",
        
        "\U0001f4ac Assistant",
        "\u270d Drafting",
        "\U0001f4c4 Reports",
        "\U0001f517 Sources & Provenance",
        "\U0001f6e1 Audit Trail",
    ):
        assert required in source

    assert "Tribunal Tools" not in source
    assert "OpenAI Connected" not in source
    assert "Chroma Connected" not in source
    assert "Connected" not in source


def test_sidebar_signature_return_and_existing_workspace_state_semantics_remain_frozen():
    source = _source(SIDEBAR)
    tree = ast.parse(source, filename=str(SIDEBAR))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar"
    )

    assert [arg.arg for arg in function.args.args] == ["active_case_id"]
    assert [arg.arg for arg in function.args.kwonlyargs] == ["reports_available"]

    returns = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Tuple)
    assert [
        item.id
        for item in returns[0].value.elts
        if isinstance(item, ast.Name)
    ] == ["selected_documents", "timeline_clicked"]

    for exact in (
        'st.session_state["m6_workspace_view"] = "traceability"',
        'st.session_state["m6_workspace_view"] = "evidence"',
        'st.session_state["m6_workspace_view"] = "people"',
        'st.session_state["m55_main_view"] = "reports"',
        'st.session_state["m55_main_view"] = "assistant"',
    ):
        assert exact in source


def test_ppr4_route_state_is_encapsulated_outside_frozen_app_sidebar_key_namespace():
    overview = _source(OVERVIEW)
    app = _source(APP)
    sidebar = _source(SIDEBAR)

    assert '"ppr4_matter_overview_view"' in overview
    assert '"ppr4_matter_overview_case_id"' in overview
    assert '"ppr4_matter_overview_view"' not in app
    assert '"ppr4_matter_overview_view"' not in sidebar
    assert "set_matter_overview_view(st.session_state, True)" in sidebar
    assert "set_matter_overview_view(st.session_state, False)" in sidebar


def test_app_preserves_specialist_route_precedence_then_overview_then_assistant():
    source = _source(APP)

    u8 = source.index(
        'if st.session_state.get("u8_evidence_inspection_view", False):'
    )
    dashboard = source.index(
        'elif st.session_state.get("ppr3_legal_issue_dashboard_view", False):'
    )
    m7 = source.index(
        'elif st.session_state.get("m7_source_evidence_view", False):'
    )
    workspace = source.index('elif st.session_state.get("m6_workspace_view")')
    reports = source.index(
        'elif st.session_state.get("m55_main_view", "assistant") == "reports"'
    )
    overview = source.index("elif is_matter_overview_active(st.session_state):")
    assistant = source.index("show_chat(", overview)

    assert u8 < dashboard < m7 < workspace < reports < overview < assistant
    assert "show_matter_overview(" in source
    assert "provider_error=report_provider_error" in source
    assert "selected_document_count=len(selected_documents)" in source


def test_app_synchronises_overview_before_sidebar_and_keeps_provider_lookup_single():
    source = _source(APP)

    provider = source.index("load_active_case_report_projection(active_case_id)")
    report_sync = source.index(
        "synchronise_report_session_state(active_case_id, report_projection)"
    )
    overview_sync = source.index(
        "synchronise_matter_overview_session_state(\n"
        "    active_case_id,\n"
        "    session_state=st.session_state,\n"
        ")"
    )
    sidebar = source.index("show_sidebar(")

    assert source.count("load_active_case_report_projection(active_case_id)") == 1
    assert provider < report_sync < overview_sync < sidebar


def test_user_facing_app_matter_caption_is_generalised():
    source = _source(APP)

    assert "Active matter:" in source
    assert "Create a matter in the sidebar" in source
    assert "Active case:" not in source


def test_compare_documents_is_not_top_level_but_comparison_capability_remains():
    sidebar = _source(SIDEBAR)
    workspace = _source(ROOT / "src" / "ui" / "workspace.py")
    app = _source(APP)

    assert "Compare Documents" not in sidebar
    assert "Projection Evidence-Use Comparison" in workspace
    assert '"comparison"' in app
