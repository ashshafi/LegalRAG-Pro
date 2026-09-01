"""Streamlit inbox for PRW1 professional review of published CAA observations."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from controlled_agentic_analysis import AgentObservation
from controlled_agentic_analysis_gaps import GapAgentObservation
from controlled_agentic_analysis_review import (
    ProfessionalReviewDecision,
    ProfessionalReviewError,
    ProfessionalReviewState,
    review_agent_observation,
)
from controlled_agentic_analysis_review_inbox import (
    ProfessionalReviewInboxError,
    ProfessionalReviewInboxItem,
    load_professional_review_inbox,
)
from controlled_agentic_analysis_review_publication import (
    ProfessionalReviewPublicationError,
    publish_professional_review_event,
)
from governed_analytical_authority.provider import (
    load_active_governed_analytical_authority,
)


PRW2_UI_VERSION = "controlled-agentic-professional-review-inbox-ui/v1"


def _decision_label(value: ProfessionalReviewDecision) -> str:
    return {
        ProfessionalReviewDecision.DEFER:
            "Defer",
        ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION:
            "Accept for MAL1 consideration",
        ProfessionalReviewDecision.REJECT:
            "Reject",
    }[value]


def _state_label(item: ProfessionalReviewInboxItem) -> str:
    projection = item.review_projection
    if projection is None:
        return "UNREVIEWED"
    return projection.state.value


def _evidence_rows(
    observation: AgentObservation | GapAgentObservation,
) -> tuple[tuple[str, str, str], ...]:
    if isinstance(observation, AgentObservation):
        rows = [
            (
                "SUPPORTING",
                ref.evidence_key,
                ref.evidence_binding_sha256,
            )
            for ref in observation.supporting_evidence_bindings
        ]
        rows.extend(
            (
                "CONTRARY",
                ref.evidence_key,
                ref.evidence_binding_sha256,
            )
            for ref in observation.contrary_evidence_bindings
        )
        return tuple(rows)

    if isinstance(observation, GapAgentObservation):
        return tuple(
            (
                "INSPECTED",
                ref.evidence_key,
                ref.evidence_binding_sha256,
            )
            for ref in observation.inspected_evidence_bindings
        )

    return ()


def _render_observation_record(
    item: ProfessionalReviewInboxItem,
) -> None:
    observation = item.observation

    st.write("**" + observation.title + "**")
    st.caption(
        "Source agent: "
        + item.source_agent.value
        + " | Review state: "
        + _state_label(item)
        + " | Materiality: "
        + observation.materiality.value.upper()
        + " | Observation confidence: "
        + observation.observation_confidence.value.upper()
    )

    if observation.issue_analysis_id:
        coordinates = "Issue: " + observation.issue_analysis_id
        if observation.element_id:
            coordinates += " | Focus area: " + observation.element_id
        st.caption(coordinates)

    st.write(observation.summary)

    st.write("**Source-bound reasoning summary**")
    st.write(observation.reasoning_summary)

    st.write("**Uncertainty**")
    st.write(observation.uncertainty)

    if observation.limitations:
        st.write("**Limitations**")
        for limitation in observation.limitations:
            st.write("- " + limitation)

    st.caption(
        "Agent recommendation: "
        + observation.recommended_action.value
        + ". Agent recommendations are not authority and do not create "
        "analytical-change proposals."
    )

    evidence_rows = _evidence_rows(observation)
    st.write("**Bound evidence references**")
    if not evidence_rows:
        st.caption("No evidence references were recorded.")
    else:
        for role, evidence_key, binding_id in evidence_rows:
            st.caption(role + ": " + evidence_key)
            st.code(binding_id, language=None)

    st.caption(
        "Observation ID: "
        + observation.observation_id
        + " | Analysis run: "
        + item.run.analysis_run_id
    )


def _render_review_history(
    item: ProfessionalReviewInboxItem,
) -> None:
    if not item.review_events:
        st.caption("No professional review event has yet been recorded.")
        return

    st.write("**Professional review history**")
    for event in item.review_events:
        st.caption(
            event.reviewed_at_utc
            + " | "
            + event.decision.value
            + " | "
            + event.reviewer_reference
        )
        st.write(event.reviewer_note)


def _render_terminal_result(
    item: ProfessionalReviewInboxItem,
) -> None:
    projection = item.review_projection
    if projection is None:
        return

    if (
        projection.state
        is ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION
    ):
        st.success(
            "ACCEPTED FOR MAL1 CONSIDERATION. This is review eligibility only; "
            "no MAL1 proposal has been created or approved."
        )
    elif projection.state is ProfessionalReviewState.REJECTED:
        st.info(
            "REJECTED BY PROFESSIONAL REVIEW. No MAL1 proposal has been created."
        )


def _is_duplicate_review_submission(
    *,
    item: ProfessionalReviewInboxItem,
    decision: ProfessionalReviewDecision,
    reviewer_reference: str,
    reviewer_note: str,
) -> bool:
    """Return True only for an exact repeat of the latest recorded review."""

    if not item.review_events:
        return False

    latest = item.review_events[-1]
    return (
        latest.decision == decision
        and latest.reviewer_reference.strip() == reviewer_reference.strip()
        and latest.reviewer_note.strip() == reviewer_note.strip()
    )


def _review_controls(
    *,
    item: ProfessionalReviewInboxItem,
) -> None:
    observation = item.observation
    suffix = observation.observation_id[7:23]

    with st.form(
        key="prw2_form_" + suffix,
        clear_on_submit=False,
    ):
        reviewer_reference = st.text_input(
            "Reviewer reference",
            key="prw2_reviewer_" + suffix,
            help=(
                "Record the professional reviewer identity or internal reviewer "
                "reference used for this decision."
            ),
        )

        reviewer_note = st.text_area(
            "Professional review note",
            height=120,
            key="prw2_note_" + suffix,
            help=(
                "Record the professional basis for deferring, accepting for MAL1 "
                "consideration, or rejecting this observation."
            ),
        )

        decision = st.selectbox(
            "Professional review decision",
            tuple(ProfessionalReviewDecision),
            format_func=_decision_label,
            key="prw2_decision_" + suffix,
        )

        st.caption(
            "ACCEPT_FOR_MAL1_CONSIDERATION does not create a MAL1 proposal, "
            "does not approve a MAL1 proposal, and does not change governed authority."
        )

        submitted = st.form_submit_button(
            "RECORD PROFESSIONAL REVIEW",
            use_container_width=True,
        )

    if not submitted:
        return

    if not reviewer_reference.strip():
        st.warning("Enter a reviewer reference before recording review.")
        return
    if not reviewer_note.strip():
        st.warning("Enter a professional review note before recording review.")
        return

    if _is_duplicate_review_submission(
        item=item,
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
    ):
        st.warning(
            "This review is identical to the most recent recorded review. "
            "No new professional review event was created."
        )
        return

    reviewed_at_utc = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        event = review_agent_observation(
            run=item.run,
            observation=observation,
            decision=decision,
            reviewer_reference=reviewer_reference,
            reviewer_note=reviewer_note,
            reviewed_at_utc=reviewed_at_utc,
            existing_events=item.review_events,
        )
        publish_professional_review_event(event=event)
    except (
        ProfessionalReviewError,
        ProfessionalReviewPublicationError,
    ) as exc:
        st.error("Professional review failed closed.")
        st.caption(str(exc))
        return

    st.success("Professional review event recorded.")
    st.rerun()


def show_professional_review_inbox(
    active_case_id: str | None,
) -> None:
    """Render published CAA observations and PRW1 review controls."""

    if active_case_id is None:
        return

    try:
        authority = load_active_governed_analytical_authority(
            active_case_id
        )
    except Exception as exc:
        st.error(
            "Professional review inbox could not load the active governed authority."
        )
        st.caption(str(exc))
        return

    if authority is None:
        return

    try:
        items = load_professional_review_inbox(
            case_id=active_case_id,
        )
    except ProfessionalReviewInboxError as exc:
        st.error("Professional review inbox failed closed.")
        st.caption(str(exc))
        return

    current_authority_id = authority.manifest.authority_id

    pending = tuple(
        item
        for item in items
        if (
            item.run.active_authority_id == current_authority_id
            and (
                item.review_projection is None
                or item.review_projection.state
                is ProfessionalReviewState.DEFERRED
            )
        )
    )
    terminal = tuple(
        item
        for item in items
        if (
            item.review_projection is not None
            and item.review_projection.state
            in {
                ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION,
                ProfessionalReviewState.REJECTED,
            }
        )
    )
    stale = tuple(
        item
        for item in items
        if (
            item.run.active_authority_id != current_authority_id
            and item not in terminal
        )
    )

    st.divider()
    with st.expander(
        "Controlled Agent Professional Review Inbox"
        + (" (" + str(len(pending)) + " pending)" if pending else ""),
        expanded=bool(pending),
    ):
        st.caption(
            "PRW2 surfaces immutable CAA observations for explicit human review. "
            "Review decisions are append-only PRW1 events. Acceptance means only "
            "eligibility for separately authored MAL1 consideration."
        )
        st.caption(
            "Current governed authority: " + current_authority_id
        )

        if not items:
            st.info(
                "No published controlled-agent observations are available for "
                "professional review."
            )
            return

        st.caption(
            "Pending/deferred: "
            + str(len(pending))
            + " | Terminal reviewed: "
            + str(len(terminal))
            + " | Prior-authority pending: "
            + str(len(stale))
        )

        for index, item in enumerate(pending, 1):
            with st.container(border=True):
                st.markdown(
                    "#### Review item " + str(index)
                )
                _render_observation_record(item)
                _render_review_history(item)
                _review_controls(item=item)

        if stale:
            st.warning(
                "Some published observations are bound to a prior governed "
                "authority. New review decisions are disabled for those records."
            )
            for item in stale:
                with st.container(border=True):
                    _render_observation_record(item)
                    _render_review_history(item)
                    st.caption(
                        "REVIEW DISABLED: observation authority "
                        + item.run.active_authority_id
                        + " is not the current authority."
                    )

        if terminal:
            st.markdown("### Reviewed observations")
            for item in terminal:
                with st.container(border=True):
                    _render_observation_record(item)
                    _render_review_history(item)
                    _render_terminal_result(item)


__all__ = [
    "PRW2_UI_VERSION",
    "show_professional_review_inbox",
]
