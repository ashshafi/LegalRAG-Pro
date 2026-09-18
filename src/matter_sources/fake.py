"""Deterministic in-memory provider for connector and sync contract tests."""

from __future__ import annotations

from dataclasses import replace

from matter_sources.base import MatterSourceConnector, MatterSourceUnavailableError
from matter_sources.models import ConnectorCapabilities, ExternalDocument, ExternalMatter, ExternalParty, ProviderIdentity


class FakeMatterSourceConnector(MatterSourceConnector):
    def __init__(self, *, provider: ProviderIdentity, matters: tuple[ExternalMatter, ...],
                 parties: tuple[ExternalParty, ...] = (), documents: tuple[ExternalDocument, ...] = (),
                 content: dict[str, bytes] | None = None) -> None:
        self._provider = provider
        self._matters = {item.source_matter_id: item for item in matters}
        self._parties = tuple(parties)
        self._documents = {item.source_document_id: item for item in documents}
        self._content = dict(content or {})
        self._failed_document_ids: set[str] = set()

    def provider_identity(self) -> ProviderIdentity:
        return self._provider

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities()

    def list_matters(self, query: str | None = None) -> tuple[ExternalMatter, ...]:
        values = sorted(self._matters.values(), key=lambda item: item.matter_reference)
        if query is None or not query.strip():
            return tuple(values)
        needle = query.casefold().strip()
        return tuple(item for item in values if needle in item.title.casefold() or needle in item.matter_reference.casefold())

    def get_matter(self, source_matter_id: str) -> ExternalMatter:
        try:
            return self._matters[source_matter_id]
        except KeyError as exc:
            raise MatterSourceUnavailableError("Matter is unavailable.") from exc

    def list_parties(self, source_matter_id: str) -> tuple[ExternalParty, ...]:
        self.get_matter(source_matter_id)
        return tuple(sorted((item for item in self._parties if item.source_matter_id == source_matter_id),
                            key=lambda item: item.source_party_id))

    def list_documents(self, source_matter_id: str) -> tuple[ExternalDocument, ...]:
        self.get_matter(source_matter_id)
        return tuple(sorted((item for item in self._documents.values() if item.source_matter_id == source_matter_id),
                            key=lambda item: item.source_document_id))

    def fetch_document_bytes(self, source_document_id: str) -> bytes:
        if source_document_id in self._failed_document_ids:
            raise MatterSourceUnavailableError("Injected document read failure.")
        try:
            value = self._content[source_document_id]
        except KeyError as exc:
            raise MatterSourceUnavailableError("Document content is unavailable.") from exc
        if type(value) is not bytes:
            raise MatterSourceUnavailableError("Document content is not exact bytes.")
        return value

    def replace_document_bytes(self, source_document_id: str, content: bytes, *, source_version_id: str | None = None) -> None:
        if type(content) is not bytes:
            raise TypeError("content must be exact bytes.")
        document = self._documents[source_document_id]
        self._content[source_document_id] = content
        self._documents[source_document_id] = replace(document, source_version_id=source_version_id, source_size=len(content))

    def remove_document(self, source_document_id: str) -> None:
        self._documents.pop(source_document_id, None)
        self._content.pop(source_document_id, None)
        self._failed_document_ids.discard(source_document_id)

    def fail_document_fetch(self, source_document_id: str) -> None:
        self._failed_document_ids.add(source_document_id)
