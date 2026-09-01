from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
from uuid import uuid4


ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION = (
    "analytical-change-proposal-event/1.0"
)
ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION = "analytical-change-proposal-event/1.1"


class AnalyticalChangeProposalError(
    RuntimeError
):
    pass


class AnalyticalChangeProposalState(
    StrEnum
):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(
    frozen=True
)
class AnalyticalChangeProposalEvent:

    schema_version: str

    case_id: str
    authority_id: str
    issue_analysis_id: str
    element_id: str

    proposal_id: str
    event_id: str

    current_status: str
    current_confidence: str

    proposed_status: str
    proposed_confidence: str

    rationale: str

    basis_relationship_ids: tuple[
        str,
        ...,
    ]

    state: AnalyticalChangeProposalState

    actor: str
    created_at: str

    previous_event_id: str | None = None
    review_note: str = ""

@dataclass(
    frozen=True
)
class ProfessionalReviewBoundAnalyticalChangeProposalEvent(
    AnalyticalChangeProposalEvent
):
    basis_analysis_run_id: str = ""
    basis_observation_id: str = ""
    basis_professional_review_event_id: str = ""



def _text(
    value: object,
    *,
    field_name: str,
) -> str:

    if not isinstance(
        value,
        str,
    ):

        raise AnalyticalChangeProposalError(
            field_name
            + " must be text."
        )

    result = value.strip()

    if not result:

        raise AnalyticalChangeProposalError(
            field_name
            + " must not be blank."
        )

    return result


def _component(
    value: object,
    *,
    field_name: str,
) -> str:

    result = _text(
        value,
        field_name=
            field_name,
    )

    if (
        "/" in result
        or "\\" in result
        or result in {
            ".",
            "..",
        }
    ):

        raise AnalyticalChangeProposalError(
            field_name
            + " is not a safe path component."
        )

    return result


def _optional_text(
    value: object,
    *,
    field_name: str,
) -> str:

    if value is None:
        return ""

    if not isinstance(
        value,
        str,
    ):

        raise AnalyticalChangeProposalError(
            field_name
            + " must be text."
        )

    return value.strip()


def _utc_now() -> str:

    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def _validate_time(
    value: str
) -> None:

    try:

        parsed = (
            datetime.fromisoformat(
                value
            )
        )

    except ValueError as exc:

        raise AnalyticalChangeProposalError(
            "created_at is not valid ISO time."
        ) from exc

    if parsed.tzinfo is None:

        raise AnalyticalChangeProposalError(
            "created_at must be timezone-aware."
        )


def _root(
    root: Path | None,
) -> Path:

    if root is not None:
        return Path(
            root
        )

    configured = os.environ.get(
        "LEGALRAG_ANALYTICAL_CHANGE_PROPOSAL_ROOT"
    )

    if configured:
        return Path(
            configured
        )

    return Path(
        "matter_analysis_change_proposals"
    )


def _event_path(
    *,
    case_id: str,
    root: Path | None,
) -> Path:

    safe_case = _component(
        case_id,
        field_name=
            "case_id",
    )

    return (
        _root(
            root
        )
        / safe_case
        / "change-events.jsonl"
    )


def _event_to_dict(
    event: AnalyticalChangeProposalEvent,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": event.schema_version,
        "case_id": event.case_id,
        "authority_id": event.authority_id,
        "issue_analysis_id": event.issue_analysis_id,
        "element_id": event.element_id,
        "proposal_id": event.proposal_id,
        "event_id": event.event_id,
        "current_status": event.current_status,
        "current_confidence": event.current_confidence,
        "proposed_status": event.proposed_status,
        "proposed_confidence": event.proposed_confidence,
        "rationale": event.rationale,
        "basis_relationship_ids": list(event.basis_relationship_ids),
        "state": event.state.value,
        "actor": event.actor,
        "created_at": event.created_at,
        "previous_event_id": event.previous_event_id,
        "review_note": event.review_note,
    }
    if isinstance(
        event,
        ProfessionalReviewBoundAnalyticalChangeProposalEvent,
    ):
        payload["basis_analysis_run_id"] = event.basis_analysis_run_id
        payload["basis_observation_id"] = event.basis_observation_id
        payload["basis_professional_review_event_id"] = (
            event.basis_professional_review_event_id
        )
    return payload



def _event_from_dict(
    data: object,
) -> AnalyticalChangeProposalEvent:
    if not isinstance(data, dict):
        raise AnalyticalChangeProposalError(
            "Change-proposal event must be an object."
        )

    schema = data.get("schema_version")
    if schema not in {
        ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION,
        ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION,
    }:
        raise AnalyticalChangeProposalError(
            "Unsupported change-proposal schema."
        )

    raw_basis = data.get("basis_relationship_ids")
    if not isinstance(raw_basis, list):
        raise AnalyticalChangeProposalError(
            "basis_relationship_ids must be a list."
        )
    basis = tuple(
        _text(v, field_name="basis_relationship_id")
        for v in raw_basis
    )

    previous = data.get("previous_event_id")
    if previous is not None:
        previous = _text(previous, field_name="previous_event_id")

    try:
        state = AnalyticalChangeProposalState(
            _text(data.get("state"), field_name="state")
        )
    except ValueError as exc:
        raise AnalyticalChangeProposalError(
            "Unknown change-proposal state."
        ) from exc

    common = dict(
        schema_version=str(schema),
        case_id=_component(data.get("case_id"), field_name="case_id"),
        authority_id=_text(data.get("authority_id"), field_name="authority_id"),
        issue_analysis_id=_text(
            data.get("issue_analysis_id"),
            field_name="issue_analysis_id",
        ),
        element_id=_text(data.get("element_id"), field_name="element_id"),
        proposal_id=_text(data.get("proposal_id"), field_name="proposal_id"),
        event_id=_text(data.get("event_id"), field_name="event_id"),
        current_status=_text(
            data.get("current_status"),
            field_name="current_status",
        ),
        current_confidence=_text(
            data.get("current_confidence"),
            field_name="current_confidence",
        ),
        proposed_status=_text(
            data.get("proposed_status"),
            field_name="proposed_status",
        ),
        proposed_confidence=_text(
            data.get("proposed_confidence"),
            field_name="proposed_confidence",
        ),
        rationale=_text(data.get("rationale"), field_name="rationale"),
        basis_relationship_ids=basis,
        state=state,
        actor=_text(data.get("actor"), field_name="actor"),
        created_at=_text(data.get("created_at"), field_name="created_at"),
        previous_event_id=previous,
        review_note=_optional_text(
            data.get("review_note"),
            field_name="review_note",
        ),
    )

    if schema == ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION:
        forbidden = {
            "basis_analysis_run_id",
            "basis_observation_id",
            "basis_professional_review_event_id",
        }
        if forbidden.intersection(data):
            raise AnalyticalChangeProposalError(
                "Legacy events cannot carry professional-review provenance."
            )
        event = AnalyticalChangeProposalEvent(**common)
    else:
        event = ProfessionalReviewBoundAnalyticalChangeProposalEvent(
            **common,
            basis_analysis_run_id=_text(
                data.get("basis_analysis_run_id"),
                field_name="basis_analysis_run_id",
            ),
            basis_observation_id=_text(
                data.get("basis_observation_id"),
                field_name="basis_observation_id",
            ),
            basis_professional_review_event_id=_text(
                data.get("basis_professional_review_event_id"),
                field_name="basis_professional_review_event_id",
            ),
        )

    _validate_event(event)
    return event



def _require_sha256_identity(
    value: str,
    *,
    field_name: str,
) -> str:
    value = _text(value, field_name=field_name)
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(c not in "0123456789abcdef" for c in value[7:])
    ):
        raise AnalyticalChangeProposalError(
            field_name + " must be canonical sha256:<64 lowercase hex>."
        )
    return value

def _validate_event(
    event: AnalyticalChangeProposalEvent,
) -> None:

    if event.schema_version not in {
        ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION,
        ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION,
    }:
        raise AnalyticalChangeProposalError(
            "Unexpected event schema."
        )

    if isinstance(
        event,
        ProfessionalReviewBoundAnalyticalChangeProposalEvent,
    ):
        if (
            event.schema_version
            != ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION
        ):
            raise AnalyticalChangeProposalError(
                "Review-bound event must use PRW provenance schema."
            )
        _require_sha256_identity(
            event.basis_analysis_run_id,
            field_name="basis_analysis_run_id",
        )
        _require_sha256_identity(
            event.basis_observation_id,
            field_name="basis_observation_id",
        )
        _require_sha256_identity(
            event.basis_professional_review_event_id,
            field_name="basis_professional_review_event_id",
        )
    elif event.schema_version != ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION:
        raise AnalyticalChangeProposalError(
            "PRW provenance schema requires review-bound event type."
        )

    _component(
        event.case_id,
        field_name=
            "case_id",
    )

    for field_name, value in (
        (
            "authority_id",
            event.authority_id,
        ),
        (
            "issue_analysis_id",
            event.issue_analysis_id,
        ),
        (
            "element_id",
            event.element_id,
        ),
        (
            "proposal_id",
            event.proposal_id,
        ),
        (
            "event_id",
            event.event_id,
        ),
        (
            "current_status",
            event.current_status,
        ),
        (
            "current_confidence",
            event.current_confidence,
        ),
        (
            "proposed_status",
            event.proposed_status,
        ),
        (
            "proposed_confidence",
            event.proposed_confidence,
        ),
        (
            "rationale",
            event.rationale,
        ),
        (
            "actor",
            event.actor,
        ),
        (
            "created_at",
            event.created_at,
        ),
    ):

        _text(
            value,
            field_name=
                field_name,
        )

    _validate_time(
        event.created_at
    )

    if (
        event.current_status
        == event.proposed_status
        and event.current_confidence
        == event.proposed_confidence
    ):

        raise AnalyticalChangeProposalError(
            "A change proposal must actually change "
            "status or confidence."
        )

    if (
        event.basis_relationship_ids
        != tuple(
            sorted(
                set(
                    event.basis_relationship_ids
                )
            )
        )
    ):

        raise AnalyticalChangeProposalError(
            "basis_relationship_ids must be "
            "sorted and unique."
        )



def _immutable_payload(
    event: AnalyticalChangeProposalEvent,
) -> tuple[object, ...]:
    return (
        event.case_id,
        event.authority_id,
        event.issue_analysis_id,
        event.element_id,
        event.proposal_id,
        event.current_status,
        event.current_confidence,
        event.proposed_status,
        event.proposed_confidence,
        event.rationale,
        event.basis_relationship_ids,
        getattr(event, "basis_analysis_run_id", None),
        getattr(event, "basis_observation_id", None),
        getattr(event, "basis_professional_review_event_id", None),
    )



def _validate_history(
    events: tuple[
        AnalyticalChangeProposalEvent,
        ...,
    ],
) -> None:

    event_ids: set[
        str
    ] = set()

    grouped: dict[
        str,
        list[
            AnalyticalChangeProposalEvent
        ],
    ] = {}

    for event in events:

        _validate_event(
            event
        )

        if event.event_id in event_ids:

            raise AnalyticalChangeProposalError(
                "Duplicate analytical change event_id."
            )

        event_ids.add(
            event.event_id
        )

        grouped.setdefault(
            event.proposal_id,
            [],
        ).append(
            event
        )

    for proposal_id, chain in grouped.items():

        first = chain[
            0
        ]

        if (
            first.state
            is not AnalyticalChangeProposalState.PROPOSED
        ):

            raise AnalyticalChangeProposalError(
                "Change proposal "
                + proposal_id
                + " does not begin PROPOSED."
            )

        if first.previous_event_id is not None:

            raise AnalyticalChangeProposalError(
                "Initial proposal event has a predecessor."
            )

        if len(
            chain
        ) > 2:

            raise AnalyticalChangeProposalError(
                "A change proposal has more than "
                "one terminal review."
            )

        for later in chain[
            1:
        ]:

            if (
                _immutable_payload(
                    later
                )
                != _immutable_payload(
                    first
                )
            ):

                raise AnalyticalChangeProposalError(
                    "Change-proposal immutable fields changed."
                )

        if len(
            chain
        ) == 2:

            terminal = chain[
                1
            ]

            if terminal.state not in {
                AnalyticalChangeProposalState.APPROVED,
                AnalyticalChangeProposalState.REJECTED,
            }:

                raise AnalyticalChangeProposalError(
                    "Second event must be terminal."
                )

            if (
                terminal.previous_event_id
                != first.event_id
            ):

                raise AnalyticalChangeProposalError(
                    "Terminal review does not reference "
                    "the proposal event."
                )


def _read_events(
    *,
    case_id: str,
    root: Path | None,
) -> tuple[
    AnalyticalChangeProposalEvent,
    ...,
]:

    path = _event_path(
        case_id=
            case_id,
        root=
            root,
    )

    if not path.exists():

        return ()

    result: list[
        AnalyticalChangeProposalEvent
    ] = []

    for line_number, line in enumerate(
        path.read_text(
            encoding="utf-8"
        ).splitlines(),
        start=1,
    ):

        if not line.strip():
            continue

        try:

            data = json.loads(
                line
            )

        except json.JSONDecodeError as exc:

            raise AnalyticalChangeProposalError(
                "Invalid JSONL at line "
                + str(
                    line_number
                )
                + "."
            ) from exc

        result.append(
            _event_from_dict(
                data
            )
        )

    events = tuple(
        result
    )

    _validate_history(
        events
    )

    return events


def _append_event(
    event: AnalyticalChangeProposalEvent,
    *,
    root: Path | None,
) -> None:

    _validate_event(
        event
    )

    path = _event_path(
        case_id=
            event.case_id,
        root=
            root,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = (
        json.dumps(
            _event_to_dict(
                event
            ),
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
        )
        + "\n"
    )

    with path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:

        handle.write(
            serialized
        )

        handle.flush()

        os.fsync(
            handle.fileno()
        )


def load_change_proposal_events(
    *,
    case_id: str,
    authority_id: str | None = None,
    root: Path | None = None,
) -> tuple[
    AnalyticalChangeProposalEvent,
    ...,
]:

    events = _read_events(
        case_id=
            case_id,
        root=
            root,
    )

    if authority_id is None:
        return events

    expected = _text(
        authority_id,
        field_name=
            "authority_id",
    )

    return tuple(
        event
        for event in events
        if event.authority_id
        == expected
    )


def project_change_proposals(
    *,
    events: tuple[
        AnalyticalChangeProposalEvent,
        ...,
    ],
    issue_analysis_id: str,
    element_id: str,
) -> tuple[
    AnalyticalChangeProposalEvent,
    ...,
]:

    _validate_history(
        events
    )

    issue = _text(
        issue_analysis_id,
        field_name=
            "issue_analysis_id",
    )

    element = _text(
        element_id,
        field_name=
            "element_id",
    )

    latest: dict[
        str,
        AnalyticalChangeProposalEvent
    ] = {}

    order: list[
        str
    ] = []

    for event in events:

        if (
            event.issue_analysis_id
            != issue
            or event.element_id
            != element
        ):
            continue

        if (
            event.proposal_id
            not in latest
        ):
            order.append(
                event.proposal_id
            )

        latest[
            event.proposal_id
        ] = event

    return tuple(
        latest[
            proposal_id
        ]
        for proposal_id in order
    )


def propose_analytical_change(
    *,
    case_id: str,
    authority_id: str,
    issue_analysis_id: str,
    element_id: str,
    current_status: str,
    current_confidence: str,
    proposed_status: str,
    proposed_confidence: str,
    rationale: str,
    actor: str,
    basis_relationship_ids: tuple[
        str,
        ...,
    ] = (),
    root: Path | None = None,
) -> AnalyticalChangeProposalEvent:

    normalized_case = _component(
        case_id,
        field_name=
            "case_id",
    )

    normalized_authority = _text(
        authority_id,
        field_name=
            "authority_id",
    )

    normalized_issue = _text(
        issue_analysis_id,
        field_name=
            "issue_analysis_id",
    )

    normalized_element = _text(
        element_id,
        field_name=
            "element_id",
    )

    existing = load_change_proposal_events(
        case_id=
            normalized_case,
        authority_id=
            normalized_authority,
        root=
            root,
    )

    projected = project_change_proposals(
        events=
            existing,
        issue_analysis_id=
            normalized_issue,
        element_id=
            normalized_element,
    )

    if any(
        event.state
        is AnalyticalChangeProposalState.PROPOSED
        for event in projected
    ):

        raise AnalyticalChangeProposalError(
            "A change proposal is already pending "
            "for this analytical element."
        )

    basis = tuple(
        sorted(
            set(
                _text(
                    value,
                    field_name=
                        "basis_relationship_id",
                )
                for value in basis_relationship_ids
            )
        )
    )

    event = AnalyticalChangeProposalEvent(
        schema_version=
            ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION,

        case_id=
            normalized_case,

        authority_id=
            normalized_authority,

        issue_analysis_id=
            normalized_issue,

        element_id=
            normalized_element,

        proposal_id=
            "acp:"
            + uuid4().hex,

        event_id=
            "ace:"
            + uuid4().hex,

        current_status=
            _text(
                current_status,
                field_name=
                    "current_status",
            ),

        current_confidence=
            _text(
                current_confidence,
                field_name=
                    "current_confidence",
            ),

        proposed_status=
            _text(
                proposed_status,
                field_name=
                    "proposed_status",
            ),

        proposed_confidence=
            _text(
                proposed_confidence,
                field_name=
                    "proposed_confidence",
            ),

        rationale=
            _text(
                rationale,
                field_name=
                    "rationale",
            ),

        basis_relationship_ids=
            basis,

        state=
            AnalyticalChangeProposalState.PROPOSED,

        actor=
            _text(
                actor,
                field_name=
                    "actor",
            ),

        created_at=
            _utc_now(),

        previous_event_id=
            None,

        review_note=
            "",
    )

    _validate_event(
        event
    )

    _append_event(
        event,
        root=
            root,
    )

    _validate_history(
        _read_events(
            case_id=
                normalized_case,
            root=
                root,
        )
    )

    return event


def propose_analytical_change_from_professional_review(
    *,
    case_id: str,
    authority_id: str,
    issue_analysis_id: str,
    element_id: str,
    current_status: str,
    current_confidence: str,
    proposed_status: str,
    proposed_confidence: str,
    rationale: str,
    actor: str,
    professional_review_events: tuple[object, ...],
    basis_relationship_ids: tuple[str, ...] = (),
    root: Path | None = None,
) -> ProfessionalReviewBoundAnalyticalChangeProposalEvent:
    from controlled_agentic_analysis_review import (
        ProfessionalReviewDecision,
        ProfessionalReviewError,
        assert_review_allows_mal1_consideration,
    )

    case = _component(case_id, field_name="case_id")
    authority = _text(authority_id, field_name="authority_id")
    issue = _text(issue_analysis_id, field_name="issue_analysis_id")
    element = _text(element_id, field_name="element_id")

    reviews = tuple(professional_review_events)
    if not reviews:
        raise AnalyticalChangeProposalError(
            "Professional-review provenance requires a review chain."
        )
    try:
        projection = assert_review_allows_mal1_consideration(reviews)
    except ProfessionalReviewError as exc:
        raise AnalyticalChangeProposalError(
            "Professional review does not permit MAL1 proposal consideration."
        ) from exc

    accepted = reviews[-1]
    if (
        getattr(accepted, "decision", None)
        is not ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION
        or getattr(accepted, "event_id", None) != projection.event_id
        or getattr(accepted, "observation_id", None)
        != projection.observation_id
    ):
        raise AnalyticalChangeProposalError(
            "Professional-review chain does not resolve to terminal acceptance."
        )

    checks = (
        ("case_id", getattr(accepted, "case_id", None), case),
        (
            "active_authority_id",
            getattr(accepted, "active_authority_id", None),
            authority,
        ),
        (
            "issue_analysis_id",
            getattr(accepted, "issue_analysis_id", None),
            issue,
        ),
        ("element_id", getattr(accepted, "element_id", None), element),
    )
    for name, actual, expected in checks:
        if actual != expected:
            raise AnalyticalChangeProposalError(
                "Professional-review "
                + name
                + " does not match the MAL1 proposal target."
            )

    existing = load_change_proposal_events(
        case_id=case,
        authority_id=authority,
        root=root,
    )
    projected = project_change_proposals(
        events=existing,
        issue_analysis_id=issue,
        element_id=element,
    )
    if any(
        x.state is AnalyticalChangeProposalState.PROPOSED
        for x in projected
    ):
        raise AnalyticalChangeProposalError(
            "A change proposal is already pending for this analytical element."
        )

    basis = tuple(
        sorted(
            set(
                _text(v, field_name="basis_relationship_id")
                for v in basis_relationship_ids
            )
        )
    )

    event = ProfessionalReviewBoundAnalyticalChangeProposalEvent(
        schema_version=
            ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION,
        case_id=case,
        authority_id=authority,
        issue_analysis_id=issue,
        element_id=element,
        proposal_id="acp:" + uuid4().hex,
        event_id="ace:" + uuid4().hex,
        current_status=_text(
            current_status,
            field_name="current_status",
        ),
        current_confidence=_text(
            current_confidence,
            field_name="current_confidence",
        ),
        proposed_status=_text(
            proposed_status,
            field_name="proposed_status",
        ),
        proposed_confidence=_text(
            proposed_confidence,
            field_name="proposed_confidence",
        ),
        rationale=_text(rationale, field_name="rationale"),
        basis_relationship_ids=basis,
        state=AnalyticalChangeProposalState.PROPOSED,
        actor=_text(actor, field_name="actor"),
        created_at=_utc_now(),
        previous_event_id=None,
        review_note="",
        basis_analysis_run_id=_require_sha256_identity(
            getattr(accepted, "analysis_run_id", ""),
            field_name="basis_analysis_run_id",
        ),
        basis_observation_id=_require_sha256_identity(
            getattr(accepted, "observation_id", ""),
            field_name="basis_observation_id",
        ),
        basis_professional_review_event_id=_require_sha256_identity(
            getattr(accepted, "event_id", ""),
            field_name="basis_professional_review_event_id",
        ),
    )
    _validate_event(event)
    _append_event(event, root=root)
    _validate_history(_read_events(case_id=case, root=root))
    return event



def review_analytical_change(
    *,
    case_id: str,
    authority_id: str,
    proposal_id: str,
    decision: AnalyticalChangeProposalState,
    actor: str,
    review_note: str = "",
    root: Path | None = None,
) -> AnalyticalChangeProposalEvent:
    from dataclasses import replace

    if decision not in {
        AnalyticalChangeProposalState.APPROVED,
        AnalyticalChangeProposalState.REJECTED,
    }:
        raise AnalyticalChangeProposalError(
            "Review decision must be APPROVED or REJECTED."
        )

    case = _component(case_id, field_name="case_id")
    authority = _text(authority_id, field_name="authority_id")
    proposal = _text(proposal_id, field_name="proposal_id")

    events = load_change_proposal_events(
        case_id=case,
        authority_id=authority,
        root=root,
    )
    chain = tuple(x for x in events if x.proposal_id == proposal)
    if not chain:
        raise AnalyticalChangeProposalError(
            "Unknown analytical change proposal."
        )

    latest = chain[-1]
    if latest.state is not AnalyticalChangeProposalState.PROPOSED:
        raise AnalyticalChangeProposalError(
            "Analytical change proposal has already been reviewed."
        )

    event = replace(
        latest,
        event_id="ace:" + uuid4().hex,
        state=decision,
        actor=_text(actor, field_name="actor"),
        created_at=_utc_now(),
        previous_event_id=latest.event_id,
        review_note=_optional_text(
            review_note,
            field_name="review_note",
        ),
    )
    _append_event(event, root=root)
    _validate_history(_read_events(case_id=case, root=root))
    return event



__all__ = [
    "ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION",
    "ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION",
    "AnalyticalChangeProposalError",
    "AnalyticalChangeProposalEvent",
    "ProfessionalReviewBoundAnalyticalChangeProposalEvent",
    "AnalyticalChangeProposalState",
    "load_change_proposal_events",
    "project_change_proposals",
    "propose_analytical_change",
    "propose_analytical_change_from_professional_review",
    "review_analytical_change",
]
