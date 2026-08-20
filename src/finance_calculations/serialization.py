"""Canonical serialization for Finance F3 calculation records."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from finance_domain.identity import canonical_decimal_text, canonical_json_bytes

from .models import AnalyticalStatus, CalculationClassification, CalculationResult, ValueClassification


def calculation_result_to_dict(value: CalculationResult) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "workspace_id": value.workspace_id,
        "company_id": value.company_id,
        "security_id": value.security_id,
        "metric_code": value.metric_code,
        "classification": value.classification.value,
        "calculation_classification": value.calculation_classification.value,
        "status": value.status.value,
        "value": canonical_decimal_text(value.value) if value.value is not None else None,
        "currency": value.currency,
        "unit": value.unit,
        "financial_period_id": value.financial_period_id,
        "as_of": value.as_of.isoformat().replace("+00:00", "Z"),
        "calculation_code": value.calculation_code,
        "calculation_version": value.calculation_version,
        "formula": value.formula,
        "input_fact_ids": list(value.input_fact_ids),
        "note": value.note,
        "result_id": value.result_id,
    }


def calculation_result_identity_payload_to_dict(value: CalculationResult) -> dict[str, Any]:
    data = calculation_result_to_dict(value)
    data.pop("result_id")
    return data


def dumps_calculation_result(value: CalculationResult) -> str:
    from .validation import validate_calculation_result

    validate_calculation_result(value)
    return canonical_json_bytes(calculation_result_to_dict(value)).decode("utf-8")


def loads_calculation_result(payload: str) -> CalculationResult:
    if not isinstance(payload, str):
        raise ValueError("payload must be canonical JSON text.")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("payload must contain valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("calculation result payload must be a JSON object.")

    expected_keys = {
        "schema_version", "workspace_id", "company_id", "security_id",
        "metric_code", "classification", "calculation_classification", "status", "value", "currency", "unit",
        "financial_period_id", "as_of", "calculation_code", "calculation_version",
        "formula", "input_fact_ids", "note", "result_id",
    }
    if set(data) != expected_keys:
        raise ValueError("calculation result payload fields are not exact.")

    try:
        as_of_text = data["as_of"]
        if not isinstance(as_of_text, str) or not as_of_text.endswith("Z"):
            raise ValueError("as_of must use canonical UTC Z form.")
        as_of = datetime.fromisoformat(as_of_text[:-1] + "+00:00")
        result = CalculationResult(
            schema_version=data["schema_version"],
            workspace_id=data["workspace_id"],
            company_id=data["company_id"],
            security_id=data["security_id"],
            metric_code=data["metric_code"],
            classification=ValueClassification(data["classification"]),
            calculation_classification=CalculationClassification(data["calculation_classification"]),
            status=AnalyticalStatus(data["status"]),
            value=Decimal(data["value"]) if data["value"] is not None else None,
            currency=data["currency"],
            unit=data["unit"],
            financial_period_id=data["financial_period_id"],
            as_of=as_of,
            calculation_code=data["calculation_code"],
            calculation_version=data["calculation_version"],
            formula=data["formula"],
            input_fact_ids=tuple(data["input_fact_ids"]),
            note=data["note"],
            result_id=data["result_id"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid calculation result payload.") from exc

    from .validation import validate_calculation_result

    validate_calculation_result(result)
    if dumps_calculation_result(result) != payload:
        raise ValueError("payload is not canonical calculation result JSON.")
    return result


__all__ = [
    "calculation_result_identity_payload_to_dict",
    "calculation_result_to_dict",
    "dumps_calculation_result",
    "loads_calculation_result",
]
