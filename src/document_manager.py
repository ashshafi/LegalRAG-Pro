"""Document metadata and migration operations for LegalRAG Pro."""

from __future__ import annotations

from pathlib import Path

import chromadb

from case_management.document_context import (
    document_names_from_metadatas,
    normalise_case_id,
)
from case_management.migration import (
    LegacyAssignmentPlan,
    apply_legacy_assignment,
    build_legacy_assignment_plan,
    list_legacy_documents as _list_legacy_documents,
)

DB_PATH = Path("db").resolve()

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection("legal_documents")


def get_documents(case_id: str | None = None) -> list[str]:
    """Return unique indexed filenames, optionally restricted to one case."""

    cleaned_case_id = normalise_case_id(case_id)
    kwargs: dict[str, object] = {"include": ["metadatas"]}

    if cleaned_case_id is not None:
        kwargs["where"] = {"case_id": cleaned_case_id}

    results = collection.get(**kwargs)

    return document_names_from_metadatas(results["metadatas"])


def get_legacy_documents() -> list[str]:
    """Return documents that still contain unassigned legacy chunks."""

    return _list_legacy_documents(collection)


def preview_legacy_assignment(
    filename: str,
    case_id: str,
) -> LegacyAssignmentPlan:
    """Return the chunks that would be assigned without changing Chroma."""

    return build_legacy_assignment_plan(
        collection,
        filename=filename,
        case_id=case_id,
    )


def commit_legacy_assignment(plan: LegacyAssignmentPlan) -> int:
    """Assign reviewed legacy chunks to a case without re-embedding."""

    return apply_legacy_assignment(collection, plan)
