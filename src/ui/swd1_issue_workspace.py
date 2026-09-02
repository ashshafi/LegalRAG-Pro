"""Solicitor-first legal issue register and core issue workspace."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from legal_issue_dashboard import (
    LegalIssueDashboardError,
    build_legal_issue_dashboard,
)

AuthorityLoader = Callable[[str], Any]

_TECHNICAL_MAPPING_TEXT = (
    "M4 does not promote the raw excerpt itself into an established proposition"
)
_PREVIEW_LIMIT = 520


def _issue_position(issue) -> str:
    counts = issue.synthesis_counts
    if counts.disputed:
        return "DISPUTED"
    if counts.insufficiently_evidenced:
        return "EVIDENCE INCOMPLETE"
    if counts.unresolved:
        return "UNRESOLVED"
    if counts.partially_supported:
        return "PARTIALLY SUPPORTED"
    if counts.well_supported:
        return "WELL SUPPORTED"
    return "NOT ASSESSED"


def _issue_confidence(issue) -> str:
    counts = issue.confidence_counts
    if counts.low:
        return "LOW"
    if counts.medium:
        return "MEDIUM"
    if counts.high:
        return "HIGH"
    return "NOT RECORDED"


def _position_explanation(position: str) -> str:
    return {
        "DISPUTED": "Material parts of this issue remain contested on the current evidence.",
        "EVIDENCE INCOMPLETE": "The current evidence is not yet sufficient for a secure assessment.",
        "UNRESOLVED": "A material legal question remains unresolved on the current evidence.",
        "PARTIALLY SUPPORTED": "The evidence provides meaningful support, but the issue is not fully established.",
        "WELL SUPPORTED": "The issue is well supported on the current evidential record.",
        "NOT ASSESSED": "No current assessment is recorded for this issue.",
    }[position]


def _label(value: str) -> str:
    return str(value).replace("_", " ").strip().upper()


def _unique_statements(*groups):
    seen = set()
    result = []
    for group in groups:
        for statement in tuple(group):
            key = (
                statement.text,
                tuple(statement.evidence_keys),
                tuple(statement.citations),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(statement)
    return tuple(result)


def _display_text(value: str) -> str:
    text = str(value).strip()
    if text.lower().startswith("source assertion:"):
        text = text[len("source assertion:"):].strip()
    return text


def _group_display_statements(statements):
    """Group repeated legal propositions while retaining all source citations."""
    substantive: dict[str, list[str]] = {}
    technical: dict[str, list[str]] = {}

    for statement in tuple(statements):
        text = _display_text(statement.text)
        bucket = technical if _TECHNICAL_MAPPING_TEXT in text else substantive
        citations = bucket.setdefault(text, [])
        for citation in tuple(statement.citations):
            value = str(citation).strip()
            if value and value not in citations:
                citations.append(value)

    return (
        tuple((text, tuple(citations)) for text, citations in substantive.items()),
        tuple((text, tuple(citations)) for text, citations in technical.items()),
    )


def _citation_caption(citations) -> str:
    values = tuple(citations)
    if not values:
        return ""
    shown = values[:3]
    suffix = (
        ""
        if len(values) <= 3
        else f" · +{len(values) - 3} more source"
        + ("s" if len(values) - 3 != 1 else "")
    )
    return "Source" + ("s" if len(values) > 1 else "") + ": " + " | ".join(shown) + suffix


def _write_statement(text: str, citations, *, allow_full_text: bool) -> None:
    with st.container(border=True):
        if len(text) <= _PREVIEW_LIMIT:
            st.write(text)
        else:
            preview = text[:_PREVIEW_LIMIT].rsplit(" ", 1)[0].rstrip()
            st.write(preview + "…")
            if allow_full_text:
                with st.expander("Read full passage", expanded=False):
                    st.write(text)
            else:
                st.caption("Full passage available in the cited source.")

        caption = _citation_caption(citations)
        if caption:
            st.caption(caption)


def _first_open_point(issue) -> str | None:
    for element in issue.elements:
        if element.unresolved_matters:
            return element.unresolved_matters[0]
    for element in issue.elements:
        if element.limitations:
            return element.limitations[0]
    if issue.overall_limitations:
        return issue.overall_limitations[0]
    return None


def _default_element(issue):
    precedence = (
        "disputed",
        "insufficiently_evidenced",
        "unresolved",
        "partially_supported",
        "well_supported_on_current_record",
    )
    elements = tuple(issue.elements)
    for status in precedence:
        for element in elements:
            if str(element.provisional_status).strip().lower() == status:
                return element
    return elements[0] if elements else None


def _recommended_next_action(element) -> str:
    if element.unresolved_matters:
        return (
            "Check the contemporaneous record for evidence that directly "
            "resolves the selected question."
        )
    if element.limitations:
        return (
            "Review the recorded limitation against the source material "
            "before changing the current assessment."
        )
    return (
        "Review the principal evidence and confirm whether the current "
        "assessment remains appropriate."
    )


def _render_evidence(title: str, statements, *, empty_message: str) -> None:
    st.subheader(title)
    substantive, technical = _group_display_statements(statements)

    if not substantive:
        st.caption(empty_message)
    else:
        for text, citations in substantive[:3]:
            _write_statement(text, citations, allow_full_text=True)

        if len(substantive) > 3:
            with st.expander(
                f"More supporting material ({len(substantive) - 3})",
                expanded=False,
            ):
                for text, citations in substantive[3:]:
                    _write_statement(text, citations, allow_full_text=False)

    if technical:
        with st.expander(
            f"Additional source mappings ({len(technical)})",
            expanded=False,
        ):
            st.caption(
                "Technical mapping material is retained here for traceability "
                "but is not part of the primary solicitor view."
            )
            for text, citations in technical:
                _write_statement(text, citations, allow_full_text=False)


def show_swd1_issue_workspace(
    active_case_id: str | None,
    *,
    authority_loader: AuthorityLoader = load_active_governed_analytical_authority,
) -> None:
    """Render SWD1-I1/I2 without changing analytical or authority state."""

    st.header("Legal Issues")
    st.caption(
        "Current case assessment — work the legal issue, evidence and next action here."
    )

    if active_case_id is None:
        st.info("Select an active matter to work on its legal issues.")
        return

    try:
        authority = authority_loader(active_case_id)
    except GovernedAnalyticalAuthorityProviderError:
        st.error(
            "The current case assessment could not be validated. "
            "No legal analysis has been displayed."
        )
        return

    if authority is None:
        st.info("No current case assessment is available for this matter.")
        return

    try:
        dashboard = build_legal_issue_dashboard(
            active_case_id=active_case_id,
            authority=authority,
        )
    except LegalIssueDashboardError:
        st.error(
            "The current case assessment could not be projected safely. "
            "No legal analysis has been displayed."
        )
        return

    selected_id = st.session_state.get("swd1_selected_issue_id")
    selected_issue = next(
        (
            issue
            for issue in dashboard.issues
            if issue.issue_analysis_id == selected_id
        ),
        None,
    )

    if selected_issue is None:
        st.info(
            "Choose an issue to see where the case stands, what is weak, "
            "and what should be done next."
        )

        for issue in dashboard.issues:
            position = _issue_position(issue)
            support = _issue_confidence(issue)
            open_point = _first_open_point(issue)

            with st.container(border=True):
                st.subheader(issue.issue_name)

                left, right = st.columns(2)
                with left:
                    st.caption("CURRENT POSITION")
                    st.write(position)
                with right:
                    st.caption("EVIDENTIAL SUPPORT")
                    st.write(support.title())

                st.write(_position_explanation(position))

                if open_point:
                    st.markdown("**Main weakness**")
                    st.write(open_point)
                else:
                    st.caption(
                        "No specific unresolved point is recorded for this issue."
                    )

                st.caption(
                    "Open the issue to review the evidence and decide the next legal action."
                )

                if st.button(
                    "Open issue",
                    key="swd1_open_issue::" + issue.issue_analysis_id,
                    type="primary",
                ):
                    st.session_state["swd1_selected_issue_id"] = (
                        issue.issue_analysis_id
                    )
                    st.session_state.pop("swd1_selected_element_id", None)
                    st.rerun()

        with st.expander("Audit", expanded=False):
            st.caption("Current governed authority: " + dashboard.authority_id)
            st.caption("Activation: " + dashboard.activation_id)
        return

    if st.button("← Back to issues", key="swd1_back_to_issues"):
        st.session_state.pop("swd1_selected_issue_id", None)
        st.session_state.pop("swd1_selected_element_id", None)
        st.rerun()

    st.header(selected_issue.issue_name)
    st.caption("Legal question: " + selected_issue.original_user_question)

    position = _issue_position(selected_issue)
    support = _issue_confidence(selected_issue)

    with st.container(border=True):
        st.caption("CURRENT POSITION")
        st.subheader(position)
        st.write("Overall evidential support: " + support.title())
        st.write(_position_explanation(position))

    elements = tuple(selected_issue.elements)
    if not elements:
        st.info("No governed legal questions are available for this issue.")
        return

    default = _default_element(selected_issue)
    ids = tuple(element.element_id for element in elements)
    chosen = st.session_state.get("swd1_selected_element_id")
    if chosen not in ids:
        chosen = default.element_id

    chosen = st.selectbox(
        "Question to work on",
        ids,
        index=ids.index(chosen),
        format_func=lambda element_id: next(
            (
                element.legal_question
                for element in elements
                if element.element_id == element_id
            ),
            element_id,
        ),
        key="swd1_question_select",
    )
    st.session_state["swd1_selected_element_id"] = chosen
    element = next(item for item in elements if item.element_id == chosen)

    st.caption(
        "Selected question — position: "
        + _label(element.provisional_status)
        + " · Evidential support: "
        + _label(element.analysis_confidence).title()
    )

    weakness = (
        element.unresolved_matters[0]
        if element.unresolved_matters
        else (
            element.limitations[0]
            if element.limitations
            else None
        )
    )

    if weakness:
        with st.container(border=True):
            st.subheader("Main weakness")
            st.write(weakness)

    st.subheader("Why this matters")
    st.write(element.legal_significance)

    indicating = _unique_statements(
        element.established_matters,
        element.supported_matters,
        element.corroborative_material,
    )
    challenging = _unique_statements(
        element.not_supported_matters,
        element.adverse_material,
        element.conflicting_material,
    )

    _render_evidence(
        "Evidence indicating the proposition",
        indicating,
        empty_message=(
            "No established, supporting or corroborative proposition "
            "is recorded for this question."
        ),
    )
    _render_evidence(
        "Evidence challenging or limiting that conclusion",
        challenging,
        empty_message=(
            "No adverse, conflicting or not-supported proposition "
            "is recorded for this question."
        ),
    )

    st.subheader("What remains unclear")
    if element.unresolved_matters:
        for item in element.unresolved_matters:
            st.write("• " + item)
    else:
        st.caption("No unresolved matter is recorded for this question.")

    if element.limitations:
        with st.expander("Important limitations", expanded=False):
            for item in element.limitations:
                st.write("• " + item)

    st.subheader("Next legal action")
    st.write(_recommended_next_action(element))

    with st.expander("Audit", expanded=False):
        st.caption("Issue analysis ID: " + selected_issue.issue_analysis_id)
        st.caption(
            "Issue definition: "
            + selected_issue.issue_definition_id
            + "/"
            + selected_issue.issue_definition_version
        )
        st.caption("Element ID: " + element.element_id)
        st.caption("Raw question position: " + element.provisional_status)
        st.caption("Raw analysis confidence: " + element.analysis_confidence)
        st.caption("Current governed authority: " + dashboard.authority_id)
        st.caption("Activation: " + dashboard.activation_id)


__all__ = ["show_swd1_issue_workspace"]
