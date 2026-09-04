"""SQLite persistence for LegalRAG Pro cases and matter membership."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterator

from case_management.access import (
    MatterAccessContext,
    MatterMembership,
    MatterRole,
    MembershipStatus,
    UserIdentity,
    require_matter_mutation,
)
from case_management.models import Case

LOGGER = logging.getLogger(__name__)

DEFAULT_DB_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "data" / "cases.sqlite3"
)


class CaseNotFoundError(LookupError):
    """Raised when a requested case does not exist."""


class MatterAccessError(PermissionError):
    """Raised when a user has no active membership for a requested matter."""


class CaseRepository:
    """Persist cases and fail-closed user-to-matter membership using SQLite."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def create(self, case: Case) -> Case:
        """Persist a new case without implicitly granting access."""
        try:
            with self._connect() as connection:
                self._insert_case(connection, case)
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A case with ID {case.case_id!r} already exists."
            ) from exc
        LOGGER.info("Created case %s", case.case_id)
        return case

    def create_for_user(self, case: Case, user: UserIdentity) -> Case:
        """Atomically create a matter and grant its creator owner access."""
        try:
            with self._connect() as connection:
                self._upsert_user(connection, user)
                self._insert_case(connection, case)
                self._upsert_membership(
                    connection,
                    MatterMembership(
                        case_id=case.case_id,
                        user_id=user.user_id,
                        role=MatterRole.OWNER,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A case with ID {case.case_id!r} already exists."
            ) from exc
        LOGGER.info("Created case %s for user %s", case.case_id, user.user_id)
        return case

    def get(self, case_id: str) -> Case | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_all(self) -> list[Case]:
        """Return every case; reserved for trusted administrative/internal use."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM cases
                ORDER BY updated_at DESC, name ASC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_for_user(self, user: UserIdentity) -> list[Case]:
        """Return only cases with an active membership for this exact user."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*
                FROM cases AS c
                INNER JOIN matter_memberships AS m
                    ON m.case_id = c.case_id
                WHERE m.user_id = ? AND m.status = ?
                ORDER BY c.updated_at DESC, c.name ASC
                """,
                (user.user_id, MembershipStatus.ACTIVE.value),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def require_access(self, user: UserIdentity, case_id: str) -> MatterAccessContext:
        """Resolve one active membership or fail closed."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT case_id, user_id, role, status
                FROM matter_memberships
                WHERE case_id = ? AND user_id = ? AND status = ?
                """,
                (case_id, user.user_id, MembershipStatus.ACTIVE.value),
            ).fetchone()
        if row is None:
            raise MatterAccessError("The authenticated user cannot access this matter.")
        membership = self._membership_from_row(row)
        return MatterAccessContext(user=user, membership=membership)

    def list_memberships(
        self,
        *,
        actor: UserIdentity,
        case_id: str,
    ) -> tuple[tuple[UserIdentity, MatterMembership], ...]:
        """Return active matter members when the actor can access the matter."""
        self.require_access(actor, case_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT u.user_id, u.email, m.case_id, m.role, m.status
                FROM matter_memberships AS m
                INNER JOIN legalrag_users AS u ON u.user_id = m.user_id
                WHERE m.case_id = ? AND m.status = ?
                ORDER BY
                    CASE m.role
                        WHEN 'owner' THEN 0
                        WHEN 'solicitor' THEN 1
                        WHEN 'reviewer' THEN 2
                        ELSE 3
                    END,
                    u.email ASC
                """,
                (case_id, MembershipStatus.ACTIVE.value),
            ).fetchall()
        return tuple(
            (
                UserIdentity(user_id=row["user_id"], email=row["email"]),
                self._membership_from_row(row),
            )
            for row in rows
        )

    def grant_membership(
        self,
        *,
        actor: UserIdentity,
        case_id: str,
        user: UserIdentity,
        role: MatterRole,
    ) -> MatterMembership:
        """Grant or update membership when the actor is the matter owner."""
        actor_access = self.require_access(actor, case_id)
        if actor_access.role is not MatterRole.OWNER:
            raise MatterAccessError("Only the matter owner may grant matter access.")
        membership = MatterMembership(
            case_id=case_id,
            user_id=user.user_id,
            role=MatterRole(role),
        )
        with self._connect() as connection:
            self._upsert_user(connection, user)
            self._upsert_membership(connection, membership)
        return membership

    def revoke_membership(
        self,
        *,
        actor: UserIdentity,
        case_id: str,
        user: UserIdentity,
    ) -> MatterMembership:
        """Revoke another user's membership when the actor is the matter owner."""
        actor_access = self.require_access(actor, case_id)
        if actor_access.role is not MatterRole.OWNER:
            raise MatterAccessError("Only the matter owner may revoke matter access.")
        if actor.user_id == user.user_id:
            raise MatterAccessError("The current matter owner cannot revoke their own access.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM matter_memberships WHERE case_id = ? AND user_id = ?",
                (case_id, user.user_id),
            ).fetchone()
            if row is None:
                raise MatterAccessError("The requested membership does not exist.")
            membership = MatterMembership(
                case_id=case_id,
                user_id=user.user_id,
                role=MatterRole(row["role"]),
                status=MembershipStatus.REVOKED,
            )
            self._upsert_membership(connection, membership)
        return membership

    def assign_unowned_cases_to_user(self, user: UserIdentity) -> tuple[str, ...]:
        """Explicitly bootstrap legacy matters that currently have no membership.

        This operation is intentionally never called automatically by the UI.
        It exists for a separately authorised migration step before strict
        multi-user activation.
        """
        with self._connect() as connection:
            self._upsert_user(connection, user)
            rows = connection.execute(
                """
                SELECT c.case_id
                FROM cases AS c
                WHERE NOT EXISTS (
                    SELECT 1 FROM matter_memberships AS m
                    WHERE m.case_id = c.case_id
                )
                ORDER BY c.case_id ASC
                """
            ).fetchall()
            case_ids = tuple(row["case_id"] for row in rows)
            for case_id in case_ids:
                self._upsert_membership(
                    connection,
                    MatterMembership(
                        case_id=case_id,
                        user_id=user.user_id,
                        role=MatterRole.OWNER,
                    ),
                )
        return case_ids

    def update(self, case: Case, *, access: MatterAccessContext) -> Case:
        require_matter_mutation(access)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET name = ?, case_number = ?, claimant = ?, respondent = ?,
                    status = ?, created_at = ?, updated_at = ?
                WHERE case_id = ?
                """,
                (
                    case.name, case.case_number, case.claimant, case.respondent,
                    case.status, case.created_at.isoformat(), case.updated_at.isoformat(),
                    case.case_id,
                ),
            )
            updated_rows = cursor.rowcount
        if updated_rows == 0:
            raise CaseNotFoundError(f"Case {case.case_id!r} was not found.")
        LOGGER.info("Updated case %s", case.case_id)
        return case

    def delete(self, case_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            LOGGER.info("Deleted case %s", case_id)
        return deleted

    def _initialise_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    case_number TEXT,
                    claimant TEXT,
                    respondent TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS legalrag_users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS matter_memberships (
                    case_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (case_id, user_id),
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES legalrag_users(user_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_matter_memberships_user_status "
                "ON matter_memberships(user_id, status, case_id)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _insert_case(connection: sqlite3.Connection, case: Case) -> None:
        connection.execute(
            """
            INSERT INTO cases (
                case_id, name, case_number, claimant, respondent, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            CaseRepository._to_row(case),
        )

    @staticmethod
    def _upsert_user(connection: sqlite3.Connection, user: UserIdentity) -> None:
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO legalrag_users (user_id, email, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email = excluded.email,
                updated_at = excluded.updated_at
            """,
            (user.user_id, user.email, now, now),
        )

    @staticmethod
    def _upsert_membership(
        connection: sqlite3.Connection,
        membership: MatterMembership,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO matter_memberships (
                case_id, user_id, role, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id, user_id) DO UPDATE SET
                role = excluded.role,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                membership.case_id,
                membership.user_id,
                membership.role.value,
                membership.status.value,
                now,
                now,
            ),
        )

    @staticmethod
    def _to_row(case: Case) -> tuple[str, str, str | None, str | None, str | None, str, str, str]:
        return (
            case.case_id, case.name, case.case_number, case.claimant,
            case.respondent, case.status, case.created_at.isoformat(),
            case.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Case:
        return Case(
            case_id=row["case_id"],
            name=row["name"],
            case_number=row["case_number"],
            claimant=row["claimant"],
            respondent=row["respondent"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _membership_from_row(row: sqlite3.Row) -> MatterMembership:
        return MatterMembership(
            case_id=row["case_id"],
            user_id=row["user_id"],
            role=MatterRole(row["role"]),
            status=MembershipStatus(row["status"]),
        )


__all__ = ["CaseNotFoundError", "CaseRepository", "MatterAccessError"]
