import streamlit as st

from ui.cases import show_case_selector
from ui.chat import show_chat
from ui.header import show_header
from ui.sidebar import show_sidebar

st.set_page_config(
    page_title="LegalRAG Pro",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

show_header()

active_case = show_case_selector()
active_case_id = active_case.case_id if active_case is not None else None

selected_documents, timeline_clicked = show_sidebar(
    active_case_id=active_case_id,
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

show_chat(
    selected_documents,
    timeline_clicked,
    active_case_id=active_case_id,
)
