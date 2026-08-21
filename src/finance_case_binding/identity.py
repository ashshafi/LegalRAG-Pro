"""Canonical identity helpers for Finance case/workspace binding state."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from .models import (
    FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
    FinanceCaseBindingActivationAction,
)

_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_uuid(value: str, *, field_name: str) -> str:
    """Require and return an already-canonical UUID string."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a canonical UUID string.")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a canonical UUID string.") from exc
    if value != canonical:
        raise ValueError(f"{field_name} must already be canonical.")
    return canonical


def validate_sha256_id(value: str, *, field_name: str) -> str:
    """Require the canonical sha256:<hex> identity form."""

    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical sha256 identity.")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(payload: str) -> str:
    if not isinstance(payload, str):
        raise TypeError("payload must be str.")
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_storage_name(identity: str, *, field_name: str) -> str:
    validate_sha256_id(identity, field_name=field_name)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def derive_finance_case_binding_activation_id(
    *,
    case_id: str,
    action: FinanceCaseBindingActivationAction,
    previous_activation_id: str | None,
    previous_workspace_id: str | None,
    new_workspace_id: str,
    previous_active_binding_sha256: str | None,
    schema_version: str = FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
) -> str:
    """Derive the deterministic identity of one lifecycle transition."""

    canonical_case_id = canonical_uuid(case_id, field_name="case_id")
    canonical_new_workspace_id = canonical_uuid(new_workspace_id, field_name="new_workspace_id")
    if not isinstance(action, FinanceCaseBindingActivationAction):
        raise ValueError("action must be a FinanceCaseBindingActivationAction.")
    if schema_version != FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION:
        raise ValueError("Unsupported Finance case-binding activation schema.")

    if previous_activation_id is not None:
        validate_sha256_id(previous_activation_id, field_name="previous_activation_id")
    if previous_workspace_id is not None:
        previous_workspace_id = canonical_uuid(
            previous_workspace_id, field_name="previous_workspace_id"
        )
    if previous_active_binding_sha256 is not None:
        validate_sha256_id(
            previous_active_binding_sha256,
            field_name="previous_active_binding_sha256",
        )

    payload = canonical_json(
        {
            "schema_version": schema_version,
            "case_id": canonical_case_id,
            "action": action.value,
            "previous_activation_id": previous_activation_id,
            "previous_workspace_id": previous_workspace_id,
            "new_workspace_id": canonical_new_workspace_id,
            "previous_active_binding_sha256": previous_active_binding_sha256,
        }
    )
    return sha256_text(payload)
