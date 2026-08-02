"""SQLite persistence for LegalRAG Pro cases."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Iterator

from case_management.models import Case

LOGGER = logging.getLogger(__name__)

DEFAULT_DB_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "data" / "cases.sqlite3"
)


class CaseNotFoundError(LookupError):
    """Raised when a requested case does not exist."""


class CaseRepository:
    """Persist and retrieve case metadata using SQLite."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Initialise the repository and ensure its schema exists.

        Args:
            db_path: SQLite database location. Parent directories are created
                automatically when required.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise_schema()

    @property
    def db_path(self) -> Path:
        """Return the repository database path."""
        return self._db_path

    def create(self, case: Case) -> Case:
        """Persist a new case."""
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO cases (
                        case_id,
                        name,
                        case_number,
                        claimant,
                        respondent,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._to_row(case),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A case with ID {case.case_id!r} already exists."
            ) from exc

        LOGGER.info("Created case %s", case.case_id)
        return case

    def get(self, case_id: str) -> Case | None:
        """Return a case by internal ID, or None if it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()

        return None if row is None else self._from_row(row)

    def list_all(self) -> list[Case]:
        """Return all cases ordered by most recently updated first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM cases
                ORDER BY updated_at DESC, name ASC
                """
            ).fetchall()

        return [self._from_row(row) for row in rows]

    def update(self, case: Case) -> Case:
        """Persist changes to an existing case."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET
                    name = ?,
                    case_number = ?,
                    claimant = ?,
                    respondent = ?,
                    status = ?,
                    created_at = ?,
                    updated_at = ?
                WHERE case_id = ?
                """,
                (
                    case.name,
                    case.case_number,
                    case.claimant,
                    case.respondent,
                    case.status,
                    case.created_at.isoformat(),
                    case.updated_at.isoformat(),
                    case.case_id,
                ),
            )

            updated_rows = cursor.rowcount

        if updated_rows == 0:
            raise CaseNotFoundError(
                f"Case {case.case_id!r} was not found."
            )

        LOGGER.info("Updated case %s", case.case_id)
        return case

    def delete(self, case_id: str) -> bool:
        """Delete case metadata and return whether a row was removed."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM cases WHERE case_id = ?",
                (case_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            LOGGER.info("Deleted case %s", case_id)

        return deleted

    def _initialise_schema(self) -> None:
        """Create the cases table if it does not already exist."""
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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection and always close it.

        Explicit close is required on Windows so temporary SQLite
        database files are not left locked after tests.
        """
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _to_row(
        case: Case,
    ) -> tuple[
        str,
        str,
        str | None,
        str | None,
        str | None,
        str,
        str,
        str,
    ]:
        """Convert a Case instance to a SQLite row tuple."""
        return (
            case.case_id,
            case.name,
            case.case_number,
            case.claimant,
            case.respondent,
            case.status,
            case.created_at.isoformat(),
            case.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Case:
        """Convert a SQLite row into a Case instance."""
        from datetime import datetime

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