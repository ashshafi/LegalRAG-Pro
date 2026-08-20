"""Read-only deterministic Finance F7B2 report export presentation."""
from __future__ import annotations

import streamlit as st

from finance_reporting import (
    FinanceReportProjection,
    render_finance_html_report,
    render_finance_markdown_report,
    validate_finance_report_projection,
)


def render_finance_report_exports(projection: FinanceReportProjection) -> None:
    """Expose F7A deterministic exports without creating new report semantics."""

    validate_finance_report_projection(projection)
    markdown_text = render_finance_markdown_report(projection)
    html_text = render_finance_html_report(projection)

    st.subheader("Deterministic report exports")
    st.caption("Exports are rendered directly from the frozen FinanceReportProjection.")
    st.download_button(
        "Download Markdown",
        data=markdown_text,
        file_name=f"finance-report-{projection.report_projection_id}.md",
        mime="text/markdown",
        key="finance_f7b2_export_markdown",
    )
    st.download_button(
        "Download HTML",
        data=html_text,
        file_name=f"finance-report-{projection.report_projection_id}.html",
        mime="text/html",
        key="finance_f7b2_export_html",
    )


__all__ = ["render_finance_report_exports"]
