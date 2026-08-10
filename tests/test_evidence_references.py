from __future__ import annotations

import hashlib
from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

import evidence_search.orchestrator as search_orchestrator
from document_catalog import DocumentCatalogEntry
from evidence_references import (
    EvidenceReferenceKind,
    EvidenceReferenceResolutionError,
    EvidenceReferenceResolutionStatus,
    resolve_evidence_references,
)
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_search import EvidenceSearchMode, search_case_evidence
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


CASE_ID = "11111111-1111-4111-8111-111111111111"
H4_ID = "44444444-4444-4444-8444-444444444444"
H5_ID = "55555555-5555-4555-8555-555555555555"
H6_ID = "66666666-6666-4666-8666-666666666666"
H4_DUP_ID = "47474747-4747-4747-8747-474747474747"


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
    page_texts=((
        "Appendix H4 - Unum correspondence",
        "From: Emma Shakespeare\nTo: Arshad Shafi\nDate: 5 July 2005\nSubject: Return to work\nWe support a gradual return-to-work plan.",
    ),),
)
H5 = _inspection(
    document_id=H5_ID,
    filename="Appendix H5 - Return to work correspondence.pdf",
    page_texts=((
        "For the earlier communication see Appendix H4.",
        "Relevance to the Claim\nThe email from Emma Shakespeare dated 5 July 2005 supports the chronology.",
        "The email from Emma Shakespeare dated 6 July 2005 is also referenced in the narrative.",
    ),),
)
H6 = _inspection(
    document_id=H6_ID,
    filename="Appendix H6 - Return to Work Communications.pdf",
    page_texts=((
        "From: Alison Brooks\nTo: Arshad Shafi\nDate: 17 July 2026\nSubject: Employment status review\nPlease provide an update on fitness for work.",
    ),),
)


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


def _install_boundaries(monkeypatch, inspections: tuple[DocumentEvidenceInspection, ...]) -> None:
    by_id = {item.source_document_instance_id: item for item in inspections}
    catalog = tuple(_entry(item) for item in inspections)
    monkeypatch.setattr(
        search_orchestrator,
        "list_case_documents",
        lambda case_id, store=None: catalog,
    )

    def fake_inspect(*, case_id: str, source_document_instance_id: str, store=None):
        assert case_id == CASE_ID
        return by_id[source_document_instance_id]

    monkeypatch.setattr(search_orchestrator, "inspect_document_complete", fake_inspect)


def _exhaustive(monkeypatch, *inspections: DocumentEvidenceInspection):
    _install_boundaries(monkeypatch, tuple(inspections))
    return search_case_evidence(
        case_id=CASE_ID,
        query="reference reconciliation",
        mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    )


def test_appendix_reference_resolves_to_governed_target_document(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5, H6)
    resolved = resolve_evidence_references(result)

    appendix = next(
        item for item in resolved.resolutions
        if item.reference.kind is EvidenceReferenceKind.APPENDIX
    )
    assert appendix.reference.appendix_label == "H4"
    assert appendix.status is EvidenceReferenceResolutionStatus.RESOLVED
    assert appendix.matched_document_ids == (H4_ID,)
    assert appendix.matched_evidence_keys == ("evidence-4444-1-1",)


def test_named_email_reference_resolves_to_underlying_primary_communication(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5, H6)
    resolved = resolve_evidence_references(result)

    email = next(
        item for item in resolved.resolutions
        if item.reference.kind is EvidenceReferenceKind.COMMUNICATION
        and item.reference.canonical_date == "2005-07-05"
    )
    assert email.reference.communication_type == "email"
    assert email.reference.person_text == "Emma Shakespeare"
    assert email.status is EvidenceReferenceResolutionStatus.RESOLVED
    assert email.matched_document_ids == (H4_ID,)
    assert email.matched_evidence_keys == ("evidence-4444-1-1",)


def test_missing_named_email_is_possible_not_located_only_after_complete_case_search(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5, H6)
    resolved = resolve_evidence_references(result)

    missing = next(
        item for item in resolved.resolutions
        if item.reference.kind is EvidenceReferenceKind.COMMUNICATION
        and item.reference.canonical_date == "2005-07-06"
    )
    assert missing.status is EvidenceReferenceResolutionStatus.POSSIBLE_REFERENCED_BUT_NOT_LOCATED
    assert missing.matched_document_ids == ()
    assert missing.matched_evidence_keys == ()
    assert resolved.receipt.case_corpus_complete is True
    assert resolved.receipt.possible_not_located_permitted is True
    assert resolved.receipt.possible_not_located_count == 1


def test_same_missing_reference_in_partial_document_scope_remains_unresolved(monkeypatch):
    _install_boundaries(monkeypatch, (H4, H5, H6))
    result = search_case_evidence(
        case_id=CASE_ID,
        query="reference reconciliation",
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=(H5_ID,),
    )
    resolved = resolve_evidence_references(result)

    assert result.receipt.case_corpus_complete is False
    assert all(
        item.status is EvidenceReferenceResolutionStatus.UNRESOLVED_REFERENCE
        for item in resolved.resolutions
    )
    assert resolved.receipt.possible_not_located_permitted is False
    assert resolved.receipt.possible_not_located_count == 0
    assert resolved.receipt.unresolved_count == len(resolved.resolutions)


def test_appendix_heading_does_not_create_self_reference(monkeypatch):
    result = _exhaustive(monkeypatch, H4)
    resolved = resolve_evidence_references(result)
    assert resolved.resolutions == ()
    assert resolved.receipt.reference_count == 0


def test_vague_earlier_correspondence_without_specific_target_is_not_invented(monkeypatch):
    vague = _inspection(
        document_id=H5_ID,
        filename="Appendix H5 - narrative.pdf",
        page_texts=(("The earlier correspondence should also be considered.",),),
    )
    result = _exhaustive(monkeypatch, vague)
    resolved = resolve_evidence_references(result)
    assert resolved.resolutions == ()


def test_duplicate_matching_communications_are_ambiguous(monkeypatch):
    duplicate = _inspection(
        document_id=H4_DUP_ID,
        filename="Appendix J1 - duplicate correspondence.pdf",
        page_texts=((
            "From: Emma Shakespeare\nTo: Arshad Shafi\nDate: 5 July 2005\nSubject: Return to work\nDuplicate retained communication.",
        ),),
    )
    result = _exhaustive(monkeypatch, H4, duplicate, H5)
    resolved = resolve_evidence_references(result)

    item = next(
        resolution for resolution in resolved.resolutions
        if resolution.reference.kind is EvidenceReferenceKind.COMMUNICATION
        and resolution.reference.canonical_date == "2005-07-05"
    )
    assert item.status is EvidenceReferenceResolutionStatus.AMBIGUOUS
    assert set(item.matched_document_ids) == {H4_ID, H4_DUP_ID}
    assert len(item.matched_evidence_keys) == 2


def test_duplicate_appendix_labels_are_ambiguous_when_both_have_target_evidence(monkeypatch):
    duplicate = _inspection(
        document_id=H4_DUP_ID,
        filename="Appendix H4 - duplicate copy.pdf",
        page_texts=((
            "From: Another Sender\nTo: Recipient\nDate: 4 July 2005\nSubject: Other communication\nText.",
        ),),
    )
    result = _exhaustive(monkeypatch, H4, duplicate, H5)
    resolved = resolve_evidence_references(result)
    item = next(
        resolution for resolution in resolved.resolutions
        if resolution.reference.kind is EvidenceReferenceKind.APPENDIX
    )
    assert item.status is EvidenceReferenceResolutionStatus.AMBIGUOUS
    assert set(item.matched_document_ids) == {H4_ID, H4_DUP_ID}


def test_communication_date_can_precede_sender_phrase(monkeypatch):
    narrative = _inspection(
        document_id=H5_ID,
        filename="Appendix H5 - narrative.pdf",
        page_texts=(("The email dated 5 July 2005 from Emma Shakespeare was considered.",),),
    )
    result = _exhaustive(monkeypatch, H4, narrative)
    resolved = resolve_evidence_references(result)
    item = resolved.resolutions[0]
    assert item.reference.canonical_date == "2005-07-05"
    assert item.reference.person_text == "Emma Shakespeare"
    assert item.status is EvidenceReferenceResolutionStatus.RESOLVED


def test_email_dated_without_sender_can_resolve_when_unique(monkeypatch):
    narrative = _inspection(
        document_id=H5_ID,
        filename="Appendix H5 - narrative.pdf",
        page_texts=(("The email dated 5 July 2005 was considered.",),),
    )
    result = _exhaustive(monkeypatch, H4, narrative)
    resolved = resolve_evidence_references(result)
    item = resolved.resolutions[0]
    assert item.reference.person_text is None
    assert item.status is EvidenceReferenceResolutionStatus.RESOLVED


def test_reference_ids_and_resolution_order_are_deterministic(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5, H6)
    first = resolve_evidence_references(result)
    second = resolve_evidence_references(result)
    assert first == second
    assert [item.reference.reference_id for item in first.resolutions] == [
        item.reference.reference_id for item in second.resolutions
    ]


def test_reference_receipt_counts_reconcile(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5, H6)
    resolved = resolve_evidence_references(result)
    receipt = resolved.receipt
    assert receipt.reference_count == 3
    assert receipt.resolved_count == 2
    assert receipt.ambiguous_count == 0
    assert receipt.possible_not_located_count == 1
    assert receipt.unresolved_count == 0
    assert receipt.documents_completely_expanded == 3
    assert receipt.pages_inspected == result.receipt.pages_inspected
    assert receipt.chunks_inspected == result.receipt.chunks_inspected


def _receipt_proxy(receipt, **changes):
    values = {field.name: getattr(receipt, field.name) for field in fields(receipt)}
    values.update(changes)
    return SimpleNamespace(**values)


def test_incomplete_u8d_receipt_is_rejected(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5)
    bad_receipt = _receipt_proxy(result.receipt, completion="partial")
    bad_result = replace(result, receipt=bad_receipt)
    with pytest.raises(EvidenceReferenceResolutionError, match="requires a COMPLETE"):
        resolve_evidence_references(bad_result)


def test_document_surface_count_mismatch_is_rejected(monkeypatch):
    result = _exhaustive(monkeypatch, H4, H5)
    bad_receipt = _receipt_proxy(
        result.receipt,
        pages_inspected=result.receipt.pages_inspected - 1,
    )
    bad_result = replace(result, receipt=bad_receipt)
    with pytest.raises(EvidenceReferenceResolutionError, match="page coverage"):
        resolve_evidence_references(bad_result)


def test_numeric_dates_remain_exact_text_matched_not_silently_reinterpreted(monkeypatch):
    target = _inspection(
        document_id=H4_ID,
        filename="Appendix H4 - correspondence.pdf",
        page_texts=(("From: Emma Shakespeare\nTo: Arshad Shafi\nDate: 05/07/2005\nEmail text.",),),
    )
    narrative = _inspection(
        document_id=H5_ID,
        filename="Appendix H5 - narrative.pdf",
        page_texts=(("The email from Emma Shakespeare dated 05/07/2005 is referenced.",),),
    )
    result = _exhaustive(monkeypatch, target, narrative)
    resolved = resolve_evidence_references(result)
    item = resolved.resolutions[0]
    assert item.reference.canonical_date is None
    assert item.reference.date_text == "05/07/2005"
    assert item.status is EvidenceReferenceResolutionStatus.RESOLVED
