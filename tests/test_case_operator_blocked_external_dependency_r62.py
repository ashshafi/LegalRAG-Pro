from pathlib import Path
import ast


def _source() -> str:
    return Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")


def _function_segment(name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    )
    return ast.get_source_segment(source, node) or ""


def test_r62_execution_prompt_defines_external_dependency_as_blocked():
    segment = _function_segment("build_task_execution_question")
    assert "the task is BLOCKED, not CONTINUE" in segment
    assert "outside the current matter corpus" in " ".join(segment.split())
    assert "Do not repeat the same corpus search." in segment


def test_r62_continuation_prompt_defines_external_dependency_as_blocked():
    segment = _function_segment("build_task_continuation_question")
    assert "the task is BLOCKED, not CONTINUE" in segment
    assert "outside the current matter corpus" in " ".join(segment.split())


def test_r62_blocked_contract_preserves_unblock_marker():
    source = _source()
    required = (
        "NEXT_TASK_INVESTIGATION: <one focused unblock requirement>\n"
        "TASK_OUTCOME: BLOCKED"
    )
    assert source.count(required) == 2


def test_r62_continue_contract_is_limited_to_work_available_now():
    source = _source()
    assert source.count(
        "If further work remains AND the next investigation can be performed now"
    ) == 2


def test_r62_blocked_ui_surfaces_unblock_requirement_and_retry_label():
    segment = _function_segment("_render_approved_task_execution")
    assert "Retry blocked task" in segment
    assert "Unblock requirement" in segment
    assert "Retry only after the dependency has been satisfied" in segment
    assert 'latest_substantive_outcome == "BLOCKED"' in segment


def test_r62_blocked_does_not_mutate_task_status_automatically():
    source = _source()
    assert source.count("update_task(") == 1
    assert '"Approve completion"' in source
    assert '"Mark in progress"' in source


def test_r62_existing_exact_marker_continuation_retained():
    segment = _function_segment("build_task_continuation_question")
    assert "EXACT NEXT TASK INVESTIGATION" in segment
    assert "extract_next_task_investigation(raw_previous_answer)" in segment
