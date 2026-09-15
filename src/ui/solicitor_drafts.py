"""Matter-level Drafts register for LegalRAG Pro D2."""
from __future__ import annotations
from typing import Any
import streamlit as st
from drafting_working_draft import DraftingWorkingDraftError, load_working_drafts
from solicitor_tasks import SolicitorTaskError, load_tasks
from task_work_progress import TaskWorkProgressError, load_task_work_progress
from ui.case_operator import _render_drafting_workflow
from ui.solicitor_workflow import (
    clear_draft_handoff,
    current_draft_handoff,
    open_reports_for_approved_work_product,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _task_label(task: Any) -> str:
    for attr in ("title", "description", "question", "task_id"):
        value = _clean(getattr(task, attr, ""))
        if value:
            return value
    return "Matter task"


def _approved_draft_ids(case_id: str) -> set[str]:
    try:
        from drafting_approved_work_product import load_approved_working_draft_products
        products = tuple(load_approved_working_draft_products(case_id))
    except Exception:
        return set()
    return {
        _clean(getattr(product, "draft_id", ""))
        for product in products
        if _clean(getattr(product, "draft_id", ""))
    }


def _open_work(case_id: str, task_id: str) -> None:
    st.session_state["ux_d2_drafts_view"] = False
    st.session_state["ppr3_legal_issue_dashboard_view"] = True
    st.session_state["case_operator_workspace_case_id"] = case_id
    st.session_state.pop("mw1_task_workspace_case_id", None)
    st.session_state["case_operator_approved_task"] = task_id
    st.session_state["m6_workspace_view"] = None
    st.session_state["m7_source_evidence_view"] = False
    st.session_state["u8_evidence_inspection_view"] = False
    st.session_state["m55_main_view"] = "assistant"




def _render_wc2_draft_handoff(active_case_id: str, tasks: tuple[Any, ...]) -> bool:
    """Render one exact session handoff through the existing governed drafting UI."""
    handoff = current_draft_handoff(active_case_id)
    if handoff is None:
        return False

    task_id = _clean(handoff.get("task_id"))
    progress_id = _clean(handoff.get("progress_id"))
    task_matches = tuple(
        task
        for task in tasks
        if _clean(getattr(task, "task_id", "")) == task_id
    )
    if len(task_matches) != 1:
        st.error(
            "The drafting handoff no longer identifies one exact matter task. "
            "No draft has been generated or saved."
        )
        return True

    task = task_matches[0]
    try:
        history = tuple(load_task_work_progress(active_case_id, task_id))
    except TaskWorkProgressError as exc:
        st.error("Recorded task work could not be validated: " + str(exc))
        return True

    progress_matches = tuple(
        row
        for row in history
        if _clean(getattr(row, "progress_id", "")) == progress_id
    )
    if len(progress_matches) != 1:
        st.error(
            "The drafting handoff no longer identifies one exact recorded-work item. "
            "No draft has been generated or saved."
        )
        return True

    progress = progress_matches[0]
    st.subheader("Draft from recorded work")
    st.caption("This handoff identifies existing recorded task work only. Opening it does not generate, save, approve or release any wording.")
    st.markdown("**Related task**")
    st.write(_task_label(task))
    recorded_at = _clean(getattr(progress, "recorded_at", ""))
    if recorded_at:
        st.caption("Recorded work · " + recorded_at)

    _render_drafting_workflow(
        case_id=active_case_id,
        task=task,
        history=history,
    )

    if st.button(
        "Close drafting work",
        key="wc2_close_drafting::" + task_id + "::" + progress_id,
    ):
        clear_draft_handoff(active_case_id)
        st.rerun()
    return True




def _render_wc3_approved_report_handoffs(active_case_id: str) -> None:
    """Offer explicit Reports handoff for validated approved work products."""
    try:
        from drafting_approved_work_product import (
            DraftingApprovedWorkProductError,
            load_approved_working_draft_products,
        )
        products = tuple(load_approved_working_draft_products(active_case_id))
    except DraftingApprovedWorkProductError as exc:
        st.error("Approved work products could not be validated: " + str(exc))
        return

    if not products:
        return

    validated = []
    seen_drafts: set[str] = set()
    seen_targets: set[str] = set()
    for product in products:
        draft_id = _clean(getattr(product, "draft_id", ""))
        target_id = _clean(getattr(product, "target_id", ""))
        if (
            not draft_id
            or not target_id
            or draft_id in seen_drafts
            or target_id in seen_targets
        ):
            st.error(
                "Approved work products could not be presented because their exact "
                "professional-release identities are not unique."
            )
            return
        seen_drafts.add(draft_id)
        seen_targets.add(target_id)
        validated.append(product)

    st.subheader("Professionally approved work products")
    st.caption(
        "Open an approved work product in Reports as read-only professional context. "
        "This does not insert it into the frozen report or change its release status."
    )
    for product in validated:
        draft_id = _clean(getattr(product, "draft_id", ""))
        target_id = _clean(getattr(product, "target_id", ""))
        approved_at = _clean(getattr(product, "approved_at", ""))
        reviewer = _clean(getattr(product, "reviewer_reference", ""))
        with st.container(border=True):
            st.markdown("**Approved work product**")
            st.success("Approved for internal professional reliance")
            if bool(getattr(product, "court_or_tribunal_reliance", False)):
                st.warning("Approved for court or tribunal reliance")
            else:
                st.caption("Not approved for court or tribunal reliance")
            meta = []
            if reviewer:
                meta.append("Approved by " + reviewer)
            if approved_at:
                meta.append("Approved " + approved_at)
            if meta:
                st.caption(" · ".join(meta))
            if st.button(
                "Open approved work product in Reports",
                key=f"wc3_open_reports::{draft_id}::{target_id}",
                use_container_width=True,
            ):
                open_reports_for_approved_work_product(
                    active_case_id,
                    draft_id,
                    target_id,
                )
                st.rerun()


def show_drafts_workspace(active_case_id: str | None) -> None:
    st.title("Drafts")
    st.caption(
        "Saved working drafts and approved work products for this matter. "
        "AI-generated wording is not saved merely because it was generated."
    )
    if active_case_id is None or not str(active_case_id).strip():
        st.info("Select an active matter to view drafts.")
        return
    try:
        tasks = tuple(load_tasks(active_case_id))
    except SolicitorTaskError:
        st.error("Matter tasks could not be loaded safely.")
        return
    wc2_handoff_active = _render_wc2_draft_handoff(active_case_id, tasks)
    if wc2_handoff_active:
        st.divider()
        st.subheader("Matter draft register")
    _render_wc3_approved_report_handoffs(active_case_id)

    approved_ids = _approved_draft_ids(active_case_id)
    rows = []
    for task in tasks:
        task_id = _clean(getattr(task, "task_id", ""))
        if not task_id:
            continue
        try:
            drafts = tuple(load_working_drafts(active_case_id, task_id))
        except DraftingWorkingDraftError:
            continue
        rows.extend((task, draft) for draft in drafts)
    if not rows:
        st.info("No saved working drafts are recorded for this matter. Draft preparation begins from recorded task work.")
        return
    st.caption(f"{len(rows)} saved working draft(s)")
    for task, draft in reversed(rows):
        task_id = _clean(getattr(task, "task_id", ""))
        draft_id = _clean(getattr(draft, "draft_id", ""))
        title = _clean(getattr(draft, "title", "")) or "Working draft"
        recorded_at = _clean(getattr(draft, "recorded_at", ""))
        with st.container(border=True):
            st.markdown("**" + title + "**")
            st.caption(
                "Professionally approved work product"
                if draft_id in approved_ids
                else "Saved working draft · not approved for reliance"
            )
            if recorded_at:
                st.caption("Saved " + recorded_at)
            st.write("Case Operator task: " + _task_label(task))
            if task_id and st.button("Open in Case Operator", key=f"ux_d2_draft_work::{task_id}::{draft_id}"):
                _open_work(active_case_id, task_id)
                st.rerun()
    st.caption("Court or tribunal reliance remains a separate governed decision from saving or internal professional approval.")
