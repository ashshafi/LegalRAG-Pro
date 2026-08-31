"""Immutable publication of GAR1 governed-authority revision receipts.

This module is intentionally outside the frozen ``governed_analytical_authority``
package.  It publishes only canonical GAR1 revision provenance.  It does not
construct authorities, publish authority bundles, activate pointers, access a
database, or invoke AI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from governed_analytical_authority.identity import canonical_sha256, require_canonical_case_id
from governed_authority_revision import (
    GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION,
    GovernedAuthorityRevisionReceipt,
    dumps_governed_authority_revision_receipt,
)


GOVERNED_AUTHORITY_REVISION_ROOT_NAME = "governed_authority_revisions"


class GovernedAuthorityRevisionPublicationError(RuntimeError):
    """Raised when immutable GAR1 revision-receipt publication fails closed."""


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GovernedAuthorityRevisionPublicationError(
            f"Unable to inspect GAR1 revision publication path: {path.name}"
        ) from exc


def _is_reparse(path: Path, value: os.stat_result) -> bool:
    if bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        return True
    checker = getattr(path, "is_junction", None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except OSError as exc:
        raise GovernedAuthorityRevisionPublicationError(
            f"Unable to inspect GAR1 revision publication junction boundary: {path.name}"
        ) from exc


def _require_plain_directory(path: Path) -> None:
    value = _lstat_or_none(path)
    if (
        value is None
        or not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse(path, value)
    ):
        raise GovernedAuthorityRevisionPublicationError(
            f"GAR1 revision publication directory is not a plain directory: {path}"
        )


def _require_plain_directory_chain(path: Path) -> None:
    chain = tuple(reversed((path, *path.parents)))
    for current in chain:
        _require_plain_directory(current)


def _ensure_plain_directory(path: Path) -> None:
    value = _lstat_or_none(path)
    if value is None:
        _require_plain_directory(path.parent)
        try:
            path.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise GovernedAuthorityRevisionPublicationError(
                f"Unable to create GAR1 revision publication directory: {path}"
            ) from exc
    _require_plain_directory(path)


def _require_plain_regular_file(path: Path) -> None:
    value = _lstat_or_none(path)
    if (
        value is None
        or not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse(path, value)
    ):
        raise GovernedAuthorityRevisionPublicationError(
            f"GAR1 revision publication target is not a plain regular file: {path.name}"
        )


def _canonical_document(receipt: GovernedAuthorityRevisionReceipt) -> tuple[str, bytes]:
    if not isinstance(receipt, GovernedAuthorityRevisionReceipt):
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision publication requires GovernedAuthorityRevisionReceipt."
        )
    if receipt.schema_version != GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt schema version is unsupported."
        )
    try:
        canonical_case_id = require_canonical_case_id(receipt.case_id)
        payload = dumps_governed_authority_revision_receipt(receipt)
        document = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt is not valid canonical publication state."
        ) from exc

    if canonical_case_id != receipt.case_id or not isinstance(document, dict):
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt canonical identity is invalid."
        )

    expected_keys = {
        "schema_version",
        "case_id",
        "predecessor_authority_id",
        "successor_authority_id",
        "proposal_id",
        "approval_event_id",
        "approval_previous_event_id",
        "issue_analysis_id",
        "element_id",
        "previous_status",
        "previous_confidence",
        "new_status",
        "new_confidence",
        "proposal_history_sha256",
        "revision_id",
    }
    if set(document) != expected_keys:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt canonical field set is invalid."
        )

    base = dict(document)
    observed_revision_id = base.pop("revision_id")
    encoded_base = json.dumps(
        base,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_revision_id = canonical_sha256(encoded_base)
    if observed_revision_id != expected_revision_id or receipt.revision_id != expected_revision_id:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt identity does not match its canonical provenance."
        )

    for field_name in (
        "predecessor_authority_id",
        "successor_authority_id",
        "proposal_history_sha256",
        "revision_id",
    ):
        value = str(document[field_name])
        if (
            not value.startswith("sha256:")
            or len(value) != 71
            or any(character not in "0123456789abcdef" for character in value[7:])
        ):
            raise GovernedAuthorityRevisionPublicationError(
                f"GAR1 revision receipt {field_name} is not a canonical sha256 identity."
            )

    if document["predecessor_authority_id"] == document["successor_authority_id"]:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt cannot bind identical predecessor and successor authorities."
        )

    for field_name in (
        "proposal_id",
        "approval_event_id",
        "issue_analysis_id",
        "element_id",
        "previous_status",
        "previous_confidence",
        "new_status",
        "new_confidence",
    ):
        value = document[field_name]
        if not isinstance(value, str) or not value:
            raise GovernedAuthorityRevisionPublicationError(
                f"GAR1 revision receipt {field_name} must be non-empty text."
            )

    return expected_revision_id, payload.encode("utf-8")


def _storage_name(revision_id: str) -> str:
    return revision_id.removeprefix("sha256:")


def _read_existing(path: Path) -> bytes | None:
    value = _lstat_or_none(path)
    if value is None:
        return None
    _require_plain_regular_file(path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise GovernedAuthorityRevisionPublicationError(
            "Unable to read existing GAR1 revision receipt publication."
        ) from exc


def _write_staging(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise GovernedAuthorityRevisionPublicationError(
            "GAR1 revision receipt staging path unexpectedly already exists."
        ) from exc
    except OSError as exc:
        raise GovernedAuthorityRevisionPublicationError(
            "Unable to write GAR1 revision receipt staging file."
        ) from exc
    _require_plain_regular_file(path)


def publish_governed_authority_revision_receipt(
    receipt: GovernedAuthorityRevisionReceipt,
    *,
    root: Path | None = None,
) -> Path:
    """Publish one canonical GAR1 revision receipt without activating anything.

    ``root`` is the exact ``governed_authority_revisions`` directory.  It exists
    for disposable validation; production callers should omit it.

    Publication is create-if-absent.  Byte-identical republication is
    idempotent.  Conflicting existing state fails closed and is never repaired.
    """

    revision_id, payload = _canonical_document(receipt)

    if root is None:
        project_root = Path(__file__).resolve().parent.parent
        revision_root = project_root / GOVERNED_AUTHORITY_REVISION_ROOT_NAME
    else:
        if not isinstance(root, Path):
            raise GovernedAuthorityRevisionPublicationError(
                "root must be pathlib.Path when supplied."
            )
        revision_root = Path(root)
        if not revision_root.is_absolute():
            raise GovernedAuthorityRevisionPublicationError(
                "root must be absolute when supplied."
            )

    _require_plain_directory_chain(revision_root.parent)
    _ensure_plain_directory(revision_root)
    case_root = revision_root / receipt.case_id
    _ensure_plain_directory(case_root)
    receipts_root = case_root / "receipts"
    _ensure_plain_directory(receipts_root)

    target = receipts_root / (_storage_name(revision_id) + ".json")
    existing = _read_existing(target)
    if existing is not None:
        if existing == payload:
            return target
        raise GovernedAuthorityRevisionPublicationError(
            "Existing immutable GAR1 revision receipt conflicts with this publication."
        )

    staging = receipts_root / (
        f".{_storage_name(revision_id)}-{uuid4().hex}.tmp"
    )
    _write_staging(staging, payload)

    try:
        try:
            os.link(staging, target)
        except FileExistsError:
            concurrent = _read_existing(target)
            if concurrent == payload:
                return target
            raise GovernedAuthorityRevisionPublicationError(
                "Concurrent immutable GAR1 revision receipt conflicts with this publication."
            )
        except OSError as exc:
            raise GovernedAuthorityRevisionPublicationError(
                "Atomic create-if-absent GAR1 revision receipt publication is unavailable."
            ) from exc

        _require_plain_regular_file(target)
        try:
            published = target.read_bytes()
        except OSError as exc:
            raise GovernedAuthorityRevisionPublicationError(
                "Unable to verify published GAR1 revision receipt."
            ) from exc
        if published != payload:
            raise GovernedAuthorityRevisionPublicationError(
                "Published GAR1 revision receipt bytes do not match canonical input."
            )
        return target
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError as exc:
            raise GovernedAuthorityRevisionPublicationError(
                "Unable to remove this invocation's GAR1 revision receipt staging file."
            ) from exc


__all__ = [
    "GOVERNED_AUTHORITY_REVISION_ROOT_NAME",
    "GovernedAuthorityRevisionPublicationError",
    "publish_governed_authority_revision_receipt",
]
