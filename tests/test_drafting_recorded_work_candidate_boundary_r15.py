from pathlib import Path
import ast

TARGET = Path('src/drafting_working_draft_orchestration.py')
FUNCTION = '_validate_candidate_bridge'
WRAPPER = '_generation_evidence_keys_for_recorded_work'
LEGACY = 'generation_evidence_keys'

def test_candidate_boundary_routes_to_recorded_work_helper():
    text = TARGET.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    matches = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == FUNCTION
    ]
    assert len(matches) == 1
    fn = matches[0]
    wrappers = []
    legacies = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            if f.id == WRAPPER: wrappers.append(n)
            if f.id == LEGACY: legacies.append(n)
        elif isinstance(f, ast.Attribute):
            if f.attr == WRAPPER: wrappers.append(n)
            if f.attr == LEGACY: legacies.append(n)
    assert len(wrappers) == 1
    assert legacies == []

def test_candidate_boundary_fail_closed_message_remains():
    text = TARGET.read_text(encoding='utf-8-sig').lower()
    assert 'generation candidate evidence boundary' in text
    assert 'r68-by-element safe set' in text
