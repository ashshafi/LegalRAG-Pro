from __future__ import annotations

from marriage_document_comparison import (
    MarriageDocumentComparisonError,
    build_source_profiles,
    compare_marriage_document_records,
)
from marriage_document_intelligence import (
    MarriageComparisonStatus,
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
)


def sha_hex(char: str) -> str:
    return char * 64


def sha_id(char: str) -> str:
    return "sha256:" + sha_hex(char)


def provenance(
    *,
    blob: str,
    candidate_char: str,
    filename: str,
    crop: str,
) -> MarriageFactProvenance:
    return MarriageFactProvenance(
        source_document_instance_id="doc-" + blob[:4],
        source_snapshot_id="snapshot-" + blob[:4],
        original_filename=filename,
        original_blob_sha256=blob,
        page_number=1,
        candidate_record_id=sha_id(candidate_char),
        transcription_sha256=sha_hex(candidate_char),
        review_event_id=sha_id("f"),
        derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
        quality_note="Test extraction.",
        binding_id=sha_id("d"),
        publication_receipt_id=sha_id("e"),
        crop_name=crop,
        bbox=__import__(
            "marriage_document_intelligence",
            fromlist=["SourceRegion"],
        ).SourceRegion(left=1, top=1, right=20, bottom=20),
    )


def record(
    *,
    blob: str,
    candidate_char: str,
    filename: str,
    crop: str,
    facts: tuple[tuple[MarriageFactField, str], ...],
) -> MarriageDocumentIntelligenceRecord:
    source = provenance(
        blob=blob,
        candidate_char=candidate_char,
        filename=filename,
        crop=crop,
    )
    return MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label=filename,
        facts=tuple(
            MarriageFact(
                field=field,
                value=value,
                provenance=source,
            )
            for field, value in facts
        ),
    )


def test_same_original_blob_fragments_are_one_source_profile():
    blob = sha_hex("a")
    left = record(
        blob=blob,
        candidate_char="1",
        filename="one.pdf",
        crop="left",
        facts=((MarriageFactField.BRIDE_NAME, "Aisha"),),
    )
    right = record(
        blob=blob,
        candidate_char="2",
        filename="one.pdf",
        crop="right",
        facts=((MarriageFactField.GROOM_NAME, "Ahmed"),),
    )

    profiles = build_source_profiles((left, right))
    assert len(profiles) == 1
    assert set(profiles[0].crop_names) == {"left", "right"}
    assert len(profiles[0].facts) == 2


def test_same_source_missing_crop_fact_is_not_a_discrepancy():
    blob = sha_hex("a")
    left = record(
        blob=blob,
        candidate_char="1",
        filename="one.pdf",
        crop="left",
        facts=((MarriageFactField.BRIDE_NAME, "Aisha"),),
    )
    right = record(
        blob=blob,
        candidate_char="2",
        filename="one.pdf",
        crop="right",
        facts=((MarriageFactField.GROOM_NAME, "Ahmed"),),
    )

    result = compare_marriage_document_records((left, right))
    assert len(result.source_profiles) == 1
    assert result.field_comparisons == ()
    assert "complementary fragments/crops" in result.potential_issues[0]


def test_exact_value_across_independent_sources_is_exact_match():
    one = record(
        blob=sha_hex("a"),
        candidate_char="1",
        filename="nikah.pdf",
        crop="one",
        facts=((MarriageFactField.REGISTRATION_NUMBER, "123/2000"),),
    )
    two = record(
        blob=sha_hex("b"),
        candidate_char="2",
        filename="uc.pdf",
        crop="two",
        facts=((MarriageFactField.REGISTRATION_NUMBER, "123/2000"),),
    )

    result = compare_marriage_document_records((one, two))
    comparison = result.field_comparisons[0]
    assert comparison.field is MarriageFactField.REGISTRATION_NUMBER
    assert comparison.status is MarriageComparisonStatus.EXACT_MATCH


def test_name_spelling_variation_is_conservative_fuzzy_match():
    one = record(
        blob=sha_hex("a"),
        candidate_char="1",
        filename="nikah.pdf",
        crop="one",
        facts=((MarriageFactField.GROOM_NAME, "Muhammad Arshad"),),
    )
    two = record(
        blob=sha_hex("b"),
        candidate_char="2",
        filename="certificate.pdf",
        crop="two",
        facts=((MarriageFactField.GROOM_NAME, "Mohammad Arshad"),),
    )

    result = compare_marriage_document_records((one, two))
    comparison = result.field_comparisons[0]
    assert comparison.status is (
        MarriageComparisonStatus.LIKELY_TRANSLITERATION_VARIATION
    )


def test_distinct_registration_numbers_are_possible_inconsistency_not_material_contradiction():
    one = record(
        blob=sha_hex("a"),
        candidate_char="1",
        filename="nikah.pdf",
        crop="one",
        facts=((MarriageFactField.REGISTRATION_NUMBER, "123/2000"),),
    )
    two = record(
        blob=sha_hex("b"),
        candidate_char="2",
        filename="certificate.pdf",
        crop="two",
        facts=((MarriageFactField.REGISTRATION_NUMBER, "999/2009"),),
    )

    result = compare_marriage_document_records((one, two))
    comparison = result.field_comparisons[0]
    assert comparison.status is MarriageComparisonStatus.POSSIBLE_INCONSISTENCY
    assert comparison.status is not MarriageComparisonStatus.MATERIAL_CONTRADICTION
    assert any(
        "does not automatically decide" in issue
        for issue in result.potential_issues
    )


def test_missing_extraction_across_independent_sources_is_unresolved_not_absence():
    one = record(
        blob=sha_hex("a"),
        candidate_char="1",
        filename="nikah.pdf",
        crop="one",
        facts=((MarriageFactField.MARRIAGE_DATE, "1 January 2000"),),
    )
    two = record(
        blob=sha_hex("b"),
        candidate_char="2",
        filename="certificate.pdf",
        crop="two",
        facts=((MarriageFactField.BRIDE_NAME, "Aisha"),),
    )

    result = compare_marriage_document_records((one, two))
    by_field = {
        item.field: item
        for item in result.field_comparisons
    }
    assert by_field[MarriageFactField.MARRIAGE_DATE].status is (
        MarriageComparisonStatus.UNRESOLVED_OR_UNCLEAR
    )
    assert "Non-extraction is not proof" in (
        by_field[MarriageFactField.MARRIAGE_DATE].summary
    )


def test_document_language_mix_is_not_compared_as_marriage_discrepancy():
    one = record(
        blob=sha_hex("a"),
        candidate_char="1",
        filename="nikah.pdf",
        crop="one",
        facts=((MarriageFactField.DOCUMENT_LANGUAGE_MIX, "Urdu"),),
    )
    two = record(
        blob=sha_hex("b"),
        candidate_char="2",
        filename="certificate.pdf",
        crop="two",
        facts=((MarriageFactField.DOCUMENT_LANGUAGE_MIX, "English and Urdu"),),
    )

    result = compare_marriage_document_records((one, two))
    assert result.field_comparisons == ()


def test_comparison_requires_source_provenance():
    empty = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="empty",
        facts=(),
    )
    try:
        compare_marriage_document_records((empty,))
    except MarriageDocumentComparisonError as exc:
        assert "source provenance" in str(exc)
    else:
        raise AssertionError("Expected provenance failure.")


def test_comparison_package_has_no_provider_or_chroma_dependency():
    import pathlib
    import marriage_document_comparison

    root = pathlib.Path(marriage_document_comparison.__file__).parent
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.py"))
    ).lower()

    for forbidden in (
        "openai",
        "chromadb",
        "persistentclient",
        "responses.create",
        "embeddings.create",
    ):
        assert forbidden not in text
