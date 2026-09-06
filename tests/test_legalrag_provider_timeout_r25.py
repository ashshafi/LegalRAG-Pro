from pathlib import Path


def _source() -> str:
    return Path("src/legalrag.py").read_text(encoding="utf-8-sig")


def test_r25_declares_finite_interactive_provider_policy():
    source = _source()
    assert "_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0" in source
    assert "_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0" in source
    assert "return openai_client.with_options(" in source
    assert "timeout=_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS" in source
    assert "max_retries=_LEGAL_ANSWER_PROVIDER_MAX_RETRIES" in source


def test_r25_bounded_governed_path_uses_bounded_client():
    source = _source()
    assert "legal_answer_client = _legal_answer_provider_client()" in source
    assert "client=legal_answer_client," in source
    assert "client=openai_client," not in source


def test_r25_direct_legal_answer_calls_use_bounded_client():
    source = _source()
    assert source.count("response = legal_answer_client.responses.create(") == 2
    ask_start = source.index("def ask(")
    ask_source = source[ask_start:]
    assert "response = openai_client.responses.create(" not in ask_source


def test_r25_timing_exposes_timeout_and_retry_policy():
    source = _source()
    assert '"LEGALRAG_TIMING PROVIDER_TIMEOUT_SECONDS="' in source
    assert '"LEGALRAG_TIMING PROVIDER_MAX_RETRIES="' in source


def test_r25_does_not_change_authority_or_task_state():
    source = _source()
    assert "activate_authority" not in source
    assert "publish_authority" not in source
    assert "update_task(" not in source
    assert "append_task_work_progress(" not in source


def test_r25_does_not_change_retrieval_or_governed_validation_contract():
    source = _source()
    assert "prepare_governed_answer_evidence(" in source
    assert "build_constrained_governed_answer_prompt(" in source
    assert "validate_answer_statement_bindings(" in source
    assert "canonicalize_exact_duplicate_source_proposition_refs(" in source
