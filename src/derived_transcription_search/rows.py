from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib

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

from .validation import (
    validate_candidate,
    validate_row,
)


def _record_value(
    record: Mapping[str, object],
    field_name: str,
) -> object:

    if field_name not in record:
        raise ValueError(
            "derived record is missing required field "
            + repr(
                field_name
            )
            + "."
        )

    return record[
        field_name
    ]


def _record_text(
    record: Mapping[str, object],
    field_name: str,
) -> str:

    value = _record_value(
        record,
        field_name,
    )

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise ValueError(
            "derived record field "
            + repr(
                field_name
            )
            + " must be non-empty text."
        )

    return value


def _record_int(
    record: Mapping[str, object],
    field_name: str,
    *,
    minimum: int,
) -> int:

    value = _record_value(
        record,
        field_name,
    )

    if (
        type(value) is not int
        or value < minimum
    ):
        raise ValueError(
            "derived record field "
            + repr(
                field_name
            )
            + " must be an integer >= "
            + str(
                minimum
            )
            + "."
        )

    return value


def prepare_candidate(
    *,
    record: Mapping[str, object],
    transcription_text: str,
) -> DerivedTranscriptionSearchCandidate:

    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "record must be a mapping."
        )

    if (
        not isinstance(
            transcription_text,
            str,
        )
        or not transcription_text
    ):
        raise ValueError(
            "transcription_text must be non-empty text."
        )

    steps_value = _record_value(
        record,
        "preprocessing_steps",
    )

    if not isinstance(
        steps_value,
        (
            list,
            tuple,
        ),
    ):
        raise ValueError(
            "derived record preprocessing_steps must be a list or tuple."
        )

    provisional = (
        DerivedTranscriptionSearchCandidate(
            schema_version=
                DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION,

            candidate_id=
                "dtx:sha256:"
                + ("0" * 64),

            authority_kind=
                DERIVED_SEARCH_AUTHORITY_KIND,

            case_id=
                _record_text(
                    record,
                    "case_id",
                ),

            source_document_instance_id=
                _record_text(
                    record,
                    "source_document_instance_id",
                ),

            source_snapshot_id=
                _record_text(
                    record,
                    "source_snapshot_id",
                ),

            page_number=
                _record_int(
                    record,
                    "page_number",
                    minimum=1,
                ),

            original_filename=
                _record_text(
                    record,
                    "original_filename",
                ),

            original_blob_sha256=
                _record_text(
                    record,
                    "original_blob_sha256",
                ),

            original_byte_length=
                _record_int(
                    record,
                    "original_byte_length",
                    minimum=1,
                ),

            source_extraction_method=
                _record_text(
                    record,
                    "source_extraction_method",
                ),

            source_page_text_sha256=
                _record_text(
                    record,
                    "source_page_text_sha256",
                ),

            source_page_text_byte_length=
                _record_int(
                    record,
                    "source_page_text_byte_length",
                    minimum=0,
                ),

            derived_record_schema_version=
                _record_text(
                    record,
                    "schema_version",
                ),

            derived_record_id=
                _record_text(
                    record,
                    "record_id",
                ),

            transcription_sha256=
                _record_text(
                    record,
                    "transcription_sha256",
                ),

            transcription_byte_length=
                _record_int(
                    record,
                    "transcription_byte_length",
                    minimum=1,
                ),

            profile_id=
                _record_text(
                    record,
                    "profile_id",
                ),

            profile_schema_version=
                _record_text(
                    record,
                    "profile_schema_version",
                ),

            embedded_image_sha256=
                _record_text(
                    record,
                    "embedded_image_sha256",
                ),

            ocr_language=
                _record_text(
                    record,
                    "ocr_language",
                ),

            ocr_psm=
                _record_int(
                    record,
                    "ocr_psm",
                    minimum=1,
                ),

            preprocessing_steps=
                tuple(
                    steps_value
                ),
        )
    )

    candidate = replace(
        provisional,
        candidate_id=
            derive_candidate_id(
                provisional
            ),
    )

    validate_candidate(
        candidate
    )

    raw = transcription_text.encode(
        "utf-8"
    )

    if (
        len(raw)
        != candidate.transcription_byte_length
    ):
        raise ValueError(
            "transcription text byte length does not match derived record."
        )

    if (
        hashlib.sha256(
            raw
        ).hexdigest()
        != candidate.transcription_sha256
    ):
        raise ValueError(
            "transcription text SHA256 does not match derived record."
        )

    return candidate


def prepare_row(
    *,
    candidate: DerivedTranscriptionSearchCandidate,
    transcription_text: str,
) -> DerivedTranscriptionSearchRow:

    validate_candidate(
        candidate
    )

    metadata = {
        "authority_kind":
            candidate.authority_kind,

        "derived_search_candidate_id":
            candidate.candidate_id,

        "derived_search_candidate_schema_version":
            candidate.schema_version,

        "derived_search_row_schema_version":
            DERIVED_SEARCH_ROW_SCHEMA_VERSION,

        "case_id":
            candidate.case_id,

        "source_document_instance_id":
            candidate.source_document_instance_id,

        "source_snapshot_id":
            candidate.source_snapshot_id,

        "page":
            candidate.page_number,

        "original_filename":
            candidate.original_filename,

        "source_original_blob_sha256":
            candidate.original_blob_sha256,

        "source_original_byte_length":
            candidate.original_byte_length,

        "source_extraction_method":
            candidate.source_extraction_method,

        "source_page_text_sha256":
            candidate.source_page_text_sha256,

        "source_page_text_byte_length":
            candidate.source_page_text_byte_length,

        "derived_record_schema_version":
            candidate.derived_record_schema_version,

        "derived_record_id":
            candidate.derived_record_id,

        "derived_transcription_sha256":
            candidate.transcription_sha256,

        "derived_transcription_byte_length":
            candidate.transcription_byte_length,

        "derived_profile_id":
            candidate.profile_id,

        "derived_profile_schema_version":
            candidate.profile_schema_version,

        "derived_embedded_image_sha256":
            candidate.embedded_image_sha256,

        "derived_ocr_language":
            candidate.ocr_language,

        "derived_ocr_psm":
            candidate.ocr_psm,
    }

    row = DerivedTranscriptionSearchRow(
        row_schema_version=
            DERIVED_SEARCH_ROW_SCHEMA_VERSION,

        row_id=
            candidate.candidate_id,

        candidate=
            candidate,

        document=
            transcription_text,

        metadata=
            metadata,
    )

    validate_row(
        row
    )

    return row


def build_collection_add_payload(
    rows: Sequence[
        DerivedTranscriptionSearchRow
    ],
) -> dict[str, list[object]]:

    canonical = tuple(
        rows
    )

    if not canonical:
        raise ValueError(
            "rows must contain at least one derived-search row."
        )

    for row in canonical:
        validate_row(
            row
        )

    row_ids = tuple(
        row.row_id
        for row in canonical
    )

    if (
        len(
            set(
                row_ids
            )
        )
        != len(
            row_ids
        )
    ):
        raise ValueError(
            "derived-search rows must have unique row IDs."
        )

    return {
        "ids":
            list(
                row_ids
            ),

        "documents":
            [
                row.document
                for row in canonical
            ],

        "metadatas":
            [
                dict(
                    row.metadata
                )
                for row in canonical
            ],
    }
