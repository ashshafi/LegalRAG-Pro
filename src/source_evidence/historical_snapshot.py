"""Immutable historical analytical-text snapshot model and publication preparation.

HM2.4 preserves historical analytical text as exact UTF-8 bytes in the existing
M2 content-addressed blob pool while keeping logical historical provenance in a
separate manifest namespace.  The module is additive: it never publishes
EvidenceBinding objects, never promotes historical provenance, and has no
Chroma, OCR, retrieval, or LLM dependency.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence

from .historical_disposition import HistoricalEvidenceRelationship
from .historical_snapshot_rehearsal import (
    HistoricalSnapshotCaptureRehearsalReport,
    HistoricalSnapshotCaptureStatus,
    validate_historical_snapshot_capture_rehearsal_report,
)
from .identity import (
    canonical_json_bytes,
    canonical_uuid,
    derive_sha256_id,
    sha256_bytes,
    validate_sha256_hex,
    validate_sha256_id,
)
from .models import BindingClass
from .store import SourceEvidenceStore, SourceEvidenceStoreError


HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION = "historical-snapshot-manifest/1.0"


class HistoricalSnapshotError(RuntimeError):
    """Raised when historical snapshot preparation or persistence is unsafe."""


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotMaterial:
    """Transient exact historical material supplied to the synthetic publisher."""

    historical_record_id: str
    historical_text: str
    historical_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "historical_metadata", dict(self.historical_metadata))


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotBlob:
    """One unique exact immutable blob planned for M2 content-addressed storage."""

    sha256_hex: str
    content: bytes


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotEntry:
    """One durable logical historical record referencing immutable blob content."""

    historical_record_id: str
    historical_evidence_key: str
    document_name: str | None
    document_id: str | None
    page: int | None
    chunk_id: str | None
    relationship: HistoricalEvidenceRelationship
    historical_binding_class: BindingClass
    historical_text_blob_sha256: str
    historical_text_byte_length: int
    historical_metadata_blob_sha256: str
    historical_metadata_byte_length: int
    historical_metadata_fingerprint: str
    current_successor_evidence_key: str | None
    current_successor_chunk_text_sha256: str | None
    binding_key_collision_risk: bool


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotManifest:
    """Immutable corpus manifest for independently preserved historical snapshots."""

    schema_version: str
    case_id: str
    hm1_report_id: str
    pfcr1_report_id: str
    hm2_manifest_id: str
    hm23_rehearsal_report_id: str
    entries: tuple[HistoricalSnapshotEntry, ...]
    historical_snapshot_manifest_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotPublicationPlan:
    """Complete deterministic in-memory plan; blobs have no authority without manifest."""

    manifest: HistoricalSnapshotManifest
    blobs: tuple[HistoricalSnapshotBlob, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "blobs", tuple(self.blobs))


def _json_compatible(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    raise HistoricalSnapshotError(
        f"Historical metadata contains unsupported value type: {type(value).__name__}."
    )


def historical_metadata_canonical_bytes(metadata: Mapping[str, object]) -> bytes:
    """Return the frozen HM1 metadata bytes: compact UTF-8 JSON with no final LF."""

    if not isinstance(metadata, Mapping):
        raise HistoricalSnapshotError("historical_metadata must be a mapping.")
    try:
        return json.dumps(
            _json_compatible(dict(metadata)),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HistoricalSnapshotError("Historical metadata is not canonical JSON.") from exc


def historical_snapshot_entry_to_dict(value: HistoricalSnapshotEntry) -> dict[str, object]:
    return {
        "historical_record_id": value.historical_record_id,
        "historical_evidence_key": value.historical_evidence_key,
        "document_name": value.document_name,
        "document_id": value.document_id,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "relationship": value.relationship.value,
        "historical_binding_class": value.historical_binding_class.value,
        "historical_text_blob_sha256": value.historical_text_blob_sha256,
        "historical_text_byte_length": value.historical_text_byte_length,
        "historical_metadata_blob_sha256": value.historical_metadata_blob_sha256,
        "historical_metadata_byte_length": value.historical_metadata_byte_length,
        "historical_metadata_fingerprint": value.historical_metadata_fingerprint,
        "current_successor_evidence_key": value.current_successor_evidence_key,
        "current_successor_chunk_text_sha256": value.current_successor_chunk_text_sha256,
        "binding_key_collision_risk": value.binding_key_collision_risk,
    }


def historical_snapshot_manifest_identity_payload_to_dict(
    value: HistoricalSnapshotManifest,
) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "hm1_report_id": value.hm1_report_id,
        "pfcr1_report_id": value.pfcr1_report_id,
        "hm2_manifest_id": value.hm2_manifest_id,
        "hm23_rehearsal_report_id": value.hm23_rehearsal_report_id,
        "entries": [historical_snapshot_entry_to_dict(item) for item in value.entries],
    }


def historical_snapshot_manifest_to_dict(
    value: HistoricalSnapshotManifest,
) -> dict[str, object]:
    return {
        **historical_snapshot_manifest_identity_payload_to_dict(value),
        "historical_snapshot_manifest_id": value.historical_snapshot_manifest_id,
    }


def dumps_historical_snapshot_manifest(value: HistoricalSnapshotManifest) -> str:
    """Return M1-canonical manifest JSON with exactly one final LF."""

    validate_historical_snapshot_manifest(value)
    return canonical_json_bytes(historical_snapshot_manifest_to_dict(value)).decode("utf-8")


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must not be empty.")
    return value


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def _nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return value


def validate_historical_snapshot_manifest(value: HistoricalSnapshotManifest) -> None:
    """Fail closed unless one historical corpus manifest is internally canonical."""

    if not isinstance(value, HistoricalSnapshotManifest):
        raise ValueError("value must be a HistoricalSnapshotManifest instance.")
    if value.schema_version != HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported HistoricalSnapshotManifest schema_version.")

    canonical_uuid(value.case_id, field_name="case_id")
    validate_sha256_id(value.hm1_report_id, field_name="hm1_report_id")
    validate_sha256_id(value.pfcr1_report_id, field_name="pfcr1_report_id")
    validate_sha256_id(value.hm2_manifest_id, field_name="hm2_manifest_id")
    validate_sha256_id(value.hm23_rehearsal_report_id, field_name="hm23_rehearsal_report_id")

    record_ids: set[str] = set()
    historical_keys: set[str] = set()
    previous_record_id: str | None = None

    for entry in value.entries:
        if not isinstance(entry, HistoricalSnapshotEntry):
            raise ValueError("manifest entries must be HistoricalSnapshotEntry values.")
        validate_sha256_id(entry.historical_record_id, field_name="historical_record_id")
        _required_text(entry.historical_evidence_key, field_name="historical_evidence_key")
        _optional_text(entry.document_name, field_name="document_name")
        _optional_text(entry.document_id, field_name="document_id")
        if entry.page is not None:
            _positive_int(entry.page, field_name="page")
        _optional_text(entry.chunk_id, field_name="chunk_id")
        if not isinstance(entry.relationship, HistoricalEvidenceRelationship):
            raise ValueError("relationship must be HistoricalEvidenceRelationship.")
        if entry.historical_binding_class is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
            raise ValueError(
                "Historical snapshots must remain LEGACY_CURRENT_INDEX_SNAPSHOT."
            )

        validate_sha256_hex(
            entry.historical_text_blob_sha256,
            field_name="historical_text_blob_sha256",
        )
        _nonnegative_int(
            entry.historical_text_byte_length,
            field_name="historical_text_byte_length",
        )
        validate_sha256_hex(
            entry.historical_metadata_blob_sha256,
            field_name="historical_metadata_blob_sha256",
        )
        _nonnegative_int(
            entry.historical_metadata_byte_length,
            field_name="historical_metadata_byte_length",
        )
        validate_sha256_id(
            entry.historical_metadata_fingerprint,
            field_name="historical_metadata_fingerprint",
        )
        if entry.historical_metadata_fingerprint != (
            "sha256:" + entry.historical_metadata_blob_sha256
        ):
            raise ValueError(
                "historical_metadata_fingerprint must identify the exact metadata blob."
            )

        successor_key = _optional_text(
            entry.current_successor_evidence_key,
            field_name="current_successor_evidence_key",
        )
        successor_sha = entry.current_successor_chunk_text_sha256
        if successor_sha is not None:
            validate_sha256_hex(
                successor_sha,
                field_name="current_successor_chunk_text_sha256",
            )
        if (successor_key is None) != (successor_sha is None):
            raise ValueError("Current successor key/hash presence must agree.")
        if type(entry.binding_key_collision_risk) is not bool:
            raise ValueError("binding_key_collision_risk must be bool.")

        if entry.relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE:
            if successor_key is not None:
                raise ValueError("NO_DIRECT_CORRESPONDENCE must not carry a successor.")
        else:
            if successor_key is None:
                raise ValueError("Related historical entries require a successor.")

        if entry.relationship is HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT:
            if successor_key != entry.historical_evidence_key:
                raise ValueError("SAME_KEY_SAME_TEXT requires identical evidence keys.")
            if successor_sha != entry.historical_text_blob_sha256:
                raise ValueError("SAME_KEY_SAME_TEXT requires identical text hashes.")
        elif entry.relationship is HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT:
            if successor_key != entry.historical_evidence_key:
                raise ValueError(
                    "SAME_KEY_DIFFERENT_TEXT requires identical evidence keys."
                )
            if successor_sha == entry.historical_text_blob_sha256:
                raise ValueError(
                    "SAME_KEY_DIFFERENT_TEXT requires different text hashes."
                )
        elif entry.relationship is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT:
            if successor_key == entry.historical_evidence_key:
                raise ValueError("CHANGED_KEY_SAME_TEXT requires distinct evidence keys.")
            if successor_sha != entry.historical_text_blob_sha256:
                raise ValueError("CHANGED_KEY_SAME_TEXT requires identical text hashes.")

        if entry.historical_record_id in record_ids:
            raise ValueError("historical_record_id values must be unique.")
        if entry.historical_evidence_key in historical_keys:
            raise ValueError("historical_evidence_key values must be unique.")
        if previous_record_id is not None and entry.historical_record_id <= previous_record_id:
            raise ValueError("Historical snapshot entries must use canonical record-id order.")
        record_ids.add(entry.historical_record_id)
        historical_keys.add(entry.historical_evidence_key)
        previous_record_id = entry.historical_record_id

    validate_sha256_id(
        value.historical_snapshot_manifest_id,
        field_name="historical_snapshot_manifest_id",
    )
    expected = derive_sha256_id(historical_snapshot_manifest_identity_payload_to_dict(value))
    if value.historical_snapshot_manifest_id != expected:
        raise ValueError("historical_snapshot_manifest_id is not canonical.")


def loads_historical_snapshot_manifest(payload: str) -> HistoricalSnapshotManifest:
    """Load only exact canonical historical snapshot manifest JSON."""

    if not isinstance(payload, str):
        raise ValueError("payload must be text.")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Historical snapshot manifest JSON is invalid.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Historical snapshot manifest JSON must be an object.")

    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise ValueError("Historical snapshot manifest entries are malformed.")

    try:
        entries = tuple(
            HistoricalSnapshotEntry(
                historical_record_id=item["historical_record_id"],
                historical_evidence_key=item["historical_evidence_key"],
                document_name=item.get("document_name"),
                document_id=item.get("document_id"),
                page=item.get("page"),
                chunk_id=item.get("chunk_id"),
                relationship=HistoricalEvidenceRelationship(item["relationship"]),
                historical_binding_class=BindingClass(item["historical_binding_class"]),
                historical_text_blob_sha256=item["historical_text_blob_sha256"],
                historical_text_byte_length=item["historical_text_byte_length"],
                historical_metadata_blob_sha256=item["historical_metadata_blob_sha256"],
                historical_metadata_byte_length=item["historical_metadata_byte_length"],
                historical_metadata_fingerprint=item["historical_metadata_fingerprint"],
                current_successor_evidence_key=item.get("current_successor_evidence_key"),
                current_successor_chunk_text_sha256=item.get(
                    "current_successor_chunk_text_sha256"
                ),
                binding_key_collision_risk=item["binding_key_collision_risk"],
            )
            for item in entries_raw
        )
        value = HistoricalSnapshotManifest(
            schema_version=raw["schema_version"],
            case_id=raw["case_id"],
            hm1_report_id=raw["hm1_report_id"],
            pfcr1_report_id=raw["pfcr1_report_id"],
            hm2_manifest_id=raw["hm2_manifest_id"],
            hm23_rehearsal_report_id=raw["hm23_rehearsal_report_id"],
            entries=entries,
            historical_snapshot_manifest_id=raw["historical_snapshot_manifest_id"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Historical snapshot manifest structure is invalid.") from exc

    validate_historical_snapshot_manifest(value)
    if dumps_historical_snapshot_manifest(value) != payload:
        raise ValueError("Historical snapshot manifest JSON is not canonical.")
    return value


def _build_blob_index(
    blobs: Sequence[HistoricalSnapshotBlob],
) -> dict[str, bytes]:
    index: dict[str, bytes] = {}
    for blob in blobs:
        if not isinstance(blob, HistoricalSnapshotBlob):
            raise ValueError("plan blobs must be HistoricalSnapshotBlob values.")
        validate_sha256_hex(blob.sha256_hex, field_name="blob.sha256_hex")
        if type(blob.content) is not bytes:
            raise ValueError("blob.content must be exact bytes.")
        if sha256_bytes(blob.content) != blob.sha256_hex:
            raise ValueError("Planned blob SHA-256 does not match its exact bytes.")
        previous = index.setdefault(blob.sha256_hex, blob.content)
        if previous != blob.content:
            raise ValueError("Two planned blobs claim the same SHA-256 with different bytes.")
    return index


def validate_historical_snapshot_publication_plan(
    value: HistoricalSnapshotPublicationPlan,
) -> None:
    if not isinstance(value, HistoricalSnapshotPublicationPlan):
        raise ValueError("value must be HistoricalSnapshotPublicationPlan.")
    validate_historical_snapshot_manifest(value.manifest)
    blob_index = _build_blob_index(value.blobs)
    if tuple(item.sha256_hex for item in value.blobs) != tuple(sorted(blob_index)):
        raise ValueError("Planned blobs must be unique and sorted by SHA-256.")
    required = {
        digest
        for entry in value.manifest.entries
        for digest in (
            entry.historical_text_blob_sha256,
            entry.historical_metadata_blob_sha256,
        )
    }
    if set(blob_index) != required:
        raise ValueError("Publication plan blobs do not exactly cover manifest content.")


def build_historical_snapshot_publication_plan(
    *,
    rehearsal_report: HistoricalSnapshotCaptureRehearsalReport,
    materials: Mapping[str, HistoricalSnapshotMaterial],
) -> HistoricalSnapshotPublicationPlan:
    """Build a complete synthetic publication plan from a validated HM2.3 authority."""

    validate_historical_snapshot_capture_rehearsal_report(rehearsal_report)
    if not isinstance(materials, Mapping):
        raise HistoricalSnapshotError("materials must be keyed by historical_record_id.")

    observations = {
        item.historical_record_id: item for item in rehearsal_report.observations
    }
    if len(observations) != len(rehearsal_report.observations):
        raise HistoricalSnapshotError("HM2.3 observations contain duplicate record IDs.")

    expected_ids = set(observations)
    supplied_ids = set(materials)
    if supplied_ids != expected_ids:
        missing = sorted(expected_ids - supplied_ids)
        unexpected = sorted(supplied_ids - expected_ids)
        raise HistoricalSnapshotError(
            f"Historical material coverage mismatch; missing={missing}, unexpected={unexpected}."
        )

    blob_bytes: dict[str, bytes] = {}
    entries: list[HistoricalSnapshotEntry] = []

    for record_id in sorted(expected_ids):
        observation = observations[record_id]
        material = materials[record_id]
        if not isinstance(material, HistoricalSnapshotMaterial):
            raise HistoricalSnapshotError("materials must contain HistoricalSnapshotMaterial.")
        if material.historical_record_id != record_id:
            raise HistoricalSnapshotError("Historical material record ID does not match its key.")
        if observation.status is not HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED:
            raise HistoricalSnapshotError(
                "Historical snapshot publication requires EXACT_TEXT_VERIFIED observations."
            )
        if observation.historical_binding_class is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
            raise HistoricalSnapshotError(
                "Historical snapshot publication cannot promote provenance."
            )
        if not isinstance(material.historical_text, str):
            raise HistoricalSnapshotError("historical_text must be exact str content.")

        text_bytes = material.historical_text.encode("utf-8")
        text_sha = sha256_bytes(text_bytes)
        if observation.expected_text_sha256 != text_sha:
            raise HistoricalSnapshotError("Historical text differs from HM2.3 expected SHA-256.")
        if observation.observed_text_sha256 != text_sha:
            raise HistoricalSnapshotError("Historical text differs from HM2.3 observed SHA-256.")

        metadata_bytes = historical_metadata_canonical_bytes(material.historical_metadata)
        metadata_sha = sha256_bytes(metadata_bytes)
        metadata_fingerprint = "sha256:" + metadata_sha
        if observation.expected_metadata_fingerprint != metadata_fingerprint:
            raise HistoricalSnapshotError(
                "Historical metadata differs from HM2.3 expected fingerprint."
            )
        if observation.observed_metadata_fingerprint != metadata_fingerprint:
            raise HistoricalSnapshotError(
                "Historical metadata differs from HM2.3 observed fingerprint."
            )

        for digest, content in (
            (text_sha, text_bytes),
            (metadata_sha, metadata_bytes),
        ):
            previous = blob_bytes.setdefault(digest, content)
            if previous != content:
                raise HistoricalSnapshotError(
                    "SHA-256 collision detected between different planned bytes."
                )

        entries.append(
            HistoricalSnapshotEntry(
                historical_record_id=observation.historical_record_id,
                historical_evidence_key=observation.historical_evidence_key,
                document_name=observation.document_name,
                document_id=observation.document_id,
                page=observation.page,
                chunk_id=observation.chunk_id,
                relationship=observation.relationship,
                historical_binding_class=observation.historical_binding_class,
                historical_text_blob_sha256=text_sha,
                historical_text_byte_length=len(text_bytes),
                historical_metadata_blob_sha256=metadata_sha,
                historical_metadata_byte_length=len(metadata_bytes),
                historical_metadata_fingerprint=metadata_fingerprint,
                current_successor_evidence_key=observation.current_successor_evidence_key,
                current_successor_chunk_text_sha256=(
                    observation.current_successor_chunk_text_sha256
                ),
                binding_key_collision_risk=observation.binding_key_collision_risk,
            )
        )

    provisional = HistoricalSnapshotManifest(
        schema_version=HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION,
        case_id=rehearsal_report.case_id,
        hm1_report_id=rehearsal_report.hm1_report_id,
        pfcr1_report_id=rehearsal_report.pfcr1_report_id,
        hm2_manifest_id=rehearsal_report.hm2_manifest_id,
        hm23_rehearsal_report_id=(
            rehearsal_report.historical_snapshot_capture_rehearsal_report_id
        ),
        entries=tuple(entries),
        historical_snapshot_manifest_id="sha256:" + ("0" * 64),
    )
    manifest = replace(
        provisional,
        historical_snapshot_manifest_id=derive_sha256_id(
            historical_snapshot_manifest_identity_payload_to_dict(provisional)
        ),
    )
    plan = HistoricalSnapshotPublicationPlan(
        manifest=manifest,
        blobs=tuple(
            HistoricalSnapshotBlob(sha256_hex=digest, content=content)
            for digest, content in sorted(blob_bytes.items())
        ),
    )
    validate_historical_snapshot_publication_plan(plan)
    return plan


def historical_snapshot_manifest_path(
    *,
    store: SourceEvidenceStore,
    case_id: str,
    hm23_rehearsal_report_id: str,
) -> Path:
    """Return the separate historical namespace path without creating it."""

    if not isinstance(store, SourceEvidenceStore):
        raise TypeError("store must be SourceEvidenceStore.")
    case = canonical_uuid(case_id, field_name="case_id")
    report_id = validate_sha256_id(
        hm23_rehearsal_report_id,
        field_name="hm23_rehearsal_report_id",
    )
    root = store.root
    path = (
        root
        / "historical-snapshots"
        / "cases"
        / case
        / report_id[7:]
        / "manifest.json"
    )
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HistoricalSnapshotError("Unsafe historical snapshot path.") from exc
    return path


def _is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as exc:
        raise HistoricalSnapshotError(
            "Unable to validate historical snapshot path safety."
        ) from exc


def _verify_existing_directory(root: Path, path: Path) -> None:
    if _is_link_like(path):
        raise HistoricalSnapshotError("Unsafe historical snapshot path.")
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise HistoricalSnapshotError(
            "Unable to inspect historical snapshot directory."
        ) from exc
    if not stat.S_ISDIR(info.st_mode):
        raise HistoricalSnapshotError(
            "Historical snapshot path component is not a directory."
        )
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise HistoricalSnapshotError("Unsafe historical snapshot path.") from exc


def _ensure_directory(root: Path, directory: Path) -> None:
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise HistoricalSnapshotError("Unsafe historical snapshot path.") from exc

    current = root
    if current.exists() or current.is_symlink():
        _verify_existing_directory(root, current)
    else:
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise HistoricalSnapshotError(
                "Unable to create historical snapshot directory."
            ) from exc
        _verify_existing_directory(root, current)

    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            _verify_existing_directory(root, current)
            continue
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise HistoricalSnapshotError(
                "Unable to create historical snapshot directory."
            ) from exc
        _verify_existing_directory(root, current)


def _read_safe_file(root: Path, path: Path, *, optional: bool) -> bytes | None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise HistoricalSnapshotError("Unsafe historical snapshot path.") from exc

    current = root
    if not current.exists() and not current.is_symlink():
        if optional:
            return None
        raise HistoricalSnapshotError("Required historical snapshot manifest is missing.")
    _verify_existing_directory(root, current)

    for part in relative.parts[:-1]:
        current = current / part
        if not current.exists() and not current.is_symlink():
            if optional:
                return None
            raise HistoricalSnapshotError(
                "Required historical snapshot manifest is missing."
            )
        _verify_existing_directory(root, current)

    if not path.exists() and not path.is_symlink():
        if optional:
            return None
        raise HistoricalSnapshotError("Required historical snapshot manifest is missing.")
    if _is_link_like(path):
        raise HistoricalSnapshotError("Unsafe historical snapshot path.")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        if optional:
            return None
        raise HistoricalSnapshotError("Required historical snapshot manifest is missing.")
    except OSError as exc:
        raise HistoricalSnapshotError(
            "Unable to inspect historical snapshot manifest."
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise HistoricalSnapshotError("Historical snapshot manifest is not a regular file.")
    try:
        path.resolve(strict=True).relative_to(root)
        return path.read_bytes()
    except (OSError, ValueError) as exc:
        raise HistoricalSnapshotError(
            "Unable to read historical snapshot manifest safely."
        ) from exc


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)


def _publish_manifest_exact(root: Path, final: Path, intended: bytes) -> None:
    _ensure_directory(root, final.parent)
    staging: Path | None = None
    try:
        try:
            fd, raw_stage = tempfile.mkstemp(
                dir=final.parent,
                prefix=".historical-snapshot-stage-",
            )
            staging = Path(raw_stage)
        except OSError as exc:
            raise HistoricalSnapshotError(
                "Unable to create historical snapshot staging file."
            ) from exc

        try:
            try:
                os.chmod(staging, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(intended)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            raise

        try:
            os.link(staging, final)
            won = True
        except FileExistsError:
            won = False
        except OSError as exc:
            raise HistoricalSnapshotError(
                "Immutable historical manifest publication requires same-filesystem "
                "hard-link create-if-absent support."
            ) from exc

        actual = _read_safe_file(root, final, optional=False)
        assert actual is not None
        if actual != intended:
            raise HistoricalSnapshotError(
                "Historical snapshot manifest conflicts with an existing record."
            )
        if won:
            _fsync_directory(final.parent)
    finally:
        if staging is not None:
            try:
                staging.unlink(missing_ok=True)
            except OSError as exc:
                raise HistoricalSnapshotError(
                    "Unable to remove this invocation's historical staging file."
                ) from exc


def publish_historical_snapshot_publication_plan(
    plan: HistoricalSnapshotPublicationPlan,
    *,
    store: SourceEvidenceStore,
) -> HistoricalSnapshotManifest:
    """Publish blobs first and the corpus manifest last as the commit marker."""

    validate_historical_snapshot_publication_plan(plan)
    if not isinstance(store, SourceEvidenceStore):
        raise TypeError("store must be SourceEvidenceStore.")

    try:
        for blob in plan.blobs:
            digest = store.put_blob(blob.content)
            if digest != blob.sha256_hex:
                raise HistoricalSnapshotError("M2 returned an unexpected blob identity.")
        for blob in plan.blobs:
            if store.read_blob(blob.sha256_hex) != blob.content:
                raise HistoricalSnapshotError("Published historical blob failed verification.")
    except SourceEvidenceStoreError as exc:
        raise HistoricalSnapshotError("M2 immutable blob publication failed.") from exc

    manifest_bytes = dumps_historical_snapshot_manifest(plan.manifest).encode("utf-8")
    final = historical_snapshot_manifest_path(
        store=store,
        case_id=plan.manifest.case_id,
        hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
    )
    _publish_manifest_exact(store.root, final, manifest_bytes)
    loaded = load_historical_snapshot_manifest(
        store=store,
        case_id=plan.manifest.case_id,
        hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
    )
    if loaded != plan.manifest:
        raise HistoricalSnapshotError(
            "Reloaded historical snapshot manifest differs from publication plan."
        )
    return loaded


def load_historical_snapshot_manifest(
    *,
    store: SourceEvidenceStore,
    case_id: str,
    hm23_rehearsal_report_id: str,
) -> HistoricalSnapshotManifest | None:
    """Load the independently published historical manifest; never fall back elsewhere."""

    final = historical_snapshot_manifest_path(
        store=store,
        case_id=case_id,
        hm23_rehearsal_report_id=hm23_rehearsal_report_id,
    )
    raw = _read_safe_file(store.root, final, optional=True)
    if raw is None:
        return None
    try:
        payload = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HistoricalSnapshotError(
            "Historical snapshot manifest is not valid UTF-8."
        ) from exc
    try:
        value = loads_historical_snapshot_manifest(payload)
    except ValueError as exc:
        raise HistoricalSnapshotError(
            "Historical snapshot manifest failed canonical validation."
        ) from exc
    if value.case_id != canonical_uuid(case_id, field_name="case_id"):
        raise HistoricalSnapshotError("Historical snapshot manifest case mismatch.")
    if value.hm23_rehearsal_report_id != validate_sha256_id(
        hm23_rehearsal_report_id,
        field_name="hm23_rehearsal_report_id",
    ):
        raise HistoricalSnapshotError("Historical snapshot HM2.3 authority mismatch.")
    return value


__all__ = [
    "HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION",
    "HistoricalSnapshotBlob",
    "HistoricalSnapshotEntry",
    "HistoricalSnapshotError",
    "HistoricalSnapshotManifest",
    "HistoricalSnapshotMaterial",
    "HistoricalSnapshotPublicationPlan",
    "build_historical_snapshot_publication_plan",
    "dumps_historical_snapshot_manifest",
    "historical_metadata_canonical_bytes",
    "historical_snapshot_entry_to_dict",
    "historical_snapshot_manifest_identity_payload_to_dict",
    "historical_snapshot_manifest_path",
    "historical_snapshot_manifest_to_dict",
    "load_historical_snapshot_manifest",
    "loads_historical_snapshot_manifest",
    "publish_historical_snapshot_publication_plan",
    "validate_historical_snapshot_manifest",
    "validate_historical_snapshot_publication_plan",
]
