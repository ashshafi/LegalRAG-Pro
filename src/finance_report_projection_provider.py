"""Read-only provider for one governed active Finance F7A report projection."""

from __future__ import annotations

from pathlib import Path
import stat
from uuid import UUID

from finance_reporting import (
    FinanceReportProjection,
    dumps_finance_report_projection,
    loads_finance_report_projection,
    validate_finance_report_projection,
)


class FinanceReportProjectionProviderError(RuntimeError):
    """Raised when an active Finance report projection cannot be trusted."""


def _canonical_workspace_id(workspace_id: str) -> str:
    try:
        return str(UUID(str(workspace_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinanceReportProjectionProviderError(
            "Invalid workspace ID for Finance report projection lookup."
        ) from exc


def _active_projection_path(workspace_id: str) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    governed_root = (project_root / "report_projections" / "finance").resolve(
        strict=False
    )
    candidate = governed_root / workspace_id / "active.json"

    try:
        resolved_candidate = candidate.resolve(strict=False)
        resolved_candidate.relative_to(governed_root)
    except (OSError, ValueError) as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection path escapes the governed projection root."
        ) from exc

    return candidate


def load_active_finance_report_projection(
    workspace_id: str,
) -> FinanceReportProjection | None:
    """Load the exact canonical active Finance projection for one workspace.

    Absence of the exact governed ``active.json`` slot is the only ``None``
    state. Any present but untrusted, malformed, non-canonical, cross-workspace,
    or filesystem-invalid state fails closed.
    """

    canonical_workspace_id = _canonical_workspace_id(workspace_id)
    active_path = _active_projection_path(canonical_workspace_id)

    try:
        file_stat = active_path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection could not be inspected."
        ) from exc

    if stat.S_ISLNK(file_stat.st_mode):
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection must not be a symlink."
        )
    if not stat.S_ISREG(file_stat.st_mode):
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection is not a regular file."
        )

    try:
        stored_bytes = active_path.read_bytes()
    except OSError as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection could not be read."
        ) from exc

    try:
        stored_text = stored_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection is not valid UTF-8."
        ) from exc

    try:
        projection = loads_finance_report_projection(stored_text)
        validate_finance_report_projection(projection)
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection could not be deserialized and validated."
        ) from exc

    try:
        canonical_bytes = dumps_finance_report_projection(projection).encode("utf-8")
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection could not be reserialized canonically."
        ) from exc

    if canonical_bytes != stored_bytes:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection is not exact canonical F7A JSON."
        )

    if projection.header.workspace_id != canonical_workspace_id:
        raise FinanceReportProjectionProviderError(
            "The active Finance report projection does not belong to the requested workspace."
        )

    return projection


__all__ = [
    "FinanceReportProjectionProviderError",
    "load_active_finance_report_projection",
]
