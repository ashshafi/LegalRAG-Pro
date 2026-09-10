from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import targeted_candidate_search_activation.providers as providers
from targeted_candidate_search_activation.models import (
    TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
)
from targeted_candidate_search_activation.providers import (
    ExternalTranscriptionReviewProjectionLoader,
    OpenAIEmbeddingProvider,
    TargetedCandidateChromaCollectionProvider,
    TargetedCandidateProviderError,
)


class _FakeCandidateStore:
    requested: list[tuple[Path, str]] = []
    record_id: str | None = None

    def __init__(self, root):
        self.root = Path(root)

    def load_candidate(self, record_id):
        type(self).requested.append((self.root, record_id))
        resolved = type(self).record_id
        if resolved is None:
            resolved = record_id
        return SimpleNamespace(record_id=resolved)


class _FakeReviewStore:
    requested: list[tuple[Path, str]] = []
    events = ("event-1",)

    def __init__(self, root):
        self.root = Path(root)

    def load_events(self, candidate_record_id):
        type(self).requested.append(
            (self.root, candidate_record_id)
        )
        return type(self).events


def _reset_review_fakes():
    _FakeCandidateStore.requested = []
    _FakeCandidateStore.record_id = None
    _FakeReviewStore.requested = []
    _FakeReviewStore.events = ("event-1",)


def test_review_loader_uses_exact_roots_and_projects_latest(monkeypatch, tmp_path):
    _reset_review_fakes()

    candidate_root = tmp_path / "candidate_store"
    review_root = tmp_path / "review_event_store"
    candidate_id = "sha256:" + "1" * 64

    projection = SimpleNamespace(candidate_record_id=candidate_id)

    monkeypatch.setattr(
        providers,
        "CandidateTranscriptionStore",
        _FakeCandidateStore,
    )
    monkeypatch.setattr(
        providers,
        "TranscriptionReviewEventStore",
        _FakeReviewStore,
    )
    monkeypatch.setattr(
        providers,
        "project_transcription_review",
        lambda events: projection if events == ("event-1",) else None,
    )

    loader = ExternalTranscriptionReviewProjectionLoader(
        candidate_root=candidate_root,
        review_root=review_root,
    )

    result = loader.load_latest(candidate_id)

    assert result is projection
    assert _FakeCandidateStore.requested == [
        (candidate_root, candidate_id)
    ]
    assert _FakeReviewStore.requested == [
        (review_root, candidate_id)
    ]


def test_review_loader_rejects_empty_candidate_id(tmp_path):
    loader = ExternalTranscriptionReviewProjectionLoader(
        candidate_root=tmp_path / "candidate",
        review_root=tmp_path / "review",
    )
    with pytest.raises(TargetedCandidateProviderError):
        loader.load_latest("")


def test_review_loader_fails_closed_on_loaded_identity_mismatch(
    monkeypatch,
    tmp_path,
):
    _reset_review_fakes()

    candidate_id = "sha256:" + "2" * 64
    _FakeCandidateStore.record_id = "sha256:" + "3" * 64

    monkeypatch.setattr(
        providers,
        "CandidateTranscriptionStore",
        _FakeCandidateStore,
    )

    loader = ExternalTranscriptionReviewProjectionLoader(
        candidate_root=tmp_path / "candidate",
        review_root=tmp_path / "review",
    )

    with pytest.raises(TargetedCandidateProviderError):
        loader.load_latest(candidate_id)

    assert _FakeReviewStore.requested == []


def test_review_loader_fails_closed_when_projection_absent(
    monkeypatch,
    tmp_path,
):
    _reset_review_fakes()
    candidate_id = "sha256:" + "4" * 64

    monkeypatch.setattr(
        providers,
        "CandidateTranscriptionStore",
        _FakeCandidateStore,
    )
    monkeypatch.setattr(
        providers,
        "TranscriptionReviewEventStore",
        _FakeReviewStore,
    )
    monkeypatch.setattr(
        providers,
        "project_transcription_review",
        lambda events: None,
    )

    loader = ExternalTranscriptionReviewProjectionLoader(
        candidate_root=tmp_path / "candidate",
        review_root=tmp_path / "review",
    )

    with pytest.raises(TargetedCandidateProviderError):
        loader.load_latest(candidate_id)


def test_review_loader_fails_closed_on_projection_identity_mismatch(
    monkeypatch,
    tmp_path,
):
    _reset_review_fakes()
    candidate_id = "sha256:" + "5" * 64

    monkeypatch.setattr(
        providers,
        "CandidateTranscriptionStore",
        _FakeCandidateStore,
    )
    monkeypatch.setattr(
        providers,
        "TranscriptionReviewEventStore",
        _FakeReviewStore,
    )
    monkeypatch.setattr(
        providers,
        "project_transcription_review",
        lambda events: SimpleNamespace(
            candidate_record_id="sha256:" + "6" * 64
        ),
    )

    loader = ExternalTranscriptionReviewProjectionLoader(
        candidate_root=tmp_path / "candidate",
        review_root=tmp_path / "review",
    )

    with pytest.raises(TargetedCandidateProviderError):
        loader.load_latest(candidate_id)


class _FakeCollection:
    def __init__(self, name):
        self.name = name


class _FakeChromaClient:
    def __init__(self, *, path):
        self.path = path
        self.requested_names = []

    def get_or_create_collection(self, *, name):
        self.requested_names.append(name)
        return _FakeCollection(name)


def test_collection_provider_is_lazy_and_opens_only_successor_collection(
    monkeypatch,
    tmp_path,
):
    constructed = []

    def persistent_client(*, path):
        client = _FakeChromaClient(path=path)
        constructed.append(client)
        return client

    monkeypatch.setattr(
        providers.chromadb,
        "PersistentClient",
        persistent_client,
    )

    db_root = tmp_path / "db"
    provider = TargetedCandidateChromaCollectionProvider(
        db_root=db_root
    )

    assert constructed == []

    collection = provider.open_collection(
        TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    )

    assert collection.name == TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    assert len(constructed) == 1
    assert constructed[0].path == str(db_root)
    assert constructed[0].requested_names == [
        TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    ]


@pytest.mark.parametrize(
    "forbidden",
    ["legal_documents", "derived_transcriptions_v1", "", "other"],
)
def test_collection_provider_rejects_non_successor_name_before_client_open(
    monkeypatch,
    tmp_path,
    forbidden,
):
    calls = []

    def persistent_client(*, path):
        calls.append(path)
        raise AssertionError("PersistentClient must not be constructed")

    monkeypatch.setattr(
        providers.chromadb,
        "PersistentClient",
        persistent_client,
    )

    provider = TargetedCandidateChromaCollectionProvider(
        db_root=tmp_path / "db"
    )

    with pytest.raises(TargetedCandidateProviderError):
        provider.open_collection(forbidden)

    assert calls == []


def test_collection_provider_fails_closed_on_wrong_opened_collection(
    monkeypatch,
    tmp_path,
):
    class WrongClient:
        def get_or_create_collection(self, *, name):
            return _FakeCollection("legal_documents")

    monkeypatch.setattr(
        providers.chromadb,
        "PersistentClient",
        lambda *, path: WrongClient(),
    )

    provider = TargetedCandidateChromaCollectionProvider(
        db_root=tmp_path / "db"
    )

    with pytest.raises(TargetedCandidateProviderError):
        provider.open_collection(
            TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
        )


class _FakeEmbeddings:
    def __init__(self, embedding=(0.125, 0.25, 0.5)):
        self.embedding = embedding
        self.calls = []

    def create(self, *, model, input):
        self.calls.append((model, input))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=self.embedding)]
        )


def test_embedding_provider_uses_injected_client_exactly():
    embeddings = _FakeEmbeddings()
    client = SimpleNamespace(embeddings=embeddings)

    provider = OpenAIEmbeddingProvider(client=client)

    assert provider.embed_document(
        model="text-embedding-3-small",
        text="document",
    ) == [0.125, 0.25, 0.5]

    assert provider.embed_query(
        model="text-embedding-3-small",
        text="query",
    ) == [0.125, 0.25, 0.5]

    assert embeddings.calls == [
        ("text-embedding-3-small", "document"),
        ("text-embedding-3-small", "query"),
    ]


def test_embedding_provider_requires_injected_client():
    with pytest.raises(TargetedCandidateProviderError):
        OpenAIEmbeddingProvider(client=None)


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[SimpleNamespace(embedding=None)]),
    ],
)
def test_embedding_provider_fails_closed_on_malformed_response(response):
    class BrokenEmbeddings:
        def create(self, *, model, input):
            return response

    provider = OpenAIEmbeddingProvider(
        client=SimpleNamespace(embeddings=BrokenEmbeddings())
    )

    with pytest.raises(TargetedCandidateProviderError):
        provider.embed_document(
            model="text-embedding-3-small",
            text="x",
        )


def test_provider_module_does_not_import_or_construct_openai_client():
    source = Path(providers.__file__).read_text(encoding="utf-8")
    assert "from openai import" not in source
    assert "OpenAI()" not in source
    assert "from config import openai_client" not in source


def test_provider_module_does_not_reference_legacy_collection():
    source = Path(providers.__file__).read_text(encoding="utf-8")
    assert "derived_transcriptions_v1" not in source
    assert '"legal_documents"' not in source