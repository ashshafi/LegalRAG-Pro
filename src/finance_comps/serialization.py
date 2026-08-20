"""Canonical serialization and identity payloads for Finance F4."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from finance_calculations import (
    AnalyticalStatus,
    CalculationClassification,
    calculation_result_to_dict,
    loads_calculation_result,
)
from finance_domain import (
    canonical_decimal_text,
    dumps_company,
    dumps_financial_fact,
    dumps_financial_observation,
    dumps_financial_period,
    dumps_security,
    loads_company,
    loads_financial_fact,
    loads_financial_observation,
    loads_financial_period,
    loads_security,
)
from finance_domain.identity import canonical_json_bytes

from .models import (
    CellValueClassification,
    ComparableCompanyAnalysis,
    ComparableMemberSelection,
    ComparableMetricCell,
    ComparableRole,
    ComparableSetDefinition,
    PeerInclusionState,
    PeerMetricSummary,
    TargetPeerPosition,
    TargetPeerRelationship,
)


def _dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("F4 datetimes must be UTC-aware.")
    text = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return text[:-6] + "Z"


def _decimal(value: Decimal | None) -> str | None:
    return canonical_decimal_text(value) if value is not None else None


def comparable_member_to_dict(value: ComparableMemberSelection) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "company_id": value.company_id,
        "security_id": value.security_id,
        "role": value.role.value,
        "inclusion_state": value.inclusion_state.value,
        "current_period_id": value.current_period_id,
        "prior_period_id": value.prior_period_id,
        "exclusion_reason": value.exclusion_reason,
        "member_id": value.member_id,
    }


def comparable_member_identity_payload_to_dict(value: ComparableMemberSelection) -> dict[str, Any]:
    data = comparable_member_to_dict(value)
    data.pop("member_id")
    return data


def comparable_set_to_dict(value: ComparableSetDefinition) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "workspace_id": value.workspace_id,
        "as_of": _dt(value.as_of),
        "members": [comparable_member_to_dict(item) for item in value.members],
        "definition_id": value.definition_id,
    }


def comparable_set_identity_payload_to_dict(value: ComparableSetDefinition) -> dict[str, Any]:
    data = comparable_set_to_dict(value)
    data.pop("definition_id")
    return data


def comparable_metric_cell_to_dict(value: ComparableMetricCell) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "workspace_id": value.workspace_id,
        "company_id": value.company_id,
        "security_id": value.security_id,
        "metric_code": value.metric_code,
        "value_classification": value.value_classification.value,
        "calculation_classification": value.calculation_classification.value if value.calculation_classification else None,
        "status": value.status.value,
        "value": _decimal(value.value),
        "currency": value.currency,
        "unit": value.unit,
        "financial_period_id": value.financial_period_id,
        "as_of": _dt(value.as_of),
        "source_fact_id": value.source_fact_id,
        "source_result_id": value.source_result_id,
        "input_fact_ids": list(value.input_fact_ids),
        "observation_ids": list(value.observation_ids),
        "note": value.note,
        "cell_id": value.cell_id,
    }


def comparable_metric_cell_identity_payload_to_dict(value: ComparableMetricCell) -> dict[str, Any]:
    data = comparable_metric_cell_to_dict(value)
    data.pop("cell_id")
    return data


def peer_metric_summary_to_dict(value: PeerMetricSummary) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "workspace_id": value.workspace_id,
        "metric_code": value.metric_code,
        "status": value.status.value,
        "value_classification": value.value_classification.value,
        "calculation_classification": value.calculation_classification.value,
        "selected_peer_count": value.selected_peer_count,
        "established_peer_count": value.established_peer_count,
        "currency": value.currency,
        "unit": value.unit,
        "mean": _decimal(value.mean),
        "median": _decimal(value.median),
        "minimum": _decimal(value.minimum),
        "maximum": _decimal(value.maximum),
        "input_cell_ids": list(value.input_cell_ids),
        "unavailable_cell_ids": list(value.unavailable_cell_ids),
        "as_of": _dt(value.as_of),
        "note": value.note,
        "summary_id": value.summary_id,
    }


def peer_metric_summary_identity_payload_to_dict(value: PeerMetricSummary) -> dict[str, Any]:
    data = peer_metric_summary_to_dict(value)
    data.pop("summary_id")
    return data


def target_peer_position_to_dict(value: TargetPeerPosition) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "workspace_id": value.workspace_id,
        "metric_code": value.metric_code,
        "status": value.status.value,
        "relationship": value.relationship.value if value.relationship else None,
        "target_cell_id": value.target_cell_id,
        "peer_summary_id": value.peer_summary_id,
        "as_of": _dt(value.as_of),
        "note": value.note,
        "position_id": value.position_id,
    }


def target_peer_position_identity_payload_to_dict(value: TargetPeerPosition) -> dict[str, Any]:
    data = target_peer_position_to_dict(value)
    data.pop("position_id")
    return data


def _existing_to_dict(dumper, value) -> dict[str, Any]:
    return json.loads(dumper(value))


def comparable_analysis_to_dict(value: ComparableCompanyAnalysis) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "identity_version": value.identity_version,
        "workspace_id": value.workspace_id,
        "provider_id": value.provider_id,
        "dataset_id": value.dataset_id,
        "dataset_version": value.dataset_version,
        "dataset_identity": value.dataset_identity,
        "as_of": _dt(value.as_of),
        "definition": comparable_set_to_dict(value.definition),
        "companies": [_existing_to_dict(dumps_company, item) for item in value.companies],
        "securities": [_existing_to_dict(dumps_security, item) for item in value.securities],
        "periods": [_existing_to_dict(dumps_financial_period, item) for item in value.periods],
        "source_observations": [_existing_to_dict(dumps_financial_observation, item) for item in value.source_observations],
        "source_facts": [_existing_to_dict(dumps_financial_fact, item) for item in value.source_facts],
        "calculation_results": [calculation_result_to_dict(item) for item in value.calculation_results],
        "cells": [comparable_metric_cell_to_dict(item) for item in value.cells],
        "summaries": [peer_metric_summary_to_dict(item) for item in value.summaries],
        "positions": [target_peer_position_to_dict(item) for item in value.positions],
        "analysis_id": value.analysis_id,
    }


def comparable_analysis_identity_payload_to_dict(value: ComparableCompanyAnalysis) -> dict[str, Any]:
    data = comparable_analysis_to_dict(value)
    data.pop("analysis_id")
    return data


def dumps_comparable_company_analysis(value: ComparableCompanyAnalysis) -> str:
    from .validation import validate_comparable_company_analysis
    validate_comparable_company_analysis(value)
    return canonical_json_bytes(comparable_analysis_to_dict(value)).decode("utf-8")


def _loads_obj(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ValueError("F4 payload must be text.")
    def reject_duplicates(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"Duplicate JSON object key {k!r} is not allowed.")
            out[k] = v
        return out
    try:
        value = json.loads(payload, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid F4 JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("F4 JSON root must be an object.")
    return value


def _utc(text: Any) -> datetime:
    if not isinstance(text, str) or not text.endswith("Z"):
        raise ValueError("F4 datetime must use canonical UTC Z form.")
    try:
        value = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Invalid F4 datetime.") from exc
    if _dt(value) != text:
        raise ValueError("F4 datetime is not canonical.")
    return value


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("F4 Decimal values must be strings.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid F4 Decimal.") from exc
    if canonical_decimal_text(parsed) != value:
        raise ValueError("F4 Decimal is not canonical.")
    return parsed


def _canonical_subpayload(data: dict[str, Any]) -> str:
    return canonical_json_bytes(data).decode("utf-8")


def _member(data: Any) -> ComparableMemberSelection:
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "company_id", "security_id", "role", "inclusion_state",
        "current_period_id", "prior_period_id", "exclusion_reason", "member_id",
    }:
        raise ValueError("Comparable member fields are not exact.")
    return ComparableMemberSelection(
        schema_version=data["schema_version"], company_id=data["company_id"], security_id=data["security_id"],
        role=ComparableRole(data["role"]), inclusion_state=PeerInclusionState(data["inclusion_state"]),
        current_period_id=data["current_period_id"], prior_period_id=data["prior_period_id"],
        exclusion_reason=data["exclusion_reason"], member_id=data["member_id"],
    )


def _definition(data: Any) -> ComparableSetDefinition:
    if not isinstance(data, dict) or set(data) != {"schema_version", "workspace_id", "as_of", "members", "definition_id"}:
        raise ValueError("Comparable definition fields are not exact.")
    if not isinstance(data["members"], list):
        raise ValueError("Comparable definition members must be an array.")
    return ComparableSetDefinition(
        schema_version=data["schema_version"], workspace_id=data["workspace_id"], as_of=_utc(data["as_of"]),
        members=tuple(_member(item) for item in data["members"]), definition_id=data["definition_id"],
    )


def _cell(data: Any) -> ComparableMetricCell:
    keys = {"schema_version","workspace_id","company_id","security_id","metric_code","value_classification","calculation_classification","status","value","currency","unit","financial_period_id","as_of","source_fact_id","source_result_id","input_fact_ids","observation_ids","note","cell_id"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("Comparable cell fields are not exact.")
    return ComparableMetricCell(
        schema_version=data["schema_version"], workspace_id=data["workspace_id"], company_id=data["company_id"],
        security_id=data["security_id"], metric_code=data["metric_code"], value_classification=CellValueClassification(data["value_classification"]),
        calculation_classification=CalculationClassification(data["calculation_classification"]) if data["calculation_classification"] is not None else None,
        status=AnalyticalStatus(data["status"]), value=_dec(data["value"]), currency=data["currency"], unit=data["unit"],
        financial_period_id=data["financial_period_id"], as_of=_utc(data["as_of"]), source_fact_id=data["source_fact_id"],
        source_result_id=data["source_result_id"], input_fact_ids=tuple(data["input_fact_ids"]), observation_ids=tuple(data["observation_ids"]),
        note=data["note"], cell_id=data["cell_id"],
    )


def _summary(data: Any) -> PeerMetricSummary:
    keys = {"schema_version","workspace_id","metric_code","status","value_classification","calculation_classification","selected_peer_count","established_peer_count","currency","unit","mean","median","minimum","maximum","input_cell_ids","unavailable_cell_ids","as_of","note","summary_id"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("Peer summary fields are not exact.")
    return PeerMetricSummary(
        schema_version=data["schema_version"], workspace_id=data["workspace_id"], metric_code=data["metric_code"],
        status=AnalyticalStatus(data["status"]), value_classification=CellValueClassification(data["value_classification"]),
        calculation_classification=CalculationClassification(data["calculation_classification"]), selected_peer_count=data["selected_peer_count"],
        established_peer_count=data["established_peer_count"], currency=data["currency"], unit=data["unit"],
        mean=_dec(data["mean"]), median=_dec(data["median"]), minimum=_dec(data["minimum"]), maximum=_dec(data["maximum"]),
        input_cell_ids=tuple(data["input_cell_ids"]), unavailable_cell_ids=tuple(data["unavailable_cell_ids"]),
        as_of=_utc(data["as_of"]), note=data["note"], summary_id=data["summary_id"],
    )


def _position(data: Any) -> TargetPeerPosition:
    keys = {"schema_version","workspace_id","metric_code","status","relationship","target_cell_id","peer_summary_id","as_of","note","position_id"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("Target position fields are not exact.")
    return TargetPeerPosition(
        schema_version=data["schema_version"], workspace_id=data["workspace_id"], metric_code=data["metric_code"],
        status=AnalyticalStatus(data["status"]), relationship=TargetPeerRelationship(data["relationship"]) if data["relationship"] is not None else None,
        target_cell_id=data["target_cell_id"], peer_summary_id=data["peer_summary_id"], as_of=_utc(data["as_of"]),
        note=data["note"], position_id=data["position_id"],
    )


def loads_comparable_company_analysis(payload: str) -> ComparableCompanyAnalysis:
    data = _loads_obj(payload)
    expected = {"schema_version","identity_version","workspace_id","provider_id","dataset_id","dataset_version","dataset_identity","as_of","definition","companies","securities","periods","source_observations","source_facts","calculation_results","cells","summaries","positions","analysis_id"}
    if set(data) != expected:
        raise ValueError("Comparable analysis fields are not exact.")
    try:
        result = ComparableCompanyAnalysis(
            schema_version=data["schema_version"], identity_version=data["identity_version"], workspace_id=data["workspace_id"],
            provider_id=data["provider_id"], dataset_id=data["dataset_id"], dataset_version=data["dataset_version"],
            dataset_identity=data["dataset_identity"], as_of=_utc(data["as_of"]), definition=_definition(data["definition"]),
            companies=tuple(loads_company(_canonical_subpayload(item)) for item in data["companies"]),
            securities=tuple(loads_security(_canonical_subpayload(item)) for item in data["securities"]),
            periods=tuple(loads_financial_period(_canonical_subpayload(item)) for item in data["periods"]),
            source_observations=tuple(loads_financial_observation(_canonical_subpayload(item)) for item in data["source_observations"]),
            source_facts=tuple(loads_financial_fact(_canonical_subpayload(item)) for item in data["source_facts"]),
            calculation_results=tuple(loads_calculation_result(_canonical_subpayload(item)) for item in data["calculation_results"]),
            cells=tuple(_cell(item) for item in data["cells"]), summaries=tuple(_summary(item) for item in data["summaries"]),
            positions=tuple(_position(item) for item in data["positions"]), analysis_id=data["analysis_id"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid comparable analysis payload.") from exc
    from .validation import validate_comparable_company_analysis
    validate_comparable_company_analysis(result)
    if dumps_comparable_company_analysis(result) != payload:
        raise ValueError("F4 payload is not canonical JSON.")
    return result


__all__ = [
    "comparable_analysis_identity_payload_to_dict",
    "comparable_analysis_to_dict",
    "comparable_member_identity_payload_to_dict",
    "comparable_member_to_dict",
    "comparable_metric_cell_identity_payload_to_dict",
    "comparable_metric_cell_to_dict",
    "comparable_set_identity_payload_to_dict",
    "comparable_set_to_dict",
    "dumps_comparable_company_analysis",
    "loads_comparable_company_analysis",
    "peer_metric_summary_identity_payload_to_dict",
    "peer_metric_summary_to_dict",
    "target_peer_position_identity_payload_to_dict",
    "target_peer_position_to_dict",
]
