"""Bounded solicitor-facing report centre over the frozen report projection."""
from __future__ import annotations

from typing import Any

import streamlit as st
import ui.reports as base

from ui.solicitor_shell import route_solicitor_view
from ui.solicitor_workflow import (
    clear_report_handoff,
    current_report_handoff,
)

_HEAVY_SECTIONS = {"chronology", "evidence_appendix"}


def _plain(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _status(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("label", "raw_value", "value"):
        text = _plain(getattr(value, attr, None))
        if text:
            return text
    return _plain(value)


def _metric(label: str, value: int) -> None:
    st.metric(label, value)


def _case_assessment(projection: Any) -> None:
    issues = tuple(getattr(projection, "issues", ()) or ())
    chronology = tuple(getattr(projection, "chronology", ()) or ())
    citations = tuple(getattr(projection, "citations", ()) or ())
    conflicts = tuple(getattr(projection, "conflicts", ()) or ())
    gaps = tuple(getattr(projection, "gaps", ()) or ())
    risks = tuple(getattr(projection, "risks", ()) or ())
    questions = tuple(getattr(projection, "priority_questions", ()) or ())

    st.markdown("### Case assessment")
    st.caption("A concise working view of the frozen report projection. Full audit material remains available section by section.")
    cols = st.columns(4)
    with cols[0]: _metric("Issues", len(issues))
    with cols[1]: _metric("Chronology", len(chronology))
    with cols[2]: _metric("Evidence citations", len(citations))
    with cols[3]: _metric("Open questions", len(questions))

    if issues:
        st.markdown("#### Current issue positions")
        for issue in issues:
            with st.container(border=True):
                name = _plain(getattr(issue, "issue_name", None)) or "Legal issue"
                st.markdown("**" + name + "**")
                summary = _plain(getattr(issue, "issue_summary", None))
                if summary:
                    st.write(summary)
                meta = []
                position = _status(getattr(issue, "position_status", None))
                confidence = _status(getattr(issue, "confidence", None))
                if position: meta.append("Position: " + position)
                if confidence: meta.append("Confidence: " + confidence)
                if meta: st.caption(" · ".join(meta))
    else:
        st.info("No issue assessments are available in this report projection.")

    with st.expander("Analytical inventory", expanded=False):
        st.write(f"Conflicts: {len(conflicts)}")
        st.write(f"Evidence gaps: {len(gaps)}")
        st.write(f"Risk areas: {len(risks)}")
        st.write(f"Priority questions: {len(questions)}")


def _chronology_summary(active_case_id: str, projection: Any) -> None:
    events = tuple(getattr(projection, "chronology", ()) or ())
    st.markdown("### Chronology")
    st.caption(f"{len(events)} frozen chronology event(s). The working chronology is paged to keep the matter navigable.")
    for event in events[:8]:
        extent = getattr(event, "canonical_temporal_extent", None)
        when = _plain(getattr(extent, "display_text", None)) if extent is not None else ""
        desc = _plain(getattr(event, "description", None)) or "Chronology event"
        st.write("• " + (when + " — " if when else "") + desc)
    if len(events) > 8:
        st.caption(f"Showing 8 of {len(events)} here.")
    if st.button("Open paged Chronology", key="ux_r6_reports_open_chronology"):
        route_solicitor_view("Chronology", case_id=active_case_id)
        st.rerun()


def _evidence_summary(active_case_id: str, projection: Any) -> None:
    citations = tuple(getattr(projection, "citations", ()) or ())
    documents = tuple(dict.fromkeys(_plain(getattr(item, "document_name", None)) for item in citations if _plain(getattr(item, "document_name", None))))
    st.markdown("### Evidence")
    st.caption(f"{len(citations)} frozen evidence citation(s) across {len(documents)} recorded document name(s).")
    for name in documents[:10]:
        st.write("• " + name)
    if len(documents) > 10:
        st.caption(f"Showing 10 of {len(documents)} document names here.")
    if st.button("Open paged Evidence", key="ux_r6_reports_open_evidence"):
        route_solicitor_view("Evidence", case_id=active_case_id)
        st.rerun()


def _full_audit_one_section(projection: Any, ordinals: dict[str, int]) -> None:
    st.markdown("### Full audit")
    st.warning(
        "Audit-grade sections can be large. LegalRAG now renders only one selected section at a time; "
        "Chronology and Evidence Appendix require an explicit Render action."
    )
    section_ids = tuple(getattr(getattr(projection, "manifest", None), "ordered_section_ids", ()) or ())
    if not section_ids:
        st.info("No audit sections are available.")
        return
    selected = st.selectbox(
        "Audit section",
        options=section_ids,
        key="ux_r6_audit_section",
        format_func=lambda value: str(value).replace("_", " ").title(),
    )
    rendered_key = "ux_r6_rendered_audit_section"
    if st.button("Render selected audit section", type="primary", key="ux_r6_render_audit_section"):
        st.session_state[rendered_key] = selected
    if st.session_state.get(rendered_key) != selected:
        if selected in _HEAVY_SECTIONS:
            st.info("This section is intentionally not rendered until you choose Render selected audit section.")
        return
    # One-shot authorisation: a later rerun must not unexpectedly re-render a
    # massive section merely because the prior selection remains in session.
    st.session_state.pop(rendered_key, None)
    base._render_section(selected, projection, ordinals)



def _render_wc3_approved_work_product_handoff(active_case_id: str) -> bool:
    """Render exact approved work-product context beside, not inside, the report projection."""
    handoff = current_report_handoff(active_case_id)
    if handoff is None:
        return False
    draft_id = _plain(handoff.get("draft_id"))
    target_id = _plain(handoff.get("target_id"))
    try:
        from drafting_approved_work_product import (
            DraftingApprovedWorkProductError,
            load_approved_working_draft_products,
        )
        products = tuple(load_approved_working_draft_products(active_case_id))
    except DraftingApprovedWorkProductError as exc:
        st.error("Approved work products could not be validated: " + str(exc))
        return True
    matches = tuple(
        product
        for product in products
        if _plain(getattr(product, "draft_id", "")) == draft_id
        and _plain(getattr(product, "target_id", "")) == target_id
    )
    if len(matches) != 1:
        st.error(
            "The Reports handoff no longer identifies one exact approved work product. "
            "The frozen report has not been changed."
        )
        return True
    product = matches[0]
    with st.container(border=True):
        st.markdown("### Approved work product")
        st.caption(
            "Selected from Drafts as read-only professional context. "
            "It has not been inserted into or merged with the frozen report projection."
        )
        st.success("Approved for internal professional reliance")
        if bool(getattr(product, "court_or_tribunal_reliance", False)):
            st.warning("Approved for court or tribunal reliance")
        else:
            st.caption("Not approved for court or tribunal reliance")
        approved_at = _plain(getattr(product, "approved_at", ""))
        reviewer = _plain(getattr(product, "reviewer_reference", ""))
        if approved_at or reviewer:
            meta = []
            if reviewer:
                meta.append("Approved by " + reviewer)
            if approved_at:
                meta.append("Approved " + approved_at)
            st.caption(" · ".join(meta))
        wording = tuple(getattr(product, "approved_wording", ()) or ())
        if wording:
            st.markdown("**Approved wording**")
            for paragraph in wording:
                text = _plain(paragraph)
                if text:
                    st.write(text)
        if st.button(
            "Close approved work-product context",
            key="wc3_close_report_context::" + draft_id + "::" + target_id,
        ):
            clear_report_handoff(active_case_id)
            st.rerun()
    return True


def show_solicitor_report_center(
    active_case_id: str | None,
    projection: Any | None,
    *,
    provider_error: Exception | None = None,
) -> None:
    st.markdown(
        '<div class="lr-report-title">Reports</div>'
        '<div class="lr-report-subtitle">Professional matter outputs from the current governed case record.</div>',
        unsafe_allow_html=True,
    )
    if active_case_id is None:
        st.info("Select an active matter to view reports.")
        return
    if provider_error is not None:
        st.error(base.INVALID_PROJECTION_TEXT)
        return
    if projection is None:
        st.info("No validated report is available for this matter.")
        return
    try:
        base.validate_case_report_projection(projection)
        if projection.case_header.case_id != active_case_id:
            raise ValueError("Report projection case ID does not match active case ID.")
        base._preflight_native_presentation(projection)
    except Exception as exc:
        base.LOGGER.error(
            "R6 solicitor report-centre validation failed for case %s error %s.",
            active_case_id,
            type(exc).__name__,
        )
        st.error(base.INVALID_PROJECTION_TEXT)
        return

    wc3_handoff_active = _render_wc3_approved_work_product_handoff(active_case_id)
    if wc3_handoff_active:
        st.divider()

    selected_view = st.segmented_control(
        "Report view",
        ("Case assessment", "Chronology", "Evidence", "Full audit"),
        selection_mode="single",
        required=True,
        default="Case assessment",
        key="ux_r6_report_view",
        label_visibility="collapsed",
        width="stretch",
    ) or "Case assessment"

    ordinals = base._citation_ordinals(projection)
    if selected_view == "Case assessment":
        _case_assessment(projection)
    elif selected_view == "Chronology":
        _chronology_summary(active_case_id, projection)
    elif selected_view == "Evidence":
        _evidence_summary(active_case_id, projection)
    else:
        _full_audit_one_section(projection, ordinals)

    with st.expander("Technical report details", expanded=False):
        available = set(projection.manifest.ordered_section_ids)
        if "report_header" in available:
            base._render_section("report_header", projection, ordinals)
        if "analytical_lineage" in available:
            st.divider()
            base._render_section("analytical_lineage", projection, ordinals)

    with st.expander("Export report", expanded=False):
        base._export_panel(active_case_id, projection)


__all__ = ["show_solicitor_report_center"]
