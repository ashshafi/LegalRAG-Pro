"""Provider-neutral models for external practice-management matter sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Mapping


class MatterSourceContractError(ValueError):
    """Raised when an external matter source violates the connector contract."""


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MatterSourceContractError(f"{field_name} must be a non-empty string.")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    provider: str
    firm_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _required(self.provider, "provider").lower())
        object.__setattr__(self, "firm_id", _required(self.firm_id, "firm_id"))


@dataclass(frozen=True, slots=True)
class ConnectorCapabilities:
    list_matters: bool = True
    matter_metadata: bool = True
    parties: bool = True
    documents: bool = True
    document_bytes: bool = True
    incremental_changes: bool = False
    writeback: bool = False


@dataclass(frozen=True, slots=True)
class ExternalMatter:
    source_matter_id: str
    matter_reference: str
    title: str
    practice_area: str | None = None
    status: str | None = None
    source_metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_matter_id", _required(self.source_matter_id, "source_matter_id"))
        object.__setattr__(self, "matter_reference", _required(self.matter_reference, "matter_reference"))
        object.__setattr__(self, "title", _required(self.title, "title"))


@dataclass(frozen=True, slots=True)
class ExternalParty:
    source_party_id: str
    source_matter_id: str
    display_name: str
    party_role: str | None = None
    person_or_organisation: str | None = None
    source_metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_party_id", _required(self.source_party_id, "source_party_id"))
        object.__setattr__(self, "source_matter_id", _required(self.source_matter_id, "source_matter_id"))
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name"))


@dataclass(frozen=True, slots=True)
class ExternalDocument:
    source_document_id: str
    source_matter_id: str
    display_name: str
    media_type: str
    source_version_id: str | None = None
    modified_at: str | None = None
    source_size: int | None = None
    source_metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_document_id", _required(self.source_document_id, "source_document_id"))
        object.__setattr__(self, "source_matter_id", _required(self.source_matter_id, "source_matter_id"))
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name"))
        object.__setattr__(self, "media_type", _required(self.media_type, "media_type").lower())
        if self.source_size is not None and self.source_size < 0:
            raise MatterSourceContractError("source_size cannot be negative.")


@dataclass(frozen=True, slots=True)
class DocumentObservation:
    source_document_id: str
    source_version_id: str | None
    content_sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_document_id", _required(self.source_document_id, "source_document_id"))
        digest = _required(self.content_sha256, "content_sha256").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise MatterSourceContractError("content_sha256 must be 64 lowercase hex.")
        object.__setattr__(self, "content_sha256", digest)
        if self.byte_length < 0:
            raise MatterSourceContractError("byte_length cannot be negative.")


class SyncDisposition(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SyncPlanEntry:
    source_document_id: str
    disposition: SyncDisposition
    document: ExternalDocument | None
    current: DocumentObservation | None
    previous: DocumentObservation | None


@dataclass(frozen=True, slots=True)
class SyncPlan:
    provider: ProviderIdentity
    source_matter_id: str
    entries: tuple[SyncPlanEntry, ...]

    def counts(self) -> dict[SyncDisposition, int]:
        return {
            disposition: sum(1 for entry in self.entries if entry.disposition is disposition)
            for disposition in SyncDisposition
        }


def observe_bytes(*, source_document_id: str, source_version_id: str | None, content: bytes) -> DocumentObservation:
    if type(content) is not bytes:
        raise TypeError("content must be exact bytes.")
    return DocumentObservation(
        source_document_id=source_document_id,
        source_version_id=source_version_id,
        content_sha256=sha256(content).hexdigest(),
        byte_length=len(content),
    )
