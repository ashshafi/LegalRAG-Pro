from uuid import uuid4

import pytest

from finance_case_binding.identity import (
    derive_finance_case_binding_activation_id,
    sha256_text,
)
from finance_case_binding.models import (
    FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
    FINANCE_CASE_BINDING_SCHEMA_VERSION,
    FinanceCaseActiveBinding,
    FinanceCaseBindingActivationAction,
    FinanceCaseBindingActivationReceipt,
)
from finance_case_binding.serialization import dumps_finance_case_active_binding
from finance_case_binding.validation import validate_finance_case_binding_activation_receipt


def _first():
    case_id = str(uuid4()); workspace_id = str(uuid4())
    aid = derive_finance_case_binding_activation_id(
        case_id=case_id,
        action=FinanceCaseBindingActivationAction.ACTIVATE,
        previous_activation_id=None,
        previous_workspace_id=None,
        new_workspace_id=workspace_id,
        previous_active_binding_sha256=None,
    )
    pointer = FinanceCaseActiveBinding(
        FINANCE_CASE_BINDING_SCHEMA_VERSION, case_id, workspace_id, aid
    )
    receipt = FinanceCaseBindingActivationReceipt(
        FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
        case_id,
        aid,
        FinanceCaseBindingActivationAction.ACTIVATE,
        None,
        None,
        workspace_id,
        None,
        sha256_text(dumps_finance_case_active_binding(pointer)),
    )
    return pointer, receipt


def test_first_activation_validates():
    pointer, receipt = _first()
    validate_finance_case_binding_activation_receipt(receipt, active_binding=pointer)


def test_first_rollback_is_rejected():
    pointer, receipt = _first()
    bad = FinanceCaseBindingActivationReceipt(
        receipt.schema_version, receipt.case_id, receipt.activation_id,
        FinanceCaseBindingActivationAction.ROLLBACK,
        None, None, receipt.new_workspace_id, None, receipt.new_active_binding_sha256
    )
    with pytest.raises(ValueError, match="First Finance case-binding action"):
        validate_finance_case_binding_activation_receipt(bad, active_binding=pointer)
