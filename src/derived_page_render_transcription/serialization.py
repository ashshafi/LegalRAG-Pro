from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from .models import PageRenderTranscriptionRecord


def record_to_dict(value: PageRenderTranscriptionRecord) -> dict[str, object]:
    if not isinstance(value, PageRenderTranscriptionRecord):
        raise TypeError("value must be a PageRenderTranscriptionRecord.")
    return asdict(value)


def record_identity_payload_to_dict(
    value: PageRenderTranscriptionRecord,
) -> dict[str, object]:
    data = record_to_dict(value)
    data.pop("record_id")
    return data


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def derive_record_id(value: PageRenderTranscriptionRecord) -> str:
    payload = record_identity_payload_to_dict(value)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def dumps_record(value: PageRenderTranscriptionRecord) -> str:
    return _canonical_json_bytes(record_to_dict(value)).decode("utf-8") + "\n"


def loads_record(payload: str) -> PageRenderTranscriptionRecord:
    if not isinstance(payload, str):
        raise TypeError("payload must be text.")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Derived page-render record is not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ValueError("Derived page-render record must be a JSON object.")

    expected = {
        field
        for field in PageRenderTranscriptionRecord.__dataclass_fields__
    }
    if set(data) != expected:
        raise ValueError("Derived page-render record fields are not exact.")

    steps = data.get("preprocessing_steps")
    if not isinstance(steps, list) or any(not isinstance(item, str) for item in steps):
        raise ValueError("preprocessing_steps must be a JSON string array.")
    data["preprocessing_steps"] = tuple(steps)

    try:
        return PageRenderTranscriptionRecord(**data)
    except TypeError as exc:
        raise ValueError("Derived page-render record fields are invalid.") from exc


__all__ = [
    "derive_record_id",
    "dumps_record",
    "loads_record",
    "record_identity_payload_to_dict",
    "record_to_dict",
]
