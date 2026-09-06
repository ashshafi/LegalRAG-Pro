from pathlib import Path
import ast


def _source() -> str:
    return Path("src/legalrag.py").read_text(encoding="utf-8-sig")


def _ask_source() -> str:
    source = _source()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "ask":
            return ast.get_source_segment(source, node) or ""
    raise AssertionError("ask not found")


def test_r40_bounded_applied_analytical_answers_use_interactive_model():
    ask = _ask_source()
    assert "new_ai_finding_mode or analytical_context is not None" in ask
    assert "model=(" in ask
    assert "INTERACTIVE_CHAT_MODEL" in ask


def test_r40_bounded_applied_analytical_answers_use_interactive_reasoning_policy():
    ask = _ask_source()
    assert "reasoning_effort=(" in ask
    assert "INTERACTIVE_REASONING_EFFORT" in ask
    assert "new_ai_finding_mode or analytical_context is not None" in ask


def test_r40_non_analytical_bounded_path_can_still_use_chat_model():
    ask = _ask_source()
    assert "else CHAT_MODEL" in ask
    assert "else None" in ask


def test_r40_non_bounded_applied_path_still_uses_interactive_model():
    ask = _ask_source()
    assert "response = legal_answer_client.responses.create(" in ask
    assert "model=INTERACTIVE_CHAT_MODEL" in ask
    assert "reasoning={\"effort\": INTERACTIVE_REASONING_EFFORT}" in ask


def test_r40_general_provider_timeout_policy_unchanged():
    source = _source()
    assert "_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0" in source
    assert "_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0" in source


def test_r40_bounded_timeout_and_r36_boundary_live_in_bounded_module():
    bounded = Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")
    assert "BOUNDED_PROVIDER_TIMEOUT_SECONDS = 90.0" in bounded
    assert "Intermediate bounded map passes perform source-bound evidence extraction." in bounded
    assert "final_prompt = _apply_constraint(" in bounded
