from __future__ import annotations

from typing import Any

from .models import (
    TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationRow,
)
from .validation import (
    validate_current_review_binding,
    validate_targeted_candidate_activation_row,
    validate_targeted_candidate_governance_gate,
)


def build_targeted_candidate_activation(
    *,
    candidate: Any,
    document: str,
    binding: Any,
    receipt: Any,
    review_projection: Any,
    embedding_model: str,
    collection_name: str = TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
) -> tuple[
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationRow,
]:
    validate_targeted_candidate_governance_gate(
        candidate=candidate,
        document=document,
        binding=binding,
        receipt=receipt,
        review_projection=review_projection,
    )

    authority = TargetedCandidateActivationAuthority(
        case_id=candidate.case_id,
        candidate_record_id=candidate.record_id,
        transcription_sha256=candidate.transcription_sha256,
        transcription_bytes=candidate.transcription_byte_length,
        binding_id=binding.binding_id,
        publication_receipt_id=receipt.receipt_id,
        review_event_id=review_projection.latest_event_id,
        derived_artifact_sha256=candidate.derived_artifact_sha256,
        embedding_model=embedding_model,
        collection_name=collection_name,
    )

    row = TargetedCandidateActivationRow(
        candidate_record_id=candidate.record_id,
        document=document,
        case_id=candidate.case_id,
        source_document_instance_id=candidate.source_document_instance_id,
        source_snapshot_id=candidate.source_snapshot_id,
        page_number=candidate.page_number,
        original_blob_sha256=candidate.original_blob_sha256,
        transcription_sha256=candidate.transcription_sha256,
        derived_artifact_sha256=candidate.derived_artifact_sha256,
        profile_id=candidate.profile_id,
        binding_id=binding.binding_id,
        parent_artifact_sha256=binding.parent_artifact_sha256,
        crop_name=binding.crop_name,
        bbox=binding.bbox,
        publication_receipt_id=receipt.receipt_id,
        review_event_id=review_projection.latest_event_id,
    )

    validate_targeted_candidate_activation_row(
        authority=authority,
        row=row,
    )
    validate_current_review_binding(
        authority=authority,
        row=row,
        review_projection=review_projection,
    )
    return authority, row
