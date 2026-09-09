"""Immutable crop-lineage sidecar binding for targeted transcription candidates.

The existing CandidateTranscriptionRecord remains unchanged.  This module binds
one existing candidate record to one released CroppedArtifactReceipt without
embedding professional-review, search, provider-call, or source-store state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .cropped_artifact import CroppedArtifactReceipt
from .models import CandidateTranscriptionRecord
from .validation import validate_candidate_transcription_record


CROP_LINEAGE_SCHEMA_VERSION = "candidate-crop-lineage-binding/1.0"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CROP_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class CandidateCropLineageError(RuntimeError):
    """Raised when candidate/crop lineage cannot be proven exactly."""


@dataclass(frozen=True)
class CandidateCropLineageBinding:
    schema_version: str
    binding_id: str
    candidate_record_id: str
    transcription_sha256: str
    derived_artifact_sha256: str
    parent_artifact_sha256: str
    parent_artifact_byte_length: int
    parent_artifact_width: int
    parent_artifact_height: int
    crop_name: str
    bbox: tuple[int, int, int, int]
    raw_pixel_sha256: str
    artifact_byte_length: int
    artifact_width: int
    artifact_height: int
    crop_profile_id: str
    crop_profile_schema_version: str


def _fail(message: str) -> None:
    raise CandidateCropLineageError(message)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail(f"{field_name} must be non-empty canonical text.")
    return value


def _sha256_hex_value(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX_RE.fullmatch(value) is None:
        _fail(f"{field_name} must be exact lower-case SHA-256 hex.")
    return value


def _sha256_id(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_ID_RE.fullmatch(value) is None:
        _fail(f"{field_name} must be an exact sha256:<hex> identifier.")
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field_name} must be a positive integer.")
    return value


def _crop_name(value: object) -> str:
    if not isinstance(value, str) or _CROP_NAME_RE.fullmatch(value) is None:
        _fail("crop_name must match the governed upper-case identifier profile.")
    return value


def _bbox(
    value: object,
    *,
    parent_width: int,
    parent_height: int,
    artifact_width: int,
    artifact_height: int,
) -> tuple[int, int, int, int]:
    if type(value) is not tuple or len(value) != 4:
        _fail("bbox must be an exact four-integer tuple.")

    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        _fail("bbox must contain exact integers.")

    left, top, right, bottom = value

    if left < 0 or top < 0:
        _fail("bbox origin must be non-negative.")
    if right <= left or bottom <= top:
        _fail("bbox must have positive width and height.")
    if right > parent_width or bottom > parent_height:
        _fail("bbox exceeds parent artifact bounds.")
    if right - left != artifact_width or bottom - top != artifact_height:
        _fail("bbox geometry does not match cropped artifact dimensions.")

    return left, top, right, bottom


def candidate_crop_lineage_identity_payload(
    *,
    candidate_record_id: str,
    transcription_sha256: str,
    derived_artifact_sha256: str,
    parent_artifact_sha256: str,
    parent_artifact_byte_length: int,
    parent_artifact_width: int,
    parent_artifact_height: int,
    crop_name: str,
    bbox: tuple[int, int, int, int],
    raw_pixel_sha256: str,
    artifact_byte_length: int,
    artifact_width: int,
    artifact_height: int,
    crop_profile_id: str,
    crop_profile_schema_version: str,
) -> dict[str, Any]:
    """Return the complete canonical identity payload except binding_id."""

    return {
        "schema_version": CROP_LINEAGE_SCHEMA_VERSION,
        "candidate_record_id": candidate_record_id,
        "transcription_sha256": transcription_sha256,
        "derived_artifact_sha256": derived_artifact_sha256,
        "parent_artifact_sha256": parent_artifact_sha256,
        "parent_artifact_byte_length": parent_artifact_byte_length,
        "parent_artifact_width": parent_artifact_width,
        "parent_artifact_height": parent_artifact_height,
        "crop_name": crop_name,
        "bbox": list(bbox),
        "raw_pixel_sha256": raw_pixel_sha256,
        "artifact_byte_length": artifact_byte_length,
        "artifact_width": artifact_width,
        "artifact_height": artifact_height,
        "crop_profile_id": crop_profile_id,
        "crop_profile_schema_version": crop_profile_schema_version,
    }


def candidate_crop_lineage_binding_id(
    **payload_values: Any,
) -> str:
    """Derive one deterministic SHA-256 identity from the canonical payload."""

    payload = candidate_crop_lineage_identity_payload(**payload_values)
    return "sha256:" + _sha256_hex(_canonical_json_bytes(payload))


def validate_candidate_crop_lineage_binding(
    binding: CandidateCropLineageBinding,
) -> None:
    """Validate one binding including deterministic identity."""

    if not isinstance(binding, CandidateCropLineageBinding):
        _fail("binding must be CandidateCropLineageBinding.")

    if binding.schema_version != CROP_LINEAGE_SCHEMA_VERSION:
        _fail("Unsupported crop-lineage schema version.")

    _sha256_id(binding.binding_id, field_name="binding_id")
    _sha256_id(binding.candidate_record_id, field_name="candidate_record_id")
    _sha256_hex_value(
        binding.transcription_sha256,
        field_name="transcription_sha256",
    )
    _sha256_hex_value(
        binding.derived_artifact_sha256,
        field_name="derived_artifact_sha256",
    )
    _sha256_hex_value(
        binding.parent_artifact_sha256,
        field_name="parent_artifact_sha256",
    )
    _sha256_hex_value(
        binding.raw_pixel_sha256,
        field_name="raw_pixel_sha256",
    )

    parent_byte_length = _positive_int(
        binding.parent_artifact_byte_length,
        field_name="parent_artifact_byte_length",
    )
    parent_width = _positive_int(
        binding.parent_artifact_width,
        field_name="parent_artifact_width",
    )
    parent_height = _positive_int(
        binding.parent_artifact_height,
        field_name="parent_artifact_height",
    )
    artifact_byte_length = _positive_int(
        binding.artifact_byte_length,
        field_name="artifact_byte_length",
    )
    artifact_width = _positive_int(
        binding.artifact_width,
        field_name="artifact_width",
    )
    artifact_height = _positive_int(
        binding.artifact_height,
        field_name="artifact_height",
    )

    crop_name = _crop_name(binding.crop_name)
    bbox = _bbox(
        binding.bbox,
        parent_width=parent_width,
        parent_height=parent_height,
        artifact_width=artifact_width,
        artifact_height=artifact_height,
    )

    crop_profile_id = _required_text(
        binding.crop_profile_id,
        field_name="crop_profile_id",
    )
    crop_profile_schema_version = _required_text(
        binding.crop_profile_schema_version,
        field_name="crop_profile_schema_version",
    )

    payload_values = {
        "candidate_record_id": binding.candidate_record_id,
        "transcription_sha256": binding.transcription_sha256,
        "derived_artifact_sha256": binding.derived_artifact_sha256,
        "parent_artifact_sha256": binding.parent_artifact_sha256,
        "parent_artifact_byte_length": parent_byte_length,
        "parent_artifact_width": parent_width,
        "parent_artifact_height": parent_height,
        "crop_name": crop_name,
        "bbox": bbox,
        "raw_pixel_sha256": binding.raw_pixel_sha256,
        "artifact_byte_length": artifact_byte_length,
        "artifact_width": artifact_width,
        "artifact_height": artifact_height,
        "crop_profile_id": crop_profile_id,
        "crop_profile_schema_version": crop_profile_schema_version,
    }

    expected_id = candidate_crop_lineage_binding_id(**payload_values)
    if binding.binding_id != expected_id:
        _fail("binding_id does not match canonical crop-lineage identity.")


def build_candidate_crop_lineage_binding(
    *,
    candidate_record: CandidateTranscriptionRecord,
    crop_receipt: CroppedArtifactReceipt,
) -> CandidateCropLineageBinding:
    """Build one immutable exact binding from an existing candidate and crop."""

    validate_candidate_transcription_record(candidate_record)

    if not isinstance(crop_receipt, CroppedArtifactReceipt):
        _fail("crop_receipt must be CroppedArtifactReceipt.")

    if candidate_record.derived_artifact_role != crop_receipt.artifact_role:
        _fail("Candidate derived artifact role does not match cropped artifact role.")
    if candidate_record.derived_artifact_sha256 != crop_receipt.artifact_sha256:
        _fail("Candidate derived artifact SHA-256 does not match cropped artifact.")
    if (
        candidate_record.derived_artifact_byte_length
        != crop_receipt.artifact_byte_length
    ):
        _fail("Candidate derived artifact byte length does not match cropped artifact.")
    if candidate_record.derived_artifact_width != crop_receipt.artifact_width:
        _fail("Candidate derived artifact width does not match cropped artifact.")
    if candidate_record.derived_artifact_height != crop_receipt.artifact_height:
        _fail("Candidate derived artifact height does not match cropped artifact.")

    payload_values = {
        "candidate_record_id": candidate_record.record_id,
        "transcription_sha256": candidate_record.transcription_sha256,
        "derived_artifact_sha256": candidate_record.derived_artifact_sha256,
        "parent_artifact_sha256": crop_receipt.parent_artifact_sha256,
        "parent_artifact_byte_length": crop_receipt.parent_artifact_byte_length,
        "parent_artifact_width": crop_receipt.parent_artifact_width,
        "parent_artifact_height": crop_receipt.parent_artifact_height,
        "crop_name": crop_receipt.crop_name,
        "bbox": crop_receipt.bbox,
        "raw_pixel_sha256": crop_receipt.raw_pixel_sha256,
        "artifact_byte_length": crop_receipt.artifact_byte_length,
        "artifact_width": crop_receipt.artifact_width,
        "artifact_height": crop_receipt.artifact_height,
        "crop_profile_id": crop_receipt.profile_id,
        "crop_profile_schema_version": crop_receipt.profile_schema_version,
    }

    binding = CandidateCropLineageBinding(
        schema_version=CROP_LINEAGE_SCHEMA_VERSION,
        binding_id=candidate_crop_lineage_binding_id(**payload_values),
        **payload_values,
    )
    validate_candidate_crop_lineage_binding(binding)
    return binding


def validate_candidate_crop_publication_unit(
    *,
    candidate_record: CandidateTranscriptionRecord,
    transcription_text: str,
    crop_receipt: CroppedArtifactReceipt,
    binding: CandidateCropLineageBinding,
) -> None:
    """Validate candidate text + crop receipt + lineage as one governed unit."""

    validate_candidate_transcription_record(candidate_record)
    validate_candidate_crop_lineage_binding(binding)

    if not isinstance(transcription_text, str):
        _fail("transcription_text must be text.")

    transcription_bytes = transcription_text.encode("utf-8")
    if _sha256_hex(transcription_bytes) != candidate_record.transcription_sha256:
        _fail("Transcription text SHA-256 does not match candidate record.")
    if len(transcription_bytes) != candidate_record.transcription_byte_length:
        _fail("Transcription text byte length does not match candidate record.")

    expected = build_candidate_crop_lineage_binding(
        candidate_record=candidate_record,
        crop_receipt=crop_receipt,
    )
    if binding != expected:
        _fail("Crop-lineage binding does not match candidate/crop publication unit.")


def candidate_crop_lineage_binding_to_dict(
    binding: CandidateCropLineageBinding,
) -> dict[str, Any]:
    validate_candidate_crop_lineage_binding(binding)
    return {
        "schema_version": binding.schema_version,
        "binding_id": binding.binding_id,
        "candidate_record_id": binding.candidate_record_id,
        "transcription_sha256": binding.transcription_sha256,
        "derived_artifact_sha256": binding.derived_artifact_sha256,
        "parent_artifact_sha256": binding.parent_artifact_sha256,
        "parent_artifact_byte_length": binding.parent_artifact_byte_length,
        "parent_artifact_width": binding.parent_artifact_width,
        "parent_artifact_height": binding.parent_artifact_height,
        "crop_name": binding.crop_name,
        "bbox": list(binding.bbox),
        "raw_pixel_sha256": binding.raw_pixel_sha256,
        "artifact_byte_length": binding.artifact_byte_length,
        "artifact_width": binding.artifact_width,
        "artifact_height": binding.artifact_height,
        "crop_profile_id": binding.crop_profile_id,
        "crop_profile_schema_version": binding.crop_profile_schema_version,
    }


def dumps_candidate_crop_lineage_binding(
    binding: CandidateCropLineageBinding,
) -> str:
    return _canonical_json_bytes(
        candidate_crop_lineage_binding_to_dict(binding)
    ).decode("utf-8")


def candidate_crop_lineage_binding_from_dict(
    value: Mapping[str, Any],
) -> CandidateCropLineageBinding:
    if not isinstance(value, Mapping):
        _fail("Serialized crop-lineage binding must be an object.")

    expected_keys = {
        "schema_version",
        "binding_id",
        "candidate_record_id",
        "transcription_sha256",
        "derived_artifact_sha256",
        "parent_artifact_sha256",
        "parent_artifact_byte_length",
        "parent_artifact_width",
        "parent_artifact_height",
        "crop_name",
        "bbox",
        "raw_pixel_sha256",
        "artifact_byte_length",
        "artifact_width",
        "artifact_height",
        "crop_profile_id",
        "crop_profile_schema_version",
    }

    if set(value) != expected_keys:
        _fail("Serialized crop-lineage binding keys are not exact.")

    raw_bbox = value["bbox"]
    if type(raw_bbox) is not list or len(raw_bbox) != 4:
        _fail("Serialized bbox must be an exact four-item JSON array.")

    binding = CandidateCropLineageBinding(
        schema_version=value["schema_version"],
        binding_id=value["binding_id"],
        candidate_record_id=value["candidate_record_id"],
        transcription_sha256=value["transcription_sha256"],
        derived_artifact_sha256=value["derived_artifact_sha256"],
        parent_artifact_sha256=value["parent_artifact_sha256"],
        parent_artifact_byte_length=value["parent_artifact_byte_length"],
        parent_artifact_width=value["parent_artifact_width"],
        parent_artifact_height=value["parent_artifact_height"],
        crop_name=value["crop_name"],
        bbox=tuple(raw_bbox),
        raw_pixel_sha256=value["raw_pixel_sha256"],
        artifact_byte_length=value["artifact_byte_length"],
        artifact_width=value["artifact_width"],
        artifact_height=value["artifact_height"],
        crop_profile_id=value["crop_profile_id"],
        crop_profile_schema_version=value["crop_profile_schema_version"],
    )
    validate_candidate_crop_lineage_binding(binding)
    return binding


def loads_candidate_crop_lineage_binding(
    text: str,
) -> CandidateCropLineageBinding:
    if not isinstance(text, str):
        _fail("Serialized crop-lineage binding must be text.")

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CandidateCropLineageError(
            "Serialized crop-lineage binding is not valid JSON."
        ) from exc

    return candidate_crop_lineage_binding_from_dict(value)


__all__ = [
    "CROP_LINEAGE_SCHEMA_VERSION",
    "CandidateCropLineageBinding",
    "CandidateCropLineageError",
    "build_candidate_crop_lineage_binding",
    "candidate_crop_lineage_binding_from_dict",
    "candidate_crop_lineage_binding_id",
    "candidate_crop_lineage_binding_to_dict",
    "candidate_crop_lineage_identity_payload",
    "dumps_candidate_crop_lineage_binding",
    "loads_candidate_crop_lineage_binding",
    "validate_candidate_crop_lineage_binding",
    "validate_candidate_crop_publication_unit",
]
