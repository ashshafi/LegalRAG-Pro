from __future__ import annotations

import streamlit as st

from governed_analytical_authority.provider import (
    load_active_governed_analytical_authority,
)

from matter_analysis_ledger import (
    MatterAnalysisLedgerError,
    RelationshipReviewState,
    RelationshipType,
    build_matter_analysis_ledger,
    load_relationship_events,
    propose_relationship,
    review_relationship,
)


def _evidence_list(
    label: str,
    values: tuple[str, ...],
) -> None:

    st.markdown(
        f"**{label} - {len(values)}**"
    )

    if values:
        st.code(
            "\n".join(
                values
            ),
            language=None,
        )

    else:
        st.caption(
            "None recorded in the "
            "governed analytical matrix."
        )


def show_matter_analysis_ledger(
    active_case_id: str | None,
) -> None:

    if active_case_id is None:
        return

    try:
        authority = (
            load_active_governed_analytical_authority(
                active_case_id
            )
        )

    except Exception as exc:

        st.error(
            "Matter Analysis Ledger could not "
            "load the governed analytical authority."
        )

        st.caption(
            str(exc)
        )

        return

    if authority is None:
        return

    try:
        events = (
            load_relationship_events(
                case_id=
                    active_case_id,

                authority_id=
                    authority.manifest.authority_id,
            )
        )

        ledger = (
            build_matter_analysis_ledger(
                authority=
                    authority,

                events=
                    events,
            )
        )

    except MatterAnalysisLedgerError as exc:

        st.error(
            "Matter Analysis Ledger failed closed."
        )

        st.caption(
            str(exc)
        )

        return

    st.divider()

    st.header(
        "?? Matter Analysis Ledger"
    )

    st.caption(
        "Relationship review is bound to analytical authority "
        f"{ledger.authority_id}. "
        "A relationship begins as PROPOSED and becomes "
        "APPROVED or REJECTED only through an explicit reviewer action. "
        "The underlying source evidence and governed analytical authority "
        "are not silently overwritten."
    )

    for issue in ledger.issues:

        with st.expander(
            f"?? {issue.issue_name}",
            expanded=False,
        ):

            st.caption(
                "Issue analysis: "
                + issue.issue_analysis_id
            )

            if issue.issue_summary:
                st.write(
                    issue.issue_summary
                )

            for element in issue.elements:

                st.markdown(
                    "---"
                )

                st.subheader(
                    element.element_name
                )

                st.caption(
                    element.legal_question
                )

                c1, c2, c3, c4, c5 = (
                    st.columns(
                        5
                    )
                )

                c1.metric(
                    "Supporting",
                    len(
                        element.supporting_evidence_keys
                    ),
                )

                c2.metric(
                    "Adverse",
                    len(
                        element.adverse_evidence_keys
                    ),
                )

                c3.metric(
                    "Corroborative",
                    len(
                        element.corroborative_evidence_keys
                    ),
                )

                c4.metric(
                    "Conflicting",
                    len(
                        element.conflicting_evidence_keys
                    ),
                )

                c5.metric(
                    "Gaps",
                    len(
                        element.evidential_gap_ids
                    ),
                )

                st.write(
                    "**Current analytical status:** "
                    + element.analytical_status
                )

                st.caption(
                    "Confidence: "
                    + element.analytical_confidence
                )

                # ----------------------------------------------------------
                # WHY?
                # ----------------------------------------------------------

                with st.expander(
                    "WHY?",
                    expanded=False,
                ):

                    if element.provisional_analysis:

                        st.write(
                            "**Current analytical explanation**"
                        )

                        st.write(
                            element.provisional_analysis
                        )

                    _evidence_list(
                        "Supporting evidence",
                        element.supporting_evidence_keys,
                    )

                    _evidence_list(
                        "Adverse evidence",
                        element.adverse_evidence_keys,
                    )

                    _evidence_list(
                        "Corroborative evidence",
                        element.corroborative_evidence_keys,
                    )

                    _evidence_list(
                        "Conflicting evidence",
                        element.conflicting_evidence_keys,
                    )

                    _evidence_list(
                        "Neutral/contextual evidence",
                        element.neutral_evidence_keys,
                    )

                    st.markdown(
                        "**Unresolved matters - "
                        f"{len(element.unresolved_matters)}**"
                    )

                    if element.unresolved_matters:

                        for value in (
                            element.unresolved_matters
                        ):
                            st.write(
                                "? "
                                + value
                            )

                    else:
                        st.caption(
                            "None recorded."
                        )

                    st.markdown(
                        "**Evidential gaps - "
                        f"{len(element.evidential_gap_ids)}**"
                    )

                    if element.evidential_gap_ids:

                        for value in (
                            element.evidential_gap_ids
                        ):
                            st.code(
                                value,
                                language=None,
                            )

                    else:
                        st.caption(
                            "None recorded."
                        )

                # ----------------------------------------------------------
                # CURRENT RELATIONSHIP REVIEWS
                # ----------------------------------------------------------

                evidence_options = tuple(
                    sorted(
                        set(
                            element.supporting_evidence_keys
                            + element.adverse_evidence_keys
                            + element.corroborative_evidence_keys
                            + element.conflicting_evidence_keys
                            + element.neutral_evidence_keys
                        )
                    )
                )

                st.markdown(
                    "#### Relationship review"
                )

                relationships = (
                    element.relationships
                )

                if relationships:

                    for relationship in relationships:

                        with st.container(
                            border=True
                        ):

                            st.write(
                                "**"
                                + relationship.relationship_type.value
                                + "** - "
                                + relationship.state.value
                            )

                            st.code(
                                relationship.left_evidence_key
                                + "\n<->\n"
                                + relationship.right_evidence_key,
                                language=None,
                            )

                            st.write(
                                relationship.proposal_rationale
                            )

                            st.caption(
                                "Proposed/reviewed by: "
                                + relationship.actor
                            )

                            st.caption(
                                "Event time: "
                                + relationship.created_at
                            )

                            if relationship.review_note:

                                st.caption(
                                    "Review note: "
                                    + relationship.review_note
                                )

                            if (
                                relationship.state
                                is RelationshipReviewState.PROPOSED
                            ):

                                review_note = (
                                    st.text_area(
                                        "Optional review note",
                                        key=(
                                            "mal_review_note_"
                                            + relationship.relationship_id
                                        ),
                                        height=90,
                                    )
                                )

                                approve, reject = (
                                    st.columns(
                                        2
                                    )
                                )

                                if approve.button(
                                    "Approve",
                                    key=(
                                        "mal_approve_"
                                        + relationship.relationship_id
                                    ),
                                ):

                                    try:
                                        review_relationship(
                                            case_id=
                                                ledger.case_id,

                                            authority_id=
                                                ledger.authority_id,

                                            relationship_id=
                                                relationship.relationship_id,

                                            decision=
                                                RelationshipReviewState.APPROVED,

                                            review_note=
                                                review_note,
                                        )

                                    except MatterAnalysisLedgerError as exc:

                                        st.error(
                                            str(exc)
                                        )

                                    else:
                                        st.rerun()

                                if reject.button(
                                    "Reject",
                                    key=(
                                        "mal_reject_"
                                        + relationship.relationship_id
                                    ),
                                ):

                                    try:
                                        review_relationship(
                                            case_id=
                                                ledger.case_id,

                                            authority_id=
                                                ledger.authority_id,

                                            relationship_id=
                                                relationship.relationship_id,

                                            decision=
                                                RelationshipReviewState.REJECTED,

                                            review_note=
                                                review_note,
                                        )

                                    except MatterAnalysisLedgerError as exc:

                                        st.error(
                                            str(exc)
                                        )

                                    else:
                                        st.rerun()

                else:

                    st.caption(
                        "No relationship review "
                        "has been recorded for this element."
                    )

                # ----------------------------------------------------------
                # NEW PROPOSAL
                # ----------------------------------------------------------

                if len(evidence_options) >= 2:

                    form_key = (
                        "mal_proposal_"
                        + issue.issue_analysis_id
                        + "_"
                        + element.element_id
                    )

                    with st.form(
                        form_key
                    ):

                        st.markdown(
                            "**Propose a contradiction "
                            "or corroboration**"
                        )

                        relationship_type = (
                            st.selectbox(
                                "Relationship",
                                options=(
                                    RelationshipType.CONTRADICTS.value,
                                    RelationshipType.CORROBORATES.value,
                                ),
                            )
                        )

                        left = (
                            st.selectbox(
                                "Evidence item A",
                                evidence_options,
                            )
                        )

                        right = (
                            st.selectbox(
                                "Evidence item B",
                                evidence_options,
                                index=1,
                            )
                        )

                        rationale = (
                            st.text_area(
                                "Why are these evidence items related?",
                                height=120,
                            )
                        )

                        submitted = (
                            st.form_submit_button(
                                "Propose relationship"
                            )
                        )

                    if submitted:

                        if left == right:

                            st.warning(
                                "Choose two different "
                                "evidence items."
                            )

                        else:

                            try:
                                propose_relationship(
                                    case_id=
                                        ledger.case_id,

                                    authority_id=
                                        ledger.authority_id,

                                    issue_analysis_id=
                                        issue.issue_analysis_id,

                                    element_id=
                                        element.element_id,

                                    relationship_type=
                                        RelationshipType(
                                            relationship_type
                                        ),

                                    left_evidence_key=
                                        left,

                                    right_evidence_key=
                                        right,

                                    rationale=
                                        rationale,
                                )

                            except MatterAnalysisLedgerError as exc:

                                st.error(
                                    str(exc)
                                )

                            else:
                                st.rerun()

                else:

                    st.caption(
                        "At least two governed evidence items "
                        "are required before a relationship "
                        "can be proposed."
                    )


__all__ = [
    "show_matter_analysis_ledger",
]
