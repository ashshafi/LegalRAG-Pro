from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from marriage_document_comparison.models import MarriageDocumentComparisonResult
from marriage_document_intelligence import (
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
    SourceRegion,
)
from marriage_document_source_native import (
    SourceEvidenceNativePage,
    SourceEvidenceNativeProvenance,
    bridge_native_facts_into_workspace,
    extract_source_evidence_native_marriage_facts,
)
from marriage_document_workspace import (
    build_marriage_document_workspace,
)


def provenance(page: int) -> SourceEvidenceNativeProvenance:
    char = str(page)
    return SourceEvidenceNativeProvenance(
        source_document_instance_id="doc-source-1",
        source_snapshot_id="sha256:" + "a" * 64,
        original_filename="marriage.pdf",
        original_blob_sha256="b" * 64,
        page_number=page,
        page_text_sha256=char * 64,
        page_text_byte_length=100,
        extraction_method="pypdf_text",
        quality_note="Exact governed native text.",
    )


def page(number: int, text: str) -> SourceEvidenceNativePage:
    return SourceEvidenceNativePage(
        provenance=provenance(number),
        text=text,
    )


def synthetic_pages():
    return (
        page(
            2,
            """
            2. Name of the bridegroom & his father with their respective
            residence Example Groom S/o Example Father Example Address
            4. Name of the bride & her father with their respective residence
            Example Bride D/o Example Father Example Address
            11. Name of the witnesses to the marriage, with residences
            (1) Witness One S/o Parent One Address
            (2) Witness Two S/o Parent Two Address
            12. Date on which the marriage was contracted 12 August 2000 AD
            13. Amount of dower 5,000/- rupees [Seal: Illegible]
            """,
        ),
        page(
            3,
            """
            Total has been paid at the time of marriage.
            person by whom the marriage was solemnized
            Example Registrar, Example Address
            24. Date of Registration of Marriage 12-8-2000
            25. Registration Fee Paid As per the rule
            """,
        ),
        page(
            4,
            """
            Signature and seal of marriage registrar
            [Signature]
            [Nazim Chairman Arbitration Council
            No. 80 Example Hall Example Town City District]
            02/10/09
            """,
        ),
    )


def _sha_id(char: str) -> str:
    return "sha256:" + char * 64


def _candidate_provenance(
    candidate_char: str,
    *,
    quality_note: str,
) -> MarriageFactProvenance:
    return MarriageFactProvenance(
        source_document_instance_id="doc-source-1",
        source_snapshot_id="sha256:" + "a" * 64,
        original_filename="marriage.pdf",
        original_blob_sha256="b" * 64,
        page_number=5,
        candidate_record_id=_sha_id(candidate_char),
        transcription_sha256=candidate_char * 64,
        review_event_id=_sha_id("f"),
        derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
        quality_note=quality_note,
        binding_id=_sha_id("d"),
        publication_receipt_id=_sha_id("e"),
        crop_name="internal_crop_" + candidate_char,
        bbox=SourceRegion(
            left=1,
            top=1,
            right=10,
            bottom=10,
        ),
    )


def _record(
    candidate_char: str,
    facts,
) -> MarriageDocumentIntelligenceRecord:
    material = []
    for field, value, note in facts:
        material.append(
            MarriageFact(
                field=field,
                value=value,
                provenance=_candidate_provenance(
                    candidate_char,
                    quality_note=note,
                ),
            )
        )
    return MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType.NIKAH_NAMA,
        document_label="synthetic approved fragment",
        facts=tuple(material),
    )


def synthetic_base_workspace():
    records = (
        _record(
            "1",
            (
                (
                    MarriageFactField.SPECIAL_CONDITION,
                    "21 source text",
                    "Recorded answer is 'No'. Part of this item is unclear.",
                ),
            ),
        ),
        _record(
            "2",
            (
                (
                    MarriageFactField.MARRIAGE_LOCALITY_OR_DISTRICT,
                    "Ward 203",
                    "Readable approved fragment.",
                ),
            ),
        ),
        _record(
            "3",
            (
                (
                    MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
                    "Example Council",
                    "Readable approved fragment.",
                ),
            ),
        ),
    )
    workspace = build_marriage_document_workspace(records)
    assert workspace.approved_fragment_count == 3
    return workspace


def test_native_provenance_has_no_candidate_or_crop_identity_fields():
    names = {field.name for field in fields(SourceEvidenceNativeProvenance)}
    for forbidden in (
        "candidate_record_id",
        "transcription_sha256",
        "review_event_id",
        "binding_id",
        "publication_receipt_id",
        "crop_name",
        "bbox",
    ):
        assert forbidden not in names


def test_deterministic_native_extraction_recovers_core_fields():
    facts = extract_source_evidence_native_marriage_facts(
        synthetic_pages()
    )
    fields_present = {item.field for item in facts}

    for expected in (
        MarriageFactField.BRIDE_NAME,
        MarriageFactField.GROOM_NAME,
        MarriageFactField.MARRIAGE_DATE,
        MarriageFactField.MEHR_PROMPT_AMOUNT,
        MarriageFactField.WITNESS_NAME,
        MarriageFactField.NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL,
        MarriageFactField.REGISTRATION_DATE,
        MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
    ):
        assert expected in fields_present


def test_two_marriage_witnesses_are_preserved():
    facts = extract_source_evidence_native_marriage_facts(
        synthetic_pages()
    )
    witnesses = [
        item
        for item in facts
        if item.field is MarriageFactField.WITNESS_NAME
    ]
    assert [item.value for item in witnesses] == [
        "Witness One",
        "Witness Two",
    ]


def test_prompt_mehr_requires_source_payment_signal():
    pages = list(synthetic_pages())
    pages[1] = page(
        3,
        """
        person by whom the marriage was solemnized
        Example Registrar
        24. Date of Registration of Marriage 12-8-2000
        25. Registration Fee Paid As per the rule
        """,
    )
    facts = extract_source_evidence_native_marriage_facts(
        tuple(pages)
    )
    assert all(
        item.field is not MarriageFactField.MEHR_PROMPT_AMOUNT
        for item in facts
    )


def test_bridge_preserves_candidate_fragment_count_and_conditions():
    base = synthetic_base_workspace()
    result = bridge_native_facts_into_workspace(
        base_workspace=base,
        native_facts=extract_source_evidence_native_marriage_facts(
            synthetic_pages()
        ),
    )

    assert result.workspace.approved_fragment_count == 3
    assert result.workspace.special_conditions == base.special_conditions
    item21 = [
        item
        for item in result.workspace.special_conditions
        if item.item_number == "21"
    ][0]
    assert item21.recorded_answer == "No"
    assert item21.verification_required is True


def test_bridge_reduces_missing_without_fabricating_registration_number():
    base = synthetic_base_workspace()
    result = bridge_native_facts_into_workspace(
        base_workspace=base,
        native_facts=extract_source_evidence_native_marriage_facts(
            synthetic_pages()
        ),
    )

    assert len(result.workspace.missing_core_particulars) < len(
        base.missing_core_particulars
    )
    assert any(
        "registration number" in value.casefold()
        for value in result.workspace.missing_core_particulars
    )
    assert all(
        item.field is not MarriageFactField.REGISTRATION_NUMBER
        for item in result.native_facts
    )


def test_bridge_adds_native_pages_without_fake_candidate_ids():
    base = synthetic_base_workspace()
    before_ids = tuple(
        value
        for source in base.sources
        for value in source.candidate_record_ids
    )

    result = bridge_native_facts_into_workspace(
        base_workspace=base,
        native_facts=extract_source_evidence_native_marriage_facts(
            synthetic_pages()
        ),
    )

    after_ids = tuple(
        value
        for source in result.workspace.sources
        for value in source.candidate_record_ids
    )

    assert after_ids == before_ids
    assert result.native_pages == (2, 3, 4)
    assert {2, 3, 4}.issubset(
        {
            value
            for source in result.workspace.sources
            for value in source.pages
        }
    )


def test_bridge_module_has_no_network_ocr_chroma_or_persistence_write_path():
    path = Path("src/marriage_document_source_native.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    imports = set()
    dangerous_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call) and isinstance(
            node.func,
            ast.Attribute,
        ):
            attr = node.func.attr
            receiver = ast.unparse(node.func.value).casefold()

            if attr in {
                "put_blob",
                "publish_document_manifest",
                "publish_evidence_binding",
                "publish_analysis_receipt",
                "publish_projection_binding",
            }:
                dangerous_calls.append(
                    receiver + "." + attr
                )

            if (
                attr in {"add", "upsert", "update", "delete"}
                and any(
                    marker in receiver
                    for marker in (
                        "chroma",
                        "collection",
                        "persistentclient",
                        "vector",
                    )
                )
            ):
                dangerous_calls.append(
                    receiver + "." + attr
                )

    forbidden_import_roots = {
        "openai",
        "chromadb",
        "pytesseract",
        "pdf2image",
    }
    assert not {
        item.split(".", 1)[0]
        for item in imports
    }.intersection(forbidden_import_roots)

    assert dangerous_calls == []
