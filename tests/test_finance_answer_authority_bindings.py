import json

import pytest

from finance_answer_authority import (
    FinanceAnswerMode,
    FinanceContentClassification,
    FinanceUnavailableReason,
    validate_finance_answer_output,
)
from test_finance_answer_authority_models import calculation, cell, claim, context, output, position, summary


def test_source_fact_and_derived_cell_classifications_are_validator_derived():
    ctx = context()
    source = cell(ctx, "REVENUE")
    derived = cell(ctx, "EV_EBITDA")
    answer = validate_finance_answer_output(raw_output=output(ctx, [
        claim("C1", "CELL_VALUE", source.cell_id),
        claim("C2", "CELL_VALUE", derived.cell_id),
    ]), context=ctx)
    assert answer.bindings[0].classifications == (
        FinanceContentClassification.SOURCE_FACT,
        FinanceContentClassification.AI_GENERATED_COMMENTARY,
    )
    assert answer.bindings[1].classifications == (
        FinanceContentClassification.DERIVED_METRIC,
        FinanceContentClassification.MODEL_CALCULATION,
        FinanceContentClassification.AI_GENERATED_COMMENTARY,
    )
    assert all(FinanceContentClassification.ANALYST_INTERPRETATION not in item.classifications for item in answer.bindings)


def test_peer_summary_position_formula_and_provenance_are_deterministic():
    ctx = context()
    s = summary(ctx, "EV_EBITDA")
    p = position(ctx, "EV_EBITDA")
    calc = calculation(ctx, "EV_EBITDA")
    answer = validate_finance_answer_output(raw_output=output(ctx, [
        claim("C1", "PEER_SUMMARY_VALUE", s.summary_id, "MEDIAN"),
        claim("C2", "TARGET_PEER_RELATIONSHIP", p.position_id),
        claim("C3", "CALCULATION_FORMULA", calc.result_id),
    ]), context=ctx)
    assert str(s.median) in answer.bindings[0].statement_text
    assert p.relationship.value in answer.bindings[1].statement_text
    assert calc.formula in answer.bindings[2].statement_text
    assert answer.relied_observation_ids
    assert len(answer.relied_evidence_binding_ids) == len(answer.relied_observation_ids)


def test_all_non_value_claims_render_from_frozen_authority_only():
    ctx = context()
    member = ctx.members[0]
    evidence = ctx.evidence_bindings[0]
    answer = validate_finance_answer_output(raw_output=output(ctx, [
        claim("C1", "ANALYSIS_AS_OF", ctx.analysis_id),
        claim("C2", "DATASET_IDENTITY", ctx.analysis_id),
        claim("C3", "MEMBER_STATUS", member.member_id),
        claim("C4", "EVIDENCE_BINDING", evidence.evidence_binding_id),
        claim("C5", "EVIDENCE_COVERAGE", ctx.document_evidence_manifest_id),
    ]), context=ctx)
    assert ctx.provider_id in answer.answer
    assert member.company_name in answer.answer
    assert evidence.observation_id in answer.answer
    assert ctx.document_evidence_coverage.value in answer.answer


def test_unavailable_is_first_class_deterministic_success():
    ctx = context()
    raw = output(ctx, [], mode="UNAVAILABLE", reason="ANALYST_INTERPRETATION_NOT_AVAILABLE")
    answer = validate_finance_answer_output(raw_output=raw, context=ctx)
    assert answer.mode is FinanceAnswerMode.UNAVAILABLE
    assert answer.unavailable_reason is FinanceUnavailableReason.ANALYST_INTERPRETATION_NOT_AVAILABLE
    assert answer.bindings == () and answer.relied_authority_ids == ()
    assert "No governed analyst interpretation" in answer.answer


def test_exact_decimal_currency_unit_and_period_are_rendered_without_new_math():
    ctx = context(); c = cell(ctx, "REVENUE")
    answer = validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", c.cell_id)]), context=ctx)
    text = answer.answer
    assert str(c.value) in text
    if c.currency is not None:
        assert c.currency in text
    assert c.unit in text
    assert c.financial_period_label in text


def test_repeated_validation_is_deterministic():
    ctx = context(); c = cell(ctx, "EV_EBITDA")
    raw = output(ctx, [claim("C1", "CELL_VALUE", c.cell_id)])
    assert validate_finance_answer_output(raw_output=raw, context=ctx) == validate_finance_answer_output(raw_output=raw, context=ctx)
