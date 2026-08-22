# Explicit UI boundary for lifecycle changes to an already-bound Finance workspace.

from finance_case_binding.activation import activate_finance_case_binding
from finance_case_binding.models import FinanceCaseBindingActivationAction
from finance_case_binding.provider import load_finance_case_binding_rollback_workspace_ids
from finance_workspace_catalog import (
    PublishedFinanceWorkspace,
    load_published_finance_workspace_catalog,
)
import streamlit as st


def _workspace_label(entry: PublishedFinanceWorkspace) -> str:
    return f"{entry.workspace_id} | projection {entry.report_projection_id}"


def show_finance_binding_lifecycle_manager(
    *,
    case_id: str,
    current_workspace_id: str,
) -> None:
    if not isinstance(case_id, str):
        raise TypeError("case_id must be a str.")
    if not case_id.strip():
        raise ValueError("case_id must be non-empty.")
    if not isinstance(current_workspace_id, str):
        raise TypeError("current_workspace_id must be a str.")
    if not current_workspace_id.strip():
        raise ValueError("current_workspace_id must be non-empty.")

    entries = load_published_finance_workspace_catalog()
    by_id = {entry.workspace_id: entry for entry in entries}
    switch_target_ids = tuple(
        workspace_id
        for workspace_id in by_id
        if workspace_id != current_workspace_id
    )
    rollback_authority_ids = load_finance_case_binding_rollback_workspace_ids(case_id)
    rollback_target_ids = tuple(
        workspace_id
        for workspace_id in rollback_authority_ids
        if workspace_id in by_id
    )

    if switch_target_ids:
        selected_switch_workspace_id = st.selectbox(
            "Switch target published Finance workspace",
            options=switch_target_ids,
            format_func=lambda workspace_id: _workspace_label(by_id[workspace_id]),
            key=f"finance-switch-target-{case_id}",
        )
        selected_switch = by_id[selected_switch_workspace_id]
        st.caption(f"Switch target: {_workspace_label(selected_switch)}")

        if st.button(
            "Switch Finance workspace",
            type="primary",
            key=f"finance-switch-{case_id}",
        ):
            binding = activate_finance_case_binding(
                case_id=case_id,
                workspace_id=selected_switch_workspace_id,
                action=FinanceCaseBindingActivationAction.ACTIVATE,
            )
            st.success(f"Finance workspace switched to {binding.workspace_id}.")
            st.rerun()
    else:
        st.info("No alternate published Finance workspace is available to switch to.")

    if rollback_target_ids:
        selected_rollback_workspace_id = st.selectbox(
            "Rollback target published Finance workspace",
            options=rollback_target_ids,
            format_func=lambda workspace_id: _workspace_label(by_id[workspace_id]),
            key=f"finance-rollback-target-{case_id}",
        )
        selected_rollback = by_id[selected_rollback_workspace_id]
        st.caption(f"Rollback target: {_workspace_label(selected_rollback)}")

        if st.button(
            "Rollback Finance workspace",
            key=f"finance-rollback-{case_id}",
        ):
            binding = activate_finance_case_binding(
                case_id=case_id,
                workspace_id=selected_rollback_workspace_id,
                action=FinanceCaseBindingActivationAction.ROLLBACK,
            )
            st.success(f"Finance workspace rolled back to {binding.workspace_id}.")
            st.rerun()
    else:
        st.info("No valid published prior Finance workspace is available for rollback.")


__all__ = ["show_finance_binding_lifecycle_manager"]
