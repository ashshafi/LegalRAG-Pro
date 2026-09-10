from __future__ import annotations

from pathlib import Path

from marriage_document_extraction.explicit_recovery import (
    reconcile_source_explicit_facts,
    recover_source_explicit_fact_payloads,
)


def by_field(text: str):
    result = recover_source_explicit_fact_payloads(text)
    return {
        item["field"]: item
        for item in result
    }


def test_urdu_item_1_ward_is_recovered_without_ai():
    text = (
        "\u06f1\u06d4 "
        "\u0648\u0627\u0631\u0688 "
        "\u06a9\u0627 \u0646\u0627\u0645 "
        "\u06f2\u06f0\u06f3\u060c "
        "\u06cc\u0648\u0646\u06cc\u0646 [unclear]\n"
    )

    facts = by_field(text)

    assert facts["marriage_locality_or_district"]["value"] == "Ward 203"
    assert facts["marriage_locality_or_district"]["derivation_kind"] == (
        "ocr_derived"
    )


def test_explicit_date_and_partial_local_authority_are_recovered():
    text = (
        "[unclear]\n"
        "Council\n"
        "Buksh Town\n"
        "Govt Lahore\n"
        "02/10/09\n"
        "\u06f1\u06f3\u06d4 [unclear]\n"
    )

    facts = by_field(text)

    assert facts["additional_date"]["value"] == "02/10/09"
    assert facts["union_council_or_local_authority"]["value"] == (
        "Council | Buksh Town | Govt Lahore"
    )
    assert "exact council designation is incomplete" in (
        facts["union_council_or_local_authority"]["quality_note"]
    )


def test_labelled_registration_date_is_not_demoted_to_other_date():
    text = "Date of Registration of Marriage 12-8-2000"

    facts = recover_source_explicit_fact_payloads(text)

    assert any(
        item["field"] == "registration_date"
        and item["value"] == "12-8-2000"
        for item in facts
    )
    assert not any(
        item["field"] == "additional_date"
        and item["value"] == "12-8-2000"
        for item in facts
    )


def test_registration_number_requires_an_explicit_label():
    labelled = by_field("Registration No: 123/2000")
    unlabelled = by_field("Reference text 123/2000")

    assert labelled["registration_number"]["value"] == "123/2000"
    assert "registration_number" not in unlabelled


def test_language_mix_ignores_unclear_control_marker():
    urdu_only = (
        "[unclear]\n"
        "\u0646\u06a9\u0627\u062d \u0646\u0627\u0645\u06c1\n"
    )
    mixed = (
        "\u0646\u06a9\u0627\u062d \u0646\u0627\u0645\u06c1\n"
        "Govt Lahore\n"
    )

    assert by_field(urdu_only)["document_language_mix"]["value"] == "Urdu"
    assert by_field(mixed)["document_language_mix"]["value"] == (
        "Urdu and English"
    )


def test_single_bare_council_line_is_not_enough_for_authority_fact():
    facts = by_field("Council\n")
    assert "union_council_or_local_authority" not in facts


def test_plain_english_fixture_does_not_create_language_fact():
    facts = by_field("approved transcription")
    assert "document_language_mix" not in facts


def test_source_explicit_facts_precede_ai_interpretation():
    payload = {
        "document_type": "nikah_nama",
        "document_label": "fragment",
        "facts": [
            {
                "field": "additional_date",
                "value": "02/10/09",
                "derivation_kind": "inferred",
                "quality_note": "AI interpretation.",
            },
            {
                "field": "marriage_locality_or_district",
                "value": "Model locality",
                "derivation_kind": "inferred",
                "quality_note": "AI interpretation.",
            },
        ],
        "ai_assisted_english_translation": None,
        "plain_english_explanation": None,
        "potential_issues": [],
        "next_professional_actions": [],
    }

    text = (
        "\u06f1\u06d4 "
        "\u0648\u0627\u0631\u0688 "
        "\u06a9\u0627 \u0646\u0627\u0645 "
        "\u06f2\u06f0\u06f3\n"
        "02/10/09\n"
    )

    reconciled = reconcile_source_explicit_facts(payload, text)

    assert reconciled["facts"][0]["field"] == (
        "marriage_locality_or_district"
    )
    assert reconciled["facts"][0]["value"] == "Ward 203"
    assert any(
        item["field"] == "marriage_locality_or_district"
        and item["value"] == "Model locality"
        for item in reconciled["facts"]
    )


def test_service_reconciles_explicit_source_facts_after_numbered_items():
    text = Path(
        "src/marriage_document_extraction/service.py"
    ).read_text(encoding="utf-8")

    numbered_call = text.index(
        "payload = _reconcile_numbered_nikah_conditions("
    )
    explicit_call = text.index(
        "payload = reconcile_source_explicit_facts(",
        numbered_call,
    )

    assert numbered_call < explicit_call
    assert "validate_extraction_payload(payload)" in text[explicit_call:]


def test_solicitor_ui_has_no_case_specific_date_or_fixed_recommendation():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")

    assert "02/10/09" not in text
    assert "item 21 and the date" not in text
    assert "enumerate(workspace.actions, start=1)" in text
    assert "st.columns([5, 1.5])" in text


def test_workspace_generates_date_action_from_current_fact_value():
    text = Path(
        "src/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")

    assert (
        'f"Check what the date {additional_date.value} relates to '
        'against the original page."'
        in text
    )


def test_workspace_prefers_source_explicit_fact_across_fragments():
    from marriage_document_intelligence import (
        MarriageDocumentIntelligenceRecord,
        MarriageDocumentType,
        MarriageFact,
        MarriageFactDerivationKind,
        MarriageFactField,
        MarriageFactProvenance,
        SourceRegion,
    )
    from marriage_document_workspace import (
        build_marriage_document_workspace,
    )

    def record(candidate: str, value: str, note: str):
        provenance = MarriageFactProvenance(
            source_document_instance_id="doc-a",
            source_snapshot_id="snap-a",
            original_filename="marriage.pdf",
            original_blob_sha256="a" * 64,
            page_number=5,
            candidate_record_id="sha256:" + candidate * 64,
            transcription_sha256=candidate * 64,
            review_event_id="sha256:" + "f" * 64,
            derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
            quality_note=note,
            binding_id="sha256:" + "d" * 64,
            publication_receipt_id="sha256:" + "e" * 64,
            crop_name="crop-" + candidate,
            bbox=SourceRegion(left=1, top=1, right=10, bottom=10),
        )
        return MarriageDocumentIntelligenceRecord.create(
            document_type=MarriageDocumentType.NIKAH_NAMA,
            document_label="fragment-" + candidate,
            facts=(
                MarriageFact(
                    field=(
                        MarriageFactField
                        .MARRIAGE_LOCALITY_OR_DISTRICT
                    ),
                    value=value,
                    provenance=provenance,
                ),
            ),
        )

    ai_first = record(
        "1",
        "Buksh Town",
        "AI semantic extraction from the approved transcription.",
    )
    direct_second = record(
        "2",
        "Ward 203",
        (
            "Ward number recovered directly from Nikah Nama item 1 "
            "in the approved transcription."
        ),
    )

    workspace = build_marriage_document_workspace(
        (ai_first, direct_second)
    )

    locality = next(
        item
        for item in workspace.particulars
        if item.label == "Locality / district"
    )
    assert locality.value == "Ward 203"


def test_workspace_keeps_first_candidate_when_none_is_source_explicit():
    from types import SimpleNamespace

    import marriage_document_workspace as workspace_module
    from marriage_document_intelligence import MarriageFactField

    field = MarriageFactField.MARRIAGE_LOCALITY_OR_DISTRICT

    first = SimpleNamespace(
        field=field,
        value="First",
        provenance=SimpleNamespace(
            quality_note="AI extraction."
        ),
    )
    second = SimpleNamespace(
        field=field,
        value="Second",
        provenance=SimpleNamespace(
            quality_note="Another AI extraction."
        ),
    )

    assert workspace_module._first_fact(
        (first, second),
        field,
    ) is first


def test_solicitor_ui_does_not_duplicate_translator_recommendation():
    ui = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")
    workspace = Path(
        "src/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")

    assert "obtain one from a suitably qualified translator" not in ui
    assert (
        workspace.count(
            "Use a qualified translator if a certified English "
            "translation is required."
        )
        == 1
    )

