from __future__ import annotations

import inspect
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import document_upload
from case_management.document_context import build_document_id
from source_evidence import ingestion
from source_evidence.chroma_lock import ChromaWriterLock
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
from source_evidence.store import SourceEvidenceStore

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
ORIGINAL = b"%PDF-1.7\nM4 deterministic fixture\n"


class FakeEmbeddings:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.inputs: list[str] = []
        self.fail_at = fail_at

    def create(self, *, model: str, input: str):
        self.inputs.append(input)
        if self.fail_at is not None and len(self.inputs) == self.fail_at:
            raise RuntimeError("controlled embedding failure")
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(len(input)), 0.25, 0.75])]
        )


class FakeOpenAI:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.embeddings = FakeEmbeddings(fail_at=fail_at)


class FakeChromaClient:
    def __init__(self, max_batch_size: int = 1000) -> None:
        self.max_batch_size = max_batch_size
        self.calls = 0

    def get_max_batch_size(self) -> int:
        self.calls += 1
        return self.max_batch_size


class FakeCollection:
    name = "legal_documents"

    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, dict[str, object], list[float]]] = {}
        self.get_calls = 0
        self.add_calls: list[dict[str, object]] = []
        self.mode = "normal"
        self._guard = threading.Lock()

    def get(self, *, ids, include):
        assert include == ["documents", "metadatas"]
        with self._guard:
            self.get_calls += 1
            found = [row_id for row_id in ids if row_id in self.rows]
            return {
                "ids": found,
                "documents": [self.rows[row_id][0] for row_id in found],
                "metadatas": [dict(self.rows[row_id][1]) for row_id in found],
            }

    def add(self, *, ids, embeddings, documents, metadatas):
        call = {
            "ids": list(ids),
            "embeddings": [list(value) for value in embeddings],
            "documents": list(documents),
            "metadatas": [dict(value) for value in metadatas],
        }
        with self._guard:
            self.add_calls.append(call)
            if self.mode == "partial_raise":
                count = max(1, len(ids) // 2)
            else:
                count = len(ids)
            for index in range(count):
                metadata = dict(metadatas[index])
                document = documents[index]
                if self.mode == "conflict_after_add" and index == 0:
                    metadata["source_snapshot_id"] = "sha256:" + "f" * 64
                self.rows[ids[index]] = (document, metadata, list(embeddings[index]))
            if self.mode in {"raise_after_all", "partial_raise"}:
                raise RuntimeError("controlled add exception")


class ScriptedCollection(FakeCollection):
    def __init__(self, results: list[dict[str, object]]) -> None:
        super().__init__()
        self.results = list(results)

    def get(self, *, ids, include):
        self.get_calls += 1
        if self.results:
            return self.results.pop(0)
        return super().get(ids=ids, include=include)


def _profiles() -> tuple[ExtractionProfile, ChunkingProfile]:
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


def _make_graph(
    tmp_path: Path,
    *,
    chunks: tuple[bytes, ...] = (b"chunk one", b"chunk two"),
    page_texts: tuple[bytes, ...] = (b"  PAGE ONE  ", b"PAGE TWO"),
    filename: str = "evidence.pdf",
    case_id: str = CASE_ID,
) -> tuple[Path, SourceDocumentManifest, SourceEvidenceStore]:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    pdf_path = tmp_path / filename
    pdf_path.write_bytes(ORIGINAL)
    original_sha = store.put_blob(ORIGINAL)
    document_id = derive_source_document_instance_id(
        case_id=case_id,
        original_filename=filename,
        original_blob_sha256=original_sha,
    )
    extraction_profile, chunking_profile = _profiles()

    pages: list[SourcePageSnapshot] = []
    chunk_index = 0
    for page_number, page_bytes in enumerate(page_texts, start=1):
        page_sha = store.put_blob(page_bytes)
        page_chunks: list[SourceChunkSnapshot] = []
        if page_number == 1:
            assigned = chunks
        else:
            assigned = ()
        for chunk_ordinal, chunk_bytes in enumerate(assigned):
            chunk_sha = store.put_blob(chunk_bytes)
            chunk_id = build_document_id(
                pdf_path=Path(filename),
                page_number=page_number,
                chunk_number=chunk_ordinal,
                case_id=case_id,
            )
            page_chunks.append(
                SourceChunkSnapshot(
                    page_number=page_number,
                    chunk_ordinal=chunk_ordinal,
                    chunk_id=chunk_id,
                    evidence_key=chunk_id,
                    chunk_text_sha256=chunk_sha,
                    chunk_text_byte_length=len(chunk_bytes),
                )
            )
            chunk_index += 1
        pages.append(
            SourcePageSnapshot(
                page_number=page_number,
                extraction_method=ExtractionMethod.PYPDF_TEXT,
                page_text_sha256=page_sha,
                page_text_byte_length=len(page_bytes),
                chunk_snapshots=tuple(page_chunks),
            )
        )

    provisional = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=case_id,
        source_document_instance_id=document_id,
        original_filename=filename,
        media_type="application/pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(ORIGINAL),
        extraction_profile=extraction_profile,
        chunking_profile=chunking_profile,
        pages=tuple(pages),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    manifest = replace(
        provisional,
        source_snapshot_id=derive_sha256_id(
            source_document_manifest_identity_payload_to_dict(provisional)
        ),
    )
    store.publish_document_manifest(manifest)
    for page in manifest.pages:
        for chunk in page.chunk_snapshots:
            binding_provisional = EvidenceBinding(
                schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
                case_id=manifest.case_id,
                evidence_key=chunk.evidence_key,
                chunk_id=chunk.chunk_id,
                binding_class=BindingClass.FULL_CHAIN_BOUND,
                bound_text_role=BoundTextRole.CHUNK_TEXT,
                source_document_instance_id=manifest.source_document_instance_id,
                source_snapshot_id=manifest.source_snapshot_id,
                document_name=manifest.original_filename,
                document_id=None,
                page=page.page_number,
                chunk_ordinal=chunk.chunk_ordinal,
                original_blob_sha256=manifest.original_blob_sha256,
                page_text_sha256=page.page_text_sha256,
                chunk_text_sha256=chunk.chunk_text_sha256,
                bound_text_sha256=chunk.chunk_text_sha256,
                extraction_profile_id=manifest.extraction_profile.profile_id,
                chunking_profile_id=manifest.chunking_profile.profile_id,
                evidence_binding_id="sha256:" + "0" * 64,
            )
            binding = replace(
                binding_provisional,
                evidence_binding_id=derive_sha256_id(
                    evidence_binding_identity_payload_to_dict(binding_provisional)
                ),
            )
            store.publish_evidence_binding(binding)
    return pdf_path, manifest, store


def _runtime(tmp_path: Path, collection: FakeCollection, *, openai=None, maximum=1000):
    return ingestion._Runtime(
        chroma_client=FakeChromaClient(maximum),
        collection=collection,
        openai_client=openai or FakeOpenAI(),
        embedding_model="text-embedding-3-small",
        db_path=(tmp_path / "db").resolve(strict=False),
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
    )


def _install_capture_and_runtime(monkeypatch, manifest, runtime):
    calls: list[dict[str, object]] = []

    def fake_capture(pdf_path, *, case_id, original_filename, store):
        calls.append(
            {
                "pdf_path": Path(pdf_path),
                "case_id": case_id,
                "original_filename": original_filename,
                "store": store,
            }
        )
        return manifest

    monkeypatch.setattr(ingestion, "capture_pdf_source", fake_capture)
    monkeypatch.setattr(ingestion, "_load_runtime", lambda: runtime)
    return calls


def _prepared(manifest, store, evidence_source_type=None):
    return ingestion._prepare_rows(
        manifest=manifest,
        store=store,
        evidence_source_type=evidence_source_type,
    )


def _exact_result(rows):
    return {
        "ids": [row.row_id for row in rows],
        "documents": [row.document for row in rows],
        "metadatas": [dict(row.metadata) for row in rows],
    }




def _alter_binding(binding: EvidenceBinding, **changes) -> EvidenceBinding:
    provisional = replace(
        binding,
        evidence_binding_id="sha256:" + "0" * 64,
        **changes,
    )
    return replace(
        provisional,
        evidence_binding_id=derive_sha256_id(
            evidence_binding_identity_payload_to_dict(provisional)
        ),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": OTHER_CASE_ID},
        {"evidence_key": "other-key", "chunk_id": "other-key"},
        {"source_document_instance_id": OTHER_CASE_ID},
        {"source_snapshot_id": "sha256:" + "f" * 64},
        {"document_name": "other.pdf"},
        {"document_id": "unexpected-document-id"},
        {"page": 2},
        {"chunk_ordinal": 9},
        {"original_blob_sha256": "e" * 64},
        {"page_text_sha256": "d" * 64},
        {"chunk_text_sha256": "c" * 64, "bound_text_sha256": "c" * 64},
    ],
)
def test_every_full_chain_binding_coordinate_is_cross_checked(tmp_path, changes):
    _, manifest, store = _make_graph(tmp_path)
    expected = store.load_evidence_binding(
        manifest.case_id,
        manifest.pages[0].chunk_snapshots[0].evidence_key,
    )
    assert expected is not None
    altered = _alter_binding(expected, **changes)
    real_load = store.load_evidence_binding

    def load(case_id, evidence_key):
        if evidence_key == expected.evidence_key:
            return altered
        return real_load(case_id, evidence_key)

    store.load_evidence_binding = load  # type: ignore[method-assign]
    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="binding"):
        _prepared(manifest, store)


def test_chunk_and_page_byte_length_checks_fail_closed(tmp_path, monkeypatch):
    _, manifest, store = _make_graph(tmp_path)
    real_read = store.read_blob
    chunk_sha = manifest.pages[0].chunk_snapshots[0].chunk_text_sha256

    def oversized(digest):
        value = real_read(digest)
        return value + b"x" if digest == chunk_sha else value

    monkeypatch.setattr(store, "read_blob", oversized)
    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="byte length"):
        _prepared(manifest, store)


def test_diagnostic_is_read_only_and_does_not_create_writer_lock(tmp_path):
    _, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    diagnostic = ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    )
    assert diagnostic.missing_count == 2
    assert not (tmp_path / "db").exists()
    assert collection.add_calls == []


def test_source_metadata_additions_are_exactly_the_approved_seven(tmp_path):
    _, manifest, store = _make_graph(tmp_path)
    row = _prepared(manifest, store)[0]
    assert {key for key in row.metadata if key.startswith("source_")} == {
        "source_evidence_binding_id",
        "source_snapshot_id",
        "source_document_instance_id",
        "source_chunk_sha256",
        "source_page_text_sha256",
        "source_original_blob_sha256",
        "source_binding_class",
    }

def test_diagnostic_classifies_exact_missing_and_conflicting_in_manifest_order(tmp_path):
    _, manifest, store = _make_graph(tmp_path)
    rows = _prepared(manifest, store)
    collection = FakeCollection()
    collection.rows[rows[0].row_id] = (rows[0].document, dict(rows[0].metadata), [1.0])
    conflicting = dict(rows[1].metadata)
    conflicting.pop("source_evidence_binding_id")
    collection.rows[rows[1].row_id] = (rows[1].document, conflicting, [2.0])

    diagnostic = ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    )

    assert [item.evidence_key for item in diagnostic.rows] == [row.row_id for row in rows]
    assert [item.state for item in diagnostic.rows] == [
        ingestion.SourceBoundIndexRowState.EXACT_PRESENT,
        ingestion.SourceBoundIndexRowState.CONFLICTING,
    ]
    assert diagnostic.exact_present_count == 1
    assert diagnostic.missing_count == 0
    assert diagnostic.conflicting_count == 1

    del collection.rows[rows[1].row_id]
    missing = ingestion.inspect_source_bound_index(manifest, store=store, collection=collection)
    assert missing.missing_count == 1
    assert missing.conflicting_count == 0


def test_diagnostic_rejects_malformed_or_unexpected_get_results(tmp_path):
    _, manifest, store = _make_graph(tmp_path)
    rows = _prepared(manifest, store)
    malformed = ScriptedCollection(
        [{"ids": [rows[0].row_id], "documents": [], "metadatas": []}]
    )
    with pytest.raises(ingestion.SourceEvidenceIngestionError):
        ingestion.inspect_source_bound_index(manifest, store=store, collection=malformed)

    unexpected = ScriptedCollection(
        [{"ids": ["unexpected"], "documents": ["x"], "metadatas": [{}]}]
    )
    with pytest.raises(ingestion.SourceEvidenceIngestionError):
        ingestion.inspect_source_bound_index(manifest, store=store, collection=unexpected)


def test_new_ingestion_uses_exact_blobs_embeddings_metadata_and_one_add(
    tmp_path, monkeypatch
):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    openai = FakeOpenAI()
    runtime = _runtime(tmp_path, collection, openai=openai)
    capture_calls = _install_capture_and_runtime(monkeypatch, manifest, runtime)

    result = ingestion.index_case_pdf_source_bound(
        pdf_path,
        case_id=CASE_ID,
        store=store,
        expected_original_sha256=manifest.original_blob_sha256,
    )

    assert result == 2
    assert len(capture_calls) == 1
    assert openai.embeddings.inputs == ["chunk one", "chunk two"]
    assert len(collection.add_calls) == 1
    call = collection.add_calls[0]
    assert call["ids"] == [
        manifest.pages[0].chunk_snapshots[0].chunk_id,
        manifest.pages[0].chunk_snapshots[1].chunk_id,
    ]
    assert call["documents"] == ["chunk one", "chunk two"]
    seven = {
        "source_evidence_binding_id",
        "source_snapshot_id",
        "source_document_instance_id",
        "source_chunk_sha256",
        "source_page_text_sha256",
        "source_original_blob_sha256",
        "source_binding_class",
    }
    for metadata in call["metadatas"]:
        assert seven.issubset(metadata)
        assert metadata["source_binding_class"] == "full_chain_bound"
        assert metadata["case_id"] == CASE_ID
        assert metadata["file"] == "evidence.pdf"
    assert ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    ).exact_present_count == 2


def test_document_hint_comes_from_rehashed_page_blobs(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    seen: list[str] = []
    real_classifier = ingestion.classify_evidence_source

    def capture_hint(**kwargs):
        seen.append(kwargs["document_hint"])
        return real_classifier(**kwargs)

    monkeypatch.setattr(ingestion, "classify_evidence_source", capture_hint)
    ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert seen == ["PAGE ONE\nPAGE TWO", "PAGE ONE\nPAGE TWO"]


def test_fully_exact_retry_returns_total_without_embedding_or_add(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    rows = _prepared(manifest, store)
    for row in rows:
        collection.rows[row.row_id] = (row.document, dict(row.metadata), [1.0])
    openai = FakeOpenAI()
    runtime = _runtime(tmp_path, collection, openai=openai)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert openai.embeddings.inputs == []
    assert collection.add_calls == []
    assert (tmp_path / "db" / ".legalrag-locks").is_dir()


def test_mixed_exact_missing_embeds_and_adds_only_missing(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    rows = _prepared(manifest, store)
    collection.rows[rows[0].row_id] = (rows[0].document, dict(rows[0].metadata), [1.0])
    openai = FakeOpenAI()
    runtime = _runtime(tmp_path, collection, openai=openai)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert openai.embeddings.inputs == [rows[1].document]
    assert collection.add_calls[0]["ids"] == [rows[1].row_id]


def test_ordinary_conflict_fails_before_embedding_and_lock(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    rows = _prepared(manifest, store)
    collection.rows[rows[0].row_id] = ("different", dict(rows[0].metadata), [1.0])
    openai = FakeOpenAI()
    runtime = _runtime(tmp_path, collection, openai=openai)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionConflictError):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert openai.embeddings.inputs == []
    assert collection.add_calls == []
    assert not (tmp_path / "db").exists()


def test_upload_hash_mismatch_fails_before_runtime_or_lock(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    monkeypatch.setattr(ingestion, "capture_pdf_source", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(
        ingestion,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="uploaded PDF bytes"):
        ingestion.index_case_pdf_source_bound(
            pdf_path,
            case_id=CASE_ID,
            store=store,
            expected_original_sha256="f" * 64,
        )
    assert not (tmp_path / "db").exists()


def test_zero_row_diagnostic_returns_without_runtime_collection_or_lock(tmp_path, monkeypatch):
    _, manifest, store = _make_graph(tmp_path, chunks=())
    monkeypatch.setattr(
        ingestion,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    diagnostic = ingestion.inspect_source_bound_index(manifest, store=store)
    assert diagnostic.total_rows == 0
    assert diagnostic.rows == ()
    assert not (tmp_path / "db").exists()


def test_zero_chunk_manifest_returns_before_runtime_and_lock(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path, chunks=())
    monkeypatch.setattr(ingestion, "capture_pdf_source", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(
        ingestion,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 0
    assert not (tmp_path / "db").exists()


def test_embedding_failure_occurs_before_lock_and_write(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection, openai=FakeOpenAI(fail_at=2))
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="Embedding creation"):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert collection.add_calls == []
    assert not (tmp_path / "db").exists()


def test_authoritative_preflight_detects_initially_exact_row_deleted_under_lock(
    tmp_path, monkeypatch
):
    pdf_path, manifest, store = _make_graph(tmp_path)
    rows = _prepared(manifest, store)
    exact = _exact_result(rows)
    missing = {"ids": [], "documents": [], "metadatas": []}
    collection = ScriptedCollection([exact, missing])
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionIncompleteError) as exc_info:
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert exc_info.value.diagnostic.missing_count == 2
    assert collection.add_calls == []


def test_batch_limit_rejects_before_add(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection, maximum=1)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="maximum batch size"):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert collection.add_calls == []


def test_add_exception_after_full_persistence_is_verified_as_success(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    collection.mode = "raise_after_all"
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert len(collection.add_calls) == 1


def test_partial_add_exception_is_recoverable_and_retry_completes(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    collection.mode = "partial_raise"
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionIncompleteError) as exc_info:
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert exc_info.value.diagnostic.exact_present_count == 1
    assert exc_info.value.diagnostic.missing_count == 1
    assert len(collection.rows) == 1

    collection.mode = "normal"
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert len(collection.rows) == 2
    assert len(collection.add_calls) == 2


def test_post_write_conflict_is_hard_failure(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    collection.mode = "conflict_after_add"
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    with pytest.raises(ingestion.SourceEvidenceIngestionConflictError):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert len(collection.add_calls) == 1


def test_lock_timeout_fails_without_add(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    real_lock = ingestion.ChromaWriterLock

    def short_lock(**kwargs):
        return real_lock(**kwargs, timeout_seconds=0.12, poll_interval_seconds=0.02)

    monkeypatch.setattr(ingestion, "ChromaWriterLock", short_lock)
    with ChromaWriterLock(
        db_path=runtime.db_path,
        tenant=runtime.tenant,
        database=runtime.database,
        collection_name=runtime.collection_name,
    ):
        with pytest.raises(ingestion.SourceEvidenceIngestionError, match="writer lock"):
            ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)
    assert collection.add_calls == []


def test_concurrent_identical_callers_are_serialized_and_both_succeed(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    def run():
        return ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results == [2, 2]
    assert len(collection.add_calls) == 1
    assert len(collection.rows) == 2


def test_concurrent_conflicting_callers_produce_one_winner_and_one_conflict(
    tmp_path, monkeypatch
):
    pdf_path, manifest, store = _make_graph(tmp_path)
    collection = FakeCollection()
    runtime = _runtime(tmp_path, collection)
    _install_capture_and_runtime(monkeypatch, manifest, runtime)

    def run(source_type):
        try:
            return ingestion.index_case_pdf_source_bound(
                pdf_path,
                case_id=CASE_ID,
                store=store,
                evidence_source_type=source_type,
            )
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run, "employer_record"),
            pool.submit(run, "independent_medical"),
        ]
        results = [future.result() for future in futures]
    assert sum(result == 2 for result in results) == 1
    assert sum(isinstance(result, ingestion.SourceEvidenceIngestionConflictError) for result in results) == 1
    assert len(collection.add_calls) == 1


def test_missing_or_mismatched_binding_fails_closed(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path)
    first_chunk = manifest.pages[0].chunk_snapshots[0]
    real_load = store.load_evidence_binding

    def missing(case_id, evidence_key):
        if evidence_key == first_chunk.evidence_key:
            return None
        return real_load(case_id, evidence_key)

    monkeypatch.setattr(store, "load_evidence_binding", missing)
    monkeypatch.setattr(ingestion, "capture_pdf_source", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(
        ingestion,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="binding"):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)


def test_invalid_utf8_chunk_fails_before_runtime(tmp_path, monkeypatch):
    pdf_path, manifest, store = _make_graph(tmp_path, chunks=(b"\xff\xfe",))
    monkeypatch.setattr(ingestion, "capture_pdf_source", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(
        ingestion,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    with pytest.raises(ingestion.SourceEvidenceIngestionError, match="valid UTF-8"):
        ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store)


def test_document_upload_default_passes_exact_upload_digest(tmp_path, monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_index(path, *, case_id, expected_original_sha256):
        calls.append(
            {
                "path": Path(path),
                "case_id": case_id,
                "expected_original_sha256": expected_original_sha256,
            }
        )
        return 3

    monkeypatch.setattr(ingestion, "index_case_pdf_source_bound", fake_index)
    content = b"%PDF-1.7\nsource-bound upload\n"
    result = document_upload.upload_case_pdf(
        filename="ET1.pdf",
        content=content,
        case_id=" case-123 ",
        docs_folder=tmp_path,
    )
    assert result.chunks_indexed == 3
    assert calls == [
        {
            "path": tmp_path / "ET1.pdf",
            "case_id": "case-123",
            "expected_original_sha256": sha256_bytes(content),
        }
    ]


def test_injected_upload_indexer_receives_only_frozen_arguments(tmp_path):
    calls: list[tuple[Path, str]] = []

    def injected(path, *, case_id):
        calls.append((Path(path), case_id))
        return 1

    document_upload.upload_case_pdf(
        filename="ET1.pdf",
        content=b"%PDF-1.7\nfixture\n",
        case_id="case-123",
        docs_folder=tmp_path,
        indexer=injected,
    )
    assert calls == [(tmp_path / "ET1.pdf", "case-123")]




def test_default_upload_failure_removes_new_working_pdf_but_retains_immutable_marker(
    tmp_path, monkeypatch
):
    marker_store = SourceEvidenceStore(tmp_path / "store-v1")
    marker_sha = marker_store.put_blob(b"immutable-capture-remains")

    def fail_after_capture(*args, **kwargs):
        raise ingestion.SourceEvidenceIngestionIncompleteError(
            "controlled incomplete",
            ingestion.SourceBoundIndexDiagnostic(
                case_id=CASE_ID,
                source_snapshot_id="sha256:" + "a" * 64,
                total_rows=1,
                exact_present_count=0,
                missing_count=1,
                conflicting_count=0,
                rows=(
                    ingestion.SourceBoundIndexRowDiagnostic(
                        evidence_key="row",
                        state=ingestion.SourceBoundIndexRowState.MISSING,
                        reason="requested Chroma row is absent",
                    ),
                ),
            ),
        )

    monkeypatch.setattr(ingestion, "index_case_pdf_source_bound", fail_after_capture)
    working = tmp_path / "docs" / "ET1.pdf"
    with pytest.raises(document_upload.DocumentUploadError):
        document_upload.upload_case_pdf(
            filename="ET1.pdf",
            content=b"%PDF-1.7\nfixture\n",
            case_id="case-123",
            docs_folder=working.parent,
        )
    assert not working.exists()
    assert marker_store.read_blob(marker_sha) == b"immutable-capture-remains"


def test_default_upload_failure_retains_identical_preexisting_working_pdf(
    tmp_path, monkeypatch
):
    content = b"%PDF-1.7\nfixture\n"
    working = tmp_path / "ET1.pdf"
    working.write_bytes(content)

    def fail(*args, **kwargs):
        raise ingestion.SourceEvidenceIngestionError("controlled")

    monkeypatch.setattr(ingestion, "index_case_pdf_source_bound", fail)
    with pytest.raises(document_upload.DocumentUploadError):
        document_upload.upload_case_pdf(
            filename="ET1.pdf",
            content=content,
            case_id="case-123",
            docs_folder=tmp_path,
        )
    assert working.read_bytes() == content


def test_default_zero_chunk_upload_removes_new_working_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion, "index_case_pdf_source_bound", lambda *args, **kwargs: 0)
    working = tmp_path / "ET1.pdf"
    with pytest.raises(document_upload.DocumentUploadError, match="No searchable text"):
        document_upload.upload_case_pdf(
            filename="ET1.pdf",
            content=b"%PDF-1.7\nblank\n",
            case_id="case-123",
            docs_folder=tmp_path,
        )
    assert not working.exists()

def test_m4_modules_are_import_safe_and_avoid_prohibited_write_apis():
    source = Path(inspect.getsourcefile(ingestion)).read_text(encoding="utf-8")
    lock_source = Path(
        inspect.getsourcefile(__import__("source_evidence.chroma_lock", fromlist=["*"]))
    ).read_text(encoding="utf-8")
    for forbidden in (
        "collection.update",
        "collection.upsert",
        "collection.delete",
        ".conditional(",
        "index_documents",
        "from ocr",
        "import ocr",
        "streamlit",
        "legal_analysis",
    ):
        assert forbidden not in source
    assert source.count("runtime.collection.add(") == 1
    assert "chromadb" not in lock_source
    assert "openai" not in lock_source.casefold()

    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import source_evidence.ingestion; "
                "assert 'config' not in sys.modules; "
                "assert 'chromadb' not in sys.modules; "
                "assert 'openai' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert completed.returncode == 0, completed.stderr


def _real_chroma_add_worker(
    db_path: str,
    ids,
    embeddings,
    documents,
    metadatas,
    before_add,
    after_add,
) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(name="legal_documents")
    before_add.set()
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    after_add.set()
    time.sleep(30)


def _real_lock_before_add_worker(db_path: str, ready) -> None:
    lock = ChromaWriterLock(
        db_path=db_path,
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
        timeout_seconds=5.0,
        poll_interval_seconds=0.02,
    )
    with lock:
        ready.set()
        time.sleep(30)


def _require_chroma_159():
    chromadb = pytest.importorskip("chromadb", reason="governed chromadb 1.5.9 unavailable")
    assert chromadb.__version__ == "1.5.9"
    return chromadb


def test_real_chroma_159_partial_exact_missing_reopens_and_completes(tmp_path, monkeypatch):
    chromadb = _require_chroma_159()
    pdf_path, manifest, store = _make_graph(tmp_path)
    rows = _prepared(manifest, store)
    db_path = tmp_path / "real-db"

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(name="legal_documents")
    collection.add(
        ids=[rows[0].row_id],
        embeddings=[[1.0, 0.0, 0.0]],
        documents=[rows[0].document],
        metadatas=[rows[0].metadata],
    )
    client.close()

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name="legal_documents")
    runtime = ingestion._Runtime(
        chroma_client=client,
        collection=collection,
        openai_client=FakeOpenAI(),
        embedding_model="text-embedding-3-small",
        db_path=db_path.resolve(strict=False),
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
    )
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    ).exact_present_count == 2
    client.close()


def test_real_chroma_159_process_death_before_add_releases_lock_and_retry_succeeds(
    tmp_path, monkeypatch
):
    chromadb = _require_chroma_159()
    import multiprocessing as mp

    pdf_path, manifest, store = _make_graph(tmp_path)
    db_path = tmp_path / "real-db"
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(name="legal_documents")
    client.close()

    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    process = ctx.Process(target=_real_lock_before_add_worker, args=(str(db_path), ready))
    process.start()
    assert ready.wait(10)
    process.terminate()
    process.join(10)

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name="legal_documents")
    runtime = ingestion._Runtime(
        chroma_client=client,
        collection=collection,
        openai_client=FakeOpenAI(),
        embedding_model="text-embedding-3-small",
        db_path=db_path.resolve(strict=False),
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
    )
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    client.close()


def test_real_chroma_159_process_death_after_add_before_verify_is_idempotent(
    tmp_path, monkeypatch
):
    chromadb = _require_chroma_159()
    import multiprocessing as mp

    pdf_path, manifest, store = _make_graph(tmp_path)
    rows = _prepared(manifest, store)
    db_path = tmp_path / "real-db"
    client = chromadb.PersistentClient(path=str(db_path))
    client.get_or_create_collection(name="legal_documents")
    client.close()

    ctx = mp.get_context("spawn")
    before_add = ctx.Event()
    after_add = ctx.Event()
    process = ctx.Process(
        target=_real_chroma_add_worker,
        args=(
            str(db_path),
            [row.row_id for row in rows],
            [[1.0, 0.0, 0.0] for _ in rows],
            [row.document for row in rows],
            [row.metadata for row in rows],
            before_add,
            after_add,
        ),
    )
    process.start()
    assert before_add.wait(10)
    assert after_add.wait(20)
    process.terminate()
    process.join(10)

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name="legal_documents")
    runtime = ingestion._Runtime(
        chroma_client=client,
        collection=collection,
        openai_client=FakeOpenAI(),
        embedding_model="text-embedding-3-small",
        db_path=db_path.resolve(strict=False),
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
    )
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == 2
    assert len(runtime.openai_client.embeddings.inputs) == 0
    client.close()


def test_real_chroma_159_process_termination_during_large_add_is_recoverable(
    tmp_path, monkeypatch
):
    chromadb = _require_chroma_159()
    import multiprocessing as mp

    chunks = tuple(f"chunk {index:04d}".encode() for index in range(400))
    pdf_path, manifest, store = _make_graph(tmp_path, chunks=chunks)
    rows = _prepared(manifest, store)
    db_path = tmp_path / "real-db"
    client = chromadb.PersistentClient(path=str(db_path))
    client.get_or_create_collection(name="legal_documents")
    client.close()

    ctx = mp.get_context("spawn")
    before_add = ctx.Event()
    after_add = ctx.Event()
    process = ctx.Process(
        target=_real_chroma_add_worker,
        args=(
            str(db_path),
            [row.row_id for row in rows],
            [[float(index), 0.0, 1.0] for index, _ in enumerate(rows)],
            [row.document for row in rows],
            [row.metadata for row in rows],
            before_add,
            after_add,
        ),
    )
    process.start()
    assert before_add.wait(10)
    time.sleep(0.01)
    if process.is_alive():
        process.terminate()
    process.join(20)

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name="legal_documents")
    diagnostic = ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    )
    assert diagnostic.conflicting_count == 0
    assert diagnostic.exact_present_count + diagnostic.missing_count == len(rows)

    runtime = ingestion._Runtime(
        chroma_client=client,
        collection=collection,
        openai_client=FakeOpenAI(),
        embedding_model="text-embedding-3-small",
        db_path=db_path.resolve(strict=False),
        tenant="default_tenant",
        database="default_database",
        collection_name="legal_documents",
    )
    _install_capture_and_runtime(monkeypatch, manifest, runtime)
    assert ingestion.index_case_pdf_source_bound(pdf_path, case_id=CASE_ID, store=store) == len(rows)
    assert ingestion.inspect_source_bound_index(
        manifest,
        store=store,
        collection=collection,
    ).exact_present_count == len(rows)
    client.close()


def test_load_runtime_uses_lazy_config_accessors(monkeypatch):
    import sys
    import types

    fake_client = FakeChromaClient()
    fake_collection = FakeCollection()
    fake_openai = FakeOpenAI()
    calls = []
    fake_config = types.ModuleType("config")

    def get_chroma_client():
        calls.append("client")
        return fake_client

    def get_collection():
        calls.append("collection")
        return fake_collection

    fake_config.get_chroma_client = get_chroma_client
    fake_config.get_collection = get_collection
    fake_config.openai_client = fake_openai
    monkeypatch.setitem(sys.modules, "config", fake_config)

    runtime = ingestion._load_runtime()

    assert calls == ["client", "collection"]
    assert runtime.chroma_client is fake_client
    assert runtime.collection is fake_collection
    assert runtime.openai_client is fake_openai
    assert runtime.collection_name == "legal_documents"
