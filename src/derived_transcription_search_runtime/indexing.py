from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from derived_transcription_search import (
    DerivedTranscriptionSearchRow,
    build_collection_add_payload,
    validate_row,
)

from .models import (
    DerivedSearchIndexAction,
    DerivedSearchIndexResult,
    DerivedSearchRowInspection,
    DerivedSearchRowState,
)


class DerivedSearchIndexError(RuntimeError):
    """Raised when disposable derived-index authority cannot be proved exactly."""


def _flat_sequence(
    response: Mapping[str, Any],
    key: str,
) -> tuple[Any, ...]:

    value = response.get(
        key,
        (),
    )

    if value is None:
        return ()

    if not isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        raise DerivedSearchIndexError(
            "Collection get response field "
            + repr(
                key
            )
            + " must be a flat sequence."
        )

    return tuple(
        value
    )


def inspect_row(
    *,
    collection: Any,
    row: DerivedTranscriptionSearchRow,
) -> DerivedSearchRowInspection:

    validate_row(
        row
    )

    response = collection.get(
        ids=[
            row.row_id
        ],
        include=[
            "documents",
            "metadatas",
        ],
    )

    if not isinstance(
        response,
        Mapping,
    ):
        raise DerivedSearchIndexError(
            "Collection get response must be a mapping."
        )

    ids = _flat_sequence(
        response,
        "ids",
    )

    documents = _flat_sequence(
        response,
        "documents",
    )

    metadatas = _flat_sequence(
        response,
        "metadatas",
    )

    if not ids:

        if documents or metadatas:
            raise DerivedSearchIndexError(
                "Collection returned content without a row identity."
            )

        return DerivedSearchRowInspection(
            row_id=row.row_id,
            state=DerivedSearchRowState.MISSING,
        )

    if (
        len(ids) != 1
        or len(documents) != 1
        or len(metadatas) != 1
    ):
        raise DerivedSearchIndexError(
            "Collection get response is not an exact singleton."
        )

    observed_id = ids[0]
    observed_document = documents[0]
    observed_metadata = metadatas[0]

    if observed_id != row.row_id:
        raise DerivedSearchIndexError(
            "Collection returned the wrong row identity."
        )

    if not isinstance(
        observed_document,
        str,
    ):
        raise DerivedSearchIndexError(
            "Collection returned a non-text document."
        )

    if not isinstance(
        observed_metadata,
        Mapping,
    ):
        raise DerivedSearchIndexError(
            "Collection returned non-mapping metadata."
        )

    if (
        observed_document
        == row.document
        and dict(
            observed_metadata
        )
        == dict(
            row.metadata
        )
    ):

        return DerivedSearchRowInspection(
            row_id=row.row_id,
            state=DerivedSearchRowState.EXACT,
        )

    return DerivedSearchRowInspection(
        row_id=row.row_id,
        state=DerivedSearchRowState.CONFLICTING,
    )


def inspect_rows(
    *,
    collection: Any,
    rows: Sequence[
        DerivedTranscriptionSearchRow
    ],
) -> tuple[
    DerivedSearchRowInspection,
    ...,
]:

    canonical = tuple(
        rows
    )

    if not canonical:
        raise DerivedSearchIndexError(
            "rows must contain at least one derived-search row."
        )

    row_ids = []

    for row in canonical:

        validate_row(
            row
        )

        row_ids.append(
            row.row_id
        )

    if len(
        set(
            row_ids
        )
    ) != len(
        row_ids
    ):
        raise DerivedSearchIndexError(
            "rows contain duplicate derived-search identities."
        )

    return tuple(
        inspect_row(
            collection=collection,
            row=row,
        )
        for row in canonical
    )


def index_rows_idempotent(
    *,
    collection: Any,
    rows: Sequence[
        DerivedTranscriptionSearchRow
    ],
) -> tuple[
    DerivedSearchIndexResult,
    ...,
]:

    canonical = tuple(
        rows
    )

    before = inspect_rows(
        collection=collection,
        rows=canonical,
    )

    if any(
        item.state
        is DerivedSearchRowState.CONFLICTING
        for item in before
    ):
        raise DerivedSearchIndexError(
            "Conflicting derived-search state detected before write; no add is permitted."
        )

    missing_ids = {
        item.row_id
        for item in before
        if (
            item.state
            is DerivedSearchRowState.MISSING
        )
    }

    missing_rows = tuple(
        row
        for row in canonical
        if row.row_id in missing_ids
    )

    if missing_rows:

        payload = build_collection_add_payload(
            missing_rows
        )

        collection.add(
            **payload
        )

    after = inspect_rows(
        collection=collection,
        rows=canonical,
    )

    if any(
        item.state
        is not DerivedSearchRowState.EXACT
        for item in after
    ):
        raise DerivedSearchIndexError(
            "Derived-search index did not reconcile to exact state after add."
        )

    after_by_id = {
        item.row_id:
            item
        for item in after
    }

    return tuple(
        DerivedSearchIndexResult(
            row_id=row.row_id,
            action=(
                DerivedSearchIndexAction.ADDED
                if row.row_id
                in missing_ids
                else
                DerivedSearchIndexAction.UNCHANGED
            ),
            final_state=
                after_by_id[
                    row.row_id
                ].state,
        )
        for row in canonical
    )
