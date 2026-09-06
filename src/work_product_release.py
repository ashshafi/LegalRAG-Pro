"""Professional work-product release state for exact rendered artifacts.

This module is deliberately separate from analytical review, legal-authority
verification, report rendering, task persistence and AI output.

Important invariants:

CAA professional review != work-product release review.
LEGAL_AUTHORITY verified != work product approved.
Work-product authority checking != work-product release approval.
Working export != approved for reliance.
APPROVED_FOR_RELIANCE != court or tribunal reliance unless that reliance is
explicitly approved by the professional release event.

Re-rendered bytes != previously approved artifact.
Changed report projection != previous approval transferred.
Work-product approval != factual proposition proved.
Work-product approval != governed case assessment changed.
Work-product approval != CAA / PRW / MAL1 / GAR1 state changed.

Only an explicit professional release event may establish
APPROVED_FOR_RELIANCE for one exact rendered artifact target.
Missing release history is WORKING, not approved.

The module does not render reports, research law, call a network service,
alter analytical authority, or make an automatic release decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable


WORK_PRODUCT_RELEASE_SCHEMA_VERSION = "work-product-release-event/1.0"
WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION = "work-product-release-target/1.0"
_DEFAULT_ROOT = Path("work_product_release")
_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_ALLOWED_FORMATS = {"markdown", "html", "pdf"}


class WorkProductReleaseError(RuntimeError):
    """Fail-closed work-product release error."""


class WorkProductReleaseDecision(StrEnum):
    APPROVED_FOR_RELIANCE = "APPROVED_FOR_RELIANCE"
    REJECTED = "REJECTED"


class WorkProductReleaseState(StrEnum):
    WORKING = "WORKING"
    APPROVED_FOR_RELIANCE = "APPROVED_FOR_RELIANCE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class WorkProductReleaseTarget:
    schema_version: str
    case_id: str
    report_projection_id: str
    projection_payload_sha256: str
    manifest_id: str
    artifact_format: str
    artifact_id: str
    artifact_sha256: str
    renderer_version: str
    output_profile: str
    target_id: str


@dataclass(frozen=True, slots=True)
class WorkProductReleaseEvent:
    schema_version: str
    event_id: str
    recorded_at: str
    case_id: str
    target_id: str
    report_projection_id: str
    projection_payload_sha256: str
    manifest_id: str
    artifact_format: str
    artifact_id: str
    artifact_sha256: str
    renderer_version: str
    output_profile: str
    decision: WorkProductReleaseDecision
    factual_basis_reviewed: bool
    legal_authorities_reviewed: bool
    unverified_authorities_remaining: int
    professional_judgment_completed: bool
    court_or_tribunal_reliance: bool
    reviewer_reference: str
    review_note: str
    previous_event_id: str | None


@dataclass(frozen=True, slots=True)
class WorkProductReleaseProjection:
    target: WorkProductReleaseTarget
    state: WorkProductReleaseState
    latest_event_id: str | None
    recorded_at: str | None
    reviewer_reference: str | None
    court_or_tribunal_reliance: bool


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise WorkProductReleaseError(field_name + " must be text.")
    result = value.strip()
    if not result:
        raise WorkProductReleaseError(field_name + " must not be blank.")
    return result


def _case_id(value: object) -> str:
    result = _required(value, "case_id")
    if not _SAFE_CASE_ID.fullmatch(result) or result in {".", ".."}:
        raise WorkProductReleaseError("case_id is invalid.")
    return result


def _uuid(value: object, field_name: str) -> str:
    result = _required(value, field_name).lower()
    if not _UUID.fullmatch(result):
        raise WorkProductReleaseError(field_name + " must be a canonical UUID.")
    return result


def _sha256_hex(value: object, field_name: str) -> str:
    result = _required(value, field_name).lower()
    if not _SHA256_HEX.fullmatch(result):
        raise WorkProductReleaseError(field_name + " must be SHA-256 hex.")
    return result


def _sha256_id(value: object, field_name: str) -> str:
    result = _required(value, field_name).lower()
    if not _SHA256_ID.fullmatch(result):
        raise WorkProductReleaseError(field_name + " must be a sha256: identity.")
    return result


def _strict_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise WorkProductReleaseError(field_name + " must be boolean.")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkProductReleaseError(field_name + " must be a non-negative integer.")
    return value


def _format(value: object) -> str:
    result = _required(value, "artifact_format").lower()
    if result not in _ALLOWED_FORMATS:
        raise WorkProductReleaseError(
            "artifact_format must be markdown, html or pdf."
        )
    return result


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_id(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _timestamp(value: object) -> str:
    result = _required(value, "recorded_at")
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkProductReleaseError("recorded_at must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise WorkProductReleaseError("recorded_at must include a timezone.")
    return result


def _root(root: object = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("LEGALRAG_WORK_PRODUCT_RELEASE_ROOT", "").strip()
    return Path(configured) if configured else _DEFAULT_ROOT


def release_event_path(case_id: str, *, root=None) -> Path:
    return _root(root) / _case_id(case_id) / "events.jsonl"


def _artifact_identity(
    artifact: object,
    artifact_format: str,
) -> tuple[str, str, bytes]:
    fmt = _format(artifact_format)
    id_field = {
        "markdown": "markdown_report_id",
        "html": "html_report_id",
        "pdf": "pdf_report_id",
    }[fmt]
    sha_field = {
        "markdown": "markdown_sha256",
        "html": "html_sha256",
        "pdf": "pdf_sha256",
    }[fmt]
    payload_field = {
        "markdown": "markdown",
        "html": "html",
        "pdf": "pdf",
    }[fmt]

    try:
        artifact_id = _uuid(getattr(artifact, id_field), "artifact_id")
        artifact_sha256 = _sha256_hex(
            getattr(artifact, sha_field),
            "artifact_sha256",
        )
        payload = getattr(artifact, payload_field)
    except AttributeError as exc:
        raise WorkProductReleaseError(
            "artifact does not provide the required renderer identity."
        ) from exc

    if fmt in {"markdown", "html"}:
        if not isinstance(payload, str) or not payload:
            raise WorkProductReleaseError(
                "text report artifact must contain non-empty text."
            )
        artifact_bytes = payload.encode("utf-8")
    else:
        if not isinstance(payload, bytes) or not payload:
            raise WorkProductReleaseError(
                "PDF report artifact must contain non-empty immutable bytes."
            )
        artifact_bytes = payload

    actual_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if actual_sha256 != artifact_sha256:
        raise WorkProductReleaseError(
            "artifact SHA-256 does not match exact rendered bytes."
        )
    return artifact_id, artifact_sha256, artifact_bytes


def build_work_product_release_target(
    *,
    projection: object,
    artifact: object,
    artifact_format: str,
) -> WorkProductReleaseTarget:
    """Bind professional release to one exact projection and rendered artifact."""

    fmt = _format(artifact_format)
    try:
        case_header = getattr(projection, "case_header")
        case_id = _case_id(getattr(case_header, "case_id"))
        report_projection_id = _uuid(
            getattr(projection, "report_projection_id"),
            "report_projection_id",
        )
        projection_payload_sha256 = _sha256_hex(
            getattr(projection, "projection_payload_sha256"),
            "projection_payload_sha256",
        )
        manifest = getattr(projection, "manifest")
        manifest_id = _uuid(getattr(manifest, "manifest_id"), "manifest_id")
    except AttributeError as exc:
        raise WorkProductReleaseError(
            "projection does not provide the required report identity."
        ) from exc

    artifact_id, artifact_sha256, _ = _artifact_identity(artifact, fmt)

    try:
        artifact_projection_id = _uuid(
            getattr(artifact, "report_projection_id"),
            "artifact.report_projection_id",
        )
        artifact_projection_sha = _sha256_hex(
            getattr(artifact, "projection_payload_sha256"),
            "artifact.projection_payload_sha256",
        )
        artifact_manifest_id = _uuid(
            getattr(artifact, "manifest_id"),
            "artifact.manifest_id",
        )
        renderer_version = _required(
            getattr(artifact, "renderer_version"),
            "renderer_version",
        )
        output_profile = _required(
            getattr(artifact, "output_profile"),
            "output_profile",
        )
        artifact_manifest = getattr(artifact, "report_manifest")
    except AttributeError as exc:
        raise WorkProductReleaseError(
            "artifact does not provide the required report binding."
        ) from exc

    if artifact_projection_id != report_projection_id:
        raise WorkProductReleaseError(
            "artifact report projection ID does not match projection."
        )
    if artifact_projection_sha != projection_payload_sha256:
        raise WorkProductReleaseError(
            "artifact projection payload SHA does not match projection."
        )
    if artifact_manifest_id != manifest_id:
        raise WorkProductReleaseError(
            "artifact manifest ID does not match projection."
        )
    if artifact_manifest != manifest:
        raise WorkProductReleaseError(
            "artifact report manifest does not match projection."
        )

    identity_payload = {
        "schema_version": WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION,
        "case_id": case_id,
        "report_projection_id": report_projection_id,
        "projection_payload_sha256": projection_payload_sha256,
        "manifest_id": manifest_id,
        "artifact_format": fmt,
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "renderer_version": renderer_version,
        "output_profile": output_profile,
    }

    return WorkProductReleaseTarget(
        schema_version=WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION,
        case_id=case_id,
        report_projection_id=report_projection_id,
        projection_payload_sha256=projection_payload_sha256,
        manifest_id=manifest_id,
        artifact_format=fmt,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        renderer_version=renderer_version,
        output_profile=output_profile,
        target_id=_derive_id(identity_payload),
    )


def _validate_target(target: WorkProductReleaseTarget) -> None:
    if target.schema_version != WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION:
        raise WorkProductReleaseError(
            "Unsupported work-product release target schema."
        )
    if _case_id(target.case_id) != target.case_id:
        raise WorkProductReleaseError("case_id is not canonical.")
    if _uuid(
        target.report_projection_id,
        "report_projection_id",
    ) != target.report_projection_id:
        raise WorkProductReleaseError(
            "report_projection_id is not canonical."
        )
    if _sha256_hex(
        target.projection_payload_sha256,
        "projection_payload_sha256",
    ) != target.projection_payload_sha256:
        raise WorkProductReleaseError(
            "projection_payload_sha256 is not canonical."
        )
    if _uuid(target.manifest_id, "manifest_id") != target.manifest_id:
        raise WorkProductReleaseError("manifest_id is not canonical.")
    if _format(target.artifact_format) != target.artifact_format:
        raise WorkProductReleaseError("artifact_format is not canonical.")
    if _uuid(target.artifact_id, "artifact_id") != target.artifact_id:
        raise WorkProductReleaseError("artifact_id is not canonical.")
    if _sha256_hex(
        target.artifact_sha256,
        "artifact_sha256",
    ) != target.artifact_sha256:
        raise WorkProductReleaseError("artifact_sha256 is not canonical.")
    if _required(
        target.renderer_version,
        "renderer_version",
    ) != target.renderer_version:
        raise WorkProductReleaseError("renderer_version is not canonical.")
    if _required(
        target.output_profile,
        "output_profile",
    ) != target.output_profile:
        raise WorkProductReleaseError("output_profile is not canonical.")
    _sha256_id(target.target_id, "target_id")

    identity_payload = {
        "schema_version": target.schema_version,
        "case_id": target.case_id,
        "report_projection_id": target.report_projection_id,
        "projection_payload_sha256": target.projection_payload_sha256,
        "manifest_id": target.manifest_id,
        "artifact_format": target.artifact_format,
        "artifact_id": target.artifact_id,
        "artifact_sha256": target.artifact_sha256,
        "renderer_version": target.renderer_version,
        "output_profile": target.output_profile,
    }
    expected = _derive_id(identity_payload)
    if target.target_id != expected:
        raise WorkProductReleaseError(
            "target_id does not match canonical work-product identity."
        )


def _target_from_event(event: WorkProductReleaseEvent) -> WorkProductReleaseTarget:
    target = WorkProductReleaseTarget(
        schema_version=WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION,
        case_id=event.case_id,
        report_projection_id=event.report_projection_id,
        projection_payload_sha256=event.projection_payload_sha256,
        manifest_id=event.manifest_id,
        artifact_format=event.artifact_format,
        artifact_id=event.artifact_id,
        artifact_sha256=event.artifact_sha256,
        renderer_version=event.renderer_version,
        output_profile=event.output_profile,
        target_id=event.target_id,
    )
    _validate_target(target)
    return target


def _event_identity_payload(event: WorkProductReleaseEvent) -> dict[str, Any]:
    value = asdict(event)
    value.pop("event_id", None)
    value["decision"] = event.decision.value
    return value


def _validate_event(event: WorkProductReleaseEvent) -> None:
    if event.schema_version != WORK_PRODUCT_RELEASE_SCHEMA_VERSION:
        raise WorkProductReleaseError(
            "Unsupported work-product release event schema."
        )
    _timestamp(event.recorded_at)
    if not isinstance(event.decision, WorkProductReleaseDecision):
        raise WorkProductReleaseError("decision is invalid.")
    _target_from_event(event)
    _strict_bool(event.factual_basis_reviewed, "factual_basis_reviewed")
    _strict_bool(
        event.legal_authorities_reviewed,
        "legal_authorities_reviewed",
    )
    _non_negative_int(
        event.unverified_authorities_remaining,
        "unverified_authorities_remaining",
    )
    _strict_bool(
        event.professional_judgment_completed,
        "professional_judgment_completed",
    )
    _strict_bool(
        event.court_or_tribunal_reliance,
        "court_or_tribunal_reliance",
    )
    _required(event.reviewer_reference, "reviewer_reference")
    _required(event.review_note, "review_note")
    if event.previous_event_id is not None:
        _sha256_id(event.previous_event_id, "previous_event_id")

    if event.decision is WorkProductReleaseDecision.APPROVED_FOR_RELIANCE:
        if not (
            event.factual_basis_reviewed
            and event.legal_authorities_reviewed
            and event.unverified_authorities_remaining == 0
            and event.professional_judgment_completed
        ):
            raise WorkProductReleaseError(
                "APPROVED_FOR_RELIANCE requires factual-basis review, "
                "legal-authority review, zero unverified authorities, and "
                "completed professional judgment."
            )
    elif event.court_or_tribunal_reliance:
        raise WorkProductReleaseError(
            "Court or tribunal reliance cannot be approved by a rejected event."
        )

    expected = _derive_id(_event_identity_payload(event))
    if expected != event.event_id:
        raise WorkProductReleaseError(
            "event_id does not match canonical work-product release identity."
        )


def _event_to_dict(event: WorkProductReleaseEvent) -> dict[str, Any]:
    value = asdict(event)
    value["decision"] = event.decision.value
    return value


def _event_from_dict(value: object) -> WorkProductReleaseEvent:
    if not isinstance(value, dict):
        raise WorkProductReleaseError("Release event must be a JSON object.")
    expected_keys = {
        "schema_version",
        "event_id",
        "recorded_at",
        "case_id",
        "target_id",
        "report_projection_id",
        "projection_payload_sha256",
        "manifest_id",
        "artifact_format",
        "artifact_id",
        "artifact_sha256",
        "renderer_version",
        "output_profile",
        "decision",
        "factual_basis_reviewed",
        "legal_authorities_reviewed",
        "unverified_authorities_remaining",
        "professional_judgment_completed",
        "court_or_tribunal_reliance",
        "reviewer_reference",
        "review_note",
        "previous_event_id",
    }
    if set(value) != expected_keys:
        raise WorkProductReleaseError("Release event keys are invalid.")

    try:
        event = WorkProductReleaseEvent(
            schema_version=_required(value["schema_version"], "schema_version"),
            event_id=_sha256_id(value["event_id"], "event_id"),
            recorded_at=_timestamp(value["recorded_at"]),
            case_id=_case_id(value["case_id"]),
            target_id=_sha256_id(value["target_id"], "target_id"),
            report_projection_id=_uuid(
                value["report_projection_id"],
                "report_projection_id",
            ),
            projection_payload_sha256=_sha256_hex(
                value["projection_payload_sha256"],
                "projection_payload_sha256",
            ),
            manifest_id=_uuid(value["manifest_id"], "manifest_id"),
            artifact_format=_format(value["artifact_format"]),
            artifact_id=_uuid(value["artifact_id"], "artifact_id"),
            artifact_sha256=_sha256_hex(
                value["artifact_sha256"],
                "artifact_sha256",
            ),
            renderer_version=_required(
                value["renderer_version"],
                "renderer_version",
            ),
            output_profile=_required(
                value["output_profile"],
                "output_profile",
            ),
            decision=WorkProductReleaseDecision(value["decision"]),
            factual_basis_reviewed=_strict_bool(
                value["factual_basis_reviewed"],
                "factual_basis_reviewed",
            ),
            legal_authorities_reviewed=_strict_bool(
                value["legal_authorities_reviewed"],
                "legal_authorities_reviewed",
            ),
            unverified_authorities_remaining=_non_negative_int(
                value["unverified_authorities_remaining"],
                "unverified_authorities_remaining",
            ),
            professional_judgment_completed=_strict_bool(
                value["professional_judgment_completed"],
                "professional_judgment_completed",
            ),
            court_or_tribunal_reliance=_strict_bool(
                value["court_or_tribunal_reliance"],
                "court_or_tribunal_reliance",
            ),
            reviewer_reference=_required(
                value["reviewer_reference"],
                "reviewer_reference",
            ),
            review_note=_required(value["review_note"], "review_note"),
            previous_event_id=(
                None
                if value["previous_event_id"] is None
                else _sha256_id(
                    value["previous_event_id"],
                    "previous_event_id",
                )
            ),
        )
    except (TypeError, ValueError) as exc:
        raise WorkProductReleaseError("Release event is invalid.") from exc
    _validate_event(event)
    return event


def load_work_product_release_events(
    case_id: str,
    *,
    root=None,
) -> tuple[WorkProductReleaseEvent, ...]:
    canonical_case_id = _case_id(case_id)
    path = release_event_path(canonical_case_id, root=root)
    if not path.exists():
        return ()
    if not path.is_file():
        raise WorkProductReleaseError("Release event path is not a file.")

    events: list[WorkProductReleaseEvent] = []
    seen_event_ids: set[str] = set()
    latest_by_target: dict[str, str] = {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise WorkProductReleaseError(
            "Release event history could not be read."
        ) from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise WorkProductReleaseError(
                f"Release event history contains a blank line at {line_number}."
            )
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkProductReleaseError(
                f"Release event history contains invalid JSON at line {line_number}."
            ) from exc

        event = _event_from_dict(raw)
        if event.case_id != canonical_case_id:
            raise WorkProductReleaseError(
                "Release event history mixes case identities."
            )
        if event.event_id in seen_event_ids:
            raise WorkProductReleaseError(
                "Release event history contains a duplicate event."
            )
        expected_previous = latest_by_target.get(event.target_id)
        if event.previous_event_id != expected_previous:
            raise WorkProductReleaseError(
                "Release event history contains an invalid target event chain."
            )
        seen_event_ids.add(event.event_id)
        latest_by_target[event.target_id] = event.event_id
        events.append(event)

    return tuple(events)


def _validated_event_sequence(
    events: Iterable[WorkProductReleaseEvent],
    *,
    case_id: str,
) -> tuple[WorkProductReleaseEvent, ...]:
    canonical_case_id = _case_id(case_id)
    result: list[WorkProductReleaseEvent] = []
    seen_event_ids: set[str] = set()
    latest_by_target: dict[str, str] = {}

    for event in events:
        _validate_event(event)
        if event.case_id != canonical_case_id:
            raise WorkProductReleaseError(
                "Release events mix case identities."
            )
        if event.event_id in seen_event_ids:
            raise WorkProductReleaseError(
                "Release events contain a duplicate event."
            )
        expected_previous = latest_by_target.get(event.target_id)
        if event.previous_event_id != expected_previous:
            raise WorkProductReleaseError(
                "Release events contain an invalid target event chain."
            )
        seen_event_ids.add(event.event_id)
        latest_by_target[event.target_id] = event.event_id
        result.append(event)

    return tuple(result)


def _current_event(
    target: WorkProductReleaseTarget,
    events: Iterable[WorkProductReleaseEvent],
) -> WorkProductReleaseEvent | None:
    _validate_target(target)
    current = None
    for event in _validated_event_sequence(events, case_id=target.case_id):
        if event.target_id == target.target_id:
            current = event
    return current


def project_work_product_release(
    *,
    target: WorkProductReleaseTarget,
    events: Iterable[WorkProductReleaseEvent],
) -> WorkProductReleaseProjection:
    current = _current_event(target, events)
    if current is None:
        return WorkProductReleaseProjection(
            target=target,
            state=WorkProductReleaseState.WORKING,
            latest_event_id=None,
            recorded_at=None,
            reviewer_reference=None,
            court_or_tribunal_reliance=False,
        )

    state = (
        WorkProductReleaseState.APPROVED_FOR_RELIANCE
        if current.decision is WorkProductReleaseDecision.APPROVED_FOR_RELIANCE
        else WorkProductReleaseState.REJECTED
    )
    return WorkProductReleaseProjection(
        target=target,
        state=state,
        latest_event_id=current.event_id,
        recorded_at=current.recorded_at,
        reviewer_reference=current.reviewer_reference,
        court_or_tribunal_reliance=current.court_or_tribunal_reliance,
    )


def record_work_product_release(
    *,
    target: WorkProductReleaseTarget,
    decision: WorkProductReleaseDecision | str,
    factual_basis_reviewed: bool,
    legal_authorities_reviewed: bool,
    unverified_authorities_remaining: int,
    professional_judgment_completed: bool,
    court_or_tribunal_reliance: bool,
    reviewer_reference: str,
    review_note: str,
    root=None,
) -> WorkProductReleaseEvent:
    """Append one explicit professional release decision for an exact artifact."""

    _validate_target(target)
    try:
        decision_value = WorkProductReleaseDecision(decision)
    except (TypeError, ValueError) as exc:
        raise WorkProductReleaseError("decision is invalid.") from exc

    existing = load_work_product_release_events(target.case_id, root=root)
    previous = _current_event(target, existing)
    recorded_at = _now()

    provisional = WorkProductReleaseEvent(
        schema_version=WORK_PRODUCT_RELEASE_SCHEMA_VERSION,
        event_id="sha256:" + ("0" * 64),
        recorded_at=recorded_at,
        case_id=target.case_id,
        target_id=target.target_id,
        report_projection_id=target.report_projection_id,
        projection_payload_sha256=target.projection_payload_sha256,
        manifest_id=target.manifest_id,
        artifact_format=target.artifact_format,
        artifact_id=target.artifact_id,
        artifact_sha256=target.artifact_sha256,
        renderer_version=target.renderer_version,
        output_profile=target.output_profile,
        decision=decision_value,
        factual_basis_reviewed=_strict_bool(
            factual_basis_reviewed,
            "factual_basis_reviewed",
        ),
        legal_authorities_reviewed=_strict_bool(
            legal_authorities_reviewed,
            "legal_authorities_reviewed",
        ),
        unverified_authorities_remaining=_non_negative_int(
            unverified_authorities_remaining,
            "unverified_authorities_remaining",
        ),
        professional_judgment_completed=_strict_bool(
            professional_judgment_completed,
            "professional_judgment_completed",
        ),
        court_or_tribunal_reliance=_strict_bool(
            court_or_tribunal_reliance,
            "court_or_tribunal_reliance",
        ),
        reviewer_reference=_required(
            reviewer_reference,
            "reviewer_reference",
        ),
        review_note=_required(review_note, "review_note"),
        previous_event_id=None if previous is None else previous.event_id,
    )
    event = WorkProductReleaseEvent(
        **{
            **asdict(provisional),
            "event_id": _derive_id(_event_identity_payload(provisional)),
        }
    )
    _validate_event(event)

    path = release_event_path(target.case_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        _event_to_dict(event),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise WorkProductReleaseError(
            "Release event could not be appended."
        ) from exc

    return event


def assert_work_product_approved_for_reliance(
    *,
    target: WorkProductReleaseTarget,
    events: Iterable[WorkProductReleaseEvent],
) -> WorkProductReleaseProjection:
    projection = project_work_product_release(target=target, events=events)
    if projection.state is not WorkProductReleaseState.APPROVED_FOR_RELIANCE:
        raise WorkProductReleaseError(
            "Work product is not currently professionally approved for reliance."
        )
    return projection


def assert_work_product_approved_for_court_or_tribunal_reliance(
    *,
    target: WorkProductReleaseTarget,
    events: Iterable[WorkProductReleaseEvent],
) -> WorkProductReleaseProjection:
    projection = assert_work_product_approved_for_reliance(
        target=target,
        events=events,
    )
    if not projection.court_or_tribunal_reliance:
        raise WorkProductReleaseError(
            "Work product is not professionally approved for court or tribunal reliance."
        )
    return projection


__all__ = [
    "WORK_PRODUCT_RELEASE_SCHEMA_VERSION",
    "WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION",
    "WorkProductReleaseDecision",
    "WorkProductReleaseError",
    "WorkProductReleaseEvent",
    "WorkProductReleaseProjection",
    "WorkProductReleaseState",
    "WorkProductReleaseTarget",
    "assert_work_product_approved_for_court_or_tribunal_reliance",
    "assert_work_product_approved_for_reliance",
    "build_work_product_release_target",
    "load_work_product_release_events",
    "project_work_product_release",
    "record_work_product_release",
    "release_event_path",
]
