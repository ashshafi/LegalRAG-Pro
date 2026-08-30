from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import math
from typing import Any
from uuid import UUID

from derived_transcription_search import (
    DERIVED_SEARCH_AUTHORITY_KIND,
    DerivedTranscriptionSearchRow,
    validate_row,
)

from .models import (
    DERIVED_SEARCH_DISCOVERY_SCOPE,
    DerivedSearchQueryResult,
    VerifiedDerivedSearchHit,
)


class DerivedSearchQueryError(RuntimeError):
    """Raised when a derived-search query result cannot be verified exactly."""


EmbeddingFunction = Callable[
    [str],
    Sequence[
        float
    ],
]


def _canonical_uuid(
    value: object,
    *,
    field_name: str,
) -> str:

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise DerivedSearchQueryError(
            field_name
            + " must be non-empty text."
        )

    try:
        canonical = str(
            UUID(
                value
            )
        )

    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:

        raise DerivedSearchQueryError(
            field_name
            + " must be a canonical UUID."
        ) from exc

    if canonical != value:
        raise DerivedSearchQueryError(
            field_name
            + " must be a canonical UUID."
        )

    return value


def _query_text(
    value: object,
) -> str:

    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise DerivedSearchQueryError(
            "query must contain non-whitespace text."
        )

    return value


def _embedding(
    value: Sequence[
        float
    ],
) -> list[
    float
]:

    try:
        items = tuple(
            value
        )
    except TypeError as exc:
        raise DerivedSearchQueryError(
            "embedding function must return a numeric sequence."
        ) from exc

    if not items:
        raise DerivedSearchQueryError(
            "embedding function returned an empty vector."
        )

    result = []

    for item in items:

        if (
            isinstance(
                item,
                bool,
            )
            or not isinstance(
                item,
                (
                    int,
                    float,
                ),
            )
        ):
            raise DerivedSearchQueryError(
                "embedding vector contains a non-numeric value."
            )

        numeric = float(
            item
        )

        if not math.isfinite(
            numeric
        ):
            raise DerivedSearchQueryError(
                "embedding vector contains a non-finite value."
            )

        result.append(
            numeric
        )

    return result


def _nested_result(
    response: Mapping[str, Any],
    key: str,
) -> tuple[Any, ...]:

    value = response.get(
        key,
    )

    if value is None:
        raise DerivedSearchQueryError(
            "Collection query response is missing "
            + repr(
                key
            )
            + "."
        )

    if (
        not isinstance(
            value,
            (
                list,
                tuple,
            )
        )
        or len(
            value
        ) != 1
    ):
        raise DerivedSearchQueryError(
            "Collection query field "
            + repr(
                key
            )
            + " must contain exactly one result list."
        )

    inner = value[0]

    if not isinstance(
        inner,
        (
            list,
            tuple,
        )
    ):
        raise DerivedSearchQueryError(
            "Collection query field "
            + repr(
                key
            )
            + " has an invalid result shape."
        )

    return tuple(
        inner
    )


def query_derived_candidates(
    *,
    collection: Any,
    query: str,
    case_id: str,
    authorities: Sequence[
        DerivedTranscriptionSearchRow
    ],
    embedder: EmbeddingFunction,
    n_results: int = 10,
) -> DerivedSearchQueryResult:

    canonical_query = _query_text(
        query
    )

    canonical_case = _canonical_uuid(
        case_id,
        field_name="case_id",
    )

    if (
        type(n_results) is not int
        or n_results < 1
    ):
        raise DerivedSearchQueryError(
            "n_results must be a positive integer."
        )

    expected_rows = tuple(
        authorities
    )

    expected_by_id = {}

    for row in expected_rows:

        validate_row(
            row
        )

        if row.row_id in expected_by_id:
            raise DerivedSearchQueryError(
                "authorities contain duplicate row identities."
            )

        expected_by_id[
            row.row_id
        ] = row

    if not expected_by_id:
        raise DerivedSearchQueryError(
            "authorities must contain at least one governed derived-search row."
        )

    for row in expected_rows:

        if (
            row.candidate.case_id
            != canonical_case
        ):
            raise DerivedSearchQueryError(
                "Governed derived-search authority belongs to the wrong case."
            )

    vector = _embedding(
        embedder(
            canonical_query
        )
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
                        canonical_case,
                }
            },
        ]
    }

    response = collection.query(
        query_embeddings=[
            vector
        ],
        n_results=n_results,
        where=where,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    if not isinstance(
        response,
        Mapping,
    ):
        raise DerivedSearchQueryError(
            "Collection query response must be a mapping."
        )

    ids = _nested_result(
        response,
        "ids",
    )

    documents = _nested_result(
        response,
        "documents",
    )

    metadatas = _nested_result(
        response,
        "metadatas",
    )

    distances = _nested_result(
        response,
        "distances",
    )

    lengths = {
        len(ids),
        len(documents),
        len(metadatas),
        len(distances),
    }

    if len(
        lengths
    ) != 1:
        raise DerivedSearchQueryError(
            "Collection query result fields have different lengths."
        )

    if len(
        set(
            ids
        )
    ) != len(
        ids
    ):
        raise DerivedSearchQueryError(
            "Collection query returned duplicate row identities."
        )

    hits = []

    for (
        row_id,
        document,
        metadata,
        distance,
    ) in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):

        if not isinstance(
            row_id,
            str,
        ):
            raise DerivedSearchQueryError(
                "Collection returned a non-text row identity."
            )

        expected = expected_by_id.get(
            row_id
        )

        if expected is None:
            raise DerivedSearchQueryError(
                "Collection returned an unknown derived-search identity."
            )

        if (
            expected.candidate.case_id
            != canonical_case
        ):
            raise DerivedSearchQueryError(
                "Returned authority belongs to the wrong case."
            )

        if not isinstance(
            document,
            str,
        ):
            raise DerivedSearchQueryError(
                "Collection returned a non-text document."
            )

        if document != expected.document:
            raise DerivedSearchQueryError(
                "Collection returned derived text that differs from governed authority."
            )

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise DerivedSearchQueryError(
                "Collection returned non-mapping metadata."
            )

        if (
            dict(
                metadata
            )
            != dict(
                expected.metadata
            )
        ):
            raise DerivedSearchQueryError(
                "Collection returned metadata that differs from governed derived authority."
            )

        if (
            metadata.get(
                "authority_kind"
            )
            != DERIVED_SEARCH_AUTHORITY_KIND
        ):
            raise DerivedSearchQueryError(
                "Returned row has the wrong authority kind."
            )

        if (
            metadata.get(
                "case_id"
            )
            != canonical_case
        ):
            raise DerivedSearchQueryError(
                "Returned row has the wrong active case."
            )

        if (
            isinstance(
                distance,
                bool,
            )
            or not isinstance(
                distance,
                (
                    int,
                    float,
                ),
            )
        ):
            raise DerivedSearchQueryError(
                "Collection returned a non-numeric distance."
            )

        numeric_distance = float(
            distance
        )

        if not math.isfinite(
            numeric_distance
        ):
            raise DerivedSearchQueryError(
                "Collection returned a non-finite distance."
            )

        hits.append(
            VerifiedDerivedSearchHit(
                row_id=row_id,
                document=document,
                metadata=metadata,
                distance=numeric_distance,
            )
        )

    query_digest = (
        "sha256:"
        + hashlib.sha256(
            canonical_query.encode(
                "utf-8"
            )
        ).hexdigest()
    )

    return DerivedSearchQueryResult(
        case_id=canonical_case,
        query_sha256=query_digest,
        discovery_scope=
            DERIVED_SEARCH_DISCOVERY_SCOPE,
        hits=tuple(
            hits
        ),
    )
