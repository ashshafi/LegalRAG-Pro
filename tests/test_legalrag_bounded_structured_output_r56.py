from pathlib import Path
import ast


def _source() -> str:
    return Path("src/legalrag.py").read_text(encoding="utf-8-sig")


def test_r56_bounded_call_receives_existing_governed_output_schema():
    source = _source()
    tree = ast.parse(source)
    ask = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "ask"
    )

    calls = [
        node for node in ast.walk(ask)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_bounded_governed_response"
        )
    ]
    assert len(calls) == 1

    call = calls[0]
    output_schema_keywords = [kw for kw in call.keywords if kw.arg == "output_schema"]
    assert len(output_schema_keywords) == 1

    segment = ast.get_source_segment(source, output_schema_keywords[0].value) or ""
    assert "build_governed_answer_output_schema(analytical_context)" in segment
    assert "analytical_context is not None" in segment


def test_r56_non_bounded_applied_path_still_uses_same_schema_builder():
    source = _source()
    assert '"name": "governed_analytical_answer"' in source
    assert '"strict": True' in source
    assert "build_governed_answer_output_schema(analytical_context)" in source


def test_r56_r54_diagnostics_and_fail_closed_path_retained():
    source = _source()
    assert "_log_analytical_binding_failure_diagnostics(" in source
    assert 'mode="invalid_analytical_output"' in source
    assert "validate_answer_statement_bindings(" in source


def test_r56_r40_model_alignment_retained():
    source = _source()
    assert "if (new_ai_finding_mode or analytical_context is not None)" in source
    assert "INTERACTIVE_CHAT_MODEL" in source


def test_r56_general_timeout_policy_retained():
    source = _source()
    assert "_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0" in source
    assert "_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0" in source
