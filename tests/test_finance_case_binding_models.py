from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from finance_case_binding.models import (
    FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
    FINANCE_CASE_BINDING_SCHEMA_VERSION,
    FinanceCaseActiveBinding,
    FinanceCaseBindingActivationAction,
    FinanceCaseBindingActivationReceipt,
)


def test_action_contract_is_activate_and_rollback_only():
    assert [x.value for x in FinanceCaseBindingActivationAction] == ["ACTIVATE", "ROLLBACK"]


def test_active_binding_is_frozen_tiny_pointer():
    pointer = FinanceCaseActiveBinding(
        schema_version=FINANCE_CASE_BINDING_SCHEMA_VERSION,
        case_id=str(uuid4()),
        workspace_id=str(uuid4()),
        activation_id="sha256:" + "a" * 64,
    )
    assert tuple(pointer.__dataclass_fields__) == (
        "schema_version", "case_id", "workspace_id", "activation_id"
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        pointer.workspace_id = str(uuid4())


def test_receipt_fields_are_exact():
    assert tuple(FinanceCaseBindingActivationReceipt.__dataclass_fields__) == (
        "schema_version",
        "case_id",
        "activation_id",
        "action",
        "previous_activation_id",
        "previous_workspace_id",
        "new_workspace_id",
        "previous_active_binding_sha256",
        "new_active_binding_sha256",
    )
    assert FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION
