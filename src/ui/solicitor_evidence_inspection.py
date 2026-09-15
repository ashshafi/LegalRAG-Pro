"""R6 presentation facade for document-complete evidence inspection."""
from __future__ import annotations

from typing import Any

import streamlit as st
import ui.evidence_inspection as base

from ui.solicitor_shell import DOCUMENTS_VIEW_KEY, INSPECTION_ORIGIN_KEY

_VIEW_KEY = "u8_evidence_inspection_view"
_DOCUMENT_KEY = "u8_evidence_inspection_document_id"


def _close_to_origin() -> None:
    st.session_state[_VIEW_KEY] = False
    origin = st.session_state.pop(INSPECTION_ORIGIN_KEY, None)
    if origin == "Documents":
        st.session_state[DOCUMENTS_VIEW_KEY] = True
        st.session_state["m55_main_view"] = "assistant"
        st.session_state["m6_workspace_view"] = None
        st.session_state["m7_source_evidence_view"] = False


def show_solicitor_evidence_inspection(
    active_case_id: str | None,
    *,
    search_service: Any = None,
) -> None:
    """Render the immutable evidence inspection with origin-aware Back navigation."""
    st.title("🔬 Document Evidence Inspection")
    if active_case_id is None or not str(active_case_id).strip():
        st.info("Select a matter before inspecting governed document evidence.")
        return
    selected_document_id = st.session_state.get(_DOCUMENT_KEY)
    if not isinstance(selected_document_id, str) or not selected_document_id.strip():
        st.info("No governed document is selected for evidence inspection.")
        return

    st.button(
        "← Back",
        key=f"ux_r6_evidence_inspection_back::{active_case_id}",
        on_click=_close_to_origin,
    )

    service = search_service or base.search_case_evidence
    try:
        result = service(
            case_id=active_case_id,
            query="",
            mode=base.EvidenceSearchMode.DOCUMENT_COMPLETE,
            candidate_document_ids=(selected_document_id,),
            text_match_mode=base.EvidenceTextMatchMode.ALL_EVIDENCE,
        )
        base._validate_result(
            active_case_id=active_case_id,
            source_document_instance_id=selected_document_id,
            result=result,
        )
    except base.EvidenceSearchError as exc:
        base.LOGGER.warning(
            "R6 evidence inspection failed for case %s document %s error %s.",
            active_case_id,
            selected_document_id,
            type(exc).__name__,
        )
        st.error(base._FAILURE_TEXT)
        return

    base._show_document_summary(result)
    base._show_pages(result)


__all__ = ["show_solicitor_evidence_inspection", "_close_to_origin"]
