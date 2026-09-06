from pathlib import Path
import ast


def _source() -> str:
    return Path("src/legalrag.py").read_text(encoding="utf-8-sig")


def _tree():
    return ast.parse(_source())


def _fn(name: str):
    source = _source()
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    )
    return node, ast.get_source_segment(source, node) or ""


def test_r54_helper_exists_and_is_timing_gated():
    _node, segment = _fn("_log_analytical_binding_failure_diagnostics")
    assert "LEGALRAG_ASSISTANT_TIMING" in segment
    assert "ANALYTICAL_BINDING_DIAGNOSTIC" in segment
    assert "ANALYTICAL_BINDING_OFFENDER" in segment


def test_r54_helper_does_not_log_statement_text():
    _node, segment = _fn("_log_analytical_binding_failure_diagnostics")
    assert 'row.get("text"' not in segment
    assert "statement_text" not in segment


def test_r54_helper_reports_only_structural_binding_fields():
    _node, segment = _fn("_log_analytical_binding_failure_diagnostics")
    assert "REF_COUNT=" in segment
    assert "RESOLVED_STATUSES=" in segment
    assert "UNKNOWN_REFS=" in segment
    assert "DECLARED_SOURCE_STATUS=" in segment


def test_r54_call_is_in_actual_governed_answer_authority_error_handler():
    source = _source()
    tree = ast.parse(source)
    ask = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "ask"
    )

    validator_tries = []
    for node in ast.walk(ask):
        if not isinstance(node, ast.Try):
            continue
        has_validator = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "validate_answer_statement_bindings"
            for stmt in node.body
            for child in ast.walk(stmt)
        )
        if has_validator:
            validator_tries.append(node)

    assert len(validator_tries) == 1
    owner = validator_tries[0]
    assert len(owner.handlers) == 1
    handler = owner.handlers[0]
    assert isinstance(handler.type, ast.Name)
    assert handler.type.id == "GovernedAnswerAuthorityError"

    calls = [
        child for child in ast.walk(handler)
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_log_analytical_binding_failure_diagnostics"
        )
    ]
    assert len(calls) == 1


def test_r54_existing_binding_error_specialisation_retained():
    source = _source()
    assert "if isinstance(exc, GovernedAnswerBindingError):" in source
    assert 'mode="invalid_analytical_output"' in source


def test_r54_validator_and_fail_closed_paths_retained():
    source = _source()
    assert "validate_answer_statement_bindings(" in source
    assert "_analytical_failure_payload(" in source
    assert "canonicalize_exact_duplicate_source_proposition_refs" in source


def test_r54_provider_timeout_policy_retained():
    source = _source()
    assert "_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0" in source
    assert "_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0" in source
