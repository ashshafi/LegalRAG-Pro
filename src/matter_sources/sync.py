"""Read-only external-matter sync planning and governed PDF handoff."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Callable, Mapping

from matter_sources.base import MatterSourceConnector, MatterSourceError
from matter_sources.models import DocumentObservation, ExternalDocument, SyncDisposition, SyncPlan, SyncPlanEntry, observe_bytes


class MatterSourceSyncError(RuntimeError):
    """Raised when a sync plan or governed handoff cannot safely complete."""


@dataclass(frozen=True, slots=True)
class AppliedDocument:
    source_document_id: str
    captured_filename: str
    content_sha256: str
    upload_result: object


UploadService = Callable[..., object]


def build_sync_plan(connector: MatterSourceConnector, *, source_matter_id: str,
                    previous: Mapping[str, DocumentObservation] | None = None) -> SyncPlan:
    """Read the provider completely and return a mutation-free content-based plan."""
    prior = dict(previous or {})
    documents = connector.list_documents(source_matter_id)
    seen: set[str] = set()
    entries: list[SyncPlanEntry] = []

    for document in documents:
        if document.source_matter_id != source_matter_id:
            raise MatterSourceSyncError("Provider returned a document bound to a different matter.")
        if document.source_document_id in seen:
            raise MatterSourceSyncError("Provider returned duplicate document identity.")
        seen.add(document.source_document_id)

        try:
            content = connector.fetch_document_bytes(document.source_document_id)
        except MatterSourceError:
            raise
        except Exception as exc:
            raise MatterSourceSyncError("Provider document read failed.") from exc

        current = observe_bytes(
            source_document_id=document.source_document_id,
            source_version_id=document.source_version_id,
            content=content,
        )
        previous_item = prior.get(document.source_document_id)
        if previous_item is None:
            disposition = SyncDisposition.NEW
        elif previous_item.content_sha256 == current.content_sha256:
            disposition = SyncDisposition.UNCHANGED
        else:
            disposition = SyncDisposition.CHANGED

        entries.append(SyncPlanEntry(
            source_document_id=document.source_document_id,
            disposition=disposition,
            document=document,
            current=current,
            previous=previous_item,
        ))

    for source_document_id in sorted(set(prior) - seen):
        entries.append(SyncPlanEntry(
            source_document_id=source_document_id,
            disposition=SyncDisposition.UNAVAILABLE,
            document=None,
            current=None,
            previous=prior[source_document_id],
        ))

    return SyncPlan(provider=connector.provider_identity(), source_matter_id=source_matter_id, entries=tuple(entries))


def observations_after_plan(plan: SyncPlan) -> dict[str, DocumentObservation]:
    return {entry.source_document_id: entry.current for entry in plan.entries if entry.current is not None}


def _safe_external_filename(document: ExternalDocument, digest: str) -> str:
    original = Path(document.display_name).name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(original).stem).strip(" ._") or "document"
    source_key = sha256(document.source_document_id.encode("utf-8")).hexdigest()[:12]
    return f"LEAP-{source_key}-{digest[:12]}-{stem}.pdf"


def _is_pdf(document: ExternalDocument, content: bytes) -> bool:
    media = document.media_type.split(";", 1)[0].strip().lower()
    return media == "application/pdf" and bool(content) and b"%PDF-" in content[:1024]


def apply_pdf_sync_plan(connector: MatterSourceConnector, *, plan: SyncPlan, case_id: str,
                        access: object, docs_folder: str | Path,
                        upload_service: UploadService | None = None) -> tuple[AppliedDocument, ...]:
    """Hand NEW/CHANGED PDFs to LegalRAG's existing governed upload service.

    Provider bytes are fully preflighted before the first LegalRAG mutation.
    Successfully published immutable evidence is never rolled back or overwritten.
    """
    from case_management.access import require_matter_mutation

    require_matter_mutation(access)
    if getattr(access, "case_id", None) != case_id:
        raise MatterSourceSyncError("Matter access does not match sync case_id.")
    if connector.provider_identity() != plan.provider:
        raise MatterSourceSyncError("Connector identity does not match the sync plan.")

    targets = tuple(entry for entry in plan.entries
                    if entry.disposition in {SyncDisposition.NEW, SyncDisposition.CHANGED})

    prefetched: list[tuple[SyncPlanEntry, bytes]] = []
    for entry in targets:
        if entry.document is None or entry.current is None:
            raise MatterSourceSyncError("Sync plan target is incomplete.")
        content = connector.fetch_document_bytes(entry.source_document_id)
        observed = observe_bytes(
            source_document_id=entry.source_document_id,
            source_version_id=entry.document.source_version_id,
            content=content,
        )
        if observed.content_sha256 != entry.current.content_sha256:
            raise MatterSourceSyncError("External document changed after planning; rebuild the sync plan.")
        if not _is_pdf(entry.document, content):
            raise MatterSourceSyncError("LEAP1 governed handoff currently supports PDF source documents only.")
        prefetched.append((entry, content))

    if upload_service is None:
        from document_upload import upload_case_pdf
        upload_service = upload_case_pdf

    applied: list[AppliedDocument] = []
    for entry, content in prefetched:
        assert entry.document is not None and entry.current is not None
        filename = _safe_external_filename(entry.document, entry.current.content_sha256)
        result = upload_service(
            filename=filename,
            content=content,
            case_id=case_id,
            access=access,
            docs_folder=docs_folder,
        )
        applied.append(AppliedDocument(
            source_document_id=entry.source_document_id,
            captured_filename=filename,
            content_sha256=entry.current.content_sha256,
            upload_result=result,
        ))

    return tuple(applied)
