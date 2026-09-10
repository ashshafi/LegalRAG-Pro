"""Concrete production-provider adapters for targeted-candidate search.

The classes in this module satisfy the provider protocols owned by the
successor runtime.  Construction is side-effect free: no Chroma collection is
opened and no OpenAI request is made until the corresponding provider method
is explicitly invoked by the governed service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from candidate_transcription import (
    CandidateTranscriptionStore,
    TranscriptionReviewEventStore,
)
from candidate_transcription.review import project_transcription_review

from .models import TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME


class TargetedCandidateProviderError(RuntimeError):
    """Fail-closed provider-adapter error."""


class ExternalTranscriptionReviewProjectionLoader:
    """Load the current candidate review projection from governed stores."""

    def __init__(
        self,
        *,
        candidate_root: str | Path,
        review_root: str | Path,
    ) -> None:
        self._candidate_root = Path(candidate_root)
        self._review_root = Path(review_root)

    def load_latest(self, candidate_record_id: str) -> Any:
        if not isinstance(candidate_record_id, str) or not candidate_record_id:
            raise TargetedCandidateProviderError(
                "candidate_record_id must be non-empty text."
            )

        candidate = CandidateTranscriptionStore(
            self._candidate_root
        ).load_candidate(candidate_record_id)

        if candidate.record_id != candidate_record_id:
            raise TargetedCandidateProviderError(
                "Loaded candidate identity does not match requested candidate_record_id."
            )

        events = TranscriptionReviewEventStore(
            self._review_root
        ).load_events(candidate_record_id)

        projection = project_transcription_review(events)
        if projection is None:
            raise TargetedCandidateProviderError(
                "Current transcription review projection is absent."
            )

        if projection.candidate_record_id != candidate_record_id:
            raise TargetedCandidateProviderError(
                "Projected review candidate identity does not match request."
            )

        return projection


class TargetedCandidateChromaCollectionProvider:
    """Open only the dedicated successor collection in the exact DB root."""

    def __init__(self, *, db_root: str | Path) -> None:
        self._db_root = Path(db_root)

    def open_collection(self, name: str) -> Any:
        if name != TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME:
            raise TargetedCandidateProviderError(
                "Only the dedicated targeted-candidate collection may be opened."
            )

        client = chromadb.PersistentClient(path=str(self._db_root))
        collection = client.get_or_create_collection(name=name)

        actual_name = getattr(collection, "name", None)
        if actual_name != TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME:
            raise TargetedCandidateProviderError(
                "Opened Chroma collection name does not match successor authority."
            )

        return collection


class OpenAIEmbeddingProvider:
    """Use an injected configured OpenAI-compatible client for embeddings."""

    def __init__(self, *, client: Any) -> None:
        if client is None:
            raise TargetedCandidateProviderError(
                "Embedding client must be supplied."
            )
        self._client = client

    def _embed(self, *, model: str, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=model,
            input=text,
        )

        data = getattr(response, "data", None)
        if not data:
            raise TargetedCandidateProviderError(
                "Embedding response contains no data."
            )

        embedding = getattr(data[0], "embedding", None)
        if embedding is None:
            raise TargetedCandidateProviderError(
                "Embedding response contains no embedding."
            )

        return list(embedding)

    def embed_document(self, *, model: str, text: str) -> list[float]:
        return self._embed(model=model, text=text)

    def embed_query(self, *, model: str, text: str) -> list[float]:
        return self._embed(model=model, text=text)


__all__ = [
    "ExternalTranscriptionReviewProjectionLoader",
    "OpenAIEmbeddingProvider",
    "TargetedCandidateChromaCollectionProvider",
    "TargetedCandidateProviderError",
]