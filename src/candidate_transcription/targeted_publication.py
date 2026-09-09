"""Governed targeted-candidate publication completion protocol.

This module composes the existing immutable CandidateTranscriptionStore and
CandidateCropLineageStore with a third immutable completion receipt.  A targeted
candidate is complete only after the candidate, transcription, and crop-lineage
binding have all been published, reloaded, and revalidated exactly.

No provider call, source-store mutation, professional-decision state, search,
Chroma, or UI behavior is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .crop_lineage import (
    CandidateCropLineageBinding,
    dumps_candidate_crop_lineage_binding,
    validate_candidate_crop_lineage_binding,
    validate_candidate_crop_publication_unit,
)
from .crop_lineage_store import (
    CandidateCropLineageStore,
    CandidateCropLineageStoreError,
)
from .cropped_artifact import CroppedArtifactReceipt
from .models import CandidateTranscriptionRecord
from .serialization import dumps_candidate_record
from .store import CandidateTranscriptionStore
from .validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
)


TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION = (
    "targeted-candidate-publication-receipt/1.0"
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CROP_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class TargetedCandidatePublicationError(RuntimeError):
    """Raised when targeted publication cannot be proven complete and exact."""


@dataclass(frozen=True)
class TargetedCandidatePublicationReceipt:
    schema_version: str
    receipt_id: str
    candidate_record_id: str
    transcription_sha256: str
    derived_artifact_sha256: str
    binding_id: str
    parent_artifact_sha256: str
    crop_name: str
    bbox: tuple[int, int, int, int]
    candidate_record_serialization_sha256: str
    crop_lineage_binding_serialization_sha256: str


def _fail(message: str) -> None:
    raise TargetedCandidatePublicationError(message)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_hex_value(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX_RE.fullmatch(value) is None:
        _fail(f"{field_name} must be exact lower-case SHA-256 hex.")
    return value


def _sha256_id(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_ID_RE.fullmatch(value) is None:
        _fail(f"{field_name} must be an exact sha256:<hex> identifier.")
    return value


def _crop_name(value: object) -> str:
    if not isinstance(value, str) or _CROP_NAME_RE.fullmatch(value) is None:
        _fail("crop_name must match the governed upper-case identifier profile.")
    return value


def _bbox(value: object) -> tuple[int, int, int, int]:
    if type(value) is not tuple or len(value) != 4:
        _fail("bbox must be an exact four-integer tuple.")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        _fail("bbox must contain exact integers.")

    left, top, right, bottom = value
    if left < 0 or top < 0 or right <= left or bottom <= top:
        _fail("bbox geometry is invalid.")

    return left, top, right, bottom


def _explicit_absolute_root(value: str | Path, *, field_name: str) -> Path:
    if isinstance(value, str) and not value.strip():
        _fail(f"{field_name} must not be empty.")

    root = Path(value)
    if str(root) in {"", "."} or not root.is_absolute():
        _fail(f"{field_name} must be an explicit absolute path.")

    return root


def targeted_candidate_publication_identity_payload(
    *,
    candidate_record_id: str,
    transcription_sha256: str,
    derived_artifact_sha256: str,
    binding_id: str,
    parent_artifact_sha256: str,
    crop_name: str,
    bbox: tuple[int, int, int, int],
    candidate_record_serialization_sha256: str,
    crop_lineage_binding_serialization_sha256: str,
) -> dict[str, Any]:
    """Return the complete canonical receipt identity payload."""

    return {
        "schema_version": TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION,
        "candidate_record_id": candidate_record_id,
        "transcription_sha256": transcription_sha256,
        "derived_artifact_sha256": derived_artifact_sha256,
        "binding_id": binding_id,
        "parent_artifact_sha256": parent_artifact_sha256,
        "crop_name": crop_name,
        "bbox": list(bbox),
        "candidate_record_serialization_sha256": (
            candidate_record_serialization_sha256
        ),
        "crop_lineage_binding_serialization_sha256": (
            crop_lineage_binding_serialization_sha256
        ),
    }


def targeted_candidate_publication_receipt_id(
    **payload_values: Any,
) -> str:
    payload = targeted_candidate_publication_identity_payload(**payload_values)
    return "sha256:" + _sha256_hex(_canonical_json_bytes(payload))


def build_targeted_candidate_publication_receipt(
    *,
    candidate_record: CandidateTranscriptionRecord,
    transcription_text: str,
    binding: CandidateCropLineageBinding,
) -> TargetedCandidatePublicationReceipt:
    """Build the immutable completion marker after exact store resolution."""

    validate_candidate_transcription_record(candidate_record)
    validate_candidate_crop_lineage_binding(binding)

    if not isinstance(transcription_text, str):
        _fail("transcription_text must be str.")

    transcription_bytes = transcription_text.encode("utf-8")
    if _sha256_hex(transcription_bytes) != candidate_record.transcription_sha256:
        _fail("Transcription text SHA-256 does not match candidate record.")
    if len(transcription_bytes) != candidate_record.transcription_byte_length:
        _fail("Transcription text byte length does not match candidate record.")

    if binding.candidate_record_id != candidate_record.record_id:
        _fail("Binding candidate_record_id does not match candidate record.")
    if binding.transcription_sha256 != candidate_record.transcription_sha256:
        _fail("Binding transcription_sha256 does not match candidate record.")
    if binding.derived_artifact_sha256 != candidate_record.derived_artifact_sha256:
        _fail("Binding derived artifact SHA-256 does not match candidate record.")

    candidate_serialized = dumps_candidate_record(candidate_record).encode("utf-8")
    binding_serialized = dumps_candidate_crop_lineage_binding(binding).encode("utf-8")

    payload_values = {
        "candidate_record_id": candidate_record.record_id,
        "transcription_sha256": candidate_record.transcription_sha256,
        "derived_artifact_sha256": candidate_record.derived_artifact_sha256,
        "binding_id": binding.binding_id,
        "parent_artifact_sha256": binding.parent_artifact_sha256,
        "crop_name": binding.crop_name,
        "bbox": binding.bbox,
        "candidate_record_serialization_sha256": _sha256_hex(
            candidate_serialized
        ),
        "crop_lineage_binding_serialization_sha256": _sha256_hex(
            binding_serialized
        ),
    }

    receipt = TargetedCandidatePublicationReceipt(
        schema_version=TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION,
        receipt_id=targeted_candidate_publication_receipt_id(**payload_values),
        **payload_values,
    )
    validate_targeted_candidate_publication_receipt(receipt)
    return receipt


def validate_targeted_candidate_publication_receipt(
    receipt: TargetedCandidatePublicationReceipt,
) -> None:
    if not isinstance(receipt, TargetedCandidatePublicationReceipt):
        _fail("receipt must be TargetedCandidatePublicationReceipt.")

    if receipt.schema_version != TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION:
        _fail("Unsupported targeted publication receipt schema version.")

    _sha256_id(receipt.receipt_id, field_name="receipt_id")
    _sha256_id(receipt.candidate_record_id, field_name="candidate_record_id")
    _sha256_id(receipt.binding_id, field_name="binding_id")
    _sha256_hex_value(
        receipt.transcription_sha256,
        field_name="transcription_sha256",
    )
    _sha256_hex_value(
        receipt.derived_artifact_sha256,
        field_name="derived_artifact_sha256",
    )
    _sha256_hex_value(
        receipt.parent_artifact_sha256,
        field_name="parent_artifact_sha256",
    )
    _sha256_hex_value(
        receipt.candidate_record_serialization_sha256,
        field_name="candidate_record_serialization_sha256",
    )
    _sha256_hex_value(
        receipt.crop_lineage_binding_serialization_sha256,
        field_name="crop_lineage_binding_serialization_sha256",
    )

    crop_name = _crop_name(receipt.crop_name)
    bbox = _bbox(receipt.bbox)

    payload_values = {
        "candidate_record_id": receipt.candidate_record_id,
        "transcription_sha256": receipt.transcription_sha256,
        "derived_artifact_sha256": receipt.derived_artifact_sha256,
        "binding_id": receipt.binding_id,
        "parent_artifact_sha256": receipt.parent_artifact_sha256,
        "crop_name": crop_name,
        "bbox": bbox,
        "candidate_record_serialization_sha256": (
            receipt.candidate_record_serialization_sha256
        ),
        "crop_lineage_binding_serialization_sha256": (
            receipt.crop_lineage_binding_serialization_sha256
        ),
    }

    expected_id = targeted_candidate_publication_receipt_id(**payload_values)
    if receipt.receipt_id != expected_id:
        _fail("receipt_id does not match canonical publication identity.")


def targeted_candidate_publication_receipt_to_dict(
    receipt: TargetedCandidatePublicationReceipt,
) -> dict[str, Any]:
    validate_targeted_candidate_publication_receipt(receipt)
    return {
        "schema_version": receipt.schema_version,
        "receipt_id": receipt.receipt_id,
        "candidate_record_id": receipt.candidate_record_id,
        "transcription_sha256": receipt.transcription_sha256,
        "derived_artifact_sha256": receipt.derived_artifact_sha256,
        "binding_id": receipt.binding_id,
        "parent_artifact_sha256": receipt.parent_artifact_sha256,
        "crop_name": receipt.crop_name,
        "bbox": list(receipt.bbox),
        "candidate_record_serialization_sha256": (
            receipt.candidate_record_serialization_sha256
        ),
        "crop_lineage_binding_serialization_sha256": (
            receipt.crop_lineage_binding_serialization_sha256
        ),
    }


def dumps_targeted_candidate_publication_receipt(
    receipt: TargetedCandidatePublicationReceipt,
) -> str:
    return _canonical_json_bytes(
        targeted_candidate_publication_receipt_to_dict(receipt)
    ).decode("utf-8")


def targeted_candidate_publication_receipt_from_dict(
    value: Mapping[str, Any],
) -> TargetedCandidatePublicationReceipt:
    if not isinstance(value, Mapping):
        _fail("Serialized targeted publication receipt must be an object.")

    expected_keys = {
        "schema_version",
        "receipt_id",
        "candidate_record_id",
        "transcription_sha256",
        "derived_artifact_sha256",
        "binding_id",
        "parent_artifact_sha256",
        "crop_name",
        "bbox",
        "candidate_record_serialization_sha256",
        "crop_lineage_binding_serialization_sha256",
    }

    if set(value) != expected_keys:
        _fail("Serialized targeted publication receipt keys are not exact.")

    raw_bbox = value["bbox"]
    if type(raw_bbox) is not list or len(raw_bbox) != 4:
        _fail("Serialized bbox must be an exact four-item JSON array.")

    receipt = TargetedCandidatePublicationReceipt(
        schema_version=value["schema_version"],
        receipt_id=value["receipt_id"],
        candidate_record_id=value["candidate_record_id"],
        transcription_sha256=value["transcription_sha256"],
        derived_artifact_sha256=value["derived_artifact_sha256"],
        binding_id=value["binding_id"],
        parent_artifact_sha256=value["parent_artifact_sha256"],
        crop_name=value["crop_name"],
        bbox=tuple(raw_bbox),
        candidate_record_serialization_sha256=(
            value["candidate_record_serialization_sha256"]
        ),
        crop_lineage_binding_serialization_sha256=(
            value["crop_lineage_binding_serialization_sha256"]
        ),
    )
    validate_targeted_candidate_publication_receipt(receipt)
    return receipt


def loads_targeted_candidate_publication_receipt(
    text: str,
) -> TargetedCandidatePublicationReceipt:
    if not isinstance(text, str):
        _fail("Serialized targeted publication receipt must be text.")

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetedCandidatePublicationError(
            "Serialized targeted publication receipt is not valid JSON."
        ) from exc

    return targeted_candidate_publication_receipt_from_dict(value)


class TargetedCandidatePublicationReceiptStore:
    """Explicit-root immutable store for completion receipts only."""

    def __init__(self, root: str | Path) -> None:
        self.root = _explicit_absolute_root(root, field_name="receipt_store_root")

    @staticmethod
    def _sha_id_hex(value: str, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise TargetedCandidatePublicationError(
                f"{field_name} must be a sha256:<hex> identifier."
            )

        match = _SHA256_ID_RE.fullmatch(value)
        if match is None:
            raise TargetedCandidatePublicationError(
                f"{field_name} must be a sha256:<hex> identifier."
            )

        return value.removeprefix("sha256:")

    def _receipt_path(
        self,
        *,
        candidate_record_id: str,
        receipt_id: str,
    ) -> Path:
        candidate_hex = self._sha_id_hex(
            candidate_record_id,
            field_name="candidate_record_id",
        )
        receipt_hex = self._sha_id_hex(
            receipt_id,
            field_name="receipt_id",
        )
        return (
            self.root
            / "targeted_candidate_publication_receipts"
            / candidate_hex
            / f"{receipt_hex}.json"
        )

    def publish_receipt(
        self,
        receipt: TargetedCandidatePublicationReceipt,
    ) -> None:
        validate_targeted_candidate_publication_receipt(receipt)
        payload = dumps_targeted_candidate_publication_receipt(receipt).encode(
            "utf-8"
        )
        path = self._receipt_path(
            candidate_record_id=receipt.candidate_record_id,
            receipt_id=receipt.receipt_id,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with path.open("xb") as handle:
                handle.write(payload)
        except FileExistsError:
            if path.read_bytes() != payload:
                _fail(
                    "Immutable targeted publication receipt exists with "
                    "different bytes."
                )
            return

        if path.read_bytes() != payload:
            _fail("Published targeted publication receipt failed read-back.")

    def load_receipt(
        self,
        *,
        candidate_record_id: str,
        receipt_id: str,
    ) -> TargetedCandidatePublicationReceipt:
        path = self._receipt_path(
            candidate_record_id=candidate_record_id,
            receipt_id=receipt_id,
        )

        if not path.is_file():
            _fail("Targeted publication receipt does not exist.")

        try:
            receipt = loads_targeted_candidate_publication_receipt(
                path.read_text(encoding="utf-8")
            )
        except UnicodeDecodeError as exc:
            raise TargetedCandidatePublicationError(
                "Stored targeted publication receipt is not valid UTF-8."
            ) from exc

        if receipt.candidate_record_id != candidate_record_id:
            _fail("Stored receipt candidate coordinate differs.")
        if receipt.receipt_id != receipt_id:
            _fail("Stored receipt identity differs.")

        return receipt


class TargetedCandidatePublicationCoordinator:
    """Coordinate one targeted candidate using an immutable completion marker."""

    def __init__(
        self,
        *,
        candidate_store_root: str | Path,
        lineage_store_root: str | Path,
        receipt_store_root: str | Path,
    ) -> None:
        candidate_root = _explicit_absolute_root(
            candidate_store_root,
            field_name="candidate_store_root",
        )
        lineage_root = _explicit_absolute_root(
            lineage_store_root,
            field_name="lineage_store_root",
        )
        receipt_root = _explicit_absolute_root(
            receipt_store_root,
            field_name="receipt_store_root",
        )

        resolved = (
            candidate_root.resolve(strict=False),
            lineage_root.resolve(strict=False),
            receipt_root.resolve(strict=False),
        )
        if len(set(resolved)) != 3:
            _fail("Candidate, lineage, and receipt store roots must be distinct.")

        self.candidate_store = CandidateTranscriptionStore(candidate_root)
        self.lineage_store = CandidateCropLineageStore(lineage_root)
        self.receipt_store = TargetedCandidatePublicationReceiptStore(
            receipt_root
        )

    def publish(
        self,
        *,
        candidate_record: CandidateTranscriptionRecord,
        transcription_text: str,
        crop_receipt: CroppedArtifactReceipt,
        binding: CandidateCropLineageBinding,
    ) -> TargetedCandidatePublicationReceipt:
        """Publish and complete one targeted candidate, failing closed."""

        validate_candidate_crop_publication_unit(
            candidate_record=candidate_record,
            transcription_text=transcription_text,
            crop_receipt=crop_receipt,
            binding=binding,
        )

        self.candidate_store.publish_candidate(
            record=candidate_record,
            transcription_text=transcription_text,
        )
        self.lineage_store.publish_binding(binding)

        loaded_candidate = self.candidate_store.load_candidate(
            candidate_record.record_id
        )
        loaded_text = self.candidate_store.read_transcription(loaded_candidate)
        loaded_binding = self.lineage_store.load_binding(
            candidate_record_id=binding.candidate_record_id,
            binding_id=binding.binding_id,
        )

        validate_candidate_crop_publication_unit(
            candidate_record=loaded_candidate,
            transcription_text=loaded_text,
            crop_receipt=crop_receipt,
            binding=loaded_binding,
        )

        receipt = build_targeted_candidate_publication_receipt(
            candidate_record=loaded_candidate,
            transcription_text=loaded_text,
            binding=loaded_binding,
        )
        self.receipt_store.publish_receipt(receipt)

        return self.resolve(
            candidate_record_id=receipt.candidate_record_id,
            receipt_id=receipt.receipt_id,
            crop_receipt=crop_receipt,
        )

    def resolve(
        self,
        *,
        candidate_record_id: str,
        receipt_id: str,
        crop_receipt: CroppedArtifactReceipt,
    ) -> TargetedCandidatePublicationReceipt:
        """Resolve completion only when receipt, candidate, text, and lineage agree."""

        receipt = self.receipt_store.load_receipt(
            candidate_record_id=candidate_record_id,
            receipt_id=receipt_id,
        )
        candidate_record = self.candidate_store.load_candidate(
            receipt.candidate_record_id
        )
        transcription_text = self.candidate_store.read_transcription(
            candidate_record
        )
        binding = self.lineage_store.load_binding(
            candidate_record_id=receipt.candidate_record_id,
            binding_id=receipt.binding_id,
        )

        validate_candidate_crop_publication_unit(
            candidate_record=candidate_record,
            transcription_text=transcription_text,
            crop_receipt=crop_receipt,
            binding=binding,
        )

        expected_receipt = build_targeted_candidate_publication_receipt(
            candidate_record=candidate_record,
            transcription_text=transcription_text,
            binding=binding,
        )
        if receipt != expected_receipt:
            _fail("Stored completion receipt does not match resolved publication.")

        return receipt


__all__ = [
    "TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION",
    "TargetedCandidatePublicationCoordinator",
    "TargetedCandidatePublicationError",
    "TargetedCandidatePublicationReceipt",
    "TargetedCandidatePublicationReceiptStore",
    "build_targeted_candidate_publication_receipt",
    "dumps_targeted_candidate_publication_receipt",
    "loads_targeted_candidate_publication_receipt",
    "targeted_candidate_publication_identity_payload",
    "targeted_candidate_publication_receipt_from_dict",
    "targeted_candidate_publication_receipt_id",
    "targeted_candidate_publication_receipt_to_dict",
    "validate_targeted_candidate_publication_receipt",
]
