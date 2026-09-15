"""Solicitor-facing audit gateway preserving frozen projection limitations."""
from __future__ import annotations

from typing import Any

import streamlit as st
import ui.source_evidence as base

from ui.solicitor_shell import route_solicitor_view


def show_solicitor_audit(active_case_id: str | None, projection: Any | None) -> None:
    st.markdown("## Audit & provenance")
    st.caption(
        "Historical projection drill-down is shown exactly where the frozen projection proves it. "
        "If an older projection has no evidence-binding manifest, LegalRAG does not reconstruct or invent one."
    )
    if active_case_id is not None:
        if st.button("Open current governed Documents", key="ux_r6_audit_open_documents"):
            route_solicitor_view("Documents", case_id=active_case_id)
            st.rerun()
        st.caption(
            "Current governed document inspection is separate from historical projection binding and does not repair a missing frozen manifest."
        )
    base.show_source_evidence(active_case_id, projection)


__all__ = ["show_solicitor_audit"]
