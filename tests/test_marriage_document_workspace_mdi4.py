from __future__ import annotations

from pathlib import Path

from marriage_document_workspace import build_marriage_document_workspace
from marriage_document_intelligence import (
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
    SourceRegion,
)


def sha_hex(char: str) -> str:
    return char * 64


def sha_id(char: str) -> str:
    return "sha256:" + sha_hex(char)


def make_record(candidate: str, facts):
    provenance = MarriageFactProvenance(
        source_document_instance_id="doc-1",
        source_snapshot_id="snap-1",
        original_filename="marriage.pdf",
        original_blob_sha256=sha_hex("a"),
        page_number=5,
        candidate_record_id=sha_id(candidate),
        transcription_sha256=sha_hex(candidate),
        review_event_id=sha_id("f"),
        derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
        quality_note="Recorded answer is 'No'.",
        binding_id=sha_id("d"),
        publication_receipt_id=sha_id("e"),
        crop_name="internal_crop",
        bbox=SourceRegion(left=1, top=1, right=10, bottom=10),
    )
    return MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="fragment",
        facts=tuple(
            MarriageFact(
                field=field,
                value=value,
                provenance=provenance,
            )
            for field, value in facts
        ),
    )


def test_current_core_projection_still_summarises_conditions():
    value = make_record(
        "1",
        (
            (
                MarriageFactField.SPECIAL_CONDITION,
                "18 source text",
            ),
            (
                MarriageFactField.MARRIAGE_LOCALITY_OR_DISTRICT,
                "Ward 203",
            ),
        ),
    )
    workspace = build_marriage_document_workspace((value,))
    assert len(workspace.special_conditions) == 1
    assert workspace.special_conditions[0].item_number == "18"
    assert workspace.special_conditions[0].recorded_answer == "No"
    assert workspace.particulars[0].value == "Ward 203"


def test_ui_is_compact_and_uses_no_dataframe():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")
    assert "st.dataframe" not in text
    assert "Nikah Nama review" in text
    assert "What this page shows" in text
    assert "Conditions recorded on the Nikah Nama" in text
    assert "Important details not yet recovered" in text
    assert "What needs checking" in text
    assert "Recommended next step" in text


def test_ui_has_no_technical_audit_block():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")
    assert 'st.expander("Audit trail")' not in text
    assert "source_blob_sha256=" not in text
    assert "candidate_record_ids=" not in text
    assert "crop_names=" not in text


def test_ui_does_not_render_raw_source_language_special_condition():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")
    assert "condition.subject" in text
    assert "condition.recorded_answer" in text
    assert "condition.value" not in text
    assert "fact.value" not in text


def test_ui_copy_avoids_known_mojibake_markers_and_problem_unicode():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")

    for bad in (
        "Ã¢",
        "Ãƒ",
        "Ã›",
        "Ã™",
        "\u2022",
        "\u2014",
        "\u2013",
    ):
        assert bad not in text


def test_single_source_comparison_is_not_rendered():
    text = Path(
        "src/ui/marriage_document_workspace.py"
    ).read_text(encoding="utf-8")
    assert "Compare documents" not in text
    assert "field_comparisons" not in text


def test_preview_title_is_nikah_nama_review():
    text = Path(
        "src/mdi_workspace_preview.py"
    ).read_text(encoding="utf-8")
    assert 'page_title="Nikah Nama review"' in text
