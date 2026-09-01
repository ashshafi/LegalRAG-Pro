import logging

import streamlit as st

from authentication import require_private_access

from report_projection_provider import (
    ReportProjectionProviderError,
    load_active_case_report_projection,
)
from ui.cases import show_case_selector
from ui.chat import show_chat
from ui.document_details import show_document_details
from ui.document_register import show_document_register
from ui.evidence_inspection import (
    show_evidence_inspection,
    synchronise_evidence_inspection_session_state,
)
from ui.document_upload import show_document_upload
from ui.header import show_header
from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from legal_issue_dashboard import LegalIssueDashboardError, build_legal_issue_dashboard
from ui.legal_issue_dashboard import show_legal_issue_dashboard
from ui.matter_analysis_ledger import show_matter_analysis_ledger
from ui.professional_review_inbox import show_professional_review_inbox
from ui.matter_overview import (
    is_matter_overview_active,
    show_matter_overview,
    synchronise_matter_overview_session_state,
)
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

require_private_access()

from finance_case_binding.provider import load_active_finance_case_binding
from ui.finance_workspace_entrypoint import show_finance_workspace
from ui.finance_binding_manager import show_finance_binding_manager
from ui.finance_binding_lifecycle_manager import show_finance_binding_lifecycle_manager

show_header()

active_case = show_case_selector()
active_case_id = active_case.case_id if active_case is not None else None

synchronise_evidence_inspection_session_state(active_case_id)
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
synchronise_matter_overview_session_state(
    active_case_id,
    session_state=st.session_state,
)
reports_available = (
    active_case_id is not None
    and report_projection is not None
    and report_provider_error is None
)

selected_documents, timeline_clicked = show_sidebar(
    active_case_id=active_case_id,
    reports_available=reports_available,
)
show_document_upload(active_case_id)
show_document_details(active_case_id)
show_document_register(active_case_id)
if active_case_id is not None and not reports_available:
    if report_provider_error is not None:
        st.sidebar.caption(
            "The stored report projection could not be validated."
        )
    else:
        st.sidebar.caption(
            "No frozen report projection is available for the active matter."
        )
if active_case is not None:
    case_reference = (
        f" · {active_case.case_number}"
        if active_case.case_number
        else ""
    )
    if st.session_state.get("m55_main_view", "assistant") != "finance":
        st.caption(
            f"Active matter: {active_case.name}{case_reference} "
            f"· Status: {active_case.status.title()}"
        )
else:
    st.info(
        "Create a matter in the sidebar to use matter-scoped document retrieval."
    )
if st.session_state.get("u8_evidence_inspection_view", False):
    show_evidence_inspection(active_case_id)
elif st.session_state.get("ppr3_legal_issue_dashboard_view", False):
    show_legal_issue_dashboard(active_case_id)
    show_professional_review_inbox(active_case_id)
    show_matter_analysis_ledger(active_case_id)
elif st.session_state.get("m7_source_evidence_view", False):
    show_source_evidence(active_case_id, report_projection)
elif st.session_state.get("m6_workspace_view") in {
    "review", "traceability", "evidence", "chronology", "people", "comparison"
}:
    evidential_dashboard = None
    if active_case_id is not None:
        try:
            governed_authority = load_active_governed_analytical_authority(active_case_id)
            if governed_authority is not None:
                evidential_dashboard = build_legal_issue_dashboard(
                    active_case_id=active_case_id,
                    authority=governed_authority,
                )
        except (GovernedAnalyticalAuthorityProviderError, LegalIssueDashboardError) as exc:
            LOGGER.error(
                "Unable to bind governed evidential-position projection for case %s error %s.",
                active_case_id,
                type(exc).__name__,
            )
    show_workspace(
        active_case_id,
        report_projection,
        evidential_dashboard=evidential_dashboard,
    )
elif st.session_state.get("m55_main_view", "assistant") == "finance":
    if active_case_id is None:
        st.info("Select an active matter to use Finance.")
    else:
        finance_binding = load_active_finance_case_binding(active_case_id)
        if finance_binding is None:
            st.info("No active Finance workspace is bound to this matter.")
            show_finance_binding_manager(case_id=active_case_id)
        else:
            show_finance_workspace(workspace_id=finance_binding.workspace_id)
            with st.expander("Workspace history and administration", expanded=False):
                show_finance_binding_lifecycle_manager(
                    case_id=active_case_id,
                    current_workspace_id=finance_binding.workspace_id,
                )
elif st.session_state.get("m55_main_view", "assistant") == "reports":
    show_report_viewer(
        active_case_id,
        report_projection,
        provider_error=report_provider_error,
    )
elif is_matter_overview_active(st.session_state):
    show_matter_overview(
        active_case,
        report_projection,
        provider_error=report_provider_error,
        selected_document_count=len(selected_documents),
    )
else:
    show_chat(
        selected_documents,
        timeline_clicked,
        active_case_id=active_case_id,
    )
