"""Explicit UI boundary for binding one Legal case to one published Finance workspace."""

from __future__ import annotations

import streamlit as st

from finance_case_binding.activation import activate_finance_case_binding
from finance_workspace_catalog import (
    PublishedFinanceWorkspace,
    load_published_finance_workspace_catalog,
)


def _workspace_label(entry: PublishedFinanceWorkspace) -> str:
    return (
        f"{entry.workspace_id} | as of {entry.as_of.isoformat()} | "
        f"{entry.provider_id} | {entry.dataset_id} {entry.dataset_version}"
    )


def show_finance_binding_manager(*, case_id: str) -> None:
    """Offer explicit user-authorised ACTIVATE only when a case has no binding."""

    if not isinstance(case_id, str):
        raise TypeError("case_id must be a str.")
    if not case_id.strip():
        raise ValueError("case_id must be non-empty.")

    entries = load_published_finance_workspace_catalog()
    if not entries:
        st.info("No published Finance workspaces are available to bind.")
        return

    by_id = {entry.workspace_id: entry for entry in entries}
    workspace_ids = tuple(by_id)

    selected_workspace_id = st.selectbox(
        "Published Finance workspace",
        options=workspace_ids,
        format_func=lambda workspace_id: _workspace_label(by_id[workspace_id]),
    )

    selected = by_id[selected_workspace_id]
    st.caption(
        "Binding is explicit and case-scoped. "
        f"Selected projection: {selected.report_projection_id}"
    )

    if st.button("Bind Finance workspace", type="primary"):
        binding = activate_finance_case_binding(
            case_id=case_id,
            workspace_id=selected_workspace_id,
        )
        st.success(f"Finance workspace bound: {binding.workspace_id}")
        st.rerun()


__all__ = ["show_finance_binding_manager"]
