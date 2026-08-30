from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import ast
import hashlib
import json

import pytest

from derived_transcription_search import (
    DERIVED_SEARCH_AUTHORITY_KIND,
    DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION,
    DERIVED_SEARCH_COLLECTION_NAME,
    DERIVED_SEARCH_ROW_SCHEMA_VERSION,
    EXPECTED_ROW_METADATA_KEYS,
    FORBIDDEN_SOURCE_LANE_METADATA,
    build_collection_add_payload,
    derive_candidate_id,
    prepare_candidate,
    prepare_row,
    validate_candidate,
    validate_row,
)


WORKSPACE = (
    Path(__file__)
    .resolve()
    .parents[1]
)

FIXTURE_RECORD_BYTES = b'{"case_id":"9e10cd5a-00fd-484e-938d-b5c3358c8dae","embedded_image_byte_length":173409,"embedded_image_height":1562,"embedded_image_name":"Image5.jpg","embedded_image_sha256":"99341c618aa14897646c2b950a40ac31ed67508f506ab324efb9ba95e03baaf4","embedded_image_width":1127,"image_selection_id":"pypdf-page-single-embedded-image/1.0","ocr_language":"eng","ocr_psm":6,"original_blob_sha256":"a759591d9dbc464ec717c918e5199fab2e644f05c414c15b95c5738d64d083a1","original_byte_length":199340,"original_filename":"NADRA-issued Marriage Certificate  NS(Exhibit 1).pdf","page_number":1,"pillow_package_version":"12.3.0","preprocessing_steps":["PIL.Image.convert:RGB","PIL.ImageOps.grayscale","PIL.ImageOps.autocontrast:cutoff=0","PIL.ImageFilter.SHARPEN"],"profile_id":"photo-embedded-image-ocr/1.0","profile_schema_version":"1.0","pypdf_package_version":"6.14.2","pytesseract_package_version":"0.3.13","record_id":"sha256:cc877d9425f688e3a7beef71f3ca6b75c8ca74d05034a498b138f4f3729132ac","schema_version":"derived-transcription-record/1.0","source_document_instance_id":"614f7017-2aab-5c59-ab16-bf4786699073","source_extraction_method":"page_ocr","source_page_text_byte_length":0,"source_page_text_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","source_snapshot_id":"sha256:51399667df2fa233c897f99a09c5804068c00f8eb7b23a2d8a0b16b1bc481434","tesseract_command":"C:\\\\Program Files\\\\Tesseract-OCR\\\\tesseract.exe","tesseract_engine_version":"5.5.3.20260724","tesseract_executable_sha256":"c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420","transcription_byte_length":1661,"transcription_sha256":"4eaed7f82e463dafea5825c4aa3dd032ab6883151bb451d0b5c80365a60144fb"}'

FIXTURE_TRANSCRIPTION_BYTES = b"2)\niach fe WA he CL nie\nZN) oe DG eel\nSS B \xe2\x80\x9d GOVERNMENT OF THE PUNJAB PAKISTAN \xe2\x80\x99\nSd si yu gilts | C184 Clos\nTracking Idi 91100072711870, ee 7 Ff WA F\nMarriage Registration Certificate | SANTINAGAR 300660 :\xc2\xa2 yall iB\nCRMS Noi! 115977569\n; a Od GRIMS No.\nLEM BEG Particulars of Groom hiss 5 Wels ;\nName + Arshad Shafi ete a +l\nNationality : Pakistani cis PREY EC}\nGNIC No: IG EO |\nReligion : Islam aku poyhe\nin A\nAge? 38 Year(s) ue eee 5. ma\nMarital Status: \xc2\xa9 Unmarried pad gal ye; Cina (9) 945) |\nFather's Name: Muhammad Shafi eee a eleelip\nPassport No NOT AVALIBLE NOT AVALIBLE Pes anely\n\xe2\x80\x98Address: 47 ARGAL ROAD WEST EALING LONDON W 13 AT oA dol ol 13 5208 Cd SAU Cass 5 LI py\nO.L.W UK City London , Area/Province West oe\nEaling , Country United Kingdom\nParticulars of Bride Gils 25 ods\nName: Nabila Shafi qed tei raul\nNationality : Pakistani piles pease\nCNICNo: 91400-0732453-3 91400-0732453-3 pas us\nReligion : islam ual 2 cide\nAge: 22 Year(s) du 22 Be\nMarital Status: Unmarried 5 odd galas se 5 Cre (2) 545)\nFather'sName: Chaudhary Muhammad Afzal Quai tana gytnga PUK ily\nPassport No NOT AVAILABL NOT AVAILABL 2 2 Sy yhals\n\xe2\x80\x98Address: HOUSE NO 13 NEAR CIVIL DEFEAR OUTFALL JH oe Spy JE Cis) gts 48 13 geal ole pay\nROAD City Lahore\nTehsil : Lahore City ony gies\nDistrict : lahore ost 1 gle\nMarriage Date : 12-Aug-2000 12-Aug-2000: GUUS Gila / cls\nMarriage Solemnized/Registered By Qari Muhammad Amin Gul wae GE esa atk | aay css\nMarriage Solemnized/Registered By CNIC No: op YS GUE LS i teen Gal / i tas CL fold I\nEntryDate: 16-Sep-2025 16-Sep-2025 gual aut\nIssueDate:  17-Sep-202 lite ell 17-Sep-2025: sal Gut\nos Ene\n58 sl Julys Only Ge rs\nOyhY 83 Gs\n"

class _ImmutableFixtureFile:
    __slots__ = ("_raw", "_sealed")

    def __init__(self, raw: bytes):
        object.__setattr__(self, "_raw", bytes(raw))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("fixture file is immutable")
        object.__setattr__(self, name, value)

    def is_file(self):
        return True

    def read_bytes(self):
        return self._raw

    def read_text(self, encoding="utf-8", errors="strict"):
        return self._raw.decode(encoding, errors)

AUTHORITY = None

CASE_ID = "9e10cd5a-00fd-484e-938d-b5c3358c8dae"
DOCUMENT_ID = "614f7017-2aab-5c59-ab16-bf4786699073"
PAGE_NUMBER = 1

DERIVED_RECORD_ID = "sha256:cc877d9425f688e3a7beef71f3ca6b75c8ca74d05034a498b138f4f3729132ac"
TRANSCRIPTION_SHA256 = "4eaed7f82e463dafea5825c4aa3dd032ab6883151bb451d0b5c80365a60144fb"
TRANSCRIPTION_BYTES = 1661

EMPTY_SOURCE_TEXT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
EMBEDDED_IMAGE_SHA256 = "99341c618aa14897646c2b950a40ac31ed67508f506ab324efb9ba95e03baaf4"

RECORD_PATH = _ImmutableFixtureFile(FIXTURE_RECORD_BYTES)

TRANSCRIPTION_PATH = _ImmutableFixtureFile(FIXTURE_TRANSCRIPTION_BYTES)


def authority():
    record = json.loads(
        RECORD_PATH.read_text(
            encoding="utf-8"
        )
    )

    raw = TRANSCRIPTION_PATH.read_bytes()

    text = raw.decode(
        "utf-8",
        errors="strict",
    )

    return (
        record,
        raw,
        text,
    )


def prepared():
    record, _, text = authority()

    candidate = prepare_candidate(
        record=record,
        transcription_text=text,
    )

    row = prepare_row(
        candidate=candidate,
        transcription_text=text,
    )

    return (
        record,
        text,
        candidate,
        row,
    )


class FakeCollection:
    def __init__(self):
        self.calls = []

    def add(
        self,
        *,
        ids,
        documents,
        metadatas,
    ):
        self.calls.append(
            {
                "ids":
                    list(ids),

                "documents":
                    list(documents),

                "metadatas":
                    [
                        dict(item)
                        for item in metadatas
                    ],
            }
        )


def test_authority_fixture_is_exact_retained_c2_output():
    record, raw, _ = authority()

    assert RECORD_PATH.is_file()
    assert TRANSCRIPTION_PATH.is_file()

    assert record["case_id"] == CASE_ID

    assert (
        record["source_document_instance_id"]
        == DOCUMENT_ID
    )

    assert (
        record["record_id"]
        == DERIVED_RECORD_ID
    )

    assert (
        record["transcription_sha256"]
        == TRANSCRIPTION_SHA256
    )

    assert (
        record["transcription_byte_length"]
        == TRANSCRIPTION_BYTES
    )

    assert len(raw) == TRANSCRIPTION_BYTES

    assert (
        hashlib.sha256(
            raw
        ).hexdigest()
        == TRANSCRIPTION_SHA256
    )

    assert (
        record["source_page_text_sha256"]
        == EMPTY_SOURCE_TEXT_SHA256
    )

    assert (
        record["source_page_text_byte_length"]
        == 0
    )

    assert (
        record["embedded_image_sha256"]
        == EMBEDDED_IMAGE_SHA256
    )


def test_candidate_foundation_has_distinct_authority_names():
    assert (
        DERIVED_SEARCH_AUTHORITY_KIND
        == "derived_transcription"
    )

    assert (
        DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION
        == "derived-transcription-search-candidate/1.0"
    )

    assert (
        DERIVED_SEARCH_ROW_SCHEMA_VERSION
        == "derived-transcription-search-row/1.0"
    )

    assert (
        DERIVED_SEARCH_COLLECTION_NAME
        == "derived_transcriptions_v1"
    )

    assert (
        DERIVED_SEARCH_COLLECTION_NAME
        != "legal_documents"
    )


def test_candidate_is_deterministic_for_exact_retained_record():
    record, _, text = authority()

    first = prepare_candidate(
        record=record,
        transcription_text=text,
    )

    second = prepare_candidate(
        record=record,
        transcription_text=text,
    )

    assert first == second

    assert (
        first.candidate_id
        == second.candidate_id
    )

    assert (
        first.candidate_id
        == derive_candidate_id(
            first
        )
    )


def test_candidate_identity_uses_separate_namespace():
    _, _, candidate, _ = prepared()

    assert candidate.candidate_id.startswith(
        "dtx:sha256:"
    )

    assert not candidate.candidate_id.startswith(
        "sha256:"
    )

    assert (
        candidate.candidate_id
        != candidate.derived_record_id
    )


def test_candidate_preserves_source_and_derived_coordinates():
    _, _, candidate, _ = prepared()

    assert candidate.case_id == CASE_ID

    assert (
        candidate.source_document_instance_id
        == DOCUMENT_ID
    )

    assert candidate.page_number == PAGE_NUMBER

    assert (
        candidate.derived_record_id
        == DERIVED_RECORD_ID
    )

    assert (
        candidate.transcription_sha256
        == TRANSCRIPTION_SHA256
    )

    assert (
        candidate.source_page_text_sha256
        == EMPTY_SOURCE_TEXT_SHA256
    )

    assert (
        candidate.source_page_text_byte_length
        == 0
    )

    assert (
        candidate.transcription_sha256
        != candidate.source_page_text_sha256
    )


def test_candidate_retains_derived_provenance_not_source_binding_claim():
    _, _, candidate, _ = prepared()

    assert (
        candidate.authority_kind
        == "derived_transcription"
    )

    assert (
        candidate.profile_id
        == "photo-embedded-image-ocr/1.0"
    )

    assert candidate.ocr_language == "eng"

    assert candidate.ocr_psm == 6

    assert (
        candidate.embedded_image_sha256
        == EMBEDDED_IMAGE_SHA256
    )


def test_prepare_candidate_rejects_transcription_content_drift():
    record, _, text = authority()

    with pytest.raises(
        ValueError,
        match="byte length|SHA256",
    ):
        prepare_candidate(
            record=record,
            transcription_text=
                text
                + "x",
        )


def test_prepare_candidate_rejects_record_hash_drift():
    record, _, text = authority()

    changed = dict(
        record
    )

    changed[
        "transcription_sha256"
    ] = (
        "0" * 64
    )

    with pytest.raises(
        ValueError,
        match="SHA256",
    ):
        prepare_candidate(
            record=changed,
            transcription_text=text,
        )


def test_prepare_candidate_rejects_missing_provenance_field():
    record, _, text = authority()

    changed = dict(
        record
    )

    del changed[
        "embedded_image_sha256"
    ]

    with pytest.raises(
        ValueError,
        match="missing required field",
    ):
        prepare_candidate(
            record=changed,
            transcription_text=text,
        )


def test_candidate_validation_rejects_identity_drift():
    _, _, candidate, _ = prepared()

    altered = replace(
        candidate,
        candidate_id=
            "dtx:sha256:"
            + ("0" * 64),
    )

    with pytest.raises(
        ValueError,
        match="canonical derived-search identity",
    ):
        validate_candidate(
            altered
        )


def test_row_is_exact_transcription_not_source_page_text():
    _, text, candidate, row = prepared()

    assert row.row_id == candidate.candidate_id

    assert row.document == text

    assert (
        hashlib.sha256(
            row.document.encode(
                "utf-8"
            )
        ).hexdigest()
        == TRANSCRIPTION_SHA256
    )

    assert (
        row.metadata[
            "source_page_text_sha256"
        ]
        == EMPTY_SOURCE_TEXT_SHA256
    )

    assert (
        row.metadata[
            "derived_transcription_sha256"
        ]
        == TRANSCRIPTION_SHA256
    )


def test_row_metadata_key_set_is_exact():
    _, _, _, row = prepared()

    assert (
        frozenset(
            row.metadata
        )
        == EXPECTED_ROW_METADATA_KEYS
    )


def test_row_contains_no_frozen_source_lane_fields():
    _, _, _, row = prepared()

    assert not (
        frozenset(
            row.metadata
        )
        & FORBIDDEN_SOURCE_LANE_METADATA
    )

    assert (
        "source_binding_class"
        not in row.metadata
    )

    assert (
        "source_evidence_binding_id"
        not in row.metadata
    )

    assert (
        "source_chunk_sha256"
        not in row.metadata
    )

    assert (
        "evidence_key"
        not in row.metadata
    )

    assert (
        "chunk_id"
        not in row.metadata
    )

    assert (
        "source_bound_analysis_receipt_id"
        not in row.metadata
    )


def test_row_metadata_is_immutable():
    _, _, _, row = prepared()

    with pytest.raises(
        TypeError
    ):
        row.metadata[
            "authority_kind"
        ] = "changed"


def test_row_validation_rejects_source_binding_class_injection():
    _, _, _, row = prepared()

    altered = replace(
        row,
        metadata={
            **dict(
                row.metadata
            ),
            "source_binding_class":
                "full_chain_bound",
        },
    )

    with pytest.raises(
        ValueError,
        match="forbidden source-lane",
    ):
        validate_row(
            altered
        )


def test_row_validation_rejects_document_drift():
    _, _, _, row = prepared()

    altered = replace(
        row,
        document=
            row.document
            + "x",
    )

    with pytest.raises(
        ValueError,
        match="byte length|SHA256",
    ):
        validate_row(
            altered
        )


def test_fake_collection_payload_is_chroma_shape_without_importing_chroma():
    _, _, _, row = prepared()

    payload = build_collection_add_payload(
        (
            row,
        )
    )

    assert set(
        payload
    ) == {
        "ids",
        "documents",
        "metadatas",
    }

    fake = FakeCollection()

    fake.add(
        **payload
    )

    assert len(
        fake.calls
    ) == 1

    call = fake.calls[0]

    assert call["ids"] == [
        row.row_id
    ]

    assert call["documents"] == [
        row.document
    ]

    assert call["metadatas"] == [
        dict(
            row.metadata
        )
    ]


def test_collection_payload_rejects_duplicate_derived_identity():
    _, _, _, row = prepared()

    with pytest.raises(
        ValueError,
        match="unique row IDs",
    ):
        build_collection_add_payload(
            (
                row,
                row,
            )
        )


def test_collection_payload_does_not_claim_source_evidence_identity():
    _, _, _, row = prepared()

    payload = build_collection_add_payload(
        (
            row,
        )
    )

    metadata = payload[
        "metadatas"
    ][0]

    assert (
        metadata[
            "authority_kind"
        ]
        == "derived_transcription"
    )

    assert (
        metadata[
            "derived_record_id"
        ]
        == DERIVED_RECORD_ID
    )

    assert (
        "source_binding_class"
        not in metadata
    )

    assert (
        "evidence_key"
        not in metadata
    )


def test_candidate_model_has_no_source_chunk_or_binding_fields():
    _, _, candidate, _ = prepared()

    names = set(
        candidate.__dataclass_fields__
    )

    assert "binding_class" not in names
    assert "bound_text_role" not in names
    assert "evidence_key" not in names
    assert "chunk_id" not in names
    assert "chunk_ordinal" not in names
    assert "evidence_binding_id" not in names


def test_candidate_package_has_no_forbidden_production_imports():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search"
    )

    forbidden = {
        "chromadb",
        "config",
        "retriever",
        "source_evidence",
        "evidence_search",
        "evidence_answer",
        "openai",
        "streamlit",
    }

    observed = set()

    for path in sorted(
        package.glob(
            "*.py"
        )
    ):
        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            )
        )

        for node in ast.walk(
            tree
        ):

            if isinstance(
                node,
                ast.Import,
            ):
                for alias in node.names:
                    observed.add(
                        alias.name.split(
                            "."
                        )[0]
                    )

            elif isinstance(
                node,
                ast.ImportFrom,
            ):
                if (
                    node.level == 0
                    and node.module
                ):
                    observed.add(
                        node.module.split(
                            "."
                        )[0]
                    )

    assert not (
        observed
        & forbidden
    )


def test_candidate_package_has_no_chroma_or_source_binding_semantics():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search"
    )

    joined = "\n".join(
        path.read_text(
            encoding="utf-8"
        )
        for path in sorted(
            package.glob(
                "*.py"
            )
        )
    )

    assert "FULL_CHAIN_BOUND" not in joined

    assert "ANALYTICAL_TEXT_BOUND" not in joined

    assert "EvidenceBinding" not in joined

    assert "SourceChunkSnapshot" not in joined

    assert "SourceBoundAnalysisReceipt" not in joined

    assert "legal_documents" not in joined


def test_candidate_package_has_no_persistent_write_operations():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search"
    )

    joined = "\n".join(
        path.read_text(
            encoding="utf-8"
        )
        for path in sorted(
            package.glob(
                "*.py"
            )
        )
    )

    forbidden_fragments = (
        ".write_text(",
        ".write_bytes(",
        ".mkdir(",
        ".unlink(",
        ".rmdir(",
        "shutil.",
        "PersistentClient",
        ".add(",
        ".upsert(",
        ".delete(",
    )

    for fragment in forbidden_fragments:
        assert fragment not in joined


def test_candidate_foundation_does_not_define_negative_finding_authority():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search"
    )

    joined = "\n".join(
        path.read_text(
            encoding="utf-8"
        )
        for path in sorted(
            package.glob(
                "*.py"
            )
        )
    ).casefold()

    assert "negative_finding" not in joined

    assert "case_corpus_complete" not in joined
