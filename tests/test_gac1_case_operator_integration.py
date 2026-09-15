from __future__ import annotations

import ast
from pathlib import Path

CASE_OPERATOR = Path("src/ui/case_operator.py")


def _function_source(name: str) -> str:
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            segment = ast.get_source_segment(text, node)
            assert segment
            return segment
    raise AssertionError(f"function not found: {name}")


def test_gac1_ui_is_explicit_and_professionally_gated():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    assert "Run governed investigation" in text
    assert "Accept proposed work" in text
    assert "Reject proposal" in text
    assert "append_governed_agentic_investigation_receipt" in text
    assert "append_governed_agentic_professional_decision" in text


def test_gac1_helper_does_not_create_complete_or_update_tasks():
    segment = _function_source("_render_governed_agentic_investigation")
    tree = ast.parse(segment)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            try:
                calls.append(ast.unparse(node.func))
            except Exception:
                pass
    forbidden = {
        "create_task",
        "update_task",
        "_update_task_status",
        "repository.update",
        "CaseRepository.update",
    }
    assert forbidden.isdisjoint(calls)


def test_gac1_acceptance_reuses_existing_task_work_persistence():
    segment = _function_source("_render_governed_agentic_investigation")
    assert "_persist_task_work_result(" in segment
    assert "GovernedAgenticDecision.ACCEPTED" in segment
    assert "GovernedAgenticDecision.REJECTED" in segment


def test_gac1_is_before_legacy_single_task_work_button():
    segment = _function_source("_render_approved_task_execution")
    assert segment.index("_render_governed_agentic_investigation(") < segment.index(
        'key="case_operator_work_selected_task"'
    )


def test_gac1_does_not_touch_downstream_approval_release():
    segment = _function_source("_render_governed_agentic_investigation")
    for forbidden in (
        "propose_analytical_change",
        "review_analytical_change",
        "save_working_draft",
        "approve_working_draft",
        "publish_work_product",
        "CaseReportProjection",
        "court_or_tribunal_reliance",
    ):
        assert forbidden not in segment



def test_gac1_r7_progress_and_elapsed_time_are_visible():
    segment = _function_source("_render_governed_agentic_investigation")
    assert "st.progress(" in segment
    assert "st.status(" in segment
    assert "Step {index} of {total_steps}" in segment
    assert "gac1_elapsed_seconds" in segment
    assert "gac1_total_elapsed_seconds" in segment
    assert "APITimeoutError" in segment
    assert "RateLimitError" in segment


def test_gac1_r7_proposal_is_compact_by_default():
    segment = _function_source("_render_governed_agentic_investigation")
    assert "_render_gac1_compact_proposal(result)" in segment
    assert "Full governed analysis and source/page references" in segment
    assert "expanded=False" in segment


def test_gac1_r7_semantic_button_colours_are_scoped():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    assert ".st-key-gac1_run_action button" in text
    assert "#1d4ed8" in text
    assert ".st-key-gac1_accept_action button" in text
    assert "#15803d" in text
    assert ".st-key-gac1_reject_action button" in text
    assert "#b91c1c" in text
    assert 'st.container(key="gac1_run_action")' in text
    assert 'st.container(key="gac1_accept_action")' in text
    assert 'st.container(key="gac1_reject_action")' in text



def test_gac1_r9_performance_diagnostics_are_display_only():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    segment = _function_source("_render_governed_agentic_investigation")
    assert "profile_governed_agentic_step_result(" in segment
    assert "build_governed_agentic_performance_profile(" in segment
    assert "_render_gac1_performance_profile(performance_profile)" in segment
    assert '"performance_profile"' in segment
    assert "_persist_task_work_result(" in segment


def test_gac1_r9_profiles_key_envelope_metrics():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    assert "Performance diagnostics" in text
    assert "unique file/page pair(s)" in text
    assert "answer-scope evidence key(s)" in text
    assert "Returned result envelope" in text
    assert "Server-side phase timings" in text
