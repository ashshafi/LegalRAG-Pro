"""Governed historical-material reacquisition and publication-plan preparation.

HM2.5 Phase A reacquires exact historical analytical text and metadata only from a
fresh byte-verified disposable copy of the retained historical Chroma database. It
re-verifies that material against frozen HM2.2/HM2.3 authority, constructs the
frozen HM2.4 in-memory publication plan, and inspects the configured M2 blob pool
read-only. It never publishes blobs, manifests, bindings, receipts, projections, or
current Chroma state.
"""

from __future__ import annotations

import json
import os
import stat
from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from .historical_disposition import (
    HistoricalEvidenceDispositionManifest,
    HistoricalEvidenceRelationship,
    validate_historical_evidence_disposition_manifest,
)
from .historical_snapshot import (
    HistoricalSnapshotMaterial,
    HistoricalSnapshotPublicationPlan,
    build_historical_snapshot_publication_plan,
    dumps_historical_snapshot_manifest,
    historical_metadata_canonical_bytes,
    validate_historical_snapshot_publication_plan,
)
from .historical_snapshot_rehearsal import (
    HistoricalSnapshotCaptureObservation,
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

HISTORICAL_MATERIAL_PREPARATION_SCHEMA_VERSION = "historical-material-preparation/1.0"

_EXPECTED_HISTORICAL_RECORD_COUNT = 745
_EXPECTED_DISTINCT_TEXT_DIGEST_COUNT = 396
_EXPECTED_DISTINCT_METADATA_FINGERPRINT_COUNT = 745
_EXPECTED_RELATIONSHIP_COUNTS = {
    HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT: 304,
    HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT: 59,
    HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT: 30,
    HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE: 352,
}
_GOVERNED_COLLECTION_NAME = "legal_documents"
_DISPOSABLE_DATABASE_DIRECTORY = "retained-db-copy"


class HistoricalMaterialPreparationError(RuntimeError):
    """Raised when HM2.5 cannot proceed without weakening a governed invariant."""


class HistoricalMaterialBlobDisposition(StrEnum):
    """Read-only disposition of one planned immutable physical blob."""

    EXISTING_VERIFIED = "existing_verified"
    NEW_REQUIRED = "new_required"


@dataclass(frozen=True, slots=True)
class HistoricalMaterialBlobAssessment:
    """One planned physical blob classified without mutating the M2 store."""

    sha256_hex: str
    byte_length: int
    roles: tuple[str, ...]
    disposition: HistoricalMaterialBlobDisposition

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", tuple(self.roles))


@dataclass(frozen=True, slots=True)
class HistoricalMaterialPreparationReport:
    """Deterministic semantic HM2.5 Phase A report containing no historical plaintext."""

    schema_version: str
    case_id: str
    hm1_report_id: str
    pfcr1_report_id: str
    hm2_manifest_id: str
    hm23_rehearsal_report_id: str
    retained_source_tree_sha256: str
    source_store_pre_tree_sha256: str
    source_store_post_tree_sha256: str
    historical_record_count: int
    exact_text_verified_count: int
    exact_metadata_verified_count: int
    distinct_text_digest_count: int
    distinct_metadata_fingerprint_count: int
    same_key_same_text_count: int
    same_key_different_text_count: int
    changed_key_same_text_count: int
    no_direct_correspondence_count: int
    legacy_current_index_snapshot_count: int
    full_chain_count: int
    planned_manifest_id: str
    planned_manifest_file_sha256: str
    planned_manifest_byte_length: int
    planned_blob_count: int
    existing_blob_reuse_count: int
    new_blob_requirement_count: int
    blob_assessments: tuple[HistoricalMaterialBlobAssessment, ...]
    production_mutation_count: int
    historical_material_preparation_report_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "blob_assessments", tuple(self.blob_assessments))


@dataclass(frozen=True, slots=True)
class HistoricalMaterialPreparationResult:
    """Transient Phase A result; the exact-byte publication plan is not a durable report."""

    report: HistoricalMaterialPreparationReport
    publication_plan: HistoricalSnapshotPublicationPlan


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


@dataclass(frozen=True, slots=True)
class _ObservedHistoricalRow:
    row_id: str
    document: object
    metadata: dict[str, object]


# HM2.3 retained-tree identities intentionally use the frozen upstream compact JSON
# contract with no final LF. Reproduce that narrow contract locally rather than
# importing underscore-prefixed frozen helpers.
def _frozen_compact_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HistoricalMaterialPreparationError(
            "Operational tree data is not canonical JSON."
        ) from exc


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
        tree_sha256="sha256:" + sha256_bytes(_frozen_compact_json_bytes(payload)),
    )


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _is_link_like(path: Path) -> bool:
    """Return True for symlinks, junctions, or Windows reparse-point entries."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        if _lexists(path):
            info = os.lstat(path)
            attributes = getattr(info, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            if attributes & reparse_flag:
                return True
        return False
    except OSError as exc:
        raise HistoricalMaterialPreparationError(
            "Unable to validate filesystem link/reparse safety."
        ) from exc


def _existing_components(path: Path) -> tuple[Path, ...]:
    path = _absolute_path(path)
    candidates = (path, *path.parents)
    existing = tuple(item for item in candidates if _lexists(item))
    return tuple(reversed(existing))


def _reject_link_like_components(path: Path, *, label: str) -> None:
    for component in _existing_components(path):
        if _is_link_like(component):
            raise HistoricalMaterialPreparationError(
                f"{label} contains a link-like path component."
            )


def _safe_existing_directory(path: Path, *, label: str) -> Path:
    candidate = _absolute_path(path)
    _reject_link_like_components(candidate, label=label)
    if not candidate.exists() or not candidate.is_dir():
        raise HistoricalMaterialPreparationError(f"{label} is not a safe existing directory.")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise HistoricalMaterialPreparationError(f"Unable to resolve {label} safely.") from exc


def _paths_overlap(left: Path, right: Path) -> bool:
    left = _absolute_path(left)
    right = _absolute_path(right)
    return left == right or left in right.parents or right in left.parents


def _safe_workspace_root(
    workspace_root: Path,
    *,
    retained_root: Path,
    source_store_root: Path,
) -> Path:
    workspace = _absolute_path(workspace_root)
    if _lexists(workspace):
        raise HistoricalMaterialPreparationError("Disposable workspace must not already exist.")
    parent = _safe_existing_directory(workspace.parent, label="Disposable workspace parent")
    workspace = parent / workspace.name

    project_root = Path(__file__).resolve().parents[2]
    for protected, label in (
        (retained_root, "retained historical database"),
        (source_store_root, "source-evidence store"),
        (project_root, "project root"),
    ):
        if _paths_overlap(workspace, protected):
            raise HistoricalMaterialPreparationError(
                f"Disposable workspace overlaps protected {label}."
            )
    return workspace


def _build_tree_manifest(
    root: Path,
    *,
    require_exists: bool,
    label: str,
) -> _TreeManifest:
    candidate = _absolute_path(root)
    if not _lexists(candidate):
        if require_exists:
            raise HistoricalMaterialPreparationError(f"Required {label} does not exist.")
        return _make_tree_manifest(False, ())

    _reject_link_like_components(candidate, label=label)
    if not candidate.is_dir():
        raise HistoricalMaterialPreparationError(f"{label} root is not a safe directory.")

    try:
        paths = sorted(
            candidate.rglob("*"),
            key=lambda item: item.relative_to(candidate).as_posix(),
        )
    except OSError as exc:
        raise HistoricalMaterialPreparationError(f"Unable to enumerate {label}.") from exc

    entries: list[_TreeEntry] = []
    for path in paths:
        if _is_link_like(path):
            raise HistoricalMaterialPreparationError(f"{label} contains a link-like entry.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise HistoricalMaterialPreparationError(f"{label} contains a non-regular entry.")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HistoricalMaterialPreparationError(f"Unable to read {label} exactly.") from exc
        entries.append(
            _TreeEntry(
                relative_path=path.relative_to(candidate).as_posix(),
                byte_length=len(data),
                sha256_hex=sha256_bytes(data),
            )
        )
    return _make_tree_manifest(True, tuple(entries))


def _copy_tree_exact(source: Path, destination: Path, manifest: _TreeManifest) -> None:
    if _lexists(destination):
        raise HistoricalMaterialPreparationError(
            "Disposable historical database target already exists."
        )
    try:
        destination.mkdir(parents=False, exist_ok=False)
        for entry in manifest.entries:
            src = source / Path(entry.relative_path)
            dst = destination / Path(entry.relative_path)
            if _is_link_like(src) or not src.is_file():
                raise HistoricalMaterialPreparationError(
                    "Retained historical tree changed during disposable copy."
                )
            data = src.read_bytes()
            if len(data) != entry.byte_length or sha256_bytes(data) != entry.sha256_hex:
                raise HistoricalMaterialPreparationError(
                    "Retained historical tree changed during disposable copy."
                )
            dst.parent.mkdir(parents=True, exist_ok=True)
            with dst.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
    except HistoricalMaterialPreparationError:
        raise
    except OSError as exc:
        raise HistoricalMaterialPreparationError(
            "Unable to construct exact disposable historical database copy."
        ) from exc

    copied = _build_tree_manifest(
        destination,
        require_exists=True,
        label="Disposable historical database tree",
    )
    if copied != manifest:
        raise HistoricalMaterialPreparationError(
            "Disposable historical database copy is not byte-identical pre-open."
        )


def _parse_chroma_response(response: object) -> tuple[_ObservedHistoricalRow, ...]:
    if not isinstance(response, Mapping):
        raise HistoricalMaterialPreparationError("Chroma response is malformed.")

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
            raise HistoricalMaterialPreparationError(f"Chroma {label} are malformed.")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise HistoricalMaterialPreparationError(
            "Chroma ids, documents, and metadatas have inconsistent lengths."
        )

    rows: list[_ObservedHistoricalRow] = []
    for row_id, document, metadata in zip(ids, documents, metadatas, strict=True):
        if not isinstance(row_id, str) or not row_id:
            raise HistoricalMaterialPreparationError("Chroma row id is malformed.")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            raise HistoricalMaterialPreparationError("Chroma row metadata is malformed.")
        rows.append(
            _ObservedHistoricalRow(
                row_id=row_id,
                document=document,
                metadata={str(key): value for key, value in metadata.items()},
            )
        )
    return tuple(rows)


def _observe_disposable_collection(db_root: Path) -> tuple[_ObservedHistoricalRow, ...]:
    try:
        import chromadb
    except ImportError as exc:
        raise HistoricalMaterialPreparationError(
            "Chroma is unavailable for HM2.5 disposable material preparation."
        ) from exc

    client = None
    try:
        client = chromadb.PersistentClient(path=str(db_root))
        collection = client.get_collection(name=_GOVERNED_COLLECTION_NAME)
        raw = collection.get(include=["documents", "metadatas"])
        return _parse_chroma_response(raw)
    except HistoricalMaterialPreparationError:
        raise
    except Exception as exc:
        raise HistoricalMaterialPreparationError(
            "Unable to observe the disposable historical Chroma collection."
        ) from exc
    finally:
        if client is not None:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()


def _observation_index(
    report: HistoricalSnapshotCaptureRehearsalReport,
) -> dict[str, HistoricalSnapshotCaptureObservation]:
    result = {item.historical_record_id: item for item in report.observations}
    if len(result) != len(report.observations):
        raise HistoricalMaterialPreparationError(
            "HM2.3 report contains duplicate historical_record_id values."
        )
    return result


def _validate_authority_linkage(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm23_report: HistoricalSnapshotCaptureRehearsalReport,
    expected_retained_tree_sha256: str,
) -> None:
    validate_historical_evidence_disposition_manifest(hm2_manifest)
    validate_historical_snapshot_capture_rehearsal_report(hm23_report)
    expected_tree = validate_sha256_id(
        expected_retained_tree_sha256,
        field_name="expected_retained_tree_sha256",
    )
    if hm2_manifest.case_id != hm23_report.case_id:
        raise HistoricalMaterialPreparationError("HM2.2/HM2.3 case authority mismatch.")
    if hm2_manifest.hm1_report_id != hm23_report.hm1_report_id:
        raise HistoricalMaterialPreparationError("HM2.2/HM2.3 HM1 authority mismatch.")
    if hm2_manifest.pfcr1_report_id != hm23_report.pfcr1_report_id:
        raise HistoricalMaterialPreparationError("HM2.2/HM2.3 PFCR1 authority mismatch.")
    if (
        hm2_manifest.historical_evidence_disposition_manifest_id
        != hm23_report.hm2_manifest_id
    ):
        raise HistoricalMaterialPreparationError("HM2.3 does not link to the HM2.2 authority.")
    if hm23_report.retained_source_tree_sha256 != expected_tree:
        raise HistoricalMaterialPreparationError("HM2.3 retained-tree authority mismatch.")


def _validate_corpus_invariants(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm23_report: HistoricalSnapshotCaptureRehearsalReport,
) -> None:
    entries = tuple(hm2_manifest.entries)
    if len(entries) != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise HistoricalMaterialPreparationError("Historical logical record count is not 745.")
    if hm23_report.historical_record_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise HistoricalMaterialPreparationError("HM2.3 historical record count is not 745.")
    if hm23_report.exact_text_verified_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise HistoricalMaterialPreparationError("HM2.3 does not contain 745 exact text verifications.")
    if any(
        count != 0
        for count in (
            hm23_report.text_hash_mismatch_count,
            hm23_report.row_missing_count,
            hm23_report.row_ambiguous_count,
            hm23_report.metadata_mismatch_count,
            hm23_report.unreadable_count,
        )
    ):
        raise HistoricalMaterialPreparationError("HM2.3 contains blocked or mismatched outcomes.")

    text_digests = {item.historical_current_chroma_text_sha256 for item in entries}
    if None in text_digests or len(text_digests) != _EXPECTED_DISTINCT_TEXT_DIGEST_COUNT:
        raise HistoricalMaterialPreparationError("Distinct historical text digest count is not 396.")
    metadata_fingerprints = {item.historical_metadata_fingerprint for item in entries}
    if (
        None in metadata_fingerprints
        or len(metadata_fingerprints) != _EXPECTED_DISTINCT_METADATA_FINGERPRINT_COUNT
    ):
        raise HistoricalMaterialPreparationError(
            "Distinct historical metadata fingerprint count is not 745."
        )

    relationships = Counter(item.relationship for item in entries)
    if dict(relationships) != _EXPECTED_RELATIONSHIP_COUNTS:
        raise HistoricalMaterialPreparationError(
            "Historical relationship partition is not 304/59/30/352."
        )
    if any(
        item.historical_binding_class is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        for item in entries
    ):
        raise HistoricalMaterialPreparationError(
            "Historical provenance class is not uniformly LEGACY_CURRENT_INDEX_SNAPSHOT."
        )

    observation_ids = {item.historical_record_id for item in hm23_report.observations}
    entry_ids = {item.historical_record_id for item in entries}
    if observation_ids != entry_ids:
        raise HistoricalMaterialPreparationError("HM2.2/HM2.3 historical identity coverage differs.")


def _verify_observation_matches_entry(entry: object, observation: object) -> None:
    expected_pairs = (
        ("historical_evidence_key", entry.historical_evidence_key, observation.historical_evidence_key),
        ("relationship", entry.relationship, observation.relationship),
        ("document_name", entry.document_name, observation.document_name),
        ("document_id", entry.document_id, observation.document_id),
        ("page", entry.page, observation.page),
        ("chunk_id", entry.chunk_id, observation.chunk_id),
        ("historical_binding_class", entry.historical_binding_class, observation.historical_binding_class),
        (
            "expected_text_sha256",
            entry.historical_current_chroma_text_sha256,
            observation.expected_text_sha256,
        ),
        (
            "expected_metadata_fingerprint",
            entry.historical_metadata_fingerprint,
            observation.expected_metadata_fingerprint,
        ),
        (
            "current_successor_evidence_key",
            entry.current_successor_evidence_key,
            observation.current_successor_evidence_key,
        ),
        (
            "current_successor_chunk_text_sha256",
            entry.current_successor_chunk_text_sha256,
            observation.current_successor_chunk_text_sha256,
        ),
        (
            "binding_key_collision_risk",
            entry.binding_key_collision_risk,
            observation.binding_key_collision_risk,
        ),
    )
    for field_name, expected, observed in expected_pairs:
        if expected != observed:
            raise HistoricalMaterialPreparationError(
                f"HM2.2/HM2.3 record authority mismatch: {field_name}."
            )
    if observation.status is not HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED:
        raise HistoricalMaterialPreparationError("Historical observation is not EXACT_TEXT_VERIFIED.")
    if observation.observed_row_count != 1:
        raise HistoricalMaterialPreparationError("Historical observation row count is not exactly one.")
    if observation.observed_row_id != entry.historical_evidence_key:
        raise HistoricalMaterialPreparationError("Historical observation row identity mismatch.")
    if observation.blockers:
        raise HistoricalMaterialPreparationError("Historical observation contains blockers.")


def _build_materials(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm23_report: HistoricalSnapshotCaptureRehearsalReport,
    rows: tuple[_ObservedHistoricalRow, ...],
) -> dict[str, HistoricalSnapshotMaterial]:
    observations = _observation_index(hm23_report)
    rows_by_id: dict[str, list[_ObservedHistoricalRow]] = {}
    for row in rows:
        rows_by_id.setdefault(row.row_id, []).append(row)

    materials: dict[str, HistoricalSnapshotMaterial] = {}
    for entry in sorted(hm2_manifest.entries, key=lambda item: item.historical_record_id):
        observation = observations.get(entry.historical_record_id)
        if observation is None:
            raise HistoricalMaterialPreparationError("HM2.3 observation is missing.")
        _verify_observation_matches_entry(entry, observation)

        matches = tuple(rows_by_id.get(entry.historical_evidence_key, ()))
        if not matches:
            raise HistoricalMaterialPreparationError("Historical row is missing during reacquisition.")
        if len(matches) != 1:
            raise HistoricalMaterialPreparationError("Historical row is ambiguous during reacquisition.")
        row = matches[0]
        if not isinstance(row.document, str):
            raise HistoricalMaterialPreparationError("Historical text is unreadable during reacquisition.")

        try:
            metadata_bytes = historical_metadata_canonical_bytes(row.metadata)
        except Exception as exc:
            raise HistoricalMaterialPreparationError(
                "Historical metadata cannot be canonicalized during reacquisition."
            ) from exc
        metadata_fingerprint = "sha256:" + sha256_bytes(metadata_bytes)
        if metadata_fingerprint != entry.historical_metadata_fingerprint:
            raise HistoricalMaterialPreparationError("Historical metadata differs from HM2.2 authority.")
        if metadata_fingerprint != observation.expected_metadata_fingerprint:
            raise HistoricalMaterialPreparationError("Historical metadata differs from HM2.3 expected authority.")
        if metadata_fingerprint != observation.observed_metadata_fingerprint:
            raise HistoricalMaterialPreparationError("Historical metadata differs from HM2.3 observed authority.")

        text_sha = sha256_bytes(row.document.encode("utf-8"))
        if text_sha != entry.historical_current_chroma_text_sha256:
            raise HistoricalMaterialPreparationError("Historical text differs from HM2.2 authority.")
        if text_sha != observation.expected_text_sha256:
            raise HistoricalMaterialPreparationError("Historical text differs from HM2.3 expected authority.")
        if text_sha != observation.observed_text_sha256:
            raise HistoricalMaterialPreparationError("Historical text differs from HM2.3 observed authority.")

        materials[entry.historical_record_id] = HistoricalSnapshotMaterial(
            historical_record_id=entry.historical_record_id,
            historical_text=row.document,
            historical_metadata=row.metadata,
        )

    if len(materials) != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise HistoricalMaterialPreparationError("Historical material coverage is not exactly 745.")
    return materials


def _blob_roles(plan: HistoricalSnapshotPublicationPlan) -> dict[str, tuple[str, ...]]:
    roles: dict[str, set[str]] = {blob.sha256_hex: set() for blob in plan.blobs}
    for entry in plan.manifest.entries:
        roles[entry.historical_text_blob_sha256] |= {"historical_text"}
        roles[entry.historical_metadata_blob_sha256] |= {"historical_metadata"}
    return {digest: tuple(sorted(value)) for digest, value in roles.items()}


def _planned_blob_path(store: SourceEvidenceStore, digest: str) -> Path:
    value = validate_sha256_hex(digest, field_name="planned_blob_sha256")
    return store.root / "blobs" / "sha256" / value[:2] / value


def _assess_planned_blobs_read_only(
    *,
    store: SourceEvidenceStore,
    plan: HistoricalSnapshotPublicationPlan,
) -> tuple[HistoricalMaterialBlobAssessment, ...]:
    roles = _blob_roles(plan)
    assessments: list[HistoricalMaterialBlobAssessment] = []
    for blob in plan.blobs:
        path = _planned_blob_path(store, blob.sha256_hex)
        if not _lexists(path):
            disposition = HistoricalMaterialBlobDisposition.NEW_REQUIRED
        else:
            _reject_link_like_components(path, label="Source-evidence planned blob path")
            if not path.is_file():
                raise HistoricalMaterialPreparationError(
                    "Existing planned source-evidence blob path is not a regular file."
                )
            try:
                existing = store.read_blob(blob.sha256_hex)
            except (SourceEvidenceStoreError, OSError, ValueError) as exc:
                raise HistoricalMaterialPreparationError(
                    "Existing source-evidence blob failed immutable verification."
                ) from exc
            if existing != blob.content:
                raise HistoricalMaterialPreparationError(
                    "Existing source-evidence blob bytes differ from the planned bytes."
                )
            disposition = HistoricalMaterialBlobDisposition.EXISTING_VERIFIED
        assessments.append(
            HistoricalMaterialBlobAssessment(
                sha256_hex=blob.sha256_hex,
                byte_length=len(blob.content),
                roles=roles[blob.sha256_hex],
                disposition=disposition,
            )
        )
    return tuple(assessments)


def historical_material_blob_assessment_to_dict(
    value: HistoricalMaterialBlobAssessment,
) -> dict[str, object]:
    return {
        "sha256_hex": value.sha256_hex,
        "byte_length": value.byte_length,
        "roles": list(value.roles),
        "disposition": value.disposition.value,
    }


def historical_material_preparation_report_identity_payload_to_dict(
    value: HistoricalMaterialPreparationReport,
) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "hm1_report_id": value.hm1_report_id,
        "pfcr1_report_id": value.pfcr1_report_id,
        "hm2_manifest_id": value.hm2_manifest_id,
        "hm23_rehearsal_report_id": value.hm23_rehearsal_report_id,
        "retained_source_tree_sha256": value.retained_source_tree_sha256,
        "source_store_pre_tree_sha256": value.source_store_pre_tree_sha256,
        "source_store_post_tree_sha256": value.source_store_post_tree_sha256,
        "historical_record_count": value.historical_record_count,
        "exact_text_verified_count": value.exact_text_verified_count,
        "exact_metadata_verified_count": value.exact_metadata_verified_count,
        "distinct_text_digest_count": value.distinct_text_digest_count,
        "distinct_metadata_fingerprint_count": value.distinct_metadata_fingerprint_count,
        "same_key_same_text_count": value.same_key_same_text_count,
        "same_key_different_text_count": value.same_key_different_text_count,
        "changed_key_same_text_count": value.changed_key_same_text_count,
        "no_direct_correspondence_count": value.no_direct_correspondence_count,
        "legacy_current_index_snapshot_count": value.legacy_current_index_snapshot_count,
        "full_chain_count": value.full_chain_count,
        "planned_manifest_id": value.planned_manifest_id,
        "planned_manifest_file_sha256": value.planned_manifest_file_sha256,
        "planned_manifest_byte_length": value.planned_manifest_byte_length,
        "planned_blob_count": value.planned_blob_count,
        "existing_blob_reuse_count": value.existing_blob_reuse_count,
        "new_blob_requirement_count": value.new_blob_requirement_count,
        "blob_assessments": [
            historical_material_blob_assessment_to_dict(item)
            for item in value.blob_assessments
        ],
        "production_mutation_count": value.production_mutation_count,
    }


def historical_material_preparation_report_to_dict(
    value: HistoricalMaterialPreparationReport,
) -> dict[str, object]:
    return {
        **historical_material_preparation_report_identity_payload_to_dict(value),
        "historical_material_preparation_report_id": (
            value.historical_material_preparation_report_id
        ),
    }


def validate_historical_material_preparation_report(
    value: HistoricalMaterialPreparationReport,
) -> None:
    if not isinstance(value, HistoricalMaterialPreparationReport):
        raise ValueError("value must be HistoricalMaterialPreparationReport.")
    if value.schema_version != HISTORICAL_MATERIAL_PREPARATION_SCHEMA_VERSION:
        raise ValueError("Unsupported HM2.5 preparation schema_version.")
    canonical_uuid(value.case_id, field_name="case_id")
    for field_name, identifier in (
        ("hm1_report_id", value.hm1_report_id),
        ("pfcr1_report_id", value.pfcr1_report_id),
        ("hm2_manifest_id", value.hm2_manifest_id),
        ("hm23_rehearsal_report_id", value.hm23_rehearsal_report_id),
        ("retained_source_tree_sha256", value.retained_source_tree_sha256),
        ("source_store_pre_tree_sha256", value.source_store_pre_tree_sha256),
        ("source_store_post_tree_sha256", value.source_store_post_tree_sha256),
        ("planned_manifest_id", value.planned_manifest_id),
    ):
        validate_sha256_id(identifier, field_name=field_name)
    validate_sha256_hex(
        value.planned_manifest_file_sha256,
        field_name="planned_manifest_file_sha256",
    )
    if value.source_store_pre_tree_sha256 != value.source_store_post_tree_sha256:
        raise ValueError("Source-evidence store changed during preparation.")
    if value.production_mutation_count != 0:
        raise ValueError("HM2.5 Phase A production mutation count must be zero.")
    if value.historical_record_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise ValueError("historical_record_count must be 745.")
    if value.exact_text_verified_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise ValueError("exact_text_verified_count must be 745.")
    if value.exact_metadata_verified_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise ValueError("exact_metadata_verified_count must be 745.")
    if value.distinct_text_digest_count != _EXPECTED_DISTINCT_TEXT_DIGEST_COUNT:
        raise ValueError("distinct_text_digest_count must be 396.")
    if (
        value.distinct_metadata_fingerprint_count
        != _EXPECTED_DISTINCT_METADATA_FINGERPRINT_COUNT
    ):
        raise ValueError("distinct_metadata_fingerprint_count must be 745.")
    if (
        value.same_key_same_text_count,
        value.same_key_different_text_count,
        value.changed_key_same_text_count,
        value.no_direct_correspondence_count,
    ) != (304, 59, 30, 352):
        raise ValueError("Historical relationship counts are not canonical.")
    if value.legacy_current_index_snapshot_count != _EXPECTED_HISTORICAL_RECORD_COUNT:
        raise ValueError("Historical legacy binding count must be 745.")
    if value.full_chain_count != 0:
        raise ValueError("Historical FULL_CHAIN count must remain zero.")
    if value.planned_manifest_byte_length <= 0 or value.planned_blob_count <= 0:
        raise ValueError("Planned manifest/blob counts must be positive.")
    if value.existing_blob_reuse_count + value.new_blob_requirement_count != value.planned_blob_count:
        raise ValueError("Blob disposition counts do not cover the publication plan.")
    if len(value.blob_assessments) != value.planned_blob_count:
        raise ValueError("Blob assessments do not cover the publication plan.")

    previous: str | None = None
    seen: set[str] = set()
    existing = 0
    new = 0
    for item in value.blob_assessments:
        if not isinstance(item, HistoricalMaterialBlobAssessment):
            raise ValueError("blob_assessments contain an invalid value.")
        validate_sha256_hex(item.sha256_hex, field_name="blob_assessment.sha256_hex")
        if type(item.byte_length) is not int or item.byte_length <= 0:
            raise ValueError("blob assessment byte_length must be positive.")
        if not item.roles or tuple(sorted(set(item.roles))) != item.roles:
            raise ValueError("blob assessment roles must be non-empty, unique, and sorted.")
        if not set(item.roles) <= {"historical_text", "historical_metadata"}:
            raise ValueError("blob assessment contains an unsupported role.")
        if item.sha256_hex in seen:
            raise ValueError("blob assessment SHA-256 values must be unique.")
        if previous is not None and item.sha256_hex <= previous:
            raise ValueError("blob assessments must use canonical SHA-256 order.")
        seen |= {item.sha256_hex}
        previous = item.sha256_hex
        if item.disposition is HistoricalMaterialBlobDisposition.EXISTING_VERIFIED:
            existing += 1
        elif item.disposition is HistoricalMaterialBlobDisposition.NEW_REQUIRED:
            new += 1
        else:
            raise ValueError("Unsupported blob disposition.")
    if existing != value.existing_blob_reuse_count or new != value.new_blob_requirement_count:
        raise ValueError("Blob disposition summary counts are inconsistent.")

    validate_sha256_id(
        value.historical_material_preparation_report_id,
        field_name="historical_material_preparation_report_id",
    )
    expected_id = derive_sha256_id(
        historical_material_preparation_report_identity_payload_to_dict(value)
    )
    if value.historical_material_preparation_report_id != expected_id:
        raise ValueError("historical_material_preparation_report_id is not canonical.")


def dumps_historical_material_preparation_report(
    value: HistoricalMaterialPreparationReport,
) -> str:
    """Return M1-canonical semantic HM2.5 report JSON with exactly one final LF."""

    validate_historical_material_preparation_report(value)
    return canonical_json_bytes(historical_material_preparation_report_to_dict(value)).decode(
        "utf-8"
    )


def _make_preparation_report(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm23_report: HistoricalSnapshotCaptureRehearsalReport,
    source_store_pre: _TreeManifest,
    source_store_post: _TreeManifest,
    plan: HistoricalSnapshotPublicationPlan,
    assessments: tuple[HistoricalMaterialBlobAssessment, ...],
) -> HistoricalMaterialPreparationReport:
    if source_store_post != source_store_pre:
        raise HistoricalMaterialPreparationError(
            "Source-evidence store changed during HM2.5 preparation."
        )
    relationships = Counter(item.relationship for item in hm2_manifest.entries)
    manifest_bytes = dumps_historical_snapshot_manifest(plan.manifest).encode("utf-8")
    existing_count = sum(
        item.disposition is HistoricalMaterialBlobDisposition.EXISTING_VERIFIED
        for item in assessments
    )
    new_count = sum(
        item.disposition is HistoricalMaterialBlobDisposition.NEW_REQUIRED
        for item in assessments
    )
    provisional = HistoricalMaterialPreparationReport(
        schema_version=HISTORICAL_MATERIAL_PREPARATION_SCHEMA_VERSION,
        case_id=hm2_manifest.case_id,
        hm1_report_id=hm2_manifest.hm1_report_id,
        pfcr1_report_id=hm2_manifest.pfcr1_report_id,
        hm2_manifest_id=hm2_manifest.historical_evidence_disposition_manifest_id,
        hm23_rehearsal_report_id=(
            hm23_report.historical_snapshot_capture_rehearsal_report_id
        ),
        retained_source_tree_sha256=hm23_report.retained_source_tree_sha256,
        source_store_pre_tree_sha256=source_store_pre.tree_sha256,
        source_store_post_tree_sha256=source_store_post.tree_sha256,
        historical_record_count=len(hm2_manifest.entries),
        exact_text_verified_count=hm23_report.exact_text_verified_count,
        exact_metadata_verified_count=len(hm2_manifest.entries),
        distinct_text_digest_count=len(
            {item.historical_current_chroma_text_sha256 for item in hm2_manifest.entries}
        ),
        distinct_metadata_fingerprint_count=len(
            {item.historical_metadata_fingerprint for item in hm2_manifest.entries}
        ),
        same_key_same_text_count=relationships[
            HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT
        ],
        same_key_different_text_count=relationships[
            HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT
        ],
        changed_key_same_text_count=relationships[
            HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT
        ],
        no_direct_correspondence_count=relationships[
            HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE
        ],
        legacy_current_index_snapshot_count=sum(
            item.historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
            for item in hm2_manifest.entries
        ),
        full_chain_count=sum(
            item.historical_binding_class is BindingClass.FULL_CHAIN_BOUND
            for item in hm2_manifest.entries
        ),
        planned_manifest_id=plan.manifest.historical_snapshot_manifest_id,
        planned_manifest_file_sha256=sha256_bytes(manifest_bytes),
        planned_manifest_byte_length=len(manifest_bytes),
        planned_blob_count=len(plan.blobs),
        existing_blob_reuse_count=existing_count,
        new_blob_requirement_count=new_count,
        blob_assessments=assessments,
        production_mutation_count=0,
        historical_material_preparation_report_id="sha256:" + ("0" * 64),
    )
    report = replace(
        provisional,
        historical_material_preparation_report_id=derive_sha256_id(
            historical_material_preparation_report_identity_payload_to_dict(provisional)
        ),
    )
    validate_historical_material_preparation_report(report)
    return report


def prepare_historical_snapshot_publication_plan(
    *,
    hm2_manifest: HistoricalEvidenceDispositionManifest,
    hm23_report: HistoricalSnapshotCaptureRehearsalReport,
    retained_db_root: Path,
    workspace_root: Path,
    expected_retained_tree_sha256: str,
    source_store: SourceEvidenceStore,
) -> HistoricalMaterialPreparationResult:
    """Reacquire exact historical material and return a validated plan without publishing.

    The retained database is hashed and copied byte-for-byte before any Chroma open.
    Only the fresh disposable copy is observed. Exact material is checked against
    HM2.2 and HM2.3 and supplied to the frozen HM2.4 in-memory builder. The M2
    source store is inspected read-only before and after blob overlap assessment.
    Any mismatch fails closed and leaves the disposable state available for
    quarantine evidence.
    """

    if not isinstance(source_store, SourceEvidenceStore):
        raise TypeError("source_store must be SourceEvidenceStore.")
    _validate_authority_linkage(
        hm2_manifest=hm2_manifest,
        hm23_report=hm23_report,
        expected_retained_tree_sha256=expected_retained_tree_sha256,
    )
    _validate_corpus_invariants(hm2_manifest=hm2_manifest, hm23_report=hm23_report)

    retained = _safe_existing_directory(retained_db_root, label="Retained historical database")
    workspace = _safe_workspace_root(
        workspace_root,
        retained_root=retained,
        source_store_root=source_store.root,
    )

    retained_pre = _build_tree_manifest(
        retained,
        require_exists=True,
        label="Retained historical database tree",
    )
    if retained_pre.tree_sha256 != expected_retained_tree_sha256:
        raise HistoricalMaterialPreparationError(
            "Retained historical database tree does not match approved authority."
        )

    source_store_pre = _build_tree_manifest(
        source_store.root,
        require_exists=False,
        label="Source-evidence store tree",
    )

    try:
        workspace.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise HistoricalMaterialPreparationError(
            "Unable to create the fresh disposable HM2.5 workspace."
        ) from exc
    disposable = workspace / _DISPOSABLE_DATABASE_DIRECTORY
    _copy_tree_exact(retained, disposable, retained_pre)

    retained_after_copy = _build_tree_manifest(
        retained,
        require_exists=True,
        label="Retained historical database tree",
    )
    if retained_after_copy != retained_pre:
        raise HistoricalMaterialPreparationError(
            "Retained historical database changed during disposable-copy construction."
        )
    disposable_pre_open = _build_tree_manifest(
        disposable,
        require_exists=True,
        label="Disposable historical database tree",
    )
    if disposable_pre_open != retained_pre:
        raise HistoricalMaterialPreparationError(
            "Disposable historical database is not exact before first Chroma open."
        )

    rows = _observe_disposable_collection(disposable)

    retained_post = _build_tree_manifest(
        retained,
        require_exists=True,
        label="Retained historical database tree",
    )
    if retained_post != retained_pre:
        raise HistoricalMaterialPreparationError(
            "Retained historical database changed during disposable observation."
        )

    materials = _build_materials(
        hm2_manifest=hm2_manifest,
        hm23_report=hm23_report,
        rows=rows,
    )
    try:
        plan = build_historical_snapshot_publication_plan(
            rehearsal_report=hm23_report,
            materials=materials,
        )
        validate_historical_snapshot_publication_plan(plan)
    except Exception as exc:
        raise HistoricalMaterialPreparationError(
            "Frozen HM2.4 publication-plan construction failed."
        ) from exc

    assessments = _assess_planned_blobs_read_only(store=source_store, plan=plan)
    source_store_post = _build_tree_manifest(
        source_store.root,
        require_exists=False,
        label="Source-evidence store tree",
    )
    if source_store_post != source_store_pre:
        raise HistoricalMaterialPreparationError(
            "Source-evidence store changed during HM2.5 preparation."
        )

    report = _make_preparation_report(
        hm2_manifest=hm2_manifest,
        hm23_report=hm23_report,
        source_store_pre=source_store_pre,
        source_store_post=source_store_post,
        plan=plan,
        assessments=assessments,
    )
    return HistoricalMaterialPreparationResult(report=report, publication_plan=plan)


__all__ = [
    "HISTORICAL_MATERIAL_PREPARATION_SCHEMA_VERSION",
    "HistoricalMaterialBlobAssessment",
    "HistoricalMaterialBlobDisposition",
    "HistoricalMaterialPreparationError",
    "HistoricalMaterialPreparationReport",
    "HistoricalMaterialPreparationResult",
    "dumps_historical_material_preparation_report",
    "historical_material_blob_assessment_to_dict",
    "historical_material_preparation_report_identity_payload_to_dict",
    "historical_material_preparation_report_to_dict",
    "prepare_historical_snapshot_publication_plan",
    "validate_historical_material_preparation_report",
]
