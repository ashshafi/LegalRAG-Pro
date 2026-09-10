from __future__ import annotations

import os

import streamlit as st

from config import openai_client
from marriage_document_extraction import (
    OpenAIMarriageFactExtractionProvider,
)
from marriage_document_live import (
    LiveMarriageDocumentError,
    build_live_marriage_document_workspace,
    discover_approved_marriage_candidate_bundles,
    live_marriage_candidate_fingerprint,
)
from ui.marriage_document_workspace import (
    show_marriage_document_workspace,
)


_MODEL = (
    os.getenv(
        "LEGALRAG_INTERACTIVE_CHAT_MODEL",
        "gpt-5.6-terra",
    ).strip()
    or "gpt-5.6-terra"
)

_CACHE_WORKSPACE = "mdi_live_workspace"
_CACHE_FINGERPRINT = "mdi_live_workspace_fingerprint"
_CACHE_CASE = "mdi_live_workspace_case_id"


def _clear_cached_review() -> None:
    for key in (
        _CACHE_WORKSPACE,
        _CACHE_FINGERPRINT,
        _CACHE_CASE,
    ):
        st.session_state.pop(key, None)


def show_marriage_document_entrypoint(
    active_case_id: str | None,
) -> None:
    if active_case_id is None:
        st.info(
            "Select an active matter to review a Nikah Nama."
        )
        return

    try:
        bundles = discover_approved_marriage_candidate_bundles(
            active_case_id
        )
    except LiveMarriageDocumentError as exc:
        st.error(
            "The approved marriage-document material could not be loaded: "
            + str(exc)
        )
        return

    if not bundles:
        st.title("Nikah Nama review")
        st.info(
            "No currently approved Nikah Nama or marriage-document "
            "transcription fragments are available for this matter."
        )
        return

    fingerprint = live_marriage_candidate_fingerprint(bundles)

    cached_case = st.session_state.get(_CACHE_CASE)
    cached_fingerprint = st.session_state.get(
        _CACHE_FINGERPRINT
    )

    if (
        cached_case != active_case_id
        or cached_fingerprint != fingerprint
    ):
        _clear_cached_review()

    workspace = st.session_state.get(_CACHE_WORKSPACE)

    if workspace is None:
        st.title("Nikah Nama review")
        source_names = sorted(
            {
                bundle.candidate.original_filename
                for bundle in bundles
            }
        )
        st.caption(
            "Approved source: "
            + " / ".join(source_names)
        )
        st.write(
            "LegalRAG will read the currently approved document "
            "fragments and prepare the solicitor review."
        )

        generate = st.button(
            "Generate review",
            type="primary",
            width="stretch",
        )
        if not generate:
            return

        try:
            with st.spinner(
                "Reading the approved Nikah Nama sections..."
            ):
                provider = OpenAIMarriageFactExtractionProvider(
                    client=openai_client
                )
                workspace = build_live_marriage_document_workspace(
                    bundles=bundles,
                    provider=provider,
                    model=_MODEL,
                )
        except Exception as exc:
            st.error(
                "The Nikah Nama review could not be generated: "
                + str(exc)
            )
            return

        st.session_state[_CACHE_WORKSPACE] = workspace
        st.session_state[_CACHE_FINGERPRINT] = fingerprint
        st.session_state[_CACHE_CASE] = active_case_id
        st.rerun()
        return

    show_marriage_document_workspace(workspace)

    if st.button(
        "Refresh from approved document sections",
        width="stretch",
    ):
        _clear_cached_review()
        st.rerun()


__all__ = ["show_marriage_document_entrypoint"]
