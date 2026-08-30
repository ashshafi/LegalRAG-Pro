from __future__ import annotations

from collections.abc import Sequence
import math
from typing import Protocol

from models import EMBEDDING_MODEL

from .models import ActivationError


class EmbeddingProvider(Protocol):
    def embed_document(
        self,
        *,
        model: str,
        text: str,
    ) -> Sequence[float]:
        ...

    def embed_query(
        self,
        *,
        model: str,
        text: str,
    ) -> Sequence[float]:
        ...


def require_governing_model(model: str) -> None:
    if model != EMBEDDING_MODEL:
        raise ActivationError(
            "Embedding model does not match the governing "
            "src/models.py::EMBEDDING_MODEL authority."
        )


def _validated_embedding(
    values: Sequence[float],
) -> list[float]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
        or not values
    ):
        raise ActivationError(
            "Embedding provider returned no usable embedding."
        )

    result: list[float] = []

    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise ActivationError(
                "Embedding provider returned a non-numeric value."
            )

        number = float(value)

        if not math.isfinite(number):
            raise ActivationError(
                "Embedding provider returned a non-finite value."
            )

        result.append(number)

    return result


def embed_document(
    provider: EmbeddingProvider,
    *,
    model: str,
    text: str,
) -> list[float]:
    require_governing_model(model)

    if not isinstance(text, str) or not text:
        raise ActivationError(
            "Document embedding input must be non-empty text."
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

    if (
        not isinstance(text, str)
        or not text.strip()
    ):
        raise ActivationError(
            "Derived-search query must be non-empty text."
        )

    return _validated_embedding(
        provider.embed_query(
            model=model,
            text=text,
        )
    )
