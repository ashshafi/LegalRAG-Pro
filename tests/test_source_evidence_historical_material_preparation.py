"""Synthetic HM2.5 historical-material preparation tests.

All filesystem and Chroma state used here is disposable pytest state. The suite
contains no real retained, current-production, or case-specific filesystem path.
"""

from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import source_evidence.historical_material_preparation as hm25
import source_evidence.historical_snapshot as hm24
import source_evidence.historical_snapshot_rehearsal as hm23
from source_evidence.historical_disposition import HistoricalEvidenceRelationship
from source_evidence.identity import derive_sha256_id, sha256_bytes
from source_evidence.models import BindingClass
from source_evidence.store import SourceEvidenceStore

CASE_ID = "12345678-1234-4234-8234-123456789abc"
HM1_ID = derive_sha256_id({"authority": "synthetic-hm1"})
PFCR1_ID = derive_sha256_id({"authority": "synthetic-pfcr1"})
HM2_ID = derive_sha256_id({"authority": "synthetic-hm2"})
DEFAULT_TREE_ID = derive_sha256_id({"authority": "synthetic-retained-tree"})


def _metadata(index: int) -> dict[str, object]:
    return {
        "case_id": CASE_ID,
        "document_name": f"synthetic-document-{index:04d}.pdf",
        "page": index + 1,
        "synthetic_ordinal": index,
    }


def _relationship(index: int) -> HistoricalEvidenceRelationship:
    if index < 304:
        return HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT
    if index < 363:
        return HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT
    if index < 393:
        return HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT
    return HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE


def _text(index: int) -> str:
    # Exactly 396 distinct historical text identities across 745 logical records.
    return f"synthetic historical text {index % 396:03d}"


def _entry_and_observation(index: int):
    relationship = _relationship(index)
    key = f"synthetic-historical-key-{index:04d}"
    text = _text(index)
    text_sha = sha256_bytes(text.encode("utf-8"))
    metadata = _metadata(index)
    metadata_fingerprint = "sha256:" + sha256_bytes(
        hm24.historical_metadata_canonical_bytes(metadata)
    )
    record_id = derive_sha256_id({"synthetic_historical_record": index})

    if relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE:
        successor_key = None
        successor_sha = None
    elif relationship is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT:
        successor_key = f"synthetic-current-key-{index:04d}"
        successor_sha = text_sha
    elif relationship is HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT:
        successor_key = key
        successor_sha = sha256_bytes(f"synthetic current changed {index}".encode("utf-8"))
    else:
        successor_key = key
        successor_sha = text_sha

    entry = SimpleNamespace(
        historical_record_id=record_id,
        historical_evidence_key=key,
        document_name=metadata["document_name"],
        document_id=f"synthetic-document-id-{index:04d}",
        page=index + 1,
        chunk_id=f"synthetic-chunk-{index:04d}",
        historical_current_chroma_text_sha256=text_sha,
        historical_metadata_fingerprint=metadata_fingerprint,
        historical_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        relationship=relationship,
        current_successor_evidence_key=successor_key,
        current_successor_chunk_text_sha256=successor_sha,
        binding_key_collision_risk=(relationship is not HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT),
    )
    observation = hm23.HistoricalSnapshotCaptureObservation(
        historical_record_id=record_id,
        historical_evidence_key=key,
        relationship=relationship,
        document_name=entry.document_name,
        document_id=entry.document_id,
        page=entry.page,
        chunk_id=entry.chunk_id,
        historical_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        expected_text_sha256=text_sha,
        observed_text_sha256=text_sha,
        expected_metadata_fingerprint=metadata_fingerprint,
        observed_metadata_fingerprint=metadata_fingerprint,
        observed_row_id=key,
        observed_row_count=1,
        current_successor_evidence_key=successor_key,
        current_successor_chunk_text_sha256=successor_sha,
        binding_key_collision_risk=entry.binding_key_collision_risk,
        status=hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED,
        blockers=(),
    )
    row = hm25._ObservedHistoricalRow(
        row_id=key,
        document=text,
        metadata=metadata,
    )
    material = hm24.HistoricalSnapshotMaterial(
        historical_record_id=record_id,
        historical_text=text,
        historical_metadata=metadata,
    )
    return entry, observation, row, material


def _corpus(tree_sha: str = DEFAULT_TREE_ID):
    values = [_entry_and_observation(index) for index in range(745)]
    entries = tuple(sorted((item[0] for item in values), key=lambda item: item.historical_record_id))
    observations = tuple(
        sorted((item[1] for item in values), key=lambda item: item.historical_record_id)
    )
    rows = tuple(item[2] for item in values)
    materials = {item[3].historical_record_id: item[3] for item in values}
    manifest = SimpleNamespace(
        case_id=CASE_ID,
        hm1_report_id=HM1_ID,
        pfcr1_report_id=PFCR1_ID,
        entries=entries,
        historical_evidence_disposition_manifest_id=HM2_ID,
    )
    provisional = hm23.HistoricalSnapshotCaptureRehearsalReport(
        schema_version=hm23.HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION,
        case_id=CASE_ID,
        hm1_report_id=HM1_ID,
        pfcr1_report_id=PFCR1_ID,
        hm2_manifest_id=HM2_ID,
        retained_source_tree_sha256=tree_sha,
        observations=observations,
        historical_record_count=745,
        exact_text_verified_count=745,
        text_hash_mismatch_count=0,
        row_missing_count=0,
        row_ambiguous_count=0,
        metadata_mismatch_count=0,
        unreadable_count=0,
        historical_snapshot_capture_rehearsal_report_id="sha256:" + ("0" * 64),
    )
    report = replace(
        provisional,
        historical_snapshot_capture_rehearsal_report_id=derive_sha256_id(
            hm23.historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(
                provisional
            )
        ),
    )
    hm23.validate_historical_snapshot_capture_rehearsal_report(report)
    return manifest, report, rows, materials


def _changed_entry(entry, **changes):
    data = dict(vars(entry))
    data.update(changes)
    return SimpleNamespace(**data)


def _changed_manifest(manifest, *, entries=None, **changes):
    data = dict(vars(manifest))
    if entries is not None:
        data["entries"] = tuple(entries)
    data.update(changes)
    return SimpleNamespace(**data)


def _report_with(report, **changes):
    provisional = replace(
        report,
        **changes,
        historical_snapshot_capture_rehearsal_report_id="sha256:" + ("0" * 64),
    )
    return replace(
        provisional,
        historical_snapshot_capture_rehearsal_report_id=derive_sha256_id(
            hm23.historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(
                provisional
            )
        ),
    )


def _synthetic_roots(tmp_path: Path):
    retained_parent = tmp_path / "retained-parent"
    retained_parent.mkdir()
    retained = retained_parent / "synthetic-retained"
    retained.mkdir()
    (retained / "seed.bin").write_bytes(b"synthetic retained database bytes")
    workspace_parent = tmp_path / "workspace-parent"
    workspace_parent.mkdir()
    workspace = workspace_parent / "hm25-workspace"
    store = SourceEvidenceStore(tmp_path / "synthetic-source-store-v1")
    tree_sha = hm25._build_tree_manifest(
        retained,
        require_exists=True,
        label="Synthetic retained tree",
    ).tree_sha256
    return retained, workspace, store, tree_sha


def _run_public(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, rows_transform=None):
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, materials = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    if rows_transform is not None:
        rows = rows_transform(rows, manifest, report, retained, workspace, store)
    opened: list[Path] = []

    def observe(disposable: Path):
        opened.append(disposable)
        return rows

    monkeypatch.setattr(hm25, "_observe_disposable_collection", observe)
    result = hm25.prepare_historical_snapshot_publication_plan(
        hm2_manifest=manifest,
        hm23_report=report,
        retained_db_root=retained,
        workspace_root=workspace,
        expected_retained_tree_sha256=tree_sha,
        source_store=store,
    )
    return result, manifest, report, rows, materials, retained, workspace, store, tree_sha, opened


def _direct_plan(tree_sha: str = DEFAULT_TREE_ID):
    _, report, _, materials = _corpus(tree_sha)
    return hm24.build_historical_snapshot_publication_plan(
        rehearsal_report=report,
        materials=materials,
    )


# 01

def test_schema_and_public_api_are_exact() -> None:
    assert hm25.HISTORICAL_MATERIAL_PREPARATION_SCHEMA_VERSION == (
        "historical-material-preparation/1.0"
    )
    assert hm25.__all__ == [
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


# 02

def test_valid_synthetic_material_preparation(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert result.report.historical_record_count == 745
    assert result.report.production_mutation_count == 0
    assert result.report.planned_manifest_id == result.publication_plan.manifest.historical_snapshot_manifest_id


# 03

def test_invalid_hm22_manifest_fails_before_workspace(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, *_ = _corpus(tree_sha)
    monkeypatch.setattr(
        hm25,
        "validate_historical_evidence_disposition_manifest",
        lambda _: (_ for _ in ()).throw(ValueError("synthetic invalid HM2.2")),
    )
    with pytest.raises(ValueError, match="synthetic invalid HM2.2"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )
    assert not workspace.exists()


# 04

def test_invalid_hm23_report_fails_before_workspace(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, *_ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    bad = replace(report, historical_snapshot_capture_rehearsal_report_id="sha256:" + ("0" * 64))
    with pytest.raises(ValueError):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=bad,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )
    assert not workspace.exists()


# 05-08 authority linkage
@pytest.mark.parametrize(
    ("manifest_changes", "report_changes", "message"),
    [
        ({"case_id": "87654321-4321-4321-8321-cba987654321"}, {}, "case"),
        ({"hm1_report_id": derive_sha256_id({"other": "hm1"})}, {}, "HM1"),
        ({"pfcr1_report_id": derive_sha256_id({"other": "pfcr1"})}, {}, "PFCR1"),
        ({"historical_evidence_disposition_manifest_id": derive_sha256_id({"other": "hm2"})}, {}, "HM2.2"),
    ],
)
def test_authority_linkage_mismatches_fail(monkeypatch, manifest_changes, report_changes, message) -> None:
    manifest, report, *_ = _corpus()
    manifest = _changed_manifest(manifest, **manifest_changes)
    report = _report_with(report, **report_changes) if report_changes else report
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match=message):
        hm25._validate_authority_linkage(
            hm2_manifest=manifest,
            hm23_report=report,
            expected_retained_tree_sha256=DEFAULT_TREE_ID,
        )


# 09

def test_wrong_retained_authority_blocks_before_chroma(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, *_ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    called = False

    def observe(_):
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr(hm25, "_observe_disposable_collection", observe)
    wrong = derive_sha256_id({"wrong": "retained"})
    with pytest.raises(hm25.HistoricalMaterialPreparationError):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=wrong,
            source_store=store,
        )
    assert called is False
    assert workspace.exists() is False


# 10

def test_workspace_must_be_fresh(tmp_path) -> None:
    retained, workspace, store, _ = _synthetic_roots(tmp_path)
    workspace.mkdir()
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="must not already exist"):
        hm25._safe_workspace_root(
            workspace,
            retained_root=retained,
            source_store_root=store.root,
        )


# 11

def test_retained_workspace_overlap_rejected(tmp_path) -> None:
    retained, _, store, _ = _synthetic_roots(tmp_path)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="retained"):
        hm25._safe_workspace_root(
            retained / "workspace",
            retained_root=retained,
            source_store_root=store.root,
        )


# 12

def test_project_workspace_overlap_rejected(tmp_path) -> None:
    retained, _, store, _ = _synthetic_roots(tmp_path)
    project_root = Path(hm25.__file__).resolve().parents[2]
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="project root"):
        hm25._safe_workspace_root(
            project_root / "synthetic-workspace-never-created",
            retained_root=retained,
            source_store_root=store.root,
        )


# 13

def test_source_store_workspace_overlap_rejected(tmp_path) -> None:
    retained, _, store, _ = _synthetic_roots(tmp_path)
    store.root.mkdir(parents=True)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="source-evidence store"):
        hm25._safe_workspace_root(
            store.root / "workspace",
            retained_root=retained,
            source_store_root=store.root,
        )


# 14

def test_workspace_parent_must_exist(tmp_path) -> None:
    retained, _, store, _ = _synthetic_roots(tmp_path)
    workspace = tmp_path / "missing-parent" / "workspace"
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="parent"):
        hm25._safe_workspace_root(
            workspace,
            retained_root=retained,
            source_store_root=store.root,
        )


# 15

def test_link_like_retained_root_rejected_when_supported(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "retained-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="link-like"):
        hm25._safe_existing_directory(link, label="Synthetic retained")


# 16

def test_symlink_in_retained_tree_rejected_when_supported(tmp_path) -> None:
    retained = tmp_path / "retained"
    retained.mkdir()
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = retained / "link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlink unavailable: {exc}")
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="link-like"):
        hm25._build_tree_manifest(retained, require_exists=True, label="Synthetic retained")


# 17

def test_reparse_point_flag_is_rejected(monkeypatch, tmp_path) -> None:
    path = tmp_path / "entry"
    path.write_bytes(b"x")
    monkeypatch.setattr(type(path), "is_symlink", lambda self: False)
    if hasattr(type(path), "is_junction"):
        monkeypatch.setattr(type(path), "is_junction", lambda self: False)
    monkeypatch.setattr(
        hm25.os,
        "lstat",
        lambda _: SimpleNamespace(st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)),
    )
    assert hm25._is_link_like(path) is True


# 18
@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_is_rejected_when_available(tmp_path) -> None:
    target = tmp_path / "junction-target"
    target.mkdir()
    junction = tmp_path / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Windows junction creation unavailable")
    assert hm25._is_link_like(junction) is True


# 19

def test_disposable_copy_is_exact_before_chroma(monkeypatch, tmp_path) -> None:
    result, _, _, _, _, retained, workspace, _, _, opened = _run_public(monkeypatch, tmp_path)
    retained_tree = hm25._build_tree_manifest(retained, require_exists=True, label="retained")
    disposable_tree = hm25._build_tree_manifest(
        workspace / "retained-db-copy", require_exists=True, label="disposable"
    )
    assert disposable_tree == retained_tree
    assert opened == [workspace / "retained-db-copy"]
    assert result.report.production_mutation_count == 0


# 20

def test_retained_mutation_during_copy_fails_closed(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, _ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    original = hm25._copy_tree_exact

    def mutating_copy(source, destination, tree):
        original(source, destination, tree)
        (retained / "seed.bin").write_bytes(b"changed")

    monkeypatch.setattr(hm25, "_copy_tree_exact", mutating_copy)
    monkeypatch.setattr(hm25, "_observe_disposable_collection", lambda _: rows)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="changed during disposable-copy"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )


# 21

def test_retained_mutation_during_observation_fails_closed(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, _ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)

    def observe(_):
        (retained / "seed.bin").write_bytes(b"changed during observation")
        return rows

    monkeypatch.setattr(hm25, "_observe_disposable_collection", observe)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="changed during disposable observation"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )


# 22

def test_disposable_runtime_mutation_is_permitted(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, _ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)

    def observe(disposable):
        (disposable / "runtime-bookkeeping.bin").write_bytes(b"permitted disposable mutation")
        return rows

    monkeypatch.setattr(hm25, "_observe_disposable_collection", observe)
    result = hm25.prepare_historical_snapshot_publication_plan(
        hm2_manifest=manifest,
        hm23_report=report,
        retained_db_root=retained,
        workspace_root=workspace,
        expected_retained_tree_sha256=tree_sha,
        source_store=store,
    )
    assert result.report.production_mutation_count == 0


# 23-24

def test_chroma_observer_receives_disposable_only(monkeypatch, tmp_path) -> None:
    _, _, _, _, _, retained, workspace, _, _, opened = _run_public(monkeypatch, tmp_path)
    assert opened == [workspace / "retained-db-copy"]
    assert opened[0] != retained


# 25-26

def test_observer_closes_client_and_makes_one_complete_get(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {"get_count": 0}

    class FakeCollection:
        def get(self, *, include):
            calls["get_count"] = int(calls["get_count"]) + 1
            calls["include"] = include
            return {"ids": ["row"], "documents": ["text"], "metadatas": [{"a": 1}]}

    class FakeClient:
        def __init__(self, *, path: str):
            calls["path"] = path
            calls["closed"] = False

        def get_collection(self, *, name: str):
            calls["collection"] = name
            return FakeCollection()

        def close(self):
            calls["closed"] = True

    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=FakeClient))
    rows = hm25._observe_disposable_collection(tmp_path)
    assert len(rows) == 1
    assert calls["get_count"] == 1
    assert calls["include"] == ["documents", "metadatas"]
    assert calls["collection"] == "legal_documents"
    assert calls["closed"] is True


# 27

def test_real_synthetic_chroma_observation_when_available(tmp_path) -> None:
    chromadb = pytest.importorskip("chromadb")
    root = tmp_path / "synthetic-chroma"
    client = chromadb.PersistentClient(path=str(root))
    collection = client.create_collection(name="legal_documents")
    collection.add(
        ids=["synthetic-row"],
        documents=["synthetic exact text"],
        metadatas=[{"case_id": CASE_ID}],
        embeddings=[[0.0, 0.0, 0.0]],
    )
    closer = getattr(client, "close", None)
    if callable(closer):
        closer()
    rows = hm25._observe_disposable_collection(root)
    assert [(item.row_id, item.document) for item in rows] == [
        ("synthetic-row", "synthetic exact text")
    ]


# 28-32
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "missing"),
        ("ambiguous", "ambiguous"),
        ("metadata", "metadata"),
        ("unreadable", "unreadable"),
        ("text", "text"),
    ],
)
def test_reacquisition_row_failures_quarantine(monkeypatch, mutation, message) -> None:
    manifest, report, rows, _ = _corpus()
    first = manifest.entries[0]
    target = next(row for row in rows if row.row_id == first.historical_evidence_key)
    kept = [row for row in rows if row.row_id != first.historical_evidence_key]
    if mutation == "missing":
        changed_rows = tuple(kept)
    elif mutation == "ambiguous":
        changed_rows = tuple(kept + [target, target])
    elif mutation == "metadata":
        changed_rows = tuple(kept + [hm25._ObservedHistoricalRow(target.row_id, target.document, {"wrong": True})])
    elif mutation == "unreadable":
        changed_rows = tuple(kept + [hm25._ObservedHistoricalRow(target.row_id, b"bytes", target.metadata)])
    else:
        changed_rows = tuple(kept + [hm25._ObservedHistoricalRow(target.row_id, "different", target.metadata)])
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match=message):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=changed_rows)


# 33-38
@pytest.mark.parametrize(
    ("entry_field", "observation_field", "message"),
    [
        ("historical_current_chroma_text_sha256", None, "record authority mismatch"),
        (None, "expected_text_sha256", "record authority mismatch"),
        (None, "observed_text_sha256", "HM2.3 observed authority"),
        ("historical_metadata_fingerprint", None, "record authority mismatch"),
        (None, "expected_metadata_fingerprint", "record authority mismatch"),
        (None, "observed_metadata_fingerprint", "HM2.3 observed authority"),
    ],
)
def test_record_authority_hash_mismatch_fails(entry_field, observation_field, message) -> None:
    manifest, report, rows, _ = _corpus()
    entries = list(manifest.entries)
    observations = list(report.observations)
    record_id = entries[0].historical_record_id
    obs_index = next(i for i, item in enumerate(observations) if item.historical_record_id == record_id)
    if entry_field:
        entries[0] = _changed_entry(entries[0], **{entry_field: derive_sha256_id({"wrong": entry_field}) if "fingerprint" in entry_field else sha256_bytes(b"wrong")})
        manifest = _changed_manifest(manifest, entries=entries)
    if observation_field:
        wrong = derive_sha256_id({"wrong": observation_field}) if "fingerprint" in observation_field else sha256_bytes(b"wrong")
        observations[obs_index] = replace(observations[obs_index], **{observation_field: wrong})
        # For expected-field mismatches we intentionally bypass HM2.3 validator and test HM2.5 cross-authority checks.
        report = replace(report, observations=tuple(observations))
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match=message):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=rows)


# 39-42 exact byte identity
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("line1\nline2", "line1\r\nline2"),
        ("é", "e\u0301"),
        (" text", "text"),
        ("text ", "text"),
    ],
)
def test_exact_text_identity_is_not_normalized(left, right) -> None:
    assert left.encode("utf-8") != right.encode("utf-8")
    assert sha256_bytes(left.encode("utf-8")) != sha256_bytes(right.encode("utf-8"))


# 43-46 relationship rules

def test_same_key_same_text_preserved_in_plan() -> None:
    entry = next(item for item in _direct_plan().manifest.entries if item.relationship is HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT)
    assert entry.historical_evidence_key == entry.current_successor_evidence_key
    assert entry.historical_text_blob_sha256 == entry.current_successor_chunk_text_sha256


def test_same_key_different_text_never_substitutes_successor() -> None:
    entry = next(item for item in _direct_plan().manifest.entries if item.relationship is HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT)
    assert entry.historical_evidence_key == entry.current_successor_evidence_key
    assert entry.historical_text_blob_sha256 != entry.current_successor_chunk_text_sha256


def test_changed_key_same_text_shares_bytes_not_identity() -> None:
    entry = next(item for item in _direct_plan().manifest.entries if item.relationship is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT)
    assert entry.historical_evidence_key != entry.current_successor_evidence_key
    assert entry.historical_text_blob_sha256 == entry.current_successor_chunk_text_sha256


def test_no_direct_correspondence_requires_no_successor() -> None:
    entry = next(item for item in _direct_plan().manifest.entries if item.relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE)
    assert entry.current_successor_evidence_key is None
    assert entry.current_successor_chunk_text_sha256 is None


# 47-48

def test_all_historical_classes_remain_legacy() -> None:
    plan = _direct_plan()
    assert all(item.historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT for item in plan.manifest.entries)


def test_full_chain_historical_entry_is_rejected_by_corpus_invariant() -> None:
    manifest, report, *_ = _corpus()
    entries = list(manifest.entries)
    entries[0] = _changed_entry(entries[0], historical_binding_class=BindingClass.FULL_CHAIN_BOUND)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="LEGACY_CURRENT_INDEX_SNAPSHOT"):
        hm25._validate_corpus_invariants(hm2_manifest=_changed_manifest(manifest, entries=entries), hm23_report=report)


# 49-52 corpus invariants

def test_historical_record_count_must_be_745() -> None:
    manifest, report, *_ = _corpus()
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="745"):
        hm25._validate_corpus_invariants(hm2_manifest=_changed_manifest(manifest, entries=manifest.entries[:-1]), hm23_report=report)


def test_distinct_text_digest_count_must_be_396() -> None:
    manifest, report, *_ = _corpus()
    entries = list(manifest.entries)
    counts = {}
    indices_by_sha = {}
    for index, entry in enumerate(entries):
        digest = entry.historical_current_chroma_text_sha256
        counts[digest] = counts.get(digest, 0) + 1
        indices_by_sha.setdefault(digest, index)
    singleton_indices = [indices_by_sha[digest] for digest, count in counts.items() if count == 1]
    left, right = singleton_indices[:2]
    entries[right] = _changed_entry(
        entries[right],
        historical_current_chroma_text_sha256=entries[left].historical_current_chroma_text_sha256,
    )
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="396"):
        hm25._validate_corpus_invariants(hm2_manifest=_changed_manifest(manifest, entries=entries), hm23_report=report)


def test_distinct_metadata_fingerprint_count_must_be_745() -> None:
    manifest, report, *_ = _corpus()
    entries = list(manifest.entries)
    entries[1] = _changed_entry(entries[1], historical_metadata_fingerprint=entries[0].historical_metadata_fingerprint)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="745"):
        hm25._validate_corpus_invariants(hm2_manifest=_changed_manifest(manifest, entries=entries), hm23_report=report)


def test_relationship_partition_must_be_exact() -> None:
    manifest, report, *_ = _corpus()
    entries = list(manifest.entries)
    index = next(i for i, item in enumerate(entries) if item.relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE)
    entries[index] = _changed_entry(entries[index], relationship=HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="304/59/30/352"):
        hm25._validate_corpus_invariants(hm2_manifest=_changed_manifest(manifest, entries=entries), hm23_report=report)


# 53

def test_hm24_historical_snapshot_material_is_used_directly(monkeypatch, tmp_path) -> None:
    captured = {}
    original = hm25.build_historical_snapshot_publication_plan

    def capture(*, rehearsal_report, materials):
        captured["types"] = {type(item) for item in materials.values()}
        return original(rehearsal_report=rehearsal_report, materials=materials)

    monkeypatch.setattr(hm25, "build_historical_snapshot_publication_plan", capture)
    _run_public(monkeypatch, tmp_path)
    assert captured["types"] == {hm24.HistoricalSnapshotMaterial}


# 54

def test_hm24_exact_material_coverage_is_required() -> None:
    _, report, _, materials = _corpus()
    materials.pop(next(iter(materials)))
    with pytest.raises(hm24.HistoricalSnapshotError, match="coverage mismatch"):
        hm24.build_historical_snapshot_publication_plan(rehearsal_report=report, materials=materials)


# 55-56

def test_frozen_hm24_builder_produces_valid_plan() -> None:
    plan = _direct_plan()
    hm24.validate_historical_snapshot_publication_plan(plan)
    assert len(plan.manifest.entries) == 745


# 57

def test_plan_is_deterministic_across_material_mapping_order() -> None:
    _, report, _, materials = _corpus()
    first = hm24.build_historical_snapshot_publication_plan(rehearsal_report=report, materials=materials)
    reversed_materials = dict(reversed(tuple(materials.items())))
    second = hm24.build_historical_snapshot_publication_plan(rehearsal_report=report, materials=reversed_materials)
    assert first == second


# 58-59

def test_planned_manifest_bytes_and_id_are_deterministic() -> None:
    first = _direct_plan()
    second = _direct_plan()
    assert first.manifest.historical_snapshot_manifest_id == second.manifest.historical_snapshot_manifest_id
    assert hm24.dumps_historical_snapshot_manifest(first.manifest) == hm24.dumps_historical_snapshot_manifest(second.manifest)


# 60

def test_source_store_pre_post_tree_is_identical(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert result.report.source_store_pre_tree_sha256 == result.report.source_store_post_tree_sha256


# 61

def test_absent_planned_blobs_are_new_required(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    plan = _direct_plan()
    assessments = hm25._assess_planned_blobs_read_only(store=store, plan=plan)
    assert all(item.disposition is hm25.HistoricalMaterialBlobDisposition.NEW_REQUIRED for item in assessments)


# 62

def test_exact_existing_blob_is_existing_verified(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    plan = _direct_plan()
    blob = plan.blobs[0]
    store.put_blob(blob.content)
    assessments = hm25._assess_planned_blobs_read_only(store=store, plan=plan)
    assessed = next(item for item in assessments if item.sha256_hex == blob.sha256_hex)
    assert assessed.disposition is hm25.HistoricalMaterialBlobDisposition.EXISTING_VERIFIED


# 63

def test_corrupt_existing_blob_fails_closed(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    plan = _direct_plan()
    blob = plan.blobs[0]
    store.put_blob(blob.content)
    path = store.root / "blobs" / "sha256" / blob.sha256_hex[:2] / blob.sha256_hex
    path.write_bytes(b"corrupted")
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="verification"):
        hm25._assess_planned_blobs_read_only(store=store, plan=plan)


# 64

def test_physical_dedup_preserves_745_logical_records() -> None:
    plan = _direct_plan()
    assert len(plan.manifest.entries) == 745
    assert len({item.historical_text_blob_sha256 for item in plan.manifest.entries}) == 396


# 65

def test_durable_preparation_report_contains_no_plaintext(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    dumped = hm25.dumps_historical_material_preparation_report(result.report)
    assert "synthetic historical text" not in dumped
    assert "synthetic_ordinal" not in dumped


# 66

def test_transient_publication_plan_is_not_serialized(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    dumped = hm25.dumps_historical_material_preparation_report(result.report)
    assert "publication_plan" not in dumped
    assert "synthetic historical text" not in dumped


# 67

def test_workspace_paths_are_excluded_from_semantic_report_identity(monkeypatch, tmp_path) -> None:
    result, _, _, _, _, retained, workspace, *_ = _run_public(monkeypatch, tmp_path)
    dumped = hm25.dumps_historical_material_preparation_report(result.report)
    assert str(retained) not in dumped
    assert str(workspace) not in dumped
    assert "retained-db-copy" not in dumped


# 68-72 publication prohibitions

def test_module_has_no_publication_capability_calls() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = {
        "publish_historical_snapshot_publication_plan",
        "put_blob",
        "publish_document_manifest",
        "publish_evidence_binding",
        "publish_analysis_receipt",
        "publish_projection_binding",
    }
    assert not (called_names & forbidden)
    assert not (called_attrs & forbidden)


# 73

def test_module_has_no_current_chroma_mutation_calls() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (
        called_attrs
        & {"add", "upsert", "update", "delete", "reset", "create_collection", "delete_collection", "get_or_create_collection"}
    )


# 74

def test_module_contains_no_real_production_path_literals() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8").casefold()
    forbidden = (
        "retained-old-active",
        "production-cutover",
        "report_projections",
        "c:\\users\\",
        "/users/",
        "/home/",
    )
    assert not any(item in source for item in forbidden)


# 75-76

def test_module_has_no_ui_openai_retrieval_ocr_or_pdf_dependencies() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports |= {node.module}
    forbidden = (
        "openai",
        "streamlit",
        "retriever",
        "legal_analysis",
        "case_analysis",
        "pypdf",
        "pdf2image",
        "pytesseract",
    )
    assert not any(name.startswith(forbidden) for name in imports)


# 77

def test_module_has_no_git_mutation_subprocess_capability() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports |= {node.module}
    assert "subprocess" not in imports
    assert "git" not in imports


# 78

def test_module_has_no_delete_or_repair_filesystem_calls() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called_attrs & {"unlink", "rmdir", "rmtree", "remove", "rename"})


# 79

def test_module_has_no_retry_while_loop() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))


# Additional deterministic-report evidence required by Board return.
def test_preparation_report_identity_is_deterministic(monkeypatch, tmp_path) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    first, *_ = _run_public(monkeypatch, first_root)
    # A separate pytest root gives different operational paths but identical semantic authority.
    second_root = tmp_path / "second"
    second_root.mkdir()
    second, *_ = _run_public(monkeypatch, second_root)
    assert first.report.historical_material_preparation_report_id == second.report.historical_material_preparation_report_id
    assert hm25.dumps_historical_material_preparation_report(first.report) == hm25.dumps_historical_material_preparation_report(second.report)


def test_preparation_report_id_tamper_is_rejected(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="not canonical"):
        hm25.validate_historical_material_preparation_report(
            replace(result.report, historical_material_preparation_report_id=derive_sha256_id({"tampered": True}))
        )


def test_source_store_change_during_assessment_quarantines(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, _ = _corpus(tree_sha)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    monkeypatch.setattr(hm25, "_observe_disposable_collection", lambda _: rows)
    original = hm25._assess_planned_blobs_read_only

    def mutate_store(*, store, plan):
        assessments = original(store=store, plan=plan)
        store.root.mkdir(parents=True, exist_ok=True)
        (store.root / "concurrent-change.bin").write_bytes(b"changed")
        return assessments

    monkeypatch.setattr(hm25, "_assess_planned_blobs_read_only", mutate_store)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="Source-evidence store changed"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )


def test_failure_preserves_disposable_quarantine_state(monkeypatch, tmp_path) -> None:
    retained, workspace, store, tree_sha = _synthetic_roots(tmp_path)
    manifest, report, rows, _ = _corpus(tree_sha)
    first_key = manifest.entries[0].historical_evidence_key
    rows = tuple(row for row in rows if row.row_id != first_key)
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    monkeypatch.setattr(hm25, "_observe_disposable_collection", lambda _: rows)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="missing"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=manifest,
            hm23_report=report,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=tree_sha,
            source_store=store,
        )
    assert workspace.is_dir()
    assert (workspace / "retained-db-copy").is_dir()
    assert (retained / "seed.bin").is_file()


def test_source_store_tree_rejects_symlink_entry_when_supported(tmp_path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    target = tmp_path / "outside.bin"
    target.write_bytes(b"x")
    link = root / "unsafe"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlink unavailable: {exc}")
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="link-like"):
        hm25._build_tree_manifest(root, require_exists=True, label="Synthetic store")


def test_blob_assessments_are_sorted_by_sha(tmp_path) -> None:
    assessments = hm25._assess_planned_blobs_read_only(
        store=SourceEvidenceStore(tmp_path / "store"),
        plan=_direct_plan(),
    )
    values = tuple(item.sha256_hex for item in assessments)
    assert values == tuple(sorted(values))


def test_blob_roles_are_nonempty_and_canonical(tmp_path) -> None:
    assessments = hm25._assess_planned_blobs_read_only(
        store=SourceEvidenceStore(tmp_path / "store"),
        plan=_direct_plan(),
    )
    assert all(item.roles == tuple(sorted(set(item.roles))) and item.roles for item in assessments)


def test_report_existing_plus_new_equals_planned(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert result.report.existing_blob_reuse_count + result.report.new_blob_requirement_count == result.report.planned_blob_count


def test_report_full_chain_count_is_zero(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert result.report.full_chain_count == 0


def test_report_relationship_counts_are_exact(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert (
        result.report.same_key_same_text_count,
        result.report.same_key_different_text_count,
        result.report.changed_key_same_text_count,
        result.report.no_direct_correspondence_count,
    ) == (304, 59, 30, 352)


def test_report_corpus_digest_counts_are_exact(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert result.report.distinct_text_digest_count == 396
    assert result.report.distinct_metadata_fingerprint_count == 745


def test_report_manifest_file_sha_matches_exact_frozen_bytes(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    manifest_bytes = hm24.dumps_historical_snapshot_manifest(result.publication_plan.manifest).encode("utf-8")
    assert result.report.planned_manifest_file_sha256 == sha256_bytes(manifest_bytes)
    assert result.report.planned_manifest_byte_length == len(manifest_bytes)


def test_report_json_has_exactly_one_final_lf(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    dumped = hm25.dumps_historical_material_preparation_report(result.report)
    assert dumped.endswith("\n") and not dumped.endswith("\n\n")


def test_report_identity_payload_excludes_report_id(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    payload = hm25.historical_material_preparation_report_identity_payload_to_dict(result.report)
    assert "historical_material_preparation_report_id" not in payload


def test_blob_assessment_dict_contains_no_blob_bytes(tmp_path) -> None:
    assessment = hm25._assess_planned_blobs_read_only(
        store=SourceEvidenceStore(tmp_path / "store"), plan=_direct_plan()
    )[0]
    payload = hm25.historical_material_blob_assessment_to_dict(assessment)
    assert set(payload) == {"sha256_hex", "byte_length", "roles", "disposition"}


def test_chroma_parser_rejects_malformed_mapping() -> None:
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="malformed"):
        hm25._parse_chroma_response([])


@pytest.mark.parametrize(
    "response",
    [
        {"ids": "bad", "documents": [], "metadatas": []},
        {"ids": [], "documents": "bad", "metadatas": []},
        {"ids": [], "documents": [], "metadatas": "bad"},
        {"ids": ["a"], "documents": [], "metadatas": []},
        {"ids": [1], "documents": ["x"], "metadatas": [{}]},
        {"ids": ["a"], "documents": ["x"], "metadatas": ["bad"]},
    ],
)
def test_chroma_parser_rejects_malformed_components(response) -> None:
    with pytest.raises(hm25.HistoricalMaterialPreparationError):
        hm25._parse_chroma_response(response)


def test_chroma_parser_accepts_none_documents_and_metadata() -> None:
    rows = hm25._parse_chroma_response(
        {"ids": ["a"], "documents": None, "metadatas": None}
    )
    assert rows[0].document is None
    assert rows[0].metadata == {}


def test_metadata_canonicalization_is_hm24_public_contract() -> None:
    metadata = {"z": "café £", "a": [1, True, None]}
    expected = json.dumps(
        metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hm24.historical_metadata_canonical_bytes(metadata) == expected


def test_report_validation_rejects_nonzero_production_mutation(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="zero"):
        hm25.validate_historical_material_preparation_report(
            replace(result.report, production_mutation_count=1)
        )


def test_report_validation_rejects_source_store_tree_mismatch(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="changed"):
        hm25.validate_historical_material_preparation_report(
            replace(
                result.report,
                source_store_post_tree_sha256=derive_sha256_id({"different": "tree"}),
            )
        )


def test_source_store_constructor_is_not_itself_a_write(tmp_path) -> None:
    root = tmp_path / "store-v1"
    SourceEvidenceStore(root)
    assert not root.exists()


def test_prepare_does_not_create_absent_source_store_root(monkeypatch, tmp_path) -> None:
    result, *_, store, _, _ = _run_public(monkeypatch, tmp_path)
    assert not store.root.exists()
    assert result.report.new_blob_requirement_count == result.report.planned_blob_count


def test_same_semantics_different_workspace_produces_same_report_id(monkeypatch, tmp_path) -> None:
    retained_parent = tmp_path / "retained-parent"
    retained_parent.mkdir()
    retained = retained_parent / "retained"
    retained.mkdir()
    (retained / "seed").write_bytes(b"same retained bytes")
    tree_sha = hm25._build_tree_manifest(retained, require_exists=True, label="retained").tree_sha256
    manifest, report, rows, _ = _corpus(tree_sha)
    store = SourceEvidenceStore(tmp_path / "store")
    monkeypatch.setattr(hm25, "validate_historical_evidence_disposition_manifest", lambda _: None)
    monkeypatch.setattr(hm25, "_observe_disposable_collection", lambda _: rows)
    parent = tmp_path / "workspaces"
    parent.mkdir()
    first = hm25.prepare_historical_snapshot_publication_plan(
        hm2_manifest=manifest,
        hm23_report=report,
        retained_db_root=retained,
        workspace_root=parent / "one",
        expected_retained_tree_sha256=tree_sha,
        source_store=store,
    )
    second = hm25.prepare_historical_snapshot_publication_plan(
        hm2_manifest=manifest,
        hm23_report=report,
        retained_db_root=retained,
        workspace_root=parent / "two",
        expected_retained_tree_sha256=tree_sha,
        source_store=store,
    )
    assert first.report.historical_material_preparation_report_id == second.report.historical_material_preparation_report_id


def test_hm23_status_must_be_exact_verified() -> None:
    manifest, report, rows, _ = _corpus()
    observations = list(report.observations)
    target = observations[0]
    observations[0] = replace(
        target,
        status=hm23.HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH,
        blockers=("synthetic",),
    )
    report = replace(report, observations=tuple(observations))
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="EXACT_TEXT_VERIFIED"):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=rows)


def test_hm23_observation_blockers_fail() -> None:
    manifest, report, rows, _ = _corpus()
    observations = list(report.observations)
    observations[0] = replace(observations[0], blockers=("synthetic-blocker",))
    report = replace(report, observations=tuple(observations))
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="blockers"):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=rows)


def test_hm23_observed_row_count_must_be_one() -> None:
    manifest, report, rows, _ = _corpus()
    observations = list(report.observations)
    observations[0] = replace(observations[0], observed_row_count=2)
    report = replace(report, observations=tuple(observations))
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="row count"):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=rows)


def test_hm23_observed_row_id_must_match_historical_key() -> None:
    manifest, report, rows, _ = _corpus()
    observations = list(report.observations)
    observations[0] = replace(observations[0], observed_row_id="other-row")
    report = replace(report, observations=tuple(observations))
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="row identity"):
        hm25._build_materials(hm2_manifest=manifest, hm23_report=report, rows=rows)


def test_hm22_hm23_identity_coverage_must_match() -> None:
    manifest, report, *_ = _corpus()
    observations = report.observations[:-1]
    bad = replace(report, observations=observations, historical_record_count=744, exact_text_verified_count=744)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="745"):
        hm25._validate_corpus_invariants(hm2_manifest=manifest, hm23_report=bad)


def test_planned_blob_path_uses_frozen_m2_layout(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    digest = "a" * 64
    assert hm25._planned_blob_path(store, digest) == (
        store.root / "blobs" / "sha256" / "aa" / digest
    )


def test_existing_blob_presence_alone_is_not_proof(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    plan = _direct_plan()
    blob = plan.blobs[0]
    path = store.root / "blobs" / "sha256" / blob.sha256_hex[:2] / blob.sha256_hex
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not the correct bytes")
    with pytest.raises(hm25.HistoricalMaterialPreparationError):
        hm25._assess_planned_blobs_read_only(store=store, plan=plan)


def test_blob_assessment_existing_path_must_be_regular_file(tmp_path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    plan = _direct_plan()
    blob = plan.blobs[0]
    path = store.root / "blobs" / "sha256" / blob.sha256_hex[:2] / blob.sha256_hex
    path.mkdir(parents=True)
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="regular file"):
        hm25._assess_planned_blobs_read_only(store=store, plan=plan)


def test_tree_manifest_is_input_order_independent(tmp_path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "b").write_bytes(b"b")
    (root / "a").write_bytes(b"a")
    first = hm25._build_tree_manifest(root, require_exists=True, label="tree")
    (root / "a").write_bytes(b"a")
    second = hm25._build_tree_manifest(root, require_exists=True, label="tree")
    assert first == second
    assert tuple(item.relative_path for item in first.entries) == ("a", "b")


def test_tree_manifest_absent_root_is_deterministic(tmp_path) -> None:
    first = hm25._build_tree_manifest(tmp_path / "absent", require_exists=False, label="tree")
    second = hm25._build_tree_manifest(tmp_path / "absent", require_exists=False, label="tree")
    assert first == second
    assert first.root_exists is False


def test_required_tree_absence_fails(tmp_path) -> None:
    with pytest.raises(hm25.HistoricalMaterialPreparationError, match="does not exist"):
        hm25._build_tree_manifest(tmp_path / "absent", require_exists=True, label="tree")


def test_prepare_requires_source_evidence_store_instance() -> None:
    with pytest.raises(TypeError, match="SourceEvidenceStore"):
        hm25.prepare_historical_snapshot_publication_plan(
            hm2_manifest=None,
            hm23_report=None,
            retained_db_root=Path("synthetic"),
            workspace_root=Path("synthetic-work"),
            expected_retained_tree_sha256=DEFAULT_TREE_ID,
            source_store=object(),
        )


def test_module_does_not_import_private_hm23_helpers() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("historical_snapshot_rehearsal"):
            assert all(not alias.name.startswith("_") for alias in node.names)


def test_module_does_not_import_private_hm24_helpers() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("historical_snapshot"):
            assert all(not alias.name.startswith("_") for alias in node.names)


def test_module_does_not_import_private_m2_helpers() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("store"):
            assert all(not alias.name.startswith("_") for alias in node.names)


def test_module_does_not_call_hm23_rehearsal_public_executor() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    assert "rehearse_historical_snapshot_capture" not in source


def test_module_does_not_call_hm24_publisher_even_by_text() -> None:
    source = Path(hm25.__file__).read_text(encoding="utf-8")
    assert "publish_historical_snapshot_publication_plan" not in source


def test_module_uses_only_read_blob_from_m2_public_methods() -> None:
    tree = ast.parse(Path(hm25.__file__).read_text(encoding="utf-8"))
    store_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {
            "read_blob",
            "put_blob",
            "publish_document_manifest",
            "publish_evidence_binding",
            "publish_analysis_receipt",
            "publish_projection_binding",
        }
    }
    assert store_attrs == {"read_blob"}


def test_public_success_state_is_prepared_not_published(monkeypatch, tmp_path) -> None:
    result, *_ = _run_public(monkeypatch, tmp_path)
    assert isinstance(result.publication_plan, hm24.HistoricalSnapshotPublicationPlan)
    assert result.report.production_mutation_count == 0
    assert result.report.source_store_pre_tree_sha256 == result.report.source_store_post_tree_sha256


# The Board's 80-82 regression gates are intentionally not recursively invoked by
# this focused test file. They are executed as separate governed commands after
# the focused synthetic suite passes.
