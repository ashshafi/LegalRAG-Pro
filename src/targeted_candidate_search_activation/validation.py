from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import (
    TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationRow,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}")


class TargetedCandidateActivationError(ValueError):
    """Fail-closed targeted-candidate activation validation failure."""


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TargetedCandidateActivationError(
            field_name + " must be non-empty text."
        )
    return value


def _require_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TargetedCandidateActivationError(
            field_name + " is not a canonical SHA256 digest."
        )
    return value


def _require_sha256_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise TargetedCandidateActivationError(
            field_name + " is not a canonical sha256: identifier."
        )
    return value


def _require_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TargetedCandidateActivationError(
            field_name + " must be a positive integer."
        )
    return value


def _require_bbox(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, tuple) or len(value) != 4:
        raise TargetedCandidateActivationError(
            "bbox must be a four-integer tuple."
        )
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise TargetedCandidateActivationError(
            "bbox must contain integers only."
        )
    left, top, right, bottom = value
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise TargetedCandidateActivationError(
            "bbox geometry is invalid."
        )
    return value


def validate_targeted_candidate_activation_authority(
    authority: TargetedCandidateActivationAuthority,
) -> None:
    _require_text(authority.case_id, "authority.case_id")
    _require_sha256_id(
        authority.candidate_record_id,
        "authority.candidate_record_id",
    )
    _require_sha256(
        authority.transcription_sha256,
        "authority.transcription_sha256",
    )
    _require_positive_int(
        authority.transcription_bytes,
        "authority.transcription_bytes",
    )
    _require_sha256_id(authority.binding_id, "authority.binding_id")
    _require_sha256_id(
        authority.publication_receipt_id,
        "authority.publication_receipt_id",
    )
    _require_sha256_id(
        authority.review_event_id,
        "authority.review_event_id",
    )
    _require_sha256(
        authority.derived_artifact_sha256,
        "authority.derived_artifact_sha256",
    )
    _require_text(authority.embedding_model, "authority.embedding_model")
    _require_text(authority.collection_name, "authority.collection_name")


def validate_targeted_candidate_activation_row(
    *,
    authority: TargetedCandidateActivationAuthority,
    row: TargetedCandidateActivationRow,
) -> None:
    validate_targeted_candidate_activation_authority(authority)

    if row.candidate_record_id != authority.candidate_record_id:
        raise TargetedCandidateActivationError(
            "Row candidate record ID does not match authority."
        )
    if row.case_id != authority.case_id:
        raise TargetedCandidateActivationError(
            "Row case ID does not match authority."
        )
    if row.transcription_sha256 != authority.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Row transcription hash does not match authority."
        )
    if row.binding_id != authority.binding_id:
        raise TargetedCandidateActivationError(
            "Row binding ID does not match authority."
        )
    if row.publication_receipt_id != authority.publication_receipt_id:
        raise TargetedCandidateActivationError(
            "Row publication receipt ID does not match authority."
        )
    if row.review_event_id != authority.review_event_id:
        raise TargetedCandidateActivationError(
            "Row review event ID does not match authority."
        )
    if row.derived_artifact_sha256 != authority.derived_artifact_sha256:
        raise TargetedCandidateActivationError(
            "Row derived artifact hash does not match authority."
        )
    if row.authority_kind != TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND:
        raise TargetedCandidateActivationError(
            "Row authority kind is not targeted_candidate_transcription."
        )

    _require_text(
        row.source_document_instance_id,
        "row.source_document_instance_id",
    )
    _require_sha256_id(row.source_snapshot_id, "row.source_snapshot_id")
    _require_positive_int(row.page_number, "row.page_number")
    _require_sha256(row.original_blob_sha256, "row.original_blob_sha256")
    _require_sha256(row.transcription_sha256, "row.transcription_sha256")
    _require_sha256(
        row.derived_artifact_sha256,
        "row.derived_artifact_sha256",
    )
    _require_text(row.profile_id, "row.profile_id")
    _require_sha256_id(row.binding_id, "row.binding_id")
    _require_sha256(
        row.parent_artifact_sha256,
        "row.parent_artifact_sha256",
    )
    _require_text(row.crop_name, "row.crop_name")
    _require_bbox(row.bbox)
    _require_sha256_id(
        row.publication_receipt_id,
        "row.publication_receipt_id",
    )
    _require_sha256_id(row.review_event_id, "row.review_event_id")

    if not isinstance(row.document, str) or not row.document:
        raise TargetedCandidateActivationError(
            "Targeted candidate transcription must be non-empty text."
        )

    raw = row.document.encode("utf-8")
    if len(raw) != authority.transcription_bytes:
        raise TargetedCandidateActivationError(
            "Targeted candidate transcription byte length differs from authority."
        )
    if hashlib.sha256(raw).hexdigest() != authority.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Targeted candidate transcription SHA256 differs from authority."
        )


def validate_targeted_candidate_governance_gate(
    *,
    candidate: Any,
    document: str,
    binding: Any,
    receipt: Any,
    review_projection: Any,
) -> None:
    _require_sha256_id(candidate.record_id, "candidate.record_id")
    _require_text(candidate.case_id, "candidate.case_id")
    _require_text(
        candidate.source_document_instance_id,
        "candidate.source_document_instance_id",
    )
    _require_sha256_id(
        candidate.source_snapshot_id,
        "candidate.source_snapshot_id",
    )
    _require_positive_int(candidate.page_number, "candidate.page_number")
    _require_sha256(
        candidate.original_blob_sha256,
        "candidate.original_blob_sha256",
    )
    _require_sha256(
        candidate.transcription_sha256,
        "candidate.transcription_sha256",
    )
    _require_positive_int(
        candidate.transcription_byte_length,
        "candidate.transcription_byte_length",
    )
    _require_sha256(
        candidate.derived_artifact_sha256,
        "candidate.derived_artifact_sha256",
    )
    _require_text(candidate.profile_id, "candidate.profile_id")

    if not isinstance(document, str) or not document:
        raise TargetedCandidateActivationError(
            "Persisted candidate transcription must be non-empty text."
        )
    raw = document.encode("utf-8")
    if len(raw) != candidate.transcription_byte_length:
        raise TargetedCandidateActivationError(
            "Persisted transcription byte length differs from candidate."
        )
    if hashlib.sha256(raw).hexdigest() != candidate.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Persisted transcription SHA256 differs from candidate."
        )

    if binding.candidate_record_id != candidate.record_id:
        raise TargetedCandidateActivationError(
            "Crop-lineage candidate binding differs from candidate."
        )
    if binding.transcription_sha256 != candidate.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Crop-lineage transcription binding differs from candidate."
        )
    if binding.derived_artifact_sha256 != candidate.derived_artifact_sha256:
        raise TargetedCandidateActivationError(
            "Crop-lineage artifact binding differs from candidate."
        )
    _require_sha256_id(binding.binding_id, "binding.binding_id")
    _require_sha256(
        binding.parent_artifact_sha256,
        "binding.parent_artifact_sha256",
    )
    _require_text(binding.crop_name, "binding.crop_name")
    _require_bbox(binding.bbox)

    if receipt.candidate_record_id != candidate.record_id:
        raise TargetedCandidateActivationError(
            "Publication receipt candidate binding differs from candidate."
        )
    if receipt.transcription_sha256 != candidate.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Publication receipt transcription binding differs from candidate."
        )
    if receipt.derived_artifact_sha256 != candidate.derived_artifact_sha256:
        raise TargetedCandidateActivationError(
            "Publication receipt artifact binding differs from candidate."
        )
    if receipt.binding_id != binding.binding_id:
        raise TargetedCandidateActivationError(
            "Publication receipt lineage binding differs from binding."
        )
    if receipt.parent_artifact_sha256 != binding.parent_artifact_sha256:
        raise TargetedCandidateActivationError(
            "Publication receipt parent artifact differs from binding."
        )
    if receipt.crop_name != binding.crop_name:
        raise TargetedCandidateActivationError(
            "Publication receipt crop name differs from binding."
        )
    if receipt.bbox != binding.bbox:
        raise TargetedCandidateActivationError(
            "Publication receipt bbox differs from binding."
        )
    _require_sha256_id(receipt.receipt_id, "receipt.receipt_id")
    _require_sha256(
        receipt.candidate_record_serialization_sha256,
        "receipt.candidate_record_serialization_sha256",
    )
    _require_sha256(
        receipt.crop_lineage_binding_serialization_sha256,
        "receipt.crop_lineage_binding_serialization_sha256",
    )

    if review_projection.candidate_record_id != candidate.record_id:
        raise TargetedCandidateActivationError(
            "Review projection candidate binding differs from candidate."
        )
    if review_projection.transcription_sha256 != candidate.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Review projection transcription binding differs from candidate."
        )
    state_value = getattr(review_projection.state, "value", None)
    if state_value != "APPROVED":
        raise TargetedCandidateActivationError(
            "Latest transcription review projection is not APPROVED."
        )
    _require_sha256_id(
        review_projection.latest_event_id,
        "review_projection.latest_event_id",
    )


def validate_current_review_binding(
    *,
    authority: TargetedCandidateActivationAuthority,
    row: TargetedCandidateActivationRow,
    review_projection: Any,
) -> None:
    validate_targeted_candidate_activation_row(
        authority=authority,
        row=row,
    )

    if review_projection.candidate_record_id != authority.candidate_record_id:
        raise TargetedCandidateActivationError(
            "Current review projection candidate differs from authority."
        )
    if review_projection.transcription_sha256 != authority.transcription_sha256:
        raise TargetedCandidateActivationError(
            "Current review projection transcription differs from authority."
        )
    if getattr(review_projection.state, "value", None) != "APPROVED":
        raise TargetedCandidateActivationError(
            "Current review projection is not APPROVED."
        )
    if review_projection.latest_event_id != authority.review_event_id:
        raise TargetedCandidateActivationError(
            "Activation authority is stale relative to latest review event."
        )
    if review_projection.latest_event_id != row.review_event_id:
        raise TargetedCandidateActivationError(
            "Activation row is stale relative to latest review event."
        )
