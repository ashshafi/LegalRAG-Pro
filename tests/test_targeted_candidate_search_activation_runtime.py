from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import targeted_candidate_search_activation as foundation
from models import EMBEDDING_MODEL
from targeted_candidate_search_activation import service
from targeted_candidate_search_activation.runtime_models import (
    TargetedCandidateActivationIndexAction,
    TargetedCandidateActivationRowState,
)


@dataclass
class FakeRow:
    candidate_record_id: str
    document: str
    case_id: str
    metadata_value: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return dict(self.metadata_value)


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.document_calls: list[tuple[str, str]] = []
        self.query_calls: list[tuple[str, str]] = []

    def embed_document(self, *, model: str, text: str) -> list[float]:
        self.document_calls.append((model, text))
        return [0.125, 0.25, 0.5]

    def embed_query(self, *, model: str, text: str) -> list[float]:
        self.query_calls.append((model, text))
        return [0.75, 0.5, 0.25]


class FakeCollection:
    def __init__(self, *, name: str) -> None:
        self.name = name
        self.rows: dict[str, tuple[str, dict[str, Any]]] = {}
        self.add_calls = 0
        self.query_calls = 0
        self.last_where: dict[str, Any] | None = None
        self.query_payload: dict[str, Any] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    def get(self, *, ids: list[str], include: list[str]) -> dict[str, Any]:
        candidate_id = ids[0]
        if candidate_id not in self.rows:
            return {
                "ids": [],
                "documents": [],
                "metadatas": [],
            }

        document, metadata = self.rows[candidate_id]
        return {
            "ids": [candidate_id],
            "documents": [document],
            "metadatas": [dict(metadata)],
        }

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        self.add_calls += 1
        self.rows[ids[0]] = (
            documents[0],
            dict(metadatas[0]),
        )

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any],
        include: list[str],
    ) -> dict[str, Any]:
        self.query_calls += 1
        self.last_where = where
        return self.query_payload


class FakeCollectionProvider:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.calls: list[str] = []

    def open_collection(self, name: str) -> FakeCollection:
        self.calls.append(name)
        return self.collection


class FakeReviewLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load_latest(self, candidate_record_id: str) -> object:
        self.calls.append(candidate_record_id)
        return SimpleNamespace(candidate_record_id=candidate_record_id)


def make_pair(
    candidate_id: str,
    *,
    case_id: str = "case-1",
    text: str | None = None,
    collection_name: str = foundation.TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
):
    document = text or f"text-{candidate_id}"
    authority = SimpleNamespace(
        candidate_record_id=candidate_id,
        case_id=case_id,
        collection_name=collection_name,
        embedding_model=EMBEDDING_MODEL,
    )
    row = FakeRow(
        candidate_record_id=candidate_id,
        document=document,
        case_id=case_id,
        metadata_value={
            "authority_kind": foundation.TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
            "case_id": case_id,
            "binding_id": f"binding-{candidate_id}",
        },
    )
    return authority, row


@pytest.fixture(autouse=True)
def foundation_validation_stubs(monkeypatch):
    monkeypatch.setattr(
        service,
        "validate_targeted_candidate_activation_authority",
        lambda *, authority: None,
    )
    monkeypatch.setattr(
        service,
        "validate_targeted_candidate_activation_row",
        lambda *, authority, row: None,
    )
    monkeypatch.setattr(
        service,
        "validate_current_review_binding",
        lambda *, authority, row, review_projection: None,
    )


def exact_collection_for(*pairs):
    collection = FakeCollection(
        name=foundation.TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    )
    for _, row in pairs:
        collection.rows[row.candidate_record_id] = (
            row.document,
            row.metadata(),
        )
    return collection


def test_index_exact_is_unchanged_without_embedding():
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    result = service.index_targeted_candidate(
        authority=pair[0],
        row=pair[1],
        review_loader=FakeReviewLoader(),
        collection_provider=provider,
        embedding_provider=embeddings,
    )

    assert result.action is TargetedCandidateActivationIndexAction.UNCHANGED
    assert result.state is TargetedCandidateActivationRowState.EXACT
    assert embeddings.document_calls == []
    assert collection.add_calls == 0


def test_index_conflicting_fails_without_embedding_or_add():
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    collection.rows["cand-a"] = ("tampered", pair[1].metadata())
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.index_targeted_candidate(
            authority=pair[0],
            row=pair[1],
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
        )

    assert embeddings.document_calls == []
    assert collection.add_calls == 0


def test_index_missing_embeds_once_adds_once_and_becomes_exact():
    pair = make_pair("cand-a")
    collection = FakeCollection(
        name=foundation.TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    )
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    result = service.index_targeted_candidate(
        authority=pair[0],
        row=pair[1],
        review_loader=FakeReviewLoader(),
        collection_provider=provider,
        embedding_provider=embeddings,
    )

    assert result.action is TargetedCandidateActivationIndexAction.ADDED
    assert result.state is TargetedCandidateActivationRowState.EXACT
    assert embeddings.document_calls == [(EMBEDDING_MODEL, pair[1].document)]
    assert collection.add_calls == 1


@pytest.mark.parametrize("state_name", ["DEFERRED", "REJECTED", "STALE"])
def test_noncurrent_review_prevents_collection_open_and_embedding(
    monkeypatch,
    state_name,
):
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    def reject_binding(*, authority, row, review_projection):
        raise foundation.TargetedCandidateActivationError(state_name)

    monkeypatch.setattr(
        service,
        "validate_current_review_binding",
        reject_binding,
    )

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.index_targeted_candidate(
            authority=pair[0],
            row=pair[1],
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
        )

    assert provider.calls == []
    assert embeddings.document_calls == []


def test_wrong_active_case_prevents_review_collection_and_embedding():
    pair = make_pair("cand-a", case_id="case-1")
    collection = exact_collection_for(pair)
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()
    review_loader = FakeReviewLoader()

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=review_loader,
            collection_provider=provider,
            embedding_provider=embeddings,
            active_case_id="case-2",
            query_text="query",
        )

    assert review_loader.calls == []
    assert provider.calls == []
    assert embeddings.query_calls == []


def test_query_multiple_candidates_arbitrary_order_and_exact_filter():
    pair_a = make_pair("cand-a")
    pair_b = make_pair("cand-b")
    collection = exact_collection_for(pair_a, pair_b)
    collection.query_payload = {
        "ids": [["cand-b", "cand-a"]],
        "documents": [[pair_b[1].document, pair_a[1].document]],
        "metadatas": [[pair_b[1].metadata(), pair_a[1].metadata()]],
        "distances": [[0.2, 0.4]],
    }
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    result = service.query_targeted_candidates(
        activations=(pair_a, pair_b),
        review_loader=FakeReviewLoader(),
        collection_provider=provider,
        embedding_provider=embeddings,
        active_case_id="case-1",
        query_text="find urdu text",
        n_results=5,
    )

    assert [hit.candidate_record_id for hit in result.hits] == [
        "cand-b",
        "cand-a",
    ]
    assert embeddings.query_calls == [(EMBEDDING_MODEL, "find urdu text")]
    assert collection.last_where == {
        "$and": [
            {
                "authority_kind": {
                    "$eq": foundation.TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
                }
            },
            {
                "case_id": {
                    "$eq": "case-1",
                }
            },
        ]
    }


def test_one_stale_activation_prevents_collection_open_and_query_embedding(
    monkeypatch,
):
    pair_a = make_pair("cand-a")
    pair_b = make_pair("cand-b")
    collection = exact_collection_for(pair_a, pair_b)
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    def reject_second(*, authority, row, review_projection):
        if row.candidate_record_id == "cand-b":
            raise foundation.TargetedCandidateActivationError("stale")

    monkeypatch.setattr(
        service,
        "validate_current_review_binding",
        reject_second,
    )

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair_a, pair_b),
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
            active_case_id="case-1",
            query_text="query",
        )

    assert provider.calls == []
    assert embeddings.query_calls == []


def test_all_rows_must_be_exact_before_query_embedding():
    pair_a = make_pair("cand-a")
    pair_b = make_pair("cand-b")
    collection = exact_collection_for(pair_a)
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair_a, pair_b),
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
            active_case_id="case-1",
            query_text="query",
        )

    assert embeddings.query_calls == []
    assert collection.query_calls == 0


def test_unknown_same_case_candidate_id_fails_closed():
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    collection.query_payload = {
        "ids": [["cand-unknown"]],
        "documents": [["text-cand-unknown"]],
        "metadatas": [[{
            "authority_kind": foundation.TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
            "case_id": "case-1",
        }]],
        "distances": [[0.1]],
    }

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=FakeReviewLoader(),
            collection_provider=FakeCollectionProvider(collection),
            embedding_provider=FakeEmbeddingProvider(),
            active_case_id="case-1",
            query_text="query",
        )


@pytest.mark.parametrize("tamper", ["document", "metadata"])
def test_tampered_known_candidate_fails_closed(tamper):
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    document = pair[1].document
    metadata = pair[1].metadata()

    if tamper == "document":
        document = "tampered"
    else:
        metadata = {**metadata, "binding_id": "tampered"}

    collection.query_payload = {
        "ids": [["cand-a"]],
        "documents": [[document]],
        "metadatas": [[metadata]],
        "distances": [[0.1]],
    }

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=FakeReviewLoader(),
            collection_provider=FakeCollectionProvider(collection),
            embedding_provider=FakeEmbeddingProvider(),
            active_case_id="case-1",
            query_text="query",
        )


@pytest.mark.parametrize("distance", [float("inf"), float("-inf"), float("nan"), True, "0.1"])
def test_invalid_distance_fails_closed(distance):
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)
    collection.query_payload = {
        "ids": [["cand-a"]],
        "documents": [[pair[1].document]],
        "metadatas": [[pair[1].metadata()]],
        "distances": [[distance]],
    }

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=FakeReviewLoader(),
            collection_provider=FakeCollectionProvider(collection),
            embedding_provider=FakeEmbeddingProvider(),
            active_case_id="case-1",
            query_text="query",
        )


def test_zero_hits_is_empty_discovery_only_result():
    pair = make_pair("cand-a")
    collection = exact_collection_for(pair)

    result = service.query_targeted_candidates(
        activations=(pair,),
        review_loader=FakeReviewLoader(),
        collection_provider=FakeCollectionProvider(collection),
        embedding_provider=FakeEmbeddingProvider(),
        active_case_id="case-1",
        query_text="query",
    )

    assert result.hits == ()


def test_legacy_collection_authority_rejected_before_provider_call():
    pair = make_pair(
        "cand-a",
        collection_name="derived_transcriptions_v1",
    )
    collection = FakeCollection(name="derived_transcriptions_v1")
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
            active_case_id="case-1",
            query_text="query",
        )

    assert provider.calls == []
    assert embeddings.query_calls == []


def test_opened_collection_must_be_exact_successor_collection():
    pair = make_pair("cand-a")
    collection = FakeCollection(name="wrong_collection")
    provider = FakeCollectionProvider(collection)
    embeddings = FakeEmbeddingProvider()

    with pytest.raises(foundation.TargetedCandidateActivationError):
        service.query_targeted_candidates(
            activations=(pair,),
            review_loader=FakeReviewLoader(),
            collection_provider=provider,
            embedding_provider=embeddings,
            active_case_id="case-1",
            query_text="query",
        )

    assert provider.calls == [
        foundation.TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    ]
    assert embeddings.query_calls == []
