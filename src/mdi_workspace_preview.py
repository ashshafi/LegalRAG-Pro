from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from candidate_transcription import (
    CandidateTranscriptionStore,
    TranscriptionReviewEventStore,
    TranscriptionReviewState,
)
from candidate_transcription.review import project_transcription_review
from candidate_transcription.crop_lineage import (
    loads_candidate_crop_lineage_binding,
)
from candidate_transcription.targeted_publication import (
    loads_targeted_candidate_publication_receipt,
)
from marriage_document_intelligence import (
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
    MarriagePotentialIssue,
    SourceRegion,
)
from marriage_document_workspace import build_marriage_document_workspace
from ui.marriage_document_workspace import show_marriage_document_workspace


st.set_page_config(
    page_title="Nikah Nama review",
    page_icon="âš–ï¸",
    layout="wide",
)

BASE = Path(
    os.getenv(
        "LEGALRAG_MDI_CANDIDATE_BASE",
        str(
            Path(os.environ["LOCALAPPDATA"])
            / "LegalRAG-Pro"
            / "candidate_transcription"
            / "v1"
        ),
    )
)

SNAPSHOT = {
    "sha256:6fc25ac8d434a68cfff6401ebe2ed4fe120fb1dd368fdedfe389ea5ee4ca180f": {
        "transcription_sha256": "c663faccfb09a1c4827e5b2c0458f81ef83613762e47b1f12d6958a268611dbe",
        "review_event_id": "sha256:fa0e3db7483e07f523e1ae1caa5fb0876e98e9e55aa6e249031a725b3af262f4",
        "lineage_rel": "crop_lineage_store/candidate_crop_lineage/6fc25ac8d434a68cfff6401ebe2ed4fe120fb1dd368fdedfe389ea5ee4ca180f/1169994a1ab598c62616bdf5c857fa2fafbee6e40121c34c9df23448142df571.json",
        "receipt_rel": "targeted_publication_receipt_store/targeted_candidate_publication_receipts/6fc25ac8d434a68cfff6401ebe2ed4fe120fb1dd368fdedfe389ea5ee4ca180f/b0d9afbb8d8e3b8dc2490c90e7fcf2e6eb4b053c713f38bf2b4e21b4da4fe332.json",
        "facts": (
            ("additional_date", "02/10/09", "Date is legible but its purpose and numeric date order are unclear."),
            ("document_language_mix", "English and Urdu", "The fragment contains English text and Urdu numbered entries."),
        ),
        "issues": (
            "The date 02/10/09 is not linked to a particular event in the approved transcription.",
            "The English authority/locality fragments are incomplete.",
        ),
        "actions": (
            "Verify what event the date 02/10/09 relates to against the original document.",
        ),
    },
    "sha256:70aacfb22b1063602efc6092f17cf4d3a844e54299931db520d5c45f07253968": {
        "transcription_sha256": "8b9d918ff424246e24c7485173261faebfa2d19d111eb44b8f2f7a5a50cb64ff",
        "review_event_id": "sha256:0d92dc70858bf3331c3804d144b76c93b36e61c7a2ec86d5cb041349c42d4ced",
        "lineage_rel": "crop_lineage_store/candidate_crop_lineage/70aacfb22b1063602efc6092f17cf4d3a844e54299931db520d5c45f07253968/c923cdd3bd57852600853d58657d5536e2fe1a3178a79c15f36ffaa987a4ffa0.json",
        "receipt_rel": "targeted_publication_receipt_store/targeted_candidate_publication_receipts/70aacfb22b1063602efc6092f17cf4d3a844e54299931db520d5c45f07253968/d5e1af8212b5ef4d36a47d203bb05276d737c586822fe1eff8bc0461fcaf1b38.json",
        "facts": (
            ("special_condition", "18Û” Ø¢ÛŒØ§ Ø´ÙˆÛØ± Ù†Û’ Ø¨ÛŒÙˆÛŒ Ú©Ùˆ Ø·Ù„Ø§Ù‚ Ú©Ø§ Ø­Ù‚ ØªÙÙˆÛŒØ¶ Ú©ÛŒØ§ ÛÛ’ØŒ Ø§Ú¯Ø± Ú©ÛŒØ§ ÛÛ’ ØªÙˆ Ú©Ù† Ø´Ø±Ø§Ø¦Ø· Ú©Û’ ØªØ­ØªÛ” Ù†ÛÛŒÚº", "Recorded answer is 'No'."),
            ("special_condition", "19Û” Ø¢ÛŒØ§ Ø´ÙˆÛØ± Ú©Û’ Ø­Ù‚ Ø·Ù„Ø§Ù‚ Ù¾Ø± Ú©Ø³ÛŒ Ù‚Ø³Ù… Ú©ÛŒ Ù¾Ø§Ø¨Ù†Ø¯ÛŒ Ù„Ú¯Ø§Ø¦ÛŒ Ú¯Ø¦ÛŒ ÛÛ’Û” Ù†ÛÛŒÚº", "Recorded answer is 'No'."),
            ("special_condition", "20Û” Ø¢ÛŒØ§ Ø´Ø§Ø¯ÛŒ Ú©Û’ Ù…ÙˆÙ‚Ø¹ Ù¾Ø± Ù…ÛØ± Ùˆ Ù†ÙÙ‚Û ÙˆØºÛŒØ±Û Ø³Û’ Ù…ØªØ¹Ù„Ù‚ Ú©ÙˆØ¦ÛŒ Ø¯Ø³ØªØ§ÙˆÛŒØ² ØªÛŒØ§Ø± Ú©ÛŒ Ú¯Ø¦ÛŒ ÛÛ’ØŒ Ø§Ú¯Ø± Ú©ÛŒ Ú¯Ø¦ÛŒ ÛÛ’ ØªÙˆ Ø§Ø³ Ú©Û’ Ù…Ø®ØªØµØ± Ù…Ù†Ø¯Ø±Ø¬Ø§ØªÛ” Ù†ÛÛŒÚº", "Recorded answer is 'No'."),
            ("special_condition", "21Û” Ø¢ÛŒØ§ Ø¯ÙˆÙ„ÛØ§ Ú©ÛŒ Ù¾ÛÙ„Û’ Ø³Û’ Ú©ÙˆØ¦ÛŒ Ø¨ÛŒÙˆÛŒ Ù…ÙˆØ¬ÙˆØ¯ ÛÛ’ØŒ Ø§Ú¯Ø± Ø¬ÙˆØ§Ø¨ Ø§Ø«Ø¨Ø§Øª Ù…ÛŒÚº ÛÙˆ ØªÙˆ Ú©ÛŒØ§ Ø´Ø§Ø¯ÛŒ Ú©Ø±Ù†Û’ Ú©ÛŒÙ„Ø¦Û’ Ø«Ø§Ù„Ø«ÛŒ Ú©ÙˆÙ†Ø³Ù„ Ø³Û’ Ø§Ø¬Ø§Ø²Øª Ù„ÛŒ ÛÛ’ØŸ [unclear] Ù†ÛÛŒÚº", "One part of the question is unclear; the recorded 'No' should be checked on the original."),
            ("special_condition", "22Û” Ù†Ù…Ø¨Ø± Ùˆ ØªØ§Ø±ÛŒØ® Ù…Ø±Ø§Ø³Ù„Û Ú©Û’ Ø°Ø±ÛŒØ¹Û Ø«Ø§Ù„Ø«ÛŒ Ú©ÙˆÙ†Ø³Ù„ Ù†Û’ Ø¯ÙˆÙ„ÛØ§ Ú©Ùˆ Ø¯ÙˆØ³Ø±ÛŒ Ø´Ø§Ø¯ÛŒ Ú©Ø±Ù†Û’ Ú©ÛŒ Ø§Ø¬Ø§Ø²Øª Ø¯ÛŒ ÛÛ’Û” Ù†ÛÛŒÚº", "Recorded answer is 'No'."),
        ),
        "issues": (
            "Question 21 contains an unclear portion and needs source review.",
            "The supplied fragment does not contain party, date, registration, dower or witness particulars.",
        ),
        "actions": (
            "Review the original image around entries 21 to 23.",
        ),
    },
    "sha256:d98763353de53eafb9808f3eec93456e1641137c380aeea65d27067937af9718": {
        "transcription_sha256": "a4a803bb7816b9285c4acfc94fdb51927f0a774574eaae6b741fc7ca10dc0edc",
        "review_event_id": "sha256:f88929e3f12fd21c688cfdab245d500d73c58f6613610777b9366c996b02db54",
        "lineage_rel": "crop_lineage_store/candidate_crop_lineage/d98763353de53eafb9808f3eec93456e1641137c380aeea65d27067937af9718/54c0852de377c28390e7131b7244be3d42fdbce6fa4107550cd74db4a9e38dcd.json",
        "receipt_rel": "targeted_publication_receipt_store/targeted_candidate_publication_receipts/d98763353de53eafb9808f3eec93456e1641137c380aeea65d27067937af9718/a3010e7e02306cc42201a1f95d676f8e074ff5181b3b6f7e60417fd1856a31f2.json",
        "facts": (
            ("marriage_locality_or_district", "Ward 203", "Ward number is legible; remaining locality entries are unclear."),
            ("document_language_mix", "Urdu", "The approved fragment is principally in Urdu."),
        ),
        "issues": (
            "Union, Tehsil/Thana and district entries remain unclear.",
            "Party names and other core marriage particulars are not recoverable from this approved fragment.",
        ),
        "actions": (
            "Obtain a fuller approved transcription or clearer copy of the complete Nikah Nama.",
            "Use a qualified translator where a certified English translation is required.",
        ),
    },
}


def build_preview_records():
    candidate_store = CandidateTranscriptionStore(BASE / "candidate_store")
    review_store = TranscriptionReviewEventStore(BASE / "review_event_store")
    records = []

    for candidate_id in sorted(SNAPSHOT):
        spec = SNAPSHOT[candidate_id]
        candidate = candidate_store.load_candidate(candidate_id)
        projection = project_transcription_review(
            review_store.load_events(candidate_id)
        )

        if projection is None or projection.state is not TranscriptionReviewState.APPROVED:
            raise RuntimeError("Preview candidate is no longer APPROVED.")
        if projection.latest_event_id != spec["review_event_id"]:
            raise RuntimeError("Preview review-event drift.")
        if candidate.transcription_sha256 != spec["transcription_sha256"]:
            raise RuntimeError("Preview transcription drift.")

        binding = loads_candidate_crop_lineage_binding(
            (BASE / spec["lineage_rel"]).read_text(encoding="utf-8")
        )
        receipt = loads_targeted_candidate_publication_receipt(
            (BASE / spec["receipt_rel"]).read_text(encoding="utf-8")
        )
        bbox = tuple(binding.bbox)

        base_provenance = MarriageFactProvenance(
            source_document_instance_id=candidate.source_document_instance_id,
            source_snapshot_id=candidate.source_snapshot_id,
            original_filename=candidate.original_filename,
            original_blob_sha256=candidate.original_blob_sha256,
            page_number=candidate.page_number,
            candidate_record_id=candidate.record_id,
            transcription_sha256=candidate.transcription_sha256,
            review_event_id=projection.latest_event_id,
            derivation_kind=MarriageFactDerivationKind.OCR_DERIVED,
            quality_note="MDI2 real-extraction snapshot.",
            binding_id=binding.binding_id,
            publication_receipt_id=receipt.receipt_id,
            crop_name=binding.crop_name,
            bbox=SourceRegion(
                left=int(bbox[0]),
                top=int(bbox[1]),
                right=int(bbox[2]),
                bottom=int(bbox[3]),
            ),
        )

        facts = tuple(
            MarriageFact(
                field=MarriageFactField(field_name),
                value=value,
                provenance=MarriageFactProvenance(
                    **{
                        **base_provenance.__dict__,
                        "quality_note": quality_note,
                    }
                ),
            )
            for field_name, value, quality_note in spec["facts"]
        )

        records.append(
            MarriageDocumentIntelligenceRecord.create(
                document_type=MarriageDocumentType.NIKAH_NAMA,
                document_label=f"Nikah Nama fragment â€” {binding.crop_name}",
                facts=facts,
                potential_issues=tuple(
                    MarriagePotentialIssue(summary=value)
                    for value in spec["issues"]
                ),
                next_professional_actions=tuple(spec["actions"]),
            )
        )

    return tuple(records)


if __name__ == "__main__":
    workspace = build_marriage_document_workspace(build_preview_records())
    show_marriage_document_workspace(workspace)
