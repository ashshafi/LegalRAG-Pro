"""Explicit ACTIVATE/ROLLBACK lifecycle for Finance case/workspace active bindings."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import uuid4

from . import provider as _provider
from .identity import (
    canonical_uuid,
    derive_finance_case_binding_activation_id,
    sha256_storage_name,
    sha256_text,
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
    dumps_finance_case_binding_activation_receipt,
)
from .validation import validate_finance_case_binding_activation_receipt


class FinanceCaseBindingActivationError(RuntimeError):
    """Raised when a binding transition cannot be proved and applied."""


def _binding_root() -> Path:
    return _provider._binding_root()


def _is_reparse(value: os.stat_result) -> bool:
    attrs = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attrs & reparse)


def _ensure_plain_directory(path: Path) -> None:
    if path.exists():
        value = path.lstat()
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or _is_reparse(value):
            raise FinanceCaseBindingActivationError(f"Activation path is not a plain directory: {path}")
        return
    try:
        path.mkdir()
    except OSError as exc:
        raise FinanceCaseBindingActivationError(f"Unable to prepare activation directory: {path}") from exc


def _write_new_file(path: Path, payload: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise FinanceCaseBindingActivationError(f"Unable to write immutable activation state: {path.name}") from exc


def activate_finance_case_binding(
    *,
    case_id: str,
    workspace_id: str,
    action: FinanceCaseBindingActivationAction = FinanceCaseBindingActivationAction.ACTIVATE,
) -> FinanceCaseActiveBinding:
    """Explicitly activate or roll back the selected Finance workspace for one Legal case."""

    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
        canonical_workspace_id = canonical_uuid(workspace_id, field_name="workspace_id")
    except ValueError as exc:
        raise FinanceCaseBindingActivationError(
            "Activation requires canonical case and workspace identities."
        ) from exc
    if not isinstance(action, FinanceCaseBindingActivationAction):
        raise FinanceCaseBindingActivationError(
            "action must be a FinanceCaseBindingActivationAction."
        )

    try:
        previous_state = _provider._load_active_state(canonical_case_id)
    except _provider.FinanceCaseBindingProviderError as exc:
        raise FinanceCaseBindingActivationError(
            "Existing Finance case-binding state is invalid; activation cannot silently repair it."
        ) from exc

    previous_pointer = None if previous_state is None else previous_state[0]
    previous_payload = None if previous_state is None else previous_state[1]
    chain = () if previous_state is None else previous_state[2]

    if previous_pointer is None:
        if action is not FinanceCaseBindingActivationAction.ACTIVATE:
            raise FinanceCaseBindingActivationError("First binding lifecycle action must be ACTIVATE.")
        previous_activation_id = None
        previous_workspace_id = None
        previous_sha = None
    else:
        previous_activation_id = previous_pointer.activation_id
        previous_workspace_id = previous_pointer.workspace_id
        previous_sha = sha256_text(previous_payload)
        if action is FinanceCaseBindingActivationAction.ACTIVATE:
            if canonical_workspace_id == previous_pointer.workspace_id:
                raise FinanceCaseBindingActivationError("ACTIVATE cannot create a no-op binding transition.")
        elif action is FinanceCaseBindingActivationAction.ROLLBACK:
            older_workspaces = {receipt.new_workspace_id for receipt in chain[1:]}
            if canonical_workspace_id not in older_workspaces:
                raise FinanceCaseBindingActivationError(
                    "ROLLBACK target workspace does not occur in validated prior activation chain."
                )

    activation_id = derive_finance_case_binding_activation_id(
        case_id=canonical_case_id,
        action=action,
        previous_activation_id=previous_activation_id,
        previous_workspace_id=previous_workspace_id,
        new_workspace_id=canonical_workspace_id,
        previous_active_binding_sha256=previous_sha,
        schema_version=FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
    )
    pointer = FinanceCaseActiveBinding(
        schema_version=FINANCE_CASE_BINDING_SCHEMA_VERSION,
        case_id=canonical_case_id,
        workspace_id=canonical_workspace_id,
        activation_id=activation_id,
    )
    pointer_payload = dumps_finance_case_active_binding(pointer)
    receipt = FinanceCaseBindingActivationReceipt(
        schema_version=FINANCE_CASE_BINDING_ACTIVATION_SCHEMA_VERSION,
        case_id=canonical_case_id,
        activation_id=activation_id,
        action=action,
        previous_activation_id=previous_activation_id,
        previous_workspace_id=previous_workspace_id,
        new_workspace_id=canonical_workspace_id,
        previous_active_binding_sha256=previous_sha,
        new_active_binding_sha256=sha256_text(pointer_payload),
    )
    try:
        validate_finance_case_binding_activation_receipt(
            receipt,
            active_binding=pointer,
            previous_active_binding_payload=previous_payload,
        )
    except ValueError as exc:
        raise FinanceCaseBindingActivationError("Constructed binding transition is invalid.") from exc

    root = _binding_root()
    if root.exists():
        _ensure_plain_directory(root)
    else:
        parent = root.parent
        if not parent.exists():
            raise FinanceCaseBindingActivationError("Binding root parent is absent.")
        _ensure_plain_directory(root)

    case_root = root / canonical_case_id
    _ensure_plain_directory(case_root)
    activations_root = case_root / "activations"
    _ensure_plain_directory(activations_root)

    receipt_payload = dumps_finance_case_binding_activation_receipt(receipt)
    receipt_path = activations_root / (
        sha256_storage_name(activation_id, field_name="activation_id") + ".json"
    )
    if receipt_path.exists():
        try:
            existing = receipt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FinanceCaseBindingActivationError("Unable to inspect existing activation receipt.") from exc
        if existing != receipt_payload:
            raise FinanceCaseBindingActivationError(
                "Existing immutable activation receipt conflicts with this transition."
            )
    else:
        staging_receipt = activations_root / f".staging-{uuid4().hex}.json"
        _write_new_file(staging_receipt, receipt_payload)
        try:
            os.rename(staging_receipt, receipt_path)
        except OSError as exc:
            raise FinanceCaseBindingActivationError(
                "Activation receipt publication failed; preserve staging state."
            ) from exc

    temp_pointer = case_root / f".active-{uuid4().hex}.tmp"
    _write_new_file(temp_pointer, pointer_payload)
    try:
        os.replace(temp_pointer, case_root / "active.json")
    except OSError as exc:
        raise FinanceCaseBindingActivationError(
            "Active binding publication failed; immutable receipt remains preserved."
        ) from exc

    try:
        proved = _provider.load_active_finance_case_binding(canonical_case_id)
    except _provider.FinanceCaseBindingProviderError as exc:
        raise FinanceCaseBindingActivationError(
            "Post-activation active-binding validation failed; preserve exact state."
        ) from exc
    if proved != pointer:
        raise FinanceCaseBindingActivationError(
            "Post-activation provider did not return exact selected binding."
        )
    return pointer
