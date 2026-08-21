"""Read-only provider for the explicitly selected Finance workspace of one Legal case."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .identity import canonical_uuid, sha256_storage_name, sha256_text
from .models import (
    FINANCE_CASE_BINDING_SCHEMA_VERSION,
    FinanceCaseActiveBinding,
    FinanceCaseBindingActivationAction,
    FinanceCaseBindingActivationReceipt,
)
from .serialization import (
    dumps_finance_case_active_binding,
    loads_finance_case_active_binding,
    loads_finance_case_binding_activation_receipt,
)
from .validation import (
    validate_finance_case_active_binding,
    validate_finance_case_binding_activation_receipt,
)


class FinanceCaseBindingProviderError(RuntimeError):
    """Raised when existing binding state cannot be proved valid."""


def _binding_root() -> Path:
    return Path(__file__).resolve().parents[2] / "finance_case_bindings"


def _is_reparse(value: os.stat_result) -> bool:
    attrs = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attrs & reparse)


def _require_plain_directory(path: Path, *, root: Path) -> None:
    try:
        value = path.lstat()
    except FileNotFoundError as exc:
        raise FinanceCaseBindingProviderError(f"Required binding directory is absent: {path.name}") from exc
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or _is_reparse(value):
        raise FinanceCaseBindingProviderError(f"Binding path is not a plain directory: {path.name}")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise FinanceCaseBindingProviderError("Binding directory escapes governed root.") from exc


def _read_utf8(path: Path, *, root: Path) -> str:
    try:
        value = path.lstat()
    except FileNotFoundError as exc:
        raise FinanceCaseBindingProviderError(f"Required binding file is absent: {path.name}") from exc
    if not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode) or _is_reparse(value):
        raise FinanceCaseBindingProviderError(f"Binding path is not a plain regular file: {path.name}")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise FinanceCaseBindingProviderError("Binding file escapes governed root.") from exc
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FinanceCaseBindingProviderError(f"Unable to read binding file: {path.name}") from exc


def _reconstruct_pointer(receipt: FinanceCaseBindingActivationReceipt) -> FinanceCaseActiveBinding:
    return FinanceCaseActiveBinding(
        schema_version=FINANCE_CASE_BINDING_SCHEMA_VERSION,
        case_id=receipt.case_id,
        workspace_id=receipt.new_workspace_id,
        activation_id=receipt.activation_id,
    )


def _load_receipt(
    *,
    case_id: str,
    activation_id: str,
    root: Path,
) -> tuple[FinanceCaseBindingActivationReceipt, str]:
    activations_root = root / case_id / "activations"
    _require_plain_directory(activations_root, root=root)
    name = sha256_storage_name(activation_id, field_name="activation_id") + ".json"
    payload = _read_utf8(activations_root / name, root=root)
    try:
        receipt = loads_finance_case_binding_activation_receipt(payload)
    except (TypeError, ValueError) as exc:
        raise FinanceCaseBindingProviderError("Activation history contains invalid canonical receipt state.") from exc
    if receipt.case_id != case_id or receipt.activation_id != activation_id:
        raise FinanceCaseBindingProviderError("Activation history receipt is cross-case or misnamed.")
    return receipt, payload


def _load_active_state(
    case_id: str,
) -> tuple[
    FinanceCaseActiveBinding,
    str,
    tuple[FinanceCaseBindingActivationReceipt, ...],
] | None:
    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
    except ValueError as exc:
        raise FinanceCaseBindingProviderError("Invalid canonical case_id.") from exc

    root = _binding_root()
    if not root.exists():
        return None
    _require_plain_directory(root, root=root)
    case_root = root / canonical_case_id
    if not case_root.exists():
        return None
    _require_plain_directory(case_root, root=root)
    active_path = case_root / "active.json"
    if not active_path.exists():
        return None

    payload = _read_utf8(active_path, root=root)
    try:
        pointer = loads_finance_case_active_binding(payload)
        validate_finance_case_active_binding(pointer)
    except (TypeError, ValueError) as exc:
        raise FinanceCaseBindingProviderError("Active Finance case binding is invalid.") from exc
    if pointer.case_id != canonical_case_id:
        raise FinanceCaseBindingProviderError("Active Finance case binding is cross-case.")

    chain: list[FinanceCaseBindingActivationReceipt] = []
    pointer_payloads: list[str] = []
    next_id: str | None = pointer.activation_id
    seen: set[str] = set()

    while next_id is not None:
        if next_id in seen:
            raise FinanceCaseBindingProviderError("Finance case-binding activation history contains a cycle.")
        seen.add(next_id)
        receipt, _ = _load_receipt(case_id=canonical_case_id, activation_id=next_id, root=root)
        reconstructed = _reconstruct_pointer(receipt)
        reconstructed_payload = dumps_finance_case_active_binding(reconstructed)
        if receipt.new_active_binding_sha256 != sha256_text(reconstructed_payload):
            raise FinanceCaseBindingProviderError("Activation receipt new active-binding SHA mismatch.")
        chain.append(receipt)
        pointer_payloads.append(reconstructed_payload)
        next_id = receipt.previous_activation_id

    if not chain:
        raise FinanceCaseBindingProviderError("Active Finance case binding has no immutable activation receipt.")
    if pointer_payloads[0] != payload:
        raise FinanceCaseBindingProviderError("Active Finance case binding does not match its immutable receipt.")

    for index, receipt in enumerate(chain):
        previous_payload = None if index + 1 >= len(pointer_payloads) else pointer_payloads[index + 1]
        try:
            validate_finance_case_binding_activation_receipt(
                receipt,
                active_binding=_reconstruct_pointer(receipt),
                previous_active_binding_payload=previous_payload,
            )
        except ValueError as exc:
            raise FinanceCaseBindingProviderError(
                "Finance case-binding activation history failed deterministic validation."
            ) from exc
        if receipt.action is FinanceCaseBindingActivationAction.ROLLBACK:
            older_workspaces = {older.new_workspace_id for older in chain[index + 1 :]}
            if receipt.new_workspace_id not in older_workspaces:
                raise FinanceCaseBindingProviderError(
                    "ROLLBACK target workspace does not occur in validated prior activation history."
                )

    return pointer, payload, tuple(chain)


def load_active_finance_case_binding(case_id: str) -> FinanceCaseActiveBinding | None:
    """Load the exact selected Finance workspace, returning None only for absence."""

    state = _load_active_state(case_id)
    return None if state is None else state[0]
