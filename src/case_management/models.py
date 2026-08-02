"""Domain models for LegalRAG Pro case management."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Case:
    """Represent a legal case managed by LegalRAG Pro.

    The internal ``case_id`` is deliberately separate from an external tribunal
    or court reference so that a case remains stable if its external reference
    is missing or changes.

    Attributes:
        case_id: Stable internal UUID string.
        name: Human-readable case name.
        case_number: Optional tribunal or court reference.
        claimant: Optional claimant name.
        respondent: Optional respondent name.
        status: Lightweight lifecycle state for the case.
        created_at: UTC creation timestamp.
        updated_at: UTC last-update timestamp.
    """

    case_id: str
    name: str
    case_number: str | None = None
    claimant: str | None = None
    respondent: str | None = None
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Validate and normalise model values."""

        name = self.name.strip()
        if not name:
            raise ValueError("Case name must not be empty.")

        status = self.status.strip().lower()
        if not status:
            raise ValueError("Case status must not be empty.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "case_number", self._clean_optional(self.case_number))
        object.__setattr__(self, "claimant", self._clean_optional(self.claimant))
        object.__setattr__(self, "respondent", self._clean_optional(self.respondent))

        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Case timestamps must be timezone-aware.")

    @classmethod
    def create(
        cls,
        name: str,
        *,
        case_number: str | None = None,
        claimant: str | None = None,
        respondent: str | None = None,
        status: str = "active",
    ) -> Case:
        """Create a new case with a generated stable identifier."""

        now = utc_now()
        return cls(
            case_id=str(uuid4()),
            name=name,
            case_number=case_number,
            claimant=claimant,
            respondent=respondent,
            status=status,
            created_at=now,
            updated_at=now,
        )

    def updated(
        self,
        *,
        name: str | None = None,
        case_number: str | None = None,
        claimant: str | None = None,
        respondent: str | None = None,
        status: str | None = None,
    ) -> Case:
        """Return a copy containing requested updates and a new timestamp."""

        return replace(
            self,
            name=self.name if name is None else name,
            case_number=self.case_number if case_number is None else case_number,
            claimant=self.claimant if claimant is None else claimant,
            respondent=self.respondent if respondent is None else respondent,
            status=self.status if status is None else status,
            updated_at=utc_now(),
        )

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
