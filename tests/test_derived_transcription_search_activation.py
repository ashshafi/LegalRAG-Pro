from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import pytest

from derived_transcription_search_activation import (
    ActivationAuthority,
    ActivationError,
    ActivationIndexAction,
    ActivationRow,
    DERIVED_SEARCH_AUTHORITY_KIND,
    DERIVED_SEARCH_COLLECTION_NAME,
    DERIVED_SEARCH_DISCOVERY_SCOPE,
    index_retained_candidate,
    query_retained_candidate,
)


CASE_ID = "9e10cd5a-00fd-484e-938d-b5c3358c8dae"
DOCUMENT_ID = "614f7017-2aab-5c59-ab16-bf4786699073"

SOURCE_SNAPSHOT_ID = (
    "sha256:51399667df2fa233c897f99a09c5804068c00f8eb7b23a2d8a0b16b1bc481434"
)

SOURCE_ORIGINAL_BLOB_SHA256 = (
    "a759591d9dbc464ec717c918e5199fab2e644f05c414c15b95c5738d64d083a1"
)

DERIVED_RECORD_ID = (
    "sha256:cc877d9425f688e3a7beef71f3ca6b75c8ca74d05034a498b138f4f3729132ac"
)

CANDIDATE_ID = (
    "dtx:sha256:ed57d5ecd869e9f960ec8756e2049c567a50b1739c165bb15962f70a7614eaf4"
)

TRANSCRIPTION_SHA256 = (
    "4eaed7f82e463dafea5825c4aa3dd032ab6883151bb451d0b5c80365a60144fb"
)

EMBEDDED_IMAGE_SHA256 = (
    "99341c618aa14897646c2b950a40ac31ed67508f506ab324efb9ba95e03baaf4"
)

PROFILE_ID = "photo-embedded-image-ocr/1.0"
EMBEDDING_MODEL = "text-embedding-3-small"


def retained_text() -> str:
    path = Path(
        os.environ[
            "LEGALRAG_RETAINED_TRANSCRIPTION_PATH"
        ]
    )

    raw = path.read_bytes()

    assert len(raw) == 1661

    return raw.decode("utf-8")


def authority() -> ActivationAuthority:
    return ActivationAuthority(
        case_id=CASE_ID,
        candidate_id=CANDIDATE_ID,
        transcription_sha256=TRANSCRIPTION_SHA256,
        transcription_bytes=1661,
        embedding_model=EMBEDDING_MODEL,
    )


def row() -> ActivationRow:
    return ActivationRow(
        candidate_id=CANDIDATE_ID,
        document=retained_text(),
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        page=1,
        source_original_blob_sha256=
            SOURCE_ORIGINAL_BLOB_SHA256,
        derived_record_id=DERIVED_RECORD_ID,
        transcription_sha256=TRANSCRIPTION_SHA256,
        embedded_image_sha256=EMBEDDED_IMAGE_SHA256,
        profile_id=PROFILE_ID,
    )


class FakeEmbeddingProvider:
    def __init__(self):
        self.document_calls = []
        self.query_calls = []
        self.fail_document = False

    def embed_document(
        self,
        *,
        model,
        text,
    ):
        self.document_calls.append(
            (model, text)
        )

        if self.fail_document:
            raise RuntimeError(
                "synthetic document embedding failure"
            )

        return [0.125, 0.25, 0.5]

    def embed_query(
        self,
        *,
        model,
        text,
    ):
        self.query_calls.append(
            (model, text)
        )

        return [0.75, 0.5, 0.25]


class FakeCollection:
    def __init__(self):
        self.name = DERIVED_SEARCH_COLLECTION_NAME
        self.rows = {}
        self.add_calls = 0
        self.query_calls = []
        self.query_override = None

    def get(
        self,
        *,
        ids,
        include,
    ):
        del include

        found_ids = []
        documents = []
        metadatas = []

        for candidate_id in ids:
            stored = self.rows.get(
                candidate_id
            )

            if stored is None:
                continue

            found_ids.append(
                candidate_id
            )

            documents.append(
                stored["document"]
            )

            metadatas.append(
                deepcopy(
                    stored["metadata"]
                )
            )

        return {
            "ids": found_ids,
            "documents": documents,
            "metadatas": metadatas,
        }

    def add(
        self,
        *,
        ids,
        documents,
        metadatas,
        embeddings,
    ):
        self.add_calls += 1

        assert len(ids) == 1
        assert len(documents) == 1
        assert len(metadatas) == 1
        assert len(embeddings) == 1

        candidate_id = ids[0]

        if candidate_id in self.rows:
            raise AssertionError(
                "duplicate fake add"
            )

        self.rows[candidate_id] = {
            "document": documents[0],
            "metadata": dict(
                metadatas[0]
            ),
            "embedding": list(
                embeddings[0]
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
        self.query_calls.append({
            "query_embeddings":
                deepcopy(
                    query_embeddings
                ),

            "n_results":
                n_results,

            "where":
                deepcopy(where),

            "include":
                list(include),
        })

        if self.query_override is not None:
            return deepcopy(
                self.query_override
            )

        expected_where = {
            "$and": [
                {
                    "authority_kind": {
                        "$eq":
                            "derived_transcription",
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

        assert where == expected_where

        stored = self.rows.get(
            CANDIDATE_ID
        )

        if stored is None:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }

        return {
            "ids": [
                [
                    CANDIDATE_ID
                ]
            ],
            "documents": [
                [
                    stored[
                        "document"
                    ]
                ]
            ],
            "metadatas": [
                [
                    deepcopy(
                        stored[
                            "metadata"
                        ]
                    )
                ]
            ],
            "distances": [
                [0.125]
            ],
        }


def test_contract_matches_published_c4_and_governing_model():
    repo = Path(
        os.environ[
            "LEGALRAG_PRODUCTION_REPO"
        ]
    )

    c4_text = (
        repo
        / "src"
        / "derived_transcription_search"
        / "models.py"
    ).read_text(
        encoding="utf-8"
    )

    runtime_models = (
        repo
        / "src"
        / "derived_transcription_search_runtime"
        / "models.py"
    ).read_text(
        encoding="utf-8"
    )

    runtime_query = (
        repo
        / "src"
        / "derived_transcription_search_runtime"
        / "query.py"
    ).read_text(
        encoding="utf-8"
    )

    model_text = (
        repo
        / "src"
        / "models.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "derived_transcriptions_v1" in c4_text
    assert "derived_transcription" in c4_text
    assert "candidate_discovery_only" in runtime_models
    assert "DERIVED_SEARCH_DISCOVERY_SCOPE" in runtime_query

    assert (
        'EMBEDDING_MODEL = "text-embedding-3-small"'
        in model_text
    )


def test_exact_one_row_creation():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    result = index_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
    )

    assert (
        result.action
        is ActivationIndexAction.ADDED
    )

    assert collection.add_calls == 1
    assert len(collection.rows) == 1
    assert len(provider.document_calls) == 1

    assert provider.document_calls[0][0] == (
        EMBEDDING_MODEL
    )

    assert provider.document_calls[0][1] == (
        retained_text()
    )


def test_idempotent_exact_existing_row_does_not_embed_again():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    first = index_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
    )

    second = index_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
    )

    assert first.action is ActivationIndexAction.ADDED
    assert second.action is ActivationIndexAction.UNCHANGED
    assert collection.add_calls == 1
    assert len(provider.document_calls) == 1


def test_conflicting_existing_row_rejected_before_embedding():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    governed = row()

    collection.rows[CANDIDATE_ID] = {
        "document": governed.document + " conflict",
        "metadata": governed.metadata(),
        "embedding": [1.0],
    }

    with pytest.raises(
        ActivationError,
        match="conflicts",
    ):
        index_retained_candidate(
            authority=authority(),
            row=governed,
            collection=collection,
            embedding_provider=provider,
        )

    assert provider.document_calls == []
    assert collection.add_calls == 0


def test_wrong_case_rejected_before_embedding_or_write():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    governed = row()

    wrong = ActivationRow(
        **{
            **governed.__dict__,
            "case_id":
                "00000000-0000-4000-8000-000000000000",
        }
    )

    with pytest.raises(
        ActivationError,
        match="case ID",
    ):
        index_retained_candidate(
            authority=authority(),
            row=wrong,
            collection=collection,
            embedding_provider=provider,
        )

    assert provider.document_calls == []
    assert collection.add_calls == 0


def test_tampered_existing_metadata_rejected_before_embedding():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    governed = row()

    metadata = governed.metadata()
    metadata["profile_id"] = "tampered-profile"

    collection.rows[CANDIDATE_ID] = {
        "document": governed.document,
        "metadata": metadata,
        "embedding": [1.0],
    }

    with pytest.raises(
        ActivationError,
        match="conflicts",
    ):
        index_retained_candidate(
            authority=authority(),
            row=governed,
            collection=collection,
            embedding_provider=provider,
        )

    assert provider.document_calls == []
    assert collection.add_calls == 0


def test_wrong_candidate_id_rejected_before_embedding_or_write():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    governed = row()

    wrong = ActivationRow(
        **{
            **governed.__dict__,
            "candidate_id":
                "dtx:sha256:"
                + ("0" * 64),
        }
    )

    with pytest.raises(
        ActivationError,
        match="candidate ID",
    ):
        index_retained_candidate(
            authority=authority(),
            row=wrong,
            collection=collection,
            embedding_provider=provider,
        )

    assert provider.document_calls == []
    assert collection.add_calls == 0


def test_embedding_failure_occurs_before_first_write():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    provider.fail_document = True

    with pytest.raises(
        RuntimeError,
        match="synthetic",
    ):
        index_retained_candidate(
            authority=authority(),
            row=row(),
            collection=collection,
            embedding_provider=provider,
        )

    assert len(provider.document_calls) == 1
    assert collection.add_calls == 0
    assert collection.rows == {}


def test_query_is_exactly_case_and_authority_isolated():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    index_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
    )

    result = query_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
        active_case_id=CASE_ID,
        query_text="registered by",
    )

    assert len(result.hits) == 1
    assert result.hits[0].candidate_id == CANDIDATE_ID

    assert len(provider.query_calls) == 1
    assert len(collection.query_calls) == 1

    assert collection.query_calls[0]["where"] == {
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


def test_query_wrong_active_case_fails_before_embedding_and_query():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    with pytest.raises(
        ActivationError,
        match="Active case",
    ):
        query_retained_candidate(
            authority=authority(),
            row=row(),
            collection=collection,
            embedding_provider=provider,
            active_case_id=
                "00000000-0000-4000-8000-000000000000",
            query_text="marriage",
        )

    assert provider.query_calls == []
    assert collection.query_calls == []


def test_query_tampered_metadata_is_rejected():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    governed = row()

    collection.query_override = {
        "ids": [[CANDIDATE_ID]],
        "documents": [[governed.document]],
        "metadatas": [[{
            **governed.metadata(),
            "authority_kind":
                "source_evidence",
        }]],
        "distances": [[0.1]],
    }

    with pytest.raises(
        ActivationError,
        match="tampered metadata",
    ):
        query_retained_candidate(
            authority=authority(),
            row=governed,
            collection=collection,
            embedding_provider=provider,
            active_case_id=CASE_ID,
            query_text="marriage",
        )


def test_query_unknown_candidate_id_is_rejected():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()
    governed = row()

    collection.query_override = {
        "ids": [[
            "dtx:sha256:"
            + ("0" * 64)
        ]],
        "documents": [[governed.document]],
        "metadatas": [[governed.metadata()]],
        "distances": [[0.1]],
    }

    with pytest.raises(
        ActivationError,
        match="unknown candidate",
    ):
        query_retained_candidate(
            authority=authority(),
            row=governed,
            collection=collection,
            embedding_provider=provider,
            active_case_id=CASE_ID,
            query_text="marriage",
        )


def test_empty_query_has_no_negative_finding_authority():
    collection = FakeCollection()
    provider = FakeEmbeddingProvider()

    result = query_retained_candidate(
        authority=authority(),
        row=row(),
        collection=collection,
        embedding_provider=provider,
        active_case_id=CASE_ID,
        query_text="marriage",
    )

    assert result.hits == ()
    assert (
        result.discovery_scope
        == DERIVED_SEARCH_DISCOVERY_SCOPE
        == "candidate_discovery_only"
    )

    assert result.negative_finding_authoritative is False
