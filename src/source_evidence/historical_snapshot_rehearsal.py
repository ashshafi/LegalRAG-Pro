"""Synthetic historical snapshot capture rehearsal for frozen HM2 evidence.

HM2.3 verifies historical analytical text from a caller-supplied retained Chroma
source by first constructing and verifying an exact disposable copy.  Only that
disposable copy may be opened with Chroma.  The module produces deterministic
audit data and never publishes source evidence, mutates a logical collection,
or upgrades historical provenance.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from .historical_disposition import (
    HistoricalEvidenceDispositionEntry,
    HistoricalEvidenceDispositionError,
    HistoricalEvidenceDispositionManifest,
    HistoricalEvidenceRelationship,
    validate_historical_evidence_disposition_manifest,
)
from .identity import (
    canonical_json_bytes,
    canonical_uuid,
    derive_sha256_id,
    sha256_bytes,
    validate_sha256_hex,
    validate_sha256_id,
)
from .migration import HistoricalMigrationReport, historical_migration_report_to_dict
from .models import BindingClass
from .reingestion_transition import (
    ProspectiveReingestionReport,
    prospective_reingestion_report_to_dict,
)

HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION = (
    "historical-snapshot-capture-rehearsal/1.0"
)
_GOVERNED_COLLECTION_NAME = "legal_documents"
_DISPOSABLE_DATABASE_DIRECTORY = "retained-db-copy"


class HistoricalSnapshotRehearsalError(RuntimeError):
    """Raised when HM2.3 cannot proceed without weakening a governed invariant."""


class HistoricalSnapshotCaptureStatus(StrEnum):
    """Deterministic row-level outcomes for historical snapshot observation."""

    EXACT_TEXT_VERIFIED = "exact_text_verified"
    TEXT_HASH_MISMATCH = "text_hash_mismatch"
    ROW_MISSING = "row_missing"
    ROW_AMBIGUOUS = "row_ambiguous"
    METADATA_MISMATCH = "metadata_mismatch"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotCaptureObservation:
    """One historical disposition reconciled with the disposable Chroma snapshot."""

    historical_record_id: str
    historical_evidence_key: str
    relationship: HistoricalEvidenceRelationship
    document_name: str | None
    document_id: str | None
    page: int | None
    chunk_id: str | None
    historical_binding_class: BindingClass
    expected_text_sha256: str | None
    observed_text_sha256: str | None
    expected_metadata_fingerprint: str | None
    observed_metadata_fingerprint: str | None
    observed_row_id: str | None
    observed_row_count: int
    current_successor_evidence_key: str | None
    current_successor_chunk_text_sha256: str | None
    binding_key_collision_risk: bool
    status: HistoricalSnapshotCaptureStatus
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "blockers", tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotCaptureRehearsalReport:
    """Deterministic semantic HM2.3 rehearsal report without historical plaintext."""

    schema_version: str
    case_id: str
    hm1_report_id: str
    pfcr1_report_id: str
    hm2_manifest_id: str
    retained_source_tree_sha256: str
    observations: tuple[HistoricalSnapshotCaptureObservation, ...]
    historical_record_count: int
    exact_text_verified_count: int
    text_hash_mismatch_count: int
    row_missing_count: int
    row_ambiguous_count: int
    metadata_mismatch_count: int
    unreadable_count: int
    historical_snapshot_capture_rehearsal_report_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    relative_path: str
    byte_length: int
    sha256_hex: str


@dataclass(frozen=True, slots=True)
class _TreeManifest:
    root_exists: bool
    entries: tuple[_TreeEntry, ...]
    tree_sha256: str


@dataclass(frozen=True, slots=True)
class _ObservedChromaRow:
    row_id: str
    document: object
    metadata: dict[str, object]


def _frozen_report_canonical_json_bytes(payload: object) -> bytes:
    """Reproduce the frozen HM1/PFCR1 no-final-LF canonical JSON contract."""

    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HistoricalSnapshotRehearsalError(
            "Frozen upstream report data is not canonical JSON."
        ) from exc


def _json_compatible(value: object) -> object:
    """Reproduce the frozen HM1 metadata JSON-compatibility conversion."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    raise HistoricalSnapshotRehearsalError(
        "Historical Chroma metadata contains a non-JSON-compatible value."
    )


def _metadata_fingerprint(metadata: Mapping[str, object]) -> str:
    payload = _frozen_report_canonical_json_bytes(_json_compatible(dict(metadata)))
    return "sha256:" + sha256_bytes(payload)


def _validate_frozen_report_identity(
    payload: dict[str, object],
    *,
    id_field: str,
    stored_id: str,
    label: str,
) -> None:
    try:
        validate_sha256_id(stored_id, field_name=id_field)
    except ValueError as exc:
        raise HistoricalSnapshotRehearsalError(
            f"{label} identity is malformed."
        ) from exc

    identity_payload = dict(payload)
    embedded_id = identity_payload.pop(id_field, None)
    if embedded_id != stored_id:
        raise HistoricalSnapshotRehearsalError(
            f"{label} serialized identity does not match its object identity."
        )

    expected = "sha256:" + sha256_bytes(
        _frozen_report_canonical_json_bytes(identity_payload)
    )
    if stored_id != expected:
        raise HistoricalSnapshotRehearsalError(
            f"{label} canonical report identity is invalid."
        )


def _validate_upstream_authorities(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm1_report: HistoricalMigrationReport,
    pfcr1_report: ProspectiveReingestionReport,
) -> str:
    try:
        validate_historical_evidence_disposition_manifest(hm2_manifest)
    except (HistoricalEvidenceDispositionError, TypeError, ValueError) as exc:
        raise HistoricalSnapshotRehearsalError(
            "HM2.2 historical disposition manifest is invalid."
        ) from exc

    hm1_payload = historical_migration_report_to_dict(hm1_report)
    pfcr1_payload = prospective_reingestion_report_to_dict(pfcr1_report)

    _validate_frozen_report_identity(
        hm1_payload,
        id_field="historical_migration_report_id",
        stored_id=hm1_report.historical_migration_report_id,
        label="HM1",
    )
    _validate_frozen_report_identity(
        pfcr1_payload,
        id_field="prospective_reingestion_report_id",
        stored_id=pfcr1_report.prospective_reingestion_report_id,
        label="PFCR1",
    )

    try:
        case_id = canonical_uuid(hm2_manifest.case_id, field_name="case_id")
    except ValueError as exc:
        raise HistoricalSnapshotRehearsalError("HM2.2 case_id is invalid.") from exc

    if hm1_report.case_id != case_id or pfcr1_report.case_id != case_id:
        raise HistoricalSnapshotRehearsalError(
            "HM1/PFCR1/HM2.2 case identities do not agree."
        )
    if hm2_manifest.hm1_report_id != hm1_report.historical_migration_report_id:
        raise HistoricalSnapshotRehearsalError(
            "HM2.2 does not reference the supplied frozen HM1 report."
        )
    if hm2_manifest.pfcr1_report_id != pfcr1_report.prospective_reingestion_report_id:
        raise HistoricalSnapshotRehearsalError(
            "HM2.2 does not reference the supplied frozen PFCR1 report."
        )
    if pfcr1_report.hm1_report_id != hm1_report.historical_migration_report_id:
        raise HistoricalSnapshotRehearsalError(
            "PFCR1 does not reference the supplied frozen HM1 report."
        )

    for entry in hm2_manifest.entries:
        if entry.historical_binding_class is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
            raise HistoricalSnapshotRehearsalError(
                "HM2.3 requires every historical disposition to remain "
                "LEGACY_CURRENT_INDEX_SNAPSHOT."
            )
        if entry.historical_current_chroma_text_sha256 is None:
            raise HistoricalSnapshotRehearsalError(
                "HM2.3 requires the frozen HM1 historical Chroma text SHA-256."
            )
        if entry.historical_metadata_fingerprint is None:
            raise HistoricalSnapshotRehearsalError(
                "HM2.3 requires the frozen HM1 historical metadata fingerprint."
            )
        try:
            validate_sha256_hex(
                entry.historical_current_chroma_text_sha256,
                field_name="historical_current_chroma_text_sha256",
            )
            validate_sha256_id(
                entry.historical_metadata_fingerprint,
                field_name="historical_metadata_fingerprint",
            )
        except ValueError as exc:
            raise HistoricalSnapshotRehearsalError(
                "HM2.2 contains an invalid historical text or metadata hash."
            ) from exc

    return case_id


def _is_link_like(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink():
        return True
    junction = getattr(path, "is_junction", None)
    if junction is not None and junction():
        return True
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise HistoricalSnapshotRehearsalError(
            f"Unable to inspect filesystem entry safely: {path}"
        ) from exc
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _same_or_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _same_or_below(left, right) or _same_or_below(right, left)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_retained_root(raw_root: Path) -> Path:
    raw = Path(raw_root).expanduser()
    if _is_link_like(raw):
        raise HistoricalSnapshotRehearsalError(
            "retained_db_root must not be a symlink, junction, or reparse point."
        )
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise HistoricalSnapshotRehearsalError(
            "retained_db_root must be an existing directory."
        ) from exc
    if not root.is_dir() or _is_link_like(root):
        raise HistoricalSnapshotRehearsalError(
            "retained_db_root must be a safe directory."
        )
    return root


def _resolve_workspace_root(raw_workspace: Path, retained_root: Path) -> Path:
    raw = Path(raw_workspace).expanduser()
    if raw.exists() or raw.is_symlink():
        raise HistoricalSnapshotRehearsalError(
            "workspace_root must be a fresh, non-existing disposable path."
        )

    parent_raw = raw.parent
    if _is_link_like(parent_raw):
        raise HistoricalSnapshotRehearsalError(
            "workspace_root parent must not be link-like."
        )
    try:
        parent = parent_raw.resolve(strict=True)
    except OSError as exc:
        raise HistoricalSnapshotRehearsalError(
            "workspace_root parent must already exist."
        ) from exc
    if not parent.is_dir() or _is_link_like(parent):
        raise HistoricalSnapshotRehearsalError(
            "workspace_root parent must be a safe directory."
        )

    workspace = (parent / raw.name).resolve(strict=False)
    project = _project_root().resolve(strict=True)
    protected = (
        retained_root,
        retained_root.parent,
        project,
        (project / "db").resolve(strict=False),
        (project / "source_evidence_store").resolve(strict=False),
        (project / "report_projections").resolve(strict=False),
        (project / "docs").resolve(strict=False),
    )
    if any(_paths_overlap(workspace, item) for item in protected):
        raise HistoricalSnapshotRehearsalError(
            "workspace_root overlaps protected project or retained state."
        )

    for part in workspace.parts:
        if part.casefold().startswith("legalrag-pfcr"):
            raise HistoricalSnapshotRehearsalError(
                "workspace_root must not be inside a retained PFCR evidence tree."
            )

    return workspace


def _make_tree_manifest(root_exists: bool, entries: tuple[_TreeEntry, ...]) -> _TreeManifest:
    payload = {
        "root_exists": root_exists,
        "entries": [
            {
                "relative_path": entry.relative_path,
                "byte_length": entry.byte_length,
                "sha256_hex": entry.sha256_hex,
            }
            for entry in entries
        ],
    }
    return _TreeManifest(
        root_exists=root_exists,
        entries=entries,
        tree_sha256="sha256:" + sha256_bytes(_frozen_report_canonical_json_bytes(payload)),
    )


def _build_tree_manifest(root: Path, *, require_exists: bool) -> _TreeManifest:
    root = Path(root).resolve(strict=False)
    if not root.exists():
        if require_exists:
            raise HistoricalSnapshotRehearsalError(
                "Required historical database tree does not exist."
            )
        return _make_tree_manifest(False, ())
    if _is_link_like(root) or not root.is_dir():
        raise HistoricalSnapshotRehearsalError(
            "Historical database tree root is not a safe directory."
        )

    entries: list[_TreeEntry] = []
    try:
        paths = sorted(
            root.rglob("*"),
            key=lambda item: item.relative_to(root).as_posix(),
        )
    except OSError as exc:
        raise HistoricalSnapshotRehearsalError(
            "Unable to enumerate historical database tree."
        ) from exc

    for path in paths:
        if _is_link_like(path):
            raise HistoricalSnapshotRehearsalError(
                "Historical database tree contains a link-like entry."
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise HistoricalSnapshotRehearsalError(
                "Historical database tree contains a non-regular entry."
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HistoricalSnapshotRehearsalError(
                "Unable to read historical database tree exactly."
            ) from exc
        entries.append(
            _TreeEntry(
                relative_path=path.relative_to(root).as_posix(),
                byte_length=len(data),
                sha256_hex=sha256_bytes(data),
            )
        )

    return _make_tree_manifest(True, tuple(entries))


def _copy_tree_exact(source: Path, destination: Path, manifest: _TreeManifest) -> None:
    if destination.exists() or destination.is_symlink():
        raise HistoricalSnapshotRehearsalError(
            "Disposable historical database target already exists."
        )
    try:
        destination.mkdir(parents=False, exist_ok=False)
        for entry in manifest.entries:
            src = source / Path(entry.relative_path)
            dst = destination / Path(entry.relative_path)
            if _is_link_like(src) or not src.is_file():
                raise HistoricalSnapshotRehearsalError(
                    "Retained historical tree changed during disposable copy."
                )
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    except HistoricalSnapshotRehearsalError:
        raise
    except OSError as exc:
        raise HistoricalSnapshotRehearsalError(
            "Unable to construct exact disposable historical database copy."
        ) from exc

    copied = _build_tree_manifest(destination, require_exists=True)
    if copied != manifest:
        raise HistoricalSnapshotRehearsalError(
            "Disposable historical database copy is not byte-identical pre-open."
        )


def _parse_chroma_response(response: object) -> tuple[_ObservedChromaRow, ...]:
    if not isinstance(response, Mapping):
        raise HistoricalSnapshotRehearsalError("Chroma response is malformed.")

    ids = response.get("ids", [])
    documents = response.get("documents", [])
    metadatas = response.get("metadatas", [])

    if documents is None:
        documents = [None] * len(ids) if isinstance(ids, Sequence) else []
    if metadatas is None:
        metadatas = [{} for _ in ids] if isinstance(ids, Sequence) else []

    for value, label in (
        (ids, "ids"),
        (documents, "documents"),
        (metadatas, "metadatas"),
    ):
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise HistoricalSnapshotRehearsalError(
                f"Chroma {label} are malformed."
            )

    if not (len(ids) == len(documents) == len(metadatas)):
        raise HistoricalSnapshotRehearsalError(
            "Chroma ids, documents, and metadatas have inconsistent lengths."
        )

    rows: list[_ObservedChromaRow] = []
    for row_id, document, metadata in zip(ids, documents, metadatas, strict=True):
        if not isinstance(row_id, str) or not row_id:
            raise HistoricalSnapshotRehearsalError("Chroma row id is malformed.")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            raise HistoricalSnapshotRehearsalError(
                "Chroma row metadata is malformed."
            )
        rows.append(
            _ObservedChromaRow(
                row_id=row_id,
                document=document,
                metadata={str(key): value for key, value in metadata.items()},
            )
        )
    return tuple(rows)


def _observe_disposable_collection(db_root: Path) -> tuple[_ObservedChromaRow, ...]:
    try:
        import chromadb
    except ImportError as exc:
        raise HistoricalSnapshotRehearsalError(
            "Chroma is unavailable for the disposable HM2.3 rehearsal."
        ) from exc

    client = None
    try:
        client = chromadb.PersistentClient(path=str(db_root))
        collection = client.get_collection(name=_GOVERNED_COLLECTION_NAME)
        raw = collection.get(include=["documents", "metadatas"])
        return _parse_chroma_response(raw)
    except HistoricalSnapshotRehearsalError:
        raise
    except Exception as exc:
        raise HistoricalSnapshotRehearsalError(
            "Unable to observe the disposable historical Chroma collection."
        ) from exc
    finally:
        if client is not None:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()


def _observation_for_entry(
    entry: HistoricalEvidenceDispositionEntry,
    rows: tuple[_ObservedChromaRow, ...],
) -> HistoricalSnapshotCaptureObservation:
    matches = tuple(row for row in rows if row.row_id == entry.historical_evidence_key)
    base = {
        "historical_record_id": entry.historical_record_id,
        "historical_evidence_key": entry.historical_evidence_key,
        "relationship": entry.relationship,
        "document_name": entry.document_name,
        "document_id": entry.document_id,
        "page": entry.page,
        "chunk_id": entry.chunk_id,
        "historical_binding_class": entry.historical_binding_class,
        "expected_text_sha256": entry.historical_current_chroma_text_sha256,
        "expected_metadata_fingerprint": entry.historical_metadata_fingerprint,
        "current_successor_evidence_key": entry.current_successor_evidence_key,
        "current_successor_chunk_text_sha256": entry.current_successor_chunk_text_sha256,
        "binding_key_collision_risk": entry.binding_key_collision_risk,
    }

    if not matches:
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=None,
            observed_metadata_fingerprint=None,
            observed_row_id=None,
            observed_row_count=0,
            status=HistoricalSnapshotCaptureStatus.ROW_MISSING,
            blockers=("row_missing",),
        )
    if len(matches) != 1:
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=None,
            observed_metadata_fingerprint=None,
            observed_row_id=None,
            observed_row_count=len(matches),
            status=HistoricalSnapshotCaptureStatus.ROW_AMBIGUOUS,
            blockers=("row_ambiguous",),
        )

    row = matches[0]
    try:
        observed_metadata = _metadata_fingerprint(row.metadata)
    except HistoricalSnapshotRehearsalError:
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=None,
            observed_metadata_fingerprint=None,
            observed_row_id=row.row_id,
            observed_row_count=1,
            status=HistoricalSnapshotCaptureStatus.METADATA_MISMATCH,
            blockers=("metadata_not_canonical",),
        )

    if observed_metadata != entry.historical_metadata_fingerprint:
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=None,
            observed_metadata_fingerprint=observed_metadata,
            observed_row_id=row.row_id,
            observed_row_count=1,
            status=HistoricalSnapshotCaptureStatus.METADATA_MISMATCH,
            blockers=("metadata_fingerprint_mismatch",),
        )

    if not isinstance(row.document, str):
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=None,
            observed_metadata_fingerprint=observed_metadata,
            observed_row_id=row.row_id,
            observed_row_count=1,
            status=HistoricalSnapshotCaptureStatus.UNREADABLE,
            blockers=("historical_text_unreadable",),
        )

    observed_text = sha256_bytes(row.document.encode("utf-8"))
    if observed_text != entry.historical_current_chroma_text_sha256:
        return HistoricalSnapshotCaptureObservation(
            **base,
            observed_text_sha256=observed_text,
            observed_metadata_fingerprint=observed_metadata,
            observed_row_id=row.row_id,
            observed_row_count=1,
            status=HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH,
            blockers=("historical_text_sha256_mismatch",),
        )

    return HistoricalSnapshotCaptureObservation(
        **base,
        observed_text_sha256=observed_text,
        observed_metadata_fingerprint=observed_metadata,
        observed_row_id=row.row_id,
        observed_row_count=1,
        status=HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED,
        blockers=(),
    )


def historical_snapshot_capture_observation_to_dict(
    value: HistoricalSnapshotCaptureObservation,
) -> dict[str, object]:
    return {
        "historical_record_id": value.historical_record_id,
        "historical_evidence_key": value.historical_evidence_key,
        "relationship": value.relationship.value,
        "document_name": value.document_name,
        "document_id": value.document_id,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "historical_binding_class": value.historical_binding_class.value,
        "expected_text_sha256": value.expected_text_sha256,
        "observed_text_sha256": value.observed_text_sha256,
        "expected_metadata_fingerprint": value.expected_metadata_fingerprint,
        "observed_metadata_fingerprint": value.observed_metadata_fingerprint,
        "observed_row_id": value.observed_row_id,
        "observed_row_count": value.observed_row_count,
        "current_successor_evidence_key": value.current_successor_evidence_key,
        "current_successor_chunk_text_sha256": value.current_successor_chunk_text_sha256,
        "binding_key_collision_risk": value.binding_key_collision_risk,
        "status": value.status.value,
        "blockers": list(value.blockers),
    }


def historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(
    value: HistoricalSnapshotCaptureRehearsalReport,
) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "hm1_report_id": value.hm1_report_id,
        "pfcr1_report_id": value.pfcr1_report_id,
        "hm2_manifest_id": value.hm2_manifest_id,
        "retained_source_tree_sha256": value.retained_source_tree_sha256,
        "observations": [
            historical_snapshot_capture_observation_to_dict(item)
            for item in value.observations
        ],
        "historical_record_count": value.historical_record_count,
        "exact_text_verified_count": value.exact_text_verified_count,
        "text_hash_mismatch_count": value.text_hash_mismatch_count,
        "row_missing_count": value.row_missing_count,
        "row_ambiguous_count": value.row_ambiguous_count,
        "metadata_mismatch_count": value.metadata_mismatch_count,
        "unreadable_count": value.unreadable_count,
    }


def historical_snapshot_capture_rehearsal_report_to_dict(
    value: HistoricalSnapshotCaptureRehearsalReport,
) -> dict[str, object]:
    return {
        **historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(value),
        "historical_snapshot_capture_rehearsal_report_id": (
            value.historical_snapshot_capture_rehearsal_report_id
        ),
    }


def validate_historical_snapshot_capture_rehearsal_report(
    value: HistoricalSnapshotCaptureRehearsalReport,
) -> None:
    if not isinstance(value, HistoricalSnapshotCaptureRehearsalReport):
        raise ValueError(
            "value must be a HistoricalSnapshotCaptureRehearsalReport instance."
        )
    if value.schema_version != HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION:
        raise ValueError("Unsupported HM2.3 rehearsal schema_version.")

    canonical_uuid(value.case_id, field_name="case_id")
    for field_name, identifier in (
        ("hm1_report_id", value.hm1_report_id),
        ("pfcr1_report_id", value.pfcr1_report_id),
        ("hm2_manifest_id", value.hm2_manifest_id),
        ("retained_source_tree_sha256", value.retained_source_tree_sha256),
    ):
        validate_sha256_id(identifier, field_name=field_name)

    seen_record_ids: set[str] = set()
    statuses: dict[HistoricalSnapshotCaptureStatus, int] = {
        status: 0 for status in HistoricalSnapshotCaptureStatus
    }
    for observation in value.observations:
        if not isinstance(observation, HistoricalSnapshotCaptureObservation):
            raise ValueError("observations contain an invalid value.")
        validate_sha256_id(
            observation.historical_record_id,
            field_name="historical_record_id",
        )
        if observation.historical_record_id in seen_record_ids:
            raise ValueError("HM2.3 observations must use unique historical_record_id values.")
        seen_record_ids |= {observation.historical_record_id}
        if not observation.historical_evidence_key:
            raise ValueError("historical_evidence_key must not be empty.")
        if not isinstance(observation.relationship, HistoricalEvidenceRelationship):
            raise ValueError("relationship must be HistoricalEvidenceRelationship.")
        if observation.historical_binding_class is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
            raise ValueError("HM2.3 may not promote historical binding class.")
        if observation.expected_text_sha256 is not None:
            validate_sha256_hex(
                observation.expected_text_sha256,
                field_name="expected_text_sha256",
            )
        if observation.observed_text_sha256 is not None:
            validate_sha256_hex(
                observation.observed_text_sha256,
                field_name="observed_text_sha256",
            )
        if observation.expected_metadata_fingerprint is not None:
            validate_sha256_id(
                observation.expected_metadata_fingerprint,
                field_name="expected_metadata_fingerprint",
            )
        if observation.observed_metadata_fingerprint is not None:
            validate_sha256_id(
                observation.observed_metadata_fingerprint,
                field_name="observed_metadata_fingerprint",
            )
        if observation.observed_row_count < 0:
            raise ValueError("observed_row_count must be non-negative.")
        if not isinstance(observation.status, HistoricalSnapshotCaptureStatus):
            raise ValueError("status must be HistoricalSnapshotCaptureStatus.")
        statuses[observation.status] += 1

        if observation.status is HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED:
            if observation.blockers:
                raise ValueError("EXACT_TEXT_VERIFIED observations must have no blockers.")
            if observation.observed_row_count != 1 or observation.observed_row_id is None:
                raise ValueError("EXACT_TEXT_VERIFIED requires exactly one observed row.")
            if observation.expected_text_sha256 != observation.observed_text_sha256:
                raise ValueError("EXACT_TEXT_VERIFIED text hashes must agree.")
            if (
                observation.expected_metadata_fingerprint
                != observation.observed_metadata_fingerprint
            ):
                raise ValueError("EXACT_TEXT_VERIFIED metadata fingerprints must agree.")
        else:
            if not observation.blockers:
                raise ValueError("Non-exact HM2.3 observations require blockers.")

        if observation.status is HistoricalSnapshotCaptureStatus.ROW_MISSING:
            if observation.observed_row_count != 0 or observation.observed_row_id is not None:
                raise ValueError("ROW_MISSING must contain no observed row.")
        elif observation.status is HistoricalSnapshotCaptureStatus.ROW_AMBIGUOUS:
            if observation.observed_row_count <= 1 or observation.observed_row_id is not None:
                raise ValueError("ROW_AMBIGUOUS requires multiple unresolved rows.")
        elif observation.status in {
            HistoricalSnapshotCaptureStatus.METADATA_MISMATCH,
            HistoricalSnapshotCaptureStatus.UNREADABLE,
            HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH,
        }:
            if observation.observed_row_count != 1 or observation.observed_row_id is None:
                raise ValueError("Observed mismatch statuses require exactly one row.")

    expected_counts = {
        "historical_record_count": len(value.observations),
        "exact_text_verified_count": statuses[
            HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
        ],
        "text_hash_mismatch_count": statuses[
            HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH
        ],
        "row_missing_count": statuses[HistoricalSnapshotCaptureStatus.ROW_MISSING],
        "row_ambiguous_count": statuses[
            HistoricalSnapshotCaptureStatus.ROW_AMBIGUOUS
        ],
        "metadata_mismatch_count": statuses[
            HistoricalSnapshotCaptureStatus.METADATA_MISMATCH
        ],
        "unreadable_count": statuses[HistoricalSnapshotCaptureStatus.UNREADABLE],
    }
    for field_name, expected in expected_counts.items():
        if getattr(value, field_name) != expected:
            raise ValueError(f"{field_name} does not match the observation population.")

    validate_sha256_id(
        value.historical_snapshot_capture_rehearsal_report_id,
        field_name="historical_snapshot_capture_rehearsal_report_id",
    )
    expected_id = derive_sha256_id(
        historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(value)
    )
    if value.historical_snapshot_capture_rehearsal_report_id != expected_id:
        raise ValueError("HM2.3 rehearsal report identity is not canonical.")


def dumps_historical_snapshot_capture_rehearsal_report(
    value: HistoricalSnapshotCaptureRehearsalReport,
) -> str:
    validate_historical_snapshot_capture_rehearsal_report(value)
    return canonical_json_bytes(
        historical_snapshot_capture_rehearsal_report_to_dict(value)
    ).decode("utf-8")


def _build_report(
    *,
    case_id: str,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm1_report: HistoricalMigrationReport,
    pfcr1_report: ProspectiveReingestionReport,
    retained_source_tree_sha256: str,
    rows: tuple[_ObservedChromaRow, ...],
) -> HistoricalSnapshotCaptureRehearsalReport:
    expected_historical_keys = {
        entry.historical_evidence_key for entry in hm2_manifest.entries
    }
    unexpected_historical_ids = tuple(
        sorted({row.row_id for row in rows} - expected_historical_keys)
    )
    if unexpected_historical_ids:
        raise HistoricalSnapshotRehearsalError(
            "Disposable historical Chroma contains unexpected historical row identities."
        )

    observations = tuple(
        _observation_for_entry(entry, rows)
        for entry in sorted(
            hm2_manifest.entries,
            key=lambda item: item.historical_record_id,
        )
    )
    counts = {
        status: sum(item.status is status for item in observations)
        for status in HistoricalSnapshotCaptureStatus
    }

    provisional = HistoricalSnapshotCaptureRehearsalReport(
        schema_version=HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION,
        case_id=case_id,
        hm1_report_id=hm1_report.historical_migration_report_id,
        pfcr1_report_id=pfcr1_report.prospective_reingestion_report_id,
        hm2_manifest_id=hm2_manifest.historical_evidence_disposition_manifest_id,
        retained_source_tree_sha256=retained_source_tree_sha256,
        observations=observations,
        historical_record_count=len(observations),
        exact_text_verified_count=counts[
            HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
        ],
        text_hash_mismatch_count=counts[
            HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH
        ],
        row_missing_count=counts[HistoricalSnapshotCaptureStatus.ROW_MISSING],
        row_ambiguous_count=counts[
            HistoricalSnapshotCaptureStatus.ROW_AMBIGUOUS
        ],
        metadata_mismatch_count=counts[
            HistoricalSnapshotCaptureStatus.METADATA_MISMATCH
        ],
        unreadable_count=counts[HistoricalSnapshotCaptureStatus.UNREADABLE],
        historical_snapshot_capture_rehearsal_report_id="sha256:" + "0" * 64,
    )
    report = replace(
        provisional,
        historical_snapshot_capture_rehearsal_report_id=derive_sha256_id(
            historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(
                provisional
            )
        ),
    )
    validate_historical_snapshot_capture_rehearsal_report(report)
    return report


def rehearse_historical_snapshot_capture(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm1_report: HistoricalMigrationReport,
    pfcr1_report: ProspectiveReingestionReport,
    retained_db_root: Path,
    workspace_root: Path,
    expected_retained_tree_sha256: str,
) -> HistoricalSnapshotCaptureRehearsalReport:
    """Run an HM2.3 rehearsal against an exact disposable historical DB copy.

    The retained source tree is never passed to Chroma.  Physical persistence
    changes caused by opening/reading the disposable copy are permitted.  Any
    change to the retained source tree causes the rehearsal to fail closed.
    """

    case_id = _validate_upstream_authorities(
        hm2_manifest=hm2_manifest,
        hm1_report=hm1_report,
        pfcr1_report=pfcr1_report,
    )
    try:
        validate_sha256_id(
            expected_retained_tree_sha256,
            field_name="expected_retained_tree_sha256",
        )
    except ValueError as exc:
        raise HistoricalSnapshotRehearsalError(
            "expected_retained_tree_sha256 is invalid."
        ) from exc

    retained = _resolve_retained_root(retained_db_root)
    workspace = _resolve_workspace_root(workspace_root, retained)

    retained_pre = _build_tree_manifest(retained, require_exists=True)
    if retained_pre.tree_sha256 != expected_retained_tree_sha256:
        raise HistoricalSnapshotRehearsalError(
            "Retained historical database tree does not match the approved SHA-256."
        )

    workspace.mkdir(parents=False, exist_ok=False)
    disposable = workspace / _DISPOSABLE_DATABASE_DIRECTORY
    _copy_tree_exact(retained, disposable, retained_pre)

    retained_after_copy = _build_tree_manifest(retained, require_exists=True)
    if retained_after_copy != retained_pre:
        raise HistoricalSnapshotRehearsalError(
            "Retained historical database changed during disposable-copy construction."
        )

    disposable_pre_open = _build_tree_manifest(disposable, require_exists=True)
    if disposable_pre_open != retained_pre:
        raise HistoricalSnapshotRehearsalError(
            "Disposable historical database is not exact before first Chroma open."
        )

    rows = _observe_disposable_collection(disposable)

    retained_post = _build_tree_manifest(retained, require_exists=True)
    if retained_post != retained_pre:
        raise HistoricalSnapshotRehearsalError(
            "Retained historical database changed during disposable observation."
        )

    return _build_report(
        case_id=case_id,
        hm2_manifest=hm2_manifest,
        hm1_report=hm1_report,
        pfcr1_report=pfcr1_report,
        retained_source_tree_sha256=retained_pre.tree_sha256,
        rows=rows,
    )


__all__ = [
    "HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION",
    "HistoricalSnapshotCaptureObservation",
    "HistoricalSnapshotCaptureRehearsalReport",
    "HistoricalSnapshotCaptureStatus",
    "HistoricalSnapshotRehearsalError",
    "dumps_historical_snapshot_capture_rehearsal_report",
    "historical_snapshot_capture_observation_to_dict",
    "historical_snapshot_capture_rehearsal_report_identity_payload_to_dict",
    "historical_snapshot_capture_rehearsal_report_to_dict",
    "rehearse_historical_snapshot_capture",
    "validate_historical_snapshot_capture_rehearsal_report",
]
