from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from case_management.document_context import build_document_id
from source_evidence import capture
from source_evidence.extraction import ExtractedPage, PdfExtractionResult
from source_evidence.identity import sha256_bytes
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    ExtractionMethod,
    ExtractionProfile,
)
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError

CASE_A = "12345678-1234-4234-8234-123456789abc"
CASE_B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ORIGINAL = b"%PDF-immutable-source-bytes\n"


def _profile(*, ocr: bool = False) -> ExtractionProfile:
    return ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version="6.14.2",
        pdf2image_package_version="1.17.0" if ocr else None,
        pytesseract_package_version="0.3.13" if ocr else None,
        tesseract_engine_version="5.5.0" if ocr else None,
        poppler_version="25.01.0" if ocr else None,
        ocr_language="eng",
        ocr_config="",
        ocr_dpi=200,
    )


def _chunk_profile() -> ChunkingProfile:
    return ChunkingProfile(
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


def _install_fake_derivation(monkeypatch, *, page_text="PAGE ONE", chunks=("chunk one", "chunk two")):
    seen = {}

    def fake_extract(pdf_bytes):
        seen.setdefault("extract_bytes", []).append(pdf_bytes)
        return PdfExtractionResult(
            extraction_profile=_profile(),
            pages=(
                ExtractedPage(
                    page_number=1,
                    extraction_method=ExtractionMethod.PYPDF_TEXT,
                    text=page_text,
                ),
            ),
        )

    monkeypatch.setattr(capture, "extract_pdf_pages", fake_extract)
    monkeypatch.setattr(capture, "build_chunking_profile", _chunk_profile)
    monkeypatch.setattr(capture, "split_page_text", lambda text: tuple(chunks) if text == page_text else ())
    return seen


def test_capture_single_read_binds_hash_and_derivation_to_same_bytes(tmp_path, monkeypatch):
    path = tmp_path / "working.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    read_calls = []
    real_read_bytes = Path.read_bytes

    def counted_read_bytes(self):
        data = real_read_bytes(self)
        if self == path:
            read_calls.append(data)
        return data

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    def fake_extract(pdf_bytes):
        assert pdf_bytes == ORIGINAL
        path.write_bytes(b"%PDF-replaced-after-first-read")
        return PdfExtractionResult(
            extraction_profile=_profile(),
            pages=(ExtractedPage(1, ExtractionMethod.PYPDF_TEXT, "PAGE ONE"),),
        )

    monkeypatch.setattr(capture, "extract_pdf_pages", fake_extract)
    monkeypatch.setattr(capture, "build_chunking_profile", _chunk_profile)
    monkeypatch.setattr(capture, "split_page_text", lambda text: ("chunk one",))

    manifest = capture.capture_pdf_source(
        path,
        case_id=CASE_A,
        original_filename="evidence.pdf",
        store=store,
    )

    assert read_calls == [ORIGINAL]
    assert manifest.original_blob_sha256 == sha256_bytes(ORIGINAL)
    assert store.read_blob(manifest.original_blob_sha256) == ORIGINAL
    assert path.read_bytes() == b"%PDF-replaced-after-first-read"


def test_capture_publishes_exact_original_page_chunk_manifest_and_bindings(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch)

    manifest = capture.capture_pdf_source(
        path,
        case_id=CASE_A,
        original_filename="evidence.pdf",
        store=store,
    )

    assert store.read_blob(manifest.original_blob_sha256) == ORIGINAL
    page = manifest.pages[0]
    assert store.read_blob(page.page_text_sha256) == b"PAGE ONE"
    assert tuple(store.read_blob(chunk.chunk_text_sha256) for chunk in page.chunk_snapshots) == (
        b"chunk one",
        b"chunk two",
    )
    assert store.load_document_manifest(CASE_A, manifest.source_document_instance_id) == manifest

    for chunk in page.chunk_snapshots:
        binding = store.load_evidence_binding(CASE_A, chunk.evidence_key)
        assert binding is not None
        assert binding.binding_class is BindingClass.FULL_CHAIN_BOUND
        assert binding.bound_text_role is BoundTextRole.CHUNK_TEXT
        assert binding.source_document_instance_id == manifest.source_document_instance_id
        assert binding.source_snapshot_id == manifest.source_snapshot_id
        assert binding.document_name == "evidence.pdf"
        assert binding.document_id is None
        assert binding.page == 1
        assert binding.chunk_ordinal == chunk.chunk_ordinal
        assert binding.original_blob_sha256 == manifest.original_blob_sha256
        assert binding.page_text_sha256 == page.page_text_sha256
        assert binding.chunk_text_sha256 == chunk.chunk_text_sha256
        assert binding.bound_text_sha256 == chunk.chunk_text_sha256

    assert not (store.root / "cases" / CASE_A / "analysis-receipts").exists()
    assert not (store.root / "cases" / CASE_A / "projection-bindings").exists()


def test_capture_navigation_ids_use_governed_original_filename(tmp_path, monkeypatch):
    physical = tmp_path / "temporary-random-name.pdf"
    physical.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch)

    manifest = capture.capture_pdf_source(
        physical,
        case_id=CASE_A,
        original_filename="ET1.pdf",
        store=store,
    )

    for chunk in manifest.pages[0].chunk_snapshots:
        assert chunk.chunk_id == build_document_id(
            pdf_path=Path("ET1.pdf"),
            page_number=1,
            chunk_number=chunk.chunk_ordinal,
            case_id=CASE_A,
        )
        assert "temporary-random-name" not in chunk.chunk_id


def test_physical_input_path_does_not_affect_source_identities(tmp_path, monkeypatch):
    path_a = tmp_path / "one.pdf"
    path_b = tmp_path / "two.pdf"
    path_a.write_bytes(ORIGINAL)
    path_b.write_bytes(ORIGINAL)
    _install_fake_derivation(monkeypatch)

    manifest_a = capture.capture_pdf_source(
        path_a,
        case_id=CASE_A,
        original_filename="evidence.pdf",
        store=SourceEvidenceStore(tmp_path / "store-a"),
    )
    manifest_b = capture.capture_pdf_source(
        path_b,
        case_id=CASE_A,
        original_filename="evidence.pdf",
        store=SourceEvidenceStore(tmp_path / "store-b"),
    )

    assert manifest_a == manifest_b


def test_filename_is_provenance_identity_not_content_identity(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    _install_fake_derivation(monkeypatch)

    manifest_a = capture.capture_pdf_source(
        path,
        case_id=CASE_A,
        original_filename="A.pdf",
        store=SourceEvidenceStore(tmp_path / "store-a"),
    )
    manifest_b = capture.capture_pdf_source(
        path,
        case_id=CASE_A,
        original_filename="B.pdf",
        store=SourceEvidenceStore(tmp_path / "store-b"),
    )

    assert manifest_a.original_blob_sha256 == manifest_b.original_blob_sha256
    assert manifest_a.pages[0].page_text_sha256 == manifest_b.pages[0].page_text_sha256
    assert manifest_a.pages[0].chunk_snapshots[0].chunk_text_sha256 == manifest_b.pages[0].chunk_snapshots[0].chunk_text_sha256
    assert manifest_a.source_document_instance_id != manifest_b.source_document_instance_id
    assert manifest_a.source_snapshot_id != manifest_b.source_snapshot_id
    assert manifest_a.pages[0].chunk_snapshots[0].chunk_id != manifest_b.pages[0].chunk_snapshots[0].chunk_id


def test_case_is_provenance_identity_not_content_identity(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    _install_fake_derivation(monkeypatch)

    manifest_a = capture.capture_pdf_source(
        path,
        case_id=CASE_A,
        original_filename="evidence.pdf",
        store=SourceEvidenceStore(tmp_path / "store-a"),
    )
    manifest_b = capture.capture_pdf_source(
        path,
        case_id=CASE_B,
        original_filename="evidence.pdf",
        store=SourceEvidenceStore(tmp_path / "store-b"),
    )

    assert manifest_a.original_blob_sha256 == manifest_b.original_blob_sha256
    assert manifest_a.pages[0].page_text_sha256 == manifest_b.pages[0].page_text_sha256
    assert manifest_a.source_document_instance_id != manifest_b.source_document_instance_id
    assert manifest_a.pages[0].chunk_snapshots[0].chunk_id != manifest_b.pages[0].chunk_snapshots[0].chunk_id


def test_identical_capture_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch)

    first = capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)
    second = capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)

    assert first == second


def test_same_document_identity_with_different_derivation_conflicts(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch, page_text="PAGE ONE", chunks=("chunk one",))
    first = capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)

    _install_fake_derivation(monkeypatch, page_text="CHANGED PAGE", chunks=("changed chunk",))
    with pytest.raises(capture.SourceEvidenceCaptureError) as exc_info:
        capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)
    assert isinstance(exc_info.value.__cause__, SourceEvidenceStoreError)
    assert store.load_document_manifest(CASE_A, first.source_document_instance_id) == first


def test_zero_chunk_page_is_valid_source_capture(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch, page_text="   \n", chunks=())

    manifest = capture.capture_pdf_source(path, case_id=CASE_A, original_filename="blank.pdf", store=store)

    assert manifest.pages[0].chunk_snapshots == ()
    assert store.read_blob(manifest.pages[0].page_text_sha256) == b"   \n"
    assert not (store.root / "cases" / CASE_A / "evidence-bindings").exists()


def test_partial_binding_publication_failure_does_not_attempt_rollback(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    _install_fake_derivation(monkeypatch, chunks=("chunk one", "chunk two"))

    class FailingStore(SourceEvidenceStore):
        def __init__(self, root):
            super().__init__(root)
            self.binding_calls = 0

        def publish_evidence_binding(self, binding):
            self.binding_calls += 1
            if self.binding_calls == 2:
                raise SourceEvidenceStoreError("controlled failure")
            return super().publish_evidence_binding(binding)

    store = FailingStore(tmp_path / "store-v1")

    with pytest.raises(capture.SourceEvidenceCaptureError):
        capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)

    # The immutable manifest and first binding remain; no delete/rollback API is invoked.
    document_dirs = list((store.root / "cases" / CASE_A / "documents").glob("*/manifest.json"))
    assert len(document_dirs) == 1
    binding_files = list((store.root / "cases" / CASE_A / "evidence-bindings").glob("*.json"))
    assert len(binding_files) == 1


def test_capture_rejects_noncanonical_case_and_nonplain_filename(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    _install_fake_derivation(monkeypatch)

    with pytest.raises(ValueError):
        capture.capture_pdf_source(path, case_id=CASE_A.upper(), store=SourceEvidenceStore(tmp_path / "s1"))
    with pytest.raises(ValueError):
        capture.capture_pdf_source(
            path,
            case_id=CASE_A,
            original_filename="../evidence.pdf",
            store=SourceEvidenceStore(tmp_path / "s2"),
        )


def test_capture_modules_obey_m3_dependency_and_scope_boundary():
    production = {
        name: Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
        for name, module in {
            "capture": capture,
            "extraction": __import__("source_evidence.extraction", fromlist=["*"]),
            "chunking": __import__("source_evidence.chunking", fromlist=["*"]),
        }.items()
    }
    joined = "\n".join(production.values())
    for forbidden in (
        "chromadb",
        "openai",
        "index_documents",
        "document_upload",
        "legal_analysis_retrieval_adapter",
        "SourceBoundAnalysisReceipt",
        "ProjectionEvidenceBindingManifest",
        "streamlit",
    ):
        assert forbidden not in joined

    capture_tree = ast.parse(production["capture"])
    imports = {
        alias.name
        for node in ast.walk(capture_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "index_documents" not in imports


def test_capture_fixed_identity_golden(tmp_path, monkeypatch):
    path = tmp_path / "input.pdf"
    path.write_bytes(ORIGINAL)
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _install_fake_derivation(monkeypatch, page_text="PAGE ONE", chunks=("chunk one", "chunk two"))

    manifest = capture.capture_pdf_source(path, case_id=CASE_A, original_filename="evidence.pdf", store=store)
    bindings = [
        store.load_evidence_binding(CASE_A, chunk.evidence_key)
        for chunk in manifest.pages[0].chunk_snapshots
    ]

    # Fixed values lock deterministic M1 identity + M3 derivation composition.
    assert manifest.source_document_instance_id == "4e207403-1731-5d91-8ef5-83bfc376d86c"
    assert manifest.source_snapshot_id == "sha256:0cf9cc4124069da1b4adb8802fdfb788b32ba7af92de4727c4221fac186852f6"
    assert [binding.evidence_binding_id for binding in bindings if binding is not None] == [
        "sha256:5355f771a41ab2530f9cbfcad9efb42147342d7c97e161abda5207917e6b4783",
        "sha256:131e3f3ceddd46d6d11bbd0f386529be7b2417f4e287270cf819db9b75876073",
    ]
