"""PFCR3 M2 disposable offline-cutover execution mechanics.

This module deliberately cannot operate on the LegalRAG Pro production
trees.  It exercises only directory handoff and rollback mechanics inside
an explicitly marked descendant of the operating-system temporary directory.

It does not import or open Chroma.  It does not provide a production
activation capability.  A later separately authorised milestone would be
required before production cutover could exist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import tempfile

from source_evidence.offline_cutover import OfflineCutoverPlan
from source_evidence.production_shadow_build import (
    _build_tree_manifest,
    _is_link_like,
)


_DISPOSABLE_MARKER_NAME = ".legalrag-pfcr3-disposable"
_DISPOSABLE_MARKER_BYTES = b"PFCR3-DISPOSABLE-WORKSPACE\n"


class DisposableOfflineCutoverBlocker(StrEnum):
    """Fail-closed blockers for PFCR3 M2 disposable execution."""

    PLAN_INVALID = "plan_invalid"
    WORKSPACE_UNSAFE = "workspace_unsafe"
    WORKSPACE_NOT_DISPOSABLE = "workspace_not_disposable"
    WORKSPACE_MARKER_INVALID = "workspace_marker_invalid"
    PROTECTED_PATH = "protected_path"
    PATH_RELATION_INVALID = "path_relation_invalid"
    PATH_LINK_LIKE = "path_link_like"
    ACTIVE_DB_MISSING = "active_db_missing"
    SHADOW_DB_MISSING = "shadow_db_missing"
    RETAINED_SLOT_OCCUPIED = "retained_slot_occupied"
    ACTIVE_TREE_MISMATCH = "active_tree_mismatch"
    SHADOW_TREE_MISMATCH = "shadow_tree_mismatch"
    RETAIN_FAILED = "retain_failed"
    ACTIVATE_FAILED = "activate_failed"
    POST_VERIFY_FAILED = "post_verify_failed"
    ROLLBACK_FAILED = "rollback_failed"


class DisposableOfflineCutoverError(RuntimeError):
    """Raised when disposable PFCR3 mechanics fail closed."""

    def __init__(
        self,
        blocker: DisposableOfflineCutoverBlocker,
        *,
        detail: str | None = None,
    ) -> None:
        self.blocker = blocker
        self.detail = detail

        message = blocker.value

        if detail:
            message = f"{message}: {detail}"

        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DisposableOfflineCutoverResult:
    """Verified result of one disposable PFCR3 directory handoff."""

    active_db_root: str
    retained_active_root: str
    activated_tree_sha256: str
    retained_tree_sha256: str
    original_shadow_path_absent: bool


def _project_root() -> Path:
    """Return the LegalRAG Pro repository root."""

    return Path(__file__).resolve().parents[2]


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether ``path`` is strictly below ``parent``."""

    try:
        relative = path.relative_to(parent)
    except ValueError:
        return False

    return bool(relative.parts)


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether two paths are equal or ancestor-related."""

    if left == right:
        return True

    return (
        _is_relative_to(left, right)
        or _is_relative_to(right, left)
    )


def _protected_roots() -> tuple[Path, ...]:
    """Return every production tree prohibited to PFCR3 M2."""

    project = _project_root().resolve(strict=False)

    return tuple(
        (project / relative).resolve(strict=False)
        for relative in (
            "db",
            "docs",
            "source_evidence_store",
            "report_projections",
        )
    )


def _validate_workspace(raw_workspace: Path) -> Path:
    """Validate the explicit disposable workspace boundary."""

    raw_workspace = Path(raw_workspace).expanduser()

    if (
        not raw_workspace.exists()
        or _is_link_like(raw_workspace)
        or not raw_workspace.is_dir()
    ):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.WORKSPACE_UNSAFE
        )

    workspace = raw_workspace.resolve(strict=True)

    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)

    if (
        workspace == temp_root
        or not _is_relative_to(workspace, temp_root)
    ):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.WORKSPACE_NOT_DISPOSABLE
        )

    for protected in _protected_roots():
        if _paths_overlap(workspace, protected):
            raise DisposableOfflineCutoverError(
                DisposableOfflineCutoverBlocker.PROTECTED_PATH
            )

    marker = workspace / _DISPOSABLE_MARKER_NAME

    if (
        not marker.exists()
        or _is_link_like(marker)
        or not marker.is_file()
    ):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.WORKSPACE_MARKER_INVALID
        )

    try:
        marker_bytes = marker.read_bytes()
    except OSError as exc:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.WORKSPACE_MARKER_INVALID
        ) from exc

    if marker_bytes != _DISPOSABLE_MARKER_BYTES:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.WORKSPACE_MARKER_INVALID
        )

    return workspace


def _resolve_workspace_slot(
    *,
    workspace: Path,
    raw_path: Path,
) -> Path:
    """Resolve one direct-child workspace slot without following unsafe roots."""

    raw = Path(raw_path).expanduser()

    if raw.exists() and _is_link_like(raw):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.PATH_LINK_LIKE
        )

    resolved = raw.resolve(strict=False)

    if resolved.parent != workspace:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.PATH_RELATION_INVALID
        )

    for protected in _protected_roots():
        if _paths_overlap(resolved, protected):
            raise DisposableOfflineCutoverError(
                DisposableOfflineCutoverBlocker.PROTECTED_PATH
            )

    return resolved


def _tree_sha(path: Path) -> str:
    """Return the frozen deterministic governed tree identity."""

    return _build_tree_manifest(
        path,
        require_exists=True,
    ).tree_sha256


def _rollback_after_activation(
    *,
    active: Path,
    shadow: Path,
    retained: Path,
) -> None:
    """Restore the disposable pre-cutover directory layout."""

    try:
        if active.exists():
            os.replace(active, shadow)

        if retained.exists():
            os.replace(retained, active)
    except OSError as exc:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.ROLLBACK_FAILED
        ) from exc


def execute_disposable_offline_cutover(
    *,
    plan: OfflineCutoverPlan,
    workspace_root: Path,
    active_db_root: Path,
    shadow_db_root: Path,
    retained_active_root: Path,
) -> DisposableOfflineCutoverResult:
    """Exercise PFCR3 handoff mechanics only inside a disposable workspace.

    The algorithm is:

    1. Verify the existing disposable active tree against the frozen plan.
    2. Verify the disposable shadow tree against the frozen plan.
    3. Rename the old active tree into a retained slot.
    4. Rename the shadow tree into the active slot.
    5. Verify both resulting tree identities.
    6. Keep the former active tree.  It is never deleted.

    If step 4 or post-verification fails, the function attempts to restore the
    original disposable directory layout.

    This function rejects the real LegalRAG Pro production trees and requires
    every mutable slot to be a direct child of a marked OS-temp workspace.
    """

    if not isinstance(plan, OfflineCutoverPlan):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.PLAN_INVALID
        )

    workspace = _validate_workspace(Path(workspace_root))

    active = _resolve_workspace_slot(
        workspace=workspace,
        raw_path=Path(active_db_root),
    )

    shadow = _resolve_workspace_slot(
        workspace=workspace,
        raw_path=Path(shadow_db_root),
    )

    retained = _resolve_workspace_slot(
        workspace=workspace,
        raw_path=Path(retained_active_root),
    )

    if len({active, shadow, retained}) != 3:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.PATH_RELATION_INVALID
        )

    if (
        not active.exists()
        or _is_link_like(active)
        or not active.is_dir()
    ):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.ACTIVE_DB_MISSING
        )

    if (
        not shadow.exists()
        or _is_link_like(shadow)
        or not shadow.is_dir()
    ):
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.SHADOW_DB_MISSING
        )

    if retained.exists() or retained.is_symlink():
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.RETAINED_SLOT_OCCUPIED
        )

    active_pre_sha = _tree_sha(active)

    if active_pre_sha != plan.active_db_pre_tree_sha256:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.ACTIVE_TREE_MISMATCH
        )

    shadow_pre_sha = _tree_sha(shadow)

    if shadow_pre_sha != plan.shadow_tree_sha256:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.SHADOW_TREE_MISMATCH
        )

    try:
        os.replace(active, retained)
    except OSError as exc:
        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.RETAIN_FAILED
        ) from exc

    try:
        os.replace(shadow, active)
    except OSError as exc:
        try:
            os.replace(retained, active)
        except OSError as rollback_exc:
            raise DisposableOfflineCutoverError(
                DisposableOfflineCutoverBlocker.ROLLBACK_FAILED
            ) from rollback_exc

        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.ACTIVATE_FAILED
        ) from exc

    try:
        active_post_sha = _tree_sha(active)
        retained_post_sha = _tree_sha(retained)
    except Exception as exc:
        _rollback_after_activation(
            active=active,
            shadow=shadow,
            retained=retained,
        )

        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.POST_VERIFY_FAILED
        ) from exc

    if (
        active_post_sha != plan.shadow_tree_sha256
        or retained_post_sha != plan.active_db_pre_tree_sha256
    ):
        _rollback_after_activation(
            active=active,
            shadow=shadow,
            retained=retained,
        )

        raise DisposableOfflineCutoverError(
            DisposableOfflineCutoverBlocker.POST_VERIFY_FAILED
        )

    return DisposableOfflineCutoverResult(
        active_db_root=str(active),
        retained_active_root=str(retained),
        activated_tree_sha256=active_post_sha,
        retained_tree_sha256=retained_post_sha,
        original_shadow_path_absent=not shadow.exists(),
    )


__all__ = [
    "DisposableOfflineCutoverBlocker",
    "DisposableOfflineCutoverError",
    "DisposableOfflineCutoverResult",
    "execute_disposable_offline_cutover",
]
