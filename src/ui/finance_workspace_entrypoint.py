"""Read-only UI entrypoint for an already-published Finance projection."""

from __future__ import annotations

import streamlit as st

from finance_report_projection_provider import load_active_finance_report_projection
from ui.finance_workspace import render_finance_workspace
from finance_dataset_locator import (
    FinanceDatasetLocatorError,
    load_validated_immutable_dataset_for_projection,
)
from finance_historical_report import build_historical_finance_report


_MISSING_PROJECTION_TEXT = "No active Finance report projection is available for this workspace."


def show_finance_workspace(*, workspace_id: str) -> None:
    """Load and render one already-published Finance projection read-only."""

    if not isinstance(workspace_id, str):
        raise TypeError("workspace_id must be a str.")
    if not workspace_id.strip():
        raise ValueError("workspace_id must be non-empty.")

    projection = load_active_finance_report_projection(workspace_id)
    historical_report = None
    historical_report_error = None
    if projection is not None:
        try:
            historical_dataset = load_validated_immutable_dataset_for_projection(
                workspace_id=workspace_id,
                projection=projection,
            )
            if historical_dataset is not None:
                historical_report = build_historical_finance_report(
                    dataset=historical_dataset,
                )
        except FinanceDatasetLocatorError as exc:
            historical_report_error = str(exc)
    if projection is None:
        st.info(_MISSING_PROJECTION_TEXT)
        return None

    if historical_report is None and historical_report_error is None:
        render_finance_workspace(
        workspace_id=workspace_id,
        projection=projection,
        index=None,
    )
    else:
        render_finance_workspace(
            workspace_id=workspace_id,
            projection=projection,
            index=None,
            historical_report=historical_report,
            historical_report_error=historical_report_error,
        )
    return None


__all__ = ["show_finance_workspace"]
