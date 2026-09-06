from pathlib import Path
import ast


def _source() -> str:
    return Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")


def _function_ast():
    source = _source()
    tree = ast.parse(source)
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "create_bounded_governed_response":
            return source, node, parents
    raise AssertionError("create_bounded_governed_response not found")


def _constraint_assignments():
    source, fn, parents = _function_ast()
    found = []
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
        found.append((node.targets[0].id, inside_for))
    return found


def test_r36_map_pass_has_no_full_analytical_constraint():
    assert ("prompt", True) not in _constraint_assignments()


def test_r36_reduce_pass_retains_full_analytical_constraint():
    assert _constraint_assignments().count(("final_prompt", False)) == 1


def test_r36_map_rules_remain_source_bound():
    source = _source()
    assert "Analyse every supplied evidence row in this batch." in source
    assert "Do not make any negative finding about evidence being absent" in source
    assert "Preserve the exact evidence_key, file and page" in source
    assert "Do not invent evidence or source coordinates." in source


def test_r36_map_and_reduce_provider_calls_remain():
    source, fn, _parents = _function_ast()
    segment = ast.get_source_segment(source, fn) or ""
    assert segment.count("_provider_call(") == 2


def test_r36_bounded_constants_unchanged():
    source = _source()
    tree = ast.parse(source)
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        values[target.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            try:
                values[node.target.id] = ast.literal_eval(node.value)
            except Exception:
                pass
    assert values["BOUNDED_ANSWER_TRIGGER_CHARS"] == 500_000
    assert values["BOUNDED_BATCH_TARGET_CHARS"] == 240_000
    assert values["MAP_MAX_OUTPUT_TOKENS"] == 5_000
    assert values["REDUCE_MAX_OUTPUT_TOKENS"] == 8_000
