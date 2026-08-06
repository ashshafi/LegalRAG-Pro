"""Production-isolated rehearsal of prospective source-bound re-ingestion.

PFCR1 is deliberately a rehearsal/orchestration layer.  It reads the frozen
HM1 inventory, current PDF bytes and the active derived Chroma collection, then
uses the frozen M3/M4 implementation only inside caller-supplied disposable
staging locations.  It never mutates the production source store, production
Chroma database, frozen projections, or current documents and it contains no
cutover/apply/retirement capability.

The report describes a *prospective* source chain created from current PDF
bytes.  It must never be interpreted as retroactive proof of historical
analytical provenance.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .identity import canonical_uuid, sha256_bytes
from .migration import (
    HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
    HistoricalMigrationDecision,
    HistoricalMigrationReport,
    historical_migration_report_to_dict,
)
from .models import BindingClass, SourceDocumentManifest
from .store import SourceEvidenceStore
from .validation import validate_evidence_binding, validate_source_document_manifest

PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION = "prospective-reingestion-report/1.0"
_GOVERNED_COLLECTION_NAME = "legal_documents"
_LEGACY_CASE_ID = "__legacy__"
_M4_SOURCE_METADATA_KEYS = (
    "source_evidence_binding_id",
    "source_snapshot_id",
    "source_document_instance_id",
    "source_chunk_sha256",
    "source_page_text_sha256",
    "source_original_blob_sha256",
    "source_binding_class",
)


class ProspectiveReingestionError(RuntimeError):
    """Raised when PFCR1 cannot perform a trustworthy isolated rehearsal."""


class ProspectiveReingestionBlocker(StrEnum):
    """Deterministic PFCR1 blocker/rehearsal outcome codes."""

    HM1_REPORT_INVALID = "hm1_report_invalid"
    HM1_ACTIVE_INDEX_DRIFT = "hm1_active_index_drift"
    HM1_CURRENT_PDF_DRIFT = "hm1_current_pdf_drift"
    ACTIVE_ROW_MISSING_FROM_HM1 = "active_row_missing_from_hm1"
    HM1_ROW_MISSING_FROM_ACTIVE_INDEX = "hm1_row_missing_from_active_index"
    UNACCOUNTED_ACTIVE_POPULATION = "unaccounted_active_population"
    TARGET_ROW_DOCUMENT_UNKNOWN = "target_row_document_unknown"
    CURRENT_PDF_MISSING = "current_pdf_missing"
    AMBIGUOUS_CURRENT_PDF = "ambiguous_current_pdf"
    CURRENT_PDF_NOT_REGULAR = "current_pdf_not_regular"
    CURRENT_PDF_SYMLINK = "current_pdf_symlink"
    DUPLICATE_PROSPECTIVE_EVIDENCE_KEY = "duplicate_prospective_evidence_key"
    EXISTING_WEAKER_BINDING_OCCUPIES_KEY = "existing_weaker_binding_occupies_key"
    EXISTING_FULL_CHAIN_BINDING_MISMATCH = "existing_full_chain_binding_mismatch"
    M3_CAPTURE_FAILED = "m3_capture_failed"
    M4_INGESTION_FAILED = "m4_ingestion_failed"
    M4_BATCH_LIMIT = "m4_batch_limit"
    M4_SHADOW_CONFLICT = "m4_shadow_conflict"
    M4_SHADOW_INCOMPLETE = "m4_shadow_incomplete"
    SHADOW_COLLECTION_UNAVAILABLE = "shadow_collection_unavailable"
    SHADOW_MISSING_ROW = "shadow_missing_row"
    SHADOW_CONFLICTING_ROW = "shadow_conflicting_row"
    SHADOW_UNEXPECTED_ROW = "shadow_unexpected_row"
    SHADOW_LEGACY_ROW = "shadow_legacy_row"
    SHADOW_CASE_MISMATCH = "shadow_case_mismatch"
    SHADOW_MANIFEST_MISMATCH = "shadow_manifest_mismatch"
    STAGING_PATH_UNSAFE = "staging_path_unsafe"


@dataclass(frozen=True, slots=True)
class ProspectiveLegacyKeyMapping:
    """Text-free audit mapping from one HM1 historical key to prospective M3."""

    historical_evidence_key: str
    document_name: str | None
    prospective_candidate_key: str | None
    actual_prospective_key_exists: bool
    same_key_as_future_m3: bool | None
    binding_key_collision_risk: bool
    historical_current_chroma_text_sha256: str | None
    prospective_chunk_text_sha256: str | None
    current_text_matches_prospective_chunk: bool | None


@dataclass(frozen=True, slots=True)
class ProspectiveDocumentRehearsal:
    """One current PDF's prospective M3/M4 rehearsal result."""

    document_name: str
    current_pdf_sha256: str | None
    current_pdf_byte_length: int | None
    source_document_instance_id: str | None
    source_snapshot_id: str | None
    prospective_evidence_keys: tuple[str, ...]
    prospective_row_count: int
    shadow_exact_row_count: int
    shadow_missing_row_count: int
    shadow_conflicting_row_count: int
    capture_succeeded: bool
    m4_ingestion_succeeded: bool
    shadow_verified: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "prospective_evidence_keys", tuple(self.prospective_evidence_keys))
        object.__setattr__(self, "blockers", tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class ProspectiveReingestionReport:
    """Deterministic PFCR1 audit report; not an M1/M2 durable schema."""

    schema_version: str
    case_id: str
    hm1_report_id: str
    historical_provenance_changed: bool
    prospective_source_chain_created: bool
    active_derived_index_changed: bool
    legacy_active_row_count: int
    legacy_target_row_count: int
    legacy_collision_risk_count: int
    legacy_key_different_count: int
    current_document_count: int
    documents_capture_ready: int
    documents_blocked: int
    prospective_manifest_count: int
    prospective_row_count: int
    exact_shadow_row_count: int
    missing_shadow_row_count: int
    conflicting_shadow_row_count: int
    unexpected_shadow_row_count: int
    legacy_shadow_row_count: int
    same_key_correspondence_count: int
    changed_key_correspondence_count: int
    no_direct_correspondence_count: int
    all_rows_source_bound: bool
    all_documents_complete: bool
    all_active_collection_populations_accounted: bool
    collection_complete_for_cutover: bool
    unaccounted_active_row_ids: tuple[str, ...]
    documents: tuple[ProspectiveDocumentRehearsal, ...]
    legacy_mappings: tuple[ProspectiveLegacyKeyMapping, ...]
    blockers: tuple[str, ...]
    prospective_reingestion_report_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "unaccounted_active_row_ids", tuple(self.unaccounted_active_row_ids))
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "legacy_mappings", tuple(self.legacy_mappings))
        object.__setattr__(self, "blockers", tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class _ObservedChromaRow:
    row_id: str
    document: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class _DocumentPreflight:
    document_name: str
    path: Path | None
    sha256_hex: str | None
    byte_length: int | None
    historical_keys: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _M4SubprocessResult:
    succeeded: bool
    indexed_row_count: int | None
    blocker: str | None


@dataclass(frozen=True, slots=True)
class _CapturedDocument:
    preflight: _DocumentPreflight
    manifest: SourceDocumentManifest | None
    m4_result: _M4SubprocessResult | None
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ShadowSnapshot:
    rows: tuple[_ObservedChromaRow, ...]
    by_id: dict[str, _ObservedChromaRow]


class _NoShadowCollection:
    """Sentinel used when no disposable shadow collection was created."""


def rehearse_prospective_reingestion(
    *,
    case_id: str,
    hm1_report: HistoricalMigrationReport,
    current_documents_root: Path,
    staging_root: Path,
    active_collection: object,
) -> ProspectiveReingestionReport:
    """Rehearse prospective M3/M4 conversion in a disposable shadow generation.

    Args:
        case_id: Canonical case UUID being rehearsed.
        hm1_report: Frozen HM1 inventory/classification report for the case.
        current_documents_root: Read-only root containing current PDF candidates.
        staging_root: Caller-supplied disposable output root.  It must not overlap
            production ``db``, ``source_evidence_store``, ``report_projections``
            or ``docs``.
        active_collection: Read-only current Chroma collection used only to
            verify the HM1 snapshot and account for active populations.

    Returns:
        A deterministic report describing only prospective rehearsal state.

    Raises:
        ProspectiveReingestionError: If the HM1 report, active collection or
            staging boundary is malformed/stale in a way that makes rehearsal
            untrustworthy.
    """

    canonical_case = canonical_uuid(case_id, field_name="case_id")
    _validate_hm1_report(hm1_report, canonical_case)

    documents_root = Path(current_documents_root).expanduser().resolve(strict=False)
    stage_root = Path(staging_root).expanduser().resolve(strict=False)
    _validate_staging_boundary(stage_root, documents_root)

    active_snapshot = _observe_collection(active_collection)
    decisions = _decision_index(hm1_report, canonical_case)
    target_active_rows, unaccounted_rows = _validate_active_snapshot_against_hm1(
        active_snapshot,
        decisions,
        canonical_case,
    )

    target_keys = tuple(sorted(target_active_rows))
    target_decisions = tuple(decisions[key] for key in target_keys)
    document_preflights = _build_document_preflights(
        target_decisions=target_decisions,
        target_rows=target_active_rows,
        current_documents_root=documents_root,
    )

    # All potentially dangerous production/HM1 drift checks happen before the
    # first staging directory is created or the first M3 capture is attempted.
    fatal_preflight = tuple(
        blocker
        for item in document_preflights
        for blocker in item.blockers
        if blocker == ProspectiveReingestionBlocker.HM1_CURRENT_PDF_DRIFT.value
    )
    if fatal_preflight:
        raise ProspectiveReingestionError(
            "Current PDF bytes no longer match the frozen HM1 observation."
        )

    staging_store_root = stage_root / "source_evidence_store" / "v1"
    runtime_root = stage_root / "runtime"
    shadow_db_root = runtime_root / "db"
    stage_root.mkdir(parents=True, exist_ok=True)
    staging_store_root.parent.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)
    staging_store = SourceEvidenceStore(staging_store_root)

    captured_documents: list[_CapturedDocument] = []
    manifest_keys: dict[str, str] = {}

    for preflight in document_preflights:
        if preflight.blockers or preflight.path is None or preflight.sha256_hex is None:
            captured_documents.append(
                _CapturedDocument(
                    preflight=preflight,
                    manifest=None,
                    m4_result=None,
                    blockers=preflight.blockers,
                )
            )
            continue

        blockers: list[str] = []
        manifest: SourceDocumentManifest | None = None
        try:
            manifest = _capture_with_frozen_m3(
                preflight.path,
                case_id=canonical_case,
                store=staging_store,
            )
            validate_source_document_manifest(manifest)
            _validate_manifest_is_current_document(
                manifest,
                preflight=preflight,
                case_id=canonical_case,
            )
        except Exception:
            manifest = None
            blockers.append(ProspectiveReingestionBlocker.M3_CAPTURE_FAILED.value)

        if manifest is not None:
            try:
                _validate_manifest_bindings(
                    manifest,
                    store=staging_store,
                    decisions=decisions,
                )
            except ProspectiveReingestionError as exc:
                value = str(exc)
                known = {item.value for item in ProspectiveReingestionBlocker}
                blockers.append(
                    value
                    if value in known
                    else ProspectiveReingestionBlocker.M3_CAPTURE_FAILED.value
                )
            except Exception:
                blockers.append(ProspectiveReingestionBlocker.M3_CAPTURE_FAILED.value)

            for evidence_key in _manifest_evidence_keys(manifest):
                previous_document = manifest_keys.get(evidence_key)
                if previous_document is not None and previous_document != manifest.original_filename:
                    blockers.append(
                        ProspectiveReingestionBlocker.DUPLICATE_PROSPECTIVE_EVIDENCE_KEY.value
                    )
                else:
                    manifest_keys[evidence_key] = manifest.original_filename

        m4_result: _M4SubprocessResult | None = None
        if manifest is not None and not blockers:
            m4_result = _run_isolated_m4_ingestion(
                pdf_path=preflight.path,
                case_id=canonical_case,
                store_root=staging_store_root,
                runtime_root=runtime_root,
                expected_original_sha256=preflight.sha256_hex,
            )
            if not m4_result.succeeded:
                blockers.append(
                    m4_result.blocker
                    or ProspectiveReingestionBlocker.M4_INGESTION_FAILED.value
                )

        captured_documents.append(
            _CapturedDocument(
                preflight=preflight,
                manifest=manifest,
                m4_result=m4_result,
                blockers=tuple(sorted(set(blockers))),
            )
        )

    manifests = tuple(
        item.manifest for item in captured_documents if item.manifest is not None
    )
    shadow_client: object | None = None
    shadow_collection: object | _NoShadowCollection = _NoShadowCollection()
    shadow_open_blocker: str | None = None
    try:
        shadow_client, shadow_collection = _open_shadow_collection(shadow_db_root)
    except Exception:
        shadow_open_blocker = ProspectiveReingestionBlocker.SHADOW_COLLECTION_UNAVAILABLE.value

    try:
        report = _build_report(
            case_id=canonical_case,
            hm1_report=hm1_report,
            active_snapshot=active_snapshot,
            target_active_rows=target_active_rows,
            unaccounted_rows=unaccounted_rows,
            decisions=decisions,
            captured_documents=tuple(captured_documents),
            manifests=manifests,
            staging_store=staging_store,
            shadow_collection=shadow_collection,
            shadow_open_blocker=shadow_open_blocker,
        )
    finally:
        _close_shadow_client(shadow_client)
    return report


def prospective_reingestion_report_to_dict(
    report: ProspectiveReingestionReport,
) -> dict[str, object]:
    """Return deterministic JSON-compatible PFCR1 report data."""

    return {
        **_report_identity_payload(report),
        "prospective_reingestion_report_id": report.prospective_reingestion_report_id,
    }


def dumps_prospective_reingestion_report(report: ProspectiveReingestionReport) -> str:
    """Return canonical PFCR1 JSON with exactly one trailing newline."""

    return _canonical_json_bytes(prospective_reingestion_report_to_dict(report)).decode(
        "utf-8"
    ) + "\n"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_staging_boundary(staging_root: Path, documents_root: Path) -> None:
    project = _project_root().resolve(strict=False)
    forbidden = tuple(
        (project / relative).resolve(strict=False)
        for relative in ("db", "source_evidence_store", "report_projections", "docs")
    )
    planned_writes = (
        staging_root,
        staging_root / "source_evidence_store" / "v1",
        staging_root / "runtime",
        staging_root / "runtime" / "db",
    )
    for candidate in planned_writes:
        resolved = candidate.resolve(strict=False)
        if any(_is_same_or_below(resolved, root) for root in forbidden):
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.STAGING_PATH_UNSAFE.value
            )
    if _paths_overlap(staging_root, documents_root):
        raise ProspectiveReingestionError(
            ProspectiveReingestionBlocker.STAGING_PATH_UNSAFE.value
        )
    if staging_root.exists() and not staging_root.is_dir():
        raise ProspectiveReingestionError("staging_root must be a directory.")


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve(strict=False)
    right = right.resolve(strict=False)
    return _is_same_or_below(left, right) or _is_same_or_below(right, left)


def _is_same_or_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_hm1_report(report: HistoricalMigrationReport, case_id: str) -> None:
    if not isinstance(report, HistoricalMigrationReport):
        raise ProspectiveReingestionError(
            ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
        )
    if report.schema_version != HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION:
        raise ProspectiveReingestionError(
            ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
        )
    if canonical_uuid(report.case_id, field_name="hm1_report.case_id") != case_id:
        raise ProspectiveReingestionError("HM1 report belongs to a different case.")
    payload = historical_migration_report_to_dict(report)
    stored_id = payload.pop("historical_migration_report_id", None)
    expected_id = "sha256:" + sha256_bytes(_canonical_json_bytes(payload))
    if stored_id != expected_id:
        raise ProspectiveReingestionError(
            ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
        )


def _decision_index(
    report: HistoricalMigrationReport,
    case_id: str,
) -> dict[str, HistoricalMigrationDecision]:
    result: dict[str, HistoricalMigrationDecision] = {}
    for decision in report.decisions:
        if decision.case_id != case_id:
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
            )
        if not isinstance(decision.evidence_key, str) or not decision.evidence_key:
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
            )
        if decision.evidence_key in result:
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_REPORT_INVALID.value
            )
        result[decision.evidence_key] = decision
    return result


def _observe_collection(collection: object) -> _ShadowSnapshot:
    try:
        raw = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        raise ProspectiveReingestionError(
            "Active Chroma collection could not be read without mutation."
        ) from exc
    rows = _parse_chroma_get(raw)
    by_id = {row.row_id: row for row in rows}
    return _ShadowSnapshot(rows=rows, by_id=by_id)


def _parse_chroma_get(raw: object) -> tuple[_ObservedChromaRow, ...]:
    if not isinstance(raw, Mapping):
        raise ProspectiveReingestionError("Chroma get result is malformed.")
    ids = raw.get("ids")
    documents = raw.get("documents")
    metadatas = raw.get("metadatas")
    if not isinstance(ids, (list, tuple)):
        raise ProspectiveReingestionError("Chroma ids are malformed.")
    if not isinstance(documents, (list, tuple)) or not isinstance(metadatas, (list, tuple)):
        raise ProspectiveReingestionError("Chroma columns are malformed.")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise ProspectiveReingestionError("Chroma get columns are misaligned.")
    seen: set[str] = set()
    rows: list[_ObservedChromaRow] = []
    for row_id, document, metadata in zip(ids, documents, metadatas, strict=True):
        if not isinstance(row_id, str) or not row_id or row_id in seen:
            raise ProspectiveReingestionError("Chroma row identity is malformed or duplicated.")
        if not isinstance(document, str) or not isinstance(metadata, dict):
            raise ProspectiveReingestionError("Chroma row document/metadata is malformed.")
        seen.add(row_id)
        rows.append(
            _ObservedChromaRow(
                row_id=row_id,
                document=document,
                metadata=dict(metadata),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.row_id))


def _validate_active_snapshot_against_hm1(
    snapshot: _ShadowSnapshot,
    decisions: Mapping[str, HistoricalMigrationDecision],
    case_id: str,
) -> tuple[dict[str, _ObservedChromaRow], tuple[_ObservedChromaRow, ...]]:
    target: dict[str, _ObservedChromaRow] = {}
    unaccounted: list[_ObservedChromaRow] = []
    seen_hm1_rows: set[str] = set()

    for row in snapshot.rows:
        decision = decisions.get(row.row_id)
        if decision is None:
            unaccounted.append(row)
            continue
        observed_count = decision.observation.current_chroma_row_count
        if observed_count != 1:
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_ACTIVE_INDEX_DRIFT.value
            )
        expected_document_sha = decision.observation.current_chroma_document_sha256
        expected_metadata_sha = decision.observation.current_chroma_metadata_fingerprint
        if expected_document_sha != sha256_bytes(row.document.encode("utf-8")):
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_ACTIVE_INDEX_DRIFT.value
            )
        if expected_metadata_sha != _metadata_fingerprint(row.metadata):
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_ACTIVE_INDEX_DRIFT.value
            )
        seen_hm1_rows.add(row.row_id)
        row_case = row.metadata.get("case_id")
        if row_case not in (None, "", _LEGACY_CASE_ID, case_id):
            unaccounted.append(row)
            continue
        target[row.row_id] = row

    for key, decision in decisions.items():
        if decision.observation.current_chroma_row_count == 1 and key not in seen_hm1_rows:
            raise ProspectiveReingestionError(
                ProspectiveReingestionBlocker.HM1_ACTIVE_INDEX_DRIFT.value
            )
    return target, tuple(sorted(unaccounted, key=lambda row: row.row_id))


def _build_document_preflights(
    *,
    target_decisions: Sequence[HistoricalMigrationDecision],
    target_rows: Mapping[str, _ObservedChromaRow],
    current_documents_root: Path,
) -> tuple[_DocumentPreflight, ...]:
    inventory = _inventory_pdf_files(current_documents_root)
    keys_by_document: dict[str, list[str]] = {}
    decision_by_key = {decision.evidence_key: decision for decision in target_decisions}
    unknown_keys: list[str] = []

    for evidence_key in sorted(target_rows):
        decision = decision_by_key[evidence_key]
        row = target_rows[evidence_key]
        row_name = _metadata_string(row.metadata, "file")
        decision_name = decision.document_name
        if not decision_name or not row_name or row_name != decision_name:
            unknown_keys.append(evidence_key)
            continue
        keys_by_document.setdefault(decision_name, []).append(evidence_key)

    preflights: list[_DocumentPreflight] = []
    if unknown_keys:
        preflights.append(
            _DocumentPreflight(
                document_name="<unknown>",
                path=None,
                sha256_hex=None,
                byte_length=None,
                historical_keys=tuple(sorted(unknown_keys)),
                blockers=(ProspectiveReingestionBlocker.TARGET_ROW_DOCUMENT_UNKNOWN.value,),
            )
        )

    for document_name in sorted(keys_by_document):
        candidates = inventory.get(document_name, ())
        blockers: list[str] = []
        path: Path | None = None
        pdf_sha: str | None = None
        byte_length: int | None = None
        if not candidates:
            blockers.append(ProspectiveReingestionBlocker.CURRENT_PDF_MISSING.value)
        elif len(candidates) > 1:
            blockers.append(ProspectiveReingestionBlocker.AMBIGUOUS_CURRENT_PDF.value)
        else:
            path = candidates[0]
            if path.is_symlink():
                blockers.append(ProspectiveReingestionBlocker.CURRENT_PDF_SYMLINK.value)
            elif not path.is_file():
                blockers.append(ProspectiveReingestionBlocker.CURRENT_PDF_NOT_REGULAR.value)
            else:
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    raise ProspectiveReingestionError(
                        f"Current PDF could not be read: {document_name}"
                    ) from exc
                if not data:
                    blockers.append(ProspectiveReingestionBlocker.CURRENT_PDF_NOT_REGULAR.value)
                else:
                    pdf_sha = sha256_bytes(data)
                    byte_length = len(data)
                    observed_shas = {
                        decision_by_key[key].observation.current_pdf_sha256
                        for key in keys_by_document[document_name]
                        if decision_by_key[key].observation.current_pdf_sha256 is not None
                    }
                    observed_lengths = {
                        decision_by_key[key].observation.current_pdf_byte_length
                        for key in keys_by_document[document_name]
                        if decision_by_key[key].observation.current_pdf_byte_length is not None
                    }
                    observed_counts = {
                        decision_by_key[key].observation.current_pdf_candidate_count
                        for key in keys_by_document[document_name]
                    }
                    if observed_counts != {1}:
                        blockers.append(ProspectiveReingestionBlocker.AMBIGUOUS_CURRENT_PDF.value)
                    if observed_shas and observed_shas != {pdf_sha}:
                        blockers.append(ProspectiveReingestionBlocker.HM1_CURRENT_PDF_DRIFT.value)
                    if observed_lengths and observed_lengths != {byte_length}:
                        blockers.append(ProspectiveReingestionBlocker.HM1_CURRENT_PDF_DRIFT.value)

        preflights.append(
            _DocumentPreflight(
                document_name=document_name,
                path=path,
                sha256_hex=pdf_sha,
                byte_length=byte_length,
                historical_keys=tuple(sorted(keys_by_document[document_name])),
                blockers=tuple(sorted(set(blockers))),
            )
        )
    return tuple(preflights)


def _inventory_pdf_files(root: Path) -> dict[str, tuple[Path, ...]]:
    if not root.exists() or not root.is_dir():
        raise ProspectiveReingestionError("current_documents_root must be an existing directory.")
    grouped: dict[str, list[Path]] = {}
    try:
        candidates = sorted(root.rglob("*"), key=lambda path: str(path.relative_to(root)))
    except OSError as exc:
        raise ProspectiveReingestionError("Current document inventory could not be read.") from exc
    for candidate in candidates:
        if candidate.suffix.lower() != ".pdf":
            continue
        if candidate.is_symlink():
            grouped.setdefault(candidate.name, []).append(candidate)
            continue
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, ValueError):
            continue
        grouped.setdefault(candidate.name, []).append(resolved)
    return {
        name: tuple(sorted(paths, key=lambda path: str(path)))
        for name, paths in grouped.items()
    }


def _capture_with_frozen_m3(
    pdf_path: Path,
    *,
    case_id: str,
    store: SourceEvidenceStore,
) -> SourceDocumentManifest:
    from .capture import capture_pdf_source

    return capture_pdf_source(
        pdf_path,
        case_id=case_id,
        original_filename=pdf_path.name,
        store=store,
    )


def _validate_manifest_is_current_document(
    manifest: SourceDocumentManifest,
    *,
    preflight: _DocumentPreflight,
    case_id: str,
) -> None:
    if manifest.case_id != case_id or manifest.original_filename != preflight.document_name:
        raise ProspectiveReingestionError("M3 manifest does not match the rehearsed document.")
    if manifest.original_blob_sha256 != preflight.sha256_hex:
        raise ProspectiveReingestionError("M3 manifest does not match current PDF bytes.")
    if manifest.original_byte_length != preflight.byte_length:
        raise ProspectiveReingestionError("M3 manifest byte length does not match current PDF bytes.")


def _validate_manifest_bindings(
    manifest: SourceDocumentManifest,
    *,
    store: SourceEvidenceStore,
    decisions: Mapping[str, HistoricalMigrationDecision],
) -> None:
    for page in manifest.pages:
        for chunk in page.chunk_snapshots:
            binding = store.load_evidence_binding(manifest.case_id, chunk.evidence_key)
            if binding is None:
                raise ProspectiveReingestionError("M3 FULL_CHAIN binding is missing in staging.")
            validate_evidence_binding(binding)
            if binding.binding_class is not BindingClass.FULL_CHAIN_BOUND:
                raise ProspectiveReingestionError("M3 staging binding is not FULL_CHAIN_BOUND.")
            if (
                binding.evidence_key != chunk.evidence_key
                or binding.chunk_id != chunk.chunk_id
                or binding.source_document_instance_id != manifest.source_document_instance_id
                or binding.source_snapshot_id != manifest.source_snapshot_id
                or binding.document_name != manifest.original_filename
                or binding.page != page.page_number
                or binding.chunk_ordinal != chunk.chunk_ordinal
                or binding.original_blob_sha256 != manifest.original_blob_sha256
                or binding.page_text_sha256 != page.page_text_sha256
                or binding.chunk_text_sha256 != chunk.chunk_text_sha256
            ):
                raise ProspectiveReingestionError("M3 staging binding does not match its manifest.")

            historical = decisions.get(chunk.evidence_key)
            if historical is None or historical.existing_evidence_binding_id is None:
                continue
            if historical.existing_binding_class is not BindingClass.FULL_CHAIN_BOUND:
                raise ProspectiveReingestionError(
                    ProspectiveReingestionBlocker.EXISTING_WEAKER_BINDING_OCCUPIES_KEY.value
                )
            if historical.existing_evidence_binding_id != binding.evidence_binding_id:
                raise ProspectiveReingestionError(
                    ProspectiveReingestionBlocker.EXISTING_FULL_CHAIN_BINDING_MISMATCH.value
                )


def _run_isolated_m4_ingestion(
    *,
    pdf_path: Path,
    case_id: str,
    store_root: Path,
    runtime_root: Path,
    expected_original_sha256: str,
) -> _M4SubprocessResult:
    """Invoke frozen M4 in a child whose relative ``db`` is disposable staging."""

    source_root = Path(__file__).resolve().parents[1]
    script = r'''import json
import sys
from pathlib import Path
from source_evidence.ingestion import index_case_pdf_source_bound
from source_evidence.store import SourceEvidenceStore

pdf_path = Path(sys.argv[1])
case_id = sys.argv[2]
store_root = Path(sys.argv[3])
expected_sha = sys.argv[4]
try:
    count = index_case_pdf_source_bound(
        pdf_path,
        case_id=case_id,
        store=SourceEvidenceStore(store_root),
        expected_original_sha256=expected_sha,
    )
except Exception as exc:
    print("__PFCR1_RESULT__" + json.dumps({"ok": False, "type": type(exc).__name__, "message": str(exc)}))
    raise SystemExit(3)
print("__PFCR1_RESULT__" + json.dumps({"ok": True, "count": count}))
'''
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(source_root)
        if not current_pythonpath
        else str(source_root) + os.pathsep + current_pythonpath
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(pdf_path.resolve(strict=True)),
                case_id,
                str(store_root.resolve(strict=False)),
                expected_original_sha256,
            ],
            cwd=runtime_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return _M4SubprocessResult(
            succeeded=False,
            indexed_row_count=None,
            blocker=ProspectiveReingestionBlocker.M4_INGESTION_FAILED.value,
        )

    payload: dict[str, object] | None = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("__PFCR1_RESULT__"):
            try:
                parsed = json.loads(line[len("__PFCR1_RESULT__") :])
            except json.JSONDecodeError:
                break
            if isinstance(parsed, dict):
                payload = parsed
            break
    if completed.returncode == 0 and payload and payload.get("ok") is True:
        count = payload.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return _M4SubprocessResult(
                succeeded=False,
                indexed_row_count=None,
                blocker=ProspectiveReingestionBlocker.M4_INGESTION_FAILED.value,
            )
        return _M4SubprocessResult(True, count, None)

    error_type = str(payload.get("type") if payload else "")
    error_message = str(payload.get("message") if payload else "")
    blocker = ProspectiveReingestionBlocker.M4_INGESTION_FAILED.value
    if error_type == "SourceEvidenceIngestionConflictError":
        blocker = ProspectiveReingestionBlocker.M4_SHADOW_CONFLICT.value
    elif error_type == "SourceEvidenceIngestionIncompleteError":
        blocker = ProspectiveReingestionBlocker.M4_SHADOW_INCOMPLETE.value
    elif "maximum batch size" in error_message.casefold():
        blocker = ProspectiveReingestionBlocker.M4_BATCH_LIMIT.value
    return _M4SubprocessResult(False, None, blocker)


def _open_shadow_collection(db_root: Path) -> tuple[object, object]:
    import chromadb  # lazy: PFCR1 module import does not initialize Chroma

    client = chromadb.PersistentClient(path=str(db_root))
    collection = client.get_collection(name=_GOVERNED_COLLECTION_NAME)
    return client, collection


def _close_shadow_client(client: object | None) -> None:
    if client is None:
        return
    closer = getattr(client, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def _build_report(
    *,
    case_id: str,
    hm1_report: HistoricalMigrationReport,
    active_snapshot: _ShadowSnapshot,
    target_active_rows: Mapping[str, _ObservedChromaRow],
    unaccounted_rows: tuple[_ObservedChromaRow, ...],
    decisions: Mapping[str, HistoricalMigrationDecision],
    captured_documents: tuple[_CapturedDocument, ...],
    manifests: tuple[SourceDocumentManifest, ...],
    staging_store: SourceEvidenceStore,
    shadow_collection: object | _NoShadowCollection,
    shadow_open_blocker: str | None,
) -> ProspectiveReingestionReport:
    blockers: list[str] = []
    if unaccounted_rows:
        blockers.append(ProspectiveReingestionBlocker.UNACCOUNTED_ACTIVE_POPULATION.value)
    if shadow_open_blocker:
        blockers.append(shadow_open_blocker)

    expected_keys = tuple(
        sorted(
            {
                chunk.evidence_key
                for manifest in manifests
                for page in manifest.pages
                for chunk in page.chunk_snapshots
            }
        )
    )
    expected_key_set = set(expected_keys)

    if isinstance(shadow_collection, _NoShadowCollection):
        shadow_snapshot = _ShadowSnapshot(rows=(), by_id={})
    else:
        shadow_snapshot = _observe_collection(shadow_collection)

    actual_ids = set(shadow_snapshot.by_id)
    missing_ids = tuple(sorted(expected_key_set - actual_ids))
    unexpected_ids = tuple(sorted(actual_ids - expected_key_set))
    if missing_ids:
        blockers.append(ProspectiveReingestionBlocker.SHADOW_MISSING_ROW.value)
    if unexpected_ids:
        blockers.append(ProspectiveReingestionBlocker.SHADOW_UNEXPECTED_ROW.value)

    legacy_shadow_ids: list[str] = []
    foreign_shadow_ids: list[str] = []
    for row in shadow_snapshot.rows:
        if not _row_is_full_chain_source_bound(row):
            legacy_shadow_ids.append(row.row_id)
        row_case = row.metadata.get("case_id")
        if row_case != case_id:
            foreign_shadow_ids.append(row.row_id)
    if legacy_shadow_ids:
        blockers.append(ProspectiveReingestionBlocker.SHADOW_LEGACY_ROW.value)
    if foreign_shadow_ids:
        blockers.append(ProspectiveReingestionBlocker.SHADOW_CASE_MISMATCH.value)

    diagnostics_by_document: dict[str, tuple[int, int, int]] = {}
    total_exact = 0
    total_conflicting = 0
    if not isinstance(shadow_collection, _NoShadowCollection):
        for manifest in manifests:
            try:
                diagnostic = _inspect_with_frozen_m4(
                    manifest,
                    store=staging_store,
                    collection=shadow_collection,
                )
            except Exception:
                diagnostics_by_document[manifest.original_filename] = (0, len(_manifest_evidence_keys(manifest)), 1)
                total_conflicting += 1
                blockers.append(ProspectiveReingestionBlocker.SHADOW_MANIFEST_MISMATCH.value)
                continue
            diagnostics_by_document[manifest.original_filename] = (
                diagnostic.exact_present_count,
                diagnostic.missing_count,
                diagnostic.conflicting_count,
            )
            total_exact += diagnostic.exact_present_count
            total_conflicting += diagnostic.conflicting_count
            if diagnostic.missing_count:
                blockers.append(ProspectiveReingestionBlocker.SHADOW_MISSING_ROW.value)
            if diagnostic.conflicting_count:
                blockers.append(ProspectiveReingestionBlocker.SHADOW_CONFLICTING_ROW.value)

    document_results: list[ProspectiveDocumentRehearsal] = []
    for item in captured_documents:
        manifest = item.manifest
        doc_blockers = list(item.blockers)
        if manifest is None:
            exact = missing = conflicting = 0
            keys: tuple[str, ...] = ()
            source_document_id = source_snapshot_id = None
            prospective_count = 0
            shadow_verified = False
            capture_succeeded = False
        else:
            keys = _manifest_evidence_keys(manifest)
            source_document_id = manifest.source_document_instance_id
            source_snapshot_id = manifest.source_snapshot_id
            prospective_count = len(keys)
            capture_succeeded = True
            exact, missing, conflicting = diagnostics_by_document.get(
                manifest.original_filename,
                (0, prospective_count, 0),
            )
            if missing:
                doc_blockers.append(ProspectiveReingestionBlocker.SHADOW_MISSING_ROW.value)
            if conflicting:
                doc_blockers.append(ProspectiveReingestionBlocker.SHADOW_CONFLICTING_ROW.value)
            shadow_verified = (
                exact == prospective_count
                and missing == 0
                and conflicting == 0
                and set(keys).issubset(actual_ids)
            )
        m4_succeeded = bool(item.m4_result and item.m4_result.succeeded)
        document_results.append(
            ProspectiveDocumentRehearsal(
                document_name=item.preflight.document_name,
                current_pdf_sha256=item.preflight.sha256_hex,
                current_pdf_byte_length=item.preflight.byte_length,
                source_document_instance_id=source_document_id,
                source_snapshot_id=source_snapshot_id,
                prospective_evidence_keys=keys,
                prospective_row_count=prospective_count,
                shadow_exact_row_count=exact,
                shadow_missing_row_count=missing,
                shadow_conflicting_row_count=conflicting,
                capture_succeeded=capture_succeeded,
                m4_ingestion_succeeded=m4_succeeded,
                shadow_verified=shadow_verified,
                blockers=tuple(sorted(set(doc_blockers))),
            )
        )
        blockers.extend(doc_blockers)

    prospective_sha_by_key = {
        chunk.evidence_key: chunk.chunk_text_sha256
        for manifest in manifests
        for page in manifest.pages
        for chunk in page.chunk_snapshots
    }
    target_decisions = tuple(decisions[key] for key in sorted(target_active_rows))
    legacy_mappings = tuple(
        _build_legacy_mapping(decision, prospective_sha_by_key)
        for decision in target_decisions
    )

    same_key_count = sum(
        item.actual_prospective_key_exists and item.same_key_as_future_m3 is True
        for item in legacy_mappings
    )
    changed_key_count = sum(
        item.actual_prospective_key_exists and item.same_key_as_future_m3 is False
        for item in legacy_mappings
    )
    no_direct_count = sum(not item.actual_prospective_key_exists for item in legacy_mappings)

    collision_count = sum(item.binding_key_collision_risk for item in target_decisions)
    key_different_count = sum(
        item.m3_case_scoped_evidence_key_candidate is not None
        and item.m3_case_scoped_evidence_key_candidate != item.evidence_key
        for item in target_decisions
    )

    all_documents_complete = bool(document_results) and all(
        item.capture_succeeded
        and item.m4_ingestion_succeeded
        and item.shadow_verified
        and not item.blockers
        for item in document_results
    )
    all_source_bound = (
        bool(shadow_snapshot.rows)
        and not legacy_shadow_ids
        and not foreign_shadow_ids
        and len(shadow_snapshot.rows) == len(expected_key_set)
    )
    populations_accounted = not unaccounted_rows
    complete_for_cutover = (
        all_documents_complete
        and all_source_bound
        and populations_accounted
        and not missing_ids
        and not unexpected_ids
        and total_conflicting == 0
        and len(actual_ids) == len(expected_key_set)
        and not blockers
    )

    provisional = ProspectiveReingestionReport(
        schema_version=PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION,
        case_id=case_id,
        hm1_report_id=hm1_report.historical_migration_report_id,
        historical_provenance_changed=False,
        prospective_source_chain_created=bool(manifests),
        active_derived_index_changed=False,
        legacy_active_row_count=len(active_snapshot.rows),
        legacy_target_row_count=len(target_active_rows),
        legacy_collision_risk_count=collision_count,
        legacy_key_different_count=key_different_count,
        current_document_count=len(document_results),
        documents_capture_ready=sum(item.capture_succeeded for item in document_results),
        documents_blocked=sum(bool(item.blockers) for item in document_results),
        prospective_manifest_count=len(manifests),
        prospective_row_count=len(expected_key_set),
        exact_shadow_row_count=total_exact,
        missing_shadow_row_count=len(missing_ids),
        conflicting_shadow_row_count=total_conflicting,
        unexpected_shadow_row_count=len(unexpected_ids),
        legacy_shadow_row_count=len(legacy_shadow_ids),
        same_key_correspondence_count=same_key_count,
        changed_key_correspondence_count=changed_key_count,
        no_direct_correspondence_count=no_direct_count,
        all_rows_source_bound=all_source_bound,
        all_documents_complete=all_documents_complete,
        all_active_collection_populations_accounted=populations_accounted,
        collection_complete_for_cutover=complete_for_cutover,
        unaccounted_active_row_ids=tuple(row.row_id for row in unaccounted_rows),
        documents=tuple(sorted(document_results, key=lambda item: item.document_name)),
        legacy_mappings=tuple(sorted(legacy_mappings, key=lambda item: item.historical_evidence_key)),
        blockers=tuple(sorted(set(blockers))),
        prospective_reingestion_report_id="sha256:" + ("0" * 64),
    )
    report_id = "sha256:" + sha256_bytes(_canonical_json_bytes(_report_identity_payload(provisional)))
    return replace(
        provisional,
        prospective_reingestion_report_id=report_id,
    )


def _build_legacy_mapping(
    decision: HistoricalMigrationDecision,
    prospective_sha_by_key: Mapping[str, str],
) -> ProspectiveLegacyKeyMapping:
    candidate = decision.m3_case_scoped_evidence_key_candidate
    prospective_sha = prospective_sha_by_key.get(candidate) if candidate is not None else None
    historical_sha = decision.observation.current_chroma_document_sha256
    return ProspectiveLegacyKeyMapping(
        historical_evidence_key=decision.evidence_key,
        document_name=decision.document_name,
        prospective_candidate_key=candidate,
        actual_prospective_key_exists=prospective_sha is not None,
        same_key_as_future_m3=decision.same_key_as_future_m3,
        binding_key_collision_risk=decision.binding_key_collision_risk,
        historical_current_chroma_text_sha256=historical_sha,
        prospective_chunk_text_sha256=prospective_sha,
        current_text_matches_prospective_chunk=(
            historical_sha == prospective_sha
            if historical_sha is not None and prospective_sha is not None
            else None
        ),
    )


def _inspect_with_frozen_m4(
    manifest: SourceDocumentManifest,
    *,
    store: SourceEvidenceStore,
    collection: object,
) -> Any:
    from .ingestion import inspect_source_bound_index

    return inspect_source_bound_index(manifest, store=store, collection=collection)


def _manifest_evidence_keys(manifest: SourceDocumentManifest) -> tuple[str, ...]:
    return tuple(
        chunk.evidence_key
        for page in manifest.pages
        for chunk in page.chunk_snapshots
    )


def _row_is_full_chain_source_bound(row: _ObservedChromaRow) -> bool:
    metadata = row.metadata
    if metadata.get("source_binding_class") != BindingClass.FULL_CHAIN_BOUND.value:
        return False
    for key in _M4_SOURCE_METADATA_KEYS:
        value = metadata.get(key)
        if not isinstance(value, str) or not value:
            return False
    return True


def _metadata_string(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _metadata_fingerprint(metadata: Mapping[str, object]) -> str:
    return "sha256:" + sha256_bytes(_canonical_json_bytes(_json_compatible(dict(metadata))))


def _json_compatible(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    raise ProspectiveReingestionError("Observed metadata is not canonical JSON.")


def _report_identity_payload(report: ProspectiveReingestionReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "case_id": report.case_id,
        "hm1_report_id": report.hm1_report_id,
        "historical_provenance_changed": report.historical_provenance_changed,
        "prospective_source_chain_created": report.prospective_source_chain_created,
        "active_derived_index_changed": report.active_derived_index_changed,
        "legacy_active_row_count": report.legacy_active_row_count,
        "legacy_target_row_count": report.legacy_target_row_count,
        "legacy_collision_risk_count": report.legacy_collision_risk_count,
        "legacy_key_different_count": report.legacy_key_different_count,
        "current_document_count": report.current_document_count,
        "documents_capture_ready": report.documents_capture_ready,
        "documents_blocked": report.documents_blocked,
        "prospective_manifest_count": report.prospective_manifest_count,
        "prospective_row_count": report.prospective_row_count,
        "exact_shadow_row_count": report.exact_shadow_row_count,
        "missing_shadow_row_count": report.missing_shadow_row_count,
        "conflicting_shadow_row_count": report.conflicting_shadow_row_count,
        "unexpected_shadow_row_count": report.unexpected_shadow_row_count,
        "legacy_shadow_row_count": report.legacy_shadow_row_count,
        "same_key_correspondence_count": report.same_key_correspondence_count,
        "changed_key_correspondence_count": report.changed_key_correspondence_count,
        "no_direct_correspondence_count": report.no_direct_correspondence_count,
        "all_rows_source_bound": report.all_rows_source_bound,
        "all_documents_complete": report.all_documents_complete,
        "all_active_collection_populations_accounted": report.all_active_collection_populations_accounted,
        "collection_complete_for_cutover": report.collection_complete_for_cutover,
        "unaccounted_active_row_ids": list(report.unaccounted_active_row_ids),
        "documents": [_document_to_dict(item) for item in report.documents],
        "legacy_mappings": [_mapping_to_dict(item) for item in report.legacy_mappings],
        "blockers": list(report.blockers),
    }


def _document_to_dict(value: ProspectiveDocumentRehearsal) -> dict[str, object]:
    return {
        "document_name": value.document_name,
        "current_pdf_sha256": value.current_pdf_sha256,
        "current_pdf_byte_length": value.current_pdf_byte_length,
        "source_document_instance_id": value.source_document_instance_id,
        "source_snapshot_id": value.source_snapshot_id,
        "prospective_evidence_keys": list(value.prospective_evidence_keys),
        "prospective_row_count": value.prospective_row_count,
        "shadow_exact_row_count": value.shadow_exact_row_count,
        "shadow_missing_row_count": value.shadow_missing_row_count,
        "shadow_conflicting_row_count": value.shadow_conflicting_row_count,
        "capture_succeeded": value.capture_succeeded,
        "m4_ingestion_succeeded": value.m4_ingestion_succeeded,
        "shadow_verified": value.shadow_verified,
        "blockers": list(value.blockers),
    }


def _mapping_to_dict(value: ProspectiveLegacyKeyMapping) -> dict[str, object]:
    return {
        "historical_evidence_key": value.historical_evidence_key,
        "document_name": value.document_name,
        "prospective_candidate_key": value.prospective_candidate_key,
        "actual_prospective_key_exists": value.actual_prospective_key_exists,
        "same_key_as_future_m3": value.same_key_as_future_m3,
        "binding_key_collision_risk": value.binding_key_collision_risk,
        "historical_current_chroma_text_sha256": value.historical_current_chroma_text_sha256,
        "prospective_chunk_text_sha256": value.prospective_chunk_text_sha256,
        "current_text_matches_prospective_chunk": value.current_text_matches_prospective_chunk,
    }


def _canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProspectiveReingestionError("PFCR1 report is not canonical JSON.") from exc


__all__ = [
    "PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION",
    "ProspectiveDocumentRehearsal",
    "ProspectiveLegacyKeyMapping",
    "ProspectiveReingestionBlocker",
    "ProspectiveReingestionError",
    "ProspectiveReingestionReport",
    "dumps_prospective_reingestion_report",
    "prospective_reingestion_report_to_dict",
    "rehearse_prospective_reingestion",
]
