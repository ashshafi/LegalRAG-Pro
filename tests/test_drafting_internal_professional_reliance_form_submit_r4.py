from pathlib import Path
import ast

TARGET = Path('src/ui/case_operator.py')
FUNCTION = '_render_working_draft_professional_review'
READY = '_internal_professional_reliance_ready'
APPROVE = 'Approve for internal professional reliance'

def _term(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None

def _function():
    text = TARGET.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    matches = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == FUNCTION
    ]
    assert len(matches) == 1
    return text, matches[0]

def test_internal_approval_form_submit_button_is_clickable_and_not_self_disabled():
    text, fn = _function()
    assignments = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and _term(node.value) == "form_submit_button"
        and node.value.args
        and isinstance(node.value.args[0], ast.Constant)
        and node.value.args[0].value == APPROVE
    ]
    assert len(assignments) == 1
    disabled = [kw.value for kw in assignments[0].value.keywords if kw.arg == "disabled"]
    assert len(disabled) == 1
    assert ast.unparse(disabled[0]) == "False"

def test_internal_approval_is_fail_closed_at_submit_time():
    text, fn = _function()
    approve = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and _term(node.value) == "form_submit_button"
        and node.value.args
        and isinstance(node.value.args[0], ast.Constant)
        and node.value.args[0].value == APPROVE
    ][0]
    click_var = approve.targets[0].id
    blocks = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == click_var
    ]
    assert len(blocks) == 1
    block = ast.get_source_segment(text, blocks[0]) or ""
    assert "FORM_SUBMIT_READINESS_GUARD_R4" in block
    assert f"if not {READY}:" in block
    assert "Internal professional approval was not recorded." in block
