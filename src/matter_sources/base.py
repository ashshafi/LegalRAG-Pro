"""Abstract read-only matter-source connector boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod

from matter_sources.models import ConnectorCapabilities, ExternalDocument, ExternalMatter, ExternalParty, ProviderIdentity


class MatterSourceError(RuntimeError):
    """Base error for provider and connector failures."""


class MatterSourceUnavailableError(MatterSourceError):
    """Raised when the external provider cannot satisfy a read request."""


class MatterSourceConnector(ABC):
    """Provider-neutral, read-only connector used by LegalRAG matter import."""

    @abstractmethod
    def provider_identity(self) -> ProviderIdentity:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        raise NotImplementedError

    @abstractmethod
    def list_matters(self, query: str | None = None) -> tuple[ExternalMatter, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_matter(self, source_matter_id: str) -> ExternalMatter:
        raise NotImplementedError

    @abstractmethod
    def list_parties(self, source_matter_id: str) -> tuple[ExternalParty, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self, source_matter_id: str) -> tuple[ExternalDocument, ...]:
        raise NotImplementedError

    @abstractmethod
    def fetch_document_bytes(self, source_document_id: str) -> bytes:
        raise NotImplementedError
