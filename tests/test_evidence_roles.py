from __future__ import annotations

from dataclasses import replace

import pytest

from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_roles import (
    EvidenceRole,
    EvidenceRoleClassificationError,
    classify_document_evidence_roles,
    classify_evidence_role,
)
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"


def _chunk(*, page: int, ordinal: int, text: str) -> DocumentEvidenceChunk:
    return DocumentEvidenceChunk(
        page_number=page,
        chunk_ordinal=ordinal,
        chunk_id=f"chunk-{page}-{ordinal}",
        evidence_key=f"evidence-{page}-{ordinal}",
        evidence_binding_id="sha256:" + f"{page}{ordinal}".ljust(64, "0")[:64],
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        chunk_text_sha256="sha256:" + f"{ordinal}{page}".ljust(64, "1")[:64],
        chunk_text_byte_length=len(text.encode("utf-8")),
        text=text,
    )


def _page(*, number: int, text: str, chunks: tuple[DocumentEvidenceChunk, ...]):
    return DocumentEvidencePage(
        page_number=number,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256="sha256:" + str(number).ljust(64, "a")[:64],
        page_text_byte_length=len(text.encode("utf-8")),
        text=text,
        chunks=chunks,
    )


def _inspection(
    *,
    filename: str,
    pages: tuple[DocumentEvidencePage, ...],
) -> DocumentEvidenceInspection:
    return DocumentEvidenceInspection(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id="sha256:" + "2" * 64,
        original_filename=filename,
        original_blob_sha256="sha256:" + "3" * 64,
        original_byte_length=1234,
        extraction_profile_id="extract-v1",
        chunking_profile_id="chunk-v1",
        page_count=len(pages),
        evidence_chunk_count=sum(len(page.chunks) for page in pages),
        pages=pages,
    )


def test_employer_email_is_primary_source():
    result = classify_evidence_role(
        file_name="Appendix H5 - Return to work correspondence.pdf",
        text=(
            "From: Alison Brooks (HR Director)\n"
            "To: Unum Claims\n"
            "We are writing regarding the proposed return to work."
        ),
    )
    assert result.role is EvidenceRole.PRIMARY_SOURCE
    assert result.source_type.value == "employer_record"
    assert result.provenance_method == "chunk-leading-sender"
    assert result.rule_id == "u8c.primary.direct-source.v1"


def test_claimant_email_is_primary_source():
    result = classify_evidence_role(
        file_name="Appendix H5 - Return to work correspondence.pdf",
        text=(
            "From: You\n"
            "To: HR Director\n"
            "Please refer me to Occupational Health before any decision."
        ),
    )
    assert result.role is EvidenceRole.PRIMARY_SOURCE
    assert result.source_type.value == "claimant_correspondence"


def test_medical_report_is_primary_source_without_email_header():
    result = classify_evidence_role(
        file_name="Consultant Psychiatrist Report.pdf",
        text="Clinical assessment, diagnosis and functional opinion.",
    )
    assert result.role is EvidenceRole.PRIMARY_SOURCE
    assert result.source_type.value == "independent_medical"


def test_witness_statement_is_commentary_role_not_primary_source():
    result = classify_evidence_role(
        file_name="Claimant Witness Statement.pdf",
        text="I am the Claimant in these proceedings. I recall the events of 2005.",
        document_hint="I am the Claimant in these proceedings.",
    )
    assert result.role is EvidenceRole.COMMENTARY
    assert result.source_type.value == "claimant_witness_statement"
    assert result.rule_id == "u8c.commentary.source-type.v1"


def test_party_submission_is_commentary_role():
    result = classify_evidence_role(
        file_name="Claimant Written Submissions.pdf",
        text="The Claimant submits that the continuing omission is in time.",
    )
    assert result.role is EvidenceRole.COMMENTARY


def test_relevance_to_claim_block_is_commentary_even_in_insurer_bundle():
    result = classify_evidence_role(
        file_name="Appendix H4 - Unum correspondence.pdf",
        text=(
            "Relevance to the Claim\n"
            "This email is relevant because it shows the employer knew of the proposed plan."
        ),
    )
    assert result.role is EvidenceRole.COMMENTARY
    assert result.rule_id == "u8c.commentary.heading-or-chronology.v1"


def test_chronology_container_is_commentary():
    result = classify_evidence_role(
        file_name="Appendix A - Chronology of Employment and Sickness Absence.pdf",
        text="5 July 2005 – GP certified sickness absence following the return-to-work attempt.",
    )
    assert result.role is EvidenceRole.COMMENTARY


def test_short_appendix_heading_is_cover_or_index():
    result = classify_evidence_role(
        file_name="Appendix H6.pdf",
        text="Appendix H6 - Return to Work Communications",
    )
    assert result.role is EvidenceRole.COVER_OR_INDEX


def test_standalone_see_appendix_reference_is_cross_reference():
    result = classify_evidence_role(
        file_name="Evidence Schedule.pdf",
        text="For the underlying correspondence see Appendix H5.",
    )
    assert result.role is EvidenceRole.CROSS_REFERENCE


def test_direct_email_with_commentary_block_is_mixed():
    result = classify_evidence_role(
        file_name="Appendix H6 - Correspondence.pdf",
        text=(
            "From: HR Director\n"
            "To: Employee\n"
            "We will discuss your proposed return.\n\n"
            "Relevance to the Claim\n"
            "This shows employer knowledge."
        ),
    )
    assert result.role is EvidenceRole.MIXED
    assert result.source_type.value == "employer_record"


def test_direct_email_that_merely_references_appendix_stays_primary():
    result = classify_evidence_role(
        file_name="Appendix H6 - Correspondence.pdf",
        text=(
            "From: HR Director\n"
            "To: Employee\n"
            "Please see Appendix H5 for the earlier plan."
        ),
    )
    assert result.role is EvidenceRole.PRIMARY_SOURCE


def test_ambiguous_correspondence_container_is_not_promoted():
    result = classify_evidence_role(
        file_name="Appendix H4 - Unum correspondence.pdf",
        text="The parties exchanged further correspondence on 12 May 2005.",
    )
    assert result.role is EvidenceRole.UNCLASSIFIED
    assert result.source_type.value == "mixed_correspondence"
    assert result.rule_id == "u8c.unclassified.mixed-correspondence.v1"


def test_legal_authority_is_not_called_primary_case_evidence():
    result = classify_evidence_role(
        file_name="Equality Act 2010.pdf",
        text="Section 15 discrimination arising from disability.",
    )
    assert result.role is EvidenceRole.UNCLASSIFIED
    assert result.source_type.value == "legal_authority"


def test_document_role_inspection_preserves_every_page_and_chunk_and_counts_roles():
    p1_chunks = (
        _chunk(
            page=1,
            ordinal=0,
            text="Appendix H6 - Return to Work Communications",
        ),
        _chunk(
            page=1,
            ordinal=1,
            text="From: HR Director\nTo: Employee\nWe will discuss your return.",
        ),
    )
    p2_chunks = (
        _chunk(
            page=2,
            ordinal=0,
            text="Relevance to the Claim\nThis shows contemporaneous knowledge.",
        ),
        _chunk(
            page=2,
            ordinal=1,
            text="For the earlier communication see Appendix H5.",
        ),
    )
    pages = (
        _page(number=1, text="\n".join(c.text for c in p1_chunks), chunks=p1_chunks),
        _page(number=2, text="\n".join(c.text for c in p2_chunks), chunks=p2_chunks),
    )
    inspection = _inspection(filename="Appendix H6 - Correspondence.pdf", pages=pages)

    result = classify_document_evidence_roles(inspection)

    assert result.document is inspection
    assert tuple(item.page for item in result.pages) == inspection.pages
    assert tuple(
        item.chunk
        for page in result.pages
        for item in page.chunks
    ) == tuple(chunk for page in inspection.pages for chunk in page.chunks)
    assert [
        item.classification.role
        for page in result.pages
        for item in page.chunks
    ] == [
        EvidenceRole.COVER_OR_INDEX,
        EvidenceRole.PRIMARY_SOURCE,
        EvidenceRole.COMMENTARY,
        EvidenceRole.CROSS_REFERENCE,
    ]
    counts = {item.role: item.count for item in result.role_counts}
    assert counts[EvidenceRole.PRIMARY_SOURCE] == 1
    assert counts[EvidenceRole.COMMENTARY] == 1
    assert counts[EvidenceRole.CROSS_REFERENCE] == 1
    assert counts[EvidenceRole.COVER_OR_INDEX] == 1
    assert counts[EvidenceRole.MIXED] == 0
    assert counts[EvidenceRole.UNCLASSIFIED] == 0


def test_zero_chunk_page_is_preserved():
    page = _page(number=1, text="Structural page only.", chunks=())
    inspection = _inspection(filename="Bundle.pdf", pages=(page,))
    result = classify_document_evidence_roles(inspection)
    assert len(result.pages) == 1
    assert result.pages[0].page is page
    assert result.pages[0].chunks == ()
    assert sum(item.count for item in result.role_counts) == 0


def test_document_classification_is_deterministic():
    chunk = _chunk(
        page=1,
        ordinal=0,
        text="From: Unum Claims Assessor\nTo: HR\nBenefit remains under review.",
    )
    page = _page(number=1, text=chunk.text, chunks=(chunk,))
    inspection = _inspection(filename="Appendix H4 - Unum correspondence.pdf", pages=(page,))
    assert classify_document_evidence_roles(inspection) == classify_document_evidence_roles(inspection)


def test_inconsistent_u8b_page_count_fails_closed():
    page = _page(number=1, text="Text", chunks=())
    inspection = replace(
        _inspection(filename="Bundle.pdf", pages=(page,)),
        page_count=2,
    )
    with pytest.raises(EvidenceRoleClassificationError, match="page_count"):
        classify_document_evidence_roles(inspection)


def test_inconsistent_u8b_chunk_order_fails_closed():
    wrong = _chunk(page=1, ordinal=1, text="From: HR Director\nText")
    page = _page(number=1, text=wrong.text, chunks=(wrong,))
    inspection = _inspection(filename="HR correspondence.pdf", pages=(page,))
    with pytest.raises(EvidenceRoleClassificationError, match="ordinal order"):
        classify_document_evidence_roles(inspection)

def test_embedded_email_marker_in_mixed_correspondence_is_primary_source():
    result = classify_evidence_role(
        file_name="Appendix H5 - Unum correspondence.pdf",
        text=(
            "Email 1 – Christine McCarroll → Arshad Shafi & Emma Shakespeare\n"
            "Date: 11 May 2005 15:13\n"
            "Subject: RTW\n"
            "We are still exploring opportunities on how we can best accommodate you."
        ),
        document_hint="The parties exchanged further correspondence on 12 May 2005.",
    )
    assert result.role is EvidenceRole.PRIMARY_SOURCE
    assert result.source_type.value == "mixed_correspondence"
    assert result.rule_id == "u8c.primary.embedded-communication.v1"


def test_embedded_email_with_later_commentary_heading_is_mixed():
    result = classify_evidence_role(
        file_name="Appendix H6 - Unum correspondence.pdf",
        text=(
            "Email 2 – Emma Shakespeare → Christine McCarroll & Nigel Phillips\n"
            "Date: 16 May 2005, 17:30\n"
            "Subject: Re: Ash Shafi\n"
            "A graduated return to work should be carefully structured.\n\n"
            "Relevance to the Claim\n"
            "This shows employer knowledge."
        ),
        document_hint="The parties exchanged further correspondence on 12 May 2005.",
    )
    assert result.role is EvidenceRole.MIXED
    assert result.source_type.value == "mixed_correspondence"
    assert result.rule_id == "u8c.mixed.embedded-communication-and-commentary.v1"


def test_document_embedded_communication_context_carries_across_chunk_boundary():
    chunks = (
        _chunk(
            page=1,
            ordinal=0,
            text=(
                "Appendix H4 - Internal Work and Rehabilitation Correspondence\n"
                "Source and Provenance\n"
                "Email 1 – Terry Williamson → Phil Lucy & Arshad Shafi\n"
                "Subject: HB documentation\n"
                "Please review the Orbis documentation."
            ),
        ),
        _chunk(
            page=1,
            ordinal=1,
            text=(
                "Please carry on with the VF specification and update the training manual."
            ),
        ),
        _chunk(
            page=1,
            ordinal=2,
            text=(
                "Relevance to the Claim\n"
                "This commentary explains why the earlier email matters."
            ),
        ),
        _chunk(
            page=1,
            ordinal=3,
            text="The parties exchanged further correspondence on 12 May 2005.",
        ),
    )
    page = _page(
        number=1,
        text="\n".join(chunk.text for chunk in chunks),
        chunks=chunks,
    )
    inspection = _inspection(
        filename="Appendix H4 - Unum correspondence.pdf",
        pages=(page,),
    )

    result = classify_document_evidence_roles(inspection)
    roles = [
        item.classification.role
        for role_page in result.pages
        for item in role_page.chunks
    ]
    assert roles == [
        EvidenceRole.PRIMARY_SOURCE,
        EvidenceRole.PRIMARY_SOURCE,
        EvidenceRole.COMMENTARY,
        EvidenceRole.UNCLASSIFIED,
    ]
    assert result.pages[0].chunks[0].classification.rule_id == (
        "u8c.primary.embedded-communication.v1"
    )
    assert result.pages[0].chunks[1].classification.rule_id == (
        "u8c.primary.embedded-communication-continuation.v1"
    )


def test_embedded_communication_continuation_with_commentary_is_mixed():
    chunks = (
        _chunk(
            page=1,
            ordinal=0,
            text=(
                "Email 1 – Christine McCarroll -> Emma Shakespeare & Nigel Phillips\n"
                "Date: 16 May 2005, 16:15\n"
                "Subject: Ash Shafi\n"
                "We do not want to overload him."
            ),
        ),
        _chunk(
            page=1,
            ordinal=1,
            text=(
                "A graduated return should be structured.\n"
                "Kind Regards,\n"
                "Emma Shakespeare\n\n"
                "Relevance to the Claim\n"
                "This commentary describes the significance of the plan."
            ),
        ),
    )
    page = _page(
        number=1,
        text="\n".join(chunk.text for chunk in chunks),
        chunks=chunks,
    )
    inspection = _inspection(
        filename="Appendix H6 - Unum correspondence.pdf",
        pages=(page,),
    )

    result = classify_document_evidence_roles(inspection)

    assert [
        item.classification.role
        for item in result.pages[0].chunks
    ] == [
        EvidenceRole.PRIMARY_SOURCE,
        EvidenceRole.MIXED,
    ]
    assert result.pages[0].chunks[1].classification.rule_id == (
        "u8c.mixed.embedded-communication-and-commentary.v1"
    )


def test_embedded_communication_context_stops_at_cross_reference():
    chunks = (
        _chunk(
            page=1,
            ordinal=0,
            text=(
                "Email 1 – Christine McCarroll → Arshad Shafi\n"
                "Subject: RTW\n"
                "We will discuss your proposed return."
            ),
        ),
        _chunk(
            page=1,
            ordinal=1,
            text="For the underlying correspondence see Appendix H5.",
        ),
        _chunk(
            page=1,
            ordinal=2,
            text="The parties exchanged further correspondence later that month.",
        ),
    )
    page = _page(
        number=1,
        text="\n".join(chunk.text for chunk in chunks),
        chunks=chunks,
    )
    inspection = _inspection(
        filename="Appendix H5 - Unum correspondence.pdf",
        pages=(page,),
    )

    result = classify_document_evidence_roles(inspection)

    assert [
        item.classification.role
        for item in result.pages[0].chunks
    ] == [
        EvidenceRole.PRIMARY_SOURCE,
        EvidenceRole.CROSS_REFERENCE,
        EvidenceRole.UNCLASSIFIED,
    ]
