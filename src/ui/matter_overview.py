"""Read-only Matter Overview presentation for the LegalRAG Pro workspace shell."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Protocol

import streamlit as st

from case_reporting.validation import validate_case_report_projection


MATTER_OVERVIEW_VIEW_KEY = "ppr4_matter_overview_view"
MATTER_OVERVIEW_CASE_KEY = "ppr4_matter_overview_case_id"


class MatterRecord(Protocol):
    """Minimal persisted matter presentation contract."""

    case_id: str
    name: str
    case_number: str | None
    claimant: str | None
    respondent: str | None
    status: str


def set_matter_overview_view(
    session_state: MutableMapping[str, Any],
    active: bool,
) -> None:
    """Set the presentation-only Matter Overview route state."""

    session_state[MATTER_OVERVIEW_VIEW_KEY] = bool(active)


def is_matter_overview_active(session_state: MutableMapping[str, Any]) -> bool:
    """Return whether the presentation-only Matter Overview route is active."""

    return bool(session_state.get(MATTER_OVERVIEW_VIEW_KEY, False))


def synchronise_matter_overview_session_state(
    active_case_id: str | None,
    *,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Default each newly selected matter to Overview without overriding user navigation."""

    state = st.session_state if session_state is None else session_state
    previous_case_id = state.get(MATTER_OVERVIEW_CASE_KEY)

    if previous_case_id != active_case_id:
        state[MATTER_OVERVIEW_CASE_KEY] = active_case_id
        set_matter_overview_view(state, active_case_id is not None)
        return

    if MATTER_OVERVIEW_VIEW_KEY not in state:
        set_matter_overview_view(state, active_case_id is not None)


def _metric_columns(values: tuple[tuple[str, str | int], ...]) -> None:
    for start in range(0, len(values), 2):
        row = values[start : start + 2]
        columns = st.columns(len(row))
        for column, (label, value) in zip(columns, row, strict=True):
            column.metric(label, value)


def _status_text(value: str) -> str:
    stripped = str(value).strip()
    return stripped.title() if stripped else "Not recorded"


def _party_text(value: str | None) -> str:
    if value is None:
        return "Not recorded"
    stripped = str(value).strip()
    return stripped if stripped else "Not recorded"


def show_matter_overview(
    active_case: MatterRecord | None,
    report_projection: Any | None,
    *,
    provider_error: Exception | None = None,
    selected_document_count: int = 0,
) -> None:
    """Render a truthful read-only overview from already available application state."""

    st.title("\u2696\ufe0f Matter Overview")

    if active_case is None:
        st.info("Select or create a matter to open its workspace.")
        return

    st.header(active_case.name)
    st.caption(
        "Reference: "
        + (active_case.case_number or "Not recorded")
        + " \u00b7 Status: "
        + _status_text(active_case.status)
    )

    st.subheader("Parties")
    st.write("Claimant: " + _party_text(active_case.claimant))
    st.write("Respondent: " + _party_text(active_case.respondent))
    st.caption(
        "Claimant and Respondent are the current Employment matter roles. "
        "Generic party-role templates are a later platform milestone."
    )

    if provider_error is not None:
        st.subheader("Matter Intelligence")
        _metric_columns((("Selected documents", int(selected_document_count)),))
        st.error(
            "The stored report projection could not be validated. "
            "No projection-derived matter intelligence has been displayed."
        )
        return

    if report_projection is None:
        st.subheader("Matter Intelligence")
        _metric_columns(
            (
                ("Selected documents", int(selected_document_count)),
                ("Legal issues", "Not available"),
                ("Chronology events", "Not available"),
                ("Evidence citations", "Not available"),
            )
        )
        st.info("No validated frozen report projection is available for this matter.")
        return

    try:
        validate_case_report_projection(report_projection)
    except Exception:
        st.error(
            "The frozen report projection could not be validated. "
            "No projection-derived matter intelligence has been displayed."
        )
        _metric_columns((("Selected documents", int(selected_document_count)),))
        return

    projection_case_id = getattr(
        getattr(report_projection, "case_header", None),
        "case_id",
        None,
    )
    if projection_case_id != active_case.case_id:
        st.error(
            "The frozen report projection belongs to a different matter. "
            "No projection-derived matter intelligence has been displayed."
        )
        _metric_columns((("Selected documents", int(selected_document_count)),))
        return

    st.subheader("Matter Intelligence")
    _metric_columns(
        (
            ("Selected documents", int(selected_document_count)),
            ("Legal issues", len(report_projection.issues)),
            ("Chronology events", len(report_projection.chronology)),
            ("Evidence citations", len(report_projection.citations)),
        )
    )
    st.caption(
        "Projection counts are read-only inventory measures from the validated frozen "
        "report projection. They are not merits findings or evidence-weight scores."
    )

    st.subheader("Attention")
    _metric_columns(
        (
            ("Material conflicts", len(report_projection.conflicts)),
            ("Evidence gaps", len(report_projection.gaps)),
            ("Risk areas", len(report_projection.risks)),
        )
    )

    st.subheader("Quick Start")
    st.write(
        "Use the workspace navigation for Documents, Legal Issues, Evidence, Analysis, "
        "Assistant, Reports, and Sources & Provenance."
    )
