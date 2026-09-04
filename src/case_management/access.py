"""Deterministic multi-user matter-access identities for LegalRAG Pro."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

_USER_NAMESPACE = UUID("c640b61f-41fd-5a68-9363-87905ed621ce")


class MatterRole(StrEnum):
    """Solicitor-facing role for one user's access to one matter."""

    OWNER = "owner"
    SOLICITOR = "solicitor"
    REVIEWER = "reviewer"
    READ_ONLY = "read_only"


class MembershipStatus(StrEnum):
    """Lifecycle state for one matter membership."""

    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """One authenticated LegalRAG user derived from a canonical email claim."""

    user_id: str
    email: str

    @classmethod
    def from_email(cls, email: str) -> "UserIdentity":
        canonical = _canonical_email(email)
        return cls(
            user_id=str(uuid5(_USER_NAMESPACE, canonical)),
            email=canonical,
        )


@dataclass(frozen=True, slots=True)
class MatterMembership:
    """One user's governed access relationship to one matter."""

    case_id: str
    user_id: str
    role: MatterRole
    status: MembershipStatus = MembershipStatus.ACTIVE

    @property
    def is_active(self) -> bool:
        return self.status is MembershipStatus.ACTIVE

    @property
    def can_manage_matter(self) -> bool:
        return self.is_active and self.role in {
            MatterRole.OWNER,
            MatterRole.SOLICITOR,
        }


@dataclass(frozen=True, slots=True)
class MatterAccessContext:
    """Validated authenticated-user access to one selected matter."""

    user: UserIdentity
    membership: MatterMembership

    @property
    def case_id(self) -> str:
        return self.membership.case_id

    @property
    def role(self) -> MatterRole:
        return self.membership.role


def _canonical_email(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("User email must be text.")
    candidate = value.strip().casefold()
    if not candidate or "@" not in candidate:
        raise ValueError("User email must be a canonical email address.")
    return candidate


__all__ = [
    "MatterAccessContext",
    "MatterMembership",
    "MatterRole",
    "MembershipStatus",
    "UserIdentity",
]
