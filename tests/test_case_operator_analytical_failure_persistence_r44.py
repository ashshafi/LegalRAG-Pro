from pathlib import Path
import ast


def _tree_and_source():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    return ast.parse(source), source


def _fn(tree, name):
    return next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_r44_helper_reads_analytical_failure_signals():
    tree, source = _tree_and_source()
    helper = _fn(tree, "_analytical_failure_reason")
    segment = ast.get_source_segment(source, helper) or ""
    assert 'result.get("analytical_validation_error")' in segment
    assert 'result.get("analytical_authority_mode")' in segment
    assert "invalid_analytical_output" in segment
    assert "invalid_authority" in segment


def test_r44_persistence_guard_is_inside_function_and_before_append():
    tree, source = _tree_and_source()
    fn = _fn(tree, "_persist_task_work_result")

    calls = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert "_analytical_failure_reason" in calls
    assert "append_task_work_progress" in calls

    segment = ast.get_source_segment(source, fn) or ""
    assert segment.index("_analytical_failure_reason(result)") < segment.index("append_task_work_progress(")


def test_r44_historical_failure_is_filtered_only_for_continuation():
    tree, source = _tree_and_source()
    render = _fn(tree, "_render_approved_task_execution")
    segment = ast.get_source_segment(source, render) or ""

    assert "_render_task_work_history(history=history)" in segment
    assert "_substantive_task_work_history(history)" in segment


def test_r44_continuation_uses_filtered_history_structurally():
    tree, _source = _tree_and_source()
    render = _fn(tree, "_render_approved_task_execution")

    calls = [
        node for node in ast.walk(render)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_task_continuation_question"
        )
    ]
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) >= 2
    second = call.args[1]
    assert isinstance(second, ast.Call)
    assert isinstance(second.func, ast.Name)
    assert second.func.id == "_substantive_task_work_history"


def test_r44_task_status_gate_retained():
    _tree, source = _tree_and_source()
    assert '"Approve completion"' in source
    assert '"Mark in progress"' in source
    assert source.count("update_task(") == 1


def test_r44_no_authority_mutation():
    _tree, source = _tree_and_source()
    assert "activate_authority" not in source
    assert "publish_authority" not in source
