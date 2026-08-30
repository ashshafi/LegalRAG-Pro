from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

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
from .models import (
    ActivationAuthority,
    ActivationError,
    ActivationIndexAction,
    ActivationIndexResult,
    ActivationQueryHit,
    ActivationQueryResult,
    ActivationRow,
    ActivationRowState,
    DERIVED_SEARCH_AUTHORITY_KIND,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^dtx:sha256:[0-9a-f]{64}$")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ActivationError(
            field + " must be non-empty text."
        )


def validate_activation_row(
    *,
    authority: ActivationAuthority,
    row: ActivationRow,
) -> None:
    _require_text(
        authority.case_id,
        "authority.case_id",
    )

    _require_text(
        authority.candidate_id,
        "authority.candidate_id",
    )

    require_governing_model(
        authority.embedding_model
    )

    if not _CANDIDATE_ID.fullmatch(
        authority.candidate_id
    ):
        raise ActivationError(
            "Authority candidate ID is not canonical."
        )

    if not _SHA256.fullmatch(
        authority.transcription_sha256
    ):
        raise ActivationError(
            "Authority transcription SHA256 is not canonical."
        )

    if (
        isinstance(
            authority.transcription_bytes,
            bool,
        )
        or not isinstance(
            authority.transcription_bytes,
            int,
        )
        or authority.transcription_bytes <= 0
    ):
        raise ActivationError(
            "Authority transcription byte length is invalid."
        )

    if row.candidate_id != authority.candidate_id:
        raise ActivationError(
            "Row candidate ID does not match retained authority."
        )

    if row.case_id != authority.case_id:
        raise ActivationError(
            "Row case ID does not match retained authority."
        )

    if row.transcription_sha256 != (
        authority.transcription_sha256
    ):
        raise ActivationError(
            "Row transcription hash does not match retained authority."
        )

    if row.authority_kind != (
        DERIVED_SEARCH_AUTHORITY_KIND
    ):
        raise ActivationError(
            "Row authority kind is not derived_transcription."
        )

    if not isinstance(row.page, int) or isinstance(
        row.page,
        bool,
    ) or row.page <= 0:
        raise ActivationError(
            "Row page must be a positive integer."
        )

    if not _SHA256_ID.fullmatch(
        row.source_snapshot_id
    ):
        raise ActivationError(
            "Source snapshot ID is not canonical."
        )

    if not _SHA256_ID.fullmatch(
        row.derived_record_id
    ):
        raise ActivationError(
            "Derived record ID is not canonical."
        )

    for value, field in (
        (
            row.source_original_blob_sha256,
            "source_original_blob_sha256",
        ),
        (
            row.transcription_sha256,
            "transcription_sha256",
        ),
        (
            row.embedded_image_sha256,
            "embedded_image_sha256",
        ),
    ):
        if not _SHA256.fullmatch(value):
            raise ActivationError(
                field + " is not canonical."
            )

    for value, field in (
        (
            row.source_document_instance_id,
            "source_document_instance_id",
        ),
        (
            row.profile_id,
            "profile_id",
        ),
    ):
        _require_text(value, field)

    if not isinstance(row.document, str) or not row.document:
        raise ActivationError(
            "Derived transcription must be non-empty text."
        )

    raw = row.document.encode("utf-8")

    if len(raw) != authority.transcription_bytes:
        raise ActivationError(
            "Derived transcription byte length differs from authority."
        )

    if hashlib.sha256(
        raw
    ).hexdigest() != authority.transcription_sha256:
        raise ActivationError(
            "Derived transcription SHA256 differs from authority."
        )


def index_retained_candidate(
    *,
    authority: ActivationAuthority,
    row: ActivationRow,
    collection: CollectionLike,
    embedding_provider: EmbeddingProvider,
) -> ActivationIndexResult:
    validate_activation_row(
        authority=authority,
        row=row,
    )

    require_collection_name(
        collection,
        expected=authority.collection_name,
    )

    inspection = inspect_exact_row(
        collection,
        row=row,
    )

    if inspection.state is ActivationRowState.EXACT:
        return ActivationIndexResult(
            action=ActivationIndexAction.UNCHANGED,
            candidate_id=row.candidate_id,
            state=ActivationRowState.EXACT,
        )

    if inspection.state is ActivationRowState.CONFLICTING:
        raise ActivationError(
            "Existing derived-search row conflicts with retained authority."
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

    if post.state is not ActivationRowState.EXACT:
        raise ActivationError(
            "Derived-search row did not become exact after add."
        )

    return ActivationIndexResult(
        action=ActivationIndexAction.ADDED,
        candidate_id=row.candidate_id,
        state=ActivationRowState.EXACT,
    )


def _nested_column(
    result: Mapping[str, Any],
    key: str,
) -> Sequence[Any]:
    value = result.get(key)

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 1
        or not isinstance(value[0], Sequence)
        or isinstance(value[0], (str, bytes))
    ):
        raise ActivationError(
            "Derived-search query returned invalid "
            + key
            + "."
        )

    return value[0]


def query_retained_candidate(
    *,
    authority: ActivationAuthority,
    row: ActivationRow,
    collection: CollectionLike,
    embedding_provider: EmbeddingProvider,
    active_case_id: str,
    query_text: str,
    n_results: int = 5,
) -> ActivationQueryResult:
    validate_activation_row(
        authority=authority,
        row=row,
    )

    require_collection_name(
        collection,
        expected=authority.collection_name,
    )

    if active_case_id != authority.case_id:
        raise ActivationError(
            "Active case does not match the retained derived authority."
        )

    if (
        isinstance(n_results, bool)
        or not isinstance(n_results, int)
        or n_results <= 0
    ):
        raise ActivationError(
            "n_results must be a positive integer."
        )

    query_embedding = embed_query(
        embedding_provider,
        model=authority.embedding_model,
        text=query_text,
    )

    where = {
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
                        active_case_id,
                }
            },
        ]
    }

    try:
        raw = collection.query(
            query_embeddings=[
                query_embedding
            ],
            n_results=n_results,
            where=where,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )
    except Exception as exc:
        raise ActivationError(
            "Derived-search query failed."
        ) from exc

    if not isinstance(raw, Mapping):
        raise ActivationError(
            "Derived-search query result is invalid."
        )

    ids = _nested_column(
        raw,
        "ids",
    )

    documents = _nested_column(
        raw,
        "documents",
    )

    metadatas = _nested_column(
        raw,
        "metadatas",
    )

    distances = _nested_column(
        raw,
        "distances",
    )

    if not (
        len(ids)
        == len(documents)
        == len(metadatas)
        == len(distances)
    ):
        raise ActivationError(
            "Derived-search result columns are misaligned."
        )

    if len(ids) != len(set(ids)):
        raise ActivationError(
            "Derived-search returned duplicate candidate IDs."
        )

    hits: list[ActivationQueryHit] = []

    expected_metadata = row.metadata()

    for candidate_id, document, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):
        if candidate_id != authority.candidate_id:
            raise ActivationError(
                "Derived-search returned an unknown candidate ID."
            )

        if document != row.document:
            raise ActivationError(
                "Derived-search returned tampered derived text."
            )

        if (
            not isinstance(metadata, Mapping)
            or dict(metadata) != expected_metadata
        ):
            raise ActivationError(
                "Derived-search returned tampered metadata."
            )

        if distance is None:
            normalized_distance = None
        elif (
            isinstance(distance, bool)
            or not isinstance(
                distance,
                (int, float),
            )
            or not math.isfinite(
                float(distance)
            )
        ):
            raise ActivationError(
                "Derived-search returned an invalid distance."
            )
        else:
            normalized_distance = float(distance)

        hits.append(
            ActivationQueryHit(
                candidate_id=candidate_id,
                document=document,
                metadata=dict(metadata),
                distance=normalized_distance,
            )
        )

    return ActivationQueryResult(
        hits=tuple(hits),
    )
