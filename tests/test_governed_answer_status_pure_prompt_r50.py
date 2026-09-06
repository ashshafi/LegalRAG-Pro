from pathlib import Path
import ast


def _context_source() -> str:
    return Path("src/governed_answer_authority/context.py").read_text(encoding="utf-8-sig")


def _prompt_segment() -> str:
    source = _context_source()
    tree = ast.parse(source)
    fn = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "build_constrained_governed_answer_prompt"
    )
    lines = source.splitlines(keepends=True)
    return "".join(lines[fn.lineno - 1:fn.end_lineno])


def test_r50_status_purity_hard_rule_present():
    segment = _prompt_segment()
    assert "STATUS-PURITY IS A HARD BINDING RULE" in segment
    assert "Choose exactly one frozen proposition status" in segment


def test_r50_mixed_status_refs_are_forbidden():
    segment = _prompt_segment()
    assert "Never combine proposition references with different frozen statuses" in segment


def test_r50_cross_status_material_requires_separate_statements():
    segment = _prompt_segment()
    assert "emit separate statement items" in segment


def test_r50_status_self_check_present():
    segment = _prompt_segment()
    assert "The resolved status set MUST contain exactly one value." in segment
    assert "split or rewrite the statement before returning it" in segment


def test_r50_existing_return_status_contract_retained():
    segment = _prompt_segment()
    assert '"source_status": must exactly equal the "status" value of every referenced' in segment
    assert "a statement may combine proposition references only" in segment
    assert 'when all referenced rows have the same "status" value' in segment


def test_r50_validator_remains_fail_closed():
    bindings = Path("src/governed_answer_authority/bindings.py").read_text(encoding="utf-8-sig")
    assert "Referenced propositions must share one frozen proposition status." in bindings
