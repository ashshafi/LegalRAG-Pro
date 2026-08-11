"""Immutable publication of already-created governed analytical authority bundles."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from uuid import uuid4

from case_analysis.m2.matrix_serialization import dumps_case_matrices
from governed_evidence_analysis.serialization import dumps_governed_evidential_analysis
from governed_issue_evidence.serialization import dumps_governed_issue_evidence_map
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from .identity import require_canonical_case_id, sha256_storage_name
from .models import GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME, GovernedAnalyticalAuthorityManifest
from .serialization import (
    dumps_governed_analytical_authority_manifest,
    dumps_structured_legal_analysis_results,
)
from .validation import build_governed_analytical_authority_manifest


class GovernedAnalyticalAuthorityPublicationError(RuntimeError):
    """Raised when immutable publication cannot complete without mutation/repair."""


def _authority_root() -> Path:
    return Path(__file__).resolve().parents[2] / GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _require_plain_directory(path: Path) -> None:
    if path.is_symlink() or _is_reparse(path) or not path.is_dir():
        raise GovernedAnalyticalAuthorityPublicationError(
            f"Governed publication directory is not a plain directory: {path}"
        )


def _ensure_plain_directory(path: Path) -> None:
    try:
        path.mkdir(exist_ok=True)
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            f"Unable to create governed publication directory: {path}"
        ) from exc
    try:
        _require_plain_directory(path)
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            f"Unable to inspect governed publication directory: {path}"
        ) from exc


def _write_new_file(path: Path, payload: str) -> None:
    data = payload.encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            f"Unable to write immutable governed authority staging file: {path.name}"
        ) from exc


def _exact_payloads(
    *,
    results: tuple[StructuredLegalAnalysisResult, ...],
    case_matrices,
    governed_issue_evidence_map,
    governed_evidential_analysis,
    manifest: GovernedAnalyticalAuthorityManifest,
) -> dict[str, str]:
    return {
        "manifest.json": dumps_governed_analytical_authority_manifest(manifest),
        "structured_legal_analysis_results.json": dumps_structured_legal_analysis_results(results),
        "case_matrices.json": dumps_case_matrices(case_matrices),
        "governed_issue_evidence_map.json": dumps_governed_issue_evidence_map(
            governed_issue_evidence_map
        ),
        "governed_evidential_analysis.json": dumps_governed_evidential_analysis(
            governed_evidential_analysis,
            governed_issue_evidence_map,
        ),
    }


def _verify_exact_directory(path: Path, expected: dict[str, str]) -> None:
    try:
        _require_plain_directory(path)
        names = {item.name for item in path.iterdir()}
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            "Unable to inspect immutable governed authority directory."
        ) from exc
    if names != set(expected):
        raise GovernedAnalyticalAuthorityPublicationError(
            f"Immutable authority file set mismatch; observed={sorted(names)}."
        )
    for name, payload in expected.items():
        item = path / name
        try:
            if item.is_symlink() or _is_reparse(item) or not item.is_file():
                raise GovernedAnalyticalAuthorityPublicationError(
                    f"Immutable authority member is not a plain regular file: {name}"
                )
            if item.read_bytes() != payload.encode("utf-8"):
                raise GovernedAnalyticalAuthorityPublicationError(
                    f"Immutable authority member differs from canonical bytes: {name}"
                )
        except OSError as exc:
            raise GovernedAnalyticalAuthorityPublicationError(
                f"Unable to verify immutable authority member: {name}"
            ) from exc


def publish_governed_analytical_authority(
    *,
    structured_legal_analysis_results,
    case_matrices,
    governed_issue_evidence_map,
    governed_evidential_analysis,
) -> GovernedAnalyticalAuthorityManifest:
    """Publish one complete supplied authority object without activating it.

    The function never retrieves, maps, assesses, renders, selects issues, or builds
    a substitute analytical component.  Validation must succeed before filesystem
    publication begins.
    """

    results = tuple(structured_legal_analysis_results)
    try:
        manifest = build_governed_analytical_authority_manifest(
            structured_legal_analysis_results=results,
            case_matrices=case_matrices,
            governed_issue_evidence_map=governed_issue_evidence_map,
            governed_evidential_analysis=governed_evidential_analysis,
        )
        case_id = require_canonical_case_id(manifest.case_id)
        storage_name = sha256_storage_name(manifest.authority_id, field_name="authority_id")
    except (TypeError, ValueError) as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            "Supplied analytical bundle is not publication-valid."
        ) from exc

    payloads = _exact_payloads(
        results=results,
        case_matrices=case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
        manifest=manifest,
    )

    root = _authority_root()
    case_root = root / case_id
    objects_root = case_root / "objects"
    for directory in (root, case_root, objects_root):
        _ensure_plain_directory(directory)

    final_root = objects_root / storage_name
    if final_root.exists():
        _verify_exact_directory(final_root, payloads)
        return manifest

    staging_root = objects_root / f".staging-{storage_name}-{uuid4().hex}"
    try:
        staging_root.mkdir()
        _require_plain_directory(staging_root)
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            "Unable to create immutable authority staging directory."
        ) from exc

    # A failure deliberately leaves the staging state intact for reconciliation.
    for name in sorted(payloads):
        _write_new_file(staging_root / name, payloads[name])
    _verify_exact_directory(staging_root, payloads)

    try:
        os.rename(staging_root, final_root)
    except OSError as exc:
        raise GovernedAnalyticalAuthorityPublicationError(
            "Immutable authority publication rename failed; preserve staging state."
        ) from exc

    _verify_exact_directory(final_root, payloads)
    return manifest


__all__ = [
    "GovernedAnalyticalAuthorityPublicationError",
    "publish_governed_analytical_authority",
]
