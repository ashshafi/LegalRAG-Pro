from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

import evidence_search.orchestrator as orchestrator
from document_catalog import DocumentCatalogEntry
from evidence_retrieval import DocumentCompleteRetrievalError
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_roles import EvidenceRole
from evidence_search import (
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    EvidenceTextMatchMode,
    NegativeFindingScope,
    record_semantic_discovery,
    search_case_evidence,
)
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
            "Relevance to the Claim\nThis bundle concerns the return-to-work proposal.",
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


def _entry(inspection: DocumentEvidenceInspection) -> DocumentCatalogEntry:
    return DocumentCatalogEntry(
        source_document_instance_id=inspection.source_document_instance_id,
        original_filename=inspection.original_filename,
        media_type="application/pdf",
        original_blob_sha256=inspection.original_blob_sha256,
        original_byte_length=inspection.original_byte_length,
        source_snapshot_id=inspection.source_snapshot_id,
        page_count=inspection.page_count,
        evidence_chunk_count=inspection.evidence_chunk_count,
        extraction_profile_id=inspection.extraction_profile_id,
        chunking_profile_id=inspection.chunking_profile_id,
        extraction_methods=(ExtractionMethod.PYPDF_TEXT.value,),
    )


CATALOG = tuple(_entry(item) for item in (H4, H5, H6))


@pytest.fixture(autouse=True)
def _fake_governed_boundaries(monkeypatch):
    monkeypatch.setattr(orchestrator, "list_case_documents", lambda case_id, store=None: CATALOG)

    def fake_inspect(*, case_id: str, source_document_instance_id: str, store=None):
        assert case_id == CASE_ID
        return INSPECTIONS[source_document_instance_id]

    monkeypatch.setattr(orchestrator, "inspect_document_complete", fake_inspect)


def test_exhaustive_search_inspects_entire_case_and_permits_case_scoped_negative_finding():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="return to work evidence",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    )

    assert [doc.document.source_document_instance_id for doc in result.documents] == [
        H4_ID,
        H5_ID,
        H6_ID,
    ]
    assert len(result.matches) == sum(item.evidence_chunk_count for item in (H4, H5, H6))
    receipt = result.receipt
    assert receipt.completion is EvidenceSearchCompletion.COMPLETE
    assert receipt.case_document_count == 3
    assert receipt.scope_document_count == 3
    assert receipt.documents_completely_expanded == 3
    assert receipt.case_page_count == 4
    assert receipt.pages_inspected == 4
    assert receipt.case_chunk_count == 7
    assert receipt.chunks_inspected == 7
    assert receipt.case_corpus_complete is True
    assert receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS
    assert receipt.negative_finding_permitted is True


def test_document_complete_expands_discovery_candidates_in_catalog_order_and_deduplicates():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="broad legal question",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H6_ID, H5_ID, H6_ID),
    )

    assert [doc.document.source_document_instance_id for doc in result.documents] == [H5_ID, H6_ID]
    assert result.receipt.candidate_document_ids == (H5_ID, H6_ID)
    assert result.receipt.searched_document_ids == (H5_ID, H6_ID)
    assert result.receipt.scope_document_count == 2
    assert result.receipt.case_corpus_complete is False
    assert result.receipt.negative_finding_scope is NegativeFindingScope.SEARCHED_SCOPE
    assert result.receipt.negative_finding_permitted is True


def test_document_complete_covering_all_catalog_documents_upgrades_negative_scope_to_case_corpus():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H6_ID, H4_ID, H5_ID),
    )

    assert result.receipt.case_corpus_complete is True
    assert result.receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS


def test_semantic_discovery_receipt_is_partial_and_never_permits_negative_finding():
    receipt = record_semantic_discovery(
        case_id=CASE_ID,
        query="reasonable adjustments and return to work",
        candidate_document_ids=(H6_ID, H5_ID, H5_ID),
    )

    assert receipt.search_mode is EvidenceSearchMode.SEMANTIC_DISCOVERY
    assert receipt.candidate_document_ids == (H5_ID, H6_ID)
    assert receipt.searched_document_ids == ()
    assert receipt.scope_document_count == 2
    assert receipt.documents_completely_expanded == 0
    assert receipt.pages_inspected == 0
    assert receipt.chunks_inspected == 0
    assert receipt.completion is EvidenceSearchCompletion.PARTIAL
    assert receipt.negative_finding_scope is NegativeFindingScope.NONE
    assert receipt.negative_finding_permitted is False


def test_semantic_discovery_mode_cannot_be_executed_as_if_complete():
    with pytest.raises(EvidenceSearchError, match="external to U8D"):
        search_case_evidence(
            case_id=CASE_ID,
            query="return to work",
            mode=EvidenceSearchMode.SEMANTIC_DISCOVERY,
            candidate_document_ids=(H5_ID,),
        )


@pytest.mark.parametrize("mode", [EvidenceSearchMode.CHRONOLOGY, EvidenceSearchMode.PERSON])
def test_recognised_but_unauthorised_modes_fail_closed(mode):
    with pytest.raises(EvidenceSearchError, match="recognised but not executable"):
        search_case_evidence(case_id=CASE_ID, query="anything", mode=mode)


def test_exhaustive_mode_rejects_supplied_candidate_scope():
    with pytest.raises(EvidenceSearchError, match="candidate_document_ids must be empty"):
        search_case_evidence(
            case_id=CASE_ID,
            query="",
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
            candidate_document_ids=(H5_ID,),
        )


def test_document_complete_requires_candidate_document():
    with pytest.raises(EvidenceSearchError, match="requires at least one"):
        search_case_evidence(
            case_id=CASE_ID,
            query="",
            mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        )


def test_unknown_candidate_document_fails_closed():
    unknown = "77777777-7777-4777-8777-777777777777"
    with pytest.raises(EvidenceSearchError, match="not present in the governed case catalog"):
        search_case_evidence(
            case_id=CASE_ID,
            query="",
            mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
            candidate_document_ids=(unknown,),
        )


def test_invalid_case_uuid_fails_before_catalog_access():
    with pytest.raises(EvidenceSearchError, match="case_id must be a valid UUID"):
        search_case_evidence(
            case_id="not-a-uuid",
            query="",
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        )


def test_all_evidence_match_mode_returns_every_chunk_even_for_broad_query():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="failure to make reasonable adjustments",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H5_ID,),
        text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
    )

    assert len(result.matches) == H5.evidence_chunk_count
    assert result.receipt.filters_applied == ("text_match=all_evidence",)


def test_exact_phrase_match_is_case_and_whitespace_insensitive():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="PROPOSED   PHASED RETURN",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H5_ID,),
        text_match_mode=EvidenceTextMatchMode.EXACT_PHRASE,
    )

    assert len(result.matches) == 1
    assert "phased return" in result.matches[0].chunk.text.casefold()


def test_all_terms_match_requires_every_term_in_same_chunk():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="occupational health decision",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H5_ID,),
        text_match_mode=EvidenceTextMatchMode.ALL_TERMS,
    )

    assert len(result.matches) == 1
    assert result.matches[0].classification.role is EvidenceRole.PRIMARY_SOURCE


def test_any_term_match_returns_deterministic_document_page_chunk_order():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="appendix occupational",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        text_match_mode=EvidenceTextMatchMode.ANY_TERM,
    )

    coordinates = [
        (match.source_document_instance_id, match.chunk.page_number, match.chunk.chunk_ordinal)
        for match in result.matches
    ]
    assert coordinates == sorted(
        coordinates,
        key=lambda item: ([H4_ID, H5_ID, H6_ID].index(item[0]), item[1], item[2]),
    )


def test_role_filter_selects_primary_sources_without_reducing_inspection_coverage():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        roles=(EvidenceRole.PRIMARY_SOURCE,),
    )

    assert result.matches
    assert all(match.classification.role is EvidenceRole.PRIMARY_SOURCE for match in result.matches)
    assert result.receipt.chunks_inspected == 7
    assert result.receipt.scope_chunk_count == 7
    assert result.receipt.filters_applied == (
        "text_match=all_evidence",
        "role=primary_source",
    )


def test_role_filter_order_is_canonical_and_duplicate_roles_are_removed():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H4_ID, H5_ID),
        roles=(EvidenceRole.COMMENTARY, EvidenceRole.PRIMARY_SOURCE, EvidenceRole.COMMENTARY),
    )

    assert result.receipt.filters_applied == (
        "text_match=all_evidence",
        "role=primary_source",
        "role=commentary",
    )


def test_non_all_evidence_match_mode_requires_non_empty_query():
    with pytest.raises(EvidenceSearchError, match="requires a non-empty"):
        search_case_evidence(
            case_id=CASE_ID,
            query="   ",
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
            text_match_mode=EvidenceTextMatchMode.EXACT_PHRASE,
        )


def test_no_literal_match_can_still_have_complete_case_coverage_receipt():
    result = search_case_evidence(
        case_id=CASE_ID,
        query="zzzz-no-such-text-zzzz",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        text_match_mode=EvidenceTextMatchMode.EXACT_PHRASE,
    )

    assert result.matches == ()
    assert result.receipt.matched_evidence_keys == ()
    assert result.receipt.case_corpus_complete is True
    assert result.receipt.negative_finding_permitted is True
    assert result.receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS


def test_query_hash_records_exact_original_query_bytes():
    query = "  Return to Work?  "
    result = search_case_evidence(
        case_id=CASE_ID,
        query=query,
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H5_ID,),
    )
    assert result.receipt.query_sha256 == "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()


def test_u8b_failure_aborts_entire_search_without_partial_receipt(monkeypatch):
    def broken_inspect(*, case_id: str, source_document_instance_id: str, store=None):
        if source_document_instance_id == H5_ID:
            raise DocumentCompleteRetrievalError("missing governed binding")
        return INSPECTIONS[source_document_instance_id]

    monkeypatch.setattr(orchestrator, "inspect_document_complete", broken_inspect)

    with pytest.raises(EvidenceSearchError, match="could not completely inspect"):
        search_case_evidence(
            case_id=CASE_ID,
            query="",
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        )


def test_catalog_and_u8b_identity_mismatch_fails_closed(monkeypatch):
    wrong = replace(H5, original_filename="Wrong name.pdf")

    def mismatched(*, case_id: str, source_document_instance_id: str, store=None):
        return wrong if source_document_instance_id == H5_ID else INSPECTIONS[source_document_instance_id]

    monkeypatch.setattr(orchestrator, "inspect_document_complete", mismatched)

    with pytest.raises(EvidenceSearchError, match="does not reconcile with the governed catalog"):
        search_case_evidence(
            case_id=CASE_ID,
            query="",
            mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
            candidate_document_ids=(H5_ID,),
        )


def test_empty_case_exhaustive_search_is_still_complete_case_corpus(monkeypatch):
    monkeypatch.setattr(orchestrator, "list_case_documents", lambda case_id, store=None: ())

    result = search_case_evidence(
        case_id=CASE_ID,
        query="",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    )

    assert result.documents == ()
    assert result.matches == ()
    assert result.receipt.case_document_count == 0
    assert result.receipt.case_corpus_complete is True
    assert result.receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS
    assert result.receipt.negative_finding_permitted is True


def test_receipt_rejects_negative_permission_for_partial_search():
    with pytest.raises(ValueError, match="Incomplete searches cannot permit"):
        EvidenceSearchReceipt(
            schema_version="1.0",
            case_id=CASE_ID,
            search_mode=EvidenceSearchMode.SEMANTIC_DISCOVERY,
            query_sha256=_digest("query"),
            case_document_count=3,
            case_page_count=4,
            case_chunk_count=7,
            scope_document_count=1,
            scope_page_count=2,
            scope_chunk_count=3,
            documents_completely_expanded=0,
            pages_inspected=0,
            chunks_inspected=0,
            candidate_document_ids=(H5_ID,),
            searched_document_ids=(),
            filters_applied=(),
            matched_evidence_keys=(),
            completion=EvidenceSearchCompletion.PARTIAL,
            case_corpus_complete=False,
            negative_finding_scope=NegativeFindingScope.SEARCHED_SCOPE,
            negative_finding_permitted=True,
        )


def test_receipt_rejects_false_case_completeness_counts():
    with pytest.raises(ValueError, match="every case document"):
        EvidenceSearchReceipt(
            schema_version="1.0",
            case_id=CASE_ID,
            search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
            query_sha256=_digest("query"),
            case_document_count=3,
            case_page_count=4,
            case_chunk_count=7,
            scope_document_count=2,
            scope_page_count=4,
            scope_chunk_count=7,
            documents_completely_expanded=2,
            pages_inspected=4,
            chunks_inspected=7,
            candidate_document_ids=(),
            searched_document_ids=(H4_ID, H5_ID),
            filters_applied=(),
            matched_evidence_keys=(),
            completion=EvidenceSearchCompletion.COMPLETE,
            case_corpus_complete=True,
            negative_finding_scope=NegativeFindingScope.CASE_CORPUS,
            negative_finding_permitted=True,
        )
