from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_OPERATOR = ROOT / "src" / "ui" / "case_operator.py"
HELPER = ROOT / "src" / "case_operator_custom_task.py"


def _function_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    segment = ast.get_source_segment(text, node)
    assert segment
    return segment


def test_case_operator_exposes_custom_task_before_open_task_early_return():
    segment = _function_source(CASE_OPERATOR, "_render_approved_task_execution")
    assert 'with st.expander("Start a custom governed task"' in segment
    assert "render_custom_governed_task_initiation(case_id=case_id)" in segment
    assert segment.index("render_custom_governed_task_initiation") < segment.index(
        "if not open_tasks:"
    )


def test_custom_task_uses_governed_issue_identity_not_free_text_issue_name():
    text = HELPER.read_text(encoding="utf-8")
    assert 'getattr(issue, "issue_analysis_id"' in text
    assert '"Related legal issue"' in text
    assert "format_func=lambda value: _issue_label(keyed[value])" in text
    assert "issue_analysis_id=selected_id" in text


def test_custom_task_delegates_creation_to_existing_professional_task_creator():
    text = HELPER.read_text(encoding="utf-8")
    assert "show_issue_task_creator(" in text
    assert 'origin="next_legal_action"' in text
    assert "default_title=_clean(title)" in text
    assert "originating_question=_clean(objective)" in text
    assert "why_it_matters=_clean(objective)" in text
    assert "create_task(" not in text


def test_custom_form_does_not_run_gac2_or_mutate_assessment_directly():
    text = HELPER.read_text(encoding="utf-8")
    forbidden = (
        "build_governed_agentic_investigation_v2_plan",
        "run_governed_agentic_investigation_v2",
        "append_governed_agentic_investigation_v2_receipt",
        "update_task(",
        "activate_authority",
        "publish_authority",
    )
    for token in forbidden:
        assert token not in text


def test_custom_form_requires_title_and_objective_before_task_proposal():
    segment = _function_source(HELPER, "render_custom_governed_task_initiation")
    guard = "if not (_clean(title) and _clean(objective)):"
    assert guard in segment
    assert segment.index(guard) < segment.index("show_issue_task_creator(")
