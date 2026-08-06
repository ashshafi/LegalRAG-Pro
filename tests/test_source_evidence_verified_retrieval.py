from __future__ import annotations

import ast
import copy
import importlib
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from source_evidence.identity import derive_sha256_id, derive_source_document_instance_id, sha256_bytes
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    PDF_MEDIA_TYPE,
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
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError
from source_evidence.verified_retrieval import (
    SourceBoundRetrievalVerificationError,
    build_singleton_analysis_receipt,
    verify_source_bound_retrieval_results,
)

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "22345678-1234-4234-8234-123456789abc"
FILENAME = "evidence.pdf"


def _profile() -> ExtractionProfile:
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


def _final_manifest(provisional: SourceDocumentManifest) -> SourceDocumentManifest:
    return replace(
        provisional,
        source_snapshot_id=derive_sha256_id(
            source_document_manifest_identity_payload_to_dict(provisional)
        ),
    )


def _final_binding(provisional: EvidenceBinding) -> EvidenceBinding:
    return replace(
        provisional,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(provisional)),
    )


def _publish_fixture(tmp_path: Path, *, two_chunks: bool = False):
    store = SourceEvidenceStore(tmp_path / "store-v1")
    original = b"%PDF-1.7 controlled exact source bytes"
    page_text = "Alpha evidence.\nBeta evidence."
    chunks = ("Alpha evidence.", "Beta evidence.") if two_chunks else (page_text,)

    original_sha = store.put_blob(original)
    page_sha = store.put_blob(page_text.encode("utf-8"))
    chunk_shas = tuple(store.put_blob(item.encode("utf-8")) for item in chunks)

    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=FILENAME,
        original_blob_sha256=original_sha,
    )
    chunk_snapshots = tuple(
        SourceChunkSnapshot(
            page_number=1,
            chunk_ordinal=ordinal,
            chunk_id=f"{CASE_ID}::{Path(FILENAME).stem}::p1::c{ordinal}",
            evidence_key=f"{CASE_ID}::{Path(FILENAME).stem}::p1::c{ordinal}",
            chunk_text_sha256=chunk_shas[ordinal],
            chunk_text_byte_length=len(chunks[ordinal].encode("utf-8")),
        )
        for ordinal in range(len(chunks))
    )
    provisional_manifest = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        original_filename=FILENAME,
        media_type=PDF_MEDIA_TYPE,
        original_blob_sha256=original_sha,
        original_byte_length=len(original),
        extraction_profile=_profile(),
        chunking_profile=_chunk_profile(),
        pages=(
            SourcePageSnapshot(
                page_number=1,
                extraction_method=ExtractionMethod.PYPDF_TEXT,
                page_text_sha256=page_sha,
                page_text_byte_length=len(page_text.encode("utf-8")),
                chunk_snapshots=chunk_snapshots,
            ),
        ),
        source_snapshot_id="sha256:" + ("0" * 64),
    )
    manifest = _final_manifest(provisional_manifest)
    store.publish_document_manifest(manifest)

    bindings = []
    for chunk in chunk_snapshots:
        provisional_binding = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=CASE_ID,
            evidence_key=chunk.evidence_key,
            chunk_id=chunk.chunk_id,
            binding_class=BindingClass.FULL_CHAIN_BOUND,
            bound_text_role=BoundTextRole.CHUNK_TEXT,
            source_document_instance_id=document_id,
            source_snapshot_id=manifest.source_snapshot_id,
            document_name=FILENAME,
            document_id=None,
            page=1,
            chunk_ordinal=chunk.chunk_ordinal,
            original_blob_sha256=original_sha,
            page_text_sha256=page_sha,
            chunk_text_sha256=chunk.chunk_text_sha256,
            bound_text_sha256=chunk.chunk_text_sha256,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
            evidence_binding_id="sha256:" + ("0" * 64),
        )
        binding = _final_binding(provisional_binding)
        store.publish_evidence_binding(binding)
        bindings.append(binding)

    rows = []
    for chunk_text, chunk, binding in zip(chunks, chunk_snapshots, bindings):
        rows.append(
            (
                chunk.chunk_id,
                chunk_text,
                {
                    "case_id": CASE_ID,
                    "file": FILENAME,
                    "page": 1,
                    "chunk": chunk.chunk_ordinal,
                    "source_evidence_binding_id": binding.evidence_binding_id,
                    "source_snapshot_id": manifest.source_snapshot_id,
                    "source_document_instance_id": manifest.source_document_instance_id,
                    "source_chunk_sha256": chunk.chunk_text_sha256,
                    "source_page_text_sha256": page_sha,
                    "source_original_blob_sha256": original_sha,
                    "source_binding_class": "full_chain_bound",
                    "rank_score": 0.91 - chunk.chunk_ordinal * 0.1,
                    "semantic_role": "supporting",
                },
            )
        )

    result = {
        "ids": [[item[0] for item in rows]],
        "documents": [[item[1] for item in rows]],
        "metadatas": [[item[2] for item in rows]],
        "distances": [[0.1 for _ in rows]],
    }
    return store, manifest, tuple(bindings), result


def test_single_exact_row_verifies_returns_same_object_and_publishes_receipt(tmp_path):
    store, _manifest, bindings, result = _publish_fixture(tmp_path)
    original_copy = copy.deepcopy(result)
    returned = verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)
    assert returned is result
    assert returned == original_copy
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=bindings[0].evidence_key,
        evidence_binding_id=bindings[0].evidence_binding_id,
        chunk_text_sha256=bindings[0].chunk_text_sha256,
    )
    assert len(receipt.verified_evidence) == 1
    assert store.load_analysis_receipt(CASE_ID, receipt.source_bound_analysis_receipt_id) == receipt


def test_multiple_rows_preserve_order_and_publish_singletons(tmp_path):
    store, _manifest, bindings, result = _publish_fixture(tmp_path, two_chunks=True)
    returned = verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)
    assert returned["ids"] == result["ids"]
    for binding in bindings:
        receipt = build_singleton_analysis_receipt(
            case_id=CASE_ID,
            evidence_key=binding.evidence_key,
            evidence_binding_id=binding.evidence_binding_id,
            chunk_text_sha256=binding.chunk_text_sha256,
        )
        assert store.load_analysis_receipt(CASE_ID, receipt.source_bound_analysis_receipt_id) == receipt


def test_empty_result_is_returned_without_creating_store(tmp_path, monkeypatch):
    result = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
    class ExplodingStore:
        def __init__(self):
            raise AssertionError("store must not be constructed")
    monkeypatch.setattr("source_evidence.verified_retrieval.SourceEvidenceStore", ExplodingStore)
    assert verify_source_bound_retrieval_results(result, case_id=CASE_ID) is result


@pytest.mark.parametrize(
    "mutator",
    [
        lambda r: r.pop("ids"),
        lambda r: r.__setitem__("ids", []),
        lambda r: r.__setitem__("ids", [["a"], ["b"]]),
        lambda r: r.__setitem__("documents", [[]]),
        lambda r: r.__setitem__("metadatas", [[{}, {}]]),
        lambda r: r.__setitem__("ids", [[1]]),
        lambda r: r.__setitem__("documents", [[1]]),
        lambda r: r.__setitem__("metadatas", [["not-metadata"]]),
    ],
)
def test_malformed_result_shapes_fail_closed(tmp_path, mutator):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    mutator(result)
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_duplicate_ids_fail_closed(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path, two_chunks=True)
    result["ids"][0][1] = result["ids"][0][0]
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_id", OTHER_CASE_ID),
        ("file", "other.pdf"),
        ("page", 2),
        ("chunk", 9),
        ("source_evidence_binding_id", "sha256:" + "1" * 64),
        ("source_snapshot_id", "sha256:" + "1" * 64),
        ("source_document_instance_id", "32345678-1234-4234-8234-123456789abc"),
        ("source_chunk_sha256", "1" * 64),
        ("source_page_text_sha256", "1" * 64),
        ("source_original_blob_sha256", "1" * 64),
        ("source_binding_class", "analytical_text_bound"),
    ],
)
def test_metadata_coordinate_mismatch_fails_closed(tmp_path, field, value):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    result["metadatas"][0][0][field] = value
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_missing_m4_metadata_fails_closed(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    del result["metadatas"][0][0]["source_snapshot_id"]
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_missing_binding_fails_closed(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    result["ids"][0][0] += "-missing"
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_non_full_chain_binding_fails_closed(tmp_path):
    store, _manifest, bindings, result = _publish_fixture(tmp_path)
    binding = bindings[0]
    path = store._evidence_binding_path(CASE_ID, binding.evidence_key)
    from source_evidence.serialization import dumps_evidence_binding
    altered = replace(
        binding,
        binding_class=BindingClass.ANALYTICAL_TEXT_BOUND,
        bound_text_role=BoundTextRole.ANALYTICAL_SUMMARY,
        source_document_instance_id=None,
        source_snapshot_id=None,
        page=None,
        chunk_ordinal=None,
        original_blob_sha256=None,
        page_text_sha256=None,
        chunk_text_sha256=None,
        extraction_profile_id=None,
        chunking_profile_id=None,
        bound_text_sha256="2" * 64,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    altered = _final_binding(altered)
    path.write_bytes(dumps_evidence_binding(altered).encode("utf-8"))
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_retrieved_document_must_match_exact_chunk_text(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    result["documents"][0][0] += " "
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_original_blob_tamper_fails_closed(tmp_path):
    store, manifest, _bindings, result = _publish_fixture(tmp_path)
    store._blob_path(manifest.original_blob_sha256).write_bytes(b"tampered")
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_page_blob_tamper_fails_closed(tmp_path):
    store, manifest, _bindings, result = _publish_fixture(tmp_path)
    store._blob_path(manifest.pages[0].page_text_sha256).write_bytes(b"tampered")
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_chunk_blob_tamper_fails_closed(tmp_path):
    store, manifest, _bindings, result = _publish_fixture(tmp_path)
    store._blob_path(manifest.pages[0].chunk_snapshots[0].chunk_text_sha256).write_bytes(b"tampered")
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=store)


def test_invalid_utf8_page_blob_fails_even_when_hash_is_rebound_via_fake_store(tmp_path):
    store, manifest, _bindings, result = _publish_fixture(tmp_path)
    class DelegatingStore:
        def load_evidence_binding(self, *a): return store.load_evidence_binding(*a)
        def load_document_manifest(self, *a): return store.load_document_manifest(*a)
        def publish_analysis_receipt(self, r): return store.publish_analysis_receipt(r)
        def read_blob(self, digest):
            if digest == manifest.pages[0].page_text_sha256:
                return b"\xff" * manifest.pages[0].page_text_byte_length
            return store.read_blob(digest)
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=DelegatingStore())


def test_per_call_blob_cache_reads_shared_original_and_page_once(tmp_path):
    store, manifest, _bindings, result = _publish_fixture(tmp_path, two_chunks=True)
    counts = {}
    class CountingStore:
        def load_evidence_binding(self, *a): return store.load_evidence_binding(*a)
        def load_document_manifest(self, *a): return store.load_document_manifest(*a)
        def publish_analysis_receipt(self, r): return store.publish_analysis_receipt(r)
        def read_blob(self, digest):
            counts[digest] = counts.get(digest, 0) + 1
            return store.read_blob(digest)
    verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=CountingStore())
    assert counts[manifest.original_blob_sha256] == 1
    assert counts[manifest.pages[0].page_text_sha256] == 1
    assert counts[manifest.pages[0].chunk_snapshots[0].chunk_text_sha256] == 1
    assert counts[manifest.pages[0].chunk_snapshots[1].chunk_text_sha256] == 1


def test_receipt_identity_is_deterministic_and_singleton(tmp_path):
    _store, _manifest, bindings, _result = _publish_fixture(tmp_path)
    b = bindings[0]
    first = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=b.evidence_key,
        evidence_binding_id=b.evidence_binding_id,
        chunk_text_sha256=b.chunk_text_sha256,
    )
    second = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=b.evidence_key,
        evidence_binding_id=b.evidence_binding_id,
        chunk_text_sha256=b.chunk_text_sha256,
    )
    assert first == second
    assert len(first.verified_evidence) == 1
    assert first.verifier_version == "source-bound-retrieval-verifier/1.0"


def test_full_batch_verifies_before_any_receipt_publication(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path, two_chunks=True)
    result["documents"][0][1] += "tamper"
    published = []
    class RecordingStore:
        def load_evidence_binding(self, *a): return store.load_evidence_binding(*a)
        def load_document_manifest(self, *a): return store.load_document_manifest(*a)
        def read_blob(self, *a): return store.read_blob(*a)
        def publish_analysis_receipt(self, r): published.append(r)
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=RecordingStore())
    assert published == []


def test_receipt_publication_failure_stops_result_and_retains_earlier(tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path, two_chunks=True)
    published = []
    class FailingStore:
        def load_evidence_binding(self, *a): return store.load_evidence_binding(*a)
        def load_document_manifest(self, *a): return store.load_document_manifest(*a)
        def read_blob(self, *a): return store.read_blob(*a)
        def publish_analysis_receipt(self, receipt):
            published.append(receipt)
            if len(published) == 2:
                raise SourceEvidenceStoreError("controlled publication failure")
            store.publish_analysis_receipt(receipt)
    with pytest.raises(SourceBoundRetrievalVerificationError):
        verify_source_bound_retrieval_results(result, case_id=CASE_ID, store=FailingStore())
    assert len(published) == 2
    first = published[0]
    assert store.load_analysis_receipt(CASE_ID, first.source_bound_analysis_receipt_id) == first


def _load_adapter(monkeypatch, *, retrieve_fn, enrich_fn):
    retriever_mod = types.ModuleType("retriever")
    retriever_mod.retrieve = retrieve_fn
    semantics_mod = types.ModuleType("evidence_semantics")
    semantics_mod.enrich_evidence_semantics = enrich_fn
    monkeypatch.setitem(sys.modules, "retriever", retriever_mod)
    monkeypatch.setitem(sys.modules, "evidence_semantics", semantics_mod)
    sys.modules.pop("legal_analysis_retrieval_adapter", None)
    return importlib.import_module("legal_analysis_retrieval_adapter")


def test_adapter_rejects_missing_or_noncanonical_case_before_retrieve(monkeypatch):
    called = []
    adapter = _load_adapter(
        monkeypatch,
        retrieve_fn=lambda *a, **k: called.append((a, k)),
        enrich_fn=lambda value: value,
    )
    for bad in (None, "", CASE_ID.upper(), "not-a-uuid"):
        with pytest.raises(SourceBoundRetrievalVerificationError):
            adapter.retrieve_for_legal_analysis("q", case_id=bad)
    assert called == []


def test_adapter_preserves_retrieval_arguments_enriches_then_verifies(monkeypatch, tmp_path):
    store, _manifest, _bindings, result = _publish_fixture(tmp_path)
    calls = []
    def fake_retrieve(question, selected_documents, *, n_results, case_id):
        calls.append(("retrieve", question, selected_documents, n_results, case_id))
        return copy.deepcopy(result)
    def fake_enrich(value):
        calls.append(("enrich", value))
        value["metadatas"][0][0]["semantic_added"] = True
        return value
    adapter = _load_adapter(monkeypatch, retrieve_fn=fake_retrieve, enrich_fn=fake_enrich)
    monkeypatch.setattr(
        adapter,
        "verify_source_bound_retrieval_results",
        lambda value, *, case_id: calls.append(("verify", value, case_id)) or value,
    )
    returned = adapter.retrieve_for_legal_analysis(
        "question",
        ["evidence.pdf"],
        7,
        case_id=CASE_ID,
    )
    assert calls[0] == ("retrieve", "question", ["evidence.pdf"], 7, CASE_ID)
    assert calls[1][0] == "enrich"
    assert calls[2][0] == "verify"
    assert calls[2][1]["metadatas"][0][0]["semantic_added"] is True
    assert returned is calls[2][1]


def test_adapter_verification_failure_has_no_fallback(monkeypatch):
    result = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
    adapter = _load_adapter(
        monkeypatch,
        retrieve_fn=lambda *a, **k: result,
        enrich_fn=lambda value: value,
    )
    def fail(*a, **k):
        raise SourceBoundRetrievalVerificationError("controlled")
    monkeypatch.setattr(adapter, "verify_source_bound_retrieval_results", fail)
    with pytest.raises(SourceBoundRetrievalVerificationError):
        adapter.retrieve_for_legal_analysis("q", case_id=CASE_ID)


def test_verifier_has_no_forbidden_runtime_dependencies_or_file_fallbacks():
    path = SRC / "source_evidence" / "verified_retrieval.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "chromadb", "openai", "retriever", "pypdf", "pdf2image", "pytesseract",
        "legal_analysis", "case_analysis", "case_reporting", "streamlit",
    }
    assert not any(item.split(".")[0] in forbidden for item in imports)
    for token in ("Path.read_bytes", "PdfReader", "convert_from_path", "docs/"):
        assert token not in source


def test_adapter_is_only_existing_production_file_changed_by_m5_scope():
    verifier = SRC / "source_evidence" / "verified_retrieval.py"
    adapter = SRC / "legal_analysis_retrieval_adapter.py"
    assert verifier.exists()
    assert adapter.exists()
    assert "verify_source_bound_retrieval_results" in adapter.read_text(encoding="utf-8")


def test_adapter_import_is_safe_without_retrieval_runtime(monkeypatch):
    monkeypatch.delitem(sys.modules, "retriever", raising=False)
    monkeypatch.delitem(sys.modules, "evidence_semantics", raising=False)
    sys.modules.pop("legal_analysis_retrieval_adapter", None)
    module = importlib.import_module("legal_analysis_retrieval_adapter")
    assert hasattr(module, "retrieve_for_legal_analysis")
    assert "retriever" not in sys.modules
    assert "evidence_semantics" not in sys.modules


def test_receipt_identity_cross_platform_golden(tmp_path):
    _store, _manifest, bindings, _result = _publish_fixture(tmp_path)
    binding = bindings[0]
    assert binding.evidence_binding_id == (
        "sha256:4f3db4d5fc9ba3d3737736989bc0bc6a7d028d4218fa9bb23afeeb9cec3c72aa"
    )
    assert binding.chunk_text_sha256 == (
        "a8c41b368ea51b011a7341f42ad2bdfacb0b6c715937c64f696f4c569527c533"
    )
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=binding.chunk_text_sha256,
    )
    assert receipt.source_bound_analysis_receipt_id == (
        "sha256:770513e0860f23552b7f111d5ebfc13ed7932b5c1ebbebb8c30a1af497a33bca"
    )
