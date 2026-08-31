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
) -> dict[
    str,
    object,
]:

    return {
        "schema_version":
            event.schema_version,

        "case_id":
            event.case_id,

        "authority_id":
            event.authority_id,

        "issue_analysis_id":
            event.issue_analysis_id,

        "element_id":
            event.element_id,

        "proposal_id":
            event.proposal_id,

        "event_id":
            event.event_id,

        "current_status":
            event.current_status,

        "current_confidence":
            event.current_confidence,

        "proposed_status":
            event.proposed_status,

        "proposed_confidence":
            event.proposed_confidence,

        "rationale":
            event.rationale,

        "basis_relationship_ids":
            list(
                event.basis_relationship_ids
            ),

        "state":
            event.state.value,

        "actor":
            event.actor,

        "created_at":
            event.created_at,

        "previous_event_id":
            event.previous_event_id,

        "review_note":
            event.review_note,
    }


def _event_from_dict(
    data: object,
) -> AnalyticalChangeProposalEvent:

    if not isinstance(
        data,
        dict,
    ):

        raise AnalyticalChangeProposalError(
            "Change-proposal event must be an object."
        )

    if (
        data.get(
            "schema_version"
        )
        != ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION
    ):

        raise AnalyticalChangeProposalError(
            "Unsupported change-proposal schema."
        )

    raw_basis = data.get(
        "basis_relationship_ids"
    )

    if not isinstance(
        raw_basis,
        list,
    ):

        raise AnalyticalChangeProposalError(
            "basis_relationship_ids must be a list."
        )

    basis = tuple(
        _text(
            value,
            field_name=
                "basis_relationship_id",
        )
        for value in raw_basis
    )

    previous = data.get(
        "previous_event_id"
    )

    if previous is not None:

        previous = _text(
            previous,
            field_name=
                "previous_event_id",
        )

    try:

        state = (
            AnalyticalChangeProposalState(
                _text(
                    data.get(
                        "state"
                    ),
                    field_name=
                        "state",
                )
            )
        )

    except ValueError as exc:

        raise AnalyticalChangeProposalError(
            "Unknown change-proposal state."
        ) from exc

    event = AnalyticalChangeProposalEvent(
        schema_version=
            ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION,

        case_id=
            _component(
                data.get(
                    "case_id"
                ),
                field_name=
                    "case_id",
            ),

        authority_id=
            _text(
                data.get(
                    "authority_id"
                ),
                field_name=
                    "authority_id",
            ),

        issue_analysis_id=
            _text(
                data.get(
                    "issue_analysis_id"
                ),
                field_name=
                    "issue_analysis_id",
            ),

        element_id=
            _text(
                data.get(
                    "element_id"
                ),
                field_name=
                    "element_id",
            ),

        proposal_id=
            _text(
                data.get(
                    "proposal_id"
                ),
                field_name=
                    "proposal_id",
            ),

        event_id=
            _text(
                data.get(
                    "event_id"
                ),
                field_name=
                    "event_id",
            ),

        current_status=
            _text(
                data.get(
                    "current_status"
                ),
                field_name=
                    "current_status",
            ),

        current_confidence=
            _text(
                data.get(
                    "current_confidence"
                ),
                field_name=
                    "current_confidence",
            ),

        proposed_status=
            _text(
                data.get(
                    "proposed_status"
                ),
                field_name=
                    "proposed_status",
            ),

        proposed_confidence=
            _text(
                data.get(
                    "proposed_confidence"
                ),
                field_name=
                    "proposed_confidence",
            ),

        rationale=
            _text(
                data.get(
                    "rationale"
                ),
                field_name=
                    "rationale",
            ),

        basis_relationship_ids=
            basis,

        state=
            state,

        actor=
            _text(
                data.get(
                    "actor"
                ),
                field_name=
                    "actor",
            ),

        created_at=
            _text(
                data.get(
                    "created_at"
                ),
                field_name=
                    "created_at",
            ),

        previous_event_id=
            previous,

        review_note=
            _optional_text(
                data.get(
                    "review_note"
                ),
                field_name=
                    "review_note",
            ),
    )

    _validate_event(
        event
    )

    return event


def _validate_event(
    event: AnalyticalChangeProposalEvent,
) -> None:

    if (
        event.schema_version
        != ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION
    ):

        raise AnalyticalChangeProposalError(
            "Unexpected event schema."
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
) -> tuple[
    object,
    ...,
]:

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

    if decision not in {
        AnalyticalChangeProposalState.APPROVED,
        AnalyticalChangeProposalState.REJECTED,
    }:

        raise AnalyticalChangeProposalError(
            "Review decision must be APPROVED or REJECTED."
        )

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

    normalized_proposal = _text(
        proposal_id,
        field_name=
            "proposal_id",
    )

    events = load_change_proposal_events(
        case_id=
            normalized_case,
        authority_id=
            normalized_authority,
        root=
            root,
    )

    chain = tuple(
        event
        for event in events
        if event.proposal_id
        == normalized_proposal
    )

    if not chain:

        raise AnalyticalChangeProposalError(
            "Unknown analytical change proposal."
        )

    latest = chain[
        -1
    ]

    if (
        latest.state
        is not AnalyticalChangeProposalState.PROPOSED
    ):

        raise AnalyticalChangeProposalError(
            "Analytical change proposal "
            "has already been reviewed."
        )

    event = AnalyticalChangeProposalEvent(
        schema_version=
            latest.schema_version,

        case_id=
            latest.case_id,

        authority_id=
            latest.authority_id,

        issue_analysis_id=
            latest.issue_analysis_id,

        element_id=
            latest.element_id,

        proposal_id=
            latest.proposal_id,

        event_id=
            "ace:"
            + uuid4().hex,

        current_status=
            latest.current_status,

        current_confidence=
            latest.current_confidence,

        proposed_status=
            latest.proposed_status,

        proposed_confidence=
            latest.proposed_confidence,

        rationale=
            latest.rationale,

        basis_relationship_ids=
            latest.basis_relationship_ids,

        state=
            decision,

        actor=
            _text(
                actor,
                field_name=
                    "actor",
            ),

        created_at=
            _utc_now(),

        previous_event_id=
            latest.event_id,

        review_note=
            _optional_text(
                review_note,
                field_name=
                    "review_note",
            ),
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


__all__ = [
    "ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION",
    "AnalyticalChangeProposalError",
    "AnalyticalChangeProposalEvent",
    "AnalyticalChangeProposalState",
    "load_change_proposal_events",
    "project_change_proposals",
    "propose_analytical_change",
    "review_analytical_change",
]
