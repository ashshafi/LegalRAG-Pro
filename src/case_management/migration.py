"""Controlled assignment of legacy Chroma document chunks to cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from case_management.document_context import normalise_case_id


@dataclass(frozen=True, slots=True)
class LegacyAssignmentPlan:
    """Describe the legacy chunks that can be assigned to one case."""

    filename: str
    case_id: str
    chunk_ids: tuple[str, ...]
    metadatas: tuple[dict[str, Any], ...]

    @property
    def chunk_count(self) -> int:
        """Return the number of chunks included in the assignment."""

        return len(self.chunk_ids)


def list_legacy_documents(collection: Any) -> list[str]:
    """Return filenames having at least one chunk without ``case_id``."""

    results = collection.get(include=["metadatas"])
    return sorted(
        {
            metadata["file"]
            for metadata in results.get("metadatas", [])
            if metadata
            and "file" in metadata
            and not normalise_case_id(metadata.get("case_id"))
        }
    )


def build_legacy_assignment_plan(
    collection: Any,
    *,
    filename: str,
    case_id: str,
) -> LegacyAssignmentPlan:
    """Build, but do not apply, a safe assignment plan.

    Only chunks whose metadata currently has no usable ``case_id`` are included.
    Already assigned chunks are never moved between cases by this workflow.
    """

    cleaned_filename = filename.strip()
    cleaned_case_id = normalise_case_id(case_id)

    if not cleaned_filename:
        raise ValueError("Document filename must not be empty.")
    if cleaned_case_id is None:
        raise ValueError("Target case ID must not be empty.")

    results = collection.get(
        where={"file": cleaned_filename},
        include=["metadatas"],
    )

    chunk_ids: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk_id, metadata in zip(
        results.get("ids", []),
        results.get("metadatas", []),
        strict=False,
    ):
        if not metadata:
            continue
        if normalise_case_id(metadata.get("case_id")) is not None:
            continue

        updated_metadata = dict(metadata)
        updated_metadata["case_id"] = cleaned_case_id
        chunk_ids.append(chunk_id)
        metadatas.append(updated_metadata)

    return LegacyAssignmentPlan(
        filename=cleaned_filename,
        case_id=cleaned_case_id,
        chunk_ids=tuple(chunk_ids),
        metadatas=tuple(metadatas),
    )


def apply_legacy_assignment(collection: Any, plan: LegacyAssignmentPlan) -> int:
    """Apply a previously reviewed assignment plan without re-embedding.

    Chroma's metadata-only ``update`` is used, so stored documents and vector
    embeddings are retained unchanged.
    """

    if plan.chunk_count == 0:
        return 0

    collection.update(
        ids=list(plan.chunk_ids),
        metadatas=[dict(metadata) for metadata in plan.metadatas],
    )
    return plan.chunk_count


def assign_legacy_document(
    collection: Any,
    *,
    filename: str,
    case_id: str,
) -> int:
    """Build and apply an assignment plan for one legacy filename."""

    plan = build_legacy_assignment_plan(
        collection,
        filename=filename,
        case_id=case_id,
    )
    return apply_legacy_assignment(collection, plan)
