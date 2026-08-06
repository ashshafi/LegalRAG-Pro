"""Projection-bound read-only source-evidence viewer."""

from __future__ import annotations

import logging

import streamlit as st

from case_reporting.models import CaseReportProjection, CitationRecord
from case_reporting.validation import validate_case_report_projection
from source_evidence.models import BindingClass
from source_evidence.resolver import (
    ResolvedSourceEvidence,
    SourceEvidenceResolverError,
    resolve_projection_citation_source,
)

LOGGER = logging.getLogger(__name__)

_IDENTITY_KEY = "m7_source_evidence_identity"
_VIEW_KEY = "m7_source_evidence_view"
_CITATION_KEY = "m7_source_evidence_citation_id"


def _projection_identity(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> tuple[str, str, str, str] | None:
    if active_case_id is None or projection is None:
        return None
    return (
        active_case_id,
        projection.report_projection_id,
        projection.projection_payload_sha256,
        projection.manifest.manifest_id,
    )


def synchronise_source_evidence_session_state(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> bool:
    """Reset only M7 navigation when the frozen case/projection identity changes."""

    identity = _projection_identity(active_case_id, projection)
    if st.session_state.get(_IDENTITY_KEY) == identity:
        return False
    st.session_state[_IDENTITY_KEY] = identity
    st.session_state[_VIEW_KEY] = False
    st.session_state.pop(_CITATION_KEY, None)
    return True


def _citation_label(citation: CitationRecord) -> str:
    page = f" · p.{citation.page}" if citation.page is not None else ""
    return f"{citation.document_name}{page} · {citation.citation_id}"


def _show_common_fields(value: ResolvedSourceEvidence) -> None:
    st.text(f"Source binding class: {value.binding_class.value}")
    st.text(f"Projection binding coverage: {value.projection_binding_coverage.value}")
    st.text(
        "Projection binding manifest ID: "
        f"{value.projection_evidence_binding_manifest_id}"
    )
    st.text(f"Evidence key: {value.evidence_key}")
    st.text(f"Document: {value.document_name}")
    if value.document_id is not None:
        st.text(f"Document ID: {value.document_id}")
    if value.page is not None:
        st.text(f"Page: {value.page}")
    if value.chunk_id is not None:
        st.text(f"Chunk ID: {value.chunk_id}")


def _show_full_chain(value: ResolvedSourceEvidence) -> None:
    if value.source_document_instance_id is not None:
        st.text(f"Source document instance ID: {value.source_document_instance_id}")
    if value.source_snapshot_id is not None:
        st.text(f"Source snapshot ID: {value.source_snapshot_id}")
    if value.chunk_ordinal is not None:
        st.text(f"Chunk ordinal: {value.chunk_ordinal}")
    if value.original_blob_sha256 is not None:
        st.text(f"Original SHA-256: {value.original_blob_sha256}")
    if value.page_text_sha256 is not None:
        st.text(f"Page-text SHA-256: {value.page_text_sha256}")
    if value.chunk_text_sha256 is not None:
        st.text(f"Chunk-text SHA-256: {value.chunk_text_sha256}")
    if value.extraction_profile_id is not None:
        st.text(f"Extraction profile: {value.extraction_profile_id}")
    if value.chunking_profile_id is not None:
        st.text(f"Chunking profile: {value.chunking_profile_id}")
    if value.extraction_method is not None:
        st.text(f"Extraction method: {value.extraction_method.value}")
    if value.source_bound_analysis_receipt_id is not None:
        st.text(
            "Verified mapper-admission receipt: "
            f"{value.source_bound_analysis_receipt_id}"
        )

    st.subheader("Immutable chunk text")
    st.code(value.exact_bound_text or "", language=None)
    st.subheader("Immutable extracted page text")
    st.code(value.exact_page_text or "", language=None)

    if value.original_pdf_bytes is not None and value.original_filename is not None:
        st.download_button(
            "⬇️ Download immutable original PDF",
            data=value.original_pdf_bytes,
            file_name=value.original_filename,
            mime="application/pdf",
            key=f"m7_original_pdf_{value.citation_id}",
        )


def _show_weaker(value: ResolvedSourceEvidence) -> None:
    if value.bound_text_sha256 is not None:
        st.text(f"Bound-text SHA-256: {value.bound_text_sha256}")
    if value.binding_class is BindingClass.ANALYTICAL_TEXT_BOUND:
        st.info("Original/page/chunk source lineage is not proven for this item.")
        st.subheader("Exact retained analytical text")
    else:
        st.info(
            "This is a preserved current-index text snapshot. "
            "It is not proof of the historical analytical text."
        )
        st.subheader("Exact preserved current-index text")
    st.code(value.exact_bound_text or "", language=None)


def show_source_evidence(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> None:
    """Render deterministic source drill-down for the selected frozen projection."""

    st.title("🔎 Source Evidence")
    if active_case_id is None:
        st.info("Select a case to inspect projection-bound source evidence.")
        return
    if projection is None:
        st.info("No validated frozen report projection is available for the active case.")
        return
    try:
        validate_case_report_projection(projection)
    except (ValueError, TypeError):
        st.error("The frozen report projection could not be validated.")
        return

    citation_by_id = {item.citation_id: item for item in projection.citations}
    citation_ids = tuple(projection.manifest.ordered_citation_ids)
    if not citation_ids:
        st.info("This frozen projection contains no evidence citations.")
        return
    if tuple(citation_by_id) != citation_ids:
        st.error("The frozen projection citation inventory could not be validated.")
        return

    current = st.session_state.get(_CITATION_KEY)
    if current not in citation_by_id:
        current = citation_ids[0]
    selected = st.selectbox(
        "Projection citation",
        options=citation_ids,
        index=citation_ids.index(current),
        format_func=lambda item: _citation_label(citation_by_id[item]),
        key=_CITATION_KEY,
    )

    try:
        resolved = resolve_projection_citation_source(
            projection,
            case_id=active_case_id,
            citation_id=selected,
        )
    except SourceEvidenceResolverError as exc:
        LOGGER.warning(
            "Source evidence resolution failed for case %s citation %s error %s.",
            active_case_id,
            selected,
            type(exc).__name__,
        )
        st.error("Source evidence could not be verified. No source text has been displayed.")
        return

    if resolved is None:
        st.info(
            "No projection evidence-binding manifest is available for this frozen projection. "
            "The report remains valid, but immutable source drill-down is unavailable."
        )
        return

    _show_common_fields(resolved)
    if resolved.binding_class is BindingClass.UNBOUND:
        st.info("Exact source text is unavailable for this projected evidence.")
        return
    if resolved.binding_class is BindingClass.FULL_CHAIN_BOUND:
        _show_full_chain(resolved)
        return
    _show_weaker(resolved)


__all__ = [
    "show_source_evidence",
    "synchronise_source_evidence_session_state",
]
