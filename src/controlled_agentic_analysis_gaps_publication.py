"""Immutable publication for CAA2 evidence-gap / unsupported-finding runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from uuid import uuid4
from typing import Any, Callable

from controlled_agentic_analysis import (
    assert_active_authority_unchanged,
    dumps_frozen_inspection_universe,
    validate_frozen_inspection_universe,
)
from controlled_agentic_analysis_gaps import (
    CAA2AnalysisResult,
    candidate_to_dict,
    observation_to_dict,
)

CAA2_PUBLICATION_ROOT = "controlled_agentic_analysis_gap_runs"
CAA2_PUBLICATION_MANIFEST_SCHEMA = "controlled-agentic-evidence-gap-publication/v1"


class CAA2PublicationError(RuntimeError):
    """Raised when CAA2 immutable publication cannot complete safely."""


@dataclass(frozen=True, slots=True)
class PublishedCAA2Run:
    run_root: Path
    manifest_path: Path
    run_path: Path
    candidates_path: Path
    observation_paths: tuple[Path, ...]


def _fail(message: str) -> None:
    raise CAA2PublicationError(message)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _storage_name(identity: str) -> str:
    if not isinstance(identity, str) or len(identity) != 71 or not identity.startswith("sha256:"):
        _fail("CAA2 storage identity must be canonical sha256.")
    value = identity[7:]
    if any(ch not in "0123456789abcdef" for ch in value):
        _fail("CAA2 storage identity must use lowercase hexadecimal.")
    return value


def _root(value: Path | None) -> Path:
    if value is None:
        return Path(__file__).resolve().parents[1] / CAA2_PUBLICATION_ROOT
    result = Path(value)
    if not result.is_absolute():
        _fail("CAA2 publication root override must be absolute.")
    return result


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _require_plain_directory(path: Path) -> None:
    if path.is_symlink() or _is_reparse(path) or not path.is_dir():
        _fail(f"CAA2 publication directory is not a plain directory: {path}")


def _ensure_plain_directory(path: Path) -> None:
    if path.exists():
        _require_plain_directory(path)
        return
    parent = path.parent
    if parent != path:
        _ensure_plain_directory(parent)
    try:
        path.mkdir(exist_ok=False)
    except FileExistsError:
        pass
    except OSError as exc:
        raise CAA2PublicationError(f"Unable to create CAA2 publication directory: {path}") from exc
    _require_plain_directory(path)


def _write_exact_new(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.is_symlink() or _is_reparse(path) or not path.is_file():
            _fail(f"CAA2 immutable target is not a plain file: {path}")
        if path.read_bytes() != payload:
            _fail(f"Conflicting immutable CAA2 publication exists: {path}")
        return
    staging = path.parent / f".staging-{path.name}-{uuid4().hex}"
    try:
        with staging.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(staging, path)
        except OSError:
            if path.exists() and path.is_file() and not path.is_symlink() and path.read_bytes() == payload:
                try:
                    staging.unlink()
                except FileNotFoundError:
                    pass
            else:
                raise
        if path.read_bytes() != payload:
            _fail(f"CAA2 immutable publication bytes differ after write: {path}")
    finally:
        if staging.exists():
            try:
                staging.unlink()
            except OSError:
                pass


def publish_caa2_analysis(
    *,
    result: CAA2AnalysisResult,
    root: Path | None = None,
    active_authority_loader: Callable[[str], Any] | None = None,
) -> PublishedCAA2Run:
    if not isinstance(result, CAA2AnalysisResult):
        _fail("result must be CAA2AnalysisResult.")
    validate_frozen_inspection_universe(result.run)

    if active_authority_loader is None:
        from governed_analytical_authority.provider import load_active_governed_analytical_authority
        active_authority_loader = load_active_governed_analytical_authority

    active = active_authority_loader(result.run.case_id)
    if active is None:
        _fail("No active governed authority exists at CAA2 publication boundary.")
    manifest = getattr(active, "manifest", None)
    try:
        assert_active_authority_unchanged(
            run=result.run,
            current_authority_id=getattr(manifest, "authority_id", None),
        )
    except Exception as exc:
        raise CAA2PublicationError(str(exc)) from exc

    candidate_ids = tuple(candidate.candidate_id for candidate in result.candidates)
    observation_ids = tuple(observation.observation_id for observation in result.observations)
    if len(candidate_ids) != len(set(candidate_ids)):
        _fail("CAA2 result contains duplicate candidate identities.")
    if len(observation_ids) != len(set(observation_ids)):
        _fail("CAA2 result contains duplicate observation identities.")

    publication_root = _root(root)
    run_root = publication_root / result.run.case_id / _storage_name(result.run.analysis_run_id)
    _ensure_plain_directory(run_root)
    observation_root = run_root / "observations"
    _ensure_plain_directory(observation_root)

    run_path = run_root / "run.json"
    candidates_path = run_root / "candidates.json"
    manifest_path = run_root / "manifest.json"

    run_payload = dumps_frozen_inspection_universe(result.run).encode("utf-8")
    candidates_payload = _canonical_json(
        [candidate_to_dict(candidate) for candidate in result.candidates]
    ).encode("utf-8")

    observation_paths = tuple(
        observation_root / (_storage_name(observation.observation_id) + ".json")
        for observation in sorted(result.observations, key=lambda item: item.observation_id)
    )
    manifest_payload = _canonical_json(
        {
            "schema_version": CAA2_PUBLICATION_MANIFEST_SCHEMA,
            "case_id": result.run.case_id,
            "active_authority_id": result.run.active_authority_id,
            "analysis_run_id": result.run.analysis_run_id,
            "candidate_ids": list(candidate_ids),
            "observation_ids": list(observation_ids),
        }
    ).encode("utf-8")

    _write_exact_new(run_path, run_payload)
    _write_exact_new(candidates_path, candidates_payload)
    for observation, path in zip(
        sorted(result.observations, key=lambda item: item.observation_id),
        observation_paths,
    ):
        _write_exact_new(path, _canonical_json(observation_to_dict(observation)).encode("utf-8"))
    _write_exact_new(manifest_path, manifest_payload)

    expected = {run_path, candidates_path, manifest_path, *observation_paths}
    actual = {
        item
        for item in run_root.rglob("*")
        if item.is_file() and not item.name.startswith(".staging-")
    }
    if actual != expected:
        _fail("CAA2 immutable run contains unexpected files.")

    residue = tuple(run_root.rglob(".staging-*"))
    if residue:
        _fail("CAA2 staging residue remains.")

    return PublishedCAA2Run(
        run_root=run_root,
        manifest_path=manifest_path,
        run_path=run_path,
        candidates_path=candidates_path,
        observation_paths=observation_paths,
    )


__all__ = [
    "CAA2_PUBLICATION_ROOT",
    "CAA2_PUBLICATION_MANIFEST_SCHEMA",
    "CAA2PublicationError",
    "PublishedCAA2Run",
    "publish_caa2_analysis",
]
