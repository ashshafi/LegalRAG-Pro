"""Synthetic HM2.4 historical snapshot publication-preparation tests.

All persistence uses pytest temporary directories and synthetic material.  These
tests do not access Chroma, the retained historical database, or any production
source-evidence store.
"""

from __future__ import annotations

import ast
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

import source_evidence.historical_snapshot as hm24
import source_evidence.historical_snapshot_rehearsal as hm23
from source_evidence.historical_disposition import HistoricalEvidenceRelationship
from source_evidence.identity import derive_sha256_id, sha256_bytes
from source_evidence.models import BindingClass
from source_evidence.store import SourceEvidenceStore


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
HM1_ID = derive_sha256_id({"authority": "hm1"})
PFCR1_ID = derive_sha256_id({"authority": "pfcr1"})
HM2_ID = derive_sha256_id({"authority": "hm2"})


def _metadata(index: int) -> dict[str, object]:
    return {
        "case_id": CASE_ID,
        "document_name": f"document-{index}.pdf",
        "page": index + 1,
        "nested": {"index": index, "unicode": "café £"},
    }


def _fingerprint(metadata: dict[str, object]) -> str:
    return "sha256:" + sha256_bytes(hm24.historical_metadata_canonical_bytes(metadata))


def _observation(
    index: int,
    *,
    relationship: HistoricalEvidenceRelationship,
    text: str,
    metadata: dict[str, object],
    successor_key: str | None,
    successor_text: str | None,
    collision_risk: bool,
) -> hm23.HistoricalSnapshotCaptureObservation:
    historical_key = (
        f"same-key-{index}"
        if relationship
        in (
            HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT,
            HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT,
        )
        else f"historical-key-{index}"
    )
    text_sha = sha256_bytes(text.encode("utf-8"))
    successor_sha = (
        sha256_bytes(successor_text.encode("utf-8"))
        if successor_key is not None and successor_text is not None
        else None
    )
    if relationship is HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT:
        successor_key = historical_key
        successor_sha = text_sha
    elif relationship is HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT:
        successor_key = historical_key
        assert successor_text is not None
        successor_sha = sha256_bytes(successor_text.encode("utf-8"))
        assert successor_sha != text_sha
    elif relationship is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT:
        successor_key = successor_key or f"current-key-{index}"
        assert successor_key != historical_key
        successor_sha = text_sha
    elif relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE:
        successor_key = None
        successor_sha = None

    fingerprint = _fingerprint(metadata)
    return hm23.HistoricalSnapshotCaptureObservation(
        historical_record_id=derive_sha256_id(
            {"case_id": CASE_ID, "historical_evidence_key": historical_key, "i": index}
        ),
        historical_evidence_key=historical_key,
        relationship=relationship,
        document_name=f"document-{index}.pdf",
        document_id=None,
        page=index + 1,
        chunk_id=f"chunk-{index}",
        historical_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        expected_text_sha256=text_sha,
        observed_text_sha256=text_sha,
        expected_metadata_fingerprint=fingerprint,
        observed_metadata_fingerprint=fingerprint,
        observed_row_id=historical_key,
        observed_row_count=1,
        current_successor_evidence_key=successor_key,
        current_successor_chunk_text_sha256=successor_sha,
        binding_key_collision_risk=collision_risk,
        status=hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED,
        blockers=(),
    )


def _report(
    observations: tuple[hm23.HistoricalSnapshotCaptureObservation, ...],
) -> hm23.HistoricalSnapshotCaptureRehearsalReport:
    observations = tuple(sorted(observations, key=lambda item: item.historical_record_id))
    provisional = hm23.HistoricalSnapshotCaptureRehearsalReport(
        schema_version=hm23.HISTORICAL_SNAPSHOT_CAPTURE_REHEARSAL_SCHEMA_VERSION,
        case_id=CASE_ID,
        hm1_report_id=HM1_ID,
        pfcr1_report_id=PFCR1_ID,
        hm2_manifest_id=HM2_ID,
        retained_source_tree_sha256=derive_sha256_id({"tree": "synthetic"}),
        observations=observations,
        historical_record_count=len(observations),
        exact_text_verified_count=len(observations),
        text_hash_mismatch_count=0,
        row_missing_count=0,
        row_ambiguous_count=0,
        metadata_mismatch_count=0,
        unreadable_count=0,
        historical_snapshot_capture_rehearsal_report_id="sha256:" + ("0" * 64),
    )
    value = replace(
        provisional,
        historical_snapshot_capture_rehearsal_report_id=derive_sha256_id(
            hm23.historical_snapshot_capture_rehearsal_report_identity_payload_to_dict(
                provisional
            )
        ),
    )
    hm23.validate_historical_snapshot_capture_rehearsal_report(value)
    return value


def _four_class_fixture():
    texts = {
        "same": "shared historical/current text",
        "different": "historical version",
        "changed": "same bytes under changed key",
        "orphan": "historical-only text",
    }
    specs = (
        (
            HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT,
            texts["same"],
            "ignored",
            True,
        ),
        (
            HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT,
            texts["different"],
            "current changed version",
            True,
        ),
        (
            HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT,
            texts["changed"],
            texts["changed"],
            False,
        ),
        (
            HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE,
            texts["orphan"],
            None,
            True,
        ),
    )
    observations = []
    materials = {}
    for index, (relationship, text, successor_text, collision) in enumerate(specs):
        metadata = _metadata(index)
        successor_key = (
            None
            if relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE
            else f"current-key-{index}"
        )
        observation = _observation(
            index,
            relationship=relationship,
            text=text,
            metadata=metadata,
            successor_key=successor_key,
            successor_text=successor_text,
            collision_risk=collision,
        )
        observations.append(observation)
        materials[observation.historical_record_id] = hm24.HistoricalSnapshotMaterial(
            historical_record_id=observation.historical_record_id,
            historical_text=text,
            historical_metadata=metadata,
        )
    report = _report(tuple(observations))
    return report, materials


def _plan() -> hm24.HistoricalSnapshotPublicationPlan:
    report, materials = _four_class_fixture()
    return hm24.build_historical_snapshot_publication_plan(
        rehearsal_report=report,
        materials=materials,
    )


def test_schema_and_public_api_are_exact() -> None:
    assert hm24.HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION == (
        "historical-snapshot-manifest/1.0"
    )
    assert hm24.__all__ == [
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


def test_metadata_contract_is_compact_utf8_no_final_lf_and_non_ascii_stable() -> None:
    metadata = {"z": "café £", "a": 1}
    expected = json.dumps(
        metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    actual = hm24.historical_metadata_canonical_bytes(metadata)
    assert actual == expected
    assert not actual.endswith(b"\n")


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("line1\nline2", "line1\r\nline2"),
        ("é", "e\u0301"),
        (" text", "text"),
        ("text ", "text"),
    ],
)
def test_exact_text_identity_does_not_normalize(left: str, right: str) -> None:
    assert left.encode("utf-8") != right.encode("utf-8")
    assert sha256_bytes(left.encode("utf-8")) != sha256_bytes(right.encode("utf-8"))


def test_build_plan_preserves_all_four_relationship_classes() -> None:
    plan = _plan()
    relationships = {entry.relationship for entry in plan.manifest.entries}
    assert relationships == {
        HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT,
        HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT,
        HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT,
        HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE,
    }
    assert all(
        entry.historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        for entry in plan.manifest.entries
    )


def test_no_direct_correspondence_requires_no_successor() -> None:
    entry = next(
        item
        for item in _plan().manifest.entries
        if item.relationship is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE
    )
    assert entry.current_successor_evidence_key is None
    assert entry.current_successor_chunk_text_sha256 is None


def test_same_key_different_text_keeps_historical_blob_distinct() -> None:
    entry = next(
        item
        for item in _plan().manifest.entries
        if item.relationship is HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT
    )
    assert entry.current_successor_evidence_key == entry.historical_evidence_key
    assert entry.current_successor_chunk_text_sha256 != entry.historical_text_blob_sha256


def test_changed_key_same_text_shares_bytes_not_identity() -> None:
    entry = next(
        item
        for item in _plan().manifest.entries
        if item.relationship is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT
    )
    assert entry.current_successor_evidence_key != entry.historical_evidence_key
    assert entry.current_successor_chunk_text_sha256 == entry.historical_text_blob_sha256


def test_manifest_entries_are_sorted_by_historical_record_id() -> None:
    plan = _plan()
    record_ids = tuple(entry.historical_record_id for entry in plan.manifest.entries)
    assert record_ids == tuple(sorted(record_ids))


def test_manifest_identity_is_deterministic_and_round_trips() -> None:
    first = _plan()
    second = _plan()
    assert first.manifest == second.manifest
    dumped = hm24.dumps_historical_snapshot_manifest(first.manifest)
    assert dumped.endswith("\n") and not dumped.endswith("\n\n")
    assert hm24.loads_historical_snapshot_manifest(dumped) == first.manifest


def test_noncanonical_manifest_json_is_rejected() -> None:
    dumped = hm24.dumps_historical_snapshot_manifest(_plan().manifest)
    with pytest.raises(ValueError, match="canonical"):
        hm24.loads_historical_snapshot_manifest(dumped + "\n")


def test_manifest_identity_tamper_is_rejected() -> None:
    manifest = _plan().manifest
    with pytest.raises(ValueError, match="not canonical"):
        hm24.validate_historical_snapshot_manifest(
            replace(
                manifest,
                historical_snapshot_manifest_id=derive_sha256_id({"tampered": True}),
            )
        )


def test_full_chain_historical_class_is_rejected() -> None:
    manifest = _plan().manifest
    changed = replace(
        manifest.entries[0],
        historical_binding_class=BindingClass.FULL_CHAIN_BOUND,
    )
    provisional = replace(
        manifest,
        entries=(changed,) + manifest.entries[1:],
        historical_snapshot_manifest_id="sha256:" + ("0" * 64),
    )
    bad = replace(
        provisional,
        historical_snapshot_manifest_id=derive_sha256_id(
            hm24.historical_snapshot_manifest_identity_payload_to_dict(provisional)
        ),
    )
    with pytest.raises(ValueError, match="LEGACY_CURRENT_INDEX_SNAPSHOT"):
        hm24.validate_historical_snapshot_manifest(bad)


def test_missing_material_fails_before_publication() -> None:
    report, materials = _four_class_fixture()
    materials.pop(next(iter(materials)))
    with pytest.raises(hm24.HistoricalSnapshotError, match="coverage mismatch"):
        hm24.build_historical_snapshot_publication_plan(
            rehearsal_report=report,
            materials=materials,
        )


def test_unexpected_material_fails_before_publication() -> None:
    report, materials = _four_class_fixture()
    materials[derive_sha256_id({"unexpected": True})] = hm24.HistoricalSnapshotMaterial(
        historical_record_id=derive_sha256_id({"unexpected": True}),
        historical_text="x",
        historical_metadata={},
    )
    with pytest.raises(hm24.HistoricalSnapshotError, match="coverage mismatch"):
        hm24.build_historical_snapshot_publication_plan(
            rehearsal_report=report,
            materials=materials,
        )


def test_text_hash_mismatch_fails_before_publication() -> None:
    report, materials = _four_class_fixture()
    key = next(iter(materials))
    materials[key] = replace(materials[key], historical_text="tampered")
    with pytest.raises(hm24.HistoricalSnapshotError, match="text differs"):
        hm24.build_historical_snapshot_publication_plan(
            rehearsal_report=report,
            materials=materials,
        )


def test_metadata_fingerprint_mismatch_fails_before_publication() -> None:
    report, materials = _four_class_fixture()
    key = next(iter(materials))
    materials[key] = replace(
        materials[key],
        historical_metadata={"case_id": CASE_ID, "changed": True},
    )
    with pytest.raises(hm24.HistoricalSnapshotError, match="metadata differs"):
        hm24.build_historical_snapshot_publication_plan(
            rehearsal_report=report,
            materials=materials,
        )


def test_plan_physically_deduplicates_identical_content() -> None:
    text = "same exact historical bytes"
    metadata_a = _metadata(100)
    metadata_b = _metadata(101)
    obs_a = _observation(
        100,
        relationship=HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT,
        text=text,
        metadata=metadata_a,
        successor_key="current-a",
        successor_text=text,
        collision_risk=False,
    )
    obs_b = _observation(
        101,
        relationship=HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT,
        text=text,
        metadata=metadata_b,
        successor_key="current-b",
        successor_text=text,
        collision_risk=False,
    )
    report = _report((obs_a, obs_b))
    materials = {
        obs_a.historical_record_id: hm24.HistoricalSnapshotMaterial(
            obs_a.historical_record_id, text, metadata_a
        ),
        obs_b.historical_record_id: hm24.HistoricalSnapshotMaterial(
            obs_b.historical_record_id, text, metadata_b
        ),
    }
    plan = hm24.build_historical_snapshot_publication_plan(
        rehearsal_report=report, materials=materials
    )
    text_sha = sha256_bytes(text.encode("utf-8"))
    assert sum(blob.sha256_hex == text_sha for blob in plan.blobs) == 1
    assert len(plan.manifest.entries) == 2
    assert (
        plan.manifest.entries[0].historical_record_id
        != plan.manifest.entries[1].historical_record_id
    )


def test_manifest_path_uses_separate_historical_namespace(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    path = hm24.historical_snapshot_manifest_path(
        store=store,
        case_id=plan.manifest.case_id,
        hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
    )
    assert path == (
        store.root
        / "historical-snapshots"
        / "cases"
        / CASE_ID
        / plan.manifest.hm23_rehearsal_report_id[7:]
        / "manifest.json"
    )
    assert not path.exists()


def test_orphan_blobs_are_not_authoritative(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    for blob in plan.blobs:
        store.put_blob(blob.content)
    assert (
        hm24.load_historical_snapshot_manifest(
            store=store,
            case_id=plan.manifest.case_id,
            hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
        )
        is None
    )


def test_publish_plan_writes_blobs_then_manifest_and_round_trips(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    loaded = hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    assert loaded == plan.manifest
    for blob in plan.blobs:
        assert store.read_blob(blob.sha256_hex) == blob.content


def test_identical_republication_is_idempotent(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    first = hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    second = hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    assert first == second == plan.manifest


def test_conflicting_manifest_for_same_hm23_authority_fails(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    hm24.publish_historical_snapshot_publication_plan(plan, store=store)

    changed_entry = replace(plan.manifest.entries[0], document_name="different-name.pdf")
    changed_entries = (changed_entry,) + plan.manifest.entries[1:]
    provisional = replace(
        plan.manifest,
        entries=changed_entries,
        historical_snapshot_manifest_id="sha256:" + ("0" * 64),
    )
    changed_manifest = replace(
        provisional,
        historical_snapshot_manifest_id=derive_sha256_id(
            hm24.historical_snapshot_manifest_identity_payload_to_dict(provisional)
        ),
    )
    changed_plan = replace(plan, manifest=changed_manifest)
    hm24.validate_historical_snapshot_publication_plan(changed_plan)
    with pytest.raises(hm24.HistoricalSnapshotError, match="conflicts"):
        hm24.publish_historical_snapshot_publication_plan(changed_plan, store=store)


def test_concurrent_identical_manifest_writers_converge(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")

    def publish():
        return hm24.publish_historical_snapshot_publication_plan(plan, store=store)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(pool.map(lambda _: publish(), range(4)))
    assert all(item == plan.manifest for item in results)


def test_symlink_escape_in_historical_namespace_is_rejected(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    store.put_blob(b"seed")
    outside = tmp_path / "outside"
    outside.mkdir()
    historical_root = store.root / "historical-snapshots"
    try:
        historical_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    with pytest.raises(hm24.HistoricalSnapshotError, match="Unsafe"):
        hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    assert not list(outside.rglob("manifest.json"))


def test_hard_link_unavailable_fails_closed_and_leaves_no_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    original_link = os.link

    def fail_manifest_link(src, dst, *args, **kwargs):
        if str(dst).endswith("manifest.json"):
            raise OSError("synthetic hard-link failure")
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", fail_manifest_link)
    with pytest.raises(hm24.HistoricalSnapshotError, match="hard-link"):
        hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    path = hm24.historical_snapshot_manifest_path(
        store=store,
        case_id=plan.manifest.case_id,
        hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
    )
    assert not path.exists()
    # Immutable blob orphans are allowed and remain non-authoritative.
    assert all(store.read_blob(blob.sha256_hex) == blob.content for blob in plan.blobs)


def test_tampered_persisted_manifest_fails_closed(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    path = hm24.historical_snapshot_manifest_path(
        store=store,
        case_id=plan.manifest.case_id,
        hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
    )
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(hm24.HistoricalSnapshotError, match="canonical"):
        hm24.load_historical_snapshot_manifest(
            store=store,
            case_id=plan.manifest.case_id,
            hm23_rehearsal_report_id=plan.manifest.hm23_rehearsal_report_id,
        )


def test_module_has_no_forbidden_runtime_dependencies_or_current_binding_publication() -> None:
    path = Path(hm24.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden_imports = (
        "chromadb",
        "openai",
        "pypdf",
        "pdf2image",
        "pytesseract",
        "retriever",
        "legal_analysis",
        "case_analysis",
        "streamlit",
    )
    assert not any(name.startswith(forbidden_imports) for name in imports)

    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (
        calls
        & {
            "publish_evidence_binding",
            "publish_analysis_receipt",
            "publish_projection_binding",
            "upsert",
            "reset",
            "create_collection",
            "delete_collection",
        }
    )


def test_module_contains_no_current_production_path_literals() -> None:
    source = Path(hm24.__file__).read_text(encoding="utf-8")
    forbidden = (
        "retained-old-active",
        "LegalRAG-PFCR3-Production-Cutover",
        "report_projections",
        "current_chroma",
        "legal_documents",
    )
    assert not any(item in source for item in forbidden)


def test_source_store_current_typed_namespaces_are_not_written(tmp_path: Path) -> None:
    plan = _plan()
    store = SourceEvidenceStore(tmp_path / "source-store-v1")
    hm24.publish_historical_snapshot_publication_plan(plan, store=store)
    cases = store.root / "cases"
    assert not cases.exists()
    historical = store.root / "historical-snapshots"
    assert historical.exists()


def test_manifest_blob_coverage_is_exact() -> None:
    plan = _plan()
    extra = hm24.HistoricalSnapshotBlob(
        sha256_hex=sha256_bytes(b"extra"),
        content=b"extra",
    )
    bad = replace(plan, blobs=tuple(sorted(plan.blobs + (extra,), key=lambda b: b.sha256_hex)))
    with pytest.raises(ValueError, match="exactly cover"):
        hm24.validate_historical_snapshot_publication_plan(bad)


def test_blob_content_mismatch_is_rejected() -> None:
    plan = _plan()
    first = plan.blobs[0]
    bad_blob = replace(first, content=first.content + b"x")
    bad = replace(plan, blobs=(bad_blob,) + plan.blobs[1:])
    with pytest.raises(ValueError, match="does not match"):
        hm24.validate_historical_snapshot_publication_plan(bad)


def test_empty_valid_manifest_is_deterministic() -> None:
    provisional = hm24.HistoricalSnapshotManifest(
        schema_version=hm24.HISTORICAL_SNAPSHOT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        hm1_report_id=HM1_ID,
        pfcr1_report_id=PFCR1_ID,
        hm2_manifest_id=HM2_ID,
        hm23_rehearsal_report_id=derive_sha256_id({"hm23": "empty"}),
        entries=(),
        historical_snapshot_manifest_id="sha256:" + ("0" * 64),
    )
    value = replace(
        provisional,
        historical_snapshot_manifest_id=derive_sha256_id(
            hm24.historical_snapshot_manifest_identity_payload_to_dict(provisional)
        ),
    )
    hm24.validate_historical_snapshot_manifest(value)
    assert hm24.loads_historical_snapshot_manifest(
        hm24.dumps_historical_snapshot_manifest(value)
    ) == value
