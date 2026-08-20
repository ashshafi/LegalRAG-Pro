from finance_answer_authority import build_constrained_finance_answer_prompt
from test_finance_answer_authority_models import context


def test_prompt_binds_exact_f4_f5_authorities_and_all_claim_types():
    ctx = context()
    prompt = build_constrained_finance_answer_prompt(base_prompt="What is the target EV/EBITDA?", context=ctx)
    assert ctx.analysis_id in prompt
    assert ctx.document_evidence_manifest_id in prompt
    assert ctx.as_of.isoformat().replace("+00:00", "Z") in prompt
    for claim_type in (
        "ANALYSIS_AS_OF", "DATASET_IDENTITY", "MEMBER_STATUS", "CELL_VALUE", "CELL_STATUS",
        "PEER_SUMMARY_VALUE", "PEER_SUMMARY_STATUS", "TARGET_PEER_RELATIONSHIP",
        "CALCULATION_FORMULA", "EVIDENCE_BINDING", "EVIDENCE_COVERAGE",
    ):
        assert claim_type in prompt


def test_prompt_explicitly_forbids_reanalysis_arithmetic_recommendations_and_analyst_invention():
    prompt = build_constrained_finance_answer_prompt(base_prompt="Explain", context=context())
    assert "Do not perform arithmetic" in prompt
    assert "Do not retrieve, recalculate, normalize, rank, infer" in prompt
    assert "target prices" in prompt and "buy/sell/hold advice" in prompt
    assert "No governed analyst interpretation exists" in prompt
    assert "Never return substantive financial prose" in prompt


def test_prompt_schema_has_no_generated_substantive_text_field_and_no_source_payloads():
    prompt = build_constrained_finance_answer_prompt(base_prompt="Explain", context=context())
    assert "claim_id, claim_type, authority_id, selector" in prompt
    assert "exact_bound_text" not in prompt
    assert "exact_page_text" not in prompt
    assert "original_pdf_bytes" not in prompt
    assert "Revenue was $1.234 billion" not in prompt


def test_prompt_is_deterministic():
    ctx = context()
    assert build_constrained_finance_answer_prompt(base_prompt="Question", context=ctx) == build_constrained_finance_answer_prompt(base_prompt="Question", context=ctx)
