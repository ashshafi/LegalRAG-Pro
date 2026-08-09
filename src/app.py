import logging

import streamlit as st

from report_projection_provider import (
    ReportProjectionProviderError,
    load_active_case_report_projection,
)
from ui.cases import show_case_selector
from ui.chat import show_chat
from ui.document_details import show_document_details
from ui.document_register import show_document_register
from ui.document_upload import show_document_upload
from ui.header import show_header
from ui.reports import show_report_viewer, synchronise_report_session_state
from ui.sidebar import show_sidebar
from ui.source_evidence import (
    show_source_evidence,
    synchronise_source_evidence_session_state,
)
from ui.workspace import show_workspace, synchronise_workspace_session_state


LOGGER = logging.getLogger(__name__)
st.set_page_config(
    page_title="LegalRAG Pro",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

show_header()

active_case = show_case_selector()
active_case_id = active_case.case_id if active_case is not None else None

show_document_upload(active_case_id)
show_document_details(active_case_id)
show_document_register(active_case_id)
report_projection = None
report_provider_error: ReportProjectionProviderError | None = None
if active_case_id is not None:
    try:
        report_projection = load_active_case_report_projection(active_case_id)
    except ReportProjectionProviderError as exc:
        report_provider_error = exc
        LOGGER.error(
            "Unable to load the active report projection for case %s error %s.",
            active_case_id,
            type(exc).__name__,
        )
synchronise_report_session_state(active_case_id, report_projection)
synchronise_workspace_session_state(active_case_id, report_projection)
synchronise_source_evidence_session_state(active_case_id, report_projection)
reports_available = (
    active_case_id is not None
    and report_projection is not None
    and report_provider_error is None
)

selected_documents, timeline_clicked = show_sidebar(
    active_case_id=active_case_id,
    reports_available=reports_available,
)
if active_case_id is not None and not reports_available:
    if report_provider_error is not None:
        st.sidebar.caption(
            "The stored report projection could not be validated."
        )
    else:
        st.sidebar.caption(
            "No frozen report projection is available for the active case."
        )
if active_case is not None:
    case_reference = (
        f" · {active_case.case_number}"
        if active_case.case_number
        else ""
    )
    st.caption(
        f"Active case: {active_case.name}{case_reference} "
        f"· Status: {active_case.status.title()}"
    )
else:
    st.info(
        "Create a case in the sidebar to use case-isolated document retrieval."
    )
if st.session_state.get("m7_source_evidence_view", False):
    show_source_evidence(active_case_id, report_projection)
elif st.session_state.get("m6_workspace_view") in {
    "traceability", "evidence", "chronology", "people", "comparison"
}:
    show_workspace(active_case_id, report_projection)
elif st.session_state.get("m55_main_view", "assistant") == "reports":
    show_report_viewer(
        active_case_id,
        report_projection,
        provider_error=report_provider_error,
    )
else:
    show_chat(
        selected_documents,
        timeline_clicked,
        active_case_id=active_case_id,
    )
