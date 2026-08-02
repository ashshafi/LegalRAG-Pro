"""Build Chroma metadata filters for case-isolated retrieval."""

from __future__ import annotations

from collections.abc import Sequence

from case_management.document_context import normalise_case_id


def build_retrieval_filter(
    *,
    case_id: str | None,
    selected_documents: Sequence[str] | None = None,
) -> dict[str, object] | None:
    """Return a Chroma ``where`` filter for the requested retrieval scope.

    When a case is active, every query is constrained by ``case_id``. Optional
    filename selection is combined with that case constraint using ``$and``.

    A missing case ID preserves the pre-Sprint-2.1 global retrieval behaviour,
    which is the compatibility path for legacy chunks that do not contain
    ``case_id`` metadata.
    """

    cleaned_case_id = normalise_case_id(case_id)
    documents = [name for name in (selected_documents or []) if name]

    file_filter: dict[str, object] | None = None
    if documents:
        file_filter = {"file": {"$in": documents}}

    if cleaned_case_id is None:
        return file_filter

    case_filter: dict[str, object] = {"case_id": cleaned_case_id}
    if file_filter is None:
        return case_filter

    return {"$and": [case_filter, file_filter]}
