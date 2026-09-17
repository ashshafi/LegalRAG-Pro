from pathlib import Path
import ast

TARGET = Path('src/ui/case_operator.py')
FUNCTION = '_render_working_draft_professional_review'
NEW_LABEL = 'Approve for internal professional reliance'
OLD_WARNING = 'Approval for reliance is unavailable because at least one'

def _terminal(call):
    if isinstance(call.func, ast.Name): return call.func.id
    if isinstance(call.func, ast.Attribute): return call.func.attr
    return None

def test_internal_professional_reliance_is_separate_from_current_assessment_authorization():
    text = TARGET.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == FUNCTION]
    assert len(fns) == 1
    assert OLD_WARNING not in text
    assert 'does not change, promote or replace the Current Assessment' in text
    buttons = [n for n in ast.walk(fns[0]) if isinstance(n, ast.Call) and _terminal(n) in ('button','form_submit_button') and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == NEW_LABEL]
    assert len(buttons) == 1
    disabled = [kw.value for kw in buttons[0].keywords if kw.arg == 'disabled']
    assert len(disabled) == 1
    assert ast.unparse(disabled[0]) == 'not _internal_professional_reliance_ready'

def test_internal_approval_readiness_requires_review_and_excludes_court_reliance():
    text = TARGET.read_text(encoding='utf-8-sig')
    assert 'and int(' in text
    assert '== 0' in text
    assert 'and not bool(' in text
    assert 'Internal professional approval records a separate work-product decision.' in text
