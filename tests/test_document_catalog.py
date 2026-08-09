from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from document_catalog import (
    DocumentCatalogError,
    list_case_documents,
)
from source_evidence.store import SourceEvidenceStoreError


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOC_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DOC_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _page(method: str, chunks: int):
    return SimpleNamespace(
        extraction_method=SimpleNamespace(value=method),
        chunk_snapshots=tuple(object() for _ in range(chunks)),
    )


def _manifest(
    document_id: str,
    filename: str,
    *,
    case_id: str = CASE_ID,
    pages=(_page("pypdf_text", 2),),
):
    return SimpleNamespace(
        case_id=case_id,
        source_document_instance_id=document_id,
        original_filename=filename,
        media_type="application/pdf",
        original_blob_sha256="a" * 64,
        original_byte_length=12345,
        source_snapshot_id="sha256:" + ("b" * 64),
        extraction_profile=SimpleNamespace(
            profile_id="pdf-page-extraction/1.0"
        ),
        chunking_profile=SimpleNamespace(
            profile_id="recursive-character-text-splitter/1.0"
        ),
        pages=tuple(pages),
    )


class FakeStore:
    def __init__(self, root: Path, manifests: dict[str, object]) -> None:
        self.root = root
        self.manifests = manifests
        self.calls: list[tuple[str, str]] = []

    def load_document_manifest(self, case_id: str, document_id: str):
        self.calls.append((case_id, document_id))
        value = self.manifests[document_id]
        if isinstance(value, Exception):
            raise value
        return value


def _make_document_dirs(root: Path, *document_ids: str) -> Path:
    documents = root / "cases" / CASE_ID / "documents"
    for document_id in document_ids:
        (documents / document_id).mkdir(parents=True)
    return documents


def test_missing_case_namespace_returns_empty_without_store_load(tmp_path: Path):
    store = FakeStore(tmp_path / "store-v1", {})
    assert list_case_documents(CASE_ID, store=store) == ()
    assert store.calls == []


def test_catalog_is_case_bound_deterministic_and_projects_exact_fields(tmp_path: Path):
    root = tmp_path / "store-v1"
    _make_document_dirs(root, DOC_B, DOC_A)
    store = FakeStore(
        root,
        {
            DOC_A: _manifest(
                DOC_A,
                "Zulu.pdf",
                pages=(
                    _page("pypdf_text", 2),
                    _page("page_ocr", 1),
                ),
            ),
            DOC_B: _manifest(
                DOC_B,
                "alpha.pdf",
                pages=(_page("pypdf_text", 3),),
            ),
        },
    )

    result = list_case_documents(CASE_ID, store=store)

    assert [item.source_document_instance_id for item in result] == [DOC_B, DOC_A]
    assert [item.original_filename for item in result] == ["alpha.pdf", "Zulu.pdf"]
    assert result[0].page_count == 1
    assert result[0].evidence_chunk_count == 3
    assert result[1].page_count == 2
    assert result[1].evidence_chunk_count == 3
    assert result[1].extraction_methods == ("pypdf_text", "page_ocr")
    assert result[1].original_blob_sha256 == "a" * 64
    assert result[1].source_snapshot_id == "sha256:" + ("b" * 64)
    assert result[1].extraction_profile_id == "pdf-page-extraction/1.0"
    assert result[1].chunking_profile_id == "recursive-character-text-splitter/1.0"
    assert sorted(store.calls) == sorted([(CASE_ID, DOC_A), (CASE_ID, DOC_B)])


def test_same_filename_is_stably_tied_by_document_identity(tmp_path: Path):
    root = tmp_path / "store-v1"
    _make_document_dirs(root, DOC_B, DOC_A)
    store = FakeStore(
        root,
        {
            DOC_A: _manifest(DOC_A, "same.pdf"),
            DOC_B: _manifest(DOC_B, "same.pdf"),
        },
    )
    result = list_case_documents(CASE_ID, store=store)
    assert [item.source_document_instance_id for item in result] == [DOC_A, DOC_B]


@pytest.mark.parametrize(
    "bad_case",
    [
        "",
        "not-a-uuid",
        "11111111-1111-4111-8111-111111111111 ",
        "11111111-1111-4111-8111-11111111111A",
    ],
)
def test_invalid_case_identity_fails_closed(tmp_path: Path, bad_case: str):
    with pytest.raises(DocumentCatalogError):
        list_case_documents(bad_case, store=FakeStore(tmp_path / "store-v1", {}))


def test_unexpected_non_directory_entry_fails_closed(tmp_path: Path):
    root = tmp_path / "store-v1"
    documents = _make_document_dirs(root, DOC_A)
    (documents / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    store = FakeStore(root, {DOC_A: _manifest(DOC_A, "A.pdf")})
    with pytest.raises(DocumentCatalogError):
        list_case_documents(CASE_ID, store=store)


def test_manifest_loader_failure_is_mapped_to_catalog_error(tmp_path: Path):
    root = tmp_path / "store-v1"
    _make_document_dirs(root, DOC_A)
    store = FakeStore(
        root,
        {DOC_A: SourceEvidenceStoreError("controlled integrity failure")},
    )
    with pytest.raises(DocumentCatalogError):
        list_case_documents(CASE_ID, store=store)


def test_manifest_identity_mismatch_fails_closed(tmp_path: Path):
    root = tmp_path / "store-v1"
    _make_document_dirs(root, DOC_A)
    store = FakeStore(
        root,
        {
            DOC_A: _manifest(
                DOC_A,
                "A.pdf",
                case_id="22222222-2222-4222-8222-222222222222",
            )
        },
    )
    with pytest.raises(DocumentCatalogError):
        list_case_documents(CASE_ID, store=store)


def test_symlinked_document_directory_is_rejected_when_supported(tmp_path: Path):
    root = tmp_path / "store-v1"
    documents = root / "cases" / CASE_ID / "documents"
    documents.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = documents / DOC_A
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    store = FakeStore(root, {DOC_A: _manifest(DOC_A, "A.pdf")})
    with pytest.raises(DocumentCatalogError):
        list_case_documents(CASE_ID, store=store)
