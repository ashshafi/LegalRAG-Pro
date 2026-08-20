from datetime import datetime, timezone

import pytest

from finance_answer_authority import validate_finance_answer_output
from test_finance_answer_authority_models import analysis, cell, claim, context, manifest_for, output, position, summary
from finance_answer_authority import build_runtime_finance_answer_context


def test_strict_json_duplicate_and_unexpected_fields_fail_closed():
    ctx = context()
    c = cell(ctx, "REVENUE")
    duplicate = '{"analysis_id":"%s","analysis_id":"%s","document_evidence_manifest_id":"%s","mode":"ANSWER","claims":[],"unavailable_reason":null}' % (ctx.analysis_id, ctx.analysis_id, ctx.document_evidence_manifest_id)
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        validate_finance_answer_output(raw_output=duplicate, context=ctx)
    with pytest.raises(ValueError, match="root JSON fields"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", c.cell_id)])[:-1] + ',"extra":1}', context=ctx)
    bad_claim = claim("C1", "CELL_VALUE", c.cell_id); bad_claim["text"] = "invented"
    with pytest.raises(ValueError, match="claim JSON fields"):
        validate_finance_answer_output(raw_output=output(ctx, [bad_claim]), context=ctx)


def test_authority_echo_unknown_claim_selector_and_duplicate_semantic_claim_fail():
    ctx = context(); c = cell(ctx, "REVENUE")
    raw = output(ctx, [claim("C1", "CELL_VALUE", c.cell_id)]).replace(ctx.analysis_id, "sha256:" + "1" * 64, 1)
    with pytest.raises(ValueError, match="analysis_id"):
        validate_finance_answer_output(raw_output=raw, context=ctx)
    with pytest.raises(ValueError, match="Unknown claim_type"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "MAGIC", c.cell_id)]), context=ctx)
    with pytest.raises(ValueError, match="CELL claim"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", "sha256:" + "1" * 64)]), context=ctx)
    with pytest.raises(ValueError, match="selector null"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", c.cell_id, "MEDIAN")]), context=ctx)
    with pytest.raises(ValueError, match="Duplicate semantic"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", c.cell_id), claim("C2", "CELL_VALUE", c.cell_id)]), context=ctx)


def test_answer_and_unavailable_mode_shape_rules_fail_closed():
    ctx = context()
    with pytest.raises(ValueError, match="at least one claim"):
        validate_finance_answer_output(raw_output=output(ctx, []), context=ctx)
    with pytest.raises(ValueError, match="unavailable_reason null"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "ANALYSIS_AS_OF", ctx.analysis_id)], reason="QUESTION_AMBIGUOUS"), context=ctx)
    with pytest.raises(ValueError, match="no claims"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "ANALYSIS_AS_OF", ctx.analysis_id)], mode="UNAVAILABLE", reason="QUESTION_AMBIGUOUS"), context=ctx)
    with pytest.raises(ValueError, match="exact unavailable reason"):
        validate_finance_answer_output(raw_output=output(ctx, [], mode="UNAVAILABLE", reason="MADE_UP"), context=ctx)


def test_non_established_cell_summary_and_position_cannot_be_upgraded_to_value_claims():
    early = datetime(2026, 3, 2, 16, 29, 59, tzinfo=timezone.utc)
    a = analysis(as_of=early); ctx = build_runtime_finance_answer_context(analysis=a, evidence_manifest=manifest_for(a))
    c = cell(ctx, "EV_EBITDA")
    s = summary(ctx, "EV_EBITDA")
    p = position(ctx, "EV_EBITDA")
    assert c.status.value != "ESTABLISHED" and s.status.value != "ESTABLISHED" and p.status.value != "ESTABLISHED"
    with pytest.raises(ValueError, match="CELL_VALUE requires"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_VALUE", c.cell_id)]), context=ctx)
    status_answer = validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "CELL_STATUS", c.cell_id)]), context=ctx)
    assert c.status.value in status_answer.answer and c.note in status_answer.answer
    with pytest.raises(ValueError, match="ESTABLISHED summary"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "PEER_SUMMARY_VALUE", s.summary_id, "MEDIAN")]), context=ctx)
    with pytest.raises(ValueError, match="established relationship"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "TARGET_PEER_RELATIONSHIP", p.position_id)]), context=ctx)


def test_peer_summary_value_requires_exact_selector_and_status_claim_forbids_one():
    ctx = context(); s = summary(ctx, "EV_EBITDA")
    with pytest.raises(ValueError, match="requires one exact statistic selector"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "PEER_SUMMARY_VALUE", s.summary_id)]), context=ctx)
    with pytest.raises(ValueError, match="Invalid selector"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "PEER_SUMMARY_VALUE", s.summary_id, "P95")]), context=ctx)
    with pytest.raises(ValueError, match="selector null"):
        validate_finance_answer_output(raw_output=output(ctx, [claim("C1", "PEER_SUMMARY_STATUS", s.summary_id, "MEDIAN")]), context=ctx)
