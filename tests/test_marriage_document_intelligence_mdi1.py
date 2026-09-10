from __future__ import annotations

from dataclasses import fields

import pytest

from marriage_document_intelligence import (
    COMPARISON_STATUSES,
    FACT_FIELDS,
    MARRIAGE_DOCUMENT_DOMAIN_CONTRACT,
    MARRIAGE_DOCUMENT_DOMAIN_CONTRACT_SHA256,
    MDI_PRODUCT_CONTRACT_SHA256,
    MDI_SCHEMA_VERSION,
    PROHIBITED_AUTOMATIC_CONCLUSIONS,
    SOLICITOR_RESULT_HEADINGS,
    SUPPORTED_DOCUMENT_TYPES,
    TEXT_REPRESENTATION_KINDS,
    MarriageComparisonNote,
    MarriageComparisonStatus,
    MarriageDocumentIntelligenceError,
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
    MarriagePotentialIssue,
    MarriageTextRepresentation,
    MarriageTextRepresentationKind,
    SourceRegion,
    build_solicitor_marriage_document_result,
    validate_marriage_document_record,
)


def sha_hex(char: str) -> str:
    return char * 64


def sha_id(char: str) -> str:
    return "sha256:" + sha_hex(char)


def provenance() -> MarriageFactProvenance:
    return MarriageFactProvenance(
        source_document_instance_id="doc-instance-1",
        source_snapshot_id="snapshot-1",
        original_filename="nikah-nama.pdf",
        original_blob_sha256=sha_hex("a"),
        page_number=1,
        candidate_record_id=sha_id("b"),
        transcription_sha256=sha_hex("c"),
        review_event_id=sha_id("d"),
        derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
        quality_note="Legible in the approved crop.",
        binding_id=sha_id("e"),
        publication_receipt_id=sha_id("f"),
        crop_name="nikah-registration-panel",
        bbox=SourceRegion(left=10, top=20, right=300, bottom=180),
    )


def record() -> MarriageDocumentIntelligenceRecord:
    source = provenance()
    return MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="Urdu Nikah Nama, page 1",
        facts=(
            MarriageFact(
                field=MarriageFactField.BRIDE_NAME,
                value="Example Bride",
                provenance=source,
            ),
            MarriageFact(
                field=MarriageFactField.GROOM_NAME,
                value="Example Groom",
                provenance=source,
            ),
            MarriageFact(
                field=MarriageFactField.MARRIAGE_DATE,
                value="1 January 2000",
                provenance=source,
            ),
            MarriageFact(
                field=MarriageFactField.REGISTRATION_NUMBER,
                value="123/2000",
                provenance=source,
            ),
            MarriageFact(
                field=MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
                value="Union Council example",
                provenance=source,
            ),
        ),
        text_representations=(
            MarriageTextRepresentation(
                kind=MarriageTextRepresentationKind.AI_TRANSCRIPTION,
                text="Approved Urdu-derived transcription.",
                provenance=source,
                produced_by_legalrag=True,
            ),
            MarriageTextRepresentation(
                kind=MarriageTextRepresentationKind.AI_ASSISTED_ENGLISH_TRANSLATION,
                text="AI-assisted English rendering.",
                provenance=source,
                produced_by_legalrag=True,
            ),
        ),
        comparisons=(
            MarriageComparisonNote(
                status=MarriageComparisonStatus.UNRESOLVED_OR_UNCLEAR,
                summary="No second marriage record has yet been compared.",
            ),
        ),
        potential_issues=(
            MarriagePotentialIssue(
                summary="Registration particulars should be checked against the original Union Council record."
            ),
        ),
        next_professional_actions=(
            "Obtain or compare the original Union Council marriage record.",
            "Use a qualified human translator where a certified translation is required.",
        ),
    )


def test_product_contract_binding_and_schema_are_frozen():
    assert MDI_PRODUCT_CONTRACT_SHA256 == (
        "98a1c8d854aa500599db52aa66d6dfb27c10e0169d2c0798f7917818dae1e51"
    )
    assert MDI_SCHEMA_VERSION == "marriage-document-intelligence/1.0"
    assert len(MARRIAGE_DOCUMENT_DOMAIN_CONTRACT_SHA256) == 64
    assert MARRIAGE_DOCUMENT_DOMAIN_CONTRACT["schema"] == MDI_SCHEMA_VERSION


def test_supported_v1_document_family_is_exact():
    assert SUPPORTED_DOCUMENT_TYPES == tuple(
        item.value for item in MarriageDocumentType
    )
    assert len(SUPPORTED_DOCUMENT_TYPES) == 5
    assert "nikah_nama" in SUPPORTED_DOCUMENT_TYPES
    assert "union_council_marriage_record" in SUPPORTED_DOCUMENT_TYPES


def test_structured_fact_schema_contains_product_contract_particulars():
    assert set(FACT_FIELDS) == {item.value for item in MarriageFactField}
    for required in (
        "bride_name",
        "groom_name",
        "marriage_date",
        "place_of_marriage",
        "registration_date",
        "registration_number",
        "union_council_or_local_authority",
        "mehr_prompt_amount",
        "mehr_deferred_amount",
        "witness_name",
        "stamp",
        "signature",
        "overwriting_or_correction",
    ):
        assert required in FACT_FIELDS


def test_every_fact_carries_exact_source_and_review_provenance():
    expected = {
        "source_document_instance_id",
        "source_snapshot_id",
        "original_filename",
        "original_blob_sha256",
        "page_number",
        "candidate_record_id",
        "transcription_sha256",
        "review_event_id",
        "derivation_kind",
        "quality_note",
        "binding_id",
        "publication_receipt_id",
        "crop_name",
        "bbox",
    }
    assert expected == {
        field.name for field in fields(MarriageFactProvenance)
    }
    validate_marriage_document_record(record())


def test_exact_crop_provenance_is_all_or_nothing():
    source = provenance()
    broken = MarriageFactProvenance(
        **{
            **source.__dict__,
            "publication_receipt_id": None,
        }
    )
    broken_record = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="broken",
        facts=(
            MarriageFact(
                field=MarriageFactField.BRIDE_NAME,
                value="Bride",
                provenance=broken,
            ),
        ),
    )
    with pytest.raises(
        MarriageDocumentIntelligenceError,
        match="Exact crop provenance",
    ):
        validate_marriage_document_record(broken_record)


def test_ai_translation_labels_are_exact_and_not_certified():
    assert TEXT_REPRESENTATION_KINDS == tuple(
        item.value for item in MarriageTextRepresentationKind
    )

    source = provenance()
    bad = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="Nikah Nama",
        facts=(),
        text_representations=(
            MarriageTextRepresentation(
                kind=MarriageTextRepresentationKind.CERTIFIED_TRANSLATION,
                text="AI text incorrectly labelled certified.",
                provenance=source,
                produced_by_legalrag=True,
            ),
        ),
    )

    with pytest.raises(
        MarriageDocumentIntelligenceError,
        match="must not be represented as a certified translation",
    ):
        validate_marriage_document_record(bad)


def test_human_certified_translation_can_be_modelled_without_ai_claim():
    source = provenance()
    value = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="Nikah Nama",
        facts=(),
        text_representations=(
            MarriageTextRepresentation(
                kind=MarriageTextRepresentationKind.CERTIFIED_TRANSLATION,
                text="Human-provided certified translation.",
                provenance=source,
                produced_by_legalrag=False,
            ),
        ),
    )
    validate_marriage_document_record(value)


def test_comparison_statuses_are_exact_product_language():
    assert COMPARISON_STATUSES == tuple(
        item.value for item in MarriageComparisonStatus
    )
    assert COMPARISON_STATUSES == (
        "exact match",
        "likely transliteration/spelling variation",
        "possible inconsistency",
        "material contradiction",
        "unresolved/unclear",
    )


def test_legal_conclusion_boundary_is_explicit():
    assert "validity of the marriage under Pakistani law" in PROHIBITED_AUTOMATIC_CONCLUSIONS
    assert "recognition under English law" in PROHIBITED_AUTOMATIC_CONCLUSIONS
    assert "authenticity of a disputed document" in PROHIBITED_AUTOMATIC_CONCLUSIONS
    assert "fraud" in PROHIBITED_AUTOMATIC_CONCLUSIONS
    assert "forgery" in PROHIBITED_AUTOMATIC_CONCLUSIONS


def test_solicitor_result_headings_use_legal_working_language():
    assert SOLICITOR_RESULT_HEADINGS == (
        "Document",
        "Key marriage particulars",
        "Registration particulars",
        "Translation / transcription",
        "Comparison",
        "Potential issues",
        "Source",
        "Next professional action",
    )
    joined = " ".join(SOLICITOR_RESULT_HEADINGS)
    for forbidden in ("CAA", "PRW", "MAL1", "GAR1", "SHA256"):
        assert forbidden not in joined


def test_projection_separates_registration_from_other_particulars():
    projected = build_solicitor_marriage_document_result(record())

    assert projected.document == "Nikah Nama â€” Urdu Nikah Nama, page 1"
    assert tuple(
        fact.field for fact in projected.registration_particulars
    ) == (
        MarriageFactField.REGISTRATION_NUMBER,
        MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
    )
    assert tuple(
        fact.field for fact in projected.key_marriage_particulars
    ) == (
        MarriageFactField.BRIDE_NAME,
        MarriageFactField.GROOM_NAME,
        MarriageFactField.MARRIAGE_DATE,
    )


def test_projection_preserves_translation_issue_source_and_next_action():
    projected = build_solicitor_marriage_document_result(record())

    assert len(projected.translation_or_transcription) == 2
    assert len(projected.comparison) == 1
    assert len(projected.potential_issues) == 1
    assert len(projected.source) == 1
    assert projected.source[0].original_filename == "nikah-nama.pdf"
    assert projected.source[0].page_number == 1
    assert len(projected.next_professional_action) == 2


def test_projection_deduplicates_same_source_region():
    projected = build_solicitor_marriage_document_result(record())
    assert len(projected.source) == 1


def test_duplicate_exact_fact_is_rejected():
    source = provenance()
    fact = MarriageFact(
        field=MarriageFactField.BRIDE_NAME,
        value="Bride",
        provenance=source,
    )
    duplicate = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="Nikah Nama",
        facts=(fact, fact),
    )
    with pytest.raises(
        MarriageDocumentIntelligenceError,
        match="Exact duplicate marriage fact",
    ):
        validate_marriage_document_record(duplicate)


def test_bad_bbox_fails_closed():
    source = provenance()
    bad_source = MarriageFactProvenance(
        **{
            **source.__dict__,
            "bbox": SourceRegion(left=100, top=20, right=90, bottom=180),
        }
    )
    bad = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="Nikah Nama",
        facts=(
            MarriageFact(
                field=MarriageFactField.BRIDE_NAME,
                value="Bride",
                provenance=bad_source,
            ),
        ),
    )
    with pytest.raises(
        MarriageDocumentIntelligenceError,
        match="positive width and height",
    ):
        validate_marriage_document_record(bad)


def test_package_is_domain_only_without_runtime_dependencies():
    import marriage_document_intelligence
    root = __import__("pathlib").Path(
        marriage_document_intelligence.__file__
    ).parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.py"))
    ).lower()

    for forbidden in (
        "import openai",
        "from openai",
        "chromadb",
        "streamlit",
        "persistentclient",
        "embeddings.create",
    ):
        assert forbidden not in source
