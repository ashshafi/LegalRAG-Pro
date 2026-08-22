"""Native Streamlit presentation for the governed Legal Issue Dashboard."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from governed_analytical_authority.models import GovernedRuntimeAnalyticalAuthority
from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from legal_issue_dashboard import (
    DashboardElement,
    DashboardGap,
    DashboardStatement,
    LegalIssueDashboardError,
    build_legal_issue_dashboard,
)


AuthorityLoader = Callable[[str], GovernedRuntimeAnalyticalAuthority | None]


def _show_metric_rows(
    metrics: tuple[tuple[str, int], ...],
) -> None:
    """Render dashboard metrics in readable rows of at most two columns."""

    for start in range(0, len(metrics), 2):
        row = metrics[start : start + 2]
        columns = st.columns(len(row))
        for column, (label, value) in zip(columns, row, strict=True):
            column.metric(label, value)


def _show_statements(
    label: str,
    statements: tuple[DashboardStatement, ...],
) -> None:
    if not statements:
        return
    st.text(label)
    for statement in statements:
        st.write("- " + statement.text)
        if statement.citations:
            st.caption("Citations: " + " | ".join(statement.citations))
        if statement.evidence_keys:
            st.caption("Evidence keys: " + " | ".join(statement.evidence_keys))


def _show_gaps(gaps: tuple[DashboardGap, ...]) -> None:
    if not gaps:
        return
    st.text("Evidential gaps")
    for gap in gaps:
        st.write(f"- {gap.description} [{gap.materiality}]")
        st.caption(f"Gap ID: {gap.gap_id}")
        st.caption("Reason: " + gap.reason)
        if gap.suggested_evidence_target:
            st.caption("Suggested evidence target: " + gap.suggested_evidence_target)


def _show_element(element: DashboardElement) -> None:
    with st.expander(
        f"{element.element_id} - {element.element_name}",
        expanded=False,
    ):
        st.text("Legal question")
        st.write(element.legal_question)
        st.text("Current evidential position")
        st.write(element.current_evidential_position)
        st.caption(
            "Frozen M5 status: "
            + element.provisional_status.upper()
            + " | Confidence: "
            + element.analysis_confidence.upper()
        )

        _show_statements("Established matters", element.established_matters)
        _show_statements("Supported matters", element.supported_matters)
        _show_statements("Not-supported matters", element.not_supported_matters)
        _show_statements("Source assertions", element.source_assertions)
        _show_statements("Adverse material", element.adverse_material)
        _show_statements("Corroborative material", element.corroborative_material)
        _show_statements("Contextual material", element.contextual_material)
        _show_statements("Conflicting material", element.conflicting_material)

        if element.disputed_matters:
            st.text("Disputed matters")
            for dispute in element.disputed_matters:
                st.write("- " + dispute.proposition)
                st.caption("Dispute ID: " + dispute.disputed_matter_id)
                if dispute.claimant_position:
                    st.caption("Claimant position: " + dispute.claimant_position)
                if dispute.respondent_position:
                    st.caption("Respondent position: " + dispute.respondent_position)

        _show_gaps(element.evidential_gaps)

        if element.unresolved_matters:
            st.text("Unresolved matters")
            for matter in element.unresolved_matters:
                st.write("- " + matter)

        if element.limitations:
            st.text("Limitations")
            for limitation in element.limitations:
                st.write("- " + limitation)

        st.text("Legal significance")
        st.write(element.legal_significance)
        st.text("Provisional analysis")
        st.write(element.provisional_analysis)

        counts = element.evidence_counts
        st.caption(
            "Unique element evidence keys: "
            f"supporting={counts.supporting}, "
            f"adverse={counts.adverse}, "
            f"corroborative={counts.corroborative}, "
            f"neutral={counts.neutral}, "
            f"conflicting={counts.conflicting}, "
            f"distinct_any_role={counts.distinct_any_role}"
        )


def show_legal_issue_dashboard(
    active_case_id: str | None,
    *,
    authority_loader: AuthorityLoader = load_active_governed_analytical_authority,
) -> None:
    """Render only already-validated frozen analytical authority state."""

    st.header("\u2696\ufe0f Legal Issue Dashboard")
    if active_case_id is None:
        st.info("Select an active case to view its governed legal issues.")
        return

    try:
        authority = authority_loader(active_case_id)
    except GovernedAnalyticalAuthorityProviderError:
        st.error(
            "The activated governed analytical authority could not be validated. "
            "No dashboard analysis has been displayed."
        )
        return

    if authority is None:
        st.info(
            "No activated governed analytical authority is available for the active case."
        )
        return

    try:
        dashboard = build_legal_issue_dashboard(
            active_case_id=active_case_id,
            authority=authority,
        )
    except LegalIssueDashboardError:
        st.error(
            "The frozen analytical authority could not be projected safely. "
            "No dashboard analysis has been displayed."
        )
        return

    st.caption(
        "Read-only governed authority: "
        + dashboard.authority_id
        + " | Activation: "
        + dashboard.activation_id
    )
    st.info(
        "Evidence metrics count distinct frozen evidence keys by analytical role. "
        "One evidence key may appear in more than one role, so role counts must not "
        "be summed as an overall evidence total."
    )

    for issue in dashboard.issues:
        st.subheader(
            f"{issue.issue_definition_id}/{issue.issue_definition_version} - "
            + issue.issue_name
        )
        st.caption("Issue analysis ID: " + issue.issue_analysis_id)
        st.write(issue.issue_summary)

        counts = issue.synthesis_counts
        _show_metric_rows(
            (
                ("Well-supported", counts.well_supported),
                ("Partially supported", counts.partially_supported),
                ("Disputed", counts.disputed),
                ("Insufficient evidence", counts.insufficiently_evidenced),
                ("Unresolved", counts.unresolved),
            )
        )

        confidence = issue.confidence_counts
        _show_metric_rows(
            (
                ("High confidence elements", confidence.high),
                ("Medium confidence elements", confidence.medium),
                ("Low confidence elements", confidence.low),
            )
        )

        evidence = issue.evidence_counts
        _show_metric_rows(
            (
                ("Supporting evidence", evidence.supporting),
                ("Adverse evidence", evidence.adverse),
                ("Corroborative evidence", evidence.corroborative),
                ("Neutral/context evidence", evidence.neutral),
                ("Conflicting evidence", evidence.conflicting),
                ("Distinct evidence involved", evidence.distinct_any_role),
            )
        )

        st.caption(
            f"Element-level evidential gaps: {issue.evidential_gap_count} | "
            f"Unresolved matters: {issue.unresolved_matter_count}"
        )

        if issue.overall_limitations:
            with st.expander("Overall limitations", expanded=False):
                for limitation in issue.overall_limitations:
                    st.write("- " + limitation)

        for element in issue.elements:
            _show_element(element)

        st.divider()


__all__ = ["show_legal_issue_dashboard"]
