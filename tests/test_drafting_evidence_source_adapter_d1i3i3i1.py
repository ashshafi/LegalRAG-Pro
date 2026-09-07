from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import drafting_evidence_source_adapter as module


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"

KEY_A = CASE_ID + "__Document_A_1_0"
KEY_B = CASE_ID + "__Document_B_2_0"


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def fixture_store(
    *,
    evidence_key: str = KEY_A,
    text: str = "Exact immutable evidence text.",
):
    page_bytes = (
        "Whole immutable page containing " + text
    ).encode("utf-8")

    chunk_bytes = text.encode("utf-8")

    page_sha = digest(page_bytes)
    chunk_sha = digest(chunk_bytes)

    source_id = "11111111-1111-4111-8111-111111111111"

    binding = SimpleNamespace(
        case_id=CASE_ID,
        evidence_key=evidence_key,
        chunk_id=evidence_key,
        binding_class="FULL_CHAIN_BOUND",
        bound_text_role="chunk_text",
        source_document_instance_id=source_id,
        source_snapshot_id="sha256:" + ("b" * 64),
        document_name="Document_A.pdf",
        document_id=None,
        page=1,
        chunk_ordinal=0,
        original_blob_sha256="a" * 64,
        page_text_sha256=page_sha,
        chunk_text_sha256=chunk_sha,
        bound_text_sha256=chunk_sha,
        extraction_profile_id="extract-v1",
        chunking_profile_id="chunk-v1",
        evidence_binding_id="sha256:" + ("c" * 64),
    )

    chunk = SimpleNamespace(
        evidence_key=evidence_key,
        chunk_id=evidence_key,
        chunk_ordinal=0,
        chunk_text_sha256=chunk_sha,
        chunk_text_byte_length=len(chunk_bytes),
    )

    page = SimpleNamespace(
        page_number=1,
        page_text_sha256=page_sha,
        page_text_byte_length=len(page_bytes),
        chunk_snapshots=(chunk,),
    )

    manifest = SimpleNamespace(
        source_document_instance_id=source_id,
        original_blob_sha256="a" * 64,
        original_filename="Document_A.pdf",
        pages=(page,),
    )

    class FakeStore:
        def load_evidence_binding(self, case_id, key):
            if case_id == CASE_ID and key == evidence_key:
                return binding
            return None

        def load_document_manifest(
            self,
            case_id,
            requested_source_id,
        ):
            assert case_id == CASE_ID
            assert requested_source_id == source_id
            return manifest

        def read_blob(self, requested_sha):
            if requested_sha == page_sha:
                return page_bytes
            if requested_sha == chunk_sha:
                return chunk_bytes
            raise AssertionError(
                "unexpected blob request"
            )

    return (
        FakeStore(),
        binding,
        manifest,
        page,
        chunk,
    )


def receipt(keys=(KEY_A, KEY_B)):
    return SimpleNamespace(
        answer_scope_evidence_keys=tuple(keys),
        relied_evidence_keys=(KEY_A,),
    )


def element():
    return SimpleNamespace(
        supporting_evidence_keys=(KEY_A,),
        adverse_evidence_keys=(KEY_B,),
        corroborative_evidence_keys=(),
        conflicting_evidence_keys=(
            CASE_ID + "__Outside_1_0",
        ),
    )


def test_safe_set_is_r68_intersection_with_element() -> None:
    keys = module.generation_evidence_keys(
        retrieval_receipt=receipt(),
        element=element(),
    )

    assert keys == tuple(
        sorted((KEY_A, KEY_B))
    )


def test_relied_keys_do_not_shrink_answer_scope() -> None:
    keys = module.generation_evidence_keys(
        retrieval_receipt=receipt(),
        element=element(),
    )

    assert KEY_A in keys
    assert KEY_B in keys


def test_no_scope_intersection_fails_closed() -> None:
    unrelated = SimpleNamespace(
        supporting_evidence_keys=(
            CASE_ID + "__Other_1_0",
        ),
        adverse_evidence_keys=(),
        corroborative_evidence_keys=(),
        conflicting_evidence_keys=(),
    )

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="no evidence intersection",
    ):
        module.generation_evidence_keys(
            retrieval_receipt=receipt(),
            element=unrelated,
        )


def test_exact_direct_source_resolution() -> None:
    store, binding, _, _, _ = fixture_store()

    row = module.resolve_exact_evidence_row(
        case_id=CASE_ID,
        evidence_key=KEY_A,
        store=store,
    )

    assert row.case_id == CASE_ID
    assert row.evidence_key == KEY_A
    assert row.evidence_binding_id == binding.evidence_binding_id
    assert row.source_document_instance_id == (
        binding.source_document_instance_id
    )
    assert row.document_name == "Document_A.pdf"
    assert row.page == 1
    assert row.chunk_ordinal == 0
    assert row.exact_bound_text == (
        "Exact immutable evidence text."
    )


def test_missing_binding_fails_closed() -> None:
    class EmptyStore:
        def load_evidence_binding(
            self,
            case_id,
            evidence_key,
        ):
            return None

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="binding is absent",
    ):
        module.resolve_exact_evidence_row(
            case_id=CASE_ID,
            evidence_key=KEY_A,
            store=EmptyStore(),
        )


def test_chunk_sha_mismatch_fails_closed() -> None:
    store, binding, _, _, _ = fixture_store()

    binding.chunk_text_sha256 = "9" * 64

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="chunk-text SHA",
    ):
        module.resolve_exact_evidence_row(
            case_id=CASE_ID,
            evidence_key=KEY_A,
            store=store,
        )


def test_chunk_identity_mismatch_fails_closed() -> None:
    store, _, _, _, chunk = fixture_store()

    chunk.evidence_key = CASE_ID + "__Wrong_1_0"

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="chunk evidence key",
    ):
        module.resolve_exact_evidence_row(
            case_id=CASE_ID,
            evidence_key=KEY_A,
            store=store,
        )


def test_page_sha_mismatch_fails_closed() -> None:
    store, binding, _, _, _ = fixture_store()

    binding.page_text_sha256 = "8" * 64

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="page-text SHA",
    ):
        module.resolve_exact_evidence_row(
            case_id=CASE_ID,
            evidence_key=KEY_A,
            store=store,
        )


def test_builds_exact_bounded_enriched_results() -> None:
    store, _, _, _, _ = fixture_store()

    row = module.resolve_exact_evidence_row(
        case_id=CASE_ID,
        evidence_key=KEY_A,
        store=store,
    )

    result = module.build_bounded_enriched_results(
        (row,)
    )

    assert result["ids"] == [[KEY_A]]
    assert result["documents"] == [[
        "Exact immutable evidence text."
    ]]

    metadata = result["metadatas"][0][0]

    assert metadata["file"] == "Document_A.pdf"
    assert metadata["page"] == 1
    assert (
        metadata["source_document_instance_id"]
        == row.source_document_instance_id
    )
    assert (
        metadata["drafting_chunk_text_sha256"]
        == row.chunk_text_sha256
    )


def test_existing_bounded_batcher_accepts_reconstruction() -> None:
    store, _, _, _, _ = fixture_store()

    row = module.resolve_exact_evidence_row(
        case_id=CASE_ID,
        evidence_key=KEY_A,
        store=store,
    )

    enriched = module.build_bounded_enriched_results(
        (row,)
    )

    from bounded_governed_answer import (
        build_evidence_batches,
    )

    batches = build_evidence_batches(
        enriched,
        target_chars=10_000,
    )

    assert len(batches) == 1
    assert KEY_A in batches[0].text
    assert "Exact immutable evidence text." in batches[0].text
    assert "Document_A.pdf" in batches[0].text


def test_reconstruction_composes_scope_and_source_adapter() -> None:
    store, _, _, _, _ = fixture_store()

    single_receipt = receipt(
        keys=(KEY_A,)
    )

    single_element = SimpleNamespace(
        supporting_evidence_keys=(KEY_A,),
        adverse_evidence_keys=(),
        corroborative_evidence_keys=(),
        conflicting_evidence_keys=(),
    )

    keys, rows, enriched = (
        module.reconstruct_bounded_generation_evidence(
            case_id=CASE_ID,
            retrieval_receipt=single_receipt,
            element=single_element,
            store=store,
        )
    )

    assert keys == (KEY_A,)
    assert len(rows) == 1
    assert enriched["ids"] == [[KEY_A]]


def test_duplicate_requested_keys_fail_closed() -> None:
    store, _, _, _, _ = fixture_store()

    with pytest.raises(
        module.DraftingEvidenceSourceError,
        match="must be unique",
    ):
        module.resolve_exact_evidence_rows(
            case_id=CASE_ID,
            evidence_keys=(KEY_A, KEY_A),
            store=store,
        )


def test_no_forbidden_runtime_dependencies() -> None:
    source = Path(module.__file__).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        "openai",
        "chromadb",
        "streamlit",
        "report_projection_provider",
        "resolve_projection_citation_source",
        "publish_projection",
        "publish_evidence",
        "record_working_draft",
        "work_product_release",
        "search_case_evidence",
        "similarity_search",
        "responses.create",
        "chat.completions",
        "write_text",
        "write_bytes",
    )

    assert not any(
        token in source
        for token in forbidden
    )