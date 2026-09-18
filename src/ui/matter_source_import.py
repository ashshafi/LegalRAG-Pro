"""Solicitor-facing Import / Sync workspace for external practice-management matters."""

from __future__ import annotations

import os

import streamlit as st

from authentication import current_user_identity
from case_management import CaseRepository
from matter_sources.fake import FakeMatterSourceConnector
from matter_sources.models import ExternalDocument, ExternalMatter, ExternalParty, ProviderIdentity, SyncDisposition
from matter_sources.registry import MatterSourceRegistry, MatterSourceRegistryError
from matter_sources.sync import MatterSourceSyncError, apply_pdf_sync_plan, build_sync_plan


_FAKE_FLAG = "LEGALRAG_LEAP_FAKE_PILOT"


def _fake_pdf_bytes(label: str) -> bytes:
    """Return a tiny structurally valid one-page PDF for local fake-provider testing."""
    safe = label.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("ascii", errors="replace")
    objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii"))
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def _fake_connector() -> FakeMatterSourceConnector:
    provider = ProviderIdentity(provider="leap", firm_id="fake-leap-firm")
    matters = (
        ExternalMatter(
            source_matter_id="fake-matter-001",
            matter_reference="LEAP-DEMO-001",
            title="Smith v Hospital Trust",
            practice_area="Clinical negligence",
            status="Open",
        ),
        ExternalMatter(
            source_matter_id="fake-matter-002",
            matter_reference="LEAP-DEMO-002",
            title="Jones Road Traffic Claim",
            practice_area="Personal injury",
            status="Open",
        ),
    )
    parties = (
        ExternalParty(
            source_party_id="fake-party-001",
            source_matter_id="fake-matter-001",
            display_name="Jane Smith",
            party_role="Client",
            person_or_organisation="person",
        ),
    )
    docs = (
        ExternalDocument(
            source_document_id="fake-doc-001",
            source_matter_id="fake-matter-001",
            display_name="Letter of instruction.pdf",
            media_type="application/pdf",
            source_version_id="v1",
        ),
        ExternalDocument(
            source_document_id="fake-doc-002",
            source_matter_id="fake-matter-001",
            display_name="Medical chronology.pdf",
            media_type="application/pdf",
            source_version_id="v1",
        ),
    )
    return FakeMatterSourceConnector(
        provider=provider,
        matters=matters,
        parties=parties,
        documents=docs,
        content={
            "fake-doc-001": _fake_pdf_bytes("Fake LEAP letter of instruction"),
            "fake-doc-002": _fake_pdf_bytes("Fake LEAP medical chronology"),
        },
    )


def _enabled() -> bool:
    return os.getenv(_FAKE_FLAG, "").strip() == "1"


def show_matter_source_import(active_case_id: str | None) -> None:
    """Render a compact LEAP-first Import / Sync workspace in the sidebar."""
    with st.sidebar.expander("Import / Sync", expanded=False):
        st.markdown("**LEAP**")
        st.caption(
            "Bring an existing practice-management matter into LegalRAG for deeper "
            "evidence analysis without replacing LEAP."
        )

        if active_case_id is None:
            st.info("Select a LegalRAG matter before importing or synchronising.")
            return

        if not _enabled():
            st.info("LEAP developer access is pending.")
            st.caption(
                "The connector boundary and sync workflow are installed. "
                "Real LEAP authentication and API calls remain disabled until LEAP approves developer access."
            )
            return

        st.warning("Fake LEAP pilot data is enabled. No LEAP network connection is being used.")

        connector = _fake_connector()
        matters = connector.list_matters()
        labels = {
            matter.source_matter_id: f"{matter.matter_reference} — {matter.title}"
            for matter in matters
        }
        selected_id = st.selectbox(
            "LEAP matter",
            options=tuple(labels),
            format_func=lambda value: labels[value],
            key=f"leap_fake_matter::{active_case_id}",
        )
        matter = connector.get_matter(selected_id)
        provider = connector.provider_identity()
        registry = MatterSourceRegistry()
        previous = registry.load_observations(provider, selected_id)

        try:
            plan = build_sync_plan(
                connector,
                source_matter_id=selected_id,
                previous=previous,
            )
        except Exception:
            st.error("The external matter could not be inspected safely.")
            return

        counts = plan.counts()
        st.caption(
            f"{counts[SyncDisposition.NEW]} new · "
            f"{counts[SyncDisposition.UNCHANGED]} unchanged · "
            f"{counts[SyncDisposition.CHANGED]} changed · "
            f"{counts[SyncDisposition.UNAVAILABLE]} unavailable"
        )

        changed = (
            counts[SyncDisposition.NEW]
            + counts[SyncDisposition.CHANGED]
            + counts[SyncDisposition.UNAVAILABLE]
        )
        if changed == 0:
            st.success("No external source changes detected.")
            return

        st.caption("Importing does not change Current Assessment or professional approval state.")

        confirmed = st.checkbox(
            "I confirm this LEAP matter corresponds to the selected LegalRAG matter.",
            key=f"leap_fake_confirm::{active_case_id}::{selected_id}",
        )
        if not st.button(
            "Import / Sync matter",
            use_container_width=True,
            disabled=not confirmed,
            key=f"leap_fake_sync::{active_case_id}::{selected_id}",
        ):
            return

        try:
            access = CaseRepository().require_access(
                current_user_identity(),
                active_case_id,
            )
            applied = apply_pdf_sync_plan(
                connector,
                plan=plan,
                case_id=active_case_id,
                access=access,
                docs_folder="docs",
            )
            registry.record_successful_sync(
                provider=provider,
                source_matter_id=selected_id,
                case_id=active_case_id,
                matter_reference=matter.matter_reference,
                title=matter.title,
                plan=plan,
            )
        except (MatterSourceSyncError, MatterSourceRegistryError, Exception):
            st.error("The matter was not synchronised. Existing matter state was preserved.")
            return

        st.success(f"Synchronised {len(applied)} new or changed PDF source document(s).")
        st.rerun()


__all__ = ["show_matter_source_import"]
