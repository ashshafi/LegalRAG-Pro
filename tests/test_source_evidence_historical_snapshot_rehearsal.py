"""Synthetic HM2.3 rehearsal tests.

These tests use only pytest temporary directories and synthetic Chroma state.
They never reference the retained pre-PFCR3 production database or any current
production database path.
"""

from __future__ import annotations

import ast
import json
import sys
import types
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import source_evidence.historical_snapshot_rehearsal as hm23
from source_evidence.historical_disposition import (
    HistoricalEvidenceDispositionEntry,
    HistoricalEvidenceRelationship,
)
from source_evidence.identity import derive_sha256_id, sha256_bytes
from source_evidence.models import BindingClass


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
HM1_ID = derive_sha256_id({"authority": "hm1"})
PFCR1_ID = derive_sha256_id({"authority": "pfcr1"})
HM2_ID = derive_sha256_id({"authority": "hm2"})


def _entry(
    index: int,
    *,
    relationship: HistoricalEvidenceRelationship = (
        HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT
    ),
    historical_key: str | None = None,
    historical_text: str | None = None,
    metadata: dict[str, object] | None = None,
    successor_key: str | None = "current-successor",
    successor_text: str | None = None,
    collision_risk: bool = True,
) -> HistoricalEvidenceDispositionEntry:
    text = historical_text if historical_text is not None else f"historical text {index}"
    metadata_value = (
        dict(metadata)
        if metadata is not None
        else {
            "case_id": CASE_ID,
            "document_name": f"document-{index}.pdf",
            "page": index + 1,
        }
    )
    key = historical_key or f"historical-key-{index:04d}"
    successor_sha = (
        sha256_bytes(
            (
                successor_text
                if successor_text is not None
                else f"current successor text {index}"
            ).encode("utf-8")
        )
        if successor_key is not None
        else None
    )
    return HistoricalEvidenceDispositionEntry(
        historical_record_id=derive_sha256_id(
            {
                "case_id": CASE_ID,
                "historical_evidence_key": key,
                "ordinal": index,
            }
        ),
        historical_evidence_key=key,
        document_name=f"document-{index}.pdf",
        document_id=f"document-id-{index}",
        page=index + 1,
        chunk_id=f"chunk-{index}",
        historical_current_chroma_text_sha256=sha256_bytes(text.encode("utf-8")),
        historical_metadata_fingerprint=hm23._metadata_fingerprint(metadata_value),
        historical_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        historical_decision_code="synthetic",
        historical_blockers=("historical_original_identity_missing",),
        historical_recommended_next_action="preserve_historical_identity",
        relationship=relationship,
        prospective_candidate_key=successor_key,
        current_successor_evidence_key=successor_key,
        current_successor_chunk_text_sha256=successor_sha,
        current_text_matches_successor=None,
        same_key_as_future_m3=None,
        binding_key_collision_risk=collision_risk,
    )


def _row(
    entry: HistoricalEvidenceDispositionEntry,
    *,
    document: object | None = None,
    metadata: dict[str, object] | None = None,
    row_id: str | None = None,
) -> hm23._ObservedChromaRow:
    if document is None:
        document = f"historical text {int(entry.chunk_id.split('-')[-1])}"
    if metadata is None:
        metadata = {
            "case_id": CASE_ID,
            "document_name": entry.document_name,
            "page": entry.page,
        }
    return hm23._ObservedChromaRow(
        row_id=row_id or entry.historical_evidence_key,
        document=document,
        metadata=dict(metadata),
    )


def _dummy_authorities(
    entries: tuple[HistoricalEvidenceDispositionEntry, ...],
) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    hm2_manifest = SimpleNamespace(
        entries=entries,
        historical_evidence_disposition_manifest_id=HM2_ID,
    )
    hm1_report = SimpleNamespace(
        historical_migration_report_id=HM1_ID,
    )
    pfcr1_report = SimpleNamespace(
        prospective_reingestion_report_id=PFCR1_ID,
    )
    return hm2_manifest, hm1_report, pfcr1_report


def _synthetic_roots(tmp_path: Path) -> tuple[Path, Path]:
    retained_parent = tmp_path / "retained-parent"
    retained_parent.mkdir()
    retained = retained_parent / "retained-db"
    retained.mkdir()
    (retained / "seed.bin").write_bytes(b"synthetic retained database bytes")

    workspace_parent = tmp_path / "workspace-parent"
    workspace_parent.mkdir()
    workspace = workspace_parent / "hm23-workspace"
    return retained, workspace


def _run_public_with_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    entries: tuple[HistoricalEvidenceDispositionEntry, ...],
    rows: tuple[hm23._ObservedChromaRow, ...],
    observer_hook=None,
):
    hm2_manifest, hm1_report, pfcr1_report = _dummy_authorities(entries)
    retained, workspace = _synthetic_roots(tmp_path)
    retained_manifest = hm23._build_tree_manifest(retained, require_exists=True)

    monkeypatch.setattr(
        hm23,
        "_validate_upstream_authorities",
        lambda **_: CASE_ID,
    )

    opened: list[Path] = []

    def observe(disposable: Path):
        opened.append(disposable)
        if observer_hook is not None:
            observer_hook(disposable, retained)
        return rows

    monkeypatch.setattr(hm23, "_observe_disposable_collection", observe)

    report = hm23.rehearse_historical_snapshot_capture(
        hm2_manifest=hm2_manifest,
        hm1_report=hm1_report,
        pfcr1_report=pfcr1_report,
        retained_db_root=retained,
        workspace_root=workspace,
        expected_retained_tree_sha256=retained_manifest.tree_sha256,
    )
    return report, retained, workspace, retained_manifest, opened


def test_exact_text_recovery() -> None:
    entry = _entry(0)
    observation = hm23._observation_for_entry(entry, (_row(entry),))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
    assert observation.observed_text_sha256 == entry.historical_current_chroma_text_sha256
    assert observation.blockers == ()


def test_text_hash_mismatch() -> None:
    entry = _entry(1)
    row = _row(entry, document="different historical text")
    observation = hm23._observation_for_entry(entry, (row,))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.TEXT_HASH_MISMATCH
    assert observation.observed_text_sha256 != observation.expected_text_sha256


def test_missing_historical_row() -> None:
    entry = _entry(2)
    observation = hm23._observation_for_entry(entry, ())
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.ROW_MISSING
    assert observation.observed_row_count == 0


def test_ambiguous_historical_row() -> None:
    entry = _entry(3)
    rows = (_row(entry), _row(entry))
    observation = hm23._observation_for_entry(entry, rows)
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.ROW_AMBIGUOUS
    assert observation.observed_row_count == 2


def test_metadata_fingerprint_mismatch() -> None:
    entry = _entry(4)
    row = _row(
        entry,
        metadata={
            "case_id": CASE_ID,
            "document_name": "wrong.pdf",
            "page": entry.page,
        },
    )
    observation = hm23._observation_for_entry(entry, (row,))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.METADATA_MISMATCH
    assert observation.blockers == ("metadata_fingerprint_mismatch",)


def test_non_string_document_is_unreadable() -> None:
    entry = _entry(5)
    row = _row(entry, document=b"not a Python string")
    observation = hm23._observation_for_entry(entry, (row,))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.UNREADABLE


def test_same_key_different_text_uses_historical_hash() -> None:
    historical = "historical version"
    current = "different current version"
    entry = _entry(
        6,
        relationship=HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT,
        historical_text=historical,
        successor_text=current,
    )
    row = _row(entry, document=historical)
    observation = hm23._observation_for_entry(entry, (row,))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
    assert observation.observed_text_sha256 == sha256_bytes(historical.encode("utf-8"))
    assert observation.observed_text_sha256 != entry.current_successor_chunk_text_sha256


def test_changed_key_same_text_preserves_both_keys() -> None:
    text = "shared text content"
    entry = _entry(
        7,
        relationship=HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT,
        historical_key="historical-key-changed",
        historical_text=text,
        successor_key="current-key-different",
        successor_text=text,
        collision_risk=False,
    )
    observation = hm23._observation_for_entry(
        entry,
        (_row(entry, document=text),),
    )
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
    assert observation.historical_evidence_key == "historical-key-changed"
    assert observation.current_successor_evidence_key == "current-key-different"
    assert observation.historical_evidence_key != observation.current_successor_evidence_key


def test_no_direct_correspondence_can_verify_without_successor() -> None:
    entry = _entry(
        8,
        relationship=HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE,
        successor_key=None,
    )
    observation = hm23._observation_for_entry(entry, (_row(entry),))
    assert observation.status is hm23.HistoricalSnapshotCaptureStatus.EXACT_TEXT_VERIFIED
    assert observation.current_successor_evidence_key is None


def test_same_key_same_text_does_not_promote_binding_class() -> None:
    entry = _entry(
        9,
        relationship=HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT,
    )
    observation = hm23._observation_for_entry(entry, (_row(entry),))
    assert observation.historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT


def test_report_rejects_unexpected_historical_row_identity() -> None:
    entry = _entry(10)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    unexpected = hm23._ObservedChromaRow(
        row_id="not-present-in-hm2",
        document="text",
        metadata={},
    )
    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="unexpected historical row identities",
    ):
        hm23._build_report(
            case_id=CASE_ID,
            hm2_manifest=hm2,
            hm1_report=hm1,
            pfcr1_report=pfcr1,
            retained_source_tree_sha256=derive_sha256_id({"tree": "synthetic"}),
            rows=(unexpected,),
        )


def test_report_order_and_identity_are_input_order_independent() -> None:
    first = _entry(11)
    second = _entry(12)
    hm2_a, hm1, pfcr1 = _dummy_authorities((first, second))
    hm2_b, _, _ = _dummy_authorities((second, first))
    rows_a = (_row(first), _row(second))
    rows_b = tuple(reversed(rows_a))
    tree_id = derive_sha256_id({"tree": "same"})

    report_a = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2_a,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=tree_id,
        rows=rows_a,
    )
    report_b = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2_b,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=tree_id,
        rows=rows_b,
    )

    assert report_a == report_b
    assert tuple(item.historical_record_id for item in report_a.observations) == tuple(
        sorted(item.historical_record_id for item in report_a.observations)
    )


def test_report_serialization_contains_no_historical_plaintext() -> None:
    secret = "historical plaintext must not be persisted"
    entry = _entry(13, historical_text=secret)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    report = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=derive_sha256_id({"tree": "plaintext-test"}),
        rows=(_row(entry, document=secret),),
    )
    dumped = hm23.dumps_historical_snapshot_capture_rehearsal_report(report)
    assert secret not in dumped
    assert dumped.endswith("\n")
    assert not dumped.endswith("\n\n")
    assert json.loads(dumped)["exact_text_verified_count"] == 1


def test_report_validation_rejects_count_tamper() -> None:
    entry = _entry(14)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    report = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=derive_sha256_id({"tree": "count"}),
        rows=(),
    )
    with pytest.raises(ValueError, match="does not match"):
        hm23.validate_historical_snapshot_capture_rehearsal_report(
            replace(report, row_missing_count=0)
        )


def test_report_validation_rejects_identity_tamper() -> None:
    entry = _entry(15)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    report = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=derive_sha256_id({"tree": "identity"}),
        rows=(),
    )
    with pytest.raises(ValueError, match="identity is not canonical"):
        hm23.validate_historical_snapshot_capture_rehearsal_report(
            replace(
                report,
                historical_snapshot_capture_rehearsal_report_id=derive_sha256_id(
                    {"tampered": True}
                ),
            )
        )


def test_frozen_non_ascii_canonicalization_contract() -> None:
    payload = {"name": "café", "symbol": "£"}
    expected = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hm23._frozen_report_canonical_json_bytes(payload) == expected


def test_metadata_fingerprint_matches_frozen_contract() -> None:
    metadata = {"name": "café", "page": 2, "active": True}
    expected_payload = json.dumps(
        metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hm23._metadata_fingerprint(metadata) == (
        "sha256:" + sha256_bytes(expected_payload)
    )


def test_malformed_chroma_response_is_rejected() -> None:
    with pytest.raises(hm23.HistoricalSnapshotRehearsalError):
        hm23._parse_chroma_response(
            {
                "ids": ["one"],
                "documents": ["text", "extra"],
                "metadatas": [{}],
            }
        )


def test_tree_manifest_and_exact_copy_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "b.bin").write_bytes(b"B")
    nested = source / "nested"
    nested.mkdir()
    (nested / "a.bin").write_bytes(b"A")

    manifest = hm23._build_tree_manifest(source, require_exists=True)
    destination = tmp_path / "destination"
    hm23._copy_tree_exact(source, destination, manifest)

    assert hm23._build_tree_manifest(destination, require_exists=True) == manifest


def test_workspace_overlap_with_retained_parent_is_rejected(tmp_path: Path) -> None:
    retained_parent = tmp_path / "retained-parent"
    retained_parent.mkdir()
    retained = retained_parent / "retained"
    retained.mkdir()
    workspace = retained_parent / "workspace"

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="overlaps protected",
    ):
        hm23._resolve_workspace_root(workspace, retained.resolve())


def test_symlink_in_retained_tree_is_rejected_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "retained"
    root.mkdir()
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = root / "link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="link-like",
    ):
        hm23._build_tree_manifest(root, require_exists=True)


def test_wrong_retained_tree_hash_blocks_before_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(16)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    retained, workspace = _synthetic_roots(tmp_path)
    monkeypatch.setattr(hm23, "_validate_upstream_authorities", lambda **_: CASE_ID)

    called = False

    def observe(_: Path):
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr(hm23, "_observe_disposable_collection", observe)

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="approved SHA-256",
    ):
        hm23.rehearse_historical_snapshot_capture(
            hm2_manifest=hm2,
            hm1_report=hm1,
            pfcr1_report=pfcr1,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=derive_sha256_id({"wrong": "tree"}),
        )

    assert called is False
    assert workspace.exists() is False


def test_disposable_pre_open_tree_must_match_retained(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(17)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    retained, workspace = _synthetic_roots(tmp_path)
    retained_manifest = hm23._build_tree_manifest(retained, require_exists=True)
    monkeypatch.setattr(hm23, "_validate_upstream_authorities", lambda **_: CASE_ID)

    original_copy = hm23._copy_tree_exact

    def corrupting_copy(source: Path, destination: Path, manifest):
        original_copy(source, destination, manifest)
        (destination / "unexpected-runtime-file").write_bytes(b"corruption")

    monkeypatch.setattr(hm23, "_copy_tree_exact", corrupting_copy)

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="not exact before first Chroma open",
    ):
        hm23.rehearse_historical_snapshot_capture(
            hm2_manifest=hm2,
            hm1_report=hm1,
            pfcr1_report=pfcr1,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=retained_manifest.tree_sha256,
        )


def test_retained_mutation_during_copy_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(18)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    retained, workspace = _synthetic_roots(tmp_path)
    retained_manifest = hm23._build_tree_manifest(retained, require_exists=True)
    monkeypatch.setattr(hm23, "_validate_upstream_authorities", lambda **_: CASE_ID)

    original_copy = hm23._copy_tree_exact

    def mutating_copy(source: Path, destination: Path, manifest):
        original_copy(source, destination, manifest)
        (retained / "seed.bin").write_bytes(b"retained changed")

    monkeypatch.setattr(hm23, "_copy_tree_exact", mutating_copy)

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="changed during disposable-copy construction",
    ):
        hm23.rehearse_historical_snapshot_capture(
            hm2_manifest=hm2,
            hm1_report=hm1,
            pfcr1_report=pfcr1,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=retained_manifest.tree_sha256,
        )


def test_retained_mutation_during_observation_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(19)

    def mutate_retained(_: Path, retained: Path) -> None:
        (retained / "seed.bin").write_bytes(b"changed during observation")

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="changed during disposable observation",
    ):
        _run_public_with_rows(
            monkeypatch,
            tmp_path,
            entries=(entry,),
            rows=(_row(entry),),
            observer_hook=mutate_retained,
        )


def test_disposable_physical_mutation_is_permitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(20)

    def mutate_disposable(disposable: Path, _: Path) -> None:
        (disposable / "runtime-persistence-change.bin").write_bytes(
            b"legitimate disposable runtime mutation"
        )

    report, retained, workspace, retained_pre, opened = _run_public_with_rows(
        monkeypatch,
        tmp_path,
        entries=(entry,),
        rows=(_row(entry),),
        observer_hook=mutate_disposable,
    )

    assert report.exact_text_verified_count == 1
    assert opened == [workspace / "retained-db-copy"]
    assert hm23._build_tree_manifest(retained, require_exists=True) == retained_pre
    disposable_post = hm23._build_tree_manifest(
        workspace / "retained-db-copy",
        require_exists=True,
    )
    assert disposable_post != retained_pre


def test_observer_receives_disposable_path_not_retained(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(21)
    report, retained, workspace, _, opened = _run_public_with_rows(
        monkeypatch,
        tmp_path,
        entries=(entry,),
        rows=(_row(entry),),
    )
    assert report.exact_text_verified_count == 1
    assert opened == [workspace / "retained-db-copy"]
    assert opened[0] != retained


def test_observe_disposable_collection_closes_client_and_requests_exact_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, object] = {}

    class FakeCollection:
        def get(self, *, include):
            calls["include"] = include
            return {
                "ids": ["row"],
                "documents": ["text"],
                "metadatas": [{"case_id": CASE_ID}],
            }

    class FakeClient:
        def __init__(self, *, path: str):
            calls["path"] = path
            calls["closed"] = False

        def get_collection(self, *, name: str):
            calls["collection"] = name
            return FakeCollection()

        def close(self):
            calls["closed"] = True

    monkeypatch.setitem(
        sys.modules,
        "chromadb",
        types.SimpleNamespace(PersistentClient=FakeClient),
    )

    rows = hm23._observe_disposable_collection(tmp_path)

    assert len(rows) == 1
    assert calls["path"] == str(tmp_path)
    assert calls["collection"] == "legal_documents"
    assert calls["include"] == ["documents", "metadatas"]
    assert calls["closed"] is True


def test_source_contains_no_logical_chroma_mutation_calls() -> None:
    source = Path(hm23.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }

    assert attribute_calls.isdisjoint(
        {
            "add",
            "upsert",
            "update",
            "delete",
            "reset",
            "create_collection",
            "delete_collection",
            "get_or_create_collection",
        }
    )


def test_source_contains_no_publication_or_forbidden_dependencies() -> None:
    source = Path(hm23.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(
        name.startswith(
            (
                "openai",
                "retriever",
                "streamlit",
                "pypdf",
                "pdf2image",
                "pytesseract",
            )
        )
        for name in imports
    )

    for forbidden in (
        "publish_evidence_binding",
        "publish_analysis_receipt",
        "publish_projection_binding",
    ):
        assert forbidden not in source


def test_upstream_authority_failure_occurs_before_filesystem_or_chroma(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(22)
    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    retained, workspace = _synthetic_roots(tmp_path)

    monkeypatch.setattr(
        hm23,
        "_validate_upstream_authorities",
        lambda **_: (_ for _ in ()).throw(
            hm23.HistoricalSnapshotRehearsalError("upstream identity invalid")
        ),
    )

    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="upstream identity invalid",
    ):
        hm23.rehearse_historical_snapshot_capture(
            hm2_manifest=hm2,
            hm1_report=hm1,
            pfcr1_report=pfcr1,
            retained_db_root=retained,
            workspace_root=workspace,
            expected_retained_tree_sha256=derive_sha256_id({"tree": "unused"}),
        )

    assert workspace.exists() is False


def test_frozen_report_identity_rejects_tamper() -> None:
    payload = {
        "value": "authoritative",
        "historical_migration_report_id": derive_sha256_id({"value": "authoritative"}),
    }
    with pytest.raises(
        hm23.HistoricalSnapshotRehearsalError,
        match="canonical report identity is invalid",
    ):
        hm23._validate_frozen_report_identity(
            payload,
            id_field="historical_migration_report_id",
            stored_id=payload["historical_migration_report_id"],
            label="HM1",
        )


def test_745_records_are_accounted_without_requiring_745_recoveries() -> None:
    relationships = (
        [HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT] * 304
        + [HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT] * 59
        + [HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT] * 30
        + [HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE] * 352
    )
    entries = tuple(
        _entry(
            index,
            relationship=relationship,
            successor_key=(
                None
                if relationship
                is HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE
                else f"successor-{index}"
            ),
            collision_risk=(
                relationship is not HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT
            ),
        )
        for index, relationship in enumerate(relationships)
    )
    hm2, hm1, pfcr1 = _dummy_authorities(entries)
    report = hm23._build_report(
        case_id=CASE_ID,
        hm2_manifest=hm2,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_source_tree_sha256=derive_sha256_id({"tree": "745"}),
        rows=(),
    )

    assert report.historical_record_count == 745
    assert report.exact_text_verified_count == 0
    assert report.row_missing_count == 745
    assert len({item.historical_record_id for item in report.observations}) == 745
    assert Counter(item.relationship for item in report.observations) == {
        HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT: 304,
        HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT: 59,
        HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT: 30,
        HistoricalEvidenceRelationship.NO_DIRECT_CORRESPONDENCE: 352,
    }
    assert all(
        item.historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        for item in report.observations
    )


def test_report_identity_excludes_workspace_and_temporary_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = _entry(23)
    report, retained, workspace, _, _ = _run_public_with_rows(
        monkeypatch,
        tmp_path,
        entries=(entry,),
        rows=(_row(entry),),
    )

    dumped = hm23.dumps_historical_snapshot_capture_rehearsal_report(report)
    assert str(retained) not in dumped
    assert str(workspace) not in dumped
    assert "retained-db-copy" not in dumped


def test_public_rehearsal_does_not_require_all_rows_to_recover(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _entry(24)
    second = _entry(25)
    report, *_ = _run_public_with_rows(
        monkeypatch,
        tmp_path,
        entries=(first, second),
        rows=(_row(first),),
    )
    assert report.historical_record_count == 2
    assert report.exact_text_verified_count == 1
    assert report.row_missing_count == 1


def test_real_synthetic_chroma_disposable_rehearsal_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chromadb = pytest.importorskip("chromadb")

    entry = _entry(26)
    metadata = {
        "case_id": CASE_ID,
        "document_name": entry.document_name,
        "page": entry.page,
    }
    entry = replace(
        entry,
        historical_metadata_fingerprint=hm23._metadata_fingerprint(metadata),
    )

    retained_parent = tmp_path / "real-chroma-retained-parent"
    retained_parent.mkdir()
    retained = retained_parent / "retained-db"
    retained.mkdir()

    client = chromadb.PersistentClient(path=str(retained))
    collection = client.create_collection(name="legal_documents")
    collection.add(
        ids=[entry.historical_evidence_key],
        documents=["historical text 26"],
        metadatas=[metadata],
        embeddings=[[0.0, 0.0, 0.0]],
    )
    closer = getattr(client, "close", None)
    if callable(closer):
        closer()

    retained_pre = hm23._build_tree_manifest(retained, require_exists=True)

    workspace_parent = tmp_path / "real-chroma-workspace-parent"
    workspace_parent.mkdir()
    workspace = workspace_parent / "workspace"

    hm2, hm1, pfcr1 = _dummy_authorities((entry,))
    monkeypatch.setattr(hm23, "_validate_upstream_authorities", lambda **_: CASE_ID)

    report = hm23.rehearse_historical_snapshot_capture(
        hm2_manifest=hm2,
        hm1_report=hm1,
        pfcr1_report=pfcr1,
        retained_db_root=retained,
        workspace_root=workspace,
        expected_retained_tree_sha256=retained_pre.tree_sha256,
    )

    assert report.exact_text_verified_count == 1
    assert hm23._build_tree_manifest(retained, require_exists=True) == retained_pre
    assert (workspace / "retained-db-copy").is_dir()
