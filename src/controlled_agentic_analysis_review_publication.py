"""Immutable publication for PRW1 professional-review events."""

from __future__ import annotations

from os import environ, link
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from controlled_agentic_analysis_review import (
    ProfessionalReviewError,
    ProfessionalReviewEvent,
    dumps_professional_review_event,
    loads_professional_review_event,
    project_professional_review,
    validate_professional_review_event,
)


DEFAULT_REVIEW_ROOT = Path("controlled_agentic_analysis_reviews") / "v1"


class ProfessionalReviewPublicationError(RuntimeError):
    """Raised when immutable PRW1 publication fails closed."""


def _fail(message: str, exc: Exception | None = None) -> None:
    if exc is None:
        raise ProfessionalReviewPublicationError(message)
    raise ProfessionalReviewPublicationError(message) from exc


def _root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    configured = environ.get("LEGALRAG_CONTROLLED_AGENT_REVIEW_ROOT", "").strip()
    return Path(configured) if configured else DEFAULT_REVIEW_ROOT


def _digest_component(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        _fail(f"{field_name} must be canonical sha256 identity.")
    digest = value[7:]
    if digest != digest.lower() or any(ch not in "0123456789abcdef" for ch in digest):
        _fail(f"{field_name} must be canonical sha256 identity.")
    return digest


def _events_dir(
    *,
    root: Path,
    case_id: str,
    observation_id: str,
) -> Path:
    if not isinstance(case_id, str) or not case_id.strip():
        _fail("case_id must be non-empty text.")
    if "/" in case_id or "\\" in case_id or case_id in (".", ".."):
        _fail("case_id must not contain path separators.")
    observation = _digest_component(
        observation_id,
        field_name="observation_id",
    )
    return root / case_id / "observations" / observation / "events"


def _event_path(
    *,
    root: Path,
    event: ProfessionalReviewEvent,
) -> Path:
    directory = _events_dir(
        root=root,
        case_id=event.case_id,
        observation_id=event.observation_id,
    )
    event_digest = _digest_component(event.event_id, field_name="event_id")
    return directory / f"{event_digest}.json"


def _safe_mkdir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(f"Unable to create professional review publication directory: {path}", exc)
    if not path.is_dir() or path.is_symlink():
        _fail(
            "Professional review publication directory is not a plain directory."
        )


def load_professional_review_events(
    *,
    case_id: str,
    observation_id: str,
    root: Path | None = None,
) -> tuple[ProfessionalReviewEvent, ...]:
    directory = _events_dir(
        root=_root(root),
        case_id=case_id,
        observation_id=observation_id,
    )
    if not directory.exists():
        return ()
    if not directory.is_dir() or directory.is_symlink():
        _fail("Professional review event path is not a plain directory.")

    events = []
    for path in sorted(directory.glob("*.json")):
        if not path.is_file() or path.is_symlink():
            _fail("Professional review publication contains a non-regular event path.")
        try:
            event = loads_professional_review_event(path.read_bytes())
        except (OSError, ProfessionalReviewError) as exc:
            _fail("Unable to read valid immutable professional review event.", exc)
        events.append(event)

    if not events:
        return ()

    # Files are content-addressed, not sequence-named. Reconstruct the one exact
    # previous_event_id chain rather than trusting lexical filename ordering.
    by_id = {event.event_id: event for event in events}
    if len(by_id) != len(events):
        _fail("Duplicate professional review event identity encountered.")

    roots = [event for event in events if event.previous_event_id is None]
    if len(roots) != 1:
        _fail("Professional review publication must contain one event-chain root.")

    ordered = [roots[0]]
    while len(ordered) < len(events):
        current_id = ordered[-1].event_id
        next_values = [
            event
            for event in events
            if event.previous_event_id == current_id
        ]
        if len(next_values) != 1:
            _fail("Professional review publication event chain is branched or incomplete.")
        ordered.append(next_values[0])

    try:
        project_professional_review(tuple(ordered))
    except ProfessionalReviewError as exc:
        _fail("Published professional review event chain is invalid.", exc)
    return tuple(ordered)


def publish_professional_review_event(
    *,
    event: ProfessionalReviewEvent,
    root: Path | None = None,
) -> Path:
    """Create one immutable event file; byte-identical republication is idempotent."""

    try:
        validate_professional_review_event(event)
    except ProfessionalReviewError as exc:
        _fail("Professional review event is invalid for publication.", exc)

    base = _root(root)
    directory = _events_dir(
        root=base,
        case_id=event.case_id,
        observation_id=event.observation_id,
    )
    _safe_mkdir(directory)

    existing_events = load_professional_review_events(
        case_id=event.case_id,
        observation_id=event.observation_id,
        root=base,
    )

    if existing_events:
        expected_previous = existing_events[-1].event_id
        if event.event_id in {item.event_id for item in existing_events}:
            target = _event_path(root=base, event=event)
            expected = dumps_professional_review_event(event).encode("utf-8")
            try:
                actual = target.read_bytes()
            except OSError as exc:
                _fail("Unable to read existing professional review publication.", exc)
            if actual != expected:
                _fail(
                    "Existing immutable professional review event conflicts with canonical bytes."
                )
            return target
        if event.previous_event_id != expected_previous:
            _fail(
                "Professional review publication event does not extend the current exact chain."
            )
    elif event.previous_event_id is not None:
        _fail("First professional review publication event must have no previous_event_id.")

    candidate_chain = existing_events + (event,)
    try:
        project_professional_review(candidate_chain)
    except ProfessionalReviewError as exc:
        _fail("Professional review publication would create an invalid event chain.", exc)

    target = _event_path(root=base, event=event)
    payload = dumps_professional_review_event(event).encode("utf-8")

    if target.exists():
        if not target.is_file() or target.is_symlink():
            _fail("Professional review publication target is not a plain regular file.")
        try:
            actual = target.read_bytes()
        except OSError as exc:
            _fail("Unable to read existing professional review event.", exc)
        if actual == payload:
            return target
        _fail("Existing immutable professional review event conflicts with this publication.")

    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=".review-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            temporary = Path(handle.name)

        # Hard-link creation gives create-if-absent semantics without replacing
        # an existing immutable target.
        try:
            link(temporary, target)
        except FileExistsError:
            actual = target.read_bytes()
            if actual != payload:
                _fail(
                    "Concurrent immutable professional review publication conflicts with this event."
                )
        except OSError as exc:
            _fail(
                "Atomic create-if-absent professional review publication is unavailable.",
                exc,
            )
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    if not target.is_file() or target.is_symlink():
        _fail("Published professional review event is not a plain regular file.")
    try:
        actual = target.read_bytes()
    except OSError as exc:
        _fail("Unable to verify published professional review event.", exc)
    if actual != payload:
        _fail("Published professional review event bytes differ from canonical payload.")

    return target


__all__ = [
    "DEFAULT_REVIEW_ROOT",
    "ProfessionalReviewPublicationError",
    "load_professional_review_events",
    "publish_professional_review_event",
]
