from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import ui.case_operator as case_operator


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ui" / "case_operator.py"


def _task(task_id: str):
    return SimpleNamespace(
        task_id=task_id,
        title=task_id,
    )


def _function_segment(name: str) -> str:
    text = SOURCE.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    lines = text.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(
                lines[node.lineno - 1 : node.end_lineno]
            )

    raise AssertionError(f"function not found: {name}")


def test_post_block_handoff_targets_first_ready_task():
    ready = (
        _task("ready-first"),
        _task("ready-second"),
    )

    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="blocked-task",
        current_selected_task_id="blocked-task",
        ready_tasks=ready,
    )

    assert target == "ready-first"


def test_no_handoff_without_one_shot_marker():
    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="",
        current_selected_task_id="blocked-task",
        ready_tasks=(_task("ready"),),
    )

    assert target is None


def test_manual_selection_is_not_overridden_when_marker_does_not_match():
    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="previously-blocked",
        current_selected_task_id="manually-selected-blocked",
        ready_tasks=(_task("ready"),),
    )

    assert target is None


def test_no_handoff_when_no_ready_task_exists():
    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="blocked-task",
        current_selected_task_id="blocked-task",
        ready_tasks=(),
    )

    assert target is None


def test_no_self_handoff():
    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="same-task",
        current_selected_task_id="same-task",
        ready_tasks=(_task("same-task"),),
    )

    assert target is None


def test_marker_is_consumed_before_selectbox_is_instantiated():
    segment = _function_segment(
        "_render_approved_task_execution"
    )

    pop_index = segment.index(
        "st.session_state.pop(_TASK_POST_BLOCK_HANDOFF_KEY"
    )

    selectbox_index = segment.index(
        "selected_task_id = st.selectbox("
    )

    assert pop_index < selectbox_index


def test_handoff_marker_is_created_only_after_successful_persistence():
    segment = _function_segment(
        "_render_approved_task_execution"
    )

    persist_index = segment.index(
        "if _persist_task_work_result("
    )

    marker_index = segment.index(
        "_TASK_POST_BLOCK_HANDOFF_KEY",
        persist_index,
    )

    rerun_index = segment.index(
        "st.rerun()",
        marker_index,
    )

    assert persist_index < marker_index < rerun_index
    assert (
        'extract_task_outcome(persisted_answer) == "BLOCKED"'
        in segment
    )


def test_v2b_preserves_manual_blocked_task_access_and_explicit_work_boundary():
    segment = _function_segment(
        "_render_approved_task_execution"
    )

    assert (
        "ordered_tasks = ready_tasks + blocked_tasks + unavailable_tasks"
        in segment
    )

    assert '"Retry blocked task"' in segment
    assert "case_operator_work_selected_task" in segment

    button_index = segment.index(
        "case_operator_work_selected_task"
    )

    provider_index = segment.index(
        "result = _run_question(",
        button_index,
    )

    assert button_index < provider_index
