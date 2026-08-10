from __future__ import annotations

import hashlib

import pytest

import evidence_search.orchestrator as search_orchestrator
from document_catalog import DocumentCatalogEntry
from evidence_answer import (
    EVIDENCE_ROLE_KEY,
    GOVERNED_DISCOVERY_N_RESULTS,
    GOVERNED_DISCOVERY_RANK_KEY,
    GovernedAnswerEvidenceError,
    build_governed_answer_prompt,
    prepare_governed_answer_evidence,
)
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_search import EvidenceSearchMode, NegativeFindingScope
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


CASE_ID = "11111111-1111-4111-8111-111111111111"
H4_ID = "44444444-4444-4444-8444-444444444444"
H5_ID = "55555555-5555-4555-8555-555555555555"
H6_ID = "66666666-6666-4666-8666-666666666666"


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _chunk(*, document_id: str, page: int, ordinal: int, text: str) -> DocumentEvidenceChunk:
    return DocumentEvidenceChunk(
        page_number=page,
        chunk_ordinal=ordinal,
        chunk_id=f"chunk-{document_id[:4]}-{page}-{ordinal}",
        evidence_key=f"evidence-{document_id[:4]}-{page}-{ordinal}",
        evidence_binding_id=_digest(f"binding:{document_id}:{page}:{ordinal}"),
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        chunk_text_sha256=_digest(f"chunk:{document_id}:{page}:{ordinal}:{text}"),
        chunk_text_byte_length=len(text.encode("utf-8")),
        text=text,
    )


def _inspection(
    *,
    document_id: str,
    filename: str,
    page_texts: tuple[tuple[str, ...], ...],
) -> DocumentEvidenceInspection:
    pages = []
    for page_number, chunk_texts in enumerate(page_texts, start=1):
        chunks = tuple(
            _chunk(
                document_id=document_id,
                page=page_number,
                ordinal=ordinal,
                text=text,
            )
            for ordinal, text in enumerate(chunk_texts)
        )
        page_text = "\n\n".join(chunk_texts)
        pages.append(
            DocumentEvidencePage(
                page_number=page_number,
                extraction_method=ExtractionMethod.PYPDF_TEXT,
                page_text_sha256=_digest(f"page:{document_id}:{page_number}:{page_text}"),
                page_text_byte_length=len(page_text.encode("utf-8")),
                text=page_text,
                chunks=chunks,
            )
        )
    return DocumentEvidenceInspection(
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        source_snapshot_id=_digest(f"snapshot:{document_id}"),
        original_filename=filename,
        original_blob_sha256=_digest(f"original:{document_id}"),
        original_byte_length=1000 + len(document_id),
        extraction_profile_id="extract-v1",
        chunking_profile_id="chunk-v1",
        page_count=len(pages),
        evidence_chunk_count=sum(len(page.chunks) for page in pages),
        pages=tuple(pages),
    )


H4 = _inspection(
    document_id=H4_ID,
    filename="Appendix H4 - Unum correspondence.pdf",
    page_texts=(
        (
            "Appendix H4 - Unum correspondence",
            "Relevance to the Claim\nThis commentary says the return-to-work correspondence supports the claim.",
        ),
    ),
)
H5 = _inspection(
    document_id=H5_ID,
    filename="Appendix H5 - Return to work correspondence.pdf",
    page_texts=(
        (
            "From: Alison Brooks (HR Director)\nTo: Unum Claims\nWe are writing regarding the proposed phased return to work.",
            "From: You\nTo: HR Director\nPlease arrange Occupational Health before any decision.",
        ),
        (
            "For the earlier communication see Appendix H4.",
        ),
    ),
)
H6 = _inspection(
    document_id=H6_ID,
    filename="Appendix H6 - Return to Work Communications.pdf",
    page_texts=(
        (
            "Appendix H6 - Return to Work Communications",
            "From: HR Director\nTo: Employee\nWe will discuss your proposed return and working arrangements.",
        ),
    ),
)
INSPECTIONS = {H4_ID: H4, H5_ID: H5, H6_ID: H6}


def _entry(value: DocumentEvidenceInspection) -> DocumentCatalogEntry:
    return DocumentCatalogEntry(
        source_document_instance_id=value.source_document_instance_id,
        original_filename=value.original_filename,
        media_type="application/pdf",
        original_blob_sha256=value.original_blob_sha256,
        original_byte_length=value.original_byte_length,
        source_snapshot_id=value.source_snapshot_id,
        page_count=value.page_count,
        evidence_chunk_count=value.evidence_chunk_count,
        extraction_profile_id=value.extraction_profile_id,
        chunking_profile_id=value.chunking_profile_id,
        extraction_methods=(ExtractionMethod.PYPDF_TEXT.value,),
    )


CATALOG = tuple(_entry(value) for value in (H4, H5, H6))


@pytest.fixture(autouse=True)
def _governed_boundaries(monkeypatch):
    monkeypatch.setattr(
        search_orchestrator,
        "list_case_documents",
        lambda case_id, store=None: CATALOG,
    )

    def fake_inspect(*, case_id: str, source_document_instance_id: str, store=None):
        assert case_id == CASE_ID
        return INSPECTIONS[source_document_instance_id]

    monkeypatch.setattr(search_orchestrator, "inspect_document_complete", fake_inspect)


def _semantic_results(*document_ids: str) -> dict:
    ids = []
    documents = []
    metadatas = []
    for document_id in document_ids:
        inspection = INSPECTIONS[document_id]
        # Only one semantic hit per document. U8 must restore the rest.
        chunk = next(
            chunk
            for page in inspection.pages
            for chunk in page.chunks
            if chunk.text.strip()
        )
        ids.append(chunk.evidence_key)
        documents.append(chunk.text)
        metadatas.append(
            {
                "case_id": CASE_ID,
                "file": inspection.original_filename,
                "page": chunk.page_number,
                "chunk": chunk.chunk_ordinal,
                "source_document_instance_id": document_id,
            }
        )
    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
    }


def _semantic_retriever_for(*document_ids: str):
    def fake(question, selected_documents, n_results, *, case_id):
        assert question
        assert case_id == CASE_ID
        assert n_results == GOVERNED_DISCOVERY_N_RESULTS
        return _semantic_results(*document_ids)

    return fake


def test_broad_question_discovers_documents_without_h_labels_and_expands_every_chunk():
    question = "Did the employer fail to make reasonable adjustments during the return-to-work process?"
    assert "H4" not in question and "H5" not in question and "H6" not in question

    evidence = prepare_governed_answer_evidence(
        question=question,
        selected_documents=[entry.original_filename for entry in CATALOG],
        case_id=CASE_ID,
        semantic_retriever=_semantic_retriever_for(H6_ID, H5_ID, H4_ID),
    )

    assert evidence.search_mode is EvidenceSearchMode.DOCUMENT_COMPLETE
    assert tuple(doc.document.source_document_instance_id for doc in evidence.search_result.documents) == (
        H4_ID,
        H5_ID,
        H6_ID,
    )
    assert evidence.search_result.receipt.chunks_inspected == 7
    assert len(evidence.answer_results["documents"][0]) == 7
    assert any("Please arrange Occupational Health before any decision." in text for text in evidence.answer_results["documents"][0])
    assert any("We will discuss your proposed return and working arrangements." in text for text in evidence.answer_results["documents"][0])

    roles = [metadata[EVIDENCE_ROLE_KEY] for metadata in evidence.answer_results["metadatas"][0]]
    assert "primary_source" in roles
    assert "commentary" in roles
    assert "cover_or_index" in roles


def test_discovery_rank_is_recorded_at_document_level_not_as_chunk_rank():
    evidence = prepare_governed_answer_evidence(
        question="What evidence supports a phased return?",
        selected_documents=None,
        case_id=CASE_ID,
        semantic_retriever=_semantic_retriever_for(H6_ID, H5_ID),
    )

    ranks_by_document = {}
    for metadata in evidence.answer_results["metadatas"][0]:
        ranks_by_document.setdefault(metadata["source_document_instance_id"], set()).add(
            metadata[GOVERNED_DISCOVERY_RANK_KEY]
        )
    assert ranks_by_document[H6_ID] == {1}
    assert ranks_by_document[H5_ID] == {2}


def test_semantic_discovery_receipt_remains_partial_even_though_candidates_are_later_complete():
    evidence = prepare_governed_answer_evidence(
        question="What happened during the return-to-work process?",
        selected_documents=None,
        case_id=CASE_ID,
        semantic_retriever=_semantic_retriever_for(H5_ID, H6_ID),
    )

    assert evidence.semantic_receipt is not None
    assert evidence.semantic_receipt.negative_finding_permitted is False
    assert evidence.search_result.receipt.negative_finding_permitted is True
    assert evidence.search_result.receipt.negative_finding_scope is NegativeFindingScope.SEARCHED_SCOPE


def test_semantic_hit_must_be_present_in_complete_expanded_document():
    bad = _semantic_results(H5_ID)
    bad["ids"][0][0] = "not-a-governed-evidence-key"

    with pytest.raises(GovernedAnswerEvidenceError, match="absent from its completely expanded"):
        prepare_governed_answer_evidence(
            question="What happened?",
            selected_documents=None,
            case_id=CASE_ID,
            semantic_retriever=lambda *args, **kwargs: bad,
        )


def test_semantic_metadata_document_identity_mismatch_fails_closed():
    bad = _semantic_results(H5_ID)
    bad["metadatas"][0][0]["source_document_instance_id"] = H6_ID

    with pytest.raises(GovernedAnswerEvidenceError):
        prepare_governed_answer_evidence(
            question="What happened?",
            selected_documents=None,
            case_id=CASE_ID,
            semantic_retriever=lambda *args, **kwargs: bad,
        )


def test_missing_source_document_identity_fails_closed():
    bad = _semantic_results(H5_ID)
    del bad["metadatas"][0][0]["source_document_instance_id"]

    with pytest.raises(GovernedAnswerEvidenceError, match="valid UUID"):
        prepare_governed_answer_evidence(
            question="What happened?",
            selected_documents=None,
            case_id=CASE_ID,
            semantic_retriever=lambda *args, **kwargs: bad,
        )


def test_empty_semantic_discovery_does_not_become_no_evidence_finding():
    empty = {"ids": [[]], "documents": [[]], "metadatas": [[]]}

    with pytest.raises(GovernedAnswerEvidenceError, match="No negative finding is permitted"):
        prepare_governed_answer_evidence(
            question="Did CACI fail to make adjustments?",
            selected_documents=None,
            case_id=CASE_ID,
            semantic_retriever=lambda *args, **kwargs: empty,
        )


def test_explicit_exhaustive_question_bypasses_semantic_top_k_and_searches_selected_scope():
    def semantic_must_not_run(*args, **kwargs):
        raise AssertionError("semantic discovery must not run for explicit exhaustive request")

    evidence = prepare_governed_answer_evidence(
        question="Search all evidence exhaustively and enumerate every communication.",
        selected_documents=[entry.original_filename for entry in CATALOG],
        case_id=CASE_ID,
        semantic_retriever=semantic_must_not_run,
        catalog_service=lambda case_id: CATALOG,
    )

    assert evidence.semantic_results is None
    assert evidence.semantic_receipt is None
    assert evidence.search_result.receipt.case_corpus_complete is True
    assert evidence.search_result.receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS
    assert len(evidence.answer_results["documents"][0]) == 7


def test_explicit_exhaustive_subset_respects_user_selected_document_scope():
    evidence = prepare_governed_answer_evidence(
        question="Search all evidence exhaustively.",
        selected_documents=[H5.original_filename, H6.original_filename],
        case_id=CASE_ID,
        semantic_retriever=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
        catalog_service=lambda case_id: CATALOG,
    )

    assert tuple(doc.document.source_document_instance_id for doc in evidence.search_result.documents) == (
        H5_ID,
        H6_ID,
    )
    assert evidence.search_result.receipt.case_corpus_complete is False
    assert evidence.search_result.receipt.negative_finding_scope is NegativeFindingScope.SEARCHED_SCOPE


def test_exhaustive_without_selected_documents_uses_case_corpus_mode():
    evidence = prepare_governed_answer_evidence(
        question="Is there no evidence anywhere in the whole corpus?",
        selected_documents=None,
        case_id=CASE_ID,
        semantic_retriever=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    assert evidence.search_mode is EvidenceSearchMode.EXHAUSTIVE_EVIDENCE
    assert evidence.search_result.receipt.case_corpus_complete is True


def test_selected_exhaustive_scope_rejects_unknown_filename():
    with pytest.raises(GovernedAnswerEvidenceError, match="not present in the governed catalog"):
        prepare_governed_answer_evidence(
            question="Search all evidence exhaustively.",
            selected_documents=["not-governed.pdf"],
            case_id=CASE_ID,
            semantic_retriever=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
            catalog_service=lambda case_id: CATALOG,
        )


def test_prompt_prioritises_primary_sources_and_limits_negative_finding_to_searched_scope():
    evidence = prepare_governed_answer_evidence(
        question="What evidence supports adjustments?",
        selected_documents=None,
        case_id=CASE_ID,
        semantic_retriever=_semantic_retriever_for(H5_ID),
    )
    prompt = build_governed_answer_prompt(
        question=evidence.question,
        evidence=evidence,
        enriched_results=evidence.answer_results,
    )
    compact = " ".join(prompt.split())

    assert "Treat Evidence role: primary_source as the strongest direct evidential layer" in compact
    assert "completely searched candidate documents" in compact
    assert "Do not generalise that statement to the entire case corpus" in compact
    assert "U8 EVIDENCE ROLE AUDIT" in prompt
    assert "role=primary_source" in prompt
    assert "Relevance to the Claim" not in prompt  # H4 was not in the discovered scope.


def test_prompt_allows_only_case_corpus_scoped_negative_wording_after_complete_case_search():
    evidence = prepare_governed_answer_evidence(
        question="Search all evidence exhaustively.",
        selected_documents=[entry.original_filename for entry in CATALOG],
        case_id=CASE_ID,
        semantic_retriever=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
        catalog_service=lambda case_id: CATALOG,
    )
    prompt = build_governed_answer_prompt(
        question=evidence.question,
        evidence=evidence,
        enriched_results=evidence.answer_results,
    )

    assert "No supporting evidence was identified in the searched case corpus." in prompt
    assert "Whole governed case corpus complete: yes" in prompt


def test_complete_answer_results_retain_exact_governed_evidence_keys_once_each():
    evidence = prepare_governed_answer_evidence(
        question="What evidence exists?",
        selected_documents=None,
        case_id=CASE_ID,
        semantic_retriever=_semantic_retriever_for(H4_ID, H5_ID, H6_ID),
    )
    ids = evidence.answer_results["ids"][0]
    expected = [
        chunk.evidence_key
        for document in (H4, H5, H6)
        for page in document.pages
        for chunk in page.chunks
    ]
    assert ids == expected
    assert len(ids) == len(set(ids)) == 7
