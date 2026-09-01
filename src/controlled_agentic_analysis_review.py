"""Professional review workflow for Controlled Agentic Analysis observations.

PRW1 sits strictly between CAA observations and MAL1 analytical-change proposals.

A professional review decision has no authority effect.  In particular:

    observation
        != professional review acceptance
        != MAL1 proposal
        != MAL1 approval
        != GAR1 revision
        != activation

ACCEPT_FOR_MAL1_CONSIDERATION means only that a human reviewer considers the
observation suitable for a separately authored MAL1 proposal.  This module
never creates, approves, publishes, revises, or activates governed authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Callable, Iterable

from controlled_agentic_analysis import (
    AgentObservation,
    FrozenInspectionUniverse,
    RecommendedAction,
    assert_active_authority_unchanged,
    dumps_agent_observation,
)
from controlled_agentic_analysis_gaps import (
    GapAgentObservation,
    dumps_gap_observation,
)


PRW1_SCHEMA_VERSION = "controlled-agentic-professional-review-event/v1"


class ProfessionalReviewError(ValueError):
    """Raised when PRW1 review state fails closed."""


class ObservationSource(str, Enum):
    CAA1 = "CAA1"
    CAA2 = "CAA2"


class ProfessionalReviewDecision(str, Enum):
    DEFER = "DEFER"
    ACCEPT_FOR_MAL1_CONSIDERATION = "ACCEPT_FOR_MAL1_CONSIDERATION"
    REJECT = "REJECT"


class ProfessionalReviewState(str, Enum):
    DEFERRED = "DEFERRED"
    ACCEPTED_FOR_MAL1_CONSIDERATION = "ACCEPTED_FOR_MAL1_CONSIDERATION"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ProfessionalReviewEvent:
    schema_version: str
    case_id: str
    active_authority_id: str
    analysis_run_id: str
    source_agent: ObservationSource
    observation_id: str
    observation_sha256: str
    issue_analysis_id: str | None
    element_id: str | None
    recommended_action: RecommendedAction
    decision: ProfessionalReviewDecision
    reviewer_reference: str
    reviewer_note: str
    reviewed_at_utc: str
    previous_event_id: str | None
    event_id: str


@dataclass(frozen=True)
class ProfessionalReviewProjection:
    observation_id: str
    event_id: str
    state: ProfessionalReviewState
    reviewer_reference: str
    reviewer_note: str
    reviewed_at_utc: str
    eligible_for_mal1_consideration: bool


Observation = AgentObservation | GapAgentObservation
AuthorityLoader = Callable[[str], Any]


def _fail(message: str) -> None:
    raise ProfessionalReviewError(message)


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field_name} must be non-empty text.")
    return value.strip()


def _optional_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(f"{field_name} must be text or None.")
    cleaned = value.strip()
    return cleaned or None


def _require_sha256_id(value: Any, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    if not text.startswith("sha256:") or len(text) != 71:
        _fail(f"{field_name} must be canonical sha256:<64 lowercase hex>.")
    digest = text[7:]
    if digest != digest.lower() or any(ch not in "0123456789abcdef" for ch in digest):
        _fail(f"{field_name} must be canonical sha256:<64 lowercase hex>.")
    return text


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _parse_reviewed_at_utc(value: str) -> str:
    text = _required_text(value, field_name="reviewed_at_utc")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise ProfessionalReviewError(
            "reviewed_at_utc must use exact UTC form YYYY-MM-DDTHH:MM:SSZ."
        ) from exc
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _observation_source(observation: Observation) -> ObservationSource:
    if isinstance(observation, AgentObservation):
        return ObservationSource.CAA1
    if isinstance(observation, GapAgentObservation):
        return ObservationSource.CAA2
    _fail("observation must be AgentObservation or GapAgentObservation.")
    raise AssertionError("unreachable")


def _observation_payload(observation: Observation) -> bytes:
    if isinstance(observation, AgentObservation):
        payload = dumps_agent_observation(observation)
    elif isinstance(observation, GapAgentObservation):
        payload = dumps_gap_observation(observation)
    else:
        _fail("observation must be AgentObservation or GapAgentObservation.")
        raise AssertionError("unreachable")
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, bytes):
        return payload
    _fail("CAA observation serializer returned unsupported payload type.")
    raise AssertionError("unreachable")


def _event_identity_payload(
    *,
    case_id: str,
    active_authority_id: str,
    analysis_run_id: str,
    source_agent: ObservationSource,
    observation_id: str,
    observation_sha256: str,
    issue_analysis_id: str | None,
    element_id: str | None,
    recommended_action: RecommendedAction,
    decision: ProfessionalReviewDecision,
    reviewer_reference: str,
    reviewer_note: str,
    reviewed_at_utc: str,
    previous_event_id: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": PRW1_SCHEMA_VERSION,
        "case_id": case_id,
        "active_authority_id": active_authority_id,
        "analysis_run_id": analysis_run_id,
        "source_agent": source_agent.value,
        "observation_id": observation_id,
        "observation_sha256": observation_sha256,
        "issue_analysis_id": issue_analysis_id,
        "element_id": element_id,
        "recommended_action": recommended_action.value,
        "decision": decision.value,
        "reviewer_reference": reviewer_reference,
        "reviewer_note": reviewer_note,
        "reviewed_at_utc": reviewed_at_utc,
        "previous_event_id": previous_event_id,
    }


def professional_review_event_to_dict(
    value: ProfessionalReviewEvent,
) -> dict[str, Any]:
    validate_professional_review_event(value)
    payload = _event_identity_payload(
        case_id=value.case_id,
        active_authority_id=value.active_authority_id,
        analysis_run_id=value.analysis_run_id,
        source_agent=value.source_agent,
        observation_id=value.observation_id,
        observation_sha256=value.observation_sha256,
        issue_analysis_id=value.issue_analysis_id,
        element_id=value.element_id,
        recommended_action=value.recommended_action,
        decision=value.decision,
        reviewer_reference=value.reviewer_reference,
        reviewer_note=value.reviewer_note,
        reviewed_at_utc=value.reviewed_at_utc,
        previous_event_id=value.previous_event_id,
    )
    payload["event_id"] = value.event_id
    return payload


def dumps_professional_review_event(value: ProfessionalReviewEvent) -> str:
    return _canonical_json_bytes(professional_review_event_to_dict(value)).decode(
        "utf-8"
    )


def professional_review_event_from_dict(
    data: dict[str, Any],
) -> ProfessionalReviewEvent:
    if not isinstance(data, dict):
        _fail("Professional review event JSON root must be an object.")
    expected = {
        "schema_version",
        "case_id",
        "active_authority_id",
        "analysis_run_id",
        "source_agent",
        "observation_id",
        "observation_sha256",
        "issue_analysis_id",
        "element_id",
        "recommended_action",
        "decision",
        "reviewer_reference",
        "reviewer_note",
        "reviewed_at_utc",
        "previous_event_id",
        "event_id",
    }
    if set(data) != expected:
        _fail("Professional review event keys are invalid.")
    try:
        result = ProfessionalReviewEvent(
            schema_version=str(data["schema_version"]),
            case_id=str(data["case_id"]),
            active_authority_id=str(data["active_authority_id"]),
            analysis_run_id=str(data["analysis_run_id"]),
            source_agent=ObservationSource(data["source_agent"]),
            observation_id=str(data["observation_id"]),
            observation_sha256=str(data["observation_sha256"]),
            issue_analysis_id=(
                None
                if data["issue_analysis_id"] is None
                else str(data["issue_analysis_id"])
            ),
            element_id=(
                None if data["element_id"] is None else str(data["element_id"])
            ),
            recommended_action=RecommendedAction(data["recommended_action"]),
            decision=ProfessionalReviewDecision(data["decision"]),
            reviewer_reference=str(data["reviewer_reference"]),
            reviewer_note=str(data["reviewer_note"]),
            reviewed_at_utc=str(data["reviewed_at_utc"]),
            previous_event_id=(
                None
                if data["previous_event_id"] is None
                else str(data["previous_event_id"])
            ),
            event_id=str(data["event_id"]),
        )
    except (TypeError, ValueError) as exc:
        raise ProfessionalReviewError(
            "Professional review event enum or field value is invalid."
        ) from exc
    validate_professional_review_event(result)
    return result


def loads_professional_review_event(payload: str | bytes) -> ProfessionalReviewEvent:
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProfessionalReviewError(
                "Professional review event payload must be UTF-8."
            ) from exc
    elif isinstance(payload, str):
        text = payload
    else:
        _fail("Professional review event payload must be str or bytes.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfessionalReviewError(
            "Professional review event payload is not valid JSON."
        ) from exc
    return professional_review_event_from_dict(data)


def validate_professional_review_event(value: ProfessionalReviewEvent) -> None:
    if not isinstance(value, ProfessionalReviewEvent):
        _fail("value must be ProfessionalReviewEvent.")
    if value.schema_version != PRW1_SCHEMA_VERSION:
        _fail("Unsupported professional review schema_version.")

    case_id = _required_text(value.case_id, field_name="case_id")
    active_authority_id = _require_sha256_id(
        value.active_authority_id,
        field_name="active_authority_id",
    )
    analysis_run_id = _require_sha256_id(
        value.analysis_run_id,
        field_name="analysis_run_id",
    )
    if not isinstance(value.source_agent, ObservationSource):
        _fail("source_agent must be ObservationSource.")
    observation_id = _require_sha256_id(
        value.observation_id,
        field_name="observation_id",
    )
    observation_sha256 = _require_sha256_id(
        value.observation_sha256,
        field_name="observation_sha256",
    )
    issue_analysis_id = _optional_text(
        value.issue_analysis_id,
        field_name="issue_analysis_id",
    )
    element_id = _optional_text(value.element_id, field_name="element_id")
    if not isinstance(value.recommended_action, RecommendedAction):
        _fail("recommended_action must be RecommendedAction.")
    if not isinstance(value.decision, ProfessionalReviewDecision):
        _fail("decision must be ProfessionalReviewDecision.")

    reviewer_reference = _required_text(
        value.reviewer_reference,
        field_name="reviewer_reference",
    )
    reviewer_note = _required_text(
        value.reviewer_note,
        field_name="reviewer_note",
    )
    reviewed_at_utc = _parse_reviewed_at_utc(value.reviewed_at_utc)
    previous_event_id = (
        None
        if value.previous_event_id is None
        else _require_sha256_id(
            value.previous_event_id,
            field_name="previous_event_id",
        )
    )
    event_id = _require_sha256_id(value.event_id, field_name="event_id")

    identity = _event_identity_payload(
        case_id=case_id,
        active_authority_id=active_authority_id,
        analysis_run_id=analysis_run_id,
        source_agent=value.source_agent,
        observation_id=observation_id,
        observation_sha256=observation_sha256,
        issue_analysis_id=issue_analysis_id,
        element_id=element_id,
        recommended_action=value.recommended_action,
        decision=value.decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
        reviewed_at_utc=reviewed_at_utc,
        previous_event_id=previous_event_id,
    )
    expected_id = _canonical_sha256(_canonical_json_bytes(identity))
    if event_id != expected_id:
        _fail("Professional review event_id does not match canonical identity.")


def _validate_observation_against_run(
    *,
    run: FrozenInspectionUniverse,
    observation: Observation,
) -> None:
    if not isinstance(run, FrozenInspectionUniverse):
        _fail("run must be FrozenInspectionUniverse.")
    for field_name in (
        "case_id",
        "active_authority_id",
        "analysis_run_id",
    ):
        if getattr(observation, field_name, None) != getattr(run, field_name):
            _fail(
                f"Observation {field_name} does not match the frozen inspection run."
            )
    _require_sha256_id(
        getattr(observation, "observation_id", None),
        field_name="observation.observation_id",
    )
    if not isinstance(
        getattr(observation, "recommended_action", None),
        RecommendedAction,
    ):
        _fail("Observation recommended_action is invalid.")


def _load_current_authority_id(
    *,
    case_id: str,
    authority_loader: AuthorityLoader | None,
) -> str:
    loader = authority_loader
    if loader is None:
        from governed_analytical_authority.provider import (
            load_active_governed_analytical_authority,
        )

        loader = load_active_governed_analytical_authority

    authority = loader(case_id)
    if authority is None:
        _fail("Active governed authority is unavailable during professional review.")
    manifest = getattr(authority, "manifest", None)
    authority_id = getattr(manifest, "authority_id", None)
    return _require_sha256_id(
        authority_id,
        field_name="current active authority_id",
    )


def project_professional_review(
    events: Iterable[ProfessionalReviewEvent],
) -> ProfessionalReviewProjection | None:
    values = tuple(events)
    if not values:
        return None

    for event in values:
        validate_professional_review_event(event)

    first = values[0]
    expected_previous: str | None = None
    terminal = False

    for index, event in enumerate(values):
        if event.observation_id != first.observation_id:
            _fail("Professional review event chain mixes observation identities.")
        if event.case_id != first.case_id:
            _fail("Professional review event chain mixes case identities.")
        if event.active_authority_id != first.active_authority_id:
            _fail("Professional review event chain mixes authority identities.")
        if event.analysis_run_id != first.analysis_run_id:
            _fail("Professional review event chain mixes analysis run identities.")
        if event.observation_sha256 != first.observation_sha256:
            _fail("Professional review event chain mixes observation payload identities.")
        if event.previous_event_id != expected_previous:
            _fail("Professional review event chain previous_event_id is invalid.")
        if terminal:
            _fail("Professional review event chain continues after a terminal decision.")

        expected_previous = event.event_id
        terminal = event.decision in (
            ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
            ProfessionalReviewDecision.REJECT,
        )

    latest = values[-1]
    if latest.decision is ProfessionalReviewDecision.DEFER:
        state = ProfessionalReviewState.DEFERRED
    elif (
        latest.decision
        is ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION
    ):
        state = ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION
    elif latest.decision is ProfessionalReviewDecision.REJECT:
        state = ProfessionalReviewState.REJECTED
    else:
        _fail("Unsupported professional review decision.")
        raise AssertionError("unreachable")

    return ProfessionalReviewProjection(
        observation_id=latest.observation_id,
        event_id=latest.event_id,
        state=state,
        reviewer_reference=latest.reviewer_reference,
        reviewer_note=latest.reviewer_note,
        reviewed_at_utc=latest.reviewed_at_utc,
        eligible_for_mal1_consideration=(
            state
            is ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION
        ),
    )


def review_agent_observation(
    *,
    run: FrozenInspectionUniverse,
    observation: Observation,
    decision: ProfessionalReviewDecision,
    reviewer_reference: str,
    reviewer_note: str,
    reviewed_at_utc: str,
    existing_events: Iterable[ProfessionalReviewEvent] = (),
    active_authority_loader: AuthorityLoader | None = None,
) -> ProfessionalReviewEvent:
    """Create one append-only PRW1 event after exact authority/run validation."""

    _validate_observation_against_run(run=run, observation=observation)

    if not isinstance(decision, ProfessionalReviewDecision):
        _fail("decision must be ProfessionalReviewDecision.")

    reviewer_reference = _required_text(
        reviewer_reference,
        field_name="reviewer_reference",
    )
    reviewer_note = _required_text(
        reviewer_note,
        field_name="reviewer_note",
    )
    reviewed_at_utc = _parse_reviewed_at_utc(reviewed_at_utc)

    existing = tuple(existing_events)
    current = project_professional_review(existing)
    if current is not None and current.state in (
        ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION,
        ProfessionalReviewState.REJECTED,
    ):
        _fail("Professional review observation already has a terminal decision.")

    if existing:
        last = existing[-1]
        if last.observation_id != observation.observation_id:
            _fail("Existing review events do not belong to this observation.")
        previous_event_id = last.event_id
    else:
        previous_event_id = None

    current_authority_id = _load_current_authority_id(
        case_id=run.case_id,
        authority_loader=active_authority_loader,
    )
    assert_active_authority_unchanged(
        run=run,
        current_authority_id=current_authority_id,
    )

    source_agent = _observation_source(observation)
    observation_sha256 = _canonical_sha256(
        _observation_payload(observation)
    )
    issue_analysis_id = _optional_text(
        getattr(observation, "issue_analysis_id", None),
        field_name="observation.issue_analysis_id",
    )
    element_id = _optional_text(
        getattr(observation, "element_id", None),
        field_name="observation.element_id",
    )
    recommended_action = observation.recommended_action

    identity = _event_identity_payload(
        case_id=run.case_id,
        active_authority_id=run.active_authority_id,
        analysis_run_id=run.analysis_run_id,
        source_agent=source_agent,
        observation_id=observation.observation_id,
        observation_sha256=observation_sha256,
        issue_analysis_id=issue_analysis_id,
        element_id=element_id,
        recommended_action=recommended_action,
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
        reviewed_at_utc=reviewed_at_utc,
        previous_event_id=previous_event_id,
    )
    event = ProfessionalReviewEvent(
        schema_version=PRW1_SCHEMA_VERSION,
        case_id=run.case_id,
        active_authority_id=run.active_authority_id,
        analysis_run_id=run.analysis_run_id,
        source_agent=source_agent,
        observation_id=observation.observation_id,
        observation_sha256=observation_sha256,
        issue_analysis_id=issue_analysis_id,
        element_id=element_id,
        recommended_action=recommended_action,
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
        reviewed_at_utc=reviewed_at_utc,
        previous_event_id=previous_event_id,
        event_id=_canonical_sha256(_canonical_json_bytes(identity)),
    )
    validate_professional_review_event(event)
    return event


def assert_review_allows_mal1_consideration(
    events: Iterable[ProfessionalReviewEvent],
) -> ProfessionalReviewProjection:
    """Require an accepted review without creating or approving any MAL1 proposal."""

    projection = project_professional_review(events)
    if (
        projection is None
        or not projection.eligible_for_mal1_consideration
    ):
        _fail(
            "Professional review does not permit MAL1 proposal consideration."
        )
    return projection


__all__ = [
    "ObservationSource",
    "PRW1_SCHEMA_VERSION",
    "ProfessionalReviewDecision",
    "ProfessionalReviewError",
    "ProfessionalReviewEvent",
    "ProfessionalReviewProjection",
    "ProfessionalReviewState",
    "assert_review_allows_mal1_consideration",
    "dumps_professional_review_event",
    "loads_professional_review_event",
    "professional_review_event_from_dict",
    "professional_review_event_to_dict",
    "project_professional_review",
    "review_agent_observation",
    "validate_professional_review_event",
]
