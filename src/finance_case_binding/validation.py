"""Fail-closed validation for Finance case/workspace active-binding state."""

from __future__ import annotations

from .identity import (
    canonical_uuid,
    derive_finance_case_binding_activation_id,
    sha256_text,
    validate_sha256_id,
)
from .models import (
    FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
    FINANCE_CASE_BINDING_SCHEMA_VERSION,
    FinanceCaseActiveBinding,
    FinanceCaseBindingActivationAction,
    FinanceCaseBindingActivationReceipt,
)
from .serialization import (
    dumps_finance_case_active_binding,
    loads_finance_case_active_binding,
)


def validate_finance_case_active_binding(pointer: FinanceCaseActiveBinding) -> None:
    if not isinstance(pointer, FinanceCaseActiveBinding):
        raise ValueError("pointer must be a FinanceCaseActiveBinding.")
    if pointer.schema_version != FINANCE_CASE_BINDING_SCHEMA_VERSION:
        raise ValueError("Unsupported Finance case-binding schema.")
    canonical_uuid(pointer.case_id, field_name="case_id")
    canonical_uuid(pointer.workspace_id, field_name="workspace_id")
    validate_sha256_id(pointer.activation_id, field_name="activation_id")


def validate_finance_case_binding_activation_receipt(
    receipt: FinanceCaseBindingActivationReceipt,
    *,
    active_binding: FinanceCaseActiveBinding,
    previous_active_binding_payload: str | None = None,
) -> None:
    if not isinstance(receipt, FinanceCaseBindingActivationReceipt):
        raise ValueError("receipt must be a FinanceCaseBindingActivationReceipt.")
    if receipt.schema_version != FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION:
        raise ValueError("Unsupported Finance case-binding activation schema.")
    if not isinstance(receipt.action, FinanceCaseBindingActivationAction):
        raise ValueError("Activation receipt action is invalid.")

    validate_finance_case_active_binding(active_binding)
    canonical_uuid(receipt.case_id, field_name="case_id")
    canonical_uuid(receipt.new_workspace_id, field_name="new_workspace_id")
    validate_sha256_id(receipt.activation_id, field_name="activation_id")
    validate_sha256_id(
        receipt.new_active_binding_sha256,
        field_name="new_active_binding_sha256",
    )

    if receipt.case_id != active_binding.case_id:
        raise ValueError("Activation receipt case_id does not match active binding.")
    if receipt.activation_id != active_binding.activation_id:
        raise ValueError("Activation receipt activation_id does not match active binding.")
    if receipt.new_workspace_id != active_binding.workspace_id:
        raise ValueError("Activation receipt workspace does not match active binding.")

    expected_new_sha = sha256_text(dumps_finance_case_active_binding(active_binding))
    if receipt.new_active_binding_sha256 != expected_new_sha:
        raise ValueError("Activation receipt does not bind exact new active-binding bytes.")

    if previous_active_binding_payload is None:
        if any(
            value is not None
            for value in (
                receipt.previous_activation_id,
                receipt.previous_workspace_id,
                receipt.previous_active_binding_sha256,
            )
        ):
            raise ValueError("First activation cannot claim previous active-binding state.")
        if receipt.action is not FinanceCaseBindingActivationAction.ACTIVATE:
            raise ValueError("First Finance case-binding action must be ACTIVATE.")
    else:
        previous = loads_finance_case_active_binding(previous_active_binding_payload)
        validate_finance_case_active_binding(previous)
        if previous.case_id != receipt.case_id:
            raise ValueError("Previous active binding belongs to a different case.")
        if receipt.previous_activation_id != previous.activation_id:
            raise ValueError("previous_activation_id mismatch.")
        if receipt.previous_workspace_id != previous.workspace_id:
            raise ValueError("previous_workspace_id mismatch.")
        if receipt.previous_active_binding_sha256 != sha256_text(previous_active_binding_payload):
            raise ValueError("previous active-binding SHA mismatch.")

    expected_id = derive_finance_case_binding_activation_id(
        case_id=receipt.case_id,
        action=receipt.action,
        previous_activation_id=receipt.previous_activation_id,
        previous_workspace_id=receipt.previous_workspace_id,
        new_workspace_id=receipt.new_workspace_id,
        previous_active_binding_sha256=receipt.previous_active_binding_sha256,
        schema_version=receipt.schema_version,
    )
    if receipt.activation_id != expected_id:
        raise ValueError("Activation receipt activation_id is not deterministic.")
