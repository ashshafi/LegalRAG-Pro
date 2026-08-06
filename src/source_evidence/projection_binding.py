"""Deterministic binding of durable report citations to immutable source evidence.

M6 is a post-projection traceability layer.  It classifies only the canonical
citation inventory of an already validated ``CaseReportProjection`` and emits a
sibling immutable ``ProjectionEvidenceBindingManifest``.  It does not mutate
reporting state, consult Chroma, re-run retrieval/analysis, migrate historical
evidence, or weaken the frozen M5 singleton-receipt contract.
"""

from __future__ import annotations

from dataclasses import replace

from case_reporting.models import CaseReportProjection
from case_reporting.validation import validate_case_report_projection

from .identity import derive_sha256_id
from .models import (
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    BindingClass,
    EvidenceBinding,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
)
from .serialization import projection_evidence_binding_manifest_identity_payload_to_dict
from .store import SourceEvidenceStore
from .validation import (
    validate_evidence_binding,
    validate_projection_evidence_binding_manifest,
)
from .verified_retrieval import build_singleton_analysis_receipt


class ProjectionEvidenceBindingError(RuntimeError):
    """Raised when a final projection cannot be bound to source evidence exactly."""


def _require_citation_compatibility(
    *,
    citation: object,
    binding: EvidenceBinding,
    case_id: str,
) -> None:
    """Require one concrete binding to describe the exact projected citation."""

    if binding.case_id != case_id:
        raise ValueError("EvidenceBinding.case_id does not match the projection case.")
    if binding.evidence_key != citation.evidence_key:
        raise ValueError("EvidenceBinding.evidence_key does not match the projected citation.")
    if binding.document_name != citation.document_name:
        raise ValueError("EvidenceBinding.document_name does not match the projected citation.")
    if binding.document_id is not None and binding.document_id != citation.document_id:
        raise ValueError("EvidenceBinding.document_id does not match the projected citation.")
    if binding.page is not None and binding.page != citation.page:
        raise ValueError("EvidenceBinding.page does not match the projected citation.")
    if binding.chunk_id is not None and binding.chunk_id != citation.chunk_id:
        raise ValueError("EvidenceBinding.chunk_id does not match the projected citation.")

    if binding.binding_class is BindingClass.FULL_CHAIN_BOUND:
        if citation.chunk_id != citation.evidence_key:
            raise ValueError("FULL_CHAIN projected citations require chunk_id == evidence_key.")
        if binding.page is None or citation.page != binding.page:
            raise ValueError("FULL_CHAIN projected citations require the exact bound page.")
        if citation.document_name != binding.document_name:
            raise ValueError("FULL_CHAIN projected citations require the exact bound document name.")


def _entry_for_citation(
    *,
    citation: object,
    case_id: str,
    store: SourceEvidenceStore,
) -> ProjectionBindingEntry:
    """Build one truthful projection-binding entry from immutable stored state."""

    binding = store.load_evidence_binding(case_id, citation.evidence_key)
    if binding is None:
        return ProjectionBindingEntry(
            citation_id=citation.citation_id,
            evidence_key=citation.evidence_key,
            binding_class=BindingClass.UNBOUND,
            evidence_binding_id=None,
            source_bound_analysis_receipt_id=None,
        )

    validate_evidence_binding(binding)
    _require_citation_compatibility(citation=citation, binding=binding, case_id=case_id)

    if binding.binding_class is BindingClass.FULL_CHAIN_BOUND:
        if binding.chunk_text_sha256 is None:
            raise ValueError("FULL_CHAIN EvidenceBinding is missing chunk_text_sha256.")
        expected_receipt = build_singleton_analysis_receipt(
            case_id=case_id,
            evidence_key=citation.evidence_key,
            evidence_binding_id=binding.evidence_binding_id,
            chunk_text_sha256=binding.chunk_text_sha256,
        )
        stored_receipt = store.load_analysis_receipt(
            case_id,
            expected_receipt.source_bound_analysis_receipt_id,
        )
        if stored_receipt != expected_receipt:
            raise ValueError(
                "Stored analysis receipt does not equal the deterministic M5 singleton receipt."
            )
        receipt_id: str | None = expected_receipt.source_bound_analysis_receipt_id
    elif binding.binding_class in (
        BindingClass.ANALYTICAL_TEXT_BOUND,
        BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
    ):
        receipt_id = None
    else:
        raise ValueError("EvidenceBinding uses an unsupported projection-binding class.")

    return ProjectionBindingEntry(
        citation_id=citation.citation_id,
        evidence_key=citation.evidence_key,
        binding_class=binding.binding_class,
        evidence_binding_id=binding.evidence_binding_id,
        source_bound_analysis_receipt_id=receipt_id,
    )


def _coverage(entries: tuple[ProjectionBindingEntry, ...]) -> ProjectionBindingCoverage:
    if not entries or all(entry.binding_class is BindingClass.UNBOUND for entry in entries):
        return ProjectionBindingCoverage.UNBOUND
    if all(entry.binding_class is BindingClass.FULL_CHAIN_BOUND for entry in entries):
        return ProjectionBindingCoverage.FULLY_SOURCE_BOUND
    return ProjectionBindingCoverage.MIXED_BINDING


def build_projection_evidence_binding_manifest(
    projection: CaseReportProjection,
    *,
    store: SourceEvidenceStore | None = None,
) -> ProjectionEvidenceBindingManifest:
    """Build, but do not publish, the canonical binding for one final projection.

    ``projection.citations`` is the durable analytical evidence inventory.  M6
    never promotes unrelated M5 receipts merely because they exist.  A
    FULL_CHAIN projection entry requires both the exact immutable
    ``EvidenceBinding`` and the exact deterministic M5 singleton receipt.
    """

    try:
        validate_case_report_projection(projection)
        target_store = store if store is not None else SourceEvidenceStore()
        case_id = projection.case_header.case_id

        entries = tuple(
            _entry_for_citation(
                citation=citation,
                case_id=case_id,
                store=target_store,
            )
            for citation in projection.citations
        )

        provisional = ProjectionEvidenceBindingManifest(
            schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=case_id,
            report_projection_id=projection.report_projection_id,
            projection_payload_sha256=projection.projection_payload_sha256,
            manifest_id=projection.manifest.manifest_id,
            coverage=_coverage(entries),
            entries=entries,
            projection_evidence_binding_manifest_id="sha256:" + ("0" * 64),
        )
        manifest = replace(
            provisional,
            projection_evidence_binding_manifest_id=derive_sha256_id(
                projection_evidence_binding_manifest_identity_payload_to_dict(provisional)
            ),
        )
        validate_projection_evidence_binding_manifest(manifest)
        return manifest
    except ProjectionEvidenceBindingError:
        raise
    except Exception as exc:
        raise ProjectionEvidenceBindingError(
            "Unable to build the canonical projection evidence-binding manifest."
        ) from exc


def publish_projection_evidence_binding(
    projection: CaseReportProjection,
    *,
    store: SourceEvidenceStore | None = None,
) -> ProjectionEvidenceBindingManifest:
    """Build and immutably publish the exact binding for one final projection."""

    target_store = store if store is not None else SourceEvidenceStore()
    try:
        manifest = build_projection_evidence_binding_manifest(
            projection,
            store=target_store,
        )
        target_store.publish_projection_binding(manifest)
        return manifest
    except ProjectionEvidenceBindingError:
        raise
    except Exception as exc:
        raise ProjectionEvidenceBindingError(
            "Unable to publish the canonical projection evidence-binding manifest."
        ) from exc


__all__ = [
    "ProjectionEvidenceBindingError",
    "build_projection_evidence_binding_manifest",
    "publish_projection_evidence_binding",
]
