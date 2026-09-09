from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any, Protocol

from . import (
    TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
    TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationError,
    TargetedCandidateActivationRow,
    validate_current_review_binding,
    validate_targeted_candidate_activation_authority,
    validate_targeted_candidate_activation_row,
)
from .chroma_adapter import (
    CollectionLike,
    add_exact_row,
    inspect_exact_row,
    require_collection_name,
)
from .embedding import (
    EmbeddingProvider,
    embed_document,
    embed_query,
    require_governing_model,
)
from .runtime_models import (
    TargetedCandidateActivationIndexAction,
    TargetedCandidateActivationIndexResult,
    TargetedCandidateActivationQueryHit,
    TargetedCandidateActivationQueryResult,
    TargetedCandidateActivationRowState,
)


class CollectionProvider(Protocol):
    def open_collection(self, name: str) -> CollectionLike:
        ...


class ReviewProjectionLoader(Protocol):
    def load_latest(self, candidate_record_id: str) -> Any:
        ...


ActivationPair = tuple[
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationRow,
]


def _validate_structural_pair(
    authority: TargetedCandidateActivationAuthority,
    row: TargetedCandidateActivationRow,
) -> None:
    validate_targeted_candidate_activation_authority(
        authority=authority,
    )
    validate_targeted_candidate_activation_row(
        authority=authority,
        row=row,
    )
    require_governing_model(
        authority.embedding_model
    )


def _require_successor_collection_authority(
    authority: TargetedCandidateActivationAuthority,
) -> None:
    if authority.collection_name != TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME:
        raise TargetedCandidateActivationError(
            "Authority collection name is not the dedicated targeted-candidate collection."
        )


def _open_successor_collection(
    provider: CollectionProvider,
) -> CollectionLike:
    collection = provider.open_collection(
        TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME
    )
    require_collection_name(
        collection,
        expected=TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
    )
    return collection


def index_targeted_candidate(
    *,
    authority: TargetedCandidateActivationAuthority,
    row: TargetedCandidateActivationRow,
    review_loader: ReviewProjectionLoader,
    collection_provider: CollectionProvider,
    embedding_provider: EmbeddingProvider,
) -> TargetedCandidateActivationIndexResult:
    _validate_structural_pair(authority, row)

    current_projection = review_loader.load_latest(
        row.candidate_record_id
    )
    validate_current_review_binding(
        authority=authority,
        row=row,
        review_projection=current_projection,
    )

    _require_successor_collection_authority(authority)

    collection = _open_successor_collection(
        collection_provider
    )

    inspection = inspect_exact_row(
        collection,
        row=row,
    )

    if inspection.state is TargetedCandidateActivationRowState.EXACT:
        return TargetedCandidateActivationIndexResult(
            action=TargetedCandidateActivationIndexAction.UNCHANGED,
            candidate_record_id=row.candidate_record_id,
            state=TargetedCandidateActivationRowState.EXACT,
        )

    if inspection.state is TargetedCandidateActivationRowState.CONFLICTING:
        raise TargetedCandidateActivationError(
            "Existing targeted-candidate row conflicts with retained authority."
        )

    embedding = embed_document(
        embedding_provider,
        model=authority.embedding_model,
        text=row.document,
    )

    add_exact_row(
        collection,
        row=row,
        embedding=embedding,
    )

    post = inspect_exact_row(
        collection,
        row=row,
    )
    if post.state is not TargetedCandidateActivationRowState.EXACT:
        raise TargetedCandidateActivationError(
            "Targeted-candidate row did not become exact after add."
        )

    return TargetedCandidateActivationIndexResult(
        action=TargetedCandidateActivationIndexAction.ADDED,
        candidate_record_id=row.candidate_record_id,
        state=TargetedCandidateActivationRowState.EXACT,
    )


def _nested_column(
    raw: Mapping[str, Any],
    name: str,
) -> list[Any]:
    outer = raw.get(name)

    if (
        not isinstance(outer, Sequence)
        or isinstance(outer, (str, bytes))
        or len(outer) != 1
    ):
        raise TargetedCandidateActivationError(
            f"Targeted-candidate query result has invalid {name}."
        )

    inner = outer[0]
    if (
        not isinstance(inner, Sequence)
        or isinstance(inner, (str, bytes))
    ):
        raise TargetedCandidateActivationError(
            f"Targeted-candidate query result has invalid nested {name}."
        )

    return list(inner)


def query_targeted_candidates(
    *,
    activations: tuple[ActivationPair, ...],
    review_loader: ReviewProjectionLoader,
    collection_provider: CollectionProvider,
    embedding_provider: EmbeddingProvider,
    active_case_id: str,
    query_text: str,
    n_results: int = 5,
) -> TargetedCandidateActivationQueryResult:
    if not isinstance(activations, tuple) or len(activations) == 0:
        raise TargetedCandidateActivationError(
            "Targeted-candidate query requires a non-empty activation tuple."
        )

    if not isinstance(active_case_id, str) or not active_case_id:
        raise TargetedCandidateActivationError(
            "Active case ID must be non-empty text."
        )

    if (
        isinstance(n_results, bool)
        or not isinstance(n_results, int)
        or n_results <= 0
    ):
        raise TargetedCandidateActivationError(
            "n_results must be a positive integer."
        )

    if not isinstance(query_text, str) or not query_text.strip():
        raise TargetedCandidateActivationError(
            "Targeted-candidate query must be non-empty text."
        )

    candidate_ids = tuple(
        row.candidate_record_id
        for _, row in activations
    )

    if any(
        not isinstance(candidate_id, str) or not candidate_id
        for candidate_id in candidate_ids
    ):
        raise TargetedCandidateActivationError(
            "Targeted-candidate activation tuple contains an invalid candidate ID."
        )

    if len(candidate_ids) != len(set(candidate_ids)):
        raise TargetedCandidateActivationError(
            "Targeted-candidate activation tuple contains duplicate candidate IDs."
        )

    for authority, row in activations:
        _validate_structural_pair(authority, row)

    for authority, _ in activations:
        if authority.case_id != active_case_id:
            raise TargetedCandidateActivationError(
                "Active case does not match a supplied targeted-candidate authority."
            )
        _require_successor_collection_authority(authority)

    registry: dict[str, tuple[
        TargetedCandidateActivationAuthority,
        TargetedCandidateActivationRow,
    ]] = {
        row.candidate_record_id: (authority, row)
        for authority, row in activations
    }

    # Mandatory pre-collection current-review gate for every activation.
    for authority, row in activations:
        current_projection = review_loader.load_latest(
            row.candidate_record_id
        )
        validate_current_review_binding(
            authority=authority,
            row=row,
            review_projection=current_projection,
        )

    collection = _open_successor_collection(
        collection_provider
    )

    # Every supplied row must be exact before any query embedding call.
    for _, row in activations:
        inspection = inspect_exact_row(
            collection,
            row=row,
        )
        if inspection.state is not TargetedCandidateActivationRowState.EXACT:
            raise TargetedCandidateActivationError(
                "Every supplied targeted-candidate row must be exact before query embedding."
            )

    governing_authority = activations[0][0]
    query_embedding = embed_query(
        embedding_provider,
        model=governing_authority.embedding_model,
        text=query_text,
    )

    where = {
        "$and": [
            {
                "authority_kind": {
                    "$eq": TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
                }
            },
            {
                "case_id": {
                    "$eq": active_case_id,
                }
            },
        ]
    }

    try:
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )
    except Exception as exc:
        raise TargetedCandidateActivationError(
            "Targeted-candidate query failed."
        ) from exc

    if not isinstance(raw, Mapping):
        raise TargetedCandidateActivationError(
            "Targeted-candidate query result is invalid."
        )

    ids = _nested_column(raw, "ids")
    documents = _nested_column(raw, "documents")
    metadatas = _nested_column(raw, "metadatas")
    distances = _nested_column(raw, "distances")

    if not (
        len(ids)
        == len(documents)
        == len(metadatas)
        == len(distances)
    ):
        raise TargetedCandidateActivationError(
            "Targeted-candidate result columns are misaligned."
        )

    if len(ids) != len(set(ids)):
        raise TargetedCandidateActivationError(
            "Targeted-candidate query returned duplicate candidate IDs."
        )

    hits: list[TargetedCandidateActivationQueryHit] = []

    for candidate_id, document, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):
        pair = registry.get(candidate_id)
        if pair is None:
            raise TargetedCandidateActivationError(
                "Targeted-candidate query returned an unknown candidate ID."
            )

        _, expected_row = pair

        if document != expected_row.document:
            raise TargetedCandidateActivationError(
                "Targeted-candidate query returned tampered derived text."
            )

        if (
            not isinstance(metadata, Mapping)
            or dict(metadata) != expected_row.metadata()
        ):
            raise TargetedCandidateActivationError(
                "Targeted-candidate query returned tampered metadata."
            )

        if distance is None:
            normalized_distance = None
        elif (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not math.isfinite(float(distance))
        ):
            raise TargetedCandidateActivationError(
                "Targeted-candidate query returned an invalid distance."
            )
        else:
            normalized_distance = float(distance)

        hits.append(
            TargetedCandidateActivationQueryHit(
                candidate_record_id=candidate_id,
                document=document,
                metadata=dict(metadata),
                distance=normalized_distance,
            )
        )

    # Empty hits are a discovery result only; callers must not interpret them
    # as an authoritative negative legal finding.
    return TargetedCandidateActivationQueryResult(
        hits=tuple(hits),
    )
