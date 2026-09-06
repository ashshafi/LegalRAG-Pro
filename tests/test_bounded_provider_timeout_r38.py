from pathlib import Path
import ast

def _source():
    return Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")

def _values():
    source = _source()
    tree = ast.parse(source)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        out[target.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            try:
                out[node.target.id] = ast.literal_eval(node.value)
            except Exception:
                pass
    return out

def test_r38_bounded_timeout_is_90():
    assert _values()["BOUNDED_PROVIDER_TIMEOUT_SECONDS"] == 90.0

def test_r38_provider_uses_with_options_timeout():
    source = _source()
    assert "client.with_options(timeout=timeout_seconds)" in source
    assert "provider_client.responses.create(**kwargs)" in source

def test_r38_general_timeout_unchanged():
    legalrag = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0" in legalrag
    assert "_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0" in legalrag

def test_r38_r36_boundary_retained():
    source = _source()
    tree = ast.parse(source)
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "create_bounded_governed_response")
    map_constraints = 0
    reduce_constraints = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not (isinstance(func, ast.Name) and func.id == "_apply_constraint"):
            continue
        cur = parents.get(node)
        inside_for = False
        while cur is not None and cur is not fn:
            if isinstance(cur, ast.For):
                inside_for = True
                break
            cur = parents.get(cur)
        if node.targets[0].id == "prompt" and inside_for:
            map_constraints += 1
        if node.targets[0].id == "final_prompt" and not inside_for:
            reduce_constraints += 1
    assert map_constraints == 0
    assert reduce_constraints == 1

def test_r38_existing_bounded_limits_unchanged():
    values = _values()
    assert values["BOUNDED_ANSWER_TRIGGER_CHARS"] == 500_000
    assert values["BOUNDED_BATCH_TARGET_CHARS"] == 240_000
    assert values["MAP_MAX_OUTPUT_TOKENS"] == 5_000
    assert values["REDUCE_MAX_OUTPUT_TOKENS"] == 8_000
