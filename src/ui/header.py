"""LegalRAG Pro D4 masthead."""
from __future__ import annotations
import streamlit as st

def show_header() -> None:
    st.markdown(
        '<div class="lr-appbar"><div class="lr-brand"><span class="lr-brand-mark">LR</span>'
        '<div><div class="lr-brand-name">LegalRAG Pro</div>'
        '<div class="lr-brand-meta">Auditable Case Intelligence</div></div></div>'
        '<div class="lr-appbar-right">Professional matter workspace</div></div>',
        unsafe_allow_html=True,
    )

__all__=["show_header"]
