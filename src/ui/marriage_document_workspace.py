from __future__ import annotations

import streamlit as st

from marriage_document_workspace import MarriageDocumentWorkspace


def _show_particular(label: str, value: str, note: str | None) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.write(value)
        if note:
            st.caption(note)


def _show_condition(condition) -> None:
    with st.container(border=True):
        left, right = st.columns([5, 1.5])
        with left:
            st.markdown(
                f"**Item {condition.item_number}: {condition.subject}**"
            )
            if condition.note:
                st.caption(condition.note)
        with right:
            st.markdown("**Answer**")
            st.write(condition.recorded_answer)


def show_marriage_document_workspace(
    workspace: MarriageDocumentWorkspace,
) -> None:
    """Render the compact solicitor-facing marriage-document review."""

    source = workspace.sources[0] if workspace.sources else None
    page_text = ""
    if source and source.pages:
        page_text = ", ".join(str(page) for page in source.pages)

    st.title("Nikah Nama review")

    if source:
        caption = f"Source: {source.filename}"
        if page_text:
            caption += f" | Page {page_text}"
        st.caption(caption)

    if workspace.partial:
        st.info(
            "Partial review. Important marriage particulars remain to be "
            "recovered from the reviewed sections."
        )

    st.markdown("### What this page shows")

    if workspace.particulars:
        columns = st.columns(2)
        for index, item in enumerate(workspace.particulars):
            with columns[index % 2]:
                _show_particular(
                    item.label,
                    item.value,
                    item.note,
                )
    else:
        st.caption(
            "No core marriage particulars have yet been recovered from "
            "the reviewed sections."
        )

    if workspace.special_conditions:
        st.markdown("### Conditions recorded on the Nikah Nama")
        st.caption(
            "These are plain-English descriptions of the form items. "
            "The recorded answers come from the reviewed section."
        )
        for condition in workspace.special_conditions:
            _show_condition(condition)

    if workspace.missing_core_particulars:
        st.markdown("### Important details not yet recovered")
        st.write(
            ", ".join(workspace.missing_core_particulars)
        )

    st.markdown("### What needs checking")
    if workspace.issues:
        for issue in workspace.issues:
            st.markdown(f"- {issue}")
    else:
        st.caption(
            "No additional point has been flagged from the reviewed material."
        )

    st.markdown("### Recommended next step")
    if workspace.actions:
        for index, action in enumerate(workspace.actions, start=1):
            st.markdown(f"{index}. {action}")
    else:
        st.caption(
            "No further action has been generated from the reviewed sections."
        )

    st.caption(
        "If a certified English translation is required for formal use, "
        "obtain one from a suitably qualified translator."
    )

    # Deliberately no technical audit block here. Technical provenance belongs
    # in the application's Audit workspace, not in the solicitor working page.
