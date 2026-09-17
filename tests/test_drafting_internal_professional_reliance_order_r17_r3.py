from pathlib import Path
import ast

TARGET = Path('src/ui/case_operator.py')
FUNCTION = '_render_working_draft_professional_review'
READY = '_internal_professional_reliance_ready'
LABELS = [('checkbox', 'I have reviewed the factual basis for this wording.'), ('checkbox', 'I have reviewed the legal authorities relevant to this wording.'), ('number_input', 'Unverified legal authorities remaining'), ('checkbox', 'I have applied my professional judgment to this wording.'), ('checkbox', 'This wording is intended for reliance in court or tribunal.')]
APPROVE = 'Approve for internal professional reliance'

def _term(call):
    if isinstance(call.func, ast.Name): return call.func.id
    if isinstance(call.func, ast.Attribute): return call.func.attr
    return None

def test_professional_review_readiness_is_evaluated_after_all_review_widgets():
    text=TARGET.read_text(encoding='utf-8-sig')
    tree=ast.parse(text)
    fn=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==FUNCTION][0]
    ready=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id==READY]
    assert len(ready)==1
    widgets=[]
    for method,label in LABELS:
        hits=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and _term(n.value)==method and n.value.args and isinstance(n.value.args[0],ast.Constant) and n.value.args[0].value==label]
        assert len(hits)==1
        widgets.append(hits[0])
    approve=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and _term(n.value) in ('button','form_submit_button') and n.value.args and isinstance(n.value.args[0],ast.Constant) and n.value.args[0].value==APPROVE]
    assert len(approve)==1
    assert max(n.end_lineno for n in widgets) < ready[0].lineno < approve[0].lineno

def test_r17_readiness_and_caption_are_singletons():
    text=TARGET.read_text(encoding='utf-8-sig')
    assert text.count(READY + ' = (')==1
    assert text.count('Internal professional approval records a separate work-product decision.')==1
