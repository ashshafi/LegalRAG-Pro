"""Professional verification state for legal authority already present in a matter.

This module is deliberately separate from evidence classification, source-bound
evidence verification, governed analytical authority and AI output.

Important invariants:

LEGAL_AUTHORITY classification != legal-authority verification.
Source-bound evidence verification != legal-authority verification.
Retrieval or AI generation != legal-authority verification.
Only an explicit professional verification event may establish
VERIFIED_FOR_RELIANCE for one exact matter-bound authority target.

LEGAL_AUTHORITY verified != factual proposition proved.
LEGAL_AUTHORITY verified != governed case assessment changed.
LEGAL_AUTHORITY verified != work product approved or court-ready.

The module does not research law, call a network service, alter analytical
authority, or make any court-readiness decision.
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

from evidence_classification import EvidenceSourceType


LEGAL_AUTHORITY_VERIFICATION_SCHEMA_VERSION = "legal-authority-verification-event/1.0"
LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION = "legal-authority-verification-target/1.0"
_DEFAULT_ROOT = Path("legal_authority_verification")
_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class LegalAuthorityVerificationError(RuntimeError):
    """Fail-closed legal-authority verification error."""


class LegalAuthorityVerificationDecision(StrEnum):
    VERIFIED_FOR_RELIANCE = "VERIFIED_FOR_RELIANCE"
    REJECTED = "REJECTED"


class LegalAuthorityVerificationState(StrEnum):
    VERIFIED_FOR_RELIANCE = "VERIFIED_FOR_RELIANCE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class LegalAuthorityVerificationTarget:
    schema_version: str
    case_id: str
    evidence_key: str
    evidence_binding_id: str
    bound_text_sha256: str
    document_name: str
    page: int | None
    authority_reference: str
    target_id: str


@dataclass(frozen=True, slots=True)
class LegalAuthorityVerificationEvent:
    schema_version: str
    event_id: str
    recorded_at: str
    case_id: str
    target_id: str
    evidence_key: str
    evidence_binding_id: str
    bound_text_sha256: str
    document_name: str
    page: int | None
    authority_reference: str
    decision: LegalAuthorityVerificationDecision
    genuine: bool
    citation_verifiable: bool
    relevant_to_matter: bool
    supports_attributed_proposition: bool
    verification_source: str
    verification_source_reference: str
    reviewer_reference: str
    review_note: str
    previous_event_id: str | None


@dataclass(frozen=True, slots=True)
class LegalAuthorityVerificationProjection:
    target: LegalAuthorityVerificationTarget
    state: LegalAuthorityVerificationState
    latest_event_id: str
    recorded_at: str
    reviewer_reference: str
    verification_source: str
    verification_source_reference: str


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise LegalAuthorityVerificationError(field_name + " must be text.")
    result = value.strip()
    if not result:
        raise LegalAuthorityVerificationError(field_name + " must not be blank.")
    return result


def _optional_page(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise LegalAuthorityVerificationError("page must be a positive integer.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise LegalAuthorityVerificationError("page must be a positive integer.") from exc
    if result < 1:
        raise LegalAuthorityVerificationError("page must be a positive integer.")
    return result


def _case_id(value: object) -> str:
    result = _required(value, "case_id")
    if not _SAFE_CASE_ID.fullmatch(result) or result in {".", ".."}:
        raise LegalAuthorityVerificationError("case_id is invalid.")
    return result


def _sha256_hex(value: object, field_name: str) -> str:
    result = _required(value, field_name).lower()
    if not _SHA256_HEX.fullmatch(result):
        raise LegalAuthorityVerificationError(field_name + " must be SHA-256 hex.")
    return result


def _sha256_id(value: object, field_name: str) -> str:
    result = _required(value, field_name).lower()
    if not _SHA256_ID.fullmatch(result):
        raise LegalAuthorityVerificationError(field_name + " must be a sha256: identity.")
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
        raise LegalAuthorityVerificationError("recorded_at must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise LegalAuthorityVerificationError("recorded_at must include a timezone.")
    return result


def _root(root: object = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("LEGALRAG_LEGAL_AUTHORITY_VERIFICATION_ROOT", "").strip()
    return Path(configured) if configured else _DEFAULT_ROOT


def verification_event_path(case_id: str, *, root=None) -> Path:
    return _root(root) / _case_id(case_id) / "events.jsonl"


def _source_type(value: EvidenceSourceType | str) -> EvidenceSourceType:
    try:
        return EvidenceSourceType(value)
    except (TypeError, ValueError) as exc:
        raise LegalAuthorityVerificationError("source_type is invalid.") from exc


def build_legal_authority_verification_target(
    *,
    binding: object,
    source_type: EvidenceSourceType | str,
    authority_reference: str,
) -> LegalAuthorityVerificationTarget:
    """Bind professional verification to one exact matter evidence binding.

    ``binding`` is intentionally consumed by attribute contract rather than by
    importing the source-evidence package. This avoids coupling the professional
    control to source-store implementation or import side effects.
    """

    if _source_type(source_type) is not EvidenceSourceType.LEGAL_AUTHORITY:
        raise LegalAuthorityVerificationError(
            "Only material classified as LEGAL_AUTHORITY may enter legal-authority verification."
        )

    try:
        case_id = _case_id(getattr(binding, "case_id"))
        evidence_key = _required(getattr(binding, "evidence_key"), "evidence_key")
        evidence_binding_id = _sha256_id(
            getattr(binding, "evidence_binding_id"),
            "evidence_binding_id",
        )
        bound_text_sha256 = _sha256_hex(
            getattr(binding, "bound_text_sha256"),
            "bound_text_sha256",
        )
        document_name = _required(getattr(binding, "document_name"), "document_name")
        page = _optional_page(getattr(binding, "page"))
    except AttributeError as exc:
        raise LegalAuthorityVerificationError(
            "binding does not provide the required source-evidence identity."
        ) from exc

    reference = _required(authority_reference, "authority_reference")
    identity_payload = {
        "schema_version": LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION,
        "case_id": case_id,
        "evidence_key": evidence_key,
        "evidence_binding_id": evidence_binding_id,
        "bound_text_sha256": bound_text_sha256,
        "authority_reference": reference,
    }

    return LegalAuthorityVerificationTarget(
        schema_version=LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION,
        case_id=case_id,
        evidence_key=evidence_key,
        evidence_binding_id=evidence_binding_id,
        bound_text_sha256=bound_text_sha256,
        document_name=document_name,
        page=page,
        authority_reference=reference,
        target_id=_derive_id(identity_payload),
    )


def _target_from_event(event: LegalAuthorityVerificationEvent) -> LegalAuthorityVerificationTarget:
    target = LegalAuthorityVerificationTarget(
        schema_version=LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION,
        case_id=event.case_id,
        evidence_key=event.evidence_key,
        evidence_binding_id=event.evidence_binding_id,
        bound_text_sha256=event.bound_text_sha256,
        document_name=event.document_name,
        page=event.page,
        authority_reference=event.authority_reference,
        target_id=event.target_id,
    )
    _validate_target(target)
    return target


def _validate_target(target: LegalAuthorityVerificationTarget) -> None:
    if target.schema_version != LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION:
        raise LegalAuthorityVerificationError("Unsupported legal-authority target schema.")
    rebuilt = build_legal_authority_verification_target(
        binding=type(
            "_Binding",
            (),
            {
                "case_id": target.case_id,
                "evidence_key": target.evidence_key,
                "evidence_binding_id": target.evidence_binding_id,
                "bound_text_sha256": target.bound_text_sha256,
                "document_name": target.document_name,
                "page": target.page,
            },
        )(),
        source_type=EvidenceSourceType.LEGAL_AUTHORITY,
        authority_reference=target.authority_reference,
    )
    if rebuilt.target_id != target.target_id:
        raise LegalAuthorityVerificationError(
            "target_id does not match the canonical legal-authority identity."
        )


def _event_identity_payload(event: LegalAuthorityVerificationEvent) -> dict[str, Any]:
    value = asdict(event)
    value.pop("event_id", None)
    value["decision"] = event.decision.value
    return value


def _validate_event(event: LegalAuthorityVerificationEvent) -> None:
    if event.schema_version != LEGAL_AUTHORITY_VERIFICATION_SCHEMA_VERSION:
        raise LegalAuthorityVerificationError("Unsupported legal-authority verification schema.")
    _timestamp(event.recorded_at)
    _target_from_event(event)
    _required(event.verification_source, "verification_source")
    _required(event.verification_source_reference, "verification_source_reference")
    _required(event.reviewer_reference, "reviewer_reference")
    _required(event.review_note, "review_note")
    if event.previous_event_id is not None:
        _sha256_id(event.previous_event_id, "previous_event_id")
    expected = _derive_id(_event_identity_payload(event))
    if expected != event.event_id:
        raise LegalAuthorityVerificationError(
            "event_id does not match the canonical verification event identity."
        )
    if event.decision is LegalAuthorityVerificationDecision.VERIFIED_FOR_RELIANCE:
        if not (
            event.genuine
            and event.citation_verifiable
            and event.relevant_to_matter
            and event.supports_attributed_proposition
        ):
            raise LegalAuthorityVerificationError(
                "VERIFIED_FOR_RELIANCE requires every professional verification check to pass."
            )


def _event_to_dict(event: LegalAuthorityVerificationEvent) -> dict[str, Any]:
    value = asdict(event)
    value["decision"] = event.decision.value
    return value


def _event_from_dict(value: object) -> LegalAuthorityVerificationEvent:
    if not isinstance(value, dict):
        raise LegalAuthorityVerificationError("Verification event must be a JSON object.")
    expected_keys = {
        "schema_version",
        "event_id",
        "recorded_at",
        "case_id",
        "target_id",
        "evidence_key",
        "evidence_binding_id",
        "bound_text_sha256",
        "document_name",
        "page",
        "authority_reference",
        "decision",
        "genuine",
        "citation_verifiable",
        "relevant_to_matter",
        "supports_attributed_proposition",
        "verification_source",
        "verification_source_reference",
        "reviewer_reference",
        "review_note",
        "previous_event_id",
    }
    if set(value) != expected_keys:
        raise LegalAuthorityVerificationError("Verification event keys are invalid.")
    try:
        event = LegalAuthorityVerificationEvent(
            schema_version=_required(value["schema_version"], "schema_version"),
            event_id=_sha256_id(value["event_id"], "event_id"),
            recorded_at=_timestamp(value["recorded_at"]),
            case_id=_case_id(value["case_id"]),
            target_id=_sha256_id(value["target_id"], "target_id"),
            evidence_key=_required(value["evidence_key"], "evidence_key"),
            evidence_binding_id=_sha256_id(
                value["evidence_binding_id"],
                "evidence_binding_id",
            ),
            bound_text_sha256=_sha256_hex(
                value["bound_text_sha256"],
                "bound_text_sha256",
            ),
            document_name=_required(value["document_name"], "document_name"),
            page=_optional_page(value["page"]),
            authority_reference=_required(
                value["authority_reference"],
                "authority_reference",
            ),
            decision=LegalAuthorityVerificationDecision(value["decision"]),
            genuine=_strict_bool(value["genuine"], "genuine"),
            citation_verifiable=_strict_bool(
                value["citation_verifiable"],
                "citation_verifiable",
            ),
            relevant_to_matter=_strict_bool(
                value["relevant_to_matter"],
                "relevant_to_matter",
            ),
            supports_attributed_proposition=_strict_bool(
                value["supports_attributed_proposition"],
                "supports_attributed_proposition",
            ),
            verification_source=_required(
                value["verification_source"],
                "verification_source",
            ),
            verification_source_reference=_required(
                value["verification_source_reference"],
                "verification_source_reference",
            ),
            reviewer_reference=_required(
                value["reviewer_reference"],
                "reviewer_reference",
            ),
            review_note=_required(value["review_note"], "review_note"),
            previous_event_id=(
                None
                if value["previous_event_id"] is None
                else _sha256_id(value["previous_event_id"], "previous_event_id")
            ),
        )
    except (TypeError, ValueError) as exc:
        raise LegalAuthorityVerificationError("Verification event is invalid.") from exc
    _validate_event(event)
    return event


def _strict_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise LegalAuthorityVerificationError(field_name + " must be boolean.")
    return value


def load_legal_authority_verification_events(
    case_id: str,
    *,
    root=None,
) -> tuple[LegalAuthorityVerificationEvent, ...]:
    canonical_case_id = _case_id(case_id)
    path = verification_event_path(canonical_case_id, root=root)
    if not path.exists():
        return ()
    if not path.is_file():
        raise LegalAuthorityVerificationError("Verification event path is not a file.")

    events: list[LegalAuthorityVerificationEvent] = []
    seen_event_ids: set[str] = set()
    latest_by_target: dict[str, str] = {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LegalAuthorityVerificationError("Verification event history could not be read.") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise LegalAuthorityVerificationError(
                f"Verification event history contains a blank line at {line_number}."
            )
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LegalAuthorityVerificationError(
                f"Verification event history contains invalid JSON at line {line_number}."
            ) from exc
        event = _event_from_dict(raw)
        if event.case_id != canonical_case_id:
            raise LegalAuthorityVerificationError("Verification event history mixes case identities.")
        if event.event_id in seen_event_ids:
            raise LegalAuthorityVerificationError("Verification event history contains a duplicate event.")
        expected_previous = latest_by_target.get(event.target_id)
        if event.previous_event_id != expected_previous:
            raise LegalAuthorityVerificationError(
                "Verification event history contains an invalid target event chain."
            )
        seen_event_ids.add(event.event_id)
        latest_by_target[event.target_id] = event.event_id
        events.append(event)

    return tuple(events)


def _validated_event_sequence(
    events: Iterable[LegalAuthorityVerificationEvent],
    *,
    case_id: str,
) -> tuple[LegalAuthorityVerificationEvent, ...]:
    canonical_case_id = _case_id(case_id)
    result: list[LegalAuthorityVerificationEvent] = []
    seen_event_ids: set[str] = set()
    latest_by_target: dict[str, str] = {}

    for event in events:
        _validate_event(event)
        if event.case_id != canonical_case_id:
            raise LegalAuthorityVerificationError("Verification events mix case identities.")
        if event.event_id in seen_event_ids:
            raise LegalAuthorityVerificationError("Verification events contain a duplicate event.")
        expected_previous = latest_by_target.get(event.target_id)
        if event.previous_event_id != expected_previous:
            raise LegalAuthorityVerificationError(
                "Verification events contain an invalid target event chain."
            )
        seen_event_ids.add(event.event_id)
        latest_by_target[event.target_id] = event.event_id
        result.append(event)

    return tuple(result)


def _current_event(
    target: LegalAuthorityVerificationTarget,
    events: Iterable[LegalAuthorityVerificationEvent],
) -> LegalAuthorityVerificationEvent | None:
    _validate_target(target)
    current = None
    for event in _validated_event_sequence(events, case_id=target.case_id):
        if event.target_id == target.target_id:
            current = event
    return current


def project_legal_authority_verification(
    *,
    target: LegalAuthorityVerificationTarget,
    events: Iterable[LegalAuthorityVerificationEvent],
) -> LegalAuthorityVerificationProjection | None:
    current = _current_event(target, events)
    if current is None:
        return None
    state = (
        LegalAuthorityVerificationState.VERIFIED_FOR_RELIANCE
        if current.decision is LegalAuthorityVerificationDecision.VERIFIED_FOR_RELIANCE
        else LegalAuthorityVerificationState.REJECTED
    )
    return LegalAuthorityVerificationProjection(
        target=target,
        state=state,
        latest_event_id=current.event_id,
        recorded_at=current.recorded_at,
        reviewer_reference=current.reviewer_reference,
        verification_source=current.verification_source,
        verification_source_reference=current.verification_source_reference,
    )


def record_legal_authority_verification(
    *,
    target: LegalAuthorityVerificationTarget,
    decision: LegalAuthorityVerificationDecision | str,
    genuine: bool,
    citation_verifiable: bool,
    relevant_to_matter: bool,
    supports_attributed_proposition: bool,
    verification_source: str,
    verification_source_reference: str,
    reviewer_reference: str,
    review_note: str,
    root=None,
) -> LegalAuthorityVerificationEvent:
    """Append one explicit professional decision for an exact authority target."""

    _validate_target(target)
    try:
        decision_value = LegalAuthorityVerificationDecision(decision)
    except (TypeError, ValueError) as exc:
        raise LegalAuthorityVerificationError("decision is invalid.") from exc

    existing = load_legal_authority_verification_events(target.case_id, root=root)
    previous = _current_event(target, existing)
    recorded_at = _now()

    provisional = LegalAuthorityVerificationEvent(
        schema_version=LEGAL_AUTHORITY_VERIFICATION_SCHEMA_VERSION,
        event_id="sha256:" + ("0" * 64),
        recorded_at=recorded_at,
        case_id=target.case_id,
        target_id=target.target_id,
        evidence_key=target.evidence_key,
        evidence_binding_id=target.evidence_binding_id,
        bound_text_sha256=target.bound_text_sha256,
        document_name=target.document_name,
        page=target.page,
        authority_reference=target.authority_reference,
        decision=decision_value,
        genuine=_strict_bool(genuine, "genuine"),
        citation_verifiable=_strict_bool(
            citation_verifiable,
            "citation_verifiable",
        ),
        relevant_to_matter=_strict_bool(
            relevant_to_matter,
            "relevant_to_matter",
        ),
        supports_attributed_proposition=_strict_bool(
            supports_attributed_proposition,
            "supports_attributed_proposition",
        ),
        verification_source=_required(
            verification_source,
            "verification_source",
        ),
        verification_source_reference=_required(
            verification_source_reference,
            "verification_source_reference",
        ),
        reviewer_reference=_required(
            reviewer_reference,
            "reviewer_reference",
        ),
        review_note=_required(review_note, "review_note"),
        previous_event_id=None if previous is None else previous.event_id,
    )
    event = LegalAuthorityVerificationEvent(
        **{
            **asdict(provisional),
            "event_id": _derive_id(_event_identity_payload(provisional)),
        }
    )
    _validate_event(event)

    path = verification_event_path(target.case_id, root=root)
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
        raise LegalAuthorityVerificationError("Verification event could not be appended.") from exc

    return event


def assert_legal_authority_verified_for_reliance(
    *,
    target: LegalAuthorityVerificationTarget,
    events: Iterable[LegalAuthorityVerificationEvent],
) -> LegalAuthorityVerificationProjection:
    projection = project_legal_authority_verification(target=target, events=events)
    if (
        projection is None
        or projection.state is not LegalAuthorityVerificationState.VERIFIED_FOR_RELIANCE
    ):
        raise LegalAuthorityVerificationError(
            "Legal authority is not currently professionally verified for reliance."
        )
    return projection


__all__ = [
    "LEGAL_AUTHORITY_TARGET_SCHEMA_VERSION",
    "LEGAL_AUTHORITY_VERIFICATION_SCHEMA_VERSION",
    "LegalAuthorityVerificationDecision",
    "LegalAuthorityVerificationError",
    "LegalAuthorityVerificationEvent",
    "LegalAuthorityVerificationProjection",
    "LegalAuthorityVerificationState",
    "LegalAuthorityVerificationTarget",
    "assert_legal_authority_verified_for_reliance",
    "build_legal_authority_verification_target",
    "load_legal_authority_verification_events",
    "project_legal_authority_verification",
    "record_legal_authority_verification",
    "verification_event_path",
]
