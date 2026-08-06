from __future__ import annotations

import ast
import json
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
    HistoricalMigrationDecisionCode,
    HistoricalMigrationInspectionError,
    dumps_historical_migration_report,
    inspect_historical_evidence,
)
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
)
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore
from source_evidence.verified_retrieval import build_singleton_analysis_receipt

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
REPORT_ID_2 = "22222222-2222-4222-8222-222222222222"
REPORT_MANIFEST_ID = "33333333-3333-4333-8333-333333333333"
PROJECTION_SHA = sha256_bytes(b"projection")
ORIGINAL = b"%PDF-1.7 historical"
PAGE = b"page text"
CHUNK = b"chunk text"


class FakeCollection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.write_calls = []
        self.get_calls = []

    def get(self, *, ids=None, where=None, include=None):
        self.get_calls.append((ids, where, tuple(include or ())))
        rows = self.rows
        if ids is not None:
            allowed = set(ids)
            rows = [item for item in rows if item[0] in allowed]
        if where is not None:
            rows = [
                item
                for item in rows
                if all(item[2].get(key) == value for key, value in where.items())
            ]
        return {
            "ids": [item[0] for item in rows],
            "documents": [item[1] for item in rows],
            "metadatas": [item[2] for item in rows],
        }

    def add(self, *args, **kwargs):
        self.write_calls.append("add")
        raise AssertionError("HM1 must not add")

    def update(self, *args, **kwargs):
        self.write_calls.append("update")
        raise AssertionError("HM1 must not update")

    def upsert(self, *args, **kwargs):
        self.write_calls.append("upsert")
        raise AssertionError("HM1 must not upsert")

    def delete(self, *args, **kwargs):
        self.write_calls.append("delete")
        raise AssertionError("HM1 must not delete")


class NoWriteStore:
    def __init__(self, *, binding=None, projection_bindings=None, blobs=None):
        self.binding = binding
        self.projection_bindings = projection_bindings or {}
        self.blobs = blobs or {}
        self.binding_reads = 0

    def load_projection_binding(self, case_id, projection_id):
        return self.projection_bindings.get(projection_id)

    def load_evidence_binding(self, case_id, evidence_key):
        self.binding_reads += 1
        return self.binding

    def read_blob(self, digest):
        return self.blobs[digest]

    def __getattr__(self, name):
        if name.startswith("publish_") or name == "put_blob":
            raise AssertionError(f"HM1 attempted write method {name}")
        raise AttributeError(name)


def _citation(
    key="evidence_1_0",
    *,
    document_name="evidence.pdf",
    page=1,
    chunk_id=None,
    document_id=None,
):
    return SimpleNamespace(
        citation_id=key,
        evidence_key=key,
        document_name=document_name,
        document_id=document_id,
        page=page,
        chunk_id=key if chunk_id is None else chunk_id,
    )


def _projection(*citations, report_id=REPORT_ID):
    citations = tuple(citations)
    return SimpleNamespace(
        case_header=SimpleNamespace(case_id=CASE_ID),
        report_projection_id=report_id,
        projection_payload_sha256=PROJECTION_SHA,
        citations=citations,
        manifest=SimpleNamespace(
            manifest_id=REPORT_MANIFEST_ID,
            ordered_citation_ids=tuple(item.citation_id for item in citations),
        ),
    )


def _row(key="evidence_1_0", text="current text", **metadata):
    base = {"file": "evidence.pdf", "page": 1, "chunk": 0, "case_id": CASE_ID}
    base.update(metadata)
    return (key, text, base)


def _decision(report, key="evidence_1_0"):
    return next(item for item in report.decisions if item.evidence_key == key)


@pytest.fixture(autouse=True)
def _accept_controlled_projections(monkeypatch):
    import source_evidence.migration as migration

    monkeypatch.setattr(migration, "_validate_projection", lambda projection: None)


def _run(
    *,
    key="evidence_1_0",
    rows=(),
    retained=None,
    documents_root=None,
    store=None,
    citations=None,
):
    if citations is None:
        citations = (_citation(key),)
    return inspect_historical_evidence(
        case_id=CASE_ID,
        projections=(_projection(*citations),),
        collection=FakeCollection(rows),
        current_documents_root=documents_root,
        retained_analytical_text=retained,
        store=store or NoWriteStore(),
    )


def _weak_binding(binding_class=BindingClass.ANALYTICAL_TEXT_BOUND):
    bound = b"retained exact text"
    digest = sha256_bytes(bound)
    role = (
        BoundTextRole.ANALYTICAL_SUMMARY
        if binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
        else BoundTextRole.LEGACY_CURRENT_INDEX_TEXT
    )
    value = EvidenceBinding(
        schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        evidence_key="evidence_1_0",
        chunk_id="evidence_1_0",
        binding_class=binding_class,
        bound_text_role=role,
        source_document_instance_id=None,
        source_snapshot_id=None,
        document_name="evidence.pdf",
        document_id=None,
        page=1,
        chunk_ordinal=None,
        original_blob_sha256=None,
        page_text_sha256=None,
        chunk_text_sha256=None,
        bound_text_sha256=digest,
        extraction_profile_id=None,
        chunking_profile_id=None,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)),
    ), {digest: bound}


def _profiles():
    extraction = ExtractionProfile(
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
    )
    chunking = ChunkingProfile(
        profile_id=CHUNKING_PROFILE_ID,
        profile_schema_version=CHUNKING_PROFILE_SCHEMA_VERSION,
        library="langchain-text-splitters",
        library_version="1.1.2",
        chunk_size=1000,
        chunk_overlap=200,
        separators=("\n\n", "\n", " ", ""),
        length_function="len",
        is_separator_regex=False,
    )
    return extraction, chunking


def _full_graph(store: SourceEvidenceStore, *, publish_receipt=True):
    original_sha = store.put_blob(ORIGINAL)
    page_sha = store.put_blob(PAGE)
    chunk_sha = store.put_blob(CHUNK)
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="evidence.pdf",
        original_blob_sha256=original_sha,
    )
    chunk = SourceChunkSnapshot(
        page_number=1,
        chunk_ordinal=0,
        chunk_id="evidence_1_0",
        evidence_key="evidence_1_0",
        chunk_text_sha256=chunk_sha,
        chunk_text_byte_length=len(CHUNK),
    )
    page = SourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=page_sha,
        page_text_byte_length=len(PAGE),
        chunk_snapshots=(chunk,),
    )
    extraction, chunking = _profiles()
    manifest = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        original_filename="evidence.pdf",
        media_type="application/pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(ORIGINAL),
        extraction_profile=extraction,
        chunking_profile=chunking,
        pages=(page,),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    manifest = replace(
        manifest,
        source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(manifest)),
    )
    store.publish_document_manifest(manifest)
    binding = EvidenceBinding(
        schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        evidence_key="evidence_1_0",
        chunk_id="evidence_1_0",
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        source_document_instance_id=document_id,
        source_snapshot_id=manifest.source_snapshot_id,
        document_name="evidence.pdf",
        document_id=None,
        page=1,
        chunk_ordinal=0,
        original_blob_sha256=original_sha,
        page_text_sha256=page_sha,
        chunk_text_sha256=chunk_sha,
        bound_text_sha256=chunk_sha,
        extraction_profile_id=EXTRACTION_PROFILE_ID,
        chunking_profile_id=CHUNKING_PROFILE_ID,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    binding = replace(
        binding,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(binding)),
    )
    store.publish_evidence_binding(binding)
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=chunk_sha,
    )
    if publish_receipt:
        store.publish_analysis_receipt(receipt)
    return binding, receipt


def _projection_binding(binding_class, *, binding_id=None, receipt_id=None):
    entry = ProjectionBindingEntry(
        citation_id="evidence_1_0",
        evidence_key="evidence_1_0",
        binding_class=binding_class,
        evidence_binding_id=binding_id,
        source_bound_analysis_receipt_id=receipt_id,
    )
    coverage = (
        ProjectionBindingCoverage.FULLY_SOURCE_BOUND
        if binding_class is BindingClass.FULL_CHAIN_BOUND
        else ProjectionBindingCoverage.UNBOUND
        if binding_class is BindingClass.UNBOUND
        else ProjectionBindingCoverage.MIXED_BINDING
    )
    value = ProjectionEvidenceBindingManifest(
        schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_payload_sha256=PROJECTION_SHA,
        manifest_id=REPORT_MANIFEST_ID,
        coverage=coverage,
        entries=(entry,),
        projection_evidence_binding_manifest_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(value)
        ),
    )


def test_current_chroma_only_is_capped_at_legacy_snapshot():
    report = _run(rows=(_row(),))
    item = _decision(report)
    assert item.maximum_historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
    assert item.full_chain_projection_eligible is False
    assert item.decision_code in {
        HistoricalMigrationDecisionCode.LEGACY_KEY_DIFFERS_FROM_M3_KEY,
        HistoricalMigrationDecisionCode.CURRENT_INDEX_SNAPSHOT_ONLY,
    }


def test_current_pdf_plus_chroma_does_not_promote_historical_class(tmp_path):
    (tmp_path / "evidence.pdf").write_bytes(b"current pdf bytes")
    report = _run(rows=(_row(),), documents_root=tmp_path)
    item = _decision(report)
    assert item.maximum_historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
    assert item.forward_reingestible is True
    assert item.observation.current_pdf_sha256 == sha256_bytes(b"current pdf bytes")


def test_retained_historical_text_proves_analytical_text_only():
    report = _run(retained={"evidence_1_0": "historical exact summary"})
    item = _decision(report)
    assert item.maximum_historical_binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.HISTORICAL_ANALYTICAL_TEXT_PROVEN
    assert item.full_chain_projection_eligible is False


def test_no_exact_text_authority_remains_unbound():
    item = _decision(_run())
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.NO_EXACT_TEXT_AUTHORITY


def test_pdf_only_is_forward_reingestion_not_historical_provenance(tmp_path):
    (tmp_path / "evidence.pdf").write_bytes(b"pdf")
    item = _decision(_run(documents_root=tmp_path))
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.forward_reingestible is True
    assert item.decision_code is HistoricalMigrationDecisionCode.FORWARD_REINGESTION_CANDIDATE


def test_legacy_key_differs_from_future_m3_case_scoped_key():
    item = _decision(_run(rows=(_row(),)))
    assert item.m3_case_scoped_evidence_key_candidate == f"{CASE_ID}__evidence_1_0"
    assert item.same_key_as_future_m3 is False
    assert item.binding_key_collision_risk is False


def test_case_scoped_weak_candidate_is_flagged_as_binding_collision():
    key = f"{CASE_ID}__evidence_1_0"
    item = _decision(_run(key=key, rows=(_row(key=key),)), key)
    assert item.same_key_as_future_m3 is True
    assert item.binding_key_collision_risk is True
    assert item.maximum_historical_binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
    assert item.decision_code is HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK


def test_case_scoped_analytical_text_candidate_is_also_collision_risk():
    key = f"{CASE_ID}__evidence_1_0"
    item = _decision(
        _run(key=key, rows=(_row(key=key),), retained={key: "historical summary"}),
        key,
    )
    assert item.maximum_historical_binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
    assert item.binding_key_collision_risk is True
    assert item.decision_code is HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK


def test_multiple_different_chroma_rows_for_same_id_are_ambiguous():
    rows = (_row(text="one"), _row(text="two"))
    item = _decision(_run(rows=rows))
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.AMBIGUOUS_CHROMA_ROWS


def test_multiple_current_files_are_ambiguous_and_not_forward_reingestible(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "evidence.pdf").write_bytes(b"one")
    (tmp_path / "b" / "evidence.pdf").write_bytes(b"two")
    item = _decision(_run(rows=(_row(),), documents_root=tmp_path))
    assert item.observation.current_pdf_candidate_count == 2
    assert item.forward_reingestible is False
    assert item.decision_code is HistoricalMigrationDecisionCode.AMBIGUOUS_CURRENT_FILES


def test_projection_coordinate_mismatch_blocks_current_row_promotion():
    item = _decision(_run(rows=(_row(file="other.pdf"),)))
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.CHROMA_COORDINATE_MISMATCH


def test_foreign_case_exact_row_is_not_used():
    item = _decision(_run(rows=(_row(case_id=OTHER_CASE_ID),)))
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.CHROMA_CASE_MISMATCH


def test_conflicting_projection_citations_for_same_evidence_key_are_ambiguous():
    citations = (
        _citation(document_name="one.pdf"),
        _citation(document_name="two.pdf"),
    )
    projections = (
        _projection(citations[0], report_id=REPORT_ID),
        _projection(citations[1], report_id=REPORT_ID_2),
    )
    report = inspect_historical_evidence(
        case_id=CASE_ID,
        projections=projections,
        collection=FakeCollection(),
        store=NoWriteStore(),
    )
    item = _decision(report)
    assert item.maximum_historical_binding_class is BindingClass.UNBOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.AMBIGUOUS_PROJECTION_CITATIONS


def test_existing_weaker_binding_is_reported_and_never_replaced():
    binding, blobs = _weak_binding()
    store = NoWriteStore(binding=binding, blobs=blobs)
    item = _decision(_run(rows=(_row(),), store=store))
    assert item.existing_binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
    assert item.maximum_historical_binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
    assert item.decision_code is HistoricalMigrationDecisionCode.ALREADY_BOUND_WEAKER


def test_existing_full_chain_with_exact_m5_and_blobs_is_already_complete(tmp_path):
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _full_graph(store)
    item = _decision(_run(store=store))
    assert item.existing_binding_class is BindingClass.FULL_CHAIN_BOUND
    assert item.maximum_historical_binding_class is BindingClass.FULL_CHAIN_BOUND
    assert item.full_chain_projection_eligible is True
    assert item.decision_code is HistoricalMigrationDecisionCode.ALREADY_FULL_CHAIN


def test_existing_full_chain_without_m5_receipt_is_not_projection_eligible(tmp_path):
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _full_graph(store, publish_receipt=False)
    item = _decision(_run(store=store))
    assert item.existing_binding_class is BindingClass.FULL_CHAIN_BOUND
    assert item.full_chain_projection_eligible is False
    assert item.decision_code is HistoricalMigrationDecisionCode.M5_RECEIPT_MISSING
    assert HistoricalMigrationDecisionCode.M5_RECEIPT_MISSING.value in item.blockers


def test_frozen_m6_unbound_remains_historically_unbound_decision():
    manifest = _projection_binding(BindingClass.UNBOUND)
    store = NoWriteStore(projection_bindings={REPORT_ID: manifest})
    item = _decision(_run(rows=(_row(),), store=store))
    assert item.existing_projection_entry_classes == ((REPORT_ID, BindingClass.UNBOUND),)
    assert item.decision_code is HistoricalMigrationDecisionCode.FROZEN_PROJECTION_UNBOUND
    assert item.full_chain_projection_eligible is False


def test_frozen_m6_weaker_state_is_preserved():
    binding, blobs = _weak_binding()
    manifest = _projection_binding(
        BindingClass.ANALYTICAL_TEXT_BOUND,
        binding_id=binding.evidence_binding_id,
    )
    store = NoWriteStore(
        binding=binding,
        blobs=blobs,
        projection_bindings={REPORT_ID: manifest},
    )
    item = _decision(_run(store=store))
    assert item.decision_code is HistoricalMigrationDecisionCode.FROZEN_PROJECTION_WEAKER
    assert item.full_chain_projection_eligible is False


def test_existing_m6_manifest_mismatch_fails_closed():
    manifest = replace(_projection_binding(BindingClass.UNBOUND), projection_payload_sha256=sha256_bytes(b"other"))
    # M1 identity is now invalid; the loader is deliberately fake to exercise validation.
    store = NoWriteStore(projection_bindings={REPORT_ID: manifest})
    with pytest.raises(HistoricalMigrationInspectionError):
        _run(store=store)


def test_non_projected_case_rows_are_included_as_separate_decisions():
    rows = (
        _row(),
        _row(key="other_1_0", file="other.pdf", page=1, chunk=0),
    )
    report = _run(rows=rows)
    assert {item.evidence_key for item in report.decisions} == {"evidence_1_0", "other_1_0"}
    assert tuple(item.evidence_key for item in report.non_projected_decisions) == ("other_1_0",)


def test_report_views_derive_from_one_decision_set(tmp_path):
    (tmp_path / "evidence.pdf").write_bytes(b"pdf")
    report = _run(rows=(_row(),), documents_root=tmp_path)
    assert report.projection_decisions == report.decisions
    assert report.non_projected_decisions == ()
    assert report.forward_reingestion_decisions == report.decisions


def test_report_contains_hashes_not_source_text(tmp_path):
    (tmp_path / "evidence.pdf").write_bytes(b"secret pdf bytes")
    report = _run(
        rows=(_row(text="secret current row text"),),
        retained={"evidence_1_0": "secret historical text"},
        documents_root=tmp_path,
    )
    payload = dumps_historical_migration_report(report)
    assert "secret current row text" not in payload
    assert "secret historical text" not in payload
    assert "secret pdf bytes" not in payload
    assert sha256_bytes("secret current row text".encode()) in payload
    assert sha256_bytes("secret historical text".encode()) in payload


def test_report_json_is_canonical_and_has_one_final_newline():
    report = _run(rows=(_row(),))
    payload = dumps_historical_migration_report(report)
    assert payload.endswith("\n") and not payload.endswith("\n\n")
    parsed = json.loads(payload)
    assert parsed["schema_version"] == HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION
    assert parsed["historical_migration_report_id"] == report.historical_migration_report_id


def test_report_identity_is_path_and_machine_independent(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "evidence.pdf").write_bytes(b"same")
    (second / "evidence.pdf").write_bytes(b"same")
    a = _run(rows=(_row(),), documents_root=first)
    b = _run(rows=(_row(),), documents_root=second)
    assert a.historical_migration_report_id == b.historical_migration_report_id
    assert dumps_historical_migration_report(a) == dumps_historical_migration_report(b)


def test_dry_run_does_not_create_absent_source_store(tmp_path):
    root = tmp_path / "absent-store-v1"
    store = SourceEvidenceStore(root)
    assert not root.exists()
    _run(store=store)
    assert not root.exists()


def test_collection_is_read_only_and_never_uses_write_methods():
    collection = FakeCollection((_row(),))
    inspect_historical_evidence(
        case_id=CASE_ID,
        projections=(_projection(_citation()),),
        collection=collection,
        store=NoWriteStore(),
    )
    assert collection.write_calls == []
    assert collection.get_calls


def test_projection_validation_occurs_before_chroma_read(monkeypatch):
    import source_evidence.migration as migration

    class NoTouchCollection:
        def get(self, **kwargs):
            raise AssertionError("collection must not be read")

    monkeypatch.setattr(
        migration,
        "_validate_projection",
        lambda projection: (_ for _ in ()).throw(HistoricalMigrationInspectionError("bad")),
    )
    with pytest.raises(HistoricalMigrationInspectionError):
        inspect_historical_evidence(
            case_id=CASE_ID,
            projections=(_projection(_citation()),),
            collection=NoTouchCollection(),
            store=NoWriteStore(),
        )


def test_cross_case_projection_fails_before_inventory():
    projection = _projection(_citation())
    projection.case_header.case_id = OTHER_CASE_ID
    with pytest.raises(HistoricalMigrationInspectionError):
        inspect_historical_evidence(
            case_id=CASE_ID,
            projections=(projection,),
            collection=FakeCollection(),
            store=NoWriteStore(),
        )


def test_malformed_chroma_response_fails_closed():
    class BadCollection:
        def get(self, **kwargs):
            return {"ids": ["x"], "documents": [], "metadatas": []}

    with pytest.raises(HistoricalMigrationInspectionError):
        inspect_historical_evidence(
            case_id=CASE_ID,
            projections=(_projection(_citation()),),
            collection=BadCollection(),
            store=NoWriteStore(),
        )


def test_no_apply_or_write_capability_exists_in_migration_module():
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "migration.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "--apply" not in source
    forbidden_attrs = {
        "put_blob",
        "publish_document_manifest",
        "publish_evidence_binding",
        "publish_analysis_receipt",
        "publish_projection_binding",
        "add",
        "update",
        "upsert",
        "delete",
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (calls & forbidden_attrs)


def test_no_capture_ingestion_ocr_or_llm_dependencies():
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "migration.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = (
        "source_evidence.capture",
        "source_evidence.ingestion",
        "source_evidence.extraction",
        "chromadb",
        "openai",
        "pypdf",
        "pdf2image",
        "pytesseract",
        "streamlit",
    )
    assert not any(name.startswith(forbidden) for name in imports)


def test_module_import_is_runtime_safe_without_chroma_or_openai():
    import source_evidence.migration as migration

    assert callable(migration.inspect_historical_evidence)
    assert not hasattr(migration, "apply_historical_migration")



def test_cross_platform_report_golden_is_stable():
    report = _run(rows=(_row(),))
    assert report.historical_migration_report_id == (
        "sha256:add97468820c98654bac30348f1b51bd08767f22c0ba1b48f950ee4b3a10a4be"
    )
    item = _decision(report)
    assert item.observation.current_chroma_document_sha256 == (
        "adafe60422c5c7971b218840a1578c32ca2f5cb9b3dc92bb832e278c142d4650"
    )
    assert item.observation.current_chroma_metadata_fingerprint == (
        "sha256:6215beaadf7a116a6a22e5f515d184f58a3e890ef0c57dfdbc6d7ffb07c5bc78"
    )


def test_invalid_case_id_fails_closed():
    with pytest.raises(ValueError):
        inspect_historical_evidence(
            case_id="not-a-uuid",
            projections=(),
            collection=FakeCollection(),
            store=NoWriteStore(),
        )
