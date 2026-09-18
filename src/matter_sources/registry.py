"""Persistent external matter/document source registry for LegalRAG Pro.

The registry records synchronization identity and last successfully captured
external document observations. It is deliberately separate from professional
analytical state.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping

from matter_sources.models import (
    DocumentObservation,
    ProviderIdentity,
    SyncDisposition,
    SyncPlan,
)


class MatterSourceRegistryError(RuntimeError):
    """Raised when external matter registry state cannot be safely persisted."""


@dataclass(frozen=True, slots=True)
class ExternalMatterBinding:
    provider: str
    firm_id: str
    source_matter_id: str
    case_id: str
    matter_reference: str
    title: str
    last_successful_sync_at: str | None


@dataclass(frozen=True, slots=True)
class RegisteredDocumentState:
    provider: str
    firm_id: str
    source_matter_id: str
    source_document_id: str
    source_version_id: str | None
    content_sha256: str
    byte_length: int
    availability: str
    last_successful_sync_at: str


def default_registry_path() -> Path:
    from persistence_paths import data_root

    return data_root() / "integrations" / "matter_sources.sqlite3"


class MatterSourceRegistry:
    """SQLite-backed source identity registry.

    Construction does not connect to LEAP or mutate professional matter state.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else default_registry_path()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            self._ensure_schema(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS matter_source_bindings (
                provider TEXT NOT NULL,
                firm_id TEXT NOT NULL,
                source_matter_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                matter_reference TEXT NOT NULL,
                title TEXT NOT NULL,
                last_successful_sync_at TEXT,
                PRIMARY KEY (provider, firm_id, source_matter_id),
                UNIQUE (provider, firm_id, case_id)
            );

            CREATE TABLE IF NOT EXISTS matter_source_documents (
                provider TEXT NOT NULL,
                firm_id TEXT NOT NULL,
                source_matter_id TEXT NOT NULL,
                source_document_id TEXT NOT NULL,
                source_version_id TEXT,
                content_sha256 TEXT NOT NULL,
                byte_length INTEGER NOT NULL,
                availability TEXT NOT NULL CHECK (availability IN ('available','unavailable')),
                last_successful_sync_at TEXT NOT NULL,
                PRIMARY KEY (provider, firm_id, source_matter_id, source_document_id),
                FOREIGN KEY (provider, firm_id, source_matter_id)
                    REFERENCES matter_source_bindings(provider, firm_id, source_matter_id)
                    ON DELETE RESTRICT
            );
            """
        )
        connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def load_binding(
        self,
        provider: ProviderIdentity,
        source_matter_id: str,
    ) -> ExternalMatterBinding | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT provider, firm_id, source_matter_id, case_id,
                       matter_reference, title, last_successful_sync_at
                FROM matter_source_bindings
                WHERE provider = ? AND firm_id = ? AND source_matter_id = ?
                """,
                (provider.provider, provider.firm_id, source_matter_id),
            ).fetchone()
        if row is None:
            return None
        return ExternalMatterBinding(**dict(row))

    def load_observations(
        self,
        provider: ProviderIdentity,
        source_matter_id: str,
    ) -> dict[str, DocumentObservation]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT source_document_id, source_version_id,
                       content_sha256, byte_length
                FROM matter_source_documents
                WHERE provider = ? AND firm_id = ? AND source_matter_id = ?
                """,
                (provider.provider, provider.firm_id, source_matter_id),
            ).fetchall()
        return {
            row["source_document_id"]: DocumentObservation(
                source_document_id=row["source_document_id"],
                source_version_id=row["source_version_id"],
                content_sha256=row["content_sha256"],
                byte_length=int(row["byte_length"]),
            )
            for row in rows
        }

    def list_document_states(
        self,
        provider: ProviderIdentity,
        source_matter_id: str,
    ) -> tuple[RegisteredDocumentState, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT provider, firm_id, source_matter_id, source_document_id,
                       source_version_id, content_sha256, byte_length,
                       availability, last_successful_sync_at
                FROM matter_source_documents
                WHERE provider = ? AND firm_id = ? AND source_matter_id = ?
                ORDER BY source_document_id
                """,
                (provider.provider, provider.firm_id, source_matter_id),
            ).fetchall()
        return tuple(RegisteredDocumentState(**dict(row)) for row in rows)

    def record_successful_sync(
        self,
        *,
        provider: ProviderIdentity,
        source_matter_id: str,
        case_id: str,
        matter_reference: str,
        title: str,
        plan: SyncPlan,
    ) -> None:
        """Atomically advance source registry state after governed sync success."""
        if plan.provider != provider:
            raise MatterSourceRegistryError("Sync plan provider does not match registry provider.")
        if plan.source_matter_id != source_matter_id:
            raise MatterSourceRegistryError("Sync plan matter does not match registry matter.")

        now = self._now()
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT case_id FROM matter_source_bindings
                    WHERE provider = ? AND firm_id = ? AND source_matter_id = ?
                    """,
                    (provider.provider, provider.firm_id, source_matter_id),
                ).fetchone()
                if existing is not None and existing["case_id"] != case_id:
                    raise MatterSourceRegistryError(
                        "External matter is already bound to a different LegalRAG matter."
                    )

                connection.execute(
                    """
                    INSERT INTO matter_source_bindings (
                        provider, firm_id, source_matter_id, case_id,
                        matter_reference, title, last_successful_sync_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider, firm_id, source_matter_id)
                    DO UPDATE SET
                        matter_reference = excluded.matter_reference,
                        title = excluded.title,
                        last_successful_sync_at = excluded.last_successful_sync_at
                    """,
                    (
                        provider.provider,
                        provider.firm_id,
                        source_matter_id,
                        case_id,
                        matter_reference,
                        title,
                        now,
                    ),
                )

                for entry in plan.entries:
                    if entry.disposition is SyncDisposition.UNAVAILABLE:
                        if entry.previous is None:
                            raise MatterSourceRegistryError(
                                "Unavailable source has no prior captured observation."
                            )
                        observation = entry.previous
                        availability = "unavailable"
                    else:
                        if entry.current is None:
                            raise MatterSourceRegistryError(
                                "Available source has no current observation."
                            )
                        observation = entry.current
                        availability = "available"

                    connection.execute(
                        """
                        INSERT INTO matter_source_documents (
                            provider, firm_id, source_matter_id, source_document_id,
                            source_version_id, content_sha256, byte_length,
                            availability, last_successful_sync_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(provider, firm_id, source_matter_id, source_document_id)
                        DO UPDATE SET
                            source_version_id = excluded.source_version_id,
                            content_sha256 = excluded.content_sha256,
                            byte_length = excluded.byte_length,
                            availability = excluded.availability,
                            last_successful_sync_at = excluded.last_successful_sync_at
                        """,
                        (
                            provider.provider,
                            provider.firm_id,
                            source_matter_id,
                            observation.source_document_id,
                            observation.source_version_id,
                            observation.content_sha256,
                            observation.byte_length,
                            availability,
                            now,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


__all__ = [
    "ExternalMatterBinding",
    "MatterSourceRegistry",
    "MatterSourceRegistryError",
    "RegisteredDocumentState",
    "default_registry_path",
]
