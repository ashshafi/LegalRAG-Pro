from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.identity import (
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
)
from source_evidence.migration import (
    HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
    HistoricalMigrationReport,
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
from source_evidence.production_shadow_build import (
    PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION,
    ProductionShadowBuildBlocker,
    ProductionShadowBuildError,
    dumps_production_shadow_build_report,
    production_shadow_build_report_to_dict,
    build_production_source_bound_shadow,
)
from source_evidence.reingestion_transition import (
    PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION,
    ProspectiveDocumentRehearsal,
    ProspectiveLegacyKeyMapping,
    ProspectiveReingestionReport,
)
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore

import source_evidence.production_shadow_build as pfcr2

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
APPROVED_ID = "sha256:" + "a" * 64
PDF_BYTES = b"%PDF-1.4\nPFCR2 current bytes\n"


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
    store: SourceEvidenceStore,
    pdf_path: Path,
    *,
    keys: tuple[str, ...] = ("key-1",),
    case_id: str = CASE_ID,
) -> tuple[SourceDocumentManifest, tuple[EvidenceBinding, ...]]:
    original = pdf_path.read_bytes()
    original_sha = store.put_blob(original)
    document_id = derive_source_document_instance_id(
        case_id=case_id,
        original_filename=pdf_path.name,
        original_blob_sha256=original_sha,
    )
    extraction, chunking = _profiles()
    texts = tuple(f"prospective text {index}" for index, _ in enumerate(keys))
    page_bytes = "\n".join(texts).encode("utf-8")
    page_sha = store.put_blob(page_bytes)
    chunks = []
    for ordinal, (key, text) in enumerate(zip(keys, texts, strict=True)):
        chunk_bytes = text.encode("utf-8")
        chunk_sha = store.put_blob(chunk_bytes)
        chunks.append(
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
        chunk_snapshots=tuple(chunks),
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
    bindings = []
    for chunk in chunks:
        provisional_binding = EvidenceBinding(
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
            provisional_binding,
            evidence_binding_id=derive_sha256_id(
                evidence_binding_identity_payload_to_dict(provisional_binding)
            ),
        )
        store.publish_evidence_binding(binding)
        bindings.append(binding)
    return manifest, tuple(bindings)


def _hm1_report() -> HistoricalMigrationReport:
    return HistoricalMigrationReport(
        schema_version=HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
        case_id=CASE_ID,
        projection_ids=(),
        decisions=(),
        historical_migration_report_id="sha256:" + "b" * 64,
    )


def _fresh_report(
    *,
    pdf_path: Path,
    keys: tuple[str, ...] = ("key-1",),
    report_id: str = APPROVED_ID,
    complete: bool = True,
    blockers: tuple[str, ...] = (),
    legacy_rows: int = 745,
    collisions: int = 715,
    different: int = 30,
) -> ProspectiveReingestionReport:
    pdf_sha = sha256_bytes(pdf_path.read_bytes())
    doc_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=pdf_path.name,
        original_blob_sha256=pdf_sha,
    )
    rehearsal = ProspectiveDocumentRehearsal(
        document_name=pdf_path.name,
        current_pdf_sha256=pdf_sha,
        current_pdf_byte_length=pdf_path.stat().st_size,
        source_document_instance_id=doc_id,
        source_snapshot_id="sha256:" + "c" * 64,
        prospective_evidence_keys=keys,
        prospective_row_count=len(keys),
        shadow_exact_row_count=len(keys),
        shadow_missing_row_count=0,
        shadow_conflicting_row_count=0,
        capture_succeeded=True,
        m4_ingestion_succeeded=True,
        shadow_verified=True,
        blockers=(),
    )
    return ProspectiveReingestionReport(
        schema_version=PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION,
        case_id=CASE_ID,
        hm1_report_id=_hm1_report().historical_migration_report_id,
        historical_provenance_changed=False,
        prospective_source_chain_created=True,
        active_derived_index_changed=False,
        legacy_active_row_count=legacy_rows,
        legacy_target_row_count=legacy_rows,
        legacy_collision_risk_count=collisions,
        legacy_key_different_count=different,
        current_document_count=1,
        documents_capture_ready=1,
        documents_blocked=0,
        prospective_manifest_count=1,
        prospective_row_count=len(keys),
        exact_shadow_row_count=len(keys),
        missing_shadow_row_count=0,
        conflicting_shadow_row_count=0,
        unexpected_shadow_row_count=0,
        legacy_shadow_row_count=0,
        same_key_correspondence_count=max(0, legacy_rows - different),
        changed_key_correspondence_count=different,
        no_direct_correspondence_count=0,
        all_rows_source_bound=True,
        all_documents_complete=True,
        all_active_collection_populations_accounted=True,
        collection_complete_for_cutover=complete,
        unaccounted_active_row_ids=(),
        documents=(rehearsal,),
        legacy_mappings=(),
        blockers=blockers,
        prospective_reingestion_report_id=report_id,
    )


def _tree(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "report_projections").mkdir()
    (project / "report_projections" / "active.json").write_text("frozen", encoding="utf-8")
    docs = tmp_path / "docs-current"
    docs.mkdir()
    pdf = docs / "evidence.pdf"
    pdf.write_bytes(PDF_BYTES)
    active = tmp_path / "active-db"
    active.mkdir()
    (active / "chroma.sqlite3").write_bytes(b"legacy-db")
    external = tmp_path / "external"
    external.mkdir()
    production_store_parent = tmp_path / "production-store"
    production_store_parent.mkdir()
    return SimpleNamespace(
        project=project,
        docs=docs,
        pdf=pdf,
        active=active,
        preflight=external / "preflight",
        shadow=external / "shadow",
        backup=external / "backup",
        store=SourceEvidenceStore(production_store_parent / "v1"),
    )


def _plan_from_report(
    report: ProspectiveReingestionReport,
    pdf_path: Path,
    store: SourceEvidenceStore,
):
    keys = report.documents[0].prospective_evidence_keys
    manifest, bindings = _publish_graph(store, pdf_path, keys=keys)
    rehearsal = replace(
        report.documents[0],
        source_document_instance_id=manifest.source_document_instance_id,
        source_snapshot_id=manifest.source_snapshot_id,
        current_pdf_sha256=manifest.original_blob_sha256,
        current_pdf_byte_length=manifest.original_byte_length,
        prospective_evidence_keys=keys,
        prospective_row_count=len(keys),
    )
    return (pfcr2._PlanDocument(rehearsal, pdf_path, manifest, bindings),)


def _exact_shadow(plan):
    ids = tuple(sorted(key for item in plan for key in pfcr2._manifest_evidence_keys(item.manifest)))
    return pfcr2._ShadowInspection(
        exact_row_count=len(ids),
        missing_row_count=0,
        conflicting_row_count=0,
        unexpected_row_ids=(),
        legacy_row_ids=(),
        foreign_case_row_ids=(),
        actual_row_ids=ids,
        per_document_verified={item.manifest.source_document_instance_id: True for item in plan},
    )


def _configure_success(monkeypatch, tree, *, keys=("key-1",), report_id=APPROVED_ID):
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    fresh = _fresh_report(pdf_path=tree.pdf, keys=keys, report_id=report_id)
    plan_holder = {}

    def rehearse(**kwargs):
        return fresh

    def build_plan(*, case_id, fresh_report, documents_root, store):
        plan = _plan_from_report(fresh_report, tree.pdf, store)
        plan_holder["plan"] = plan
        # The real fresh PFCR1 source-snapshot ID must equal frozen M3; normalize fixture now.
        normalized = replace(
            fresh,
            documents=tuple(item.rehearsal for item in plan),
        )
        plan_holder["fresh_normalized"] = normalized
        return plan

    # Because the public build validates fresh report before the disposable plan,
    # make the initially supplied report already carry the graph identity used by plan.
    fixture_parent = tree.preflight.parent / "fixture-store"
    fixture_parent.mkdir(parents=True, exist_ok=True)
    staging = SourceEvidenceStore(fixture_parent / "v1")
    fixture_plan = _plan_from_report(fresh, tree.pdf, staging)
    fresh = replace(fresh, documents=tuple(item.rehearsal for item in fixture_plan))

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", lambda **kwargs: fresh)
    monkeypatch.setattr(pfcr2, "_build_disposable_plan", build_plan)

    def run_m4(**kwargs):
        plan = plan_holder["plan"]
        item = plan[0]
        _publish_graph(SourceEvidenceStore(kwargs["store_root"]), tree.pdf, keys=keys)
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        return pfcr2._M4RunResult(True, len(keys), None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", run_m4)
    monkeypatch.setattr(
        pfcr2,
        "_inspect_inactive_shadow",
        lambda **kwargs: _exact_shadow(plan_holder["plan"]),
    )
    monkeypatch.setattr(
        pfcr2,
        "_safe_final_shadow_inspection",
        lambda **kwargs: _exact_shadow(plan_holder["plan"]),
    )
    return fresh, plan_holder


def _configure_multi_document_success(monkeypatch, tree, documents):
    """Configure a cumulative-shadow success path for two or more documents."""

    if len(documents) < 2:
        raise AssertionError("multi-document fixture requires at least two documents")

    rehearsals = []
    total_rows = 0
    for pdf_path, keys in documents:
        single = _fresh_report(pdf_path=pdf_path, keys=keys)
        rehearsals.append(single.documents[0])
        total_rows += len(keys)

    fresh = replace(
        _fresh_report(pdf_path=documents[0][0], keys=documents[0][1]),
        current_document_count=len(documents),
        documents_capture_ready=len(documents),
        prospective_manifest_count=len(documents),
        prospective_row_count=total_rows,
        exact_shadow_row_count=total_rows,
        documents=tuple(rehearsals),
    )
    plan_holder = {}
    shadow_ids: set[str] = set()

    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", lambda **kwargs: fresh)

    def build_plan(*, case_id, fresh_report, documents_root, store):
        plan = []
        for rehearsal, (pdf_path, keys) in zip(
            fresh_report.documents,
            documents,
            strict=True,
        ):
            manifest, bindings = _publish_graph(store, pdf_path, keys=keys)
            normalized = replace(
                rehearsal,
                source_document_instance_id=manifest.source_document_instance_id,
                source_snapshot_id=manifest.source_snapshot_id,
                current_pdf_sha256=manifest.original_blob_sha256,
                current_pdf_byte_length=manifest.original_byte_length,
                prospective_evidence_keys=keys,
                prospective_row_count=len(keys),
            )
            plan.append(
                pfcr2._PlanDocument(
                    normalized,
                    pdf_path,
                    manifest,
                    bindings,
                )
            )
        plan_holder["plan"] = tuple(plan)
        return tuple(plan)

    monkeypatch.setattr(pfcr2, "_build_disposable_plan", build_plan)

    def run_m4(**kwargs):
        pdf_path = Path(kwargs["pdf_path"]).resolve(strict=True)
        item = next(
            candidate
            for candidate in plan_holder["plan"]
            if candidate.pdf_path.resolve(strict=True) == pdf_path
        )
        keys = pfcr2._manifest_evidence_keys(item.manifest)
        _publish_graph(
            SourceEvidenceStore(kwargs["store_root"]),
            item.pdf_path,
            keys=keys,
        )
        shadow_ids.update(keys)
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        return pfcr2._M4RunResult(True, len(keys), None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", run_m4)

    def inspect(**kwargs):
        manifests = tuple(kwargs["manifests"])
        expected = {
            key
            for manifest in manifests
            for key in pfcr2._manifest_evidence_keys(manifest)
        }
        missing = tuple(sorted(expected - shadow_ids))
        unexpected = tuple(sorted(shadow_ids - expected))
        actual = tuple(sorted(shadow_ids))
        per_document = {
            manifest.source_document_instance_id: set(
                pfcr2._manifest_evidence_keys(manifest)
            ).issubset(shadow_ids)
            for manifest in manifests
        }
        return pfcr2._ShadowInspection(
            exact_row_count=len(expected & shadow_ids),
            missing_row_count=len(missing),
            conflicting_row_count=0,
            unexpected_row_ids=unexpected,
            legacy_row_ids=(),
            foreign_case_row_ids=(),
            actual_row_ids=actual,
            per_document_verified=per_document,
        )

    monkeypatch.setattr(pfcr2, "_inspect_inactive_shadow", inspect)
    monkeypatch.setattr(pfcr2, "_safe_final_shadow_inspection", inspect)
    return fresh, plan_holder, shadow_ids


def _run(monkeypatch, tree, **kwargs):
    return build_production_source_bound_shadow(
        case_id=CASE_ID,
        hm1_report=_hm1_report(),
        approved_pfcr1_report_id=kwargs.pop("approved_id", APPROVED_ID),
        current_documents_root=tree.docs,
        preflight_staging_root=tree.preflight,
        shadow_generation_root=tree.shadow,
        active_db_root=tree.active,
        backup_root=tree.backup,
        production_store=tree.store,
        **kwargs,
    )


def test_successful_build_is_additive_and_carries_715_30_semantics(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree, keys=("key-1", "key-2"))
    report = _run(monkeypatch, tree)
    assert report.schema_version == PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION
    assert report.legacy_active_row_count == 745
    assert report.legacy_collision_risk_count == 715
    assert report.legacy_key_different_count == 30
    assert report.production_prospective_row_count == 2  # deliberately N != 745
    assert report.shadow_exact_row_count == 2
    assert report.shadow_complete_for_pfcr3 is True
    assert report.active_derived_index_changed is False
    assert report.historical_provenance_changed is False
    assert report.new_analysis_receipt_count == 0
    assert report.new_projection_binding_count == 0
    assert (tree.active / "chroma.sqlite3").read_bytes() == b"legacy-db"
    assert tree.pdf.read_bytes() == PDF_BYTES
    assert (tree.backup / "active_db" / "chroma.sqlite3").read_bytes() == b"legacy-db"


def test_multi_document_shadow_verification_uses_cumulative_manifests(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    second_pdf = tree.docs / "evidence-b.pdf"
    second_pdf.write_bytes(PDF_BYTES + b"second\n")
    documents = (
        (tree.pdf, ("a-1", "a-2", "a-3")),
        (second_pdf, ("b-1", "b-2")),
    )
    _, holder, shadow_ids = _configure_multi_document_success(
        monkeypatch,
        tree,
        documents,
    )

    report = _run(monkeypatch, tree)

    assert len(holder["plan"]) == 2
    assert shadow_ids == {"a-1", "a-2", "a-3", "b-1", "b-2"}
    assert len(report.documents) == 2
    assert [item.shadow_verified for item in report.documents] == [True, True]
    assert [item.blockers for item in report.documents] == [(), ()]
    assert report.production_manifest_count == 2
    assert report.production_prospective_row_count == 5
    assert report.shadow_exact_row_count == 5
    assert report.shadow_missing_row_count == 0
    assert report.shadow_unexpected_row_count == 0
    assert report.shadow_exact_set_verified is True
    assert report.all_documents_production_verified is True
    assert report.shadow_complete_for_pfcr3 is True
    assert report.blockers == ()


def test_fresh_pfcr1_uses_verified_observation_copy_not_active_db(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, _ = _configure_success(monkeypatch, tree)
    observed = {}

    def rehearse(**kwargs):
        adapter = kwargs["active_collection"]
        observed["root"] = adapter._db_root
        assert adapter._db_root != tree.active.resolve(strict=False)
        assert (adapter._db_root / "chroma.sqlite3").read_bytes() == b"legacy-db"
        (adapter._db_root / "chroma.sqlite3").write_bytes(b"normalized-by-chroma")
        return fresh

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    report = _run(monkeypatch, tree)

    expected_observation = tree.preflight.with_name(tree.preflight.name + ".active-db-observation") / "active_db"
    assert observed["root"] == expected_observation.resolve(strict=False)
    assert (tree.active / "chroma.sqlite3").read_bytes() == b"legacy-db"
    assert report.active_db_unchanged is True
    assert report.shadow_complete_for_pfcr3 is True

    audit = tree.backup / "audit"
    observation_pre = json.loads((audit / "active_db_observation_pre.json").read_text(encoding="utf-8"))
    observation_post = json.loads((audit / "active_db_observation_post.json").read_text(encoding="utf-8"))
    assert observation_pre["tree_sha256"] != observation_post["tree_sha256"]


def test_subprocess_collection_uses_ascii_safe_unicode_transport(tmp_path, monkeypatch):
    captured = {}

    def run(command, **kwargs):
        captured["script"] = command[2]
        captured["env"] = kwargs["env"]
        payload = {
            "ids": ["row-1"],
            "documents": ["two thirds \u2154"],
            "metadatas": [{"file": "evidence.pdf"}],
        }
        stdout = "__PFCR2_GET__" + json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        assert stdout.isascii()
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(pfcr2.subprocess, "run", run)
    result = pfcr2._SubprocessCollection(tmp_path / "db").get(
        include=["documents", "metadatas"]
    )

    assert "ensure_ascii=True" in captured["script"]
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert result["documents"] == ["two thirds \u2154"]


def test_fresh_pfcr1_id_mismatch_fails_before_production_store_creation(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    monkeypatch.setattr(
        pfcr2,
        "rehearse_prospective_reingestion",
        lambda **kwargs: _fresh_report(pdf_path=tree.pdf, report_id="sha256:" + "d" * 64),
    )
    with pytest.raises(ProductionShadowBuildError, match="fresh_pfcr1_id_mismatch"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()
    assert not tree.backup.exists()


@pytest.mark.parametrize(
    ("complete", "blockers"),
    [(False, ()), (True, ("blocked",))],
)
def test_fresh_pfcr1_must_be_complete_before_production_write(
    tmp_path, monkeypatch, complete, blockers
):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    monkeypatch.setattr(
        pfcr2,
        "rehearse_prospective_reingestion",
        lambda **kwargs: _fresh_report(
            pdf_path=tree.pdf,
            complete=complete,
            blockers=blockers,
        ),
    )
    with pytest.raises(ProductionShadowBuildError, match="fresh_pfcr1_incomplete"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()


def test_credential_or_pfcr1_runtime_failure_leaves_production_store_untouched(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)

    def fail(**kwargs):
        raise RuntimeError("credential preflight failed")

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", fail)
    with pytest.raises(RuntimeError, match="credential preflight"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()
    assert (tree.active / "chroma.sqlite3").read_bytes() == b"legacy-db"


def test_pfcr1_observation_mutating_active_db_fails_before_source_write(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)

    def rehearse(**kwargs):
        (tree.active / "chroma.sqlite3").write_bytes(b"changed-by-read")
        return _fresh_report(pdf_path=tree.pdf)

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ProductionShadowBuildError, match="preflight_changed_active_db"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()


def test_pfcr1_observation_mutating_docs_fails_before_source_write(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)

    def rehearse(**kwargs):
        tree.pdf.write_bytes(b"changed")
        return _fresh_report(pdf_path=tree.pdf)

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ProductionShadowBuildError, match="preflight_changed_docs"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()


def test_pfcr1_observation_mutating_report_projection_fails_before_source_write(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)

    def rehearse(**kwargs):
        (tree.project / "report_projections" / "active.json").write_text("changed", encoding="utf-8")
        return _fresh_report(pdf_path=tree.pdf)

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ProductionShadowBuildError, match="preflight_changed_report_projections"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()


def test_runtime_shadowing_config_is_rejected_before_pfcr1(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    runtime = tree.shadow / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "config.py").write_text("# forbidden", encoding="utf-8")
    called = False

    def rehearse(**kwargs):
        nonlocal called
        called = True
        return _fresh_report(pdf_path=tree.pdf)

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ProductionShadowBuildError, match="runtime_shadowing"):
        _run(monkeypatch, tree)
    assert called is False


@pytest.mark.parametrize("unsafe_name", ["extra.txt", "source_evidence"])
def test_runtime_rejects_any_non_db_child(tmp_path, unsafe_name):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    target = runtime / unsafe_name
    if "." in unsafe_name:
        target.write_text("x", encoding="utf-8")
    else:
        target.mkdir()
    with pytest.raises(ProductionShadowBuildError, match="runtime_shadowing"):
        pfcr2._reject_runtime_shadowing(runtime)


def test_backup_tamper_is_detected_before_production_write(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)

    def bad_copy(source, destination, manifest):
        destination.mkdir(parents=True)
        (destination / "chroma.sqlite3").write_bytes(b"wrong")

    monkeypatch.setattr(pfcr2, "_copy_tree_exact", bad_copy)
    with pytest.raises(ProductionShadowBuildError, match="backup_verification_failed"):
        _run(monkeypatch, tree)
    assert not tree.store.root.exists()


def test_weaker_binding_occupying_prospective_slot_blocks_before_backup_or_m4(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)
    (tmp_path / "weak-plan").mkdir()
    plan_store = SourceEvidenceStore(tmp_path / "weak-plan" / "v1")
    plan = _plan_from_report(fresh, tree.pdf, plan_store)
    intended = plan[0].bindings[0]
    weak = replace(
        intended,
        binding_class=BindingClass.ANALYTICAL_TEXT_BOUND,
        bound_text_role=BoundTextRole.ANALYTICAL_SUMMARY,
        source_document_instance_id=None,
        source_snapshot_id=None,
        chunk_id=None,
        page=None,
        chunk_ordinal=None,
        original_blob_sha256=None,
        page_text_sha256=None,
        chunk_text_sha256=None,
        extraction_profile_id=None,
        chunking_profile_id=None,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    weak = replace(
        weak,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(weak)),
    )
    tree.store.put_blob(b"prospective text 0")
    tree.store.publish_evidence_binding(weak)
    with pytest.raises(ProductionShadowBuildError, match="existing_weaker_binding_occupies_key"):
        _run(monkeypatch, tree)
    assert not tree.backup.exists()


def test_different_full_chain_binding_blocks_before_backup(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)
    (tmp_path / "other-plan").mkdir()
    plan_store = SourceEvidenceStore(tmp_path / "other-plan" / "v1")
    plan = _plan_from_report(fresh, tree.pdf, plan_store)
    intended = plan[0].bindings[0]
    different = replace(
        intended,
        evidence_binding_id="sha256:" + "1" * 64,
    )
    # Persist a canonical but different FULL_CHAIN graph by changing source snapshot too.
    different = replace(
        intended,
        source_snapshot_id="sha256:" + "2" * 64,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    different = replace(
        different,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(different)),
    )
    tree.store.publish_evidence_binding(different)
    with pytest.raises(ProductionShadowBuildError, match="existing_full_chain_binding_mismatch"):
        _run(monkeypatch, tree)
    assert not tree.backup.exists()


def test_partial_exact_source_store_retry_reuses_existing_graphs_and_continues(
    tmp_path,
    monkeypatch,
):
    tree = _tree(tmp_path)
    second_pdf = tree.docs / "evidence-b.pdf"
    third_pdf = tree.docs / "evidence-c.pdf"
    second_pdf.write_bytes(PDF_BYTES + b"second\n")
    third_pdf.write_bytes(PDF_BYTES + b"third\n")
    documents = (
        (tree.pdf, ("a-1", "a-2", "a-3")),
        (second_pdf, ("b-1", "b-2")),
        (third_pdf, ("c-1",)),
    )
    _configure_multi_document_success(monkeypatch, tree, documents)

    # Mirror the governed production state after a prior fail-closed attempt:
    # the first two source graphs already exist exactly; the third is absent.
    _publish_graph(tree.store, tree.pdf, keys=documents[0][1])
    _publish_graph(tree.store, second_pdf, keys=documents[1][1])
    pre = pfcr2._build_tree_manifest(tree.store.root, require_exists=True)

    report = _run(monkeypatch, tree)
    post = pfcr2._build_tree_manifest(tree.store.root, require_exists=True)

    pre_by_path = {entry.relative_path: entry for entry in pre.entries}
    post_by_path = {entry.relative_path: entry for entry in post.entries}
    assert pre_by_path
    assert all(post_by_path.get(path) == entry for path, entry in pre_by_path.items())
    assert report.preexisting_source_store_file_count == len(pre.entries)
    assert report.modified_preexisting_source_store_file_count == 0
    assert report.deleted_preexisting_source_store_file_count == 0
    assert report.new_source_store_file_count > 0
    assert len(report.documents) == 3
    assert all(item.production_manifest_verified for item in report.documents)
    assert all(item.production_bindings_verified for item in report.documents)
    assert all(item.shadow_verified for item in report.documents)
    assert report.production_manifest_count == 3
    assert report.production_prospective_row_count == 6
    assert report.shadow_exact_row_count == 6
    assert report.shadow_missing_row_count == 0
    assert report.shadow_unexpected_row_count == 0
    assert report.source_store_append_only_valid is True
    assert report.shadow_complete_for_pfcr3 is True
    assert report.blockers == ()


def test_exact_existing_full_chain_is_idempotently_allowed(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)
    (tmp_path / "fixture").mkdir()
    fixture_store = SourceEvidenceStore(tmp_path / "fixture" / "v1")
    plan = _plan_from_report(fresh, tree.pdf, fixture_store)
    # Copy the exact source graph into the intended production store before build.
    _publish_graph(tree.store, tree.pdf, keys=plan[0].rehearsal.prospective_evidence_keys)
    report = _run(monkeypatch, tree)
    assert report.shadow_complete_for_pfcr3 is True
    assert report.modified_preexisting_source_store_file_count == 0
    assert report.deleted_preexisting_source_store_file_count == 0


@pytest.mark.parametrize(
    ("m4_blocker", "expected"),
    [
        (ProductionShadowBuildBlocker.M4_INGESTION_FAILED.value, "m4_ingestion_failed"),
        (ProductionShadowBuildBlocker.M4_BATCH_LIMIT.value, "m4_batch_limit"),
        (ProductionShadowBuildBlocker.M4_SHADOW_CONFLICT.value, "m4_shadow_conflict"),
        (ProductionShadowBuildBlocker.M4_SHADOW_INCOMPLETE.value, "m4_shadow_incomplete"),
    ],
)
def test_m4_failure_modes_do_not_mutate_active_db_and_do_not_fallback(
    tmp_path, monkeypatch, m4_blocker, expected
):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)

    def fail_m4(**kwargs):
        # Frozen M4 may have already completed M3 publication before embedding/write failure.
        plan = holder["plan"]
        _publish_graph(SourceEvidenceStore(kwargs["store_root"]), tree.pdf, keys=plan[0].rehearsal.prospective_evidence_keys)
        return pfcr2._M4RunResult(False, None, m4_blocker)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", fail_m4)
    monkeypatch.setattr(
        pfcr2,
        "_safe_final_shadow_inspection",
        lambda **kwargs: pfcr2._ShadowInspection(0, 1, 0, (), (), (), (), {}),
    )
    report = _run(monkeypatch, tree)
    assert expected in report.blockers
    assert report.shadow_complete_for_pfcr3 is False
    assert report.source_store_append_only_valid is True
    assert report.active_db_unchanged is True
    assert (tree.active / "chroma.sqlite3").read_bytes() == b"legacy-db"


def test_source_store_preexisting_tamper_is_reported_and_blocks_pfcr3(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    preexisting_sha = tree.store.put_blob(b"preexisting")
    preexisting_path = tree.store.root / "blobs" / "sha256" / preexisting_sha[:2] / preexisting_sha
    _configure_success(monkeypatch, tree)
    original_run = pfcr2._run_production_m4_ingestion

    def tamper(**kwargs):
        plan_store = SourceEvidenceStore(kwargs["store_root"])
        # Success helper's production graph is created by replacing the configured runner logic.
        _publish_graph(plan_store, tree.pdf)
        preexisting_path.write_bytes(b"tampered")
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        return pfcr2._M4RunResult(True, 1, None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", tamper)
    report = _run(monkeypatch, tree)
    assert ProductionShadowBuildBlocker.SOURCE_STORE_PREEXISTING_CHANGED.value in report.blockers
    assert report.source_store_append_only_valid is False
    assert report.shadow_complete_for_pfcr3 is False


def test_new_analysis_receipt_and_projection_binding_paths_are_rejected(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)

    def bad_m4(**kwargs):
        plan = holder["plan"]
        store = SourceEvidenceStore(kwargs["store_root"])
        _publish_graph(store, tree.pdf, keys=plan[0].rehearsal.prospective_evidence_keys)
        case_dir = store.root / "cases" / CASE_ID
        receipt_dir = case_dir / "analysis-receipts"
        projection_dir = case_dir / "projection-bindings"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        projection_dir.mkdir(parents=True, exist_ok=True)
        (receipt_dir / "unexpected.json").write_text("{}", encoding="utf-8")
        (projection_dir / "unexpected.json").write_text("{}", encoding="utf-8")
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        return pfcr2._M4RunResult(True, 1, None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", bad_m4)
    report = _run(monkeypatch, tree)
    assert report.new_analysis_receipt_count == 1
    assert report.new_projection_binding_count == 1
    assert ProductionShadowBuildBlocker.ANALYSIS_RECEIPT_CREATED.value in report.blockers
    assert ProductionShadowBuildBlocker.PROJECTION_BINDING_CREATED.value in report.blockers
    assert report.shadow_complete_for_pfcr3 is False


@pytest.mark.parametrize("target", ["active", "docs", "reports"])
def test_post_write_mutation_of_protected_tree_blocks_pfcr3(tmp_path, monkeypatch, target):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)

    def mutate(**kwargs):
        plan = holder["plan"]
        _publish_graph(SourceEvidenceStore(kwargs["store_root"]), tree.pdf, keys=plan[0].rehearsal.prospective_evidence_keys)
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        if target == "active":
            (tree.active / "chroma.sqlite3").write_bytes(b"changed")
        elif target == "docs":
            tree.pdf.write_bytes(b"changed")
        else:
            (tree.project / "report_projections" / "active.json").write_text("changed", encoding="utf-8")
        return pfcr2._M4RunResult(True, 1, None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", mutate)
    report = _run(monkeypatch, tree)
    expected = {
        "active": ProductionShadowBuildBlocker.ACTIVE_DB_CHANGED.value,
        "docs": ProductionShadowBuildBlocker.DOCS_CHANGED.value,
        "reports": ProductionShadowBuildBlocker.REPORT_PROJECTIONS_CHANGED.value,
    }[target]
    assert expected in report.blockers
    assert report.shadow_complete_for_pfcr3 is False


def test_shadow_unexpected_legacy_foreign_and_missing_rows_block_completion(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)
    bad = pfcr2._ShadowInspection(
        exact_row_count=0,
        missing_row_count=1,
        conflicting_row_count=1,
        unexpected_row_ids=("unexpected",),
        legacy_row_ids=("legacy",),
        foreign_case_row_ids=("foreign",),
        actual_row_ids=("unexpected",),
        per_document_verified={},
    )
    monkeypatch.setattr(pfcr2, "_inspect_inactive_shadow", lambda **kwargs: bad)
    monkeypatch.setattr(pfcr2, "_safe_final_shadow_inspection", lambda **kwargs: bad)
    report = _run(monkeypatch, tree)
    for blocker in (
        ProductionShadowBuildBlocker.SHADOW_MISSING_ROW.value,
        ProductionShadowBuildBlocker.SHADOW_CONFLICTING_ROW.value,
        ProductionShadowBuildBlocker.SHADOW_UNEXPECTED_ROW.value,
        ProductionShadowBuildBlocker.SHADOW_LEGACY_ROW.value,
        ProductionShadowBuildBlocker.SHADOW_CASE_MISMATCH.value,
    ):
        assert blocker in report.blockers
    assert report.shadow_complete_for_pfcr3 is False


def test_idempotent_retry_reuses_exact_production_graph_and_shadow(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree)
    first = _run(monkeypatch, tree)
    assert first.shadow_complete_for_pfcr3 is True

    # New fresh preflight/backup locations; same production source store + inactive shadow.
    tree.preflight = tree.preflight.parent / "preflight-retry"
    tree.backup = tree.backup.parent / "backup-retry"
    _configure_success(monkeypatch, tree)
    second = _run(monkeypatch, tree)
    assert second.shadow_complete_for_pfcr3 is True
    assert second.modified_preexisting_source_store_file_count == 0
    assert second.deleted_preexisting_source_store_file_count == 0
    assert second.new_source_store_file_count == 0


def test_backup_manifest_uses_paths_lengths_and_hashes_not_mtime(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    file = root / "a.bin"
    file.write_bytes(b"abc")
    first = pfcr2._build_tree_manifest(root, require_exists=True)
    os.utime(file, (1, 1))
    second = pfcr2._build_tree_manifest(root, require_exists=True)
    assert first == second
    assert first.entries[0].relative_path == "a.bin"
    assert first.entries[0].byte_length == 3
    assert first.entries[0].sha256_hex == sha256_bytes(b"abc")


def test_tree_manifest_rejects_symlink(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    target = tmp_path / "outside"
    target.write_text("x", encoding="utf-8")
    link = root / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ProductionShadowBuildError, match="Link-like"):
        pfcr2._build_tree_manifest(root, require_exists=True)


def test_shadow_generation_must_share_filesystem(monkeypatch, tmp_path):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    monkeypatch.setattr(pfcr2, "_same_filesystem", lambda left, right: False)
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        _run(monkeypatch, tree)


@pytest.mark.parametrize("kind", ["preflight", "shadow", "backup"])
def test_external_roots_must_not_be_inside_project(tmp_path, monkeypatch, kind):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    setattr(tree, kind, tree.project / kind)
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        _run(monkeypatch, tree)


def test_external_roots_must_not_overlap(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    tree.backup = tree.shadow / "backup"
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        _run(monkeypatch, tree)


def test_derived_observation_root_must_not_overlap_external_roots(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    tree.shadow = tree.preflight.with_name(tree.preflight.name + ".active-db-observation")
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        _run(monkeypatch, tree)


def test_nonempty_observation_root_fails_before_pfcr1(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    observation = tree.preflight.with_name(tree.preflight.name + ".active-db-observation")
    observation.mkdir()
    (observation / "sentinel.bin").write_bytes(b"occupied")
    called = False

    def rehearse(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ProductionShadowBuildError, match="active_db_observation_root must be absent or empty"):
        _run(monkeypatch, tree)
    assert called is False


def test_production_mode_requires_exact_project_docs_and_db(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        build_production_source_bound_shadow(
            case_id=CASE_ID,
            hm1_report=_hm1_report(),
            approved_pfcr1_report_id=APPROVED_ID,
            current_documents_root=tree.docs,
            preflight_staging_root=tree.preflight,
            shadow_generation_root=tree.shadow,
            active_db_root=tree.active,
            backup_root=tree.backup,
            production_store=None,
        )



def test_injected_store_cannot_target_production_source_store(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    monkeypatch.setattr(pfcr2, "_project_root", lambda: tree.project)
    production_parent = tree.project / "source_evidence_store"
    production_parent.mkdir()
    injected = SourceEvidenceStore(production_parent / "v1")
    with pytest.raises(ProductionShadowBuildError, match="path_unsafe"):
        build_production_source_bound_shadow(
            case_id=CASE_ID,
            hm1_report=_hm1_report(),
            approved_pfcr1_report_id=APPROVED_ID,
            current_documents_root=tree.docs,
            preflight_staging_root=tree.preflight,
            shadow_generation_root=tree.shadow,
            active_db_root=tree.active,
            backup_root=tree.backup,
            production_store=injected,
        )

def test_production_store_source_graph_must_match_disposable_plan(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    fresh, holder = _configure_success(monkeypatch, tree)

    def wrong_graph(**kwargs):
        _publish_graph(SourceEvidenceStore(kwargs["store_root"]), tree.pdf, keys=("different-key",))
        db = Path(kwargs["runtime_root"]) / "db"
        db.mkdir(parents=True, exist_ok=True)
        (db / "chroma.sqlite3").write_bytes(b"inactive-shadow")
        return pfcr2._M4RunResult(True, 1, None)

    monkeypatch.setattr(pfcr2, "_run_production_m4_ingestion", wrong_graph)
    report = _run(monkeypatch, tree)
    assert ProductionShadowBuildBlocker.PRODUCTION_MANIFEST_MISMATCH.value in report.documents[0].blockers
    assert report.shadow_complete_for_pfcr3 is False


def test_report_json_contains_no_source_text_or_machine_paths(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree)
    report = _run(monkeypatch, tree)
    payload = dumps_production_shadow_build_report(report)
    assert "prospective text" not in payload
    assert str(tree.preflight) not in payload
    assert str(tree.shadow) not in payload
    assert str(tree.backup) not in payload
    assert str(tree.docs) not in payload
    parsed = json.loads(payload)
    assert parsed["production_shadow_build_report_id"] == report.production_shadow_build_report_id


def test_report_identity_excludes_operational_tree_hashes(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree)
    report = _run(monkeypatch, tree)
    changed = replace(
        report,
        active_db_pre_tree_sha256="sha256:" + "1" * 64,
        shadow_tree_sha256="sha256:" + "2" * 64,
    )
    assert pfcr2._report_identity_payload(changed) == pfcr2._report_identity_payload(report)
    assert production_shadow_build_report_to_dict(changed)["active_db_pre_tree_sha256"] != (
        production_shadow_build_report_to_dict(report)["active_db_pre_tree_sha256"]
    )


def test_controlled_report_identity_golden(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree, keys=("key-1", "key-2"))
    report = _run(monkeypatch, tree)
    assert report.production_shadow_build_report_id == "sha256:3bd6409eac4a4b1aa7a3a52e099ce75d31a898407e95950b3f0f4351f971c5bb"


def test_audit_sidecars_are_written_only_under_external_backup_root(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree)
    report = _run(monkeypatch, tree)
    audit = tree.backup / "audit"
    assert (audit / "production_shadow_build_report.json").exists()
    assert json.loads((audit / "production_shadow_build_report.json").read_text())["production_shadow_build_report_id"] == report.production_shadow_build_report_id
    assert not (tree.project / "pfcr2-audit").exists()


def test_sealed_shadow_tree_hash_changes_after_tamper(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    _configure_success(monkeypatch, tree)
    report = _run(monkeypatch, tree)
    before = pfcr2._build_tree_manifest(tree.shadow / "runtime" / "db", require_exists=True)
    assert before.tree_sha256 == report.shadow_tree_sha256
    (tree.shadow / "runtime" / "db" / "chroma.sqlite3").write_bytes(b"tampered")
    after = pfcr2._build_tree_manifest(tree.shadow / "runtime" / "db", require_exists=True)
    assert after.tree_sha256 != report.shadow_tree_sha256


def test_public_module_import_does_not_initialize_chromadb_or_openai():
    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys\n"
        "import source_evidence.production_shadow_build as module\n"
        "assert callable(module.build_production_source_bound_shadow)\n"
        "assert 'chromadb' not in sys.modules\n"
        "assert 'openai' not in sys.modules\n"
    )
    env = dict(os.environ)
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src) if not current else str(src) + os.pathsep + current
    completed = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_production_module_has_no_cutover_hm2_m5_m6_or_active_chroma_writer_calls():
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "production_shadow_build.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = set()
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden_calls = {"upsert", "delete", "publish_analysis_receipt", "publish_projection_binding", "rename"}
    assert not (forbidden_calls & calls)
    assert "collection.update(" not in source
    assert "collection.add(" not in source
    assert "collection.upsert(" not in source
    assert "collection.delete(" not in source
    assert "os.rename" not in source
    assert "os.replace" not in source
    assert "shutil.rmtree" not in source
    assert "legal_analysis" not in imports
    assert "case_analysis" not in imports
    assert "retriever" not in imports
    assert "source_evidence.projection_binding" not in imports
    assert "source_evidence.verified_retrieval" not in imports


def test_exact_public_api():
    assert pfcr2.__all__ == [
        "PRODUCTION_SHADOW_BUILD_REPORT_SCHEMA_VERSION",
        "ProductionShadowBuildBlocker",
        "ProductionShadowBuildError",
        "ProductionShadowBuildReport",
        "ProductionShadowDocumentResult",
        "build_production_source_bound_shadow",
        "dumps_production_shadow_build_report",
        "production_shadow_build_report_to_dict",
    ]


def test_invalid_case_rejected_before_pfcr1(tmp_path, monkeypatch):
    tree = _tree(tmp_path)
    called = False

    def rehearse(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(pfcr2, "rehearse_prospective_reingestion", rehearse)
    with pytest.raises(ValueError):
        build_production_source_bound_shadow(
            case_id="not-a-uuid",
            hm1_report=_hm1_report(),
            approved_pfcr1_report_id=APPROVED_ID,
            current_documents_root=tree.docs,
            preflight_staging_root=tree.preflight,
            shadow_generation_root=tree.shadow,
            active_db_root=tree.active,
            backup_root=tree.backup,
            production_store=tree.store,
        )
    assert called is False


def test_real_m4_credentialed_inactive_shadow_gate(tmp_path, monkeypatch):
    if os.getenv("LEGALRAG_PFCR2_REAL_EMBEDDING_TEST") != "1":
        pytest.skip("Set LEGALRAG_PFCR2_REAL_EMBEDDING_TEST=1 for governed real embedding gate")
    if importlib.util.find_spec("chromadb") is None:
        pytest.skip("chromadb unavailable")
    import chromadb

    assert chromadb.__version__ == "1.5.9"
    if not os.getenv("OPENAI_API_KEY"):
        pytest.fail("Governed PFCR2 real embedding gate requires OPENAI_API_KEY")
    try:
        from pypdf import PdfWriter
    except Exception as exc:  # pragma: no cover - governed environment gate
        pytest.skip(f"pypdf unavailable: {exc}")

    runtime = tmp_path / "shadow" / "runtime"
    runtime.mkdir(parents=True)
    store = SourceEvidenceStore(tmp_path / "store" / "v1")
    store.root.mkdir(parents=True, exist_ok=True)
    pdf = tmp_path / "real.pdf"
    text = "PFCR2 real credentialed embedding gate"
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
    pdf.write_bytes(bytes(pdf_bytes))
    expected_sha = sha256_bytes(pdf.read_bytes())
    result = pfcr2._run_production_m4_ingestion(
        pdf_path=pdf,
        case_id=CASE_ID,
        store_root=store.root,
        runtime_root=runtime,
        expected_original_sha256=expected_sha,
    )
    # Text-bearing PDF requires real frozen-M4 embedding and shadow-row creation.
    assert result.succeeded is True
    doc_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=pdf.name,
        original_blob_sha256=expected_sha,
    )
    manifest = store.load_document_manifest(CASE_ID, doc_id)
    inspection = pfcr2._inspect_inactive_shadow(
        case_id=CASE_ID,
        shadow_db_root=runtime / "db",
        store_root=store.root,
        manifests=(manifest,),
    )
    assert inspection.conflicting_row_count == 0
    assert inspection.missing_row_count == 0
    assert inspection.actual_row_ids == tuple(sorted(pfcr2._manifest_evidence_keys(manifest)))


def test_no_test_embedding_shim_is_present_in_production_module():
    source = (Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "production_shadow_build.py").read_text(encoding="utf-8")
    assert "0.125" not in source
    assert "embeddings.create" not in source
    assert "runtime_root / \"config.py\"" not in source
    assert "openai_client" not in source

