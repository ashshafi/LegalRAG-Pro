from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


DERIVED_SEARCH_COLLECTION_NAME = "derived_transcriptions_v1"
DERIVED_SEARCH_AUTHORITY_KIND = "derived_transcription"
DERIVED_SEARCH_DISCOVERY_SCOPE = "candidate_discovery_only"


class ActivationError(RuntimeError):
    """Fail-closed derived-search activation failure."""


class ActivationRowState(str, Enum):
    MISSING = "MISSING"
    EXACT = "EXACT"
    CONFLICTING = "CONFLICTING"


class ActivationIndexAction(str, Enum):
    ADDED = "ADDED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class ActivationAuthority:
    case_id: str
    candidate_id: str
    transcription_sha256: str
    transcription_bytes: int
    embedding_model: str
    collection_name: str = DERIVED_SEARCH_COLLECTION_NAME


@dataclass(frozen=True)
class ActivationRow:
    candidate_id: str
    document: str
    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    page: int
    source_original_blob_sha256: str
    derived_record_id: str
    transcription_sha256: str
    embedded_image_sha256: str
    profile_id: str
    authority_kind: str = DERIVED_SEARCH_AUTHORITY_KIND

    def metadata(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "source_document_instance_id":
                self.source_document_instance_id,
            "source_snapshot_id":
                self.source_snapshot_id,
            "page": self.page,
            "source_original_blob_sha256":
                self.source_original_blob_sha256,
            "derived_record_id":
                self.derived_record_id,
            "transcription_sha256":
                self.transcription_sha256,
            "embedded_image_sha256":
                self.embedded_image_sha256,
            "profile_id":
                self.profile_id,
            "authority_kind":
                self.authority_kind,
        }


@dataclass(frozen=True)
class ActivationInspection:
    state: ActivationRowState
    reason: str


@dataclass(frozen=True)
class ActivationIndexResult:
    action: ActivationIndexAction
    candidate_id: str
    state: ActivationRowState


@dataclass(frozen=True)
class ActivationQueryHit:
    candidate_id: str
    document: str
    metadata: Mapping[str, object]
    distance: float | None


@dataclass(frozen=True)
class ActivationQueryResult:
    hits: tuple[ActivationQueryHit, ...]
    discovery_scope: str = DERIVED_SEARCH_DISCOVERY_SCOPE
    negative_finding_authoritative: bool = False
