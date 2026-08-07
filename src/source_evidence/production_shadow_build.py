"""Production prospective source capture and inactive shadow-index construction.

PFCR2 is a build-only orchestration layer over the frozen HM1/PFCR1/M2/M3/M4
boundaries.  It may publish exact prospective M2/M3 source authority into the
production source-evidence store and may construct a replacement
``legal_documents`` collection in a caller-supplied inactive database
generation.  It never activates that database, mutates the active production
Chroma database, rewrites current documents or projections, publishes M5/M6
records, or performs historical backfill.

A successful PFCR2 report means only that the prospective source graph and an
inactive derived index have been built and verified.  PFCR3 remains the sole
future place for any active-database handoff.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from .identity import canonical_uuid, sha256_bytes, validate_sha256_id
from .migration import HistoricalMigrationReport
from .models import BindingClass, EvidenceBinding, SourceDocumentManifest
from .reingestion_transition import (
    ProspectiveDocumentRehearsal,
    ProspectiveReingestionReport,
    rehearse_prospective_reingestion,
)
from .store import SourceEvidenceStore, SourceEvidenceStoreError
from .validation import validate_evidence_binding, validate_source_document_manifest

PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION = "production-shadow-build-report/1.0"
_FROZEN_BASELINE_COMMIT = "e8897f37f55670fe460f6e53e2a1a25eb4f340f8"
_GOVERNED_COLLECTION_NAME = "legal_documents"
_M4_SOURCE_METADATA_KEYS = (
    "source_evidence_binding_id",
    "source_snapshot_id",
    "source_document_instance_id",
    "source_chunk_sha256",
    "source_page_text_sha256",
    "source_original_blob_sha256",
    "source_binding_class",
)
_RUNTIME_SHADOW_NAMES = {
    "config.py",
    "models.py",
    "openai.py",
    "chromadb.py",
    "config",
    "models",
    "openai",
    "chromadb",
}


class ProductionShadowBuildError(RuntimeError):
    """Raised when PFCR2 cannot proceed without violating its frozen boundary."""


class ProductionShadowBuildBlocker(StrEnum):
    """Deterministic PFCR2 blocker codes."""

    PATH_UNSAFE = "path_unsafe"
    RUNTIME_SHADOWING = "runtime_shadowing"
    FRESH_PFCR1_ID_MISMATCH = "fresh_pfcr1_id_mismatch"
    FRESH_PFCR1_INCOMPLETE = "fresh_pfcr1_incomplete"
    PREFLIGHT_CHANGED_ACTIVE_DB = "preflight_changed_active_db"
    PREFLIGHT_CHANGED_DOCS = "preflight_changed_docs"
    PREFLIGHT_CHANGED_REPORT_PROJECTIONS = "preflight_changed_report_projections"
    PROSPECTIVE_PLAN_MISMATCH = "prospective_plan_mismatch"
    EXISTING_WEAKER_BINDING_OCCUPIES_KEY = "existing_weaker_binding_occupies_key"
    EXISTING_FULL_CHAIN_BINDING_MISMATCH = "existing_full_chain_binding_mismatch"
    EXISTING_MANIFEST_MISMATCH = "existing_manifest_mismatch"
    BACKUP_VERIFICATION_FAILED = "backup_verification_failed"
    M4_INGESTION_FAILED = "m4_ingestion_failed"
    M4_BATCH_LIMIT = "m4_batch_limit"
    M4_SHADOW_CONFLICT = "m4_shadow_conflict"
    M4_SHADOW_INCOMPLETE = "m4_shadow_incomplete"
    PRODUCTION_MANIFEST_MISMATCH = "production_manifest_mismatch"
    PRODUCTION_BINDING_MISMATCH = "production_binding_mismatch"
    SHADOW_UNAVAILABLE = "shadow_unavailable"
    SHADOW_MISSING_ROW = "shadow_missing_row"
    SHADOW_CONFLICTING_ROW = "shadow_conflicting_row"
    SHADOW_UNEXPECTED_ROW = "shadow_unexpected_row"
    SHADOW_LEGACY_ROW = "shadow_legacy_row"
    SHADOW_CASE_MISMATCH = "shadow_case_mismatch"
    SOURCE_STORE_PREEXISTING_CHANGED = "source_store_preexisting_changed"
    SOURCE_STORE_PREEXISTING_DELETED = "source_store_preexisting_deleted"
    SOURCE_STORE_UNEXPECTED_NEW_OBJECT = "source_store_unexpected_new_object"
    ANALYSIS_RECEIPT_CREATED = "analysis_receipt_created"
    PROJECTION_BINDING_CREATED = "projection_binding_created"
    ACTIVE_DB_CHANGED = "active_db_changed"
    DOCS_CHANGED = "docs_changed"
    REPORT_PROJECTIONS_CHANGED = "report_projections_changed"


@dataclass(frozen=True, slots=True)
class ProductionShadowDocumentResult:
    """One document's production prospective source/shadow build result."""

    document_name: str
    current_pdf_sha256: str
    current_pdf_byte_length: int
    source_document_instance_id: str
    source_snapshot_id: str
    prospective_evidence_keys: tuple[str, ...]
    prospective_row_count: int
    m4_indexed_row_count: int | None
    production_manifest_verified: bool
    production_bindings_verified: bool
    shadow_verified: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "prospective_evidence_keys", tuple(self.prospective_evidence_keys))
        object.__setattr__(self, "blockers", tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class ProductionShadowBuildReport:
    """Deterministic PFCR2 build report; not an M1/M2 durable schema."""

    schema_version: str
    case_id: str
    baseline_commit: str
    hm1_report_id: str
    approved_pfcr1_report_id: str
    fresh_pfcr1_report_id: str
    historical_provenance_changed: bool
    active_derived_index_changed: bool
    production_source_chain_created: bool
    inactive_shadow_created: bool
    legacy_active_row_count: int
    legacy_collision_risk_count: int
    legacy_key_different_count: int
    current_document_count: int
    production_manifest_count: int
    production_prospective_row_count: int
    shadow_exact_row_count: int
    shadow_missing_row_count: int
    shadow_conflicting_row_count: int
    shadow_unexpected_row_count: int
    shadow_legacy_row_count: int
    preexisting_source_store_file_count: int
    new_source_store_file_count: int
    modified_preexisting_source_store_file_count: int
    deleted_preexisting_source_store_file_count: int
    new_analysis_receipt_count: int
    new_projection_binding_count: int
    active_db_unchanged: bool
    docs_unchanged: bool
    report_projections_unchanged: bool
    source_store_append_only_valid: bool
    backup_verified: bool
    all_documents_production_verified: bool
    shadow_exact_set_verified: bool
    shadow_complete_for_pfcr3: bool
    documents: tuple[ProductionShadowDocumentResult, ...]
    blockers: tuple[str, ...]
    active_db_pre_tree_sha256: str
    active_db_backup_tree_sha256: str
    docs_pre_tree_sha256: str
    report_projections_pre_tree_sha256: str
    source_store_pre_tree_sha256: str
    source_store_post_tree_sha256: str
    shadow_tree_sha256: str
    production_shadow_build_report_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "blockers", tuple(self.blockers))


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
class _PlanDocument:
    rehearsal: ProspectiveDocumentRehearsal
    pdf_path: Path
    manifest: SourceDocumentManifest
    bindings: tuple[EvidenceBinding, ...]


@dataclass(frozen=True, slots=True)
class _M4RunResult:
    succeeded: bool
    indexed_row_count: int | None
    blocker: str | None


@dataclass(frozen=True, slots=True)
class _ShadowInspection:
    exact_row_count: int
    missing_row_count: int
    conflicting_row_count: int
    unexpected_row_ids: tuple[str, ...]
    legacy_row_ids: tuple[str, ...]
    foreign_case_row_ids: tuple[str, ...]
    actual_row_ids: tuple[str, ...]
    per_document_verified: Mapping[str, bool]


class _SubprocessCollection:
    """Read-only Chroma collection adapter whose handles die with each child."""

    def __init__(self, db_root: Path) -> None:
        self._db_root = Path(db_root).resolve(strict=False)

    def get(self, *, include=None, ids=None, where=None):
        source_root = Path(__file__).resolve().parents[1]
        script = r'''import json
import sys
from pathlib import Path
import chromadb

db_root = Path(sys.argv[1])
ids_payload = json.loads(sys.argv[2])
where_payload = json.loads(sys.argv[3])
client = chromadb.PersistentClient(path=str(db_root))
collection = client.get_collection(name="legal_documents")
kwargs = {"include": ["documents", "metadatas"]}
if ids_payload is not None:
    kwargs["ids"] = ids_payload
if where_payload is not None:
    kwargs["where"] = where_payload
result = collection.get(**kwargs)
print("__PFCR2_GET__" + json.dumps({
    "ids": result.get("ids"),
    "documents": result.get("documents"),
    "metadatas": result.get("metadatas"),
}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        current = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(source_root) if not current else str(source_root) + os.pathsep + current
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self._db_root),
                json.dumps(ids if ids is not None else None),
                json.dumps(where if where is not None else None),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ProductionShadowBuildError("Active Chroma collection could not be read safely.")
        for line in reversed(completed.stdout.splitlines()):
            if line.startswith("__PFCR2_GET__"):
                try:
                    value = json.loads(line[len("__PFCR2_GET__") :])
                except json.JSONDecodeError as exc:
                    raise ProductionShadowBuildError("Active Chroma result was malformed.") from exc
                if not isinstance(value, dict):
                    raise ProductionShadowBuildError("Active Chroma result was malformed.")
                return value
        raise ProductionShadowBuildError("Active Chroma child returned no result.")


def build_production_source_bound_shadow(
    *,
    case_id: str,
    hm1_report: HistoricalMigrationReport,
    approved_pfcr1_report_id: str,
    current_documents_root: Path,
    preflight_staging_root: Path,
    shadow_generation_root: Path,
    active_db_root: Path,
    backup_root: Path,
    production_store: SourceEvidenceStore | None = None,
) -> ProductionShadowBuildReport:
    """Build prospective production source authority and an inactive shadow DB.

    This function deliberately contains no activation/cutover/legacy-retirement
    capability.  When ``production_store`` is omitted, production path identities
    are required exactly.  Tests may inject a temporary M2 store.
    """

    canonical_case = canonical_uuid(case_id, field_name="case_id")
    approved_report_id = validate_sha256_id(
        approved_pfcr1_report_id,
        field_name="approved_pfcr1_report_id",
    )
    paths = _validate_paths(
        current_documents_root=current_documents_root,
        preflight_staging_root=preflight_staging_root,
        shadow_generation_root=shadow_generation_root,
        active_db_root=active_db_root,
        backup_root=backup_root,
        production_mode=production_store is None,
    )
    docs_root, preflight_root, shadow_root, active_root, backup, observation_root = paths
    target_store = production_store if production_store is not None else SourceEvidenceStore()
    if production_store is not None:
        production_store_tree = (_project_root() / "source_evidence_store").resolve(strict=False)
        if _same_or_below(target_store.root, production_store_tree):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)

    # Production trees are frozen observations during PFCR2, except the source store.
    active_pre = _build_tree_manifest(active_root, require_exists=True)
    docs_pre = _build_tree_manifest(docs_root, require_exists=True)
    reports_root = _project_root() / "report_projections"
    reports_pre = _build_tree_manifest(reports_root, require_exists=False)
    store_pre = _build_tree_manifest(target_store.root, require_exists=False)

    _require_absent_or_empty(preflight_root, field_name="preflight_staging_root")
    _require_absent_or_empty(backup, field_name="backup_root")
    _require_absent_or_empty(observation_root, field_name="active_db_observation_root")
    _validate_shadow_runtime(shadow_root)

    # PFCR2.1: Chroma may rewrite persistent bytes even for observational opens.
    # Therefore fresh PFCR1 must never open the protected active DB directly.
    observation_db_root = observation_root / "active_db"
    _copy_observation_tree_exact(
        active_root,
        observation_db_root,
        active_pre,
    )
    observation_pre = _build_tree_manifest(observation_db_root, require_exists=True)
    if observation_pre.entries != active_pre.entries:
        raise ProductionShadowBuildError("active_db_observation_copy_failed")

    # Verify the protected active DB remained exact during snapshot construction.
    if _build_tree_manifest(active_root, require_exists=True) != active_pre:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_ACTIVE_DB.value)

    # Frozen PFCR1 is rerun from a truly fresh staging root against the verified
    # disposable observation snapshot before any production M2 writes.
    active_collection = _SubprocessCollection(observation_db_root)
    previous_no_bytecode = os.environ.get("PYTHONDONTWRITEBYTECODE")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        fresh_pfcr1 = rehearse_prospective_reingestion(
            case_id=canonical_case,
            hm1_report=hm1_report,
            current_documents_root=docs_root,
            staging_root=preflight_root,
            active_collection=active_collection,
        )
    finally:
        if previous_no_bytecode is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous_no_bytecode
    _validate_fresh_pfcr1(
        fresh_pfcr1,
        approved_report_id,
        case_id=canonical_case,
        hm1_report_id=hm1_report.historical_migration_report_id,
    )
    observation_post = _build_tree_manifest(observation_db_root, require_exists=True)

    # Prove the rehearsal observation did not change any protected production tree.
    active_after_preflight = _build_tree_manifest(active_root, require_exists=True)
    docs_after_preflight = _build_tree_manifest(docs_root, require_exists=True)
    reports_after_preflight = _build_tree_manifest(reports_root, require_exists=False)
    if active_after_preflight != active_pre:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_ACTIVE_DB.value)
    if docs_after_preflight != docs_pre:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_DOCS.value)
    if reports_after_preflight != reports_pre:
        raise ProductionShadowBuildError(
            ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_REPORT_PROJECTIONS.value
        )

    plan_store = SourceEvidenceStore(preflight_root / "pfcr2-plan" / "source_evidence_store" / "v1")
    plan_store.root.parent.mkdir(parents=True, exist_ok=True)
    plan = _build_disposable_plan(
        case_id=canonical_case,
        fresh_report=fresh_pfcr1,
        documents_root=docs_root,
        store=plan_store,
    )
    _preflight_production_slots(plan, target_store)

    # Backup is completed and verified before the first production source-store write.
    backup_db_root = backup / "active_db"
    _copy_tree_exact(active_root, backup_db_root, active_pre)
    backup_manifest = _build_tree_manifest(backup_db_root, require_exists=True)
    if backup_manifest.entries != active_pre.entries:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.BACKUP_VERIFICATION_FAILED.value)

    # Recheck all protected trees immediately before the first intentional source write.
    if _build_tree_manifest(active_root, require_exists=True) != active_pre:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_ACTIVE_DB.value)
    if _build_tree_manifest(docs_root, require_exists=True) != docs_pre:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_DOCS.value)
    if _build_tree_manifest(reports_root, require_exists=False) != reports_pre:
        raise ProductionShadowBuildError(
            ProductionShadowBuildBlocker.PREFLIGHT_CHANGED_REPORT_PROJECTIONS.value
        )

    # The M2 root itself remains created only by frozen M2 publication, but its
    # fixed parent must exist for M2's create-exact-root operation.
    target_store.root.parent.mkdir(parents=True, exist_ok=True)

    runtime_root = shadow_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    _reject_runtime_shadowing(runtime_root)

    document_results: list[ProductionShadowDocumentResult] = []
    build_blockers: list[str] = []
    verified_manifests: list[SourceDocumentManifest] = []

    for item in plan:
        m4_result = _run_production_m4_ingestion(
            pdf_path=item.pdf_path,
            case_id=canonical_case,
            store_root=target_store.root,
            runtime_root=runtime_root,
            expected_original_sha256=item.rehearsal.current_pdf_sha256 or "",
        )
        blockers: list[str] = []
        production_manifest_verified = False
        production_bindings_verified = False
        shadow_verified = False

        if not m4_result.succeeded:
            blockers.append(m4_result.blocker or ProductionShadowBuildBlocker.M4_INGESTION_FAILED.value)
        else:
            try:
                _verify_production_graph(item, target_store)
                production_manifest_verified = True
                production_bindings_verified = True
            except ProductionShadowBuildError as exc:
                blockers.append(str(exc))

            if not blockers:
                # The inactive shadow is cumulative across the document loop.
                # Verify the exact set accumulated so far; otherwise rows from
                # earlier verified documents are falsely classified as unexpected.
                verified_manifests.append(item.manifest)
                inspection = _inspect_inactive_shadow(
                    case_id=canonical_case,
                    shadow_db_root=runtime_root / "db",
                    store_root=target_store.root,
                    manifests=tuple(verified_manifests),
                )
                shadow_verified = (
                    inspection.missing_row_count == 0
                    and inspection.conflicting_row_count == 0
                    and not inspection.unexpected_row_ids
                    and not inspection.legacy_row_ids
                    and not inspection.foreign_case_row_ids
                    and inspection.per_document_verified.get(item.manifest.source_document_instance_id)
                    is True
                )
                if not shadow_verified:
                    blockers.append(_shadow_blocker(inspection))

        result = ProductionShadowDocumentResult(
            document_name=item.rehearsal.document_name,
            current_pdf_sha256=item.rehearsal.current_pdf_sha256 or "",
            current_pdf_byte_length=item.rehearsal.current_pdf_byte_length or 0,
            source_document_instance_id=item.manifest.source_document_instance_id,
            source_snapshot_id=item.manifest.source_snapshot_id,
            prospective_evidence_keys=_manifest_evidence_keys(item.manifest),
            prospective_row_count=len(_manifest_evidence_keys(item.manifest)),
            m4_indexed_row_count=m4_result.indexed_row_count,
            production_manifest_verified=production_manifest_verified,
            production_bindings_verified=production_bindings_verified,
            shadow_verified=shadow_verified,
            blockers=tuple(sorted(set(blockers))),
        )
        document_results.append(result)
        if blockers:
            build_blockers.extend(blockers)
            break

    # Final inspection is always attempted for auditability; it never activates the DB.
    final_shadow = _safe_final_shadow_inspection(
        case_id=canonical_case,
        shadow_db_root=runtime_root / "db",
        store_root=target_store.root,
        manifests=tuple(item.manifest for item in plan),
    )

    active_post = _build_tree_manifest(active_root, require_exists=True)
    docs_post = _build_tree_manifest(docs_root, require_exists=True)
    reports_post = _build_tree_manifest(reports_root, require_exists=False)
    store_post = _build_tree_manifest(target_store.root, require_exists=False)
    shadow_tree = _build_tree_manifest(runtime_root / "db", require_exists=False)

    source_audit = _audit_source_store(
        pre=store_pre,
        post=store_post,
        plan_store_root=plan_store.root,
    )
    build_blockers.extend(source_audit["blockers"])

    active_unchanged = active_post == active_pre
    docs_unchanged = docs_post == docs_pre
    reports_unchanged = reports_post == reports_pre
    if not active_unchanged:
        build_blockers.append(ProductionShadowBuildBlocker.ACTIVE_DB_CHANGED.value)
    if not docs_unchanged:
        build_blockers.append(ProductionShadowBuildBlocker.DOCS_CHANGED.value)
    if not reports_unchanged:
        build_blockers.append(ProductionShadowBuildBlocker.REPORT_PROJECTIONS_CHANGED.value)

    expected_keys = tuple(sorted({key for item in plan for key in _manifest_evidence_keys(item.manifest)}))
    actual_keys = final_shadow.actual_row_ids
    exact_set = actual_keys == expected_keys
    if final_shadow.missing_row_count:
        build_blockers.append(ProductionShadowBuildBlocker.SHADOW_MISSING_ROW.value)
    if final_shadow.conflicting_row_count:
        build_blockers.append(ProductionShadowBuildBlocker.SHADOW_CONFLICTING_ROW.value)
    if final_shadow.unexpected_row_ids:
        build_blockers.append(ProductionShadowBuildBlocker.SHADOW_UNEXPECTED_ROW.value)
    if final_shadow.legacy_row_ids:
        build_blockers.append(ProductionShadowBuildBlocker.SHADOW_LEGACY_ROW.value)
    if final_shadow.foreign_case_row_ids:
        build_blockers.append(ProductionShadowBuildBlocker.SHADOW_CASE_MISMATCH.value)

    all_document_results = len(document_results) == len(plan) and all(
        item.production_manifest_verified
        and item.production_bindings_verified
        and item.shadow_verified
        and not item.blockers
        for item in document_results
    )
    source_append_only_valid = not source_audit["blockers"]
    blockers = tuple(sorted(set(build_blockers)))
    complete = (
        not blockers
        and fresh_pfcr1.collection_complete_for_cutover
        and fresh_pfcr1.all_active_collection_populations_accounted
        and all_document_results
        and exact_set
        and final_shadow.missing_row_count == 0
        and final_shadow.conflicting_row_count == 0
        and not final_shadow.unexpected_row_ids
        and not final_shadow.legacy_row_ids
        and not final_shadow.foreign_case_row_ids
        and active_unchanged
        and docs_unchanged
        and reports_unchanged
        and source_append_only_valid
        and backup_manifest.entries == active_pre.entries
        and source_audit["new_analysis_receipt_count"] == 0
        and source_audit["new_projection_binding_count"] == 0
    )

    provisional = ProductionShadowBuildReport(
        schema_version=PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION,
        case_id=canonical_case,
        baseline_commit=_FROZEN_BASELINE_COMMIT,
        hm1_report_id=hm1_report.historical_migration_report_id,
        approved_pfcr1_report_id=approved_report_id,
        fresh_pfcr1_report_id=fresh_pfcr1.prospective_reingestion_report_id,
        historical_provenance_changed=False,
        active_derived_index_changed=False,
        production_source_chain_created=bool(store_post.entries) and len(store_post.entries) >= len(store_pre.entries),
        inactive_shadow_created=shadow_tree.root_exists,
        legacy_active_row_count=fresh_pfcr1.legacy_active_row_count,
        legacy_collision_risk_count=fresh_pfcr1.legacy_collision_risk_count,
        legacy_key_different_count=fresh_pfcr1.legacy_key_different_count,
        current_document_count=fresh_pfcr1.current_document_count,
        production_manifest_count=len(plan),
        production_prospective_row_count=len(expected_keys),
        shadow_exact_row_count=final_shadow.exact_row_count,
        shadow_missing_row_count=final_shadow.missing_row_count,
        shadow_conflicting_row_count=final_shadow.conflicting_row_count,
        shadow_unexpected_row_count=len(final_shadow.unexpected_row_ids),
        shadow_legacy_row_count=len(final_shadow.legacy_row_ids),
        preexisting_source_store_file_count=len(store_pre.entries),
        new_source_store_file_count=source_audit["new_count"],
        modified_preexisting_source_store_file_count=source_audit["modified_count"],
        deleted_preexisting_source_store_file_count=source_audit["deleted_count"],
        new_analysis_receipt_count=source_audit["new_analysis_receipt_count"],
        new_projection_binding_count=source_audit["new_projection_binding_count"],
        active_db_unchanged=active_unchanged,
        docs_unchanged=docs_unchanged,
        report_projections_unchanged=reports_unchanged,
        source_store_append_only_valid=source_append_only_valid,
        backup_verified=backup_manifest.entries == active_pre.entries,
        all_documents_production_verified=all_document_results,
        shadow_exact_set_verified=exact_set,
        shadow_complete_for_pfcr3=complete,
        documents=tuple(document_results),
        blockers=blockers,
        active_db_pre_tree_sha256=active_pre.tree_sha256,
        active_db_backup_tree_sha256=backup_manifest.tree_sha256,
        docs_pre_tree_sha256=docs_pre.tree_sha256,
        report_projections_pre_tree_sha256=reports_pre.tree_sha256,
        source_store_pre_tree_sha256=store_pre.tree_sha256,
        source_store_post_tree_sha256=store_post.tree_sha256,
        shadow_tree_sha256=shadow_tree.tree_sha256,
        production_shadow_build_report_id="sha256:" + ("0" * 64),
    )
    report_id = "sha256:" + sha256_bytes(_canonical_json_bytes(_report_identity_payload(provisional)))
    report = replace(provisional, production_shadow_build_report_id=report_id)
    _write_external_audit_artifacts(
        backup_root=backup,
        report=report,
        manifests={
            "active_db_pre": active_pre,
            "active_db_observation_pre": observation_pre,
            "active_db_observation_post": observation_post,
            "active_db_backup": backup_manifest,
            "docs_pre": docs_pre,
            "report_projections_pre": reports_pre,
            "source_store_pre": store_pre,
            "source_store_post": store_post,
            "shadow": shadow_tree,
        },
    )
    return report


def production_shadow_build_report_to_dict(report: ProductionShadowBuildReport) -> dict[str, object]:
    """Return deterministic PFCR2 report data including operational tree hashes."""

    return {
        **_report_identity_payload(report),
        "active_db_pre_tree_sha256": report.active_db_pre_tree_sha256,
        "active_db_backup_tree_sha256": report.active_db_backup_tree_sha256,
        "docs_pre_tree_sha256": report.docs_pre_tree_sha256,
        "report_projections_pre_tree_sha256": report.report_projections_pre_tree_sha256,
        "source_store_pre_tree_sha256": report.source_store_pre_tree_sha256,
        "source_store_post_tree_sha256": report.source_store_post_tree_sha256,
        "shadow_tree_sha256": report.shadow_tree_sha256,
        "production_shadow_build_report_id": report.production_shadow_build_report_id,
    }


def dumps_production_shadow_build_report(report: ProductionShadowBuildReport) -> str:
    """Return canonical PFCR2 JSON with exactly one trailing newline."""

    return _canonical_json_bytes(production_shadow_build_report_to_dict(report)).decode("utf-8") + "\n"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_paths(
    *,
    current_documents_root: Path,
    preflight_staging_root: Path,
    shadow_generation_root: Path,
    active_db_root: Path,
    backup_root: Path,
    production_mode: bool,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    project = _project_root().resolve(strict=False)
    docs = Path(current_documents_root).expanduser().resolve(strict=False)
    preflight = Path(preflight_staging_root).expanduser().resolve(strict=False)
    shadow = Path(shadow_generation_root).expanduser().resolve(strict=False)
    active = Path(active_db_root).expanduser().resolve(strict=False)
    backup = Path(backup_root).expanduser().resolve(strict=False)
    try:
        observation = preflight.with_name(preflight.name + ".active-db-observation")
    except ValueError as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value) from exc

    if production_mode:
        if docs != (project / "docs").resolve(strict=False):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
        if active != (project / "db").resolve(strict=False):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)

    external = (preflight, shadow, backup, observation)
    for value in external:
        if _same_or_below(value, project):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    protected = (
        active,
        docs,
        (project / "source_evidence_store").resolve(strict=False),
        (project / "report_projections").resolve(strict=False),
    )
    for external_root in external:
        for protected_root in protected:
            if _paths_overlap(external_root, protected_root):
                raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    for index, left in enumerate(external):
        for right in external[index + 1 :]:
            if _paths_overlap(left, right):
                raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    if _paths_overlap(shadow, docs) or _paths_overlap(shadow, active):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    if not _same_filesystem(active, shadow):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    return docs, preflight, shadow, active, backup, observation


def _same_or_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _paths_overlap(left: Path, right: Path) -> bool:
    return _same_or_below(left, right) or _same_or_below(right, left)


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
        current = current.parent
    return current


def _same_filesystem(left: Path, right: Path) -> bool:
    try:
        left_existing = _nearest_existing(left)
        right_existing = _nearest_existing(right)
        if os.name == "nt" and left_existing.drive.casefold() != right_existing.drive.casefold():
            return False
        return os.stat(left_existing).st_dev == os.stat(right_existing).st_dev
    except OSError as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value) from exc


def _require_absent_or_empty(root: Path, *, field_name: str) -> None:
    if _is_link_like(root):
        raise ProductionShadowBuildError(f"{field_name} is unsafe.")
    if not root.exists():
        return
    if not root.is_dir():
        raise ProductionShadowBuildError(f"{field_name} must be a directory.")
    try:
        if any(root.iterdir()):
            raise ProductionShadowBuildError(f"{field_name} must be absent or empty.")
    except OSError as exc:
        raise ProductionShadowBuildError(f"{field_name} could not be inspected.") from exc


def _validate_shadow_runtime(shadow_root: Path) -> None:
    if _is_link_like(shadow_root):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    if not shadow_root.exists():
        return
    if not shadow_root.is_dir():
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)
    _reject_runtime_shadowing(shadow_root / "runtime")
    allowed_top = {"runtime"}
    try:
        unexpected = {path.name for path in shadow_root.iterdir()} - allowed_top
    except OSError as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value) from exc
    if unexpected:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value)


def _reject_runtime_shadowing(runtime_root: Path) -> None:
    if not runtime_root.exists():
        return
    if _is_link_like(runtime_root) or not runtime_root.is_dir():
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.RUNTIME_SHADOWING.value)
    try:
        children = tuple(runtime_root.iterdir())
    except OSError as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.RUNTIME_SHADOWING.value) from exc
    # A production M4 child must see repository modules only.  The runtime cwd
    # may contain the derived ``db`` directory and nothing importable/shadowing.
    unexpected = tuple(path for path in children if path.name != "db")
    if unexpected:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.RUNTIME_SHADOWING.value)
    if any(path.name.casefold() in {name.casefold() for name in _RUNTIME_SHADOW_NAMES} for path in children):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.RUNTIME_SHADOWING.value)


def _is_link_like(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    try:
        if path.is_symlink():
            return True
        junction = getattr(path, "is_junction", None)
        if junction is not None and junction():
            return True
        info = os.lstat(path)
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(reparse and attributes & reparse)
    except OSError as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PATH_UNSAFE.value) from exc


def _build_tree_manifest(root: Path, *, require_exists: bool) -> _TreeManifest:
    root = Path(root).resolve(strict=False)
    if not root.exists():
        if require_exists:
            raise ProductionShadowBuildError("Required audited production tree is missing.")
        return _make_tree_manifest(False, ())
    if _is_link_like(root) or not root.is_dir():
        raise ProductionShadowBuildError("Audited tree root is unsafe.")
    entries: list[_TreeEntry] = []
    try:
        paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    except OSError as exc:
        raise ProductionShadowBuildError("Audited tree could not be enumerated.") from exc
    for path in paths:
        if _is_link_like(path):
            raise ProductionShadowBuildError("Link-like entry is forbidden in audited tree.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ProductionShadowBuildError("Non-regular entry is forbidden in audited tree.")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ProductionShadowBuildError("Audited tree file could not be read.") from exc
        entries.append(
            _TreeEntry(
                relative_path=path.relative_to(root).as_posix(),
                byte_length=len(data),
                sha256_hex=sha256_bytes(data),
            )
        )
    return _make_tree_manifest(True, tuple(entries))


def _make_tree_manifest(root_exists: bool, entries: tuple[_TreeEntry, ...]) -> _TreeManifest:
    payload = {
        "root_exists": root_exists,
        "entries": [
            {
                "relative_path": item.relative_path,
                "byte_length": item.byte_length,
                "sha256_hex": item.sha256_hex,
            }
            for item in entries
        ],
    }
    return _TreeManifest(
        root_exists=root_exists,
        entries=entries,
        tree_sha256="sha256:" + sha256_bytes(_canonical_json_bytes(payload)),
    )


def _validate_fresh_pfcr1(
    report: ProspectiveReingestionReport,
    approved_id: str,
    *,
    case_id: str,
    hm1_report_id: str,
) -> None:
    if (
        report.case_id != case_id
        or report.hm1_report_id != hm1_report_id
        or report.historical_provenance_changed
        or report.active_derived_index_changed
    ):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.FRESH_PFCR1_INCOMPLETE.value)
    if report.prospective_reingestion_report_id != approved_id:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.FRESH_PFCR1_ID_MISMATCH.value)
    if (
        not report.collection_complete_for_cutover
        or not report.all_active_collection_populations_accounted
        or report.blockers
    ):
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.FRESH_PFCR1_INCOMPLETE.value)


def _build_disposable_plan(
    *,
    case_id: str,
    fresh_report: ProspectiveReingestionReport,
    documents_root: Path,
    store: SourceEvidenceStore,
) -> tuple[_PlanDocument, ...]:
    from .capture import capture_pdf_source

    plan: list[_PlanDocument] = []
    seen_keys: set[str] = set()
    for rehearsal in sorted(fresh_report.documents, key=lambda value: value.document_name):
        if (
            not rehearsal.capture_succeeded
            or not rehearsal.m4_ingestion_succeeded
            or not rehearsal.shadow_verified
            or rehearsal.blockers
            or rehearsal.current_pdf_sha256 is None
            or rehearsal.current_pdf_byte_length is None
            or rehearsal.source_document_instance_id is None
            or rehearsal.source_snapshot_id is None
        ):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.FRESH_PFCR1_INCOMPLETE.value)
        pdf_path = _resolve_unique_current_pdf(documents_root, rehearsal.document_name)
        data = pdf_path.read_bytes()
        if sha256_bytes(data) != rehearsal.current_pdf_sha256 or len(data) != rehearsal.current_pdf_byte_length:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
        manifest = capture_pdf_source(
            pdf_path,
            case_id=case_id,
            original_filename=rehearsal.document_name,
            store=store,
        )
        validate_source_document_manifest(manifest)
        keys = _manifest_evidence_keys(manifest)
        if (
            manifest.source_document_instance_id != rehearsal.source_document_instance_id
            or manifest.source_snapshot_id != rehearsal.source_snapshot_id
            or manifest.original_blob_sha256 != rehearsal.current_pdf_sha256
            or manifest.original_byte_length != rehearsal.current_pdf_byte_length
            or keys != rehearsal.prospective_evidence_keys
        ):
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
        overlap = seen_keys & set(keys)
        if overlap:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
        seen_keys.update(keys)
        bindings = _load_manifest_bindings(manifest, store)
        plan.append(_PlanDocument(rehearsal, pdf_path, manifest, bindings))
    if len(plan) != fresh_report.current_document_count:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
    return tuple(plan)


def _resolve_unique_current_pdf(root: Path, filename: str) -> Path:
    matches: list[Path] = []
    try:
        for candidate in root.rglob("*"):
            if candidate.name != filename:
                continue
            if _is_link_like(candidate):
                continue
            if candidate.is_file():
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root.resolve(strict=True))
                matches.append(resolved)
    except (OSError, ValueError) as exc:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value) from exc
    if len(matches) != 1:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
    return matches[0]


def _load_manifest_bindings(
    manifest: SourceDocumentManifest,
    store: SourceEvidenceStore,
) -> tuple[EvidenceBinding, ...]:
    result: list[EvidenceBinding] = []
    for key in _manifest_evidence_keys(manifest):
        binding = store.load_evidence_binding(manifest.case_id, key)
        if binding is None:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
        validate_evidence_binding(binding)
        if binding.binding_class is not BindingClass.FULL_CHAIN_BOUND:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.PROSPECTIVE_PLAN_MISMATCH.value)
        result.append(binding)
    return tuple(result)


def _preflight_production_slots(plan: Sequence[_PlanDocument], store: SourceEvidenceStore) -> None:
    for item in plan:
        try:
            existing_manifest = store.load_document_manifest(
                item.manifest.case_id,
                item.manifest.source_document_instance_id,
            )
        except SourceEvidenceStoreError as exc:
            if str(exc) != "Required source-evidence record is missing.":
                raise ProductionShadowBuildError(
                    ProductionShadowBuildBlocker.EXISTING_MANIFEST_MISMATCH.value
                ) from exc
        else:
            if existing_manifest != item.manifest:
                raise ProductionShadowBuildError(
                    ProductionShadowBuildBlocker.EXISTING_MANIFEST_MISMATCH.value
                )
        for intended in item.bindings:
            existing = store.load_evidence_binding(item.manifest.case_id, intended.evidence_key)
            if existing is None:
                continue
            validate_evidence_binding(existing)
            if existing.binding_class is not BindingClass.FULL_CHAIN_BOUND:
                raise ProductionShadowBuildError(
                    ProductionShadowBuildBlocker.EXISTING_WEAKER_BINDING_OCCUPIES_KEY.value
                )
            if existing != intended:
                raise ProductionShadowBuildError(
                    ProductionShadowBuildBlocker.EXISTING_FULL_CHAIN_BINDING_MISMATCH.value
                )


def _copy_observation_tree_exact(
    source: Path,
    destination: Path,
    manifest: _TreeManifest,
) -> None:
    """Copy a verified active-DB observation snapshot without reusing backup hooks."""

    failure = "active_db_observation_copy_failed"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ProductionShadowBuildError(failure)
    destination.mkdir()
    for entry in manifest.entries:
        src = source / Path(entry.relative_path)
        dst = destination / Path(entry.relative_path)
        if _is_link_like(src) or not src.is_file():
            raise ProductionShadowBuildError(failure)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def _copy_tree_exact(source: Path, destination: Path, manifest: _TreeManifest) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.BACKUP_VERIFICATION_FAILED.value)
    destination.mkdir()
    for entry in manifest.entries:
        src = source / Path(entry.relative_path)
        dst = destination / Path(entry.relative_path)
        if _is_link_like(src) or not src.is_file():
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.BACKUP_VERIFICATION_FAILED.value)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def _run_production_m4_ingestion(
    *,
    pdf_path: Path,
    case_id: str,
    store_root: Path,
    runtime_root: Path,
    expected_original_sha256: str,
) -> _M4RunResult:
    source_root = Path(__file__).resolve().parents[1]
    _reject_runtime_shadowing(runtime_root)
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
    print("__PFCR2_M4__" + json.dumps({"ok": False, "type": type(exc).__name__, "message": str(exc)}))
    raise SystemExit(3)
print("__PFCR2_M4__" + json.dumps({"ok": True, "count": count}))
'''
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(source_root) if not current else str(source_root) + os.pathsep + current
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
        return _M4RunResult(False, None, ProductionShadowBuildBlocker.M4_INGESTION_FAILED.value)

    payload: dict[str, object] | None = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("__PFCR2_M4__"):
            try:
                candidate = json.loads(line[len("__PFCR2_M4__") :])
            except json.JSONDecodeError:
                break
            if isinstance(candidate, dict):
                payload = candidate
            break
    if completed.returncode == 0 and payload and payload.get("ok") is True:
        count = payload.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return _M4RunResult(False, None, ProductionShadowBuildBlocker.M4_INGESTION_FAILED.value)
        return _M4RunResult(True, count, None)

    error_type = str(payload.get("type") if payload else "")
    error_message = str(payload.get("message") if payload else "")
    blocker = ProductionShadowBuildBlocker.M4_INGESTION_FAILED.value
    if error_type == "SourceEvidenceIngestionConflictError":
        blocker = ProductionShadowBuildBlocker.M4_SHADOW_CONFLICT.value
    elif error_type == "SourceEvidenceIngestionIncompleteError":
        blocker = ProductionShadowBuildBlocker.M4_SHADOW_INCOMPLETE.value
    elif "maximum batch size" in error_message.casefold():
        blocker = ProductionShadowBuildBlocker.M4_BATCH_LIMIT.value
    return _M4RunResult(False, None, blocker)


def _verify_production_graph(item: _PlanDocument, store: SourceEvidenceStore) -> None:
    try:
        manifest = store.load_document_manifest(
            item.manifest.case_id,
            item.manifest.source_document_instance_id,
        )
    except Exception as exc:
        raise ProductionShadowBuildError(
            ProductionShadowBuildBlocker.PRODUCTION_MANIFEST_MISMATCH.value
        ) from exc
    if manifest != item.manifest:
        raise ProductionShadowBuildError(
            ProductionShadowBuildBlocker.PRODUCTION_MANIFEST_MISMATCH.value
        )
    intended = {binding.evidence_key: binding for binding in item.bindings}
    for key in _manifest_evidence_keys(item.manifest):
        binding = store.load_evidence_binding(item.manifest.case_id, key)
        if binding != intended[key]:
            raise ProductionShadowBuildError(
                ProductionShadowBuildBlocker.PRODUCTION_BINDING_MISMATCH.value
            )


def _inspect_inactive_shadow(
    *,
    case_id: str,
    shadow_db_root: Path,
    store_root: Path,
    manifests: Sequence[SourceDocumentManifest],
) -> _ShadowInspection:
    source_root = Path(__file__).resolve().parents[1]
    manifest_ids = [manifest.source_document_instance_id for manifest in manifests]
    script = r'''import json
import sys
from pathlib import Path
import chromadb
from source_evidence.ingestion import inspect_source_bound_index
from source_evidence.store import SourceEvidenceStore

case_id = sys.argv[1]
db_root = Path(sys.argv[2])
store_root = Path(sys.argv[3])
manifest_ids = json.loads(sys.argv[4])
store = SourceEvidenceStore(store_root)
client = chromadb.PersistentClient(path=str(db_root))
collection = client.get_collection(name="legal_documents")
per_doc = {}
exact = 0
missing = 0
conflicting = 0
for document_id in manifest_ids:
    manifest = store.load_document_manifest(case_id, document_id)
    diagnostic = inspect_source_bound_index(manifest, store=store, collection=collection)
    per_doc[document_id] = bool(
        diagnostic.exact_present_count == diagnostic.total_rows
        and diagnostic.missing_count == 0
        and diagnostic.conflicting_count == 0
    )
    exact += diagnostic.exact_present_count
    missing += diagnostic.missing_count
    conflicting += diagnostic.conflicting_count
raw = collection.get(include=["metadatas"])
ids = raw.get("ids") or []
metadatas = raw.get("metadatas") or []
legacy = []
foreign = []
keys = (
    "source_evidence_binding_id",
    "source_snapshot_id",
    "source_document_instance_id",
    "source_chunk_sha256",
    "source_page_text_sha256",
    "source_original_blob_sha256",
    "source_binding_class",
)
for row_id, metadata in zip(ids, metadatas, strict=True):
    metadata = metadata or {}
    if metadata.get("source_binding_class") != "full_chain_bound" or any(
        not isinstance(metadata.get(key), str) or not metadata.get(key) for key in keys
    ):
        legacy.append(row_id)
    if metadata.get("case_id") != case_id:
        foreign.append(row_id)
print("__PFCR2_INSPECT__" + json.dumps({
    "exact": exact,
    "missing": missing,
    "conflicting": conflicting,
    "ids": sorted(ids),
    "legacy": sorted(legacy),
    "foreign": sorted(foreign),
    "per_doc": per_doc,
}, sort_keys=True, separators=(",", ":")))
'''
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(source_root) if not current else str(source_root) + os.pathsep + current
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            case_id,
            str(Path(shadow_db_root).resolve(strict=False)),
            str(Path(store_root).resolve(strict=False)),
            json.dumps(manifest_ids),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProductionShadowBuildError(ProductionShadowBuildBlocker.SHADOW_UNAVAILABLE.value)
    for line in reversed(completed.stdout.splitlines()):
        if not line.startswith("__PFCR2_INSPECT__"):
            continue
        try:
            value = json.loads(line[len("__PFCR2_INSPECT__") :])
        except json.JSONDecodeError as exc:
            raise ProductionShadowBuildError(ProductionShadowBuildBlocker.SHADOW_UNAVAILABLE.value) from exc
        if not isinstance(value, dict):
            break
        ids = tuple(value.get("ids") or ())
        expected = tuple(sorted({key for manifest in manifests for key in _manifest_evidence_keys(manifest)}))
        unexpected = tuple(sorted(set(ids) - set(expected)))
        return _ShadowInspection(
            exact_row_count=int(value.get("exact") or 0),
            missing_row_count=int(value.get("missing") or 0),
            conflicting_row_count=int(value.get("conflicting") or 0),
            unexpected_row_ids=unexpected,
            legacy_row_ids=tuple(value.get("legacy") or ()),
            foreign_case_row_ids=tuple(value.get("foreign") or ()),
            actual_row_ids=tuple(ids),
            per_document_verified={str(k): bool(v) for k, v in dict(value.get("per_doc") or {}).items()},
        )
    raise ProductionShadowBuildError(ProductionShadowBuildBlocker.SHADOW_UNAVAILABLE.value)


def _safe_final_shadow_inspection(
    *,
    case_id: str,
    shadow_db_root: Path,
    store_root: Path,
    manifests: Sequence[SourceDocumentManifest],
) -> _ShadowInspection:
    if not shadow_db_root.exists():
        expected = tuple(sorted({key for manifest in manifests for key in _manifest_evidence_keys(manifest)}))
        return _ShadowInspection(
            exact_row_count=0,
            missing_row_count=len(expected),
            conflicting_row_count=0,
            unexpected_row_ids=(),
            legacy_row_ids=(),
            foreign_case_row_ids=(),
            actual_row_ids=(),
            per_document_verified={},
        )
    try:
        return _inspect_inactive_shadow(
            case_id=case_id,
            shadow_db_root=shadow_db_root,
            store_root=store_root,
            manifests=manifests,
        )
    except ProductionShadowBuildError:
        expected = tuple(sorted({key for manifest in manifests for key in _manifest_evidence_keys(manifest)}))
        return _ShadowInspection(
            exact_row_count=0,
            missing_row_count=len(expected),
            conflicting_row_count=0,
            unexpected_row_ids=(),
            legacy_row_ids=(),
            foreign_case_row_ids=(),
            actual_row_ids=(),
            per_document_verified={},
        )


def _shadow_blocker(inspection: _ShadowInspection) -> str:
    if inspection.conflicting_row_count:
        return ProductionShadowBuildBlocker.SHADOW_CONFLICTING_ROW.value
    if inspection.missing_row_count:
        return ProductionShadowBuildBlocker.SHADOW_MISSING_ROW.value
    if inspection.unexpected_row_ids:
        return ProductionShadowBuildBlocker.SHADOW_UNEXPECTED_ROW.value
    if inspection.legacy_row_ids:
        return ProductionShadowBuildBlocker.SHADOW_LEGACY_ROW.value
    if inspection.foreign_case_row_ids:
        return ProductionShadowBuildBlocker.SHADOW_CASE_MISMATCH.value
    return ProductionShadowBuildBlocker.SHADOW_UNAVAILABLE.value


def _manifest_evidence_keys(manifest: SourceDocumentManifest) -> tuple[str, ...]:
    return tuple(chunk.evidence_key for page in manifest.pages for chunk in page.chunk_snapshots)


def _audit_source_store(
    *,
    pre: _TreeManifest,
    post: _TreeManifest,
    plan_store_root: Path,
) -> dict[str, object]:
    pre_by = {entry.relative_path: entry for entry in pre.entries}
    post_by = {entry.relative_path: entry for entry in post.entries}
    plan_manifest = _build_tree_manifest(plan_store_root, require_exists=False)
    plan_by = {entry.relative_path: entry for entry in plan_manifest.entries}

    deleted = sorted(set(pre_by) - set(post_by))
    modified = sorted(
        path for path in set(pre_by) & set(post_by) if pre_by[path] != post_by[path]
    )
    new_paths = sorted(set(post_by) - set(pre_by))
    unexpected_new = sorted(path for path in new_paths if plan_by.get(path) != post_by[path])
    new_receipts = [path for path in new_paths if "/analysis-receipts/" in f"/{path}"]
    new_projection_bindings = [path for path in new_paths if "/projection-bindings/" in f"/{path}"]
    blockers: list[str] = []
    if deleted:
        blockers.append(ProductionShadowBuildBlocker.SOURCE_STORE_PREEXISTING_DELETED.value)
    if modified:
        blockers.append(ProductionShadowBuildBlocker.SOURCE_STORE_PREEXISTING_CHANGED.value)
    if unexpected_new:
        blockers.append(ProductionShadowBuildBlocker.SOURCE_STORE_UNEXPECTED_NEW_OBJECT.value)
    if new_receipts:
        blockers.append(ProductionShadowBuildBlocker.ANALYSIS_RECEIPT_CREATED.value)
    if new_projection_bindings:
        blockers.append(ProductionShadowBuildBlocker.PROJECTION_BINDING_CREATED.value)
    return {
        "deleted_count": len(deleted),
        "modified_count": len(modified),
        "new_count": len(new_paths),
        "new_analysis_receipt_count": len(new_receipts),
        "new_projection_binding_count": len(new_projection_bindings),
        "blockers": tuple(blockers),
    }


def _write_external_audit_artifacts(
    *,
    backup_root: Path,
    report: ProductionShadowBuildReport,
    manifests: Mapping[str, _TreeManifest],
) -> None:
    audit = backup_root / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    for name, manifest in sorted(manifests.items()):
        payload = {
            "root_exists": manifest.root_exists,
            "tree_sha256": manifest.tree_sha256,
            "entries": [
                {
                    "relative_path": entry.relative_path,
                    "byte_length": entry.byte_length,
                    "sha256_hex": entry.sha256_hex,
                }
                for entry in manifest.entries
            ],
        }
        (audit / f"{name}.json").write_bytes(_canonical_json_bytes(payload) + b"\n")
    (audit / "production_shadow_build_report.json").write_text(
        dumps_production_shadow_build_report(report),
        encoding="utf-8",
        newline="\n",
    )


def _report_identity_payload(report: ProductionShadowBuildReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "case_id": report.case_id,
        "baseline_commit": report.baseline_commit,
        "hm1_report_id": report.hm1_report_id,
        "approved_pfcr1_report_id": report.approved_pfcr1_report_id,
        "fresh_pfcr1_report_id": report.fresh_pfcr1_report_id,
        "historical_provenance_changed": report.historical_provenance_changed,
        "active_derived_index_changed": report.active_derived_index_changed,
        "production_source_chain_created": report.production_source_chain_created,
        "inactive_shadow_created": report.inactive_shadow_created,
        "legacy_active_row_count": report.legacy_active_row_count,
        "legacy_collision_risk_count": report.legacy_collision_risk_count,
        "legacy_key_different_count": report.legacy_key_different_count,
        "current_document_count": report.current_document_count,
        "production_manifest_count": report.production_manifest_count,
        "production_prospective_row_count": report.production_prospective_row_count,
        "shadow_exact_row_count": report.shadow_exact_row_count,
        "shadow_missing_row_count": report.shadow_missing_row_count,
        "shadow_conflicting_row_count": report.shadow_conflicting_row_count,
        "shadow_unexpected_row_count": report.shadow_unexpected_row_count,
        "shadow_legacy_row_count": report.shadow_legacy_row_count,
        "preexisting_source_store_file_count": report.preexisting_source_store_file_count,
        "new_source_store_file_count": report.new_source_store_file_count,
        "modified_preexisting_source_store_file_count": report.modified_preexisting_source_store_file_count,
        "deleted_preexisting_source_store_file_count": report.deleted_preexisting_source_store_file_count,
        "new_analysis_receipt_count": report.new_analysis_receipt_count,
        "new_projection_binding_count": report.new_projection_binding_count,
        "active_db_unchanged": report.active_db_unchanged,
        "docs_unchanged": report.docs_unchanged,
        "report_projections_unchanged": report.report_projections_unchanged,
        "source_store_append_only_valid": report.source_store_append_only_valid,
        "backup_verified": report.backup_verified,
        "all_documents_production_verified": report.all_documents_production_verified,
        "shadow_exact_set_verified": report.shadow_exact_set_verified,
        "shadow_complete_for_pfcr3": report.shadow_complete_for_pfcr3,
        "documents": [_document_result_to_dict(item) for item in report.documents],
        "blockers": list(report.blockers),
    }


def _document_result_to_dict(value: ProductionShadowDocumentResult) -> dict[str, object]:
    return {
        "document_name": value.document_name,
        "current_pdf_sha256": value.current_pdf_sha256,
        "current_pdf_byte_length": value.current_pdf_byte_length,
        "source_document_instance_id": value.source_document_instance_id,
        "source_snapshot_id": value.source_snapshot_id,
        "prospective_evidence_keys": list(value.prospective_evidence_keys),
        "prospective_row_count": value.prospective_row_count,
        "m4_indexed_row_count": value.m4_indexed_row_count,
        "production_manifest_verified": value.production_manifest_verified,
        "production_bindings_verified": value.production_bindings_verified,
        "shadow_verified": value.shadow_verified,
        "blockers": list(value.blockers),
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
        raise ProductionShadowBuildError("PFCR2 audit data is not canonical JSON.") from exc


__all__ = [
    "PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION",
    "ProductionShadowBuildBlocker",
    "ProductionShadowBuildError",
    "ProductionShadowBuildReport",
    "ProductionShadowDocumentResult",
    "build_production_source_bound_shadow",
    "dumps_production_shadow_build_report",
    "production_shadow_build_report_to_dict",
]
