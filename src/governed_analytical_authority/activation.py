"""Explicit activation and rollback selection for published analytical authorities."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from uuid import uuid4

from .identity import (
    canonical_sha256,
    derive_governed_analytical_authority_activation_id,
    require_canonical_case_id,
    sha256_storage_name,
)
from .models import (
    GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME,
    GovernedAnalyticalAuthorityActivationAction,
    GovernedAnalyticalAuthorityActivationReceipt,
    GovernedAnalyticalAuthorityActivePointer,
)
from .provider import (
    GovernedAnalyticalAuthorityProviderError,
    _load_published_authority,
    _read_utf8,
    _require_safe_directory,
)
from .serialization import (
    dumps_governed_analytical_authority_activation_receipt,
    dumps_governed_analytical_authority_active_pointer,
    loads_governed_analytical_authority_activation_receipt,
    loads_governed_analytical_authority_active_pointer,
)
from .validation import validate_governed_analytical_authority_active_pointer


class GovernedAnalyticalAuthorityActivationError(RuntimeError):
    """Raised when an explicit activation transition cannot be proved and applied."""


def _authority_root() -> Path:
    return Path(__file__).resolve().parents[2] / GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _ensure_plain_directory(path: Path) -> None:
    try:
        path.mkdir(exist_ok=True)
        if path.is_symlink() or _is_reparse(path) or not path.is_dir():
            raise GovernedAnalyticalAuthorityActivationError(
                f"Activation path is not a plain directory: {path}"
            )
    except OSError as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            f"Unable to prepare activation directory: {path}"
        ) from exc


def _write_new_file(path: Path, payload: str) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            f"Unable to write immutable activation state: {path.name}"
        ) from exc


def _load_receipt(
    *,
    case_id: str,
    activation_id: str,
    root: Path,
) -> tuple[GovernedAnalyticalAuthorityActivationReceipt, str]:
    activations_root = root / case_id / "activations"
    _require_safe_directory(activations_root, root=root)
    filename = sha256_storage_name(activation_id, field_name="activation_id") + ".json"
    payload = _read_utf8(activations_root / filename, root=root)
    try:
        receipt = loads_governed_analytical_authority_activation_receipt(payload)
    except (TypeError, ValueError) as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            "Activation history contains invalid canonical receipt state."
        ) from exc
    if receipt.case_id != case_id or receipt.activation_id != activation_id:
        raise GovernedAnalyticalAuthorityActivationError(
            "Activation history receipt is cross-case or misnamed."
        )
    return receipt, payload


def _reconstruct_receipt_pointer(
    receipt: GovernedAnalyticalAuthorityActivationReceipt,
    *,
    root: Path,
) -> GovernedAnalyticalAuthorityActivePointer:
    published = _load_published_authority(
        case_id=receipt.case_id,
        authority_id=receipt.new_authority_id,
        root=root,
    )
    pointer = GovernedAnalyticalAuthorityActivePointer(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
        case_id=receipt.case_id,
        authority_id=receipt.new_authority_id,
        authority_manifest_sha256=canonical_sha256(published.manifest_payload),
        activation_id=receipt.activation_id,
    )
    validate_governed_analytical_authority_active_pointer(pointer)
    if canonical_sha256(dumps_governed_analytical_authority_active_pointer(pointer)) != receipt.new_active_pointer_sha256:
        raise GovernedAnalyticalAuthorityActivationError(
            "Activation history receipt does not bind its reconstructed active pointer."
        )
    return pointer


def _load_activation_chain(
    *,
    case_id: str,
    current_activation_id: str,
    root: Path,
) -> tuple[GovernedAnalyticalAuthorityActivationReceipt, ...]:
    """Return newest-to-oldest validated immutable activation history."""

    chain: list[GovernedAnalyticalAuthorityActivationReceipt] = []
    seen: set[str] = set()
    next_id: str | None = current_activation_id
    newer: GovernedAnalyticalAuthorityActivationReceipt | None = None
    while next_id is not None:
        if next_id in seen:
            raise GovernedAnalyticalAuthorityActivationError("Activation history contains a cycle.")
        seen.add(next_id)
        receipt, _ = _load_receipt(case_id=case_id, activation_id=next_id, root=root)

        expected_id = derive_governed_analytical_authority_activation_id(
            case_id=receipt.case_id,
            action=receipt.action,
            previous_activation_id=receipt.previous_activation_id,
            previous_authority_id=receipt.previous_authority_id,
            new_authority_id=receipt.new_authority_id,
            previous_active_pointer_sha256=receipt.previous_active_pointer_sha256,
            schema_version=receipt.schema_version,
        )
        if receipt.activation_id != expected_id:
            raise GovernedAnalyticalAuthorityActivationError(
                "Activation history contains a nondeterministic activation identity."
            )
        receipt_pointer = _reconstruct_receipt_pointer(receipt, root=root)

        if newer is not None:
            if newer.previous_activation_id != receipt.activation_id:
                raise GovernedAnalyticalAuthorityActivationError(
                    "Activation history previous_activation_id chain is broken."
                )
            if newer.previous_authority_id != receipt.new_authority_id:
                raise GovernedAnalyticalAuthorityActivationError(
                    "Activation history previous_authority_id chain is broken."
                )
            if newer.previous_active_pointer_sha256 != canonical_sha256(
                dumps_governed_analytical_authority_active_pointer(receipt_pointer)
            ):
                raise GovernedAnalyticalAuthorityActivationError(
                    "Activation history previous pointer SHA chain is broken."
                )

        if receipt.previous_activation_id is None:
            if any(
                item is not None
                for item in (
                    receipt.previous_authority_id,
                    receipt.previous_active_pointer_sha256,
                )
            ):
                raise GovernedAnalyticalAuthorityActivationError(
                    "First activation receipt claims nonexistent previous state."
                )
            if receipt.action is not GovernedAnalyticalAuthorityActivationAction.ACTIVATE:
                raise GovernedAnalyticalAuthorityActivationError(
                    "First activation history action must be ACTIVATE."
                )
        else:
            if receipt.previous_authority_id is None or receipt.previous_active_pointer_sha256 is None:
                raise GovernedAnalyticalAuthorityActivationError(
                    "Activation history omits required previous-pointer provenance."
                )

        chain.append(receipt)
        newer = receipt
        next_id = receipt.previous_activation_id
    return tuple(chain)


def _load_current_pointer(
    *,
    case_id: str,
    root: Path,
) -> tuple[GovernedAnalyticalAuthorityActivePointer, str, tuple[GovernedAnalyticalAuthorityActivationReceipt, ...]] | None:
    case_root = root / case_id
    active_path = case_root / "active.json"
    if not active_path.exists():
        return None
    active_payload = _read_utf8(active_path, root=root)
    try:
        pointer = loads_governed_analytical_authority_active_pointer(active_payload)
        validate_governed_analytical_authority_active_pointer(pointer)
    except (TypeError, ValueError) as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            "Existing active pointer is invalid; activation cannot silently repair it."
        ) from exc
    if pointer.case_id != case_id:
        raise GovernedAnalyticalAuthorityActivationError(
            "Existing active pointer is cross-case."
        )
    chain = _load_activation_chain(
        case_id=case_id,
        current_activation_id=pointer.activation_id,
        root=root,
    )
    reconstructed = _reconstruct_receipt_pointer(chain[0], root=root)
    if reconstructed != pointer:
        raise GovernedAnalyticalAuthorityActivationError(
            "Existing active pointer does not match its immutable activation receipt."
        )
    if canonical_sha256(active_payload) != chain[0].new_active_pointer_sha256:
        raise GovernedAnalyticalAuthorityActivationError(
            "Existing active pointer bytes do not match its activation receipt."
        )
    return pointer, active_payload, chain


def activate_governed_analytical_authority(
    *,
    case_id: str,
    authority_id: str,
    action: GovernedAnalyticalAuthorityActivationAction = GovernedAnalyticalAuthorityActivationAction.ACTIVATE,
) -> GovernedAnalyticalAuthorityActivePointer:
    """Select one already-published valid authority via an explicit lifecycle action."""

    try:
        canonical_case_id = require_canonical_case_id(case_id)
        sha256_storage_name(authority_id, field_name="authority_id")
    except ValueError as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            "Activation requires canonical case and authority identities."
        ) from exc
    if not isinstance(action, GovernedAnalyticalAuthorityActivationAction):
        raise GovernedAnalyticalAuthorityActivationError(
            "action must be a GovernedAnalyticalAuthorityActivationAction."
        )

    root = _authority_root()
    try:
        _require_safe_directory(root, root=root)
        _require_safe_directory(root / canonical_case_id, root=root)
        target = _load_published_authority(
            case_id=canonical_case_id,
            authority_id=authority_id,
            root=root,
        )
    except GovernedAnalyticalAuthorityProviderError as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            "Target authority is not an already-published valid immutable authority."
        ) from exc

    current = _load_current_pointer(case_id=canonical_case_id, root=root)
    if current is None:
        if action is not GovernedAnalyticalAuthorityActivationAction.ACTIVATE:
            raise GovernedAnalyticalAuthorityActivationError(
                "ROLLBACK is invalid when no authority has previously been active."
            )
        previous_pointer = None
        previous_payload = None
        chain: tuple[GovernedAnalyticalAuthorityActivationReceipt, ...] = ()
    else:
        previous_pointer, previous_payload, chain = current
        if previous_pointer.authority_id == authority_id:
            if action is GovernedAnalyticalAuthorityActivationAction.ACTIVATE:
                return previous_pointer
            raise GovernedAnalyticalAuthorityActivationError(
                "ROLLBACK cannot target the already-active authority."
            )
        previously_active = {item.new_authority_id for item in chain[1:]}
        if authority_id in previously_active:
            if action is not GovernedAnalyticalAuthorityActivationAction.ROLLBACK:
                raise GovernedAnalyticalAuthorityActivationError(
                    "Re-selection of a previously active authority must use ROLLBACK."
                )
        elif action is GovernedAnalyticalAuthorityActivationAction.ROLLBACK:
            raise GovernedAnalyticalAuthorityActivationError(
                "ROLLBACK target does not occur in the validated prior activation chain."
            )

    previous_activation_id = None if previous_pointer is None else previous_pointer.activation_id
    previous_authority_id = None if previous_pointer is None else previous_pointer.authority_id
    previous_pointer_sha = None if previous_payload is None else canonical_sha256(previous_payload)

    activation_id = derive_governed_analytical_authority_activation_id(
        case_id=canonical_case_id,
        action=action,
        previous_activation_id=previous_activation_id,
        previous_authority_id=previous_authority_id,
        new_authority_id=authority_id,
        previous_active_pointer_sha256=previous_pointer_sha,
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    )
    pointer = GovernedAnalyticalAuthorityActivePointer(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
        case_id=canonical_case_id,
        authority_id=authority_id,
        authority_manifest_sha256=canonical_sha256(target.manifest_payload),
        activation_id=activation_id,
    )
    pointer_payload = dumps_governed_analytical_authority_active_pointer(pointer)
    receipt = GovernedAnalyticalAuthorityActivationReceipt(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
        case_id=canonical_case_id,
        activation_id=activation_id,
        action=action,
        previous_activation_id=previous_activation_id,
        previous_authority_id=previous_authority_id,
        new_authority_id=authority_id,
        previous_active_pointer_sha256=previous_pointer_sha,
        new_active_pointer_sha256=canonical_sha256(pointer_payload),
    )
    receipt_payload = dumps_governed_analytical_authority_activation_receipt(receipt)

    case_root = root / canonical_case_id
    activations_root = case_root / "activations"
    _ensure_plain_directory(activations_root)
    receipt_path = activations_root / (
        sha256_storage_name(activation_id, field_name="activation_id") + ".json"
    )
    if receipt_path.exists():
        existing = _read_utf8(receipt_path, root=root)
        if existing != receipt_payload:
            raise GovernedAnalyticalAuthorityActivationError(
                "Existing immutable activation receipt conflicts with this transition."
            )
    else:
        staging_receipt = activations_root / f".staging-{uuid4().hex}.json"
        _write_new_file(staging_receipt, receipt_payload)
        try:
            os.rename(staging_receipt, receipt_path)
        except OSError as exc:
            raise GovernedAnalyticalAuthorityActivationError(
                "Activation receipt publication failed; preserve staging state."
            ) from exc

    # Pointer replacement is intentionally the only mutable lifecycle write.
    temp_pointer = case_root / f".active-{uuid4().hex}.tmp"
    _write_new_file(temp_pointer, pointer_payload)
    try:
        os.replace(temp_pointer, case_root / "active.json")
    except OSError as exc:
        raise GovernedAnalyticalAuthorityActivationError(
            "Atomic active-pointer replacement failed; no automatic rollback is permitted."
        ) from exc

    observed = _load_current_pointer(case_id=canonical_case_id, root=root)
    if observed is None or observed[0] != pointer:
        raise GovernedAnalyticalAuthorityActivationError(
            "Post-activation active-pointer validation failed; preserve exact state."
        )
    return pointer


__all__ = [
    "GovernedAnalyticalAuthorityActivationError",
    "activate_governed_analytical_authority",
]
