from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from evidence_classification import EvidenceSourceType
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_roles import (
    DocumentEvidenceRoleInspection,
    EvidenceRole,
    EvidenceRoleChunk,
    EvidenceRoleClassification,
    EvidenceRolePage,
)
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchMatch,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    NegativeFindingScope,
)
from governed_analytical_capture import (
    GovernedAnalyticalCaptureError,
    U8_EXHAUSTIVE_MAPPER_INPUT_POLICY_VERSION,
    U8ExhaustiveMapperInput,
    build_u8_exhaustive_mapper_input,
)
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOC1_ID = "22222222-2222-4222-8222-222222222222"
DOC2_ID = "33333333-3333-4333-8333-333333333333"


def _sha(seed: str) -> str:
    return "sha256:" + (seed * 64)[:64]


def _chunk(*, document_id: str, page: int, ordinal: int, text: str) -> DocumentEvidenceChunk:
    key = f"{CASE_ID}__{document_id}_{page}_{ordinal}"
    return DocumentEvidenceChunk(
        page_number=page,
        chunk_ordinal=ordinal,
        chunk_id=key,
        evidence_key=key,
        evidence_binding_id=_sha(str(page + ordinal + 1)),
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        chunk_text_sha256=_sha(str(ordinal + 4)),
        chunk_text_byte_length=len(text.encode("utf-8")),
        text=text,
    )


def _classification(*, role: EvidenceRole, source_type: EvidenceSourceType) -> EvidenceRoleClassification:
    return EvidenceRoleClassification(
        role=role,
        rule_id=f"synthetic.{role.value}.v1",
        basis=f"Synthetic {role.value} role for adapter testing.",
        source_type=source_type,
        source_label=source_type.value,
        provenance_method="synthetic-deterministic",
        primary_tier=1 if role is EvidenceRole.PRIMARY_SOURCE else 0,
        primary_label="Synthetic primary" if role is EvidenceRole.PRIMARY_SOURCE else "Synthetic source",
    )


def _document(
    *,
    document_id: str,
    filename: str,
    page_chunks: tuple[tuple[tuple[str, EvidenceRole, EvidenceSourceType], ...], ...],
    document_source_type: EvidenceSourceType,
) -> DocumentEvidenceRoleInspection:
    pages = []
    role_pages = []
    for page_number, specs in enumerate(page_chunks, start=1):
        chunks = tuple(
            _chunk(document_id=document_id, page=page_number, ordinal=index, text=text)
            for index, (text, _, _) in enumerate(specs)
        )
        page_text = "\n\n".join(chunk.text for chunk in chunks)
        page = DocumentEvidencePage(
            page_number=page_number,
            extraction_method=ExtractionMethod.PYPDF_TEXT,
            page_text_sha256=_sha(str(page_number + 7)),
            page_text_byte_length=len(page_text.encode("utf-8")),
            text=page_text,
            chunks=chunks,
        )
        pages.append(page)
        role_pages.append(
            EvidenceRolePage(
                page=page,
                chunks=tuple(
                    EvidenceRoleChunk(
                        chunk=chunk,
                        classification=_classification(role=role, source_type=source_type),
                    )
                    for chunk, (_, role, source_type) in zip(chunks, specs, strict=True)
                ),
            )
        )

    inspection = DocumentEvidenceInspection(
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        source_snapshot_id=_sha(document_id[-1]),
        original_filename=filename,
        original_blob_sha256=_sha(document_id[-2]),
        original_byte_length=1234,
        extraction_profile_id="extract-v1",
        chunking_profile_id="chunk-v1",
        page_count=len(pages),
        evidence_chunk_count=sum(len(page.chunks) for page in pages),
        pages=tuple(pages),
    )
    return DocumentEvidenceRoleInspection(
        document=inspection,
        document_source_type=document_source_type,
        document_source_label=document_source_type.value,
        document_source_method="synthetic-document-classifier",
        pages=tuple(role_pages),
        role_counts=(),
    )


def _result() -> CaseEvidenceSearchResult:
    doc1 = _document(
        document_id=DOC1_ID,
        filename="Employer email.pdf",
        document_source_type=EvidenceSourceType.EMPLOYER_RECORD,
        page_chunks=(
            (
                (
                    "From: HR Director\nTo: Employee\nWe discussed a phased return to work.",
                    EvidenceRole.PRIMARY_SOURCE,
                    EvidenceSourceType.EMPLOYER_RECORD,
                ),
                (
                    "Relevance to the Claim\nEditorial commentary about the correspondence.",
                    EvidenceRole.COMMENTARY,
                    EvidenceSourceType.SECONDARY_SUMMARY,
                ),
            ),
        ),
    )
    doc2 = _document(
        document_id=DOC2_ID,
        filename="Medical evidence.pdf",
        document_source_type=EvidenceSourceType.INDEPENDENT_MEDICAL,
        page_chunks=(
            (
                (
                    "Clinical assessment records anxiety, depression and work-related limitations.",
                    EvidenceRole.PRIMARY_SOURCE,
                    EvidenceSourceType.INDEPENDENT_MEDICAL,
                ),
            ),
        ),
    )
    documents = (doc1, doc2)
    matches = tuple(
        EvidenceSearchMatch(
            source_document_instance_id=document.document.source_document_instance_id,
            original_filename=document.document.original_filename,
            chunk=item.chunk,
            classification=item.classification,
        )
        for document in documents
        for page in document.pages
        for item in page.chunks
    )
    keys = tuple(match.chunk.evidence_key for match in matches)
    receipt = EvidenceSearchReceipt(
        schema_version="1.0",
        case_id=CASE_ID,
        search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        query_sha256=_sha("a"),
        case_document_count=2,
        case_page_count=2,
        case_chunk_count=3,
        scope_document_count=2,
        scope_page_count=2,
        scope_chunk_count=3,
        documents_completely_expanded=2,
        pages_inspected=2,
        chunks_inspected=3,
        candidate_document_ids=(),
        searched_document_ids=(DOC1_ID, DOC2_ID),
        filters_applied=("text_match=all_evidence",),
        matched_evidence_keys=keys,
        completion=EvidenceSearchCompletion.COMPLETE,
        case_corpus_complete=True,
        negative_finding_scope=NegativeFindingScope.CASE_CORPUS,
        negative_finding_permitted=True,
    )
    return CaseEvidenceSearchResult(
        case_id=CASE_ID,
        query="capture policy does not filter on this text",
        search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        documents=documents,
        matches=matches,
        receipt=receipt,
    )


def _ids(source: CaseEvidenceSearchResult) -> list[str]:
    return [match.chunk.evidence_key for match in source.matches]


def test_builds_explicit_exhaustive_policy_without_mutating_source() -> None:
    source = _result()
    before = copy.deepcopy(source)
    adapter = build_u8_exhaustive_mapper_input(source)
    assert adapter.case_id == CASE_ID
    assert adapter.policy_version == U8_EXHAUSTIVE_MAPPER_INPUT_POLICY_VERSION
    assert adapter.evidence_count == 3
    assert source == before


def test_every_call_returns_all_rows_in_u8_order_and_ignores_question_and_n_results() -> None:
    source = _result()
    adapter = U8ExhaustiveMapperInput(source)
    first = adapter.retrieve("first question", n_results=1, case_id=CASE_ID)
    second = adapter.retrieve("unrelated second question", n_results=999, case_id=CASE_ID)
    assert first == second
    assert first["ids"] == [_ids(source)]
    assert first["documents"] == [[match.chunk.text for match in source.matches]]
    assert len(first["metadatas"][0]) == source.receipt.case_chunk_count


def test_mapper_rows_preserve_u8_source_identity_roles_and_no_discovery_rank() -> None:
    source = _result()
    output = U8ExhaustiveMapperInput(source).retrieve("anything", case_id=CASE_ID)
    for match, row_id, text, metadata in zip(
        source.matches,
        output["ids"][0],
        output["documents"][0],
        output["metadatas"][0],
        strict=True,
    ):
        assert row_id == match.chunk.evidence_key
        assert text == match.chunk.text
        assert metadata["case_id"] == CASE_ID
        assert metadata["file"] == match.original_filename
        assert metadata["page"] == match.chunk.page_number
        assert metadata["chunk"] == match.chunk.chunk_ordinal
        assert metadata["source_document_instance_id"] == match.source_document_instance_id
        assert metadata["source_evidence_binding_id"] == match.chunk.evidence_binding_id
        assert metadata["source_chunk_sha256"] == match.chunk.chunk_text_sha256
        assert metadata["source_binding_class"] == BindingClass.FULL_CHAIN_BOUND.value
        assert metadata["u8_evidence_role"] == match.classification.role.value
        assert metadata["u8_semantic_discovery_rank"] is None
        assert metadata["u8_governed_search_mode"] == EvidenceSearchMode.EXHAUSTIVE_EVIDENCE.value


def test_each_call_is_fresh_and_cannot_mutate_later_calls_or_source() -> None:
    source = _result()
    before = copy.deepcopy(source)
    adapter = U8ExhaustiveMapperInput(source)
    first = adapter.retrieve("one", case_id=CASE_ID)
    first["documents"][0][0] = "tampered caller copy"
    first["metadatas"][0][0]["file"] = "tampered.pdf"
    second = adapter.retrieve("two", case_id=CASE_ID)
    assert second["documents"][0][0] == source.matches[0].chunk.text
    assert second["metadatas"][0][0]["file"] == source.matches[0].original_filename
    assert source == before


@pytest.mark.parametrize("selection", [[], (), ["Employer email.pdf"]])
def test_selected_documents_always_fail_closed(selection) -> None:
    adapter = U8ExhaustiveMapperInput(_result())
    with pytest.raises(GovernedAnalyticalCaptureError, match="selected_documents"):
        adapter.retrieve("anything", selected_documents=selection, case_id=CASE_ID)


@pytest.mark.parametrize("case_id", [None, DOC1_ID, "11111111-1111-4111-8111-11111111111A"])
def test_mapper_call_requires_exact_canonical_capture_case(case_id) -> None:
    adapter = U8ExhaustiveMapperInput(_result())
    with pytest.raises(GovernedAnalyticalCaptureError, match="case_id|canonical"):
        adapter.retrieve("anything", case_id=case_id)


def test_rejects_non_exhaustive_or_incomplete_or_filtered_receipts() -> None:
    base = _result()
    bad = (
        replace(base, search_mode=EvidenceSearchMode.DOCUMENT_COMPLETE),
        replace(base, receipt=replace(base.receipt, search_mode=EvidenceSearchMode.DOCUMENT_COMPLETE)),
        replace(
            base,
            receipt=replace(
                base.receipt,
                completion=EvidenceSearchCompletion.PARTIAL,
                case_corpus_complete=False,
                negative_finding_scope=NegativeFindingScope.NONE,
                negative_finding_permitted=False,
            ),
        ),
        replace(
            base,
            receipt=replace(
                base.receipt,
                case_corpus_complete=False,
                negative_finding_scope=NegativeFindingScope.SEARCHED_SCOPE,
            ),
        ),
        replace(base, receipt=replace(base.receipt, candidate_document_ids=(DOC1_ID,))),
        replace(base, receipt=replace(base.receipt, filters_applied=("text_match=all_evidence", "role=primary_source"))),
    )
    for item in bad:
        with pytest.raises(GovernedAnalyticalCaptureError):
            U8ExhaustiveMapperInput(item)


def test_rejects_receipt_count_identity_or_match_drift() -> None:
    base = _result()
    drifted_match = replace(base.matches[0], original_filename="wrong.pdf")
    bad = (
        replace(base, receipt=replace(base.receipt, matched_evidence_keys=tuple(reversed(base.receipt.matched_evidence_keys)))),
        replace(base, matches=(drifted_match,) + base.matches[1:]),
        replace(
            base,
            receipt=replace(
                base.receipt,
                chunks_inspected=2,
                completion=EvidenceSearchCompletion.PARTIAL,
                case_corpus_complete=False,
                negative_finding_scope=NegativeFindingScope.NONE,
                negative_finding_permitted=False,
            ),
        ),
    )
    for item in bad:
        with pytest.raises(GovernedAnalyticalCaptureError):
            U8ExhaustiveMapperInput(item)


def test_rejects_non_full_chain_or_non_chunk_text_evidence() -> None:
    base = _result()
    first_doc = base.documents[0]
    first_page = first_doc.pages[0]
    first_role_chunk = first_page.chunks[0]

    weak_chunk = replace(first_role_chunk.chunk, binding_class=BindingClass.ANALYTICAL_TEXT_BOUND)
    weak_role_chunk = replace(first_role_chunk, chunk=weak_chunk)
    weak_page = replace(first_page, page=replace(first_page.page, chunks=(weak_chunk,) + first_page.page.chunks[1:]), chunks=(weak_role_chunk,) + first_page.chunks[1:])
    weak_doc_model = replace(first_doc.document, pages=(weak_page.page,), evidence_chunk_count=len(weak_page.page.chunks))
    weak_doc = replace(first_doc, document=weak_doc_model, pages=(weak_page,))
    weak_match = replace(base.matches[0], chunk=weak_chunk)
    weak = replace(base, documents=(weak_doc,) + base.documents[1:], matches=(weak_match,) + base.matches[1:])
    with pytest.raises(GovernedAnalyticalCaptureError, match="FULL_CHAIN_BOUND"):
        U8ExhaustiveMapperInput(weak)

    alternate_roles = [role for role in BoundTextRole if role is not BoundTextRole.CHUNK_TEXT]
    if not alternate_roles:
        pytest.skip("BoundTextRole exposes only CHUNK_TEXT in this frozen model.")
    bad_text_chunk = replace(first_role_chunk.chunk, bound_text_role=alternate_roles[0])
    bad_role_chunk = replace(first_role_chunk, chunk=bad_text_chunk)
    bad_page = replace(first_page, page=replace(first_page.page, chunks=(bad_text_chunk,) + first_page.page.chunks[1:]), chunks=(bad_role_chunk,) + first_page.chunks[1:])
    bad_doc_model = replace(first_doc.document, pages=(bad_page.page,), evidence_chunk_count=len(bad_page.page.chunks))
    bad_doc = replace(first_doc, document=bad_doc_model, pages=(bad_page,))
    bad_match = replace(base.matches[0], chunk=bad_text_chunk)
    wrong_role = replace(base, documents=(bad_doc,) + base.documents[1:], matches=(bad_match,) + base.matches[1:])
    with pytest.raises(GovernedAnalyticalCaptureError, match="CHUNK_TEXT"):
        U8ExhaustiveMapperInput(wrong_role)


def test_frozen_element_mapper_receives_the_same_complete_u8_population_for_every_element() -> None:
    from legal_analysis.evidence_mapper import ElementEvidenceMapper
    from legal_analysis.selector import DeterministicIssueSelector

    source = _result()
    before = copy.deepcopy(source)
    adapter = U8ExhaustiveMapperInput(source)
    question = "What evidence shows CACI knew about my disability?"
    selection = DeterministicIssueSelector().select(question, case_id=CASE_ID)

    mapped = ElementEvidenceMapper(
        retrieval_callable=adapter.retrieve,
        # Deliberately smaller than the exhaustive population: the adapter must
        # not permit the legacy retriever limit to truncate capture evidence.
        candidate_limit=1,
        retain_limit=1,
    ).map_primary_issue(
        case_id=CASE_ID,
        user_question=question,
        selection=selection,
    )

    expected_keys = tuple(_ids(source))
    assert len(mapped.element_results) == len(mapped.analysis.elements)
    assert len(mapped.element_results) > 1
    for element_result in mapped.element_results:
        assert tuple(item.evidence_key for item in element_result.mappings) == expected_keys

    assert source == before
