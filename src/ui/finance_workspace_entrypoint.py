"""Read-only UI entrypoint for an already-published Finance projection."""

from __future__ import annotations

import streamlit as st

from finance_report_projection_provider import load_active_finance_report_projection
from ui.finance_workspace import render_finance_workspace


_MISSING_PROJECTION_TEXT = "No active Finance report projection is available for this workspace."


def show_finance_workspace(*, workspace_id: str) -> None:
    """Load and render one already-published Finance projection read-only."""

    if not isinstance(workspace_id, str):
        raise TypeError("workspace_id must be a str.")
    if not workspace_id.strip():
        raise ValueError("workspace_id must be non-empty.")

    projection = load_active_finance_report_projection(workspace_id)
    if projection is None:
        st.info(_MISSING_PROJECTION_TEXT)
        return None

    render_finance_workspace(
        workspace_id=workspace_id,
        projection=projection,
        index=None,
    )
    return None


__all__ = ["show_finance_workspace"]
