from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import (
    DerivedTranscriptionSearchCandidate,
)


_CANDIDATE_ID_PREFIX = (
    "dtx:sha256:"
)


def candidate_identity_payload_to_dict(
    value: DerivedTranscriptionSearchCandidate,
) -> dict[str, Any]:

    return {
        "schema_version":
            value.schema_version,

        "authority_kind":
            value.authority_kind,

        "case_id":
            value.case_id,

        "source_document_instance_id":
            value.source_document_instance_id,

        "source_snapshot_id":
            value.source_snapshot_id,

        "page_number":
            value.page_number,

        "original_blob_sha256":
            value.original_blob_sha256,

        "source_page_text_sha256":
            value.source_page_text_sha256,

        "source_page_text_byte_length":
            value.source_page_text_byte_length,

        "derived_record_schema_version":
            value.derived_record_schema_version,

        "derived_record_id":
            value.derived_record_id,

        "transcription_sha256":
            value.transcription_sha256,

        "transcription_byte_length":
            value.transcription_byte_length,

        "profile_id":
            value.profile_id,

        "profile_schema_version":
            value.profile_schema_version,

        "embedded_image_sha256":
            value.embedded_image_sha256,

        "ocr_language":
            value.ocr_language,

        "ocr_psm":
            value.ocr_psm,

        "preprocessing_steps":
            list(
                value.preprocessing_steps
            ),
    }


def canonical_identity_bytes(
    value: DerivedTranscriptionSearchCandidate,
) -> bytes:

    return json.dumps(
        candidate_identity_payload_to_dict(
            value
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )


def derive_candidate_id(
    value: DerivedTranscriptionSearchCandidate,
) -> str:

    digest = hashlib.sha256(
        canonical_identity_bytes(
            value
        )
    ).hexdigest()

    return (
        _CANDIDATE_ID_PREFIX
        + digest
    )
