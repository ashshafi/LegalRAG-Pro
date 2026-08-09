"""Read-only case-scoped catalog of immutable source-document provenance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from source_evidence.identity import canonical_uuid
from source_evidence.models import SourceDocumentManifest
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError


class DocumentCatalogError(RuntimeError):
    """Raised when governed document provenance cannot be listed safely."""


@dataclass(frozen=True, slots=True)
class DocumentCatalogEntry:
    """Read-only presentation projection of one immutable document manifest."""

    source_document_instance_id: str
    original_filename: str
    media_type: str
    original_blob_sha256: str
    original_byte_length: int
    source_snapshot_id: str
    page_count: int
    evidence_chunk_count: int
    extraction_profile_id: str
    chunking_profile_id: str
    extraction_methods: tuple[str, ...]


def _entry_from_manifest(manifest: SourceDocumentManifest) -> DocumentCatalogEntry:
    """Project one validated manifest into inert document-detail fields."""

    methods = tuple(
        dict.fromkeys(page.extraction_method.value for page in manifest.pages)
    )
    chunk_count = sum(len(page.chunk_snapshots) for page in manifest.pages)
    return DocumentCatalogEntry(
        source_document_instance_id=manifest.source_document_instance_id,
        original_filename=manifest.original_filename,
        media_type=manifest.media_type,
        original_blob_sha256=manifest.original_blob_sha256,
        original_byte_length=manifest.original_byte_length,
        source_snapshot_id=manifest.source_snapshot_id,
        page_count=len(manifest.pages),
        evidence_chunk_count=chunk_count,
        extraction_profile_id=manifest.extraction_profile.profile_id,
        chunking_profile_id=manifest.chunking_profile.profile_id,
        extraction_methods=methods,
    )


def _assert_read_boundary(path: Path, root: Path, *, label: str) -> None:
    """Require an existing governed directory to remain below the store root."""

    if path.is_symlink():
        raise DocumentCatalogError(f"{label} must not be a symbolic link.")
    try:
        resolved = path.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise DocumentCatalogError(
            f"{label} could not be resolved inside the governed store."
        ) from exc


def list_case_documents(
    case_id: str,
    *,
    store: SourceEvidenceStore | None = None,
) -> tuple[DocumentCatalogEntry, ...]:
    """Return deterministic read-only provenance details for one exact case.

    Discovery is limited to the frozen case-document manifest namespace. Every
    discovered identity is then loaded through ``SourceEvidenceStore`` so its
    canonical bytes and manifest identity are revalidated by the frozen store.
    """

    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
        target_store = store if store is not None else SourceEvidenceStore()
        store_root = target_store.root
        documents_root = (
            store_root
            / "cases"
            / canonical_case_id
            / "documents"
        )

        if not documents_root.exists():
            return ()
        if not documents_root.is_dir():
            raise DocumentCatalogError(
                "The governed document-manifest namespace is not a directory."
            )

        _assert_read_boundary(
            documents_root,
            store_root,
            label="Document-manifest namespace",
        )

        entries: list[DocumentCatalogEntry] = []
        for child in sorted(documents_root.iterdir(), key=lambda item: item.name):
            if child.is_symlink() or not child.is_dir():
                raise DocumentCatalogError(
                    "Unexpected entry exists in the governed document namespace."
                )

            document_id = canonical_uuid(
                child.name,
                field_name="source_document_instance_id",
            )
            manifest = target_store.load_document_manifest(
                canonical_case_id,
                document_id,
            )

            if (
                manifest.case_id != canonical_case_id
                or manifest.source_document_instance_id != document_id
            ):
                raise DocumentCatalogError(
                    "Loaded document manifest does not match its requested identity."
                )

            entries.append(_entry_from_manifest(manifest))

        return tuple(
            sorted(
                entries,
                key=lambda item: (
                    item.original_filename.casefold(),
                    item.original_filename,
                    item.source_document_instance_id,
                ),
            )
        )
    except DocumentCatalogError:
        raise
    except (
        OSError,
        SourceEvidenceStoreError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise DocumentCatalogError(
            "Document provenance could not be read safely."
        ) from exc


__all__ = [
    "DocumentCatalogEntry",
    "DocumentCatalogError",
    "list_case_documents",
]
