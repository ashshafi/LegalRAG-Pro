from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from . import (
    TargetedCandidateActivationError,
    TargetedCandidateActivationRow,
)
from .runtime_models import (
    TargetedCandidateActivationInspection,
    TargetedCandidateActivationRowState,
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
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        ...

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any],
        include: list[str],
    ) -> Mapping[str, Any]:
        ...


def require_collection_name(
    collection: CollectionLike,
    *,
    expected: str,
) -> None:
    if getattr(collection, "name", None) != expected:
        raise TargetedCandidateActivationError(
            "Injected collection does not match the dedicated targeted-candidate collection authority."
        )


def inspect_exact_row(
    collection: CollectionLike,
    *,
    row: TargetedCandidateActivationRow,
) -> TargetedCandidateActivationInspection:
    try:
        result = collection.get(
            ids=[row.candidate_record_id],
            include=[
                "documents",
                "metadatas",
            ],
        )
    except Exception as exc:
        raise TargetedCandidateActivationError(
            "Targeted-candidate collection inspection failed."
        ) from exc

    if not isinstance(result, Mapping):
        raise TargetedCandidateActivationError(
            "Targeted-candidate collection returned an invalid get result."
        )

    ids = result.get("ids")
    documents = result.get("documents")
    metadatas = result.get("metadatas")

    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        raise TargetedCandidateActivationError(
            "Targeted-candidate get result has invalid ids."
        )

    if len(ids) == 0:
        return TargetedCandidateActivationInspection(
            state=TargetedCandidateActivationRowState.MISSING,
            reason="targeted-candidate row is absent",
        )

    if len(ids) != 1:
        raise TargetedCandidateActivationError(
            "Targeted-candidate get result cardinality is not one."
        )

    if ids[0] != row.candidate_record_id:
        raise TargetedCandidateActivationError(
            "Targeted-candidate get result returned an unexpected ID."
        )

    if (
        not isinstance(documents, Sequence)
        or isinstance(documents, (str, bytes))
        or len(documents) != 1
        or not isinstance(documents[0], str)
    ):
        raise TargetedCandidateActivationError(
            "Targeted-candidate get result has invalid documents."
        )

    if (
        not isinstance(metadatas, Sequence)
        or isinstance(metadatas, (str, bytes))
        or len(metadatas) != 1
        or not isinstance(metadatas[0], Mapping)
    ):
        raise TargetedCandidateActivationError(
            "Targeted-candidate get result has invalid metadata."
        )

    if (
        documents[0] == row.document
        and dict(metadatas[0]) == row.metadata()
    ):
        return TargetedCandidateActivationInspection(
            state=TargetedCandidateActivationRowState.EXACT,
            reason="stored targeted-candidate row is exact",
        )

    return TargetedCandidateActivationInspection(
        state=TargetedCandidateActivationRowState.CONFLICTING,
        reason="stored targeted-candidate row conflicts with authority",
    )


def add_exact_row(
    collection: CollectionLike,
    *,
    row: TargetedCandidateActivationRow,
    embedding: list[float],
) -> None:
    collection.add(
        ids=[row.candidate_record_id],
        documents=[row.document],
        metadatas=[row.metadata()],
        embeddings=[embedding],
    )
