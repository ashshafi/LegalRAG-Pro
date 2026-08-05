"""Case-scoped provider for the governed active M5.1 report projection."""

from __future__ import annotations

from pathlib import Path
import stat
from uuid import UUID

from case_reporting.models import CaseReportProjection
from case_reporting.serialization import (
    dumps_case_report_projection,
    loads_case_report_projection,
)
from case_reporting.validation import validate_case_report_projection


class ReportProjectionProviderError(RuntimeError):
    """Raised when the governed active report projection cannot be trusted."""


def _canonical_case_id(case_id: str) -> str:
    try:
        return str(UUID(str(case_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ReportProjectionProviderError(
            "Invalid case ID for report projection lookup."
        ) from exc


def _active_projection_path(case_id: str) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    governed_root = (project_root / "report_projections").resolve(strict=False)
    candidate = governed_root / case_id / "active.json"

    try:
        resolved_candidate = candidate.resolve(strict=False)
        resolved_candidate.relative_to(governed_root)
    except (OSError, ValueError) as exc:
        raise ReportProjectionProviderError(
            "The active report projection path escapes the governed projection root."
        ) from exc

    return candidate


def load_active_case_report_projection(
    case_id: str,
) -> CaseReportProjection | None:
    """Load the exact canonical active projection for one case.

    Absence of the exact governed ``active.json`` slot is the only condition that
    returns ``None``. Every malformed, non-canonical, tampered, cross-case or
    filesystem-invalid state raises :class:`ReportProjectionProviderError`.
    """

    canonical_case_id = _canonical_case_id(case_id)
    active_path = _active_projection_path(canonical_case_id)

    try:
        file_stat = active_path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReportProjectionProviderError(
            "The active report projection could not be inspected."
        ) from exc

    if stat.S_ISLNK(file_stat.st_mode):
        raise ReportProjectionProviderError(
            "The active report projection must not be a symlink."
        )
    if not stat.S_ISREG(file_stat.st_mode):
        raise ReportProjectionProviderError(
            "The active report projection is not a regular file."
        )

    try:
        stored_bytes = active_path.read_bytes()
    except OSError as exc:
        raise ReportProjectionProviderError(
            "The active report projection could not be read."
        ) from exc

    try:
        stored_text = stored_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportProjectionProviderError(
            "The active report projection is not valid UTF-8."
        ) from exc

    try:
        projection = loads_case_report_projection(stored_text)
        validate_case_report_projection(projection)
    except Exception as exc:
        raise ReportProjectionProviderError(
            "The active report projection could not be deserialized and validated."
        ) from exc

    try:
        canonical_bytes = dumps_case_report_projection(projection).encode("utf-8")
    except Exception as exc:
        raise ReportProjectionProviderError(
            "The active report projection could not be reserialized canonically."
        ) from exc

    if stored_bytes != canonical_bytes:
        raise ReportProjectionProviderError(
            "The active report projection is not exact canonical M5.1 JSON."
        )

    if projection.case_header.case_id != canonical_case_id:
        raise ReportProjectionProviderError(
            "The active report projection does not belong to the requested case."
        )

    return projection
