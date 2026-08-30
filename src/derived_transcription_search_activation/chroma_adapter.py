from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .models import (
    ActivationError,
    ActivationInspection,
    ActivationRow,
    ActivationRowState,
)


class CollectionLike(Protocol):
    name: str

    def get(
        self,
        *,
        ids: list[str],
        include: list[str],
    ) -> Mapping[str, Any]:
        ...

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[Mapping[str, object]],
        embeddings: list[list[float]],
    ) -> None:
        ...

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: Mapping[str, object],
        include: list[str],
    ) -> Mapping[str, Any]:
        ...


def require_collection_name(
    collection: CollectionLike,
    *,
    expected: str,
) -> None:
    if getattr(collection, "name", None) != expected:
        raise ActivationError(
            "Injected collection does not match the dedicated "
            "derived-search collection authority."
        )


def inspect_exact_row(
    collection: CollectionLike,
    *,
    row: ActivationRow,
) -> ActivationInspection:
    try:
        result = collection.get(
            ids=[row.candidate_id],
            include=[
                "documents",
                "metadatas",
            ],
        )
    except Exception as exc:
        raise ActivationError(
            "Derived-search collection inspection failed."
        ) from exc

    if not isinstance(result, Mapping):
        raise ActivationError(
            "Derived-search collection returned an invalid get result."
        )

    ids = result.get("ids")
    documents = result.get("documents")
    metadatas = result.get("metadatas")

    if not isinstance(ids, Sequence) or isinstance(
        ids,
        (str, bytes),
    ):
        raise ActivationError(
            "Derived-search get result has invalid ids."
        )

    if len(ids) == 0:
        return ActivationInspection(
            state=ActivationRowState.MISSING,
            reason="candidate row is absent",
        )

    if len(ids) != 1:
        raise ActivationError(
            "Derived-search get result cardinality is not one."
        )

    if ids[0] != row.candidate_id:
        raise ActivationError(
            "Derived-search get result returned an unexpected ID."
        )

    if (
        not isinstance(documents, Sequence)
        or isinstance(documents, (str, bytes))
        or len(documents) != 1
        or not isinstance(documents[0], str)
    ):
        raise ActivationError(
            "Derived-search get result has invalid documents."
        )

    if (
        not isinstance(metadatas, Sequence)
        or isinstance(metadatas, (str, bytes))
        or len(metadatas) != 1
        or not isinstance(metadatas[0], Mapping)
    ):
        raise ActivationError(
            "Derived-search get result has invalid metadata."
        )

    if (
        documents[0] == row.document
        and dict(metadatas[0]) == row.metadata()
    ):
        return ActivationInspection(
            state=ActivationRowState.EXACT,
            reason="stored derived-search row is exact",
        )

    return ActivationInspection(
        state=ActivationRowState.CONFLICTING,
        reason="stored derived-search row conflicts with authority",
    )


def add_exact_row(
    collection: CollectionLike,
    *,
    row: ActivationRow,
    embedding: list[float],
) -> None:
    collection.add(
        ids=[row.candidate_id],
        documents=[row.document],
        metadatas=[row.metadata()],
        embeddings=[embedding],
    )
