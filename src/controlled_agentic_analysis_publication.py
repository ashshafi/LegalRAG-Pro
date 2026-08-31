"""Append-only immutable persistence for CAA1 runs and observations."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import uuid
from typing import Any, Callable, Iterable

from controlled_agentic_analysis import (
    AgentObservation,
    CAA1Error,
    FrozenInspectionUniverse,
    assert_active_authority_unchanged,
    dumps_agent_observation,
    dumps_frozen_inspection_universe,
    validate_agent_observation,
    validate_frozen_inspection_universe,
)

CAA1_PUBLICATION_ROOT = "controlled_agentic_analysis_runs"


class CAA1PublicationError(RuntimeError):
    """Raised when immutable CAA1 publication cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class PublishedCAA1Run:
    run_path: Path
    observation_paths: tuple[Path, ...]


def _fail(message: str) -> None:
    raise CAA1PublicationError(message)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _storage_hex(identity: str) -> str:
    if not isinstance(identity, str) or not identity.startswith("sha256:") or len(identity) != 71:
        _fail("Identity must be canonical sha256.")
    value = identity[7:]
    if any(ch not in "0123456789abcdef" for ch in value):
        _fail("Identity must use lowercase hexadecimal.")
    return value


def _root(value: Path | None) -> Path:
    result = (_repo_root() / CAA1_PUBLICATION_ROOT) if value is None else Path(value)
    if not result.is_absolute():
        _fail("CAA1 publication root override must be absolute.")
    return result


def _ensure_plain_directory(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            _fail(f"CAA1 publication path is not a plain directory: {path}")
        return
    parent = path.parent
    if parent != path:
        _ensure_plain_directory(parent)
    path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _fail(f"CAA1 publication directory is unsafe: {path}")


def _publish_exact(path: Path, payload: bytes) -> None:
    _ensure_plain_directory(path.parent)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            _fail(f"CAA1 publication target is not a plain file: {path}")
        if path.read_bytes() != payload:
            _fail(f"Conflicting immutable CAA1 publication exists: {path}")
        return

    staging = path.parent / f".staging-{uuid.uuid4().hex}.tmp"
    try:
        with staging.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staging, path)
        except FileExistsError:
            if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
                _fail(f"Conflicting concurrent CAA1 publication exists: {path}")
        if path.read_bytes() != payload:
            _fail(f"CAA1 publication bytes failed final verification: {path}")
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def publish_caa1_run(
    *,
    run: FrozenInspectionUniverse,
    observations: Iterable[AgentObservation],
    root: Path | None = None,
    active_authority_loader: Callable[[str], Any] | None = None,
) -> PublishedCAA1Run:
    """Publish one frozen CAA1 run and immutable observation set.

    The active authority is rechecked immediately before publication. If it has
    drifted from the authority frozen into the run, publication fails closed.
    """
    try:
        validate_frozen_inspection_universe(run)
        observation_tuple = tuple(observations)
        ids: set[str] = set()
        for observation in observation_tuple:
            validate_agent_observation(run=run, observation=observation)
            if observation.observation_id in ids:
                raise CAA1Error("Duplicate observation identity.")
            ids.add(observation.observation_id)
    except CAA1Error as exc:
        raise CAA1PublicationError(str(exc)) from exc

    if active_authority_loader is None:
        from governed_analytical_authority.provider import load_active_governed_analytical_authority
        active_authority_loader = load_active_governed_analytical_authority

    active = active_authority_loader(run.case_id)
    if active is None:
        _fail("No active governed authority exists at CAA1 publication boundary.")
    authority_id = getattr(getattr(active, "manifest", None), "authority_id", None)
    try:
        assert_active_authority_unchanged(run=run, current_authority_id=authority_id)
    except CAA1Error as exc:
        raise CAA1PublicationError(str(exc)) from exc

    publication_root = _root(root)
    run_root = publication_root / run.case_id / _storage_hex(run.analysis_run_id)
    run_path = run_root / "run.json"
    observation_root = run_root / "observations"

    run_payload = dumps_frozen_inspection_universe(run).encode("utf-8")
    _publish_exact(run_path, run_payload)

    paths: list[Path] = []
    for observation in sorted(observation_tuple, key=lambda value: value.observation_id):
        target = observation_root / (_storage_hex(observation.observation_id) + ".json")
        _publish_exact(target, dumps_agent_observation(observation).encode("utf-8"))
        paths.append(target)

    expected = {run_path, *paths}
    actual = {
        item
        for item in run_root.rglob("*")
        if item.is_file() and not item.name.startswith(".staging-")
    }
    if actual != expected:
        _fail("CAA1 run publication contains unexpected files.")

    staging = tuple(item for item in run_root.rglob(".staging-*") if item.exists())
    if staging:
        _fail("CAA1 staging residue remains.")

    return PublishedCAA1Run(run_path=run_path, observation_paths=tuple(paths))


__all__ = [
    "CAA1PublicationError",
    "CAA1_PUBLICATION_ROOT",
    "PublishedCAA1Run",
    "publish_caa1_run",
]
