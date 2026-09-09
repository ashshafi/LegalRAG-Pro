from __future__ import annotations

from collections.abc import Sequence
import math
from typing import Protocol

from models import EMBEDDING_MODEL

from . import TargetedCandidateActivationError


class EmbeddingProvider(Protocol):
    def embed_document(self, *, model: str, text: str) -> Sequence[float]:
        ...

    def embed_query(self, *, model: str, text: str) -> Sequence[float]:
        ...


def require_governing_model(model: str) -> None:
    if model != EMBEDDING_MODEL:
        raise TargetedCandidateActivationError(
            "Embedding model does not match the governing src/models.py::EMBEDDING_MODEL authority."
        )


def _validated_embedding(values: Sequence[float]) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TargetedCandidateActivationError(
            "Embedding provider returned a non-sequence result."
        )

    if len(values) == 0:
        raise TargetedCandidateActivationError(
            "Embedding provider returned an empty embedding."
        )

    normalized: list[float] = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise TargetedCandidateActivationError(
                "Embedding provider returned a non-finite real value."
            )
        normalized.append(float(value))

    return normalized


def embed_document(
    provider: EmbeddingProvider,
    *,
    model: str,
    text: str,
) -> list[float]:
    require_governing_model(model)

    if not isinstance(text, str) or not text:
        raise TargetedCandidateActivationError(
            "Targeted-candidate document embedding input must be non-empty text."
        )

    return _validated_embedding(
        provider.embed_document(
            model=model,
            text=text,
        )
    )


def embed_query(
    provider: EmbeddingProvider,
    *,
    model: str,
    text: str,
) -> list[float]:
    require_governing_model(model)

    if not isinstance(text, str) or not text.strip():
        raise TargetedCandidateActivationError(
            "Targeted-candidate query must be non-empty text."
        )

    return _validated_embedding(
        provider.embed_query(
            model=model,
            text=text,
        )
    )
