"""Canonical JSON serialization for Finance case/workspace binding state."""

from __future__ import annotations

import json
from typing import Any

from .identity import canonical_json
from .models import (
    FinanceCaseActiveBinding,
    FinanceCaseBindingActivationAction,
    FinanceCaseBindingActivationReceipt,
)


_POINTER_KEYS = frozenset({"schema_version", "case_id", "workspace_id", "activation_id"})
_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "activation_id",
        "action",
        "previous_activation_id",
        "previous_workspace_id",
        "new_workspace_id",
        "previous_active_binding_sha256",
        "new_active_binding_sha256",
    }
)


def _object(payload: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} JSON is invalid.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _exact_keys(value: dict[str, Any], expected: frozenset[str], *, label: str) -> None:
    if frozenset(value) != expected:
        raise ValueError(f"{label} keys are not exact.")


def finance_case_active_binding_to_dict(value: FinanceCaseActiveBinding) -> dict[str, Any]:
    if not isinstance(value, FinanceCaseActiveBinding):
        raise ValueError("value must be a FinanceCaseActiveBinding.")
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "workspace_id": value.workspace_id,
        "activation_id": value.activation_id,
    }


def dumps_finance_case_active_binding(value: FinanceCaseActiveBinding) -> str:
    return canonical_json(finance_case_active_binding_to_dict(value))


def loads_finance_case_active_binding(payload: str) -> FinanceCaseActiveBinding:
    data = _object(payload, label="FinanceCaseActiveBinding")
    _exact_keys(data, _POINTER_KEYS, label="FinanceCaseActiveBinding")
    result = FinanceCaseActiveBinding(
        schema_version=str(data["schema_version"]),
        case_id=str(data["case_id"]),
        workspace_id=str(data["workspace_id"]),
        activation_id=str(data["activation_id"]),
    )
    if dumps_finance_case_active_binding(result) != payload:
        raise ValueError("FinanceCaseActiveBinding JSON is not canonical.")
    return result


def finance_case_binding_activation_receipt_to_dict(
    value: FinanceCaseBindingActivationReceipt,
) -> dict[str, Any]:
    if not isinstance(value, FinanceCaseBindingActivationReceipt):
        raise ValueError("value must be a FinanceCaseBindingActivationReceipt.")
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "activation_id": value.activation_id,
        "action": value.action.value,
        "previous_activation_id": value.previous_activation_id,
        "previous_workspace_id": value.previous_workspace_id,
        "new_workspace_id": value.new_workspace_id,
        "previous_active_binding_sha256": value.previous_active_binding_sha256,
        "new_active_binding_sha256": value.new_active_binding_sha256,
    }


def dumps_finance_case_binding_activation_receipt(
    value: FinanceCaseBindingActivationReceipt,
) -> str:
    return canonical_json(finance_case_binding_activation_receipt_to_dict(value))


def loads_finance_case_binding_activation_receipt(
    payload: str,
) -> FinanceCaseBindingActivationReceipt:
    data = _object(payload, label="FinanceCaseBindingActivationReceipt")
    _exact_keys(data, _RECEIPT_KEYS, label="FinanceCaseBindingActivationReceipt")
    try:
        action = FinanceCaseBindingActivationAction(str(data["action"]))
    except ValueError as exc:
        raise ValueError("Finance case-binding activation action is invalid.") from exc
    result = FinanceCaseBindingActivationReceipt(
        schema_version=str(data["schema_version"]),
        case_id=str(data["case_id"]),
        activation_id=str(data["activation_id"]),
        action=action,
        previous_activation_id=(
            None if data["previous_activation_id"] is None else str(data["previous_activation_id"])
        ),
        previous_workspace_id=(
            None if data["previous_workspace_id"] is None else str(data["previous_workspace_id"])
        ),
        new_workspace_id=str(data["new_workspace_id"]),
        previous_active_binding_sha256=(
            None
            if data["previous_active_binding_sha256"] is None
            else str(data["previous_active_binding_sha256"])
        ),
        new_active_binding_sha256=str(data["new_active_binding_sha256"]),
    )
    if dumps_finance_case_binding_activation_receipt(result) != payload:
        raise ValueError("FinanceCaseBindingActivationReceipt JSON is not canonical.")
    return result
