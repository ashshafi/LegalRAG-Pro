"""Streamlit UI for selecting and maintaining legal cases."""

from __future__ import annotations

import logging

import streamlit as st

from authentication import current_user_identity
from case_management import Case, CaseRepository, MatterAccessError

LOGGER = logging.getLogger(__name__)

ACTIVE_CASE_KEY = "active_case_id"


def show_case_selector(repository: CaseRepository | None = None) -> Case | None:
    """Render case selection and lightweight case maintenance controls.

    The selected case is stored in Streamlit session state. This milestone
    deliberately does not pass the case into document retrieval; case-aware
    indexing and RAG isolation are later milestones.

    Args:
        repository: Optional repository override, primarily useful for tests.

    Returns:
        The currently selected case, or ``None`` when no cases exist.
    """

    repo = repository or CaseRepository()
    user = current_user_identity()
    cases = repo.list_for_user(user)

    st.sidebar.title("🗂 Matters")

    if not cases:
        st.sidebar.info("No matters yet. Create your first matter below.")
        _show_create_case_form(repo, user=user)
        st.session_state.pop(ACTIVE_CASE_KEY, None)
        st.sidebar.divider()
        return None

    active_case_id = _resolve_active_case_id(cases)
    case_by_id = {case.case_id: case for case in cases}
    case_ids = [case.case_id for case in cases]
    selected_index = case_ids.index(active_case_id)

    selected_case_id = st.sidebar.selectbox(
        "Active matter",
        options=case_ids,
        index=selected_index,
        format_func=lambda case_id: _case_label(case_by_id[case_id]),
        key="case_selector",
    )
    st.session_state[ACTIVE_CASE_KEY] = selected_case_id
    active_case = case_by_id[selected_case_id]

    if active_case.case_number:
        st.sidebar.caption(f"Reference: {active_case.case_number}")

    access = repo.require_access(user, active_case.case_id)

    with st.sidebar.expander("➕ Create matter"):
        _show_create_case_form(repo, user=user, embedded=True)

    with st.sidebar.expander("✏️ Edit active matter"):
        if access.membership.can_manage_matter:
            _show_edit_case_form(repo, active_case)
        else:
            st.caption("You have read-only access to this matter.")

    with st.sidebar.expander("📥 Assign legacy documents"):
        if access.membership.can_manage_matter:
            _show_legacy_assignment(active_case)
        else:
            st.caption("Your role does not allow legacy document assignment.")

    st.sidebar.divider()
    return active_case


def _resolve_active_case_id(cases: list[Case]) -> str:
    """Return a valid active case ID, defaulting to the first listed case."""

    valid_ids = {case.case_id for case in cases}
    stored_id = st.session_state.get(ACTIVE_CASE_KEY)

    if stored_id in valid_ids:
        return stored_id

    active_case_id = cases[0].case_id
    st.session_state[ACTIVE_CASE_KEY] = active_case_id
    return active_case_id


def _case_label(case: Case) -> str:
    """Return the concise label displayed by the case selector."""

    if case.case_number:
        return f"{case.name} ({case.case_number})"
    return case.name


def _show_create_case_form(
    repository: CaseRepository,
    *,
    user,
    embedded: bool = False,
) -> None:
    """Render the create-case form and persist valid submissions."""

    form_key = "create_case_embedded" if embedded else "create_case_empty"
    with st.form(form_key, clear_on_submit=True):
        name = st.text_input("Matter name", key=f"{form_key}_name")
        case_number = st.text_input("Reference", key=f"{form_key}_number")
        claimant = st.text_input("Claimant", key=f"{form_key}_claimant")
        respondent = st.text_input("Respondent", key=f"{form_key}_respondent")
        submitted = st.form_submit_button(
            "Create matter",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        case = Case.create(
            name,
            case_number=case_number,
            claimant=claimant,
            respondent=respondent,
        )
        repository.create_for_user(case, user)
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Unable to create case.")
        st.error("The matter could not be created.")
        return

    st.session_state[ACTIVE_CASE_KEY] = case.case_id
    st.success(f"Created {case.name}.")
    st.rerun()


def _show_edit_case_form(repository: CaseRepository, case: Case) -> None:
    """Render the active-case edit form and persist submitted changes."""

    form_key = f"edit_case_{case.case_id}"
    with st.form(form_key):
        name = st.text_input("Matter name", value=case.name)
        case_number = st.text_input(
            "Reference",
            value=case.case_number or "",
        )
        claimant = st.text_input("Claimant", value=case.claimant or "")
        respondent = st.text_input("Respondent", value=case.respondent or "")
        status = st.selectbox(
            "Status",
            options=("active", "closed"),
            index=0 if case.status == "active" else 1,
        )
        submitted = st.form_submit_button(
            "Save changes",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        updated = case.updated(
            name=name,
            case_number=case_number,
            claimant=claimant,
            respondent=respondent,
            status=status,
        )
        repository.update(updated)
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Unable to update case %s.", case.case_id)
        st.error("The matter could not be updated.")
        return

    st.success("Matter updated.")
    st.rerun()


def _show_legacy_assignment(case: Case) -> None:
    """Render a reviewed migration workflow for pre-case-management documents."""

    try:
        from document_manager import (
            commit_legacy_assignment,
            get_legacy_documents,
            preview_legacy_assignment,
        )

        legacy_documents = get_legacy_documents()
    except Exception:
        LOGGER.exception("Unable to inspect legacy Chroma documents.")
        st.warning("Legacy document assignments are currently unavailable.")
        return

    if not legacy_documents:
        st.caption("No unassigned legacy documents.")
        return

    filename = st.selectbox(
        "Legacy document",
        options=legacy_documents,
        key=f"legacy_document_{case.case_id}",
    )

    try:
        plan = preview_legacy_assignment(filename, case.case_id)
    except Exception:
        LOGGER.exception("Unable to preview legacy assignment.")
        st.error("The assignment could not be previewed.")
        return

    st.caption(
        f"{plan.chunk_count} legacy chunk(s) will be assigned to {case.name}. "
        "Embeddings will not be regenerated."
    )

    confirmed = st.checkbox(
        f"I confirm {filename} belongs to {case.name}",
        key=f"confirm_legacy_{case.case_id}_{filename}",
    )

    if st.button(
        "Assign to active matter",
        disabled=not confirmed or plan.chunk_count == 0,
        use_container_width=True,
        key=f"assign_legacy_{case.case_id}_{filename}",
    ):
        try:
            assigned = commit_legacy_assignment(plan)
        except Exception:
            LOGGER.exception("Unable to commit legacy assignment.")
            st.error("The legacy document could not be assigned.")
            return

        st.success(f"Assigned {assigned} chunk(s) from {filename}.")
        st.rerun()
