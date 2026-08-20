"""Fail-closed validation for Finance F3 calculation records."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from finance_domain.identity import canonical_decimal_text, canonical_uuid, derive_finance_id, validate_sha256_id

from .models import (
    AnalyticalStatus,
    CALCULATION_RESULT_SCHEMA_VERSION,
    CALCULATION_VERSION,
    CalculationClassification,
    CalculationResult,
    ValueClassification,
)
from .serialization import calculation_result_identity_payload_to_dict

_METRIC_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_UNIT = re.compile(r"^[a-z][a-z0-9_./-]{0,63}$")
_CALC_CODE = re.compile(r"^[A-Z][A-Z0-9_.]{2,95}$")


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")
    return value


def validate_calculation_result(value: CalculationResult) -> None:
    if not isinstance(value, CalculationResult):
        raise ValueError("value must be a CalculationResult instance.")
    if value.schema_version != CALCULATION_RESULT_SCHEMA_VERSION:
        raise ValueError("Unsupported CalculationResult schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    if value.security_id is not None:
        canonical_uuid(value.security_id, field_name="security_id")
    if not isinstance(value.metric_code, str) or not _METRIC_CODE.fullmatch(value.metric_code):
        raise ValueError("metric_code must use canonical uppercase identifier syntax.")
    if value.classification is not ValueClassification.DERIVED_METRIC:
        raise ValueError("CalculationResult classification must be DERIVED_METRIC.")
    if value.calculation_classification is not CalculationClassification.MODEL_CALCULATION:
        raise ValueError("CalculationResult calculation_classification must be MODEL_CALCULATION.")
    if not isinstance(value.status, AnalyticalStatus):
        raise ValueError("CalculationResult.status must be AnalyticalStatus.")
    if value.value is not None:
        if not isinstance(value.value, Decimal) or not value.value.is_finite():
            raise ValueError("value must be a finite Decimal when present.")
        canonical_decimal_text(value.value)
    if value.currency is not None and (
        not isinstance(value.currency, str) or not _CURRENCY.fullmatch(value.currency)
    ):
        raise ValueError("currency must be an uppercase three-letter code when present.")
    if value.unit is not None and (
        not isinstance(value.unit, str) or not _UNIT.fullmatch(value.unit)
    ):
        raise ValueError("unit must use canonical lowercase unit syntax when present.")
    if value.financial_period_id is not None:
        validate_sha256_id(value.financial_period_id, field_name="financial_period_id")
    if not isinstance(value.as_of, datetime) or value.as_of.tzinfo is None or value.as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware.")
    if value.as_of.utcoffset().total_seconds() != 0:
        raise ValueError("as_of must be expressed in UTC.")
    if not isinstance(value.calculation_code, str) or not _CALC_CODE.fullmatch(value.calculation_code):
        raise ValueError("calculation_code must use canonical uppercase calculation syntax.")
    if value.calculation_version != CALCULATION_VERSION:
        raise ValueError("Unsupported calculation_version.")
    _required_text(value.formula, field_name="formula")
    if value.input_fact_ids != tuple(sorted(value.input_fact_ids)):
        raise ValueError("input_fact_ids must use canonical sorted order.")
    if len(set(value.input_fact_ids)) != len(value.input_fact_ids):
        raise ValueError("input_fact_ids must be unique.")
    for fact_id in value.input_fact_ids:
        validate_sha256_id(fact_id, field_name="input_fact_id")
    if value.note is not None:
        _required_text(value.note, field_name="note")

    if value.status is AnalyticalStatus.ESTABLISHED:
        if value.value is None or value.unit is None:
            raise ValueError("ESTABLISHED calculation must contain value and unit.")
        if not value.input_fact_ids:
            raise ValueError("ESTABLISHED calculation must retain input_fact_ids.")
        if value.note is not None:
            raise ValueError("ESTABLISHED calculation must not carry a failure note.")
    else:
        if value.value is not None or value.currency is not None or value.unit is not None:
            raise ValueError("Non-established calculation must not expose an analytical value.")
        if value.note is None:
            raise ValueError("Non-established calculation must explain its failure status.")

    validate_sha256_id(value.result_id, field_name="result_id")
    expected = derive_finance_id(calculation_result_identity_payload_to_dict(value))
    if value.result_id != expected:
        raise ValueError("result_id does not match canonical calculation identity payload.")


__all__ = ["validate_calculation_result"]
