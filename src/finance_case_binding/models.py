"""Immutable models for the explicit Legal-case to Finance-workspace active binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


FINANCE_CASE_BINDING_SCHEMA_VERSION = "finance-case-binding-v1"
FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION = "finance-case-binding-activation-v1"


class FinanceCaseBindingActivationAction(str, Enum):
    """Explicit lifecycle actions permitted by the frozen P12 contract."""

    ACTIVATE = "ACTIVATE"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class FinanceCaseActiveBinding:
    """Tiny current-state pointer from one Legal case to one selected Finance workspace."""

    schema_version: str
    case_id: str
    workspace_id: str
    activation_id: str


@dataclass(frozen=True, slots=True)
class FinanceCaseBindingActivationReceipt:
    """Immutable receipt proving one active-binding lifecycle transition."""

    schema_version: str
    case_id: str
    activation_id: str
    action: FinanceCaseBindingActivationAction
    previous_activation_id: str | None
    previous_workspace_id: str | None
    new_workspace_id: str
    previous_active_binding_sha256: str | None
    new_active_binding_sha256: str
