"""Matter Analysis Ledger relationship review.

This module deliberately extends the existing LegalRAG analytical state
rather than creating another issue/evidence model.

The existing governed analytical authority remains unchanged.

Relationship review state is append-only and bound to:
    case_id
    authority_id
    issue_analysis_id
    element_id
    evidence keys

Permitted transition:
    PROPOSED -> APPROVED
    PROPOSED -> REJECTED

No caller can silently replace an approved/rejected review event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable
import hashlib
import json
import os
import re


RELATIONSHIP_EVENT_SCHEMA_VERSION = (
    "matter-analysis-ledger-relationship-event/1.0"
)

_SAFE_CASE_ID = re.compile(
    r"^[A-Za-z0-9_.:-]+$"
)


class MatterAnalysisLedgerError(RuntimeError):
    """Fail-closed Matter Analysis Ledger error."""


class RelationshipType(str, Enum):
    CONTRADICTS = "CONTRADICTS"
    CORROBORATES = "CORROBORATES"


class RelationshipReviewState(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RelationshipEvent:
    schema_version: str
    case_id: str
    authority_id: str
    issue_analysis_id: str
    element_id: str
    relationship_id: str
    event_id: str
    relationship_type: RelationshipType
    left_evidence_key: str
    right_evidence_key: str
    proposal_rationale: str
    state: RelationshipReviewState
    actor: str
    created_at: str
    previous_event_id: str | None = None
    review_note: str = ""

    def __post_init__(self):
        if (
            self.schema_version
            != RELATIONSHIP_EVENT_SCHEMA_VERSION
        ):
            raise ValueError(
                "Unsupported relationship-event schema."
            )

        for name in (
            "case_id",
            "authority_id",
            "issue_analysis_id",
            "element_id",
            "relationship_id",
            "event_id",
            "left_evidence_key",
            "right_evidence_key",
            "proposal_rationale",
            "actor",
            "created_at",
        ):
            value = getattr(
                self,
                name,
            )

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{name} must be non-empty."
                )

        if (
            self.left_evidence_key
            == self.right_evidence_key
        ):
            raise ValueError(
                "A relationship requires two "
                "different evidence keys."
            )

        if (
            self.state
            is RelationshipReviewState.PROPOSED
        ):
            if self.previous_event_id is not None:
                raise ValueError(
                    "A proposal cannot have a "
                    "previous event."
                )
        else:
            if not self.previous_event_id:
                raise ValueError(
                    "A review event must reference "
                    "its proposal event."
                )


@dataclass(frozen=True)
class LedgerElement:
    element_id: str
    element_name: str
    legal_question: str

    analytical_status: str
    analytical_confidence: str

    supporting_evidence_keys: tuple[str, ...]
    adverse_evidence_keys: tuple[str, ...]
    corroborative_evidence_keys: tuple[str, ...]
    conflicting_evidence_keys: tuple[str, ...]
    neutral_evidence_keys: tuple[str, ...]

    evidential_gap_ids: tuple[str, ...]
    unresolved_matters: tuple[str, ...]

    provisional_analysis: str

    relationships: tuple[
        RelationshipEvent,
        ...,
    ]


@dataclass(frozen=True)
class LedgerIssue:
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    issue_summary: str
    elements: tuple[
        LedgerElement,
        ...,
    ]


@dataclass(frozen=True)
class MatterAnalysisLedger:
    case_id: str
    authority_id: str
    issues: tuple[
        LedgerIssue,
        ...,
    ]


def _text(value) -> str:
    raw = getattr(
        value,
        "value",
        value,
    )

    return str(raw)


def _canonical_pair(
    left: str,
    right: str,
) -> tuple[str, str]:

    if (
        not isinstance(left, str)
        or not left.strip()
        or not isinstance(right, str)
        or not right.strip()
    ):
        raise ValueError(
            "Two non-empty evidence keys are required."
        )

    left = left.strip()
    right = right.strip()

    if left == right:
        raise ValueError(
            "Two different evidence keys are required."
        )

    return tuple(
        sorted(
            (
                left,
                right,
            )
        )
    )


def derive_relationship_id(
    *,
    case_id: str,
    authority_id: str,
    issue_analysis_id: str,
    element_id: str,
    relationship_type: RelationshipType,
    left_evidence_key: str,
    right_evidence_key: str,
) -> str:

    left, right = _canonical_pair(
        left_evidence_key,
        right_evidence_key,
    )

    payload = json.dumps(
        {
            "case_id":
                case_id,

            "authority_id":
                authority_id,

            "issue_analysis_id":
                issue_analysis_id,

            "element_id":
                element_id,

            "relationship_type":
                relationship_type.value,

            "left_evidence_key":
                left,

            "right_evidence_key":
                right,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return (
        "rel:sha256:"
        + hashlib.sha256(
            payload
        ).hexdigest()
    )


def _event_id(
    payload: dict,
) -> str:

    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return (
        "evt:sha256:"
        + hashlib.sha256(
            raw
        ).hexdigest()
    )


def _event_to_dict(
    value: RelationshipEvent,
) -> dict:

    return {
        "schema_version":
            value.schema_version,

        "case_id":
            value.case_id,

        "authority_id":
            value.authority_id,

        "issue_analysis_id":
            value.issue_analysis_id,

        "element_id":
            value.element_id,

        "relationship_id":
            value.relationship_id,

        "event_id":
            value.event_id,

        "relationship_type":
            value.relationship_type.value,

        "left_evidence_key":
            value.left_evidence_key,

        "right_evidence_key":
            value.right_evidence_key,

        "proposal_rationale":
            value.proposal_rationale,

        "state":
            value.state.value,

        "actor":
            value.actor,

        "created_at":
            value.created_at,

        "previous_event_id":
            value.previous_event_id,

        "review_note":
            value.review_note,
    }


def _event_from_dict(
    data: dict,
) -> RelationshipEvent:

    return RelationshipEvent(
        schema_version=str(
            data["schema_version"]
        ),

        case_id=str(
            data["case_id"]
        ),

        authority_id=str(
            data["authority_id"]
        ),

        issue_analysis_id=str(
            data["issue_analysis_id"]
        ),

        element_id=str(
            data["element_id"]
        ),

        relationship_id=str(
            data["relationship_id"]
        ),

        event_id=str(
            data["event_id"]
        ),

        relationship_type=
            RelationshipType(
                data[
                    "relationship_type"
                ]
            ),

        left_evidence_key=str(
            data[
                "left_evidence_key"
            ]
        ),

        right_evidence_key=str(
            data[
                "right_evidence_key"
            ]
        ),

        proposal_rationale=str(
            data[
                "proposal_rationale"
            ]
        ),

        state=
            RelationshipReviewState(
                data["state"]
            ),

        actor=str(
            data["actor"]
        ),

        created_at=str(
            data["created_at"]
        ),

        previous_event_id=
            data.get(
                "previous_event_id"
            ),

        review_note=str(
            data.get(
                "review_note",
                "",
            )
        ),
    )


def _default_root() -> Path:

    configured = os.environ.get(
        "LEGALRAG_MATTER_ANALYSIS_LEDGER_ROOT"
    )

    if configured:
        return Path(
            configured
        )

    return (
        Path(__file__)
        .resolve()
        .parents[1]
        / "matter_analysis_ledger"
    )


def _case_path(
    case_id: str,
    root: Path | None = None,
) -> Path:

    if not _SAFE_CASE_ID.fullmatch(
        case_id
    ):
        raise MatterAnalysisLedgerError(
            "Case ID is not safe for "
            "ledger persistence."
        )

    return (
        (root or _default_root())
        / case_id
        / "relationship-events.jsonl"
    )


def _validate_chain(
    events: Iterable[
        RelationshipEvent
    ],
) -> dict[
    str,
    RelationshipEvent,
]:

    current: dict[
        str,
        RelationshipEvent,
    ] = {}

    for event in events:

        previous = current.get(
            event.relationship_id
        )

        if previous is None:

            if (
                event.state
                is not RelationshipReviewState.PROPOSED
            ):
                raise MatterAnalysisLedgerError(
                    "A relationship history "
                    "must begin with PROPOSED."
                )

            if (
                event.previous_event_id
                is not None
            ):
                raise MatterAnalysisLedgerError(
                    "Initial proposal has "
                    "a previous event."
                )

        else:

            if (
                previous.state
                is not RelationshipReviewState.PROPOSED
            ):
                raise MatterAnalysisLedgerError(
                    "A terminal relationship "
                    "review cannot be overwritten."
                )

            if (
                event.previous_event_id
                != previous.event_id
            ):
                raise MatterAnalysisLedgerError(
                    "Relationship event chain "
                    "is broken."
                )

            if (
                event.state
                not in {
                    RelationshipReviewState.APPROVED,
                    RelationshipReviewState.REJECTED,
                }
            ):
                raise MatterAnalysisLedgerError(
                    "Only APPROVED or REJECTED "
                    "may follow PROPOSED."
                )

        current[
            event.relationship_id
        ] = event

    return current


def load_relationship_events(
    *,
    case_id: str,
    authority_id: str | None = None,
    root: Path | None = None,
) -> tuple[
    RelationshipEvent,
    ...,
]:

    path = _case_path(
        case_id,
        root,
    )

    if not path.is_file():
        return ()

    values = []

    for number, line in enumerate(
        path.read_text(
            encoding="utf-8"
        ).splitlines(),
        start=1,
    ):

        if not line.strip():
            continue

        try:
            value = _event_from_dict(
                json.loads(
                    line
                )
            )

        except Exception as exc:
            raise MatterAnalysisLedgerError(
                "Invalid ledger event "
                f"at line {number}."
            ) from exc

        if (
            value.case_id
            != case_id
        ):
            raise MatterAnalysisLedgerError(
                "Ledger contains a "
                "foreign case event."
            )

        values.append(
            value
        )

    # Validate the complete append-only file before
    # applying an authority filter.
    _validate_chain(
        values
    )

    if authority_id is not None:
        values = [
            item
            for item in values
            if (
                item.authority_id
                == authority_id
            )
        ]

    return tuple(
        values
    )


def current_relationships(
    events: Iterable[
        RelationshipEvent
    ],
) -> tuple[
    RelationshipEvent,
    ...,
]:

    current = _validate_chain(
        tuple(
            events
        )
    )

    return tuple(
        sorted(
            current.values(),
            key=lambda item: (
                item.issue_analysis_id,
                item.element_id,
                item.relationship_type.value,
                item.left_evidence_key,
                item.right_evidence_key,
            ),
        )
    )


def _write_event(
    event: RelationshipEvent,
    *,
    root: Path | None = None,
) -> None:

    path = _case_path(
        event.case_id,
        root,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = (
        path.read_bytes()
        if path.exists()
        else b""
    )

    line = (
        json.dumps(
            _event_to_dict(
                event
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode(
        "utf-8"
    )

    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_bytes(
        existing
        + line
    )

    os.replace(
        temporary,
        path,
    )


def _utc_now() -> str:

    return (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
    )


def propose_relationship(
    *,
    case_id: str,
    authority_id: str,
    issue_analysis_id: str,
    element_id: str,
    relationship_type: RelationshipType,
    left_evidence_key: str,
    right_evidence_key: str,
    rationale: str,
    actor: str = "interactive_user",
    root: Path | None = None,
    created_at: str | None = None,
) -> RelationshipEvent:

    if (
        not isinstance(
            rationale,
            str,
        )
        or not rationale.strip()
    ):
        raise MatterAnalysisLedgerError(
            "A proposed relationship "
            "requires a rationale."
        )

    left, right = _canonical_pair(
        left_evidence_key,
        right_evidence_key,
    )

    existing = current_relationships(
        load_relationship_events(
            case_id=case_id,
            authority_id=authority_id,
            root=root,
        )
    )

    # V1 deliberately permits only one relationship
    # review history for a given evidence pair within
    # an issue element and analytical authority.
    #
    # A rejected relationship therefore cannot simply
    # be silently re-proposed. A later revision model
    # can explicitly model supersession/versioning.
    for item in existing:

        same_coordinate = (
            item.issue_analysis_id
            == issue_analysis_id

            and item.element_id
            == element_id

            and {
                item.left_evidence_key,
                item.right_evidence_key,
            }
            == {
                left,
                right,
            }
        )

        if same_coordinate:
            raise MatterAnalysisLedgerError(
                "This evidence pair already "
                "has a relationship review history "
                "for the current analytical authority."
            )

    relationship_id = derive_relationship_id(
        case_id=case_id,
        authority_id=authority_id,
        issue_analysis_id=issue_analysis_id,
        element_id=element_id,
        relationship_type=relationship_type,
        left_evidence_key=left,
        right_evidence_key=right,
    )

    timestamp = (
        created_at
        or _utc_now()
    )

    identity_payload = {
        "relationship_id":
            relationship_id,

        "state":
            RelationshipReviewState.PROPOSED.value,

        "actor":
            actor,

        "created_at":
            timestamp,

        "proposal_rationale":
            rationale.strip(),
    }

    event = RelationshipEvent(
        schema_version=
            RELATIONSHIP_EVENT_SCHEMA_VERSION,

        case_id=
            case_id,

        authority_id=
            authority_id,

        issue_analysis_id=
            issue_analysis_id,

        element_id=
            element_id,

        relationship_id=
            relationship_id,

        event_id=
            _event_id(
                identity_payload
            ),

        relationship_type=
            relationship_type,

        left_evidence_key=
            left,

        right_evidence_key=
            right,

        proposal_rationale=
            rationale.strip(),

        state=
            RelationshipReviewState.PROPOSED,

        actor=
            actor,

        created_at=
            timestamp,
    )

    _write_event(
        event,
        root=root,
    )

    return event


def review_relationship(
    *,
    case_id: str,
    authority_id: str,
    relationship_id: str,
    decision: RelationshipReviewState,
    actor: str = "interactive_user",
    review_note: str = "",
    root: Path | None = None,
    created_at: str | None = None,
) -> RelationshipEvent:

    if decision not in {
        RelationshipReviewState.APPROVED,
        RelationshipReviewState.REJECTED,
    }:
        raise MatterAnalysisLedgerError(
            "Review decision must be "
            "APPROVED or REJECTED."
        )

    events = load_relationship_events(
        case_id=case_id,
        authority_id=authority_id,
        root=root,
    )

    current = {
        item.relationship_id:
            item

        for item
        in current_relationships(
            events
        )
    }

    proposal = current.get(
        relationship_id
    )

    if proposal is None:
        raise MatterAnalysisLedgerError(
            "Relationship proposal "
            "is unavailable."
        )

    if (
        proposal.state
        is not RelationshipReviewState.PROPOSED
    ):
        raise MatterAnalysisLedgerError(
            "Relationship has already "
            "been reviewed."
        )

    timestamp = (
        created_at
        or _utc_now()
    )

    identity_payload = {
        "relationship_id":
            relationship_id,

        "state":
            decision.value,

        "actor":
            actor,

        "created_at":
            timestamp,

        "previous_event_id":
            proposal.event_id,

        "review_note":
            review_note.strip(),
    }

    event = RelationshipEvent(
        schema_version=
            RELATIONSHIP_EVENT_SCHEMA_VERSION,

        case_id=
            proposal.case_id,

        authority_id=
            proposal.authority_id,

        issue_analysis_id=
            proposal.issue_analysis_id,

        element_id=
            proposal.element_id,

        relationship_id=
            proposal.relationship_id,

        event_id=
            _event_id(
                identity_payload
            ),

        relationship_type=
            proposal.relationship_type,

        left_evidence_key=
            proposal.left_evidence_key,

        right_evidence_key=
            proposal.right_evidence_key,

        proposal_rationale=
            proposal.proposal_rationale,

        state=
            decision,

        actor=
            actor,

        created_at=
            timestamp,

        previous_event_id=
            proposal.event_id,

        review_note=
            review_note.strip(),
    )

    _write_event(
        event,
        root=root,
    )

    return event


def build_matter_analysis_ledger(
    *,
    authority,
    events: Iterable[
        RelationshipEvent
    ] = (),
) -> MatterAnalysisLedger:

    case_id = (
        authority.manifest.case_id
    )

    authority_id = (
        authority.manifest.authority_id
    )

    current = tuple(
        item
        for item
        in current_relationships(
            tuple(
                events
            )
        )
        if (
            item.case_id
            == case_id

            and item.authority_id
            == authority_id
        )
    )

    issues = []

    for issue in (
        authority
        .case_matrices
        .issue_matrix
    ):

        elements = []

        for element in (
            issue.element_records
        ):

            relationships = tuple(
                item
                for item
                in current
                if (
                    item.issue_analysis_id
                    == issue.issue_analysis_id

                    and item.element_id
                    == element.element_id
                )
            )

            elements.append(
                LedgerElement(
                    element_id=
                        element.element_id,

                    element_name=
                        element.element_name,

                    legal_question=
                        element.legal_question,

                    analytical_status=
                        _text(
                            element.analysis_status
                        ),

                    analytical_confidence=
                        _text(
                            element.analysis_confidence
                        ),

                    supporting_evidence_keys=
                        tuple(
                            element.supporting_evidence_keys
                        ),

                    adverse_evidence_keys=
                        tuple(
                            element.adverse_evidence_keys
                        ),

                    corroborative_evidence_keys=
                        tuple(
                            element.corroborative_evidence_keys
                        ),

                    conflicting_evidence_keys=
                        tuple(
                            element.conflicting_evidence_keys
                        ),

                    neutral_evidence_keys=
                        tuple(
                            element.neutral_evidence_keys
                        ),

                    evidential_gap_ids=
                        tuple(
                            element.evidential_gap_ids
                        ),

                    unresolved_matters=
                        tuple(
                            element.unresolved_matters
                        ),

                    provisional_analysis=
                        str(
                            element.provisional_analysis
                        ),

                    relationships=
                        relationships,
                )
            )

        issues.append(
            LedgerIssue(
                issue_analysis_id=
                    issue.issue_analysis_id,

                issue_definition_id=
                    issue.issue_definition_id,

                issue_definition_version=
                    issue.issue_definition_version,

                issue_name=
                    issue.issue_name,

                issue_summary=
                    issue.issue_summary,

                elements=
                    tuple(
                        elements
                    ),
            )
        )

    return MatterAnalysisLedger(
        case_id=
            case_id,

        authority_id=
            authority_id,

        issues=
            tuple(
                issues
            ),
    )
