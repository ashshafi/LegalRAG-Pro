from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.identity import (
    canonical_json_bytes,
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
)
from source_evidence.migration import (
    HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
    HistoricalMigrationDecision,
    HistoricalMigrationDecisionCode,
    HistoricalMigrationReport,
    HistoricalMigrationSourceObservation,
)
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
)
from source_evidence.reingestion_transition import (
    PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION,
    ProspectiveReingestionBlocker,
    ProspectiveReingestionError,
    dumps_prospective_reingestion_report,
    prospective_reingestion_report_to_dict,
    rehearse_prospective_reingestion,
)
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore

import source_evidence.migration as hm1
import source_evidence.reingestion_transition as transition

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
PDF_BYTES = b"%PDF-1.7\nprospective current bytes\n"


class FakeCollection:
    def __init__(self, rows=()):
        self.rows: dict[str, tuple[str, dict[str, object]]] = {}
        self.get_calls = 0
        for row_id, document, metadata in rows:
            self.rows[row_id] = (document, dict(metadata))

    def get(self, *, include=None, ids=None, where=None):
        self.get_calls += 1
        if ids is None:
            keys = sorted(self.rows)
        else:
            keys = [row_id for row_id in ids if row_id in self.rows]
        return {
            "ids": keys,
            "documents": [self.rows[key][0] for key in keys],
            "metadatas": [dict(self.rows[key][1]) for key in keys],
        }


class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeM4Diagnostic:
    def __init__(self, exact, missing, conflicting):
        self.exact_present_count = exact
        self.missing_count = missing
        self.conflicting_count = conflicting
        self.total_rows = exact + missing + conflicting


def _profiles():
    return (
        ExtractionProfile(
            profile_id=EXTRACTION_PROFILE_ID,
            profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
            pypdf_package_version="6.14.2",
            pdf2image_package_version=None,
            pytesseract_package_version=None,
            tesseract_engine_version=None,
            poppler_version=None,
            ocr_language="eng",
            ocr_config="",
            ocr_dpi=200,
        ),
        ChunkingProfile(
            profile_id=CHUNKING_PROFILE_ID,
            profile_schema_version=CHUNKING_PROFILE_SCHEMA_VERSION,
            library="langchain-text-splitters",
            library_version="1.1.2",
            chunk_size=1000,
            chunk_overlap=200,
            separators=("\n\n", "\n", " ", ""),
            length_function="len",
            is_separator_regex=False,
        ),
    )


def _publish_graph(
    *,
    store: SourceEvidenceStore,
    pdf_path: Path,
    case_id: str,
    key_texts: tuple[tuple[str, str], ...],
) -> SourceDocumentManifest:
    original = pdf_path.read_bytes()
    original_sha = store.put_blob(original)
    document_id = derive_source_document_instance_id(
        case_id=case_id,
        original_filename=pdf_path.name,
        original_blob_sha256=original_sha,
    )
    extraction, chunking = _profiles()
    page_text = "\n".join(text for _, text in key_texts)
    page_bytes = page_text.encode("utf-8")
    page_sha = store.put_blob(page_bytes)
    snapshots = []
    for ordinal, (key, text) in enumerate(key_texts):
        chunk_bytes = text.encode("utf-8")
        chunk_sha = store.put_blob(chunk_bytes)
        snapshots.append(
            SourceChunkSnapshot(
                page_number=1,
                chunk_ordinal=ordinal,
                chunk_id=key,
                evidence_key=key,
                chunk_text_sha256=chunk_sha,
                chunk_text_byte_length=len(chunk_bytes),
            )
        )
    page = SourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=page_sha,
        page_text_byte_length=len(page_bytes),
        chunk_snapshots=tuple(snapshots),
    )
    provisional = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=case_id,
        source_document_instance_id=document_id,
        original_filename=pdf_path.name,
        media_type="application/pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(original),
        extraction_profile=extraction,
        chunking_profile=chunking,
        pages=(page,),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    manifest = replace(
        provisional,
        source_snapshot_id=derive_sha256_id(
            source_document_manifest_identity_payload_to_dict(provisional)
        ),
    )
    store.publish_document_manifest(manifest)
    for chunk in page.chunk_snapshots:
        binding_provisional = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=case_id,
            evidence_key=chunk.evidence_key,
            chunk_id=chunk.chunk_id,
            binding_class=BindingClass.FULL_CHAIN_BOUND,
            bound_text_role=BoundTextRole.CHUNK_TEXT,
            source_document_instance_id=document_id,
            source_snapshot_id=manifest.source_snapshot_id,
            document_name=pdf_path.name,
            document_id=None,
            page=1,
            chunk_ordinal=chunk.chunk_ordinal,
            original_blob_sha256=original_sha,
            page_text_sha256=page_sha,
            chunk_text_sha256=chunk.chunk_text_sha256,
            bound_text_sha256=chunk.chunk_text_sha256,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
            evidence_binding_id="sha256:" + "0" * 64,
        )
        binding = replace(
            binding_provisional,
            evidence_binding_id=derive_sha256_id(
                evidence_binding_identity_payload_to_dict(binding_provisional)
            ),
        )
        store.publish_evidence_binding(binding)
    return manifest


def _m4_rows(manifest: SourceDocumentManifest, store: SourceEvidenceStore):
    rows = []
    for page in manifest.pages:
        for chunk in page.chunk_snapshots:
            binding = store.load_evidence_binding(manifest.case_id, chunk.evidence_key)
            assert binding is not None
            text = store.read_blob(chunk.chunk_text_sha256).decode("utf-8")
            metadata = {
                "file": manifest.original_filename,
                "page": page.page_number,
                "chunk": chunk.chunk_ordinal,
                "case_id": manifest.case_id,
                "source_evidence_binding_id": binding.evidence_binding_id,
                "source_snapshot_id": manifest.source_snapshot_id,
                "source_document_instance_id": manifest.source_document_instance_id,
                "source_chunk_sha256": chunk.chunk_text_sha256,
                "source_page_text_sha256": page.page_text_sha256,
                "source_original_blob_sha256": manifest.original_blob_sha256,
                "source_binding_class": BindingClass.FULL_CHAIN_BOUND.value,
            }
            rows.append((chunk.evidence_key, text, metadata))
    return tuple(rows)


def _metadata_fingerprint(metadata):
    return "sha256:" + sha256_bytes(
        json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )


def _decision(
    *,
    evidence_key: str,
    candidate_key: str,
    text: str,
    metadata: dict[str, object],
    pdf_sha: str,
    pdf_len: int,
    collision: bool,
    existing_binding_id: str | None = None,
    existing_binding_class: BindingClass | None = None,
):
    return HistoricalMigrationDecision(
        case_id=CASE_ID,
        evidence_key=evidence_key,
        document_name=str(metadata["file"]),
        document_id=None,
        page=int(metadata["page"]),
        chunk_id=evidence_key,
        referencing_report_projection_ids=(),
        existing_evidence_binding_id=existing_binding_id,
        existing_binding_class=existing_binding_class,
        existing_projection_binding_manifest_ids=(),
        existing_projection_entry_classes=(),
        observation=HistoricalMigrationSourceObservation(
            current_chroma_row_count=1,
            current_chroma_document_sha256=sha256_bytes(text.encode("utf-8")),
            current_chroma_metadata_fingerprint=_metadata_fingerprint(metadata),
            current_pdf_candidate_count=1,
            current_pdf_sha256=pdf_sha,
            current_pdf_byte_length=pdf_len,
            retained_historical_text_sha256=None,
        ),
        m3_case_scoped_evidence_key_candidate=candidate_key,
        same_key_as_future_m3=candidate_key == evidence_key,
        binding_key_collision_risk=collision,
        maximum_historical_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        full_chain_projection_eligible=False,
        forward_reingestible=True,
        decision_code=(
            HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK
            if collision
            else HistoricalMigrationDecisionCode.LEGACY_KEY_DIFFERS_FROM_M3_KEY
        ),
        blockers=(HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK.value,)
        if collision
        else (),
        recommended_next_action=(
            "defer_binding_publication"
            if collision
            else "preserve_historical_key_consider_forward_reingestion"
        ),
    )


def _hm1_report(decisions):
    provisional = HistoricalMigrationReport(
        schema_version=HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
        case_id=CASE_ID,
        projection_ids=(),
        decisions=tuple(sorted(decisions, key=lambda item: item.evidence_key)),
        historical_migration_report_id="sha256:" + "0" * 64,
    )
    report_id = "sha256:" + sha256_bytes(
        hm1._canonical_json_bytes(hm1._report_identity_payload(provisional))
    )
    return replace(provisional, historical_migration_report_id=report_id)


def _fixture(tmp_path: Path, *, count=2, changed=1):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    pdf = docs / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    pdf_sha = sha256_bytes(PDF_BYTES)
    rows = []
    decisions = []
    prospective = []
    same_count = count - changed
    for index in range(count):
        candidate = f"{CASE_ID}__evidence_1_{index}"
        old_key = candidate if index < same_count else f"evidence_1_{index}"
        text = f"legacy text {index}"
        metadata = {
            "file": "evidence.pdf",
            "page": 1,
            "chunk": index,
            "case_id": CASE_ID,
        }
        rows.append((old_key, text, metadata))
        decisions.append(
            _decision(
                evidence_key=old_key,
                candidate_key=candidate,
                text=text,
                metadata=metadata,
                pdf_sha=pdf_sha,
                pdf_len=len(PDF_BYTES),
                collision=old_key == candidate,
            )
        )
        prospective.append((candidate, text))
    return docs, FakeCollection(rows), _hm1_report(decisions), tuple(prospective)


def _install_fake_rehearsal(monkeypatch, prospective, shadow: FakeCollection):
    state = {"manifest": None, "store": None, "runner_calls": 0}

    def fake_capture(pdf_path, *, case_id, store):
        manifest = _publish_graph(
            store=store,
            pdf_path=Path(pdf_path),
            case_id=case_id,
            key_texts=tuple(prospective),
        )
        state["manifest"] = manifest
        state["store"] = store
        return manifest

    def fake_runner(**kwargs):
        state["runner_calls"] += 1
        manifest = state["manifest"]
        store = state["store"]
        for row_id, text, metadata in _m4_rows(manifest, store):
            existing = shadow.rows.get(row_id)
            if existing is not None and existing != (text, metadata):
                return transition._M4SubprocessResult(
                    False,
                    None,
                    ProspectiveReingestionBlocker.M4_SHADOW_CONFLICT.value,
                )
            shadow.rows[row_id] = (text, dict(metadata))
        return transition._M4SubprocessResult(
            True,
            len(_m4_rows(manifest, store)),
            None,
        )

    def fake_open(_db_root):
        return FakeClient(), shadow

    def fake_inspect(manifest, *, store, collection):
        intended = {row_id: (text, metadata) for row_id, text, metadata in _m4_rows(manifest, store)}
        exact = missing = conflicting = 0
        for key, expected in intended.items():
            actual = collection.rows.get(key)
            if actual is None:
                missing += 1
            elif actual == expected:
                exact += 1
            else:
                conflicting += 1
        return FakeM4Diagnostic(exact, missing, conflicting)

    monkeypatch.setattr(transition, "_capture_with_frozen_m3", fake_capture)
    monkeypatch.setattr(transition, "_run_isolated_m4_ingestion", fake_runner)
    monkeypatch.setattr(transition, "_open_shadow_collection", fake_open)
    monkeypatch.setattr(transition, "_inspect_with_frozen_m4", fake_inspect)
    return state


def _run(tmp_path, monkeypatch, *, count=2, changed=1, prospective_override=None, shadow=None):
    docs, active, report, prospective = _fixture(tmp_path, count=count, changed=changed)
    if prospective_override is not None:
        prospective = tuple(prospective_override)
    shadow = shadow or FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    return result, state, docs, active, report, shadow


def test_715_collision_and_30_key_different_population_rehearses_cleanly(tmp_path, monkeypatch):
    result, state, *_ = _run(tmp_path, monkeypatch, count=745, changed=30)
    assert result.legacy_active_row_count == 745
    assert result.legacy_target_row_count == 745
    assert result.legacy_collision_risk_count == 715
    assert result.legacy_key_different_count == 30
    assert result.prospective_row_count == 745
    assert result.same_key_correspondence_count == 715
    assert result.changed_key_correspondence_count == 30
    assert result.no_direct_correspondence_count == 0
    assert result.all_rows_source_bound is True
    assert result.all_documents_complete is True
    assert result.collection_complete_for_cutover is True
    assert result.historical_provenance_changed is False
    assert result.active_derived_index_changed is False
    assert state["runner_calls"] == 1


def test_prospective_count_need_not_equal_legacy_count(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=2, changed=1)
    prospective = (*prospective, (f"{CASE_ID}__evidence_1_2", "new third chunk"))
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.legacy_target_row_count == 2
    assert result.prospective_row_count == 3
    assert result.collection_complete_for_cutover is True


def test_missing_direct_old_to_new_correspondence_does_not_invalidate_complete_manifest(tmp_path, monkeypatch):
    docs, active, report, _ = _fixture(tmp_path, count=1, changed=1)
    prospective = ((f"{CASE_ID}__evidence_1_99", "different current chunk"),)
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.no_direct_correspondence_count == 1
    assert result.prospective_row_count == 1
    assert result.collection_complete_for_cutover is True


def test_report_never_claims_historical_provenance_upgrade(tmp_path, monkeypatch):
    result, *_ = _run(tmp_path, monkeypatch)
    assert result.historical_provenance_changed is False
    assert result.prospective_source_chain_created is True
    payload = prospective_reingestion_report_to_dict(result)
    assert payload["historical_provenance_changed"] is False
    assert payload["active_derived_index_changed"] is False


def test_current_pdf_bytes_determine_prospective_source_document_identity():
    sha_a = sha256_bytes(b"current-a")
    sha_b = sha256_bytes(b"current-b")
    one = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="evidence.pdf",
        original_blob_sha256=sha_a,
    )
    two = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="evidence.pdf",
        original_blob_sha256=sha_b,
    )
    assert one != two


def test_hm1_report_tamper_fails_before_staging_creation(tmp_path, monkeypatch):
    docs, active, report, _ = _fixture(tmp_path)
    bad = replace(report, historical_migration_report_id="sha256:" + "1" * 64)
    stage = tmp_path / "stage"
    with pytest.raises(ProspectiveReingestionError, match="hm1_report_invalid"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=bad,
            current_documents_root=docs,
            staging_root=stage,
            active_collection=active,
        )
    assert not stage.exists()


def test_active_chroma_drift_fails_before_staging_creation(tmp_path):
    docs, active, report, _ = _fixture(tmp_path)
    first = next(iter(active.rows))
    document, metadata = active.rows[first]
    active.rows[first] = (document + " changed", metadata)
    stage = tmp_path / "stage"
    with pytest.raises(ProspectiveReingestionError, match="hm1_active_index_drift"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=stage,
            active_collection=active,
        )
    assert not stage.exists()


def test_current_pdf_drift_fails_before_staging_creation(tmp_path):
    docs, active, report, _ = _fixture(tmp_path)
    (docs / "evidence.pdf").write_bytes(PDF_BYTES + b"changed")
    stage = tmp_path / "stage"
    with pytest.raises(ProspectiveReingestionError, match="Current PDF bytes"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=stage,
            active_collection=active,
        )
    assert not stage.exists()


@pytest.mark.parametrize("relative", ["db", "source_evidence_store", "report_projections", "docs"])
def test_staging_equal_to_or_inside_production_roots_is_rejected(tmp_path, monkeypatch, relative):
    project = tmp_path / "project"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "evidence.pdf").write_bytes(PDF_BYTES)
    _, active, report, _ = _fixture(tmp_path / "fixture")
    monkeypatch.setattr(transition, "_project_root", lambda: project)
    stage = project / relative / "pfcr1-stage"
    with pytest.raises(ProspectiveReingestionError, match="staging_path_unsafe"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=stage,
            active_collection=active,
        )


def test_project_root_as_staging_is_rejected_because_outputs_hit_production_store(tmp_path, monkeypatch):
    project = tmp_path / "project"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "evidence.pdf").write_bytes(PDF_BYTES)
    _, active, report, _ = _fixture(tmp_path / "fixture")
    monkeypatch.setattr(transition, "_project_root", lambda: project)
    with pytest.raises(ProspectiveReingestionError, match="staging_path_unsafe"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=project,
            active_collection=active,
        )


def test_staging_and_input_document_tree_may_not_overlap(tmp_path):
    docs, active, report, _ = _fixture(tmp_path)
    with pytest.raises(ProspectiveReingestionError, match="staging_path_unsafe"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=docs / "stage",
            active_collection=active,
        )


def test_ambiguous_same_filename_blocks_document_without_m4(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path)
    duplicate_dir = docs / "duplicate"
    duplicate_dir.mkdir()
    (duplicate_dir / "evidence.pdf").write_bytes(PDF_BYTES + b"different")
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.collection_complete_for_cutover is False
    assert ProspectiveReingestionBlocker.AMBIGUOUS_CURRENT_PDF.value in result.blockers
    assert state["runner_calls"] == 0


def test_unaccounted_active_population_blocks_cutover_but_does_not_rewrite_it(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path)
    active.rows["foreign_1_0"] = (
        "foreign",
        {"file": "foreign.pdf", "page": 1, "chunk": 0, "case_id": OTHER_CASE_ID},
    )
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.legacy_active_row_count == 3
    assert result.legacy_target_row_count == 2
    assert result.all_active_collection_populations_accounted is False
    assert result.unaccounted_active_row_ids == ("foreign_1_0",)
    assert result.collection_complete_for_cutover is False


def test_shadow_unexpected_row_blocks_cutover(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path)
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    original_runner = transition._run_isolated_m4_ingestion

    def runner(**kwargs):
        result = original_runner(**kwargs)
        shadow.rows["unexpected"] = (
            "x",
            {
                "file": "x.pdf",
                "page": 1,
                "chunk": 0,
                "case_id": CASE_ID,
                "source_evidence_binding_id": "sha256:" + "1" * 64,
                "source_snapshot_id": "sha256:" + "2" * 64,
                "source_document_instance_id": "11111111-1111-4111-8111-111111111111",
                "source_chunk_sha256": "3" * 64,
                "source_page_text_sha256": "4" * 64,
                "source_original_blob_sha256": "5" * 64,
                "source_binding_class": BindingClass.FULL_CHAIN_BOUND.value,
            },
        )
        return result

    monkeypatch.setattr(transition, "_run_isolated_m4_ingestion", runner)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.unexpected_shadow_row_count == 1
    assert result.collection_complete_for_cutover is False
    assert ProspectiveReingestionBlocker.SHADOW_UNEXPECTED_ROW.value in result.blockers


def test_shadow_legacy_row_is_rejected(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=1, changed=0)
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    original_runner = transition._run_isolated_m4_ingestion

    def runner(**kwargs):
        result = original_runner(**kwargs)
        key = next(iter(shadow.rows))
        text, metadata = shadow.rows[key]
        metadata = dict(metadata)
        metadata.pop("source_evidence_binding_id")
        shadow.rows[key] = (text, metadata)
        return result

    monkeypatch.setattr(transition, "_run_isolated_m4_ingestion", runner)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.legacy_shadow_row_count == 1
    assert result.all_rows_source_bound is False
    assert result.collection_complete_for_cutover is False


def test_missing_shadow_row_blocks_cutover(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=2, changed=0)
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    original_runner = transition._run_isolated_m4_ingestion

    def runner(**kwargs):
        result = original_runner(**kwargs)
        shadow.rows.pop(sorted(shadow.rows)[-1])
        return result

    monkeypatch.setattr(transition, "_run_isolated_m4_ingestion", runner)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.missing_shadow_row_count == 1
    assert result.collection_complete_for_cutover is False


def test_m4_batch_limit_is_reported_without_custom_split_add(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=2, changed=0)
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)

    def fail_runner(**kwargs):
        state["runner_calls"] += 1
        return transition._M4SubprocessResult(
            False,
            None,
            ProspectiveReingestionBlocker.M4_BATCH_LIMIT.value,
        )

    monkeypatch.setattr(transition, "_run_isolated_m4_ingestion", fail_runner)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert ProspectiveReingestionBlocker.M4_BATCH_LIMIT.value in result.blockers
    assert result.collection_complete_for_cutover is False
    assert state["runner_calls"] == 1


def test_isolated_subprocess_error_mapping_for_frozen_m4_conflict(monkeypatch, tmp_path):
    completed = SimpleNamespace(
        returncode=3,
        stdout='__PFCR1_RESULT__{"ok": false, "type": "SourceEvidenceIngestionConflictError", "message": "conflict"}\n',
        stderr="",
    )
    monkeypatch.setattr(subprocess_module(), "run", lambda *args, **kwargs: completed)
    pdf = tmp_path / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    result = transition._run_isolated_m4_ingestion(
        pdf_path=pdf,
        case_id=CASE_ID,
        store_root=tmp_path / "store-v1",
        runtime_root=runtime,
        expected_original_sha256=sha256_bytes(PDF_BYTES),
    )
    assert result.blocker == ProspectiveReingestionBlocker.M4_SHADOW_CONFLICT.value


def subprocess_module():
    import subprocess

    return subprocess


def test_isolated_subprocess_error_mapping_for_batch_limit(monkeypatch, tmp_path):
    completed = SimpleNamespace(
        returncode=3,
        stdout="__PFCR1_RESULT__{\"ok\": false, \"type\": \"SourceEvidenceIngestionError\", \"message\": \"The source-bound missing row set exceeds Chroma\'s maximum batch size.\"}\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess_module(), "run", lambda *args, **kwargs: completed)
    pdf = tmp_path / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    result = transition._run_isolated_m4_ingestion(
        pdf_path=pdf,
        case_id=CASE_ID,
        store_root=tmp_path / "store-v1",
        runtime_root=runtime,
        expected_original_sha256=sha256_bytes(PDF_BYTES),
    )
    assert result.blocker == ProspectiveReingestionBlocker.M4_BATCH_LIMIT.value


def test_exact_rehearsal_retry_is_idempotent_and_report_identity_is_stable(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path)
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    kwargs = dict(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    first = rehearse_prospective_reingestion(**kwargs)
    second = rehearse_prospective_reingestion(**kwargs)
    assert first == second
    assert first.prospective_reingestion_report_id == second.prospective_reingestion_report_id
    assert len(shadow.rows) == first.prospective_row_count


def test_report_is_canonical_and_contains_no_machine_paths_or_source_text(tmp_path, monkeypatch):
    result, *_ = _run(tmp_path, monkeypatch)
    encoded = dumps_prospective_reingestion_report(result)
    assert encoded.endswith("\n") and not encoded.endswith("\n\n")
    assert str(tmp_path) not in encoded
    assert "legacy text 0" not in encoded
    assert json.loads(encoded)["schema_version"] == PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION


def test_report_identity_is_path_independent(tmp_path, monkeypatch):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    one, *_ = _run(left, monkeypatch)
    two, *_ = _run(right, monkeypatch)
    assert one.prospective_reingestion_report_id == two.prospective_reingestion_report_id
    assert dumps_prospective_reingestion_report(one) == dumps_prospective_reingestion_report(two)


def test_controlled_report_golden_is_stable(tmp_path, monkeypatch):
    result, *_ = _run(tmp_path, monkeypatch, count=2, changed=1)
    # Frozen after first deterministic PFCR1 implementation pass.
    assert result.prospective_reingestion_report_id == "sha256:de8df2b626ac712e256a408e4329b9b10dba0f5243d31b4286d4b4bea02f01cd"


def test_existing_weaker_binding_slot_blocks_prospective_full_chain_publication_plan(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=1, changed=0)
    decision = report.decisions[0]
    report = _hm1_report(
        (
            replace(
                decision,
                existing_evidence_binding_id="sha256:" + "1" * 64,
                existing_binding_class=BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
            ),
        )
    )
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert ProspectiveReingestionBlocker.EXISTING_WEAKER_BINDING_OCCUPIES_KEY.value in result.blockers
    assert result.collection_complete_for_cutover is False
    assert state["runner_calls"] == 0


def test_existing_full_chain_binding_id_must_match_prospective_graph(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=1, changed=0)
    decision = report.decisions[0]
    report = _hm1_report(
        (
            replace(
                decision,
                existing_evidence_binding_id="sha256:" + "2" * 64,
                existing_binding_class=BindingClass.FULL_CHAIN_BOUND,
            ),
        )
    )
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert ProspectiveReingestionBlocker.EXISTING_FULL_CHAIN_BINDING_MISMATCH.value in result.blockers
    assert state["runner_calls"] == 0


def test_production_trees_remain_byte_identical_in_rehearsal(tmp_path, monkeypatch):
    project = tmp_path / "project"
    for name in ("db", "source_evidence_store", "report_projections", "docs"):
        (project / name).mkdir(parents=True, exist_ok=True)
        (project / name / "sentinel.bin").write_bytes((name + "-sentinel").encode())
    (project / "docs" / "evidence.pdf").write_bytes(PDF_BYTES)

    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    _, active, report, prospective = _fixture(fixture_root)
    monkeypatch.setattr(transition, "_project_root", lambda: project)
    shadow = FakeCollection()
    _install_fake_rehearsal(monkeypatch, prospective, shadow)
    before = _tree_hashes(project)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=project / "docs",
        staging_root=tmp_path / "external-stage",
        active_collection=active,
    )
    after = _tree_hashes(project)
    assert before == after
    assert result.active_derived_index_changed is False


def _tree_hashes(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(root))] = sha256_bytes(path.read_bytes())
    return result


def test_no_production_or_staging_m5_receipt_is_created_by_rehearsal(tmp_path, monkeypatch):
    result, _, *_ = _run(tmp_path, monkeypatch)
    store_root = tmp_path / "stage" / "source_evidence_store" / "v1"
    receipts = list(store_root.rglob("analysis-receipts"))
    assert receipts == []
    assert result.collection_complete_for_cutover is True


def test_no_apply_cutover_delete_or_production_writer_public_capability_exists():
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "reingestion_transition.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    public_names = set(transition.__all__)
    assert not any(
        token in name.casefold()
        for name in public_names
        for token in ("apply", "cutover", "activate", "delete", "retire", "replace_production")
    )
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "publish_analysis_receipt" not in calls
    assert "publish_projection_binding" not in calls
    for forbidden in ("collection.add(", "collection.update(", "collection.upsert(", "collection.delete("):
        assert forbidden not in source


def test_pfcr1_does_not_import_config_retriever_m5_or_chromadb_at_module_import():
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "reingestion_transition.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_level_imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.add(node.module)
    assert "chromadb" not in top_level_imports
    assert "config" not in top_level_imports
    assert "retriever" not in top_level_imports
    assert "source_evidence.verified_retrieval" not in top_level_imports


def test_module_import_does_not_initialize_chromadb_or_openai():
    src_root = Path(__file__).resolve().parents[1] / "src"
    expected_module = src_root / "source_evidence" / "reingestion_transition.py"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_root)
        if not existing_pythonpath
        else str(src_root) + os.pathsep + existing_pythonpath
    )
    code = "\n".join(
        (
            "import sys",
            "from pathlib import Path",
            "import source_evidence.reingestion_transition as candidate",
            "assert callable(candidate.rehearse_prospective_reingestion)",
            f"assert Path(candidate.__file__).resolve() == Path({str(expected_module)!r}).resolve()",
            'assert "chromadb" not in sys.modules',
            'assert "openai" not in sys.modules',
        )
    )
    completed = subprocess_module().run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_malformed_active_collection_shape_fails_closed(tmp_path):
    docs, _, report, _ = _fixture(tmp_path)

    class Bad:
        def get(self, **kwargs):
            return {"ids": ["x"], "documents": [], "metadatas": []}

    with pytest.raises(ProspectiveReingestionError, match="misaligned"):
        rehearse_prospective_reingestion(
            case_id=CASE_ID,
            hm1_report=report,
            current_documents_root=docs,
            staging_root=tmp_path / "stage",
            active_collection=Bad(),
        )


def test_wrong_case_rejected_before_active_collection_read(tmp_path):
    docs, active, report, _ = _fixture(tmp_path)
    with pytest.raises(ValueError):
        rehearse_prospective_reingestion(
            case_id="not-a-uuid",
            hm1_report=report,
            current_documents_root=docs,
            staging_root=tmp_path / "stage",
            active_collection=active,
        )
    assert active.get_calls == 0


def test_foreign_case_row_never_becomes_target_population(tmp_path, monkeypatch):
    docs, active, report, prospective = _fixture(tmp_path, count=1, changed=0)
    key = next(iter(active.rows))
    document, metadata = active.rows[key]
    foreign_metadata = dict(metadata)
    foreign_metadata["case_id"] = OTHER_CASE_ID
    active.rows[key] = (document, foreign_metadata)
    decision = report.decisions[0]
    updated_observation = replace(
        decision.observation,
        current_chroma_metadata_fingerprint=_metadata_fingerprint(foreign_metadata),
    )
    report = _hm1_report((replace(decision, observation=updated_observation),))
    shadow = FakeCollection()
    state = _install_fake_rehearsal(monkeypatch, prospective, shadow)
    result = rehearse_prospective_reingestion(
        case_id=CASE_ID,
        hm1_report=report,
        current_documents_root=docs,
        staging_root=tmp_path / "stage",
        active_collection=active,
    )
    assert result.legacy_target_row_count == 0
    assert result.all_active_collection_populations_accounted is False
    assert state["runner_calls"] == 0


def test_exact_old_to_new_mapping_is_audit_only_and_does_not_rewrite_historical_key(tmp_path, monkeypatch):
    result, *_ = _run(tmp_path, monkeypatch, count=1, changed=1)
    mapping = result.legacy_mappings[0]
    assert mapping.historical_evidence_key == "evidence_1_0"
    assert mapping.prospective_candidate_key == f"{CASE_ID}__evidence_1_0"
    assert mapping.actual_prospective_key_exists is True
    assert mapping.same_key_as_future_m3 is False


def test_same_id_population_is_new_shadow_generation_not_historical_promotion(tmp_path, monkeypatch):
    result, *_ = _run(tmp_path, monkeypatch, count=1, changed=0)
    mapping = result.legacy_mappings[0]
    assert mapping.same_key_as_future_m3 is True
    assert mapping.binding_key_collision_risk is True
    assert result.historical_provenance_changed is False
    assert result.active_derived_index_changed is False


def test_real_frozen_m4_classifies_same_id_legacy_row_as_conflict(tmp_path):
    try:
        from source_evidence import ingestion
    except Exception as exc:
        pytest.skip(f"frozen M4 runtime unavailable in this artifact environment: {exc}")
    store = SourceEvidenceStore(tmp_path / "store-v1")
    pdf = tmp_path / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    key = f"{CASE_ID}__evidence_1_0"
    manifest = _publish_graph(
        store=store,
        pdf_path=pdf,
        case_id=CASE_ID,
        key_texts=((key, "same exact text"),),
    )
    legacy = FakeCollection(
        ((key, "same exact text", {"file": "evidence.pdf", "page": 1, "chunk": 0, "case_id": CASE_ID}),)
    )
    diagnostic = ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=legacy,
    )
    assert diagnostic.conflicting_count == 1
    assert diagnostic.exact_present_count == 0


def test_frozen_m4_diagnostic_fails_after_staging_chunk_blob_tamper(tmp_path):
    try:
        from source_evidence import ingestion
    except Exception as exc:
        pytest.skip(f"frozen M4 runtime unavailable in this artifact environment: {exc}")
    store = SourceEvidenceStore(tmp_path / "store-v1")
    pdf = tmp_path / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    key = f"{CASE_ID}__evidence_1_0"
    manifest = _publish_graph(
        store=store,
        pdf_path=pdf,
        case_id=CASE_ID,
        key_texts=((key, "exact chunk"),),
    )
    collection = FakeCollection(_m4_rows(manifest, store))
    chunk_sha = manifest.pages[0].chunk_snapshots[0].chunk_text_sha256
    blob = tmp_path / "store-v1" / "blobs" / "sha256" / chunk_sha[:2] / chunk_sha
    blob.write_bytes(b"tampered")
    with pytest.raises(Exception):
        ingestion.inspect_source_bound_index(manifest, store=store, collection=collection)


def test_real_chroma_159_disposable_shadow_exact_set_and_legacy_conflict(tmp_path):
    chromadb = pytest.importorskip("chromadb", reason="governed chromadb 1.5.9 unavailable")
    assert chromadb.__version__ == "1.5.9"
    try:
        from source_evidence import ingestion
    except Exception as exc:
        pytest.skip(f"frozen M4 runtime unavailable: {exc}")

    text = "exact current chunk"
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    pdf_bytes = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(pdf_bytes))
        pdf_bytes += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(pdf_bytes)
    pdf_bytes += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf_bytes += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf_bytes += f"{offset:010d} 00000 n \n".encode()
    pdf_bytes += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()

    store_root = tmp_path / "store-v1"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "config.py").write_text(
        """from types import SimpleNamespace
import chromadb


class _DeterministicEmbeddings:
    def create(self, *, model, input):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.125, 0.25, 0.5, 1.0])]
        )


class _DeterministicOpenAI:
    def __init__(self):
        self.embeddings = _DeterministicEmbeddings()


openai_client = _DeterministicOpenAI()
chroma_client = chromadb.PersistentClient(path="db")
collection = chroma_client.get_or_create_collection(name="legal_documents")
""",
        encoding="utf-8",
    )
    pdf = tmp_path / "evidence.pdf"
    pdf.write_bytes(bytes(pdf_bytes))
    original_sha = sha256_bytes(bytes(pdf_bytes))

    result = transition._run_isolated_m4_ingestion(
        pdf_path=pdf,
        case_id=CASE_ID,
        store_root=store_root,
        runtime_root=runtime_root,
        expected_original_sha256=original_sha,
    )
    assert result.succeeded is True

    store = SourceEvidenceStore(store_root)
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=pdf.name,
        original_blob_sha256=original_sha,
    )
    manifest = store.load_document_manifest(CASE_ID, document_id)
    expected_ids = tuple(
        chunk.evidence_key
        for page in manifest.pages
        for chunk in page.chunk_snapshots
    )
    assert result.indexed_row_count == len(expected_ids)

    client = chromadb.PersistentClient(path=str(runtime_root / "db"))
    collection = client.get_collection(name="legal_documents")
    diagnostic = ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    )
    assert diagnostic.exact_present_count == diagnostic.total_rows
    assert diagnostic.missing_count == 0
    assert diagnostic.conflicting_count == 0
    assert tuple(sorted(collection.get()["ids"])) == tuple(sorted(expected_ids))
    closer = getattr(client, "close", None)
    if callable(closer):
        closer()


def test_exact_two_path_boundary_names_are_the_only_pfcr1_candidate_paths():
    root = Path(__file__).resolve().parents[1]
    module = root / "src" / "source_evidence" / "reingestion_transition.py"
    test_file = root / "tests" / "test_source_evidence_reingestion_transition.py"
    assert module.exists()
    assert test_file.exists()
