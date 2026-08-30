from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any

from .models import DerivedTranscriptionRecord


_RECORD_FIELDS = tuple(
    DerivedTranscriptionRecord.__dataclass_fields__.keys()
)


def record_to_dict(
    value: DerivedTranscriptionRecord,
) -> dict[str, Any]:
    if not isinstance(value, DerivedTranscriptionRecord):
        raise TypeError(
            "value must be a DerivedTranscriptionRecord."
        )

    data = asdict(value)
    data["preprocessing_steps"] = list(
        value.preprocessing_steps
    )
    return data


def record_identity_payload_to_dict(
    value: DerivedTranscriptionRecord,
) -> dict[str, Any]:
    data = record_to_dict(value)
    data.pop("record_id")
    return data


def _canonical_json_bytes(
    value: dict[str, Any],
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def derive_record_id(
    value: DerivedTranscriptionRecord,
) -> str:
    payload = record_identity_payload_to_dict(value)

    digest = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()

    return f"sha256:{digest}"


def dumps_record(
    value: DerivedTranscriptionRecord,
) -> str:
    return _canonical_json_bytes(
        record_to_dict(value)
    ).decode("utf-8")


def loads_record(
    value: str,
) -> DerivedTranscriptionRecord:
    if not isinstance(value, str):
        raise TypeError("value must be text.")

    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Derived transcription record is not valid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Derived transcription record must be a JSON object."
        )

    if set(data) != set(_RECORD_FIELDS):
        raise ValueError(
            "Derived transcription record fields are not exact."
        )

    steps = data.get("preprocessing_steps")

    if not isinstance(steps, list):
        raise ValueError(
            "preprocessing_steps must be a JSON array."
        )

    data["preprocessing_steps"] = tuple(steps)

    return DerivedTranscriptionRecord(**data)


__all__ = [
    "derive_record_id",
    "dumps_record",
    "loads_record",
    "record_identity_payload_to_dict",
    "record_to_dict",
]
