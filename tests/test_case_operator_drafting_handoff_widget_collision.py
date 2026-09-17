
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "src" / "ui" / "solicitor_workflow.py"
CALLER = ROOT / "src" / "ui" / "case_operator.py"


def _fn(path: Path, name: str):
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    return text, matches[0]


def test_handoff_preserves_exact_context_without_widget_write():
    text, fn = _fn(WORKFLOW, "open_drafts_for_task_work")
    src = ast.get_source_segment(text, fn) or ""
    assert "_WC2_DRAFT_HANDOFF_KEY" in src
    assert '"case_id": case_id' in src
    assert '"task_id": task_id' in src
    assert '"progress_id": progress_id' in src
    assert 'route_solicitor_view("Drafts", case_id=case_id)' in src
    assert "case_operator_drafting_progress_" not in src


def test_live_caller_selects_work_before_handoff_call():
    text, fn = _fn(CALLER, "_render_drafting_workflow")
    src = ast.get_source_segment(text, fn) or ""
    select_pos = src.index('"Work to draft from"')
    key_pos = src.index('"case_operator_drafting_progress_"')
    button_pos = src.index('"Draft from this work"')
    call_pos = src.index("open_drafts_for_task_work(")
    assert select_pos <= key_pos < button_pos < call_pos


def test_workflow_only_clears_progress_widget_key():
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    occurrences = [
        line.strip()
        for line in text.splitlines()
        if "case_operator_drafting_progress_" in line
    ]
    assert occurrences == [
        'st.session_state.pop("case_operator_drafting_progress_" + task_id, None)'
    ]
