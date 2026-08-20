"""Fail-closed publication for canonical Finance report projections.

F7C-P2 publishes one canonical FinanceReportProjection into the governed
workspace slot expected by the read-only F7C-P1 provider. Publication is
create-if-absent: identical republication is idempotent; a different existing
active projection is a conflict and is never overwritten here.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

from finance_reporting.models import FinanceReportProjection
from finance_reporting.serialization import dumps_finance_report_projection


class FinanceReportProjectionPublicationError(RuntimeError):
    """Raised when governed Finance projection publication cannot complete safely."""


def _canonical_workspace_id(workspace_id: str) -> str:
    try:
        return str(UUID(str(workspace_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinanceReportProjectionPublicationError(
            "Finance workspace_id must be a canonical UUID identity."
        ) from exc


def _lstat_or_none(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FinanceReportProjectionPublicationError(
            f"Unable to inspect governed Finance publication path: {path.name}"
        ) from exc


def _is_reparse_stat(value) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _require_plain_directory(path: Path) -> None:
    value = _lstat_or_none(path)
    if value is None:
        raise FinanceReportProjectionPublicationError(
            f"Required governed Finance directory does not exist: {path.name}"
        )
    if stat.S_ISLNK(value.st_mode) or _is_reparse_stat(value) or not stat.S_ISDIR(
        value.st_mode
    ):
        raise FinanceReportProjectionPublicationError(
            f"Governed Finance directory is not a plain directory: {path.name}"
        )


def _ensure_plain_directory(path: Path) -> None:
    value = _lstat_or_none(path)
    if value is None:
        try:
            path.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise FinanceReportProjectionPublicationError(
                f"Unable to create governed Finance directory: {path.name}"
            ) from exc
    _require_plain_directory(path)


def _require_plain_regular_file(path: Path) -> None:
    value = _lstat_or_none(path)
    if value is None:
        raise FinanceReportProjectionPublicationError(
            f"Governed Finance projection disappeared during publication: {path.name}"
        )
    if stat.S_ISLNK(value.st_mode) or _is_reparse_stat(value) or not stat.S_ISREG(
        value.st_mode
    ):
        raise FinanceReportProjectionPublicationError(
            f"Governed Finance projection is not a plain regular file: {path.name}"
        )


def _read_existing_active(path: Path) -> bytes | None:
    value = _lstat_or_none(path)
    if value is None:
        return None
    if stat.S_ISLNK(value.st_mode) or _is_reparse_stat(value) or not stat.S_ISREG(
        value.st_mode
    ):
        raise FinanceReportProjectionPublicationError(
            "Existing Finance active projection is not a plain regular file."
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FinanceReportProjectionPublicationError(
            "Unable to read existing Finance active projection."
        ) from exc


def _write_staging_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise FinanceReportProjectionPublicationError(
            "Finance publication staging path unexpectedly already exists."
        ) from exc
    except OSError as exc:
        raise FinanceReportProjectionPublicationError(
            "Unable to write Finance publication staging file."
        ) from exc
    _require_plain_regular_file(path)


def publish_finance_report_projection(
    projection: FinanceReportProjection,
    *,
    root: Path | None = None,
) -> Path:
    """Publish one canonical Finance projection without overwriting active state.

    ``root`` is the exact ``report_projections/finance`` directory. It exists
    primarily for disposable validation; production callers should omit it.
    """

    workspace_id = _canonical_workspace_id(projection.header.workspace_id)

    try:
        payload = dumps_finance_report_projection(projection).encode("utf-8")
    except Exception as exc:
        raise FinanceReportProjectionPublicationError(
            "Finance report projection is not valid canonical F7A state."
        ) from exc

    if projection.header.workspace_id != workspace_id:
        raise FinanceReportProjectionPublicationError(
            "Finance projection workspace identity is not canonical."
        )

    if root is None:
        project_root = Path(__file__).resolve().parent.parent
        report_root = project_root / "report_projections"
        _require_plain_directory(report_root)
        finance_root = report_root / "finance"
    else:
        finance_root = Path(root)
        _require_plain_directory(finance_root.parent)

    _ensure_plain_directory(finance_root)
    workspace_root = finance_root / workspace_id
    _ensure_plain_directory(workspace_root)

    active_path = workspace_root / "active.json"
    existing = _read_existing_active(active_path)
    if existing is not None:
        if existing == payload:
            return active_path
        raise FinanceReportProjectionPublicationError(
            "Existing Finance active projection conflicts with this publication."
        )

    staging = workspace_root / f".active-{uuid4().hex}.tmp"
    _write_staging_file(staging, payload)

    try:
        try:
            os.link(staging, active_path)
        except FileExistsError:
            concurrent = _read_existing_active(active_path)
            if concurrent == payload:
                return active_path
            raise FinanceReportProjectionPublicationError(
                "Concurrent Finance active projection conflicts with this publication."
            )
        except OSError as exc:
            raise FinanceReportProjectionPublicationError(
                "Atomic create-if-absent Finance publication is unavailable."
            ) from exc

        _require_plain_regular_file(active_path)
        try:
            published = active_path.read_bytes()
        except OSError as exc:
            raise FinanceReportProjectionPublicationError(
                "Unable to verify published Finance active projection."
            ) from exc
        if published != payload:
            raise FinanceReportProjectionPublicationError(
                "Published Finance active projection bytes do not match canonical input."
            )
        return active_path
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError as exc:
            raise FinanceReportProjectionPublicationError(
                "Unable to remove this invocation's Finance staging file."
            ) from exc


__all__ = [
    "FinanceReportProjectionPublicationError",
    "publish_finance_report_projection",
]
