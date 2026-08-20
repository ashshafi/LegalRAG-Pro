"""Canonical fail-closed JSON serialization for Finance MVP records."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints

from .identity import canonical_decimal_text, canonical_json_bytes
from .models import (
    Company,
    FinanceWorkspace,
    FinancialFact,
    FinancialObservation,
    FinancialPeriod,
    FinancialPeriodType,
    Security,
    SecurityType,
    WorkspaceStatus,
)

_ALLOWED_DATACLASSES = frozenset(
    {FinanceWorkspace, Company, Security, FinancialPeriod, FinancialObservation, FinancialFact}
)
_ALLOWED_ENUMS = frozenset({WorkspaceStatus, SecurityType, FinancialPeriodType})


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Finance datetimes must be timezone-aware.")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("Finance datetimes must be expressed in UTC.")
    utc = value.astimezone(timezone.utc)
    text = utc.isoformat(timespec="microseconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _encode(value: Any) -> Any:
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum) and type(value) in _ALLOWED_ENUMS:
        return value.value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    value_type = type(value)
    if is_dataclass(value) and value_type in _ALLOWED_DATACLASSES:
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"Unsupported finance serialization value {value_type!r}.")


def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (types.UnionType, getattr(__import__("typing"), "Union")):
        if value is None and type(None) in args:
            return None
        non_none = tuple(item for item in args if item is not type(None))
        if len(non_none) != 1:
            raise ValueError(f"Unsupported finance union annotation {annotation!r}.")
        return _decode(non_none[0], value)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("Tuple finance field must be encoded as a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(args) != len(value):
            raise ValueError("Fixed tuple finance field has the wrong length.")
        return tuple(_decode(item_type, item) for item_type, item in zip(args, value))
    if isinstance(annotation, type) and annotation in _ALLOWED_ENUMS:
        if not isinstance(value, str):
            raise ValueError(f"{annotation.__name__} must be encoded as a JSON string.")
        try:
            return annotation(value)
        except ValueError as exc:
            raise ValueError(f"Unknown {annotation.__name__} value {value!r}.") from exc
    if isinstance(annotation, type) and annotation in _ALLOWED_DATACLASSES:
        if not isinstance(value, dict):
            raise ValueError(f"{annotation.__name__} must be encoded as a JSON object.")
        hints = get_type_hints(annotation)
        expected = {field.name for field in fields(annotation)}
        if set(value) != expected:
            missing = sorted(expected - set(value))
            extra = sorted(set(value) - expected)
            raise ValueError(
                f"{annotation.__name__} fields do not match schema; missing={missing}, extra={extra}."
            )
        return annotation(**{f.name: _decode(hints[f.name], value[f.name]) for f in fields(annotation)})
    if annotation is Decimal:
        if not isinstance(value, str):
            raise ValueError("Decimal finance fields must be encoded as JSON strings.")
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid Decimal finance value.") from exc
        if canonical_decimal_text(decimal_value) != value:
            raise ValueError("Decimal finance field is not in canonical form.")
        return decimal_value
    if annotation is datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("Finance datetime must use canonical UTC 'Z' form.")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("Invalid finance datetime.") from exc
        if _datetime_text(parsed) != value:
            raise ValueError("Finance datetime is not in canonical form.")
        return parsed
    if annotation is date:
        if not isinstance(value, str):
            raise ValueError("Finance date must be encoded as a JSON string.")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Invalid finance date.") from exc
        if parsed.isoformat() != value:
            raise ValueError("Finance date is not in canonical form.")
        return parsed
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"Expected {annotation.__name__} finance value.")
        return value
    raise ValueError(f"Unsupported finance field annotation {annotation!r}.")


def _loads_json_object(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ValueError("Finance JSON payload must be text.")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key {key!r} is not allowed.")
            result[key] = value
        return result

    try:
        data = json.loads(payload, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid finance JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Finance JSON root must be an object.")
    return data


def _to_dict(value: Any) -> dict[str, Any]:
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise AssertionError("Finance record must encode to a JSON object.")
    return encoded


def _dumps(value: Any) -> str:
    return canonical_json_bytes(_to_dict(value)).decode("utf-8")


def _loads(payload: str, model_type: type[Any], validator_name: str) -> Any:
    data = _loads_json_object(payload)
    value = _decode(model_type, data)
    from . import validation as validation_module

    getattr(validation_module, validator_name)(value)
    if payload != _dumps(value):
        raise ValueError("Finance JSON is not in the exact canonical v1 form.")
    return value


def financial_period_to_dict(value: FinancialPeriod) -> dict[str, Any]:
    return _to_dict(value)


def financial_period_identity_payload_to_dict(value: FinancialPeriod) -> dict[str, Any]:
    data = financial_period_to_dict(value)
    data.pop("financial_period_id")
    return data


def financial_observation_to_dict(value: FinancialObservation) -> dict[str, Any]:
    return _to_dict(value)


def financial_observation_identity_payload_to_dict(value: FinancialObservation) -> dict[str, Any]:
    data = financial_observation_to_dict(value)
    data.pop("observation_id")
    return data


def financial_fact_to_dict(value: FinancialFact) -> dict[str, Any]:
    return _to_dict(value)


def financial_fact_identity_payload_to_dict(value: FinancialFact) -> dict[str, Any]:
    data = financial_fact_to_dict(value)
    data.pop("fact_id")
    return data


def dumps_finance_workspace(value: FinanceWorkspace) -> str:
    return _dumps(value)


def loads_finance_workspace(payload: str) -> FinanceWorkspace:
    return _loads(payload, FinanceWorkspace, "validate_finance_workspace")


def dumps_company(value: Company) -> str:
    return _dumps(value)


def loads_company(payload: str) -> Company:
    return _loads(payload, Company, "validate_company")


def dumps_security(value: Security) -> str:
    return _dumps(value)


def loads_security(payload: str) -> Security:
    return _loads(payload, Security, "validate_security")


def dumps_financial_period(value: FinancialPeriod) -> str:
    return _dumps(value)


def loads_financial_period(payload: str) -> FinancialPeriod:
    return _loads(payload, FinancialPeriod, "validate_financial_period")


def dumps_financial_observation(value: FinancialObservation) -> str:
    return _dumps(value)


def loads_financial_observation(payload: str) -> FinancialObservation:
    return _loads(payload, FinancialObservation, "validate_financial_observation")


def dumps_financial_fact(value: FinancialFact) -> str:
    return _dumps(value)


def loads_financial_fact(payload: str) -> FinancialFact:
    return _loads(payload, FinancialFact, "validate_financial_fact")


__all__ = [
    "dumps_company",
    "dumps_finance_workspace",
    "dumps_financial_fact",
    "dumps_financial_observation",
    "dumps_financial_period",
    "dumps_security",
    "financial_fact_identity_payload_to_dict",
    "financial_observation_identity_payload_to_dict",
    "financial_period_identity_payload_to_dict",
    "loads_company",
    "loads_finance_workspace",
    "loads_financial_fact",
    "loads_financial_observation",
    "loads_financial_period",
    "loads_security",
]
