"""Read-only catalog of already-published governed Finance workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import stat
from uuid import UUID

from finance_report_projection_provider import (
    FinanceReportProjectionProviderError,
    load_active_finance_report_projection,
)


class FinanceWorkspaceCatalogError(RuntimeError):
    """Raised when the governed Finance workspace catalog cannot be trusted."""


@dataclass(frozen=True, slots=True)
class PublishedFinanceWorkspace:
    workspace_id: str
    report_projection_id: str
    as_of: datetime
    provider_id: str
    dataset_id: str
    dataset_version: str


def _catalog_root() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    return project_root / "report_projections" / "finance"


def _is_reparse(value) -> bool:
    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    marker = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & marker)


def _require_plain_directory(path: Path) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise FinanceWorkspaceCatalogError(
            f"Finance workspace catalog path could not be inspected: {path}"
        ) from exc
    if stat.S_ISLNK(value.st_mode) or _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise FinanceWorkspaceCatalogError(
            f"Finance workspace catalog path must be a plain directory: {path}"
        )


def _canonical_workspace_id(value: str) -> str:
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinanceWorkspaceCatalogError(
            f"Finance workspace catalog contains a non-UUID directory: {value!r}."
        ) from exc
    if canonical != value:
        raise FinanceWorkspaceCatalogError(
            f"Finance workspace directory is not canonical UUID form: {value!r}."
        )
    return canonical


def load_published_finance_workspace_catalog() -> tuple[PublishedFinanceWorkspace, ...]:
    """Enumerate only trusted active Finance projections, without creating state."""

    root = _catalog_root()
    if not root.exists():
        return ()

    _require_plain_directory(root)

    entries: list[PublishedFinanceWorkspace] = []
    try:
        children = tuple(sorted(root.iterdir(), key=lambda candidate: candidate.name))
    except OSError as exc:
        raise FinanceWorkspaceCatalogError(
            "Finance workspace catalog root could not be enumerated."
        ) from exc

    for child in children:
        _require_plain_directory(child)
        workspace_id = _canonical_workspace_id(child.name)

        try:
            projection = load_active_finance_report_projection(workspace_id)
        except FinanceReportProjectionProviderError as exc:
            raise FinanceWorkspaceCatalogError(
                f"Published Finance workspace {workspace_id} failed trusted projection loading."
            ) from exc

        if projection is None:
            continue
        if projection.header.workspace_id != workspace_id:
            raise FinanceWorkspaceCatalogError(
                "Published Finance projection workspace identity differs from its catalog directory."
            )

        entries.append(
            PublishedFinanceWorkspace(
                workspace_id=workspace_id,
                report_projection_id=projection.report_projection_id,
                as_of=projection.header.as_of,
                provider_id=projection.header.provider_id,
                dataset_id=projection.header.dataset_id,
                dataset_version=projection.header.dataset_version,
            )
        )

    return tuple(entries)


__all__ = [
    "FinanceWorkspaceCatalogError",
    "PublishedFinanceWorkspace",
    "load_published_finance_workspace_catalog",
]
