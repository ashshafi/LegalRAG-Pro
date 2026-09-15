"""Commercial solicitor-facing Overview facade.

The established SWR1 matter_overview module remains the semantic and tested
read-only authority for attention ordering and projection validation. This
module changes presentation only.
"""
from __future__ import annotations

from html import escape
from typing import Any
import streamlit as st
import ui.matter_overview as base


def _html(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def show_solicitor_overview(
    active_case: Any | None,
    report_projection: Any | None,
    *,
    provider_error: Exception | None = None,
    selected_document_count: int = 0,
    issue_dashboard: Any | None = None,
    tasks: tuple[Any, ...] = (),
    issue_error: Exception | None = None,
    task_error: Exception | None = None,
) -> None:
    """Render existing SWR1 state as a compact commercial dashboard."""
    _html(
        '<div class="lr-page-heading">Overview</div>'
        '<div class="lr-page-lede">Current matter position, immediate work and key matter information.</div>'
    )
    if active_case is None:
        st.info("Select or create a matter to open its workspace.")
        return

    _html('<div class="lr-section-title">Needs attention now</div>')
    rows = base._attention_rows(issue_dashboard, tuple(tasks or ()))
    groups = base._attention_groups(rows)

    if groups:
        cards: list[str] = []
        for index, group in enumerate(groups[:5], start=1):
            label = base._group_attention_label(group)
            label_class = "lr-chip"
            if label == "HIGH PRIORITY":
                label_class += " lr-chip--high"
            elif label == "OVERDUE":
                label_class += " lr-chip--overdue"

            chips: list[str] = []
            position = str(group.get("position", "") or "").strip()
            if position and position != "NOT ASSESSED":
                chips.append('<span class="lr-chip">' + escape(position) + '</span>')
            chips.append('<span class="' + label_class + '">' + escape(label) + '</span>')

            task_rows = [row for row in group.get("rows", ()) if row.get("kind") == "task"]
            work_lines: list[str] = []
            if task_rows:
                for row in task_rows:
                    line = escape(str(row.get("work", "") or "").strip())
                    due = str(row.get("due", "") or "").strip()
                    if due:
                        line += ' <span style="color:#667085">· Due ' + escape(due) + '</span>'
                    work_lines.append('<div class="lr-workline">' + line + '</div>')
            else:
                work_lines.append(
                    '<div class="lr-workline" style="color:#667085">'
                    'No open task is currently recorded for this unsettled issue.'
                    '</div>'
                )

            cards.append(
                '<div class="lr-attention-card">'
                '<div class="lr-attention-index">' + f"{index:02d}" + '</div>'
                '<div><div class="lr-attention-title">' + escape(str(group.get("issue_name", "") or "Issue")) + '</div>'
                '<div class="lr-chiprow">' + ''.join(chips) + '</div>' + ''.join(work_lines) + '</div></div>'
            )
        _html('<div class="lr-attention-list">' + ''.join(cards) + '</div>')
    else:
        st.caption("No prioritised attention item can be shown from the currently available issue and task state.")

    if issue_error is not None:
        st.caption("Current legal-issue position could not be loaded safely.")
    if task_error is not None:
        st.caption("Current solicitor tasks could not be loaded safely.")

    next_due = base._next_work_due(tuple(tasks or ()))
    claimant = base._party_text(getattr(active_case, "claimant", None))
    respondent = base._party_text(getattr(active_case, "respondent", None))
    _html(
        '<div class="lr-summary-grid">'
        '<div class="lr-summary-card"><div class="lr-summary-label">Next work due</div><div class="lr-summary-value">'
        + escape(next_due) + '</div></div>'
        '<div class="lr-summary-card"><div class="lr-summary-label">Procedural stage</div><div class="lr-summary-value">Not recorded in the matter workspace</div></div>'
        '<div class="lr-summary-card"><div class="lr-summary-label">Parties</div><div class="lr-summary-value">'
        + escape(claimant) + '<br>' + escape(respondent) + '</div></div></div>'
    )
    st.caption(
        "LegalRAG does not infer procedural stage, hearing dates or legal deadlines from document text."
    )

    _html('<div class="lr-section-title">Matter information</div>')

    if provider_error is not None:
        base._metric_columns((("Selected documents", int(selected_document_count)),))
        st.error(
            "The stored report projection could not be validated. "
            "No projection-derived matter inventory has been displayed."
        )
        return

    if report_projection is None:
        base._metric_columns((
            ("Selected documents", int(selected_document_count)),
            ("Legal issues", "Not available"),
            ("Chronology events", "Not available"),
            ("Evidence citations", "Not available"),
        ))
        st.info("No validated frozen report projection is available for this matter.")
        return

    try:
        base.validate_case_report_projection(report_projection)
    except Exception:
        st.error(
            "The frozen report projection could not be validated. "
            "No projection-derived matter inventory has been displayed."
        )
        base._metric_columns((("Selected documents", int(selected_document_count)),))
        return

    projection_case_id = getattr(getattr(report_projection, "case_header", None), "case_id", None)
    if projection_case_id != active_case.case_id:
        st.error(
            "The frozen report projection belongs to a different matter. "
            "No projection-derived matter inventory has been displayed."
        )
        base._metric_columns((("Selected documents", int(selected_document_count)),))
        return

    base._metric_columns((
        ("Documents", int(selected_document_count)),
        ("Issues", len(report_projection.issues)),
        ("Chronology", len(report_projection.chronology)),
        ("Evidence citations", len(report_projection.citations)),
    ))
    st.caption(
        "Read-only inventory counts from the validated report projection. "
        "They are not merits findings or risk scores."
    )


__all__ = ["show_solicitor_overview"]
