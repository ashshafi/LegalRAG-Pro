"""Read-only U8 document-complete evidence inspection UI."""

from __future__ import annotations

import logging
from collections.abc import Callable

import streamlit as st

from evidence_roles import EvidenceRole
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    EvidenceTextMatchMode,
    NegativeFindingScope,
    search_case_evidence,
)


LOGGER = logging.getLogger(__name__)

_CASE_KEY = "u8_evidence_inspection_case_id"
_VIEW_KEY = "u8_evidence_inspection_view"
_DOCUMENT_KEY = "u8_evidence_inspection_document_id"

_FAILURE_TEXT = (
    "Document-complete evidence could not be verified. "
    "No evidence text has been displayed."
)
_MISSING_SELECTION_TEXT = (
    "No governed document is selected for evidence inspection."
)

SearchService = Callable[..., CaseEvidenceSearchResult]


def synchronise_evidence_inspection_session_state(
    active_case_id: str | None,
) -> bool:
    """Reset only U8E navigation when the active case identity changes."""

    if st.session_state.get(_CASE_KEY) == active_case_id:
        return False
    st.session_state[_CASE_KEY] = active_case_id
    st.session_state[_VIEW_KEY] = False
    st.session_state.pop(_DOCUMENT_KEY, None)
    return True


def _close_evidence_inspection() -> None:
    """Close the U8 inspection route without touching other feature state."""

    st.session_state[_VIEW_KEY] = False


def _role_count(result: CaseEvidenceSearchResult, role: EvidenceRole) -> int:
    document = result.documents[0]
    return next(item.count for item in document.role_counts if item.role is role)


def _validate_result(
    *,
    active_case_id: str,
    source_document_instance_id: str,
    result: CaseEvidenceSearchResult,
) -> None:
    """Fail closed if the service result does not prove the requested document."""

    if result.case_id != active_case_id:
        raise EvidenceSearchError("Evidence inspection returned the wrong case.")
    if result.search_mode is not EvidenceSearchMode.DOCUMENT_COMPLETE:
        raise EvidenceSearchError("Evidence inspection returned the wrong search mode.")
    if len(result.documents) != 1:
        raise EvidenceSearchError("Evidence inspection did not return exactly one document.")

    document = result.documents[0]
    if document.document.source_document_instance_id != source_document_instance_id:
        raise EvidenceSearchError("Evidence inspection returned the wrong document.")

    receipt = result.receipt
    if receipt.completion is not EvidenceSearchCompletion.COMPLETE:
        raise EvidenceSearchError("Evidence inspection is not complete.")
    if receipt.scope_document_count != 1 or receipt.documents_completely_expanded != 1:
        raise EvidenceSearchError("Evidence inspection did not completely expand one document.")
    if receipt.searched_document_ids != (source_document_instance_id,):
        raise EvidenceSearchError("Evidence inspection receipt identifies the wrong document.")
    if receipt.pages_inspected != document.document.page_count:
        raise EvidenceSearchError("Evidence inspection did not inspect every governed page.")
    if receipt.chunks_inspected != document.document.evidence_chunk_count:
        raise EvidenceSearchError("Evidence inspection did not inspect every governed chunk.")
    if not receipt.negative_finding_permitted:
        raise EvidenceSearchError("Complete document inspection did not permit scoped findings.")
    if receipt.negative_finding_scope not in {
        NegativeFindingScope.SEARCHED_SCOPE,
        NegativeFindingScope.CASE_CORPUS,
    }:
        raise EvidenceSearchError("Evidence inspection receipt has an invalid finding scope.")


def _show_document_summary(result: CaseEvidenceSearchResult) -> None:
    document = result.documents[0]
    value = document.document

    st.subheader("Document")
    st.text(f"Filename: {value.original_filename}")
    st.text(f"Source document ID: {value.source_document_instance_id}")
    st.text(f"Source snapshot ID: {value.source_snapshot_id}")
    st.text(f"Original SHA-256: {value.original_blob_sha256}")
    st.text(f"Original size: {value.original_byte_length:,} bytes")
    st.text(f"Pages: {value.page_count}")
    st.text(f"Evidence chunks: {value.evidence_chunk_count}")
    st.text(f"Extraction profile: {value.extraction_profile_id}")
    st.text(f"Chunking profile: {value.chunking_profile_id}")
    st.text("Source-bound status: FULL_CHAIN_BOUND (all governed chunks)")

    st.subheader("Evidence roles")
    st.text(f"Primary source: {_role_count(result, EvidenceRole.PRIMARY_SOURCE)}")
    st.text(f"Commentary: {_role_count(result, EvidenceRole.COMMENTARY)}")
    st.text(f"Cross-reference: {_role_count(result, EvidenceRole.CROSS_REFERENCE)}")
    st.text(f"Cover / index: {_role_count(result, EvidenceRole.COVER_OR_INDEX)}")
    st.text(f"Mixed: {_role_count(result, EvidenceRole.MIXED)}")
    st.text(f"Unclassified: {_role_count(result, EvidenceRole.UNCLASSIFIED)}")

    st.info(
        "People and dates are not asserted as governed structured metadata in this view. "
        "U8 displays only source-bound facts and deterministic evidence-role decisions."
    )


def _show_receipt(result: CaseEvidenceSearchResult) -> None:
    receipt = result.receipt
    with st.expander("Search coverage receipt", expanded=False):
        st.text(f"Search mode: {receipt.search_mode.value}")
        st.text(f"Completion: {receipt.completion.value}")
        st.text(
            "Documents completely expanded: "
            f"{receipt.documents_completely_expanded}/{receipt.scope_document_count}"
        )
        st.text(f"Pages inspected: {receipt.pages_inspected}/{receipt.scope_page_count}")
        st.text(f"Chunks inspected: {receipt.chunks_inspected}/{receipt.scope_chunk_count}")
        st.text(f"Whole case corpus complete: {'yes' if receipt.case_corpus_complete else 'no'}")
        st.text(f"Negative-finding scope: {receipt.negative_finding_scope.value}")
        st.text(
            "Scoped negative finding permitted: "
            f"{'yes' if receipt.negative_finding_permitted else 'no'}"
        )
        st.text(f"Query SHA-256: {receipt.query_sha256}")


def _show_pages(result: CaseEvidenceSearchResult) -> None:
    document = result.documents[0]

    st.subheader("Pages and governed chunks")
    for page in document.pages:
        page_value = page.page
        st.text(
            f"Page {page_value.page_number} · "
            f"{page_value.extraction_method.value} · "
            f"{len(page.chunks)} governed chunks"
        )
        st.text(f"Page-text SHA-256: {page_value.page_text_sha256}")

        with st.expander(
            f"Page {page_value.page_number} — immutable extracted text",
            expanded=False,
        ):
            st.code(page_value.text, language=None)

        for item in page.chunks:
            chunk = item.chunk
            classification = item.classification
            label = (
                f"Page {chunk.page_number} · chunk {chunk.chunk_ordinal} · "
                f"{classification.role.value} · {chunk.evidence_key[:12]}"
            )
            with st.expander(label, expanded=False):
                st.text(f"Evidence role: {classification.role.value}")
                st.text(f"Role rule: {classification.rule_id}")
                st.text(f"Role basis: {classification.basis}")
                st.text(f"Source type: {classification.source_type.value}")
                st.text(f"Source label: {classification.source_label}")
                st.text(f"Provenance method: {classification.provenance_method}")
                st.text(f"Primary tier: {classification.primary_tier}")
                st.text(f"Primary label: {classification.primary_label}")
                st.text(f"Binding class: {chunk.binding_class.value}")
                st.text(f"Evidence key: {chunk.evidence_key}")
                st.text(f"Evidence binding ID: {chunk.evidence_binding_id}")
                st.text(f"Chunk ID: {chunk.chunk_id}")
                st.text(f"Chunk-text SHA-256: {chunk.chunk_text_sha256}")
                st.text(f"Chunk byte length: {chunk.chunk_text_byte_length:,}")
                st.code(chunk.text, language=None)


def show_evidence_inspection(
    active_case_id: str | None,
    *,
    search_service: SearchService = search_case_evidence,
) -> None:
    """Render complete immutable evidence for the U7-selected governed document."""

    st.title("🔬 Document Evidence Inspection")

    if active_case_id is None or not active_case_id.strip():
        st.info("Select a case before inspecting governed document evidence.")
        return

    selected_document_id = st.session_state.get(_DOCUMENT_KEY)
    if not isinstance(selected_document_id, str) or not selected_document_id.strip():
        st.info(_MISSING_SELECTION_TEXT)
        return

    st.button(
        "← Back",
        key=f"u8_evidence_inspection_back::{active_case_id}",
        on_click=_close_evidence_inspection,
    )

    try:
        result = search_service(
            case_id=active_case_id,
            query="",
            mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
            candidate_document_ids=(selected_document_id,),
            text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
        )
        _validate_result(
            active_case_id=active_case_id,
            source_document_instance_id=selected_document_id,
            result=result,
        )
    except EvidenceSearchError as exc:
        LOGGER.warning(
            "U8 evidence inspection failed for case %s document %s error %s.",
            active_case_id,
            selected_document_id,
            type(exc).__name__,
        )
        st.error(_FAILURE_TEXT)
        return

    _show_document_summary(result)
    _show_receipt(result)
    _show_pages(result)


__all__ = [
    "show_evidence_inspection",
    "synchronise_evidence_inspection_session_state",
]
