from __future__ import annotations

import ast
from pathlib import Path

CASE_OPERATOR = Path("src/ui/case_operator.py")


def _function_source(name: str) -> str:
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(text, node)
            assert segment
            return segment
    raise AssertionError(f"function not found: {name}")


def test_gac2_ui_requires_objective_plan_and_explicit_run():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    assert "Advanced governed investigation" in text
    assert "Investigation objective" in text
    assert "Prepare investigation plan" in text
    assert "Run approved investigation plan" in text
    assert "build_governed_agentic_investigation_v2_plan" in text
    assert "append_governed_agentic_investigation_v2_receipt" in text


def test_gac2_is_professionally_gated_before_task_work_persistence():
    segment = _function_source("_render_governed_agentic_investigation_v2")
    assert "Accept advanced investigation" in segment
    assert "Reject advanced investigation" in segment
    assert "GovernedAgenticDecisionV2.ACCEPTED" in segment
    assert "GovernedAgenticDecisionV2.REJECTED" in segment
    assert "_persist_task_work_result(" in segment
    assert segment.index("GovernedAgenticDecisionV2.ACCEPTED") < segment.index(
        "_persist_task_work_result("
    )


def test_gac2_helper_does_not_mutate_professional_state_directly():
    segment = _function_source("_render_governed_agentic_investigation_v2")
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
        "save_working_draft",
        "approve_working_draft",
        "publish_work_product",
        "repository.update",
        "CaseRepository.update",
    }
    assert forbidden.isdisjoint(calls)


def test_gac2_does_not_touch_downstream_release_or_assessment():
    segment = _function_source("_render_governed_agentic_investigation_v2")
    for forbidden in (
        "propose_analytical_change",
        "review_analytical_change",
        "record_working_draft_professional_release",
        "CaseReportProjection",
        "court_or_tribunal_reliance",
    ):
        assert forbidden not in segment


def test_gac2_precedes_preserved_gac1_and_legacy_single_task_action():
    segment = _function_source("_render_approved_task_execution")
    gac2 = segment.index("_render_governed_agentic_investigation_v2(")
    gac1 = segment.index("_render_governed_agentic_investigation(")
    legacy = segment.index('key="case_operator_work_selected_task"')
    assert gac2 < gac1 < legacy
    assert "Legacy three-step governed investigation (GAC1)" in segment


def test_gac2_surfaces_persistent_investigation_history():
    segment = _function_source("_render_governed_agentic_investigation_v2")
    assert "load_governed_agentic_investigation_v2_receipts(" in segment
    assert "Previous advanced investigations" in segment
    assert "Execution receipt:" in segment


def test_gac2_preserves_gac1_import_and_runtime_surface():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    assert "from governed_agentic_investigation import (" in text
    assert "build_governed_agentic_investigation_plan" in text
    assert "_render_governed_agentic_investigation(" in text
    assert "from governed_agentic_investigation_v2 import (" in text
