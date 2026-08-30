from __future__ import annotations

import hashlib
import re
from uuid import UUID

from .identity import (
    derive_candidate_id,
)

from .models import (
    DERIVED_SEARCH_AUTHORITY_KIND,
    DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION,
    DERIVED_SEARCH_ROW_SCHEMA_VERSION,
    DerivedTranscriptionSearchCandidate,
    DerivedTranscriptionSearchRow,
)


_SHA256_RE = re.compile(
    r"^[0-9a-f]{64}$"
)

_SHA256_ID_RE = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)

_CANDIDATE_ID_RE = re.compile(
    r"^dtx:sha256:[0-9a-f]{64}$"
)


# Fields belonging to the frozen source-evidence / M5 lane
# are deliberately forbidden from the derived-search row.
FORBIDDEN_SOURCE_LANE_METADATA = frozenset(
    {
        "binding_class",
        "bound_text_role",
        "chunk",
        "chunk_id",
        "chunk_ordinal",
        "evidence_key",
        "source_binding_class",
        "source_chunk_sha256",
        "source_evidence_binding_id",
        "source_bound_analysis_receipt_id",
    }
)


EXPECTED_ROW_METADATA_KEYS = frozenset(
    {
        "authority_kind",
        "derived_search_candidate_id",
        "derived_search_candidate_schema_version",
        "derived_search_row_schema_version",

        "case_id",
        "source_document_instance_id",
        "source_snapshot_id",
        "page",

        "original_filename",
        "source_original_blob_sha256",
        "source_original_byte_length",
        "source_extraction_method",
        "source_page_text_sha256",
        "source_page_text_byte_length",

        "derived_record_schema_version",
        "derived_record_id",
        "derived_transcription_sha256",
        "derived_transcription_byte_length",

        "derived_profile_id",
        "derived_profile_schema_version",
        "derived_embedded_image_sha256",

        "derived_ocr_language",
        "derived_ocr_psm",
    }
)


def _required_text(
    value: object,
    *,
    field_name: str,
) -> str:

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise ValueError(
            field_name
            + " must be non-empty text."
        )

    return value


def _positive_int(
    value: object,
    *,
    field_name: str,
) -> int:

    if (
        type(value) is not int
        or value < 1
    ):
        raise ValueError(
            field_name
            + " must be a positive integer."
        )

    return value


def _nonnegative_int(
    value: object,
    *,
    field_name: str,
) -> int:

    if (
        type(value) is not int
        or value < 0
    ):
        raise ValueError(
            field_name
            + " must be a non-negative integer."
        )

    return value


def _canonical_uuid(
    value: object,
    *,
    field_name: str,
) -> str:

    text = _required_text(
        value,
        field_name=field_name,
    )

    try:
        canonical = str(
            UUID(
                text
            )
        )

    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:

        raise ValueError(
            field_name
            + " must be a canonical UUID."
        ) from exc

    if canonical != text:
        raise ValueError(
            field_name
            + " must be a canonical UUID."
        )

    return text


def _sha256(
    value: object,
    *,
    field_name: str,
) -> str:

    text = _required_text(
        value,
        field_name=field_name,
    )

    if _SHA256_RE.fullmatch(
        text
    ) is None:

        raise ValueError(
            field_name
            + " must be a lowercase SHA256 digest."
        )

    return text


def _sha256_id(
    value: object,
    *,
    field_name: str,
) -> str:

    text = _required_text(
        value,
        field_name=field_name,
    )

    if _SHA256_ID_RE.fullmatch(
        text
    ) is None:

        raise ValueError(
            field_name
            + " must be a lowercase sha256: identifier."
        )

    return text


def validate_candidate(
    value: DerivedTranscriptionSearchCandidate,
) -> None:

    if not isinstance(
        value,
        DerivedTranscriptionSearchCandidate,
    ):
        raise ValueError(
            "value must be DerivedTranscriptionSearchCandidate."
        )

    if (
        value.schema_version
        != DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported derived-search candidate schema."
        )

    if (
        value.authority_kind
        != DERIVED_SEARCH_AUTHORITY_KIND
    ):
        raise ValueError(
            "Derived-search authority_kind is invalid."
        )

    if _CANDIDATE_ID_RE.fullmatch(
        value.candidate_id
    ) is None:

        raise ValueError(
            "candidate_id is not in the dedicated derived-transcription namespace."
        )

    _canonical_uuid(
        value.case_id,
        field_name="case_id",
    )

    _canonical_uuid(
        value.source_document_instance_id,
        field_name="source_document_instance_id",
    )

    _sha256_id(
        value.source_snapshot_id,
        field_name="source_snapshot_id",
    )

    _positive_int(
        value.page_number,
        field_name="page_number",
    )

    _required_text(
        value.original_filename,
        field_name="original_filename",
    )

    _sha256(
        value.original_blob_sha256,
        field_name="original_blob_sha256",
    )

    _positive_int(
        value.original_byte_length,
        field_name="original_byte_length",
    )

    _required_text(
        value.source_extraction_method,
        field_name="source_extraction_method",
    )

    _sha256(
        value.source_page_text_sha256,
        field_name="source_page_text_sha256",
    )

    _nonnegative_int(
        value.source_page_text_byte_length,
        field_name="source_page_text_byte_length",
    )

    _required_text(
        value.derived_record_schema_version,
        field_name="derived_record_schema_version",
    )

    _sha256_id(
        value.derived_record_id,
        field_name="derived_record_id",
    )

    _sha256(
        value.transcription_sha256,
        field_name="transcription_sha256",
    )

    _positive_int(
        value.transcription_byte_length,
        field_name="transcription_byte_length",
    )

    _required_text(
        value.profile_id,
        field_name="profile_id",
    )

    _required_text(
        value.profile_schema_version,
        field_name="profile_schema_version",
    )

    _sha256(
        value.embedded_image_sha256,
        field_name="embedded_image_sha256",
    )

    _required_text(
        value.ocr_language,
        field_name="ocr_language",
    )

    _positive_int(
        value.ocr_psm,
        field_name="ocr_psm",
    )

    if (
        not value.preprocessing_steps
        or any(
            not isinstance(
                item,
                str,
            )
            or not item
            for item in value.preprocessing_steps
        )
    ):
        raise ValueError(
            "preprocessing_steps must contain non-empty text values."
        )

    if (
        value.candidate_id
        != derive_candidate_id(
            value
        )
    ):
        raise ValueError(
            "candidate_id does not match canonical derived-search identity."
        )


def validate_row(
    value: DerivedTranscriptionSearchRow,
) -> None:

    if not isinstance(
        value,
        DerivedTranscriptionSearchRow,
    ):
        raise ValueError(
            "value must be DerivedTranscriptionSearchRow."
        )

    if (
        value.row_schema_version
        != DERIVED_SEARCH_ROW_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported derived-search row schema."
        )

    validate_candidate(
        value.candidate
    )

    if (
        value.row_id
        != value.candidate.candidate_id
    ):
        raise ValueError(
            "row_id must equal candidate_id."
        )

    if (
        not isinstance(
            value.document,
            str,
        )
        or not value.document
    ):
        raise ValueError(
            "row document must be non-empty text."
        )

    raw = value.document.encode(
        "utf-8"
    )

    if (
        len(raw)
        != value.candidate.transcription_byte_length
    ):
        raise ValueError(
            "row document byte length does not match candidate transcription."
        )

    if (
        hashlib.sha256(
            raw
        ).hexdigest()
        != value.candidate.transcription_sha256
    ):
        raise ValueError(
            "row document SHA256 does not match candidate transcription."
        )

    keys = frozenset(
        value.metadata
    )

    forbidden = (
        keys
        & FORBIDDEN_SOURCE_LANE_METADATA
    )

    if forbidden:
        raise ValueError(
            "row metadata contains forbidden source-lane fields: "
            + ", ".join(
                sorted(
                    forbidden
                )
            )
        )

    if (
        keys
        != EXPECTED_ROW_METADATA_KEYS
    ):

        missing = sorted(
            EXPECTED_ROW_METADATA_KEYS
            - keys
        )

        extra = sorted(
            keys
            - EXPECTED_ROW_METADATA_KEYS
        )

        raise ValueError(
            "row metadata key set is not exact; "
            + f"missing={missing}, extra={extra}."
        )

    expected = {
        "authority_kind":
            value.candidate.authority_kind,

        "derived_search_candidate_id":
            value.candidate.candidate_id,

        "derived_search_candidate_schema_version":
            value.candidate.schema_version,

        "derived_search_row_schema_version":
            value.row_schema_version,

        "case_id":
            value.candidate.case_id,

        "source_document_instance_id":
            value.candidate.source_document_instance_id,

        "source_snapshot_id":
            value.candidate.source_snapshot_id,

        "page":
            value.candidate.page_number,

        "original_filename":
            value.candidate.original_filename,

        "source_original_blob_sha256":
            value.candidate.original_blob_sha256,

        "source_original_byte_length":
            value.candidate.original_byte_length,

        "source_extraction_method":
            value.candidate.source_extraction_method,

        "source_page_text_sha256":
            value.candidate.source_page_text_sha256,

        "source_page_text_byte_length":
            value.candidate.source_page_text_byte_length,

        "derived_record_schema_version":
            value.candidate.derived_record_schema_version,

        "derived_record_id":
            value.candidate.derived_record_id,

        "derived_transcription_sha256":
            value.candidate.transcription_sha256,

        "derived_transcription_byte_length":
            value.candidate.transcription_byte_length,

        "derived_profile_id":
            value.candidate.profile_id,

        "derived_profile_schema_version":
            value.candidate.profile_schema_version,

        "derived_embedded_image_sha256":
            value.candidate.embedded_image_sha256,

        "derived_ocr_language":
            value.candidate.ocr_language,

        "derived_ocr_psm":
            value.candidate.ocr_psm,
    }

    if (
        dict(
            value.metadata
        )
        != expected
    ):
        raise ValueError(
            "row metadata does not exactly match candidate authority."
        )
