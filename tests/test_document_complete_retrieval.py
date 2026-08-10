from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence_retrieval.document_complete import (
    DocumentCompleteRetrievalError,
    inspect_document_complete,
)
from source_evidence.identity import derive_sha256_id, derive_source_document_instance_id
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

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "22345678-1234-4234-8234-123456789abc"
OTHER_DOCUMENT_ID = "32345678-1234-4234-8234-123456789abc"
FILENAME = "Appendix H6.pdf"


def _profile() -> ExtractionProfile:
    return ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version="6.14.2",
        pdf2image_package_version="1.17.0",
        pytesseract_package_version="0.3.13",
        tesseract_engine_version="5.5.0",
        poppler_version="25.07.0",
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
        evidence_binding_id=derive_sha256_id(
            evidence_binding_identity_payload_to_dict(provisional)
        ),
    )


def _publish_fixture(
    tmp_path: Path,
    *,
    page_specs: tuple[tuple[str, ExtractionMethod, tuple[str, ...]], ...] | None = None,
) -> tuple[SourceEvidenceStore, SourceDocumentManifest, tuple[EvidenceBinding, ...]]:
    if page_specs is None:
        page_specs = (
            (
                "Page one full text with Alpha and Beta.",
                ExtractionMethod.PYPDF_TEXT,
                ("Alpha evidence.", "Beta evidence."),
            ),
            (
                "Page two OCR text with Gamma.",
                ExtractionMethod.PAGE_OCR,
                ("Gamma evidence.",),
            ),
        )

    store = SourceEvidenceStore(tmp_path / "store-v1")
    original = b"%PDF-1.7 governed source bytes not read by U8B"
    original_sha = store.put_blob(original)
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=FILENAME,
        original_blob_sha256=original_sha,
    )

    pages: list[SourcePageSnapshot] = []
    chunk_bind_specs: list[tuple[SourcePageSnapshot, SourceChunkSnapshot]] = []

    for page_number, (page_text, extraction_method, chunks) in enumerate(page_specs, start=1):
        page_bytes = page_text.encode("utf-8")
        page_sha = store.put_blob(page_bytes)
        chunk_snapshots: list[SourceChunkSnapshot] = []

        for ordinal, chunk_text in enumerate(chunks):
            chunk_bytes = chunk_text.encode("utf-8")
            chunk_sha = store.put_blob(chunk_bytes)
            evidence_key = f"{CASE_ID}::{Path(FILENAME).stem}::p{page_number}::c{ordinal}"
            chunk_snapshots.append(
                SourceChunkSnapshot(
                    page_number=page_number,
                    chunk_ordinal=ordinal,
                    chunk_id=evidence_key,
                    evidence_key=evidence_key,
                    chunk_text_sha256=chunk_sha,
                    chunk_text_byte_length=len(chunk_bytes),
                )
            )

        page = SourcePageSnapshot(
            page_number=page_number,
            extraction_method=extraction_method,
            page_text_sha256=page_sha,
            page_text_byte_length=len(page_bytes),
            chunk_snapshots=tuple(chunk_snapshots),
        )
        pages.append(page)
        chunk_bind_specs.extend((page, chunk) for chunk in chunk_snapshots)

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
        pages=tuple(pages),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    manifest = _final_manifest(provisional_manifest)
    store.publish_document_manifest(manifest)

    bindings: list[EvidenceBinding] = []
    for page, chunk in chunk_bind_specs:
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
            page=page.page_number,
            chunk_ordinal=chunk.chunk_ordinal,
            original_blob_sha256=original_sha,
            page_text_sha256=page.page_text_sha256,
            chunk_text_sha256=chunk.chunk_text_sha256,
            bound_text_sha256=chunk.chunk_text_sha256,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
            evidence_binding_id="sha256:" + "0" * 64,
        )
        binding = _final_binding(provisional_binding)
        store.publish_evidence_binding(binding)
        bindings.append(binding)

    return store, manifest, tuple(bindings)


class _DelegatingStore:
    def __init__(
        self,
        base: SourceEvidenceStore,
        *,
        manifest: SourceDocumentManifest | None = None,
        binding_overrides: dict[str, EvidenceBinding | None] | None = None,
        blob_overrides: dict[str, bytes | Exception] | None = None,
    ) -> None:
        self.base = base
        self.manifest = manifest
        self.binding_overrides = binding_overrides or {}
        self.blob_overrides = blob_overrides or {}
        self.read_digests: list[str] = []

    def load_document_manifest(self, case_id: str, document_id: str) -> SourceDocumentManifest:
        if self.manifest is not None:
            return self.manifest
        return self.base.load_document_manifest(case_id, document_id)

    def load_evidence_binding(self, case_id: str, evidence_key: str) -> EvidenceBinding | None:
        if evidence_key in self.binding_overrides:
            return self.binding_overrides[evidence_key]
        return self.base.load_evidence_binding(case_id, evidence_key)

    def read_blob(self, digest: str) -> bytes:
        self.read_digests.append(digest)
        if digest in self.blob_overrides:
            value = self.blob_overrides[digest]
            if isinstance(value, Exception):
                raise value
            return value
        return self.base.read_blob(digest)


def _alter_binding(binding: EvidenceBinding, **changes: Any) -> EvidenceBinding:
    provisional = replace(
        binding,
        evidence_binding_id="sha256:" + "0" * 64,
        **changes,
    )
    return _final_binding(provisional)


def test_complete_retrieval_returns_every_page_and_chunk_in_manifest_order(tmp_path):
    store, manifest, bindings = _publish_fixture(tmp_path)

    result = inspect_document_complete(
        case_id=CASE_ID,
        source_document_instance_id=manifest.source_document_instance_id,
        store=store,
    )

    assert result.case_id == CASE_ID
    assert result.source_document_instance_id == manifest.source_document_instance_id
    assert result.source_snapshot_id == manifest.source_snapshot_id
    assert result.original_filename == FILENAME
    assert result.original_blob_sha256 == manifest.original_blob_sha256
    assert result.page_count == 2
    assert result.evidence_chunk_count == 3
    assert [page.page_number for page in result.pages] == [1, 2]
    assert [page.extraction_method for page in result.pages] == [
        ExtractionMethod.PYPDF_TEXT,
        ExtractionMethod.PAGE_OCR,
    ]
    assert [chunk.evidence_key for page in result.pages for chunk in page.chunks] == [
        binding.evidence_key for binding in bindings
    ]
    assert [[chunk.chunk_ordinal for chunk in page.chunks] for page in result.pages] == [
        [0, 1],
        [0],
    ]
    assert [page.text for page in result.pages] == [
        "Page one full text with Alpha and Beta.",
        "Page two OCR text with Gamma.",
    ]
    assert [chunk.text for page in result.pages for chunk in page.chunks] == [
        "Alpha evidence.",
        "Beta evidence.",
        "Gamma evidence.",
    ]


def test_repeated_complete_retrieval_is_deterministically_equal(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    kwargs = {
        "case_id": CASE_ID,
        "source_document_instance_id": manifest.source_document_instance_id,
        "store": store,
    }
    assert inspect_document_complete(**kwargs) == inspect_document_complete(**kwargs)


def test_page_with_zero_chunks_is_preserved_as_governed_page(tmp_path):
    store, manifest, _bindings = _publish_fixture(
        tmp_path,
        page_specs=(
            ("Only structural page text.", ExtractionMethod.PYPDF_TEXT, ()),
            ("Evidence page.", ExtractionMethod.PYPDF_TEXT, ("One item.",)),
        ),
    )
    result = inspect_document_complete(
        case_id=CASE_ID,
        source_document_instance_id=manifest.source_document_instance_id,
        store=store,
    )
    assert result.page_count == 2
    assert result.evidence_chunk_count == 1
    assert result.pages[0].text == "Only structural page text."
    assert result.pages[0].chunks == ()


def test_original_pdf_blob_is_not_read_during_document_complete_inspection(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    wrapped = _DelegatingStore(store)
    inspect_document_complete(
        case_id=CASE_ID,
        source_document_instance_id=manifest.source_document_instance_id,
        store=wrapped,  # type: ignore[arg-type]
    )
    assert manifest.original_blob_sha256 not in wrapped.read_digests
    expected = [
        item
        for page in manifest.pages
        for item in (
            page.page_text_sha256,
            *(chunk.chunk_text_sha256 for chunk in page.chunk_snapshots),
        )
    ]
    assert wrapped.read_digests == expected


def test_missing_evidence_binding_fails_closed(tmp_path):
    store, manifest, bindings = _publish_fixture(tmp_path)
    wrapped = _DelegatingStore(
        store,
        binding_overrides={bindings[1].evidence_key: None},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="missing EvidenceBinding"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"case_id": OTHER_CASE_ID}, "case_id"),
        ({"source_document_instance_id": OTHER_DOCUMENT_ID}, "source_document_instance_id"),
        ({"source_snapshot_id": "sha256:" + "1" * 64}, "source_snapshot_id"),
        ({"document_name": "Different.pdf"}, "document_name"),
        ({"page": 9}, "page"),
        ({"chunk_ordinal": 9}, "chunk_ordinal"),
        ({"original_blob_sha256": "1" * 64}, "original_blob_sha256"),
        ({"page_text_sha256": "2" * 64}, "page_text_sha256"),
        ({"chunk_text_sha256": "3" * 64, "bound_text_sha256": "3" * 64}, "chunk_text_sha256"),
        ({"extraction_profile_id": "other-profile"}, "extraction_profile_id"),
        ({"chunking_profile_id": "other-profile"}, "chunking_profile_id"),
    ],
)
def test_binding_coordinate_mismatch_fails_closed(tmp_path, changes, match):
    store, manifest, bindings = _publish_fixture(tmp_path)
    altered = _alter_binding(bindings[0], **changes)
    wrapped = _DelegatingStore(
        store,
        binding_overrides={bindings[0].evidence_key: altered},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match=match):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_non_full_chain_binding_fails_closed(tmp_path):
    store, manifest, bindings = _publish_fixture(tmp_path)
    altered = _alter_binding(
        bindings[0],
        binding_class=BindingClass.ANALYTICAL_TEXT_BOUND,
        bound_text_role=BoundTextRole.ANALYTICAL_SUMMARY,
    )
    wrapped = _DelegatingStore(
        store,
        binding_overrides={bindings[0].evidence_key: altered},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="not FULL_CHAIN_BOUND"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_invalid_binding_identity_fails_closed(tmp_path):
    store, manifest, bindings = _publish_fixture(tmp_path)
    altered = replace(bindings[0], evidence_binding_id="sha256:" + "f" * 64)
    wrapped = _DelegatingStore(
        store,
        binding_overrides={bindings[0].evidence_key: altered},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="immutable source-evidence chain"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_page_blob_length_mismatch_fails_closed(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    page = manifest.pages[0]
    wrapped = _DelegatingStore(
        store,
        blob_overrides={page.page_text_sha256: b"short"},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="byte length"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_chunk_blob_length_mismatch_fails_closed(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    chunk = manifest.pages[0].chunk_snapshots[0]
    wrapped = _DelegatingStore(
        store,
        blob_overrides={chunk.chunk_text_sha256: b"x"},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="byte length"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_non_utf8_chunk_blob_fails_closed(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    chunk = manifest.pages[0].chunk_snapshots[0]
    bad = b"\xff" * chunk.chunk_text_byte_length
    wrapped = _DelegatingStore(
        store,
        blob_overrides={chunk.chunk_text_sha256: bad},
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="strict UTF-8"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


def test_store_blob_verification_failure_is_wrapped_fail_closed(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    chunk = manifest.pages[0].chunk_snapshots[0]
    wrapped = _DelegatingStore(
        store,
        blob_overrides={
            chunk.chunk_text_sha256: SourceEvidenceStoreError("corrupt immutable blob")
        },
    )
    with pytest.raises(DocumentCompleteRetrievalError, match="immutable source-evidence chain"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("case_id", "document_id"),
    [
        ("not-a-uuid", OTHER_DOCUMENT_ID),
        (CASE_ID, "not-a-uuid"),
        (CASE_ID.upper(), OTHER_DOCUMENT_ID),
    ],
)
def test_invalid_or_noncanonical_uuid_inputs_fail_closed(tmp_path, case_id, document_id):
    store = SourceEvidenceStore(tmp_path / "unused")
    with pytest.raises(DocumentCompleteRetrievalError, match="canonical case and document UUIDs"):
        inspect_document_complete(
            case_id=case_id,
            source_document_instance_id=document_id,
            store=store,
        )



def test_invalid_manifest_order_is_rejected_by_frozen_manifest_validation(tmp_path):
    store, manifest, _bindings = _publish_fixture(tmp_path)
    provisional = replace(
        manifest,
        pages=(manifest.pages[1], manifest.pages[0]),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    invalid_manifest = _final_manifest(provisional)
    wrapped = _DelegatingStore(store, manifest=invalid_manifest)
    with pytest.raises(DocumentCompleteRetrievalError, match="immutable source-evidence chain"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=manifest.source_document_instance_id,
            store=wrapped,  # type: ignore[arg-type]
        )

def test_manifest_load_failure_is_wrapped_fail_closed(tmp_path):
    store = SourceEvidenceStore(tmp_path / "missing-store")
    with pytest.raises(DocumentCompleteRetrievalError, match="immutable source-evidence chain"):
        inspect_document_complete(
            case_id=CASE_ID,
            source_document_instance_id=OTHER_DOCUMENT_ID,
            store=store,
        )
