from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import json

import pytest

from derived_transcription_search import (
    DERIVED_SEARCH_AUTHORITY_KIND,
    DERIVED_SEARCH_COLLECTION_NAME,
    prepare_candidate,
    prepare_row,
)

from derived_transcription_search_runtime import (
    DERIVED_SEARCH_DISCOVERY_SCOPE,
    DerivedSearchIndexAction,
    DerivedSearchIndexError,
    DerivedSearchQueryError,
    DerivedSearchRowState,
    index_rows_idempotent,
    inspect_row,
    inspect_rows,
    query_derived_candidates,
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

RECORD_PATH = _ImmutableFixtureFile(FIXTURE_RECORD_BYTES)

TEXT_PATH = _ImmutableFixtureFile(FIXTURE_TRANSCRIPTION_BYTES)


def prepared_row():
    record = json.loads(
        RECORD_PATH.read_text(
            encoding="utf-8"
        )
    )

    text = (
        TEXT_PATH
        .read_bytes()
        .decode(
            "utf-8",
            errors="strict",
        )
    )

    candidate = prepare_candidate(
        record=record,
        transcription_text=text,
    )

    row = prepare_row(
        candidate=candidate,
        transcription_text=text,
    )

    return row


EXPECTED_WHERE = {
    "$and": [
        {
            "authority_kind": {
                "$eq":
                    DERIVED_SEARCH_AUTHORITY_KIND,
            }
        },
        {
            "case_id": {
                "$eq":
                    CASE_ID,
            }
        },
    ]
}


class FakeCollection:
    def __init__(self):
        self.rows = {}
        self.get_calls = []
        self.add_calls = []
        self.query_calls = []
        self.forced_query_response = None

    def get(
        self,
        *,
        ids,
        include,
    ):
        self.get_calls.append(
            {
                "ids":
                    list(ids),

                "include":
                    list(include),
            }
        )

        found_ids = []
        documents = []
        metadatas = []

        for row_id in ids:

            if row_id not in self.rows:
                continue

            item = self.rows[
                row_id
            ]

            found_ids.append(
                row_id
            )

            documents.append(
                item[
                    "document"
                ]
            )

            metadatas.append(
                deepcopy(
                    item[
                        "metadata"
                    ]
                )
            )

        return {
            "ids":
                found_ids,

            "documents":
                documents,

            "metadatas":
                metadatas,
        }

    def add(
        self,
        *,
        ids,
        documents,
        metadatas,
    ):
        call = {
            "ids":
                list(ids),

            "documents":
                list(documents),

            "metadatas":
                [
                    deepcopy(item)
                    for item in metadatas
                ],
        }

        self.add_calls.append(
            call
        )

        for (
            row_id,
            document,
            metadata,
        ) in zip(
            ids,
            documents,
            metadatas,
            strict=True,
        ):

            if row_id in self.rows:
                raise RuntimeError(
                    "fake add refuses duplicate row identity"
                )

            self.rows[
                row_id
            ] = {
                "document":
                    document,

                "metadata":
                    deepcopy(
                        metadata
                    ),
            }

    def query(
        self,
        *,
        query_embeddings,
        n_results,
        where,
        include,
    ):
        self.query_calls.append(
            {
                "query_embeddings":
                    deepcopy(
                        query_embeddings
                    ),

                "n_results":
                    n_results,

                "where":
                    deepcopy(
                        where
                    ),

                "include":
                    list(
                        include
                    ),
            }
        )

        if (
            self.forced_query_response
            is not None
        ):
            return deepcopy(
                self.forced_query_response
            )

        if where != EXPECTED_WHERE:
            raise AssertionError(
                "query did not use exact governed derived/case filter"
            )

        ids = []
        documents = []
        metadatas = []
        distances = []

        for row_id, item in self.rows.items():

            metadata = item[
                "metadata"
            ]

            if (
                metadata[
                    "authority_kind"
                ]
                != DERIVED_SEARCH_AUTHORITY_KIND
            ):
                continue

            if (
                metadata[
                    "case_id"
                ]
                != CASE_ID
            ):
                continue

            ids.append(
                row_id
            )

            documents.append(
                item[
                    "document"
                ]
            )

            metadatas.append(
                deepcopy(
                    metadata
                )
            )

            distances.append(
                0.125
            )

        return {
            "ids":
                [
                    ids[
                        :n_results
                    ]
                ],

            "documents":
                [
                    documents[
                        :n_results
                    ]
                ],

            "metadatas":
                [
                    metadatas[
                        :n_results
                    ]
                ],

            "distances":
                [
                    distances[
                        :n_results
                    ]
                ],
        }


def insert_exact(
    collection,
    row,
):
    collection.rows[
        row.row_id
    ] = {
        "document":
            row.document,

        "metadata":
            dict(
                row.metadata
            ),
    }


def exact_query_response(
    row,
):
    return {
        "ids":
            [
                [
                    row.row_id
                ]
            ],

        "documents":
            [
                [
                    row.document
                ]
            ],

        "metadatas":
            [
                [
                    dict(
                        row.metadata
                    )
                ]
            ],

        "distances":
            [
                [
                    0.25
                ]
            ],
    }


def embedder_calls():
    calls = []

    def embedder(text):
        calls.append(
            text
        )

        return [
            0.1,
            0.2,
            0.3,
        ]

    return (
        calls,
        embedder,
    )


def test_d1_collection_contract_remains_dedicated():
    assert (
        DERIVED_SEARCH_COLLECTION_NAME
        == "derived_transcriptions_v1"
    )

    assert (
        DERIVED_SEARCH_COLLECTION_NAME
        != "legal_documents"
    )


def test_missing_row_is_inspected_as_missing():
    row = prepared_row()
    collection = FakeCollection()

    inspection = inspect_row(
        collection=collection,
        row=row,
    )

    assert (
        inspection.state
        is DerivedSearchRowState.MISSING
    )


def test_exact_row_is_inspected_as_exact():
    row = prepared_row()
    collection = FakeCollection()

    insert_exact(
        collection,
        row,
    )

    inspection = inspect_row(
        collection=collection,
        row=row,
    )

    assert (
        inspection.state
        is DerivedSearchRowState.EXACT
    )


def test_changed_document_is_conflicting():
    row = prepared_row()
    collection = FakeCollection()

    insert_exact(
        collection,
        row,
    )

    collection.rows[
        row.row_id
    ][
        "document"
    ] += "x"

    inspection = inspect_row(
        collection=collection,
        row=row,
    )

    assert (
        inspection.state
        is DerivedSearchRowState.CONFLICTING
    )


def test_changed_metadata_is_conflicting():
    row = prepared_row()
    collection = FakeCollection()

    insert_exact(
        collection,
        row,
    )

    collection.rows[
        row.row_id
    ][
        "metadata"
    ][
        "derived_record_id"
    ] = (
        "sha256:"
        + ("0" * 64)
    )

    inspection = inspect_row(
        collection=collection,
        row=row,
    )

    assert (
        inspection.state
        is DerivedSearchRowState.CONFLICTING
    )


def test_missing_row_is_added_once_and_reconciles_exact():
    row = prepared_row()
    collection = FakeCollection()

    result = index_rows_idempotent(
        collection=collection,
        rows=(
            row,
        ),
    )

    assert len(
        collection.add_calls
    ) == 1

    assert len(
        result
    ) == 1

    assert (
        result[0].action
        is DerivedSearchIndexAction.ADDED
    )

    assert (
        result[0].final_state
        is DerivedSearchRowState.EXACT
    )


def test_second_index_is_idempotent_and_performs_no_second_add():
    row = prepared_row()
    collection = FakeCollection()

    first = index_rows_idempotent(
        collection=collection,
        rows=(
            row,
        ),
    )

    second = index_rows_idempotent(
        collection=collection,
        rows=(
            row,
        ),
    )

    assert (
        first[0].action
        is DerivedSearchIndexAction.ADDED
    )

    assert (
        second[0].action
        is DerivedSearchIndexAction.UNCHANGED
    )

    assert len(
        collection.add_calls
    ) == 1


def test_conflict_fails_before_any_add():
    row = prepared_row()
    collection = FakeCollection()

    insert_exact(
        collection,
        row,
    )

    collection.rows[
        row.row_id
    ][
        "metadata"
    ][
        "page"
    ] = 99

    with pytest.raises(
        DerivedSearchIndexError,
        match="before write",
    ):
        index_rows_idempotent(
            collection=collection,
            rows=(
                row,
            ),
        )

    assert collection.add_calls == []


def test_duplicate_input_identity_is_rejected_before_add():
    row = prepared_row()
    collection = FakeCollection()

    with pytest.raises(
        DerivedSearchIndexError,
        match="duplicate",
    ):
        index_rows_idempotent(
            collection=collection,
            rows=(
                row,
                row,
            ),
        )

    assert collection.add_calls == []


def test_query_uses_injected_embedding_and_exact_case_authority_filter():
    row = prepared_row()
    collection = FakeCollection()

    insert_exact(
        collection,
        row,
    )

    calls, embedder = embedder_calls()

    result = query_derived_candidates(
        collection=collection,
        query="Nabila Shafi",
        case_id=CASE_ID,
        authorities=(
            row,
        ),
        embedder=embedder,
        n_results=5,
    )

    assert calls == [
        "Nabila Shafi"
    ]

    assert len(
        collection.query_calls
    ) == 1

    call = collection.query_calls[
        0
    ]

    assert (
        call[
            "query_embeddings"
        ]
        == [
            [
                0.1,
                0.2,
                0.3,
            ]
        ]
    )

    assert (
        call[
            "where"
        ]
        == EXPECTED_WHERE
    )

    assert (
        call[
            "n_results"
        ]
        == 5
    )

    assert (
        result.discovery_scope
        == DERIVED_SEARCH_DISCOVERY_SCOPE
    )

    assert len(
        result.hits
    ) == 1

    assert (
        result.hits[0].row_id
        == row.row_id
    )


def test_empty_query_result_is_discovery_only_and_valid():
    row = prepared_row()
    collection = FakeCollection()

    calls, embedder = embedder_calls()

    result = query_derived_candidates(
        collection=collection,
        query="unmatched term",
        case_id=CASE_ID,
        authorities=(
            row,
        ),
        embedder=embedder,
    )

    assert calls == [
        "unmatched term"
    ]

    assert result.hits == ()

    assert (
        result.discovery_scope
        == "candidate_discovery_only"
    )


def test_query_rejects_unknown_returned_identity():
    row = prepared_row()
    collection = FakeCollection()

    response = exact_query_response(
        row
    )

    response[
        "ids"
    ][0][0] = (
        "dtx:sha256:"
        + ("0" * 64)
    )

    collection.forced_query_response = (
        response
    )

    _, embedder = embedder_calls()

    with pytest.raises(
        DerivedSearchQueryError,
        match="unknown",
    ):
        query_derived_candidates(
            collection=collection,
            query="registration",
            case_id=CASE_ID,
            authorities=(
                row,
            ),
            embedder=embedder,
        )


def test_query_rejects_tampered_document_text():
    row = prepared_row()
    collection = FakeCollection()

    response = exact_query_response(
        row
    )

    response[
        "documents"
    ][0][0] += "x"

    collection.forced_query_response = (
        response
    )

    _, embedder = embedder_calls()

    with pytest.raises(
        DerivedSearchQueryError,
        match="derived text",
    ):
        query_derived_candidates(
            collection=collection,
            query="registered",
            case_id=CASE_ID,
            authorities=(
                row,
            ),
            embedder=embedder,
        )


@pytest.mark.parametrize(
    "field,replacement",
    [
        (
            "case_id",
            "11111111-1111-1111-1111-111111111111",
        ),
        (
            "source_document_instance_id",
            "11111111-1111-1111-1111-111111111111",
        ),
        (
            "source_snapshot_id",
            "sha256:" + ("0" * 64),
        ),
        (
            "page",
            99,
        ),
        (
            "derived_record_id",
            "sha256:" + ("0" * 64),
        ),
        (
            "derived_transcription_sha256",
            "0" * 64,
        ),
        (
            "authority_kind",
            "source_evidence",
        ),
    ],
)
def test_query_rejects_tampered_authority_metadata(
    field,
    replacement,
):
    row = prepared_row()
    collection = FakeCollection()

    response = exact_query_response(
        row
    )

    response[
        "metadatas"
    ][0][0][
        field
    ] = replacement

    collection.forced_query_response = (
        response
    )

    _, embedder = embedder_calls()

    with pytest.raises(
        DerivedSearchQueryError,
        match="metadata",
    ):
        query_derived_candidates(
            collection=collection,
            query="marriage",
            case_id=CASE_ID,
            authorities=(
                row,
            ),
            embedder=embedder,
        )


def test_query_rejects_duplicate_returned_identity():
    row = prepared_row()
    collection = FakeCollection()

    response = exact_query_response(
        row
    )

    response = {
        "ids":
            [
                [
                    row.row_id,
                    row.row_id,
                ]
            ],

        "documents":
            [
                [
                    row.document,
                    row.document,
                ]
            ],

        "metadatas":
            [
                [
                    dict(
                        row.metadata
                    ),
                    dict(
                        row.metadata
                    ),
                ]
            ],

        "distances":
            [
                [
                    0.1,
                    0.2,
                ]
            ],
    }

    collection.forced_query_response = (
        response
    )

    _, embedder = embedder_calls()

    with pytest.raises(
        DerivedSearchQueryError,
        match="duplicate",
    ):
        query_derived_candidates(
            collection=collection,
            query="marriage",
            case_id=CASE_ID,
            authorities=(
                row,
            ),
            embedder=embedder,
        )


def test_query_rejects_invalid_embedding():
    row = prepared_row()
    collection = FakeCollection()

    with pytest.raises(
        DerivedSearchQueryError,
        match="empty vector",
    ):
        query_derived_candidates(
            collection=collection,
            query="marriage",
            case_id=CASE_ID,
            authorities=(
                row,
            ),
            embedder=lambda _: (),
        )

    assert collection.query_calls == []


def test_query_rejects_wrong_active_case_before_collection_query():
    row = prepared_row()
    collection = FakeCollection()

    _, embedder = embedder_calls()

    wrong_case = (
        "11111111-1111-1111-1111-111111111111"
    )

    with pytest.raises(
        DerivedSearchQueryError,
        match="wrong case",
    ):
        query_derived_candidates(
            collection=collection,
            query="marriage",
            case_id=wrong_case,
            authorities=(
                row,
            ),
            embedder=embedder,
        )

    # Embedding occurs before returned-row authority evaluation,
    # but the collection may return no matching rows. Force the
    # expected authority row to demonstrate fail-closed behaviour.
def test_query_rejects_cross_case_return_even_when_fake_backend_violates_filter():
    row = prepared_row()
    collection = FakeCollection()

    collection.forced_query_response = (
        exact_query_response(
            row
        )
    )

    _, embedder = embedder_calls()

    wrong_case = (
        "11111111-1111-1111-1111-111111111111"
    )

    with pytest.raises(
        DerivedSearchQueryError,
        match="wrong case",
    ):
        query_derived_candidates(
            collection=collection,
            query="marriage",
            case_id=wrong_case,
            authorities=(
                row,
            ),
            embedder=embedder,
        )


def test_runtime_package_has_no_forbidden_production_dependencies():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search_runtime"
    )

    forbidden_roots = {
        "chromadb",
        "openai",
        "source_evidence",
        "retriever",
        "config",
        "evidence_search",
        "evidence_answer",
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
        & forbidden_roots
    )


def test_runtime_package_has_no_source_evidence_authority_claims():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search_runtime"
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
    assert "PersistentClient" not in joined


def test_runtime_package_does_not_define_complete_corpus_authority():
    package = (
        WORKSPACE
        / "src"
        / "derived_transcription_search_runtime"
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

    assert "case_corpus_complete" not in joined
    assert "searched_scope" not in joined
    assert "negative_finding" not in joined

    assert (
        "candidate_discovery_only"
        in joined
    )
