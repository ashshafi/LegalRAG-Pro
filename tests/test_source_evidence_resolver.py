from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.identity import (
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
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
from source_evidence.resolver import (
    SourceEvidenceResolverError,
    resolve_projection_citation_source,
)
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError
from source_evidence.verified_retrieval import build_singleton_analysis_receipt

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
REPORT_MANIFEST_ID = "22222222-2222-4222-8222-222222222222"
PROJECTION_SHA = sha256_bytes(b"projection")
ORIGINAL = b"%PDF-1.7 exact immutable original"
PAGE_TEXT = b"page text\nwith exact spacing"
CHUNK_TEXT = b"chunk text\nexact"


def _citation(evidence_key: str = "chunk-1", *, document_name: str = "evidence.pdf"):
    return SimpleNamespace(
        citation_id=evidence_key,
        evidence_key=evidence_key,
        citation=f"{document_name}, p.1",
        document_name=document_name,
        document_id=None,
        page=1,
        chunk_id=evidence_key,
    )


def _projection(citations=(_citation(),)):
    citations = tuple(citations)
    return SimpleNamespace(
        case_header=SimpleNamespace(case_id=CASE_ID),
        report_projection_id=REPORT_ID,
        projection_payload_sha256=PROJECTION_SHA,
        citations=citations,
        manifest=SimpleNamespace(
            manifest_id=REPORT_MANIFEST_ID,
            ordered_citation_ids=tuple(item.citation_id for item in citations),
        ),
    )


@pytest.fixture(autouse=True)
def _accept_controlled_projection(monkeypatch):
    import source_evidence.resolver as resolver

    monkeypatch.setattr(resolver, "validate_case_report_projection", lambda value: None)


def _extraction_profile() -> ExtractionProfile:
    return ExtractionProfile(
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


def _chunking_profile() -> ChunkingProfile:
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


def _make_manifest() -> SourceDocumentManifest:
    original_sha = sha256_bytes(ORIGINAL)
    page_sha = sha256_bytes(PAGE_TEXT)
    chunk_sha = sha256_bytes(CHUNK_TEXT)
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="evidence.pdf",
        original_blob_sha256=original_sha,
    )
    chunk = SourceChunkSnapshot(
        page_number=1,
        chunk_ordinal=0,
        chunk_id="chunk-1",
        evidence_key="chunk-1",
        chunk_text_sha256=chunk_sha,
        chunk_text_byte_length=len(CHUNK_TEXT),
    )
    page = SourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=page_sha,
        page_text_byte_length=len(PAGE_TEXT),
        chunk_snapshots=(chunk,),
    )
    value = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        original_filename="evidence.pdf",
        media_type="application/pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(ORIGINAL),
        extraction_profile=_extraction_profile(),
        chunking_profile=_chunking_profile(),
        pages=(page,),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_snapshot_id=derive_sha256_id(
            source_document_manifest_identity_payload_to_dict(value)
        ),
    )


def _make_binding(
    binding_class: BindingClass = BindingClass.FULL_CHAIN_BOUND,
    *,
    bound_text_sha256: str | None = None,
) -> EvidenceBinding:
    manifest = _make_manifest()
    if binding_class is BindingClass.FULL_CHAIN_BOUND:
        value = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=CASE_ID,
            evidence_key="chunk-1",
            chunk_id="chunk-1",
            binding_class=binding_class,
            bound_text_role=BoundTextRole.CHUNK_TEXT,
            source_document_instance_id=manifest.source_document_instance_id,
            source_snapshot_id=manifest.source_snapshot_id,
            document_name="evidence.pdf",
            document_id=None,
            page=1,
            chunk_ordinal=0,
            original_blob_sha256=manifest.original_blob_sha256,
            page_text_sha256=manifest.pages[0].page_text_sha256,
            chunk_text_sha256=manifest.pages[0].chunk_snapshots[0].chunk_text_sha256,
            bound_text_sha256=manifest.pages[0].chunk_snapshots[0].chunk_text_sha256,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
            evidence_binding_id="sha256:" + "0" * 64,
        )
    else:
        role = (
            BoundTextRole.ANALYTICAL_SUMMARY
            if binding_class is BindingClass.ANALYTICAL_TEXT_BOUND
            else BoundTextRole.LEGACY_CURRENT_INDEX_TEXT
        )
        assert bound_text_sha256 is not None
        value = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=CASE_ID,
            evidence_key="chunk-1",
            chunk_id="chunk-1",
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
            bound_text_sha256=bound_text_sha256,
            extraction_profile_id=None,
            chunking_profile_id=None,
            evidence_binding_id="sha256:" + "0" * 64,
        )
    return replace(
        value,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)),
    )


def _projection_binding(entries) -> ProjectionEvidenceBindingManifest:
    entries = tuple(entries)
    if not entries or all(item.binding_class is BindingClass.UNBOUND for item in entries):
        coverage = ProjectionBindingCoverage.UNBOUND
    elif all(item.binding_class is BindingClass.FULL_CHAIN_BOUND for item in entries):
        coverage = ProjectionBindingCoverage.FULLY_SOURCE_BOUND
    else:
        coverage = ProjectionBindingCoverage.MIXED_BINDING
    value = ProjectionEvidenceBindingManifest(
        schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_payload_sha256=PROJECTION_SHA,
        manifest_id=REPORT_MANIFEST_ID,
        coverage=coverage,
        entries=entries,
        projection_evidence_binding_manifest_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(value)
        ),
    )


def _full_entry(binding: EvidenceBinding) -> ProjectionBindingEntry:
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=binding.chunk_text_sha256,
    )
    return ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        evidence_binding_id=binding.evidence_binding_id,
        source_bound_analysis_receipt_id=receipt.source_bound_analysis_receipt_id,
    )


def _publish_full_graph(store: SourceEvidenceStore) -> tuple[EvidenceBinding, object]:
    manifest = _make_manifest()
    for content in (ORIGINAL, PAGE_TEXT, CHUNK_TEXT):
        store.put_blob(content)
    store.publish_document_manifest(manifest)
    binding = _make_binding()
    store.publish_evidence_binding(binding)
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=binding.chunk_text_sha256,
    )
    store.publish_analysis_receipt(receipt)
    store.publish_projection_binding(_projection_binding((_full_entry(binding),)))
    return binding, receipt


def test_missing_projection_binding_returns_none_without_creating_store(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    assert resolve_projection_citation_source(
        _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
    ) is None
    assert not store.root.exists()


def test_cross_case_fails_before_store_access(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    with pytest.raises(SourceEvidenceResolverError, match="Active case"):
        resolve_projection_citation_source(
            _projection(), case_id=OTHER_CASE_ID, citation_id="chunk-1", store=store
        )
    assert not store.root.exists()


def test_unknown_projection_citation_fails(tmp_path: Path) -> None:
    with pytest.raises(SourceEvidenceResolverError, match="citation"):
        resolve_projection_citation_source(
            _projection(),
            case_id=CASE_ID,
            citation_id="not-in-projection",
            store=SourceEvidenceStore(tmp_path / "store"),
        )


def test_unbound_honours_frozen_m6_class_without_loading_current_binding(monkeypatch, tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    store.publish_projection_binding(
        _projection_binding((ProjectionBindingEntry(
            citation_id="chunk-1",
            evidence_key="chunk-1",
            binding_class=BindingClass.UNBOUND,
            evidence_binding_id=None,
            source_bound_analysis_receipt_id=None,
        ),))
    )
    monkeypatch.setattr(
        store,
        "load_evidence_binding",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not load current binding")),
    )
    result = resolve_projection_citation_source(
        _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
    )
    assert result is not None
    assert result.binding_class is BindingClass.UNBOUND
    assert result.exact_bound_text is None
    assert result.original_pdf_bytes is None


@pytest.mark.parametrize(
    ("binding_class", "text"),
    [
        (BindingClass.ANALYTICAL_TEXT_BOUND, "retained analytical text"),
        (BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT, "preserved index snapshot"),
    ],
)
def test_weaker_binding_resolves_only_exact_bound_text(
    tmp_path: Path,
    binding_class: BindingClass,
    text: str,
) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    digest = store.put_blob(text.encode("utf-8"))
    binding = _make_binding(binding_class, bound_text_sha256=digest)
    store.publish_evidence_binding(binding)
    store.publish_projection_binding(_projection_binding((ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=binding_class,
        evidence_binding_id=binding.evidence_binding_id,
        source_bound_analysis_receipt_id=None,
    ),)))
    result = resolve_projection_citation_source(
        _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
    )
    assert result is not None
    assert result.binding_class is binding_class
    assert result.exact_bound_text == text
    assert result.exact_page_text is None
    assert result.original_pdf_bytes is None


def test_full_chain_resolves_exact_receipt_manifest_and_bytes(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    binding, receipt = _publish_full_graph(store)
    result = resolve_projection_citation_source(
        _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
    )
    assert result is not None
    assert result.binding_class is BindingClass.FULL_CHAIN_BOUND
    assert result.evidence_binding_id == binding.evidence_binding_id
    assert result.source_bound_analysis_receipt_id == receipt.source_bound_analysis_receipt_id
    assert result.exact_bound_text == CHUNK_TEXT.decode("utf-8")
    assert result.exact_page_text == PAGE_TEXT.decode("utf-8")
    assert result.original_pdf_bytes == ORIGINAL
    assert result.original_filename == "evidence.pdf"
    assert result.extraction_method is ExtractionMethod.PYPDF_TEXT


def test_full_chain_missing_receipt_fails_closed(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    manifest = _make_manifest()
    for content in (ORIGINAL, PAGE_TEXT, CHUNK_TEXT):
        store.put_blob(content)
    store.publish_document_manifest(manifest)
    binding = _make_binding()
    store.publish_evidence_binding(binding)
    store.publish_projection_binding(_projection_binding((_full_entry(binding),)))
    with pytest.raises(SourceEvidenceResolverError):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


def test_full_chain_wrong_stored_receipt_fails_closed(monkeypatch, tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    _binding, receipt = _publish_full_graph(store)
    wrong = replace(receipt, case_id=OTHER_CASE_ID)
    monkeypatch.setattr(store, "load_analysis_receipt", lambda *args, **kwargs: wrong)
    with pytest.raises(SourceEvidenceResolverError, match="receipt"):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


def test_projection_binding_top_level_mismatch_fails(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    entry = ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=BindingClass.UNBOUND,
        evidence_binding_id=None,
        source_bound_analysis_receipt_id=None,
    )
    manifest = _projection_binding((entry,))
    bad = replace(manifest, projection_payload_sha256=sha256_bytes(b"different"))
    bad = replace(
        bad,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(bad)
        ),
    )
    store.publish_projection_binding(bad)
    with pytest.raises(SourceEvidenceResolverError, match="payload"):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


def test_projection_binding_complete_inventory_is_required(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    store.publish_projection_binding(_projection_binding((ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=BindingClass.UNBOUND,
        evidence_binding_id=None,
        source_bound_analysis_receipt_id=None,
    ),)))
    projection = _projection((_citation("chunk-1"), _citation("chunk-2", document_name="two.pdf")))
    with pytest.raises(SourceEvidenceResolverError, match="inventory"):
        resolve_projection_citation_source(
            projection, case_id=CASE_ID, citation_id="chunk-1", store=store
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_name", "different.pdf"),
        ("page", 2),
        ("chunk_id", "different-chunk"),
    ],
)
def test_citation_binding_coordinate_mismatch_fails(
    monkeypatch,
    tmp_path: Path,
    field: str,
    value,
) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    binding, _receipt = _publish_full_graph(store)
    bad = replace(binding, **{field: value}, evidence_binding_id="sha256:" + "0" * 64)
    bad = replace(
        bad,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(bad)),
    )
    monkeypatch.setattr(store, "load_evidence_binding", lambda *args, **kwargs: bad)
    with pytest.raises(SourceEvidenceResolverError):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


@pytest.mark.parametrize("content_index", [0, 1, 2])
def test_full_chain_original_page_chunk_tamper_fails(tmp_path: Path, content_index: int) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    _publish_full_graph(store)
    content = (ORIGINAL, PAGE_TEXT, CHUNK_TEXT)[content_index]
    digest = sha256_bytes(content)
    blob = store.root / "blobs" / "sha256" / digest[:2] / digest
    blob.write_bytes(b"tampered")
    with pytest.raises(SourceEvidenceResolverError):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


def test_invalid_utf8_weaker_text_fails(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store")
    digest = store.put_blob(b"\xff\xfe")
    binding = _make_binding(BindingClass.ANALYTICAL_TEXT_BOUND, bound_text_sha256=digest)
    store.publish_evidence_binding(binding)
    store.publish_projection_binding(_projection_binding((ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=binding.binding_class,
        evidence_binding_id=binding.evidence_binding_id,
        source_bound_analysis_receipt_id=None,
    ),)))
    with pytest.raises(SourceEvidenceResolverError, match="UTF-8"):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )


def test_projection_validator_runs_before_store(monkeypatch, tmp_path: Path) -> None:
    import source_evidence.resolver as resolver

    monkeypatch.setattr(
        resolver,
        "validate_case_report_projection",
        lambda value: (_ for _ in ()).throw(ValueError("invalid projection")),
    )
    store = SourceEvidenceStore(tmp_path / "store")
    with pytest.raises(SourceEvidenceResolverError):
        resolve_projection_citation_source(
            _projection(), case_id=CASE_ID, citation_id="chunk-1", store=store
        )
    assert not store.root.exists()


def test_resolver_production_module_has_no_forbidden_dependencies_or_file_fallback() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "resolver.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = (
        "chromadb",
        "retriever",
        "config",
        "document_manager",
        "pypdf",
        "pdf2image",
        "pytesseract",
        "ocr",
        "legal_analysis",
        "case_analysis",
        "openai",
    )
    assert not any(name.startswith(forbidden) for name in imports)
    for forbidden_text in ("docs/", "PdfReader", "convert_from_path", "open("):
        assert forbidden_text not in source
    for write_name in (
        "put_blob",
        "publish_document_manifest",
        "publish_evidence_binding",
        "publish_analysis_receipt",
        "publish_projection_binding",
    ):
        assert write_name not in source
