"""Deterministic model-visible Finance F6 claim catalogue and prompt contract."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .models import FinanceClaimType, FinanceSummarySelector, RuntimeFinanceAnswerAuthorityContext
from .validation import validate_runtime_finance_answer_context


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported prompt value: {type(value)!r}")


def _catalogue(context: RuntimeFinanceAnswerAuthorityContext) -> dict:
    return {
        "analysis": {
            "analysis_id": context.analysis_id,
            "workspace_id": context.workspace_id,
            "as_of": _json_value(context.as_of),
            "provider_id": context.provider_id,
            "dataset_id": context.dataset_id,
            "dataset_version": context.dataset_version,
            "dataset_identity": context.dataset_identity,
            "document_evidence_manifest_id": context.document_evidence_manifest_id,
            "document_evidence_coverage": context.document_evidence_coverage.value,
        },
        "members": [
            {
                "member_id": item.member_id,
                "company_id": item.company_id,
                "company_name": item.company_name,
                "security_id": item.security_id,
                "role": item.role.value,
                "inclusion_state": item.inclusion_state.value,
                "current_period_id": item.current_period_id,
                "prior_period_id": item.prior_period_id,
                "exclusion_reason": item.exclusion_reason,
            }
            for item in context.members
        ],
        "cells": [
            {
                "cell_id": item.cell_id,
                "company_id": item.company_id,
                "company_name": item.company_name,
                "metric_code": item.metric_code,
                "value_classification": item.value_classification.value,
                "calculation_classification": _json_value(item.calculation_classification),
                "status": item.status.value,
                "value": _json_value(item.value),
                "currency": item.currency,
                "unit": item.unit,
                "financial_period_id": item.financial_period_id,
                "financial_period_label": item.financial_period_label,
                "observation_ids": list(item.observation_ids),
                "note": item.note,
            }
            for item in context.cells
        ],
        "summaries": [
            {
                "summary_id": item.summary_id,
                "metric_code": item.metric_code,
                "status": item.status.value,
                "selected_peer_count": item.selected_peer_count,
                "established_peer_count": item.established_peer_count,
                "currency": item.currency,
                "unit": item.unit,
                "mean": _json_value(item.mean),
                "median": _json_value(item.median),
                "minimum": _json_value(item.minimum),
                "maximum": _json_value(item.maximum),
                "input_cell_ids": list(item.input_cell_ids),
                "unavailable_cell_ids": list(item.unavailable_cell_ids),
                "note": item.note,
            }
            for item in context.summaries
        ],
        "positions": [
            {
                "position_id": item.position_id,
                "metric_code": item.metric_code,
                "status": item.status.value,
                "relationship": _json_value(item.relationship),
                "target_cell_id": item.target_cell_id,
                "peer_summary_id": item.peer_summary_id,
                "note": item.note,
            }
            for item in context.positions
        ],
        "calculations": [
            {
                "result_id": item.result_id,
                "company_id": item.company_id,
                "company_name": item.company_name,
                "metric_code": item.metric_code,
                "status": item.status.value,
                "calculation_code": item.calculation_code,
                "calculation_version": item.calculation_version,
                "formula": item.formula,
                "observation_ids": list(item.observation_ids),
                "note": item.note,
            }
            for item in context.calculations
        ],
        "evidence_bindings": [
            {
                "evidence_binding_id": item.evidence_binding_id,
                "observation_id": item.observation_id,
                "company_id": item.company_id,
                "company_name": item.company_name,
                "provider": item.provider,
                "source_id": item.source_id,
                "source_version": item.source_version,
                "publication_at": _json_value(item.publication_at),
                "source_channel": item.source_channel.value,
                "binding_class": item.binding_class.value,
                "document_snapshot_id": item.document_snapshot_id,
                "page_number": item.page_number,
                "bound_text_sha256": item.bound_text_sha256,
                "note": item.note,
            }
            for item in context.evidence_bindings
        ],
    }


def build_constrained_finance_answer_prompt(*, base_prompt: str, context: RuntimeFinanceAnswerAuthorityContext) -> str:
    validate_runtime_finance_answer_context(context)
    if not isinstance(base_prompt, str) or not base_prompt.strip():
        raise ValueError("base_prompt must be non-empty text.")

    catalogue = json.dumps(_catalogue(context), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    claim_types = ", ".join(item.value for item in FinanceClaimType)
    selectors = ", ".join(item.value for item in FinanceSummarySelector)

    return (
        base_prompt.strip()
        + "\n\nFINANCE F6 FROZEN ANSWER AUTHORITY\n"
        + "The F4 comparable-company analysis and F5 evidence manifest below are frozen read-only authorities.\n"
        + "Do not retrieve, recalculate, normalize, rank, infer, or create financial state. Do not perform arithmetic.\n"
        + "Do not infer a numeric value from source text. Do not change any frozen AnalyticalStatus.\n"
        + "Do not create missing metrics, replacement peers, replacement securities, causal explanations, valuations, target prices, or buy/sell/hold advice.\n"
        + "No governed analyst interpretation exists in F1-F5; do not create or label AI inference as analyst interpretation.\n"
        + "Return claim selections only. Never return substantive financial prose. Every claim must reference one exact visible authority ID.\n"
        + "For unsupported or ambiguous questions return mode UNAVAILABLE with one exact reason.\n"
        + f"Allowed claim_type values: {claim_types}.\n"
        + f"PEER_SUMMARY_VALUE selector values: {selectors}. All other claim types require selector null.\n"
        + "Return strict JSON with exactly these root fields: analysis_id, document_evidence_manifest_id, mode, claims, unavailable_reason.\n"
        + "Each claim object must contain exactly: claim_id, claim_type, authority_id, selector. No text/value/status/formula/provenance fields are allowed.\n"
        + "ANSWER requires at least one claim and unavailable_reason null. UNAVAILABLE requires claims [] and an exact unavailable reason.\n"
        + "AUTHORITY_CATALOGUE="
        + catalogue
    )
