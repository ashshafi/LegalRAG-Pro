from __future__ import annotations

from dataclasses import dataclass

TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME = "targeted_candidate_transcriptions_v1"
TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND = "targeted_candidate_transcription"
TARGETED_CANDIDATE_SEARCH_DISCOVERY_SCOPE = "targeted_candidate_discovery_only"
TARGETED_CANDIDATE_ACTIVATION_CONTRACT_SHA256 = "b58841d281f0723df80762c578a133d0ebaf9f180a7822d8a55f23a05c072ed3"


@dataclass(frozen=True)
class TargetedCandidateActivationAuthority:
    case_id: str
    candidate_record_id: str
    transcription_sha256: str
    transcription_bytes: int
    binding_id: str
    publication_receipt_id: str
    review_event_id: str
    derived_artifact_sha256: str
    embedding_model: str
    collection_name: str = TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME


@dataclass(frozen=True)
class TargetedCandidateActivationRow:
    candidate_record_id: str
    document: str
    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    page_number: int
    original_blob_sha256: str
    transcription_sha256: str
    derived_artifact_sha256: str
    profile_id: str
    binding_id: str
    parent_artifact_sha256: str
    crop_name: str
    bbox: tuple[int, int, int, int]
    publication_receipt_id: str
    review_event_id: str
    authority_kind: str = TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND

    def metadata(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "source_document_instance_id": self.source_document_instance_id,
            "source_snapshot_id": self.source_snapshot_id,
            "page_number": self.page_number,
            "original_blob_sha256": self.original_blob_sha256,
            "transcription_sha256": self.transcription_sha256,
            "derived_artifact_sha256": self.derived_artifact_sha256,
            "profile_id": self.profile_id,
            "binding_id": self.binding_id,
            "parent_artifact_sha256": self.parent_artifact_sha256,
            "crop_name": self.crop_name,
            "bbox": ",".join(str(value) for value in self.bbox),
            "publication_receipt_id": self.publication_receipt_id,
            "review_event_id": self.review_event_id,
            "authority_kind": self.authority_kind,
        }
