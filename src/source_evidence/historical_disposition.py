"""Deterministic HM2 historical/current evidence disposition.

HM2.2 is a text-free model layer. It binds frozen HM1 historical inventory
records to frozen PFCR1 prospective mappings without opening Chroma, reading
or publishing source-store objects, capturing historical text, or changing
historical provenance.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, replace
from enum import StrEnum

from .identity import (
    canonical_json_bytes,
    canonical_uuid,
    derive_sha256_id,
    sha256_bytes,
)
from .migration import (
    HistoricalMigrationDecision,
    HistoricalMigrationReport,
    historical_migration_report_to_dict,
)
from .models import BindingClass
from .reingestion_transition import (
    ProspectiveLegacyKeyMapping,
    ProspectiveReingestionReport,
    prospective_reingestion_report_to_dict,
)


HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION = (
    "historical-evidence-disposition-manifest/1.0"
)


class HistoricalEvidenceDispositionError(RuntimeError):
    """Raised when frozen historical/current state cannot reconcile exactly."""


class HistoricalEvidenceRelationship(StrEnum):
    """Observed relationship between one HM1 row and prospective evidence."""

    SAME_KEY_SAME_TEXT = "same_key_same_text"
    SAME_KEY_DIFFERENT_TEXT = "same_key_different_text"
    CHANGED_KEY_SAME_TEXT = "changed_key_same_text"
    NO_DIRECT_CORRESPONDENCE = "no_direct_correspondence"


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceDispositionEntry:
    """One immutable text-free historical disposition."""

    historical_record_id: str
    historical_evidence_key: str

    document_name: str | None
    document_id: str | None
    page: int | None
    chunk_id: str | None

    historical_current_chroma_text_sha256: str | None
    historical_metadata_fingerprint: str | None

    historical_binding_class: BindingClass
    historical_decision_code: str
    historical_blockers: tuple[str, ...]
    historical_recommended_next_action: str

    relationship: HistoricalEvidenceRelationship

    prospective_candidate_key: str | None
    current_successor_evidence_key: str | None
    current_successor_chunk_text_sha256: str | None

    current_text_matches_successor: bool | None
    same_key_as_future_m3: bool | None
    binding_key_collision_risk: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "historical_blockers",
            tuple(self.historical_blockers),
        )


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceDispositionManifest:
    """Complete deterministic disposition of a frozen HM1 inventory."""

    schema_version: str
    case_id: str
    hm1_report_id: str
    pfcr1_report_id: str
    entries: tuple[HistoricalEvidenceDispositionEntry, ...]
    historical_evidence_disposition_manifest_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entries",
            tuple(self.entries),
        )


def _frozen_report_canonical_json_bytes(
    payload: object,
) -> bytes:
    """Return bytes matching frozen HM1/PFCR1 report identity."""
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HistoricalEvidenceDispositionError(
            "Frozen HM1/PFCR1 report payload "
            "is not canonical JSON."
        ) from exc


def _validate_report_identity(
    payload: dict[str, object],
    *,
    id_field: str,
    stored_id: str,
    label: str,
) -> None:
    candidate = dict(payload)
    observed = candidate.pop(id_field, None)

    expected = (
        "sha256:"
        + sha256_bytes(
            _frozen_report_canonical_json_bytes(candidate)
        )
    )

    if observed != stored_id or stored_id != expected:
        raise HistoricalEvidenceDispositionError(
            f"{label} canonical report identity is invalid."
        )


def _validate_inputs(
    hm1_report: HistoricalMigrationReport,
    pfcr1_report: ProspectiveReingestionReport,
) -> str:
    if not isinstance(
        hm1_report,
        HistoricalMigrationReport,
    ):
        raise HistoricalEvidenceDispositionError(
            "hm1_report must be HistoricalMigrationReport."
        )

    if not isinstance(
        pfcr1_report,
        ProspectiveReingestionReport,
    ):
        raise HistoricalEvidenceDispositionError(
            "pfcr1_report must be ProspectiveReingestionReport."
        )

    _validate_report_identity(
        historical_migration_report_to_dict(
            hm1_report
        ),
        id_field="historical_migration_report_id",
        stored_id=(
            hm1_report.historical_migration_report_id
        ),
        label="HM1",
    )

    _validate_report_identity(
        prospective_reingestion_report_to_dict(
            pfcr1_report
        ),
        id_field="prospective_reingestion_report_id",
        stored_id=(
            pfcr1_report.prospective_reingestion_report_id
        ),
        label="PFCR1",
    )

    case_id = canonical_uuid(
        hm1_report.case_id,
        field_name="hm1_report.case_id",
    )

    if (
        canonical_uuid(
            pfcr1_report.case_id,
            field_name="pfcr1_report.case_id",
        )
        != case_id
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1 and PFCR1 belong to different cases."
        )

    if (
        pfcr1_report.hm1_report_id
        != hm1_report.historical_migration_report_id
    ):
        raise HistoricalEvidenceDispositionError(
            "PFCR1 is not bound to the supplied HM1 report."
        )

    if pfcr1_report.historical_provenance_changed:
        raise HistoricalEvidenceDispositionError(
            "PFCR1 must not claim historical provenance changed."
        )

    return case_id


def _relationship(
    mapping: ProspectiveLegacyKeyMapping,
) -> HistoricalEvidenceRelationship:
    if not mapping.actual_prospective_key_exists:
        if (
            mapping.prospective_chunk_text_sha256
            is not None
        ):
            raise HistoricalEvidenceDispositionError(
                "No-direct correspondence must not "
                "carry prospective chunk text SHA."
            )

        if (
            mapping.current_text_matches_prospective_chunk
            is not None
        ):
            raise HistoricalEvidenceDispositionError(
                "No-direct correspondence must not "
                "claim text equality."
            )

        return (
            HistoricalEvidenceRelationship
            .NO_DIRECT_CORRESPONDENCE
        )

    if mapping.prospective_candidate_key is None:
        raise HistoricalEvidenceDispositionError(
            "Direct correspondence requires "
            "prospective_candidate_key."
        )

    if mapping.same_key_as_future_m3 is None:
        raise HistoricalEvidenceDispositionError(
            "Direct correspondence requires "
            "deterministic key relation."
        )

    if mapping.prospective_chunk_text_sha256 is None:
        raise HistoricalEvidenceDispositionError(
            "Direct correspondence requires "
            "prospective chunk text SHA."
        )

    if mapping.same_key_as_future_m3:
        if (
            mapping.current_text_matches_prospective_chunk
            is True
        ):
            return (
                HistoricalEvidenceRelationship
                .SAME_KEY_SAME_TEXT
            )

        if (
            mapping.current_text_matches_prospective_chunk
            is False
        ):
            return (
                HistoricalEvidenceRelationship
                .SAME_KEY_DIFFERENT_TEXT
            )

        raise HistoricalEvidenceDispositionError(
            "Same-key correspondence requires "
            "deterministic text comparison."
        )

    if (
        mapping.current_text_matches_prospective_chunk
        is True
    ):
        return (
            HistoricalEvidenceRelationship
            .CHANGED_KEY_SAME_TEXT
        )

    raise HistoricalEvidenceDispositionError(
        "Changed-key correspondence without exact "
        "text equality is unsupported."
    )


def _build_entry(
    *,
    case_id: str,
    hm1_report_id: str,
    decision: HistoricalMigrationDecision,
    mapping: ProspectiveLegacyKeyMapping,
) -> HistoricalEvidenceDispositionEntry:
    if decision.case_id != case_id:
        raise HistoricalEvidenceDispositionError(
            "HM1 decision belongs to a different case."
        )

    if (
        mapping.historical_evidence_key
        != decision.evidence_key
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 historical evidence keys differ."
        )

    if mapping.document_name != decision.document_name:
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 document names differ."
        )

    if (
        mapping.prospective_candidate_key
        != decision.m3_case_scoped_evidence_key_candidate
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 prospective candidate keys differ."
        )

    if (
        mapping.same_key_as_future_m3
        != decision.same_key_as_future_m3
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 key relation differs."
        )

    if (
        mapping.binding_key_collision_risk
        != decision.binding_key_collision_risk
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 collision state differs."
        )

    if (
        mapping.historical_current_chroma_text_sha256
        != decision.observation.current_chroma_document_sha256
    ):
        raise HistoricalEvidenceDispositionError(
            "HM1/PFCR1 historical text SHA differs."
        )

    if (
        decision.maximum_historical_binding_class
        is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
    ):
        raise HistoricalEvidenceDispositionError(
            "Historical evidence must remain "
            "LEGACY_CURRENT_INDEX_SNAPSHOT."
        )

    if decision.full_chain_projection_eligible:
        raise HistoricalEvidenceDispositionError(
            "HM2.2 must not promote historical "
            "FULL_CHAIN eligibility."
        )

    relationship = _relationship(mapping)

    successor = (
        mapping.prospective_candidate_key
        if mapping.actual_prospective_key_exists
        else None
    )

    if relationship in {
        HistoricalEvidenceRelationship.SAME_KEY_SAME_TEXT,
        HistoricalEvidenceRelationship.SAME_KEY_DIFFERENT_TEXT,
    }:
        if successor != decision.evidence_key:
            raise HistoricalEvidenceDispositionError(
                "Same-key relationship has different keys."
            )

    if (
        relationship
        is HistoricalEvidenceRelationship.CHANGED_KEY_SAME_TEXT
        and successor == decision.evidence_key
    ):
        raise HistoricalEvidenceDispositionError(
            "Changed-key relationship has identical keys."
        )

    historical_record_id = derive_sha256_id(
        {
            "case_id": case_id,
            "hm1_report_id": hm1_report_id,
            "historical_evidence_key": (
                decision.evidence_key
            ),
        }
    )

    return HistoricalEvidenceDispositionEntry(
        historical_record_id=historical_record_id,
        historical_evidence_key=decision.evidence_key,
        document_name=decision.document_name,
        document_id=decision.document_id,
        page=decision.page,
        chunk_id=decision.chunk_id,
        historical_current_chroma_text_sha256=(
            decision.observation
            .current_chroma_document_sha256
        ),
        historical_metadata_fingerprint=(
            decision.observation
            .current_chroma_metadata_fingerprint
        ),
        historical_binding_class=(
            decision.maximum_historical_binding_class
        ),
        historical_decision_code=(
            decision.decision_code.value
        ),
        historical_blockers=decision.blockers,
        historical_recommended_next_action=(
            decision.recommended_next_action
        ),
        relationship=relationship,
        prospective_candidate_key=(
            mapping.prospective_candidate_key
        ),
        current_successor_evidence_key=successor,
        current_successor_chunk_text_sha256=(
            mapping.prospective_chunk_text_sha256
            if mapping.actual_prospective_key_exists
            else None
        ),
        current_text_matches_successor=(
            mapping.current_text_matches_prospective_chunk
        ),
        same_key_as_future_m3=(
            mapping.same_key_as_future_m3
        ),
        binding_key_collision_risk=(
            mapping.binding_key_collision_risk
        ),
    )


def historical_evidence_disposition_entry_to_dict(
    value: HistoricalEvidenceDispositionEntry,
) -> dict[str, object]:
    return {
        "historical_record_id": (
            value.historical_record_id
        ),
        "historical_evidence_key": (
            value.historical_evidence_key
        ),
        "document_name": value.document_name,
        "document_id": value.document_id,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "historical_current_chroma_text_sha256": (
            value.historical_current_chroma_text_sha256
        ),
        "historical_metadata_fingerprint": (
            value.historical_metadata_fingerprint
        ),
        "historical_binding_class": (
            value.historical_binding_class.value
        ),
        "historical_decision_code": (
            value.historical_decision_code
        ),
        "historical_blockers": list(
            value.historical_blockers
        ),
        "historical_recommended_next_action": (
            value.historical_recommended_next_action
        ),
        "relationship": value.relationship.value,
        "prospective_candidate_key": (
            value.prospective_candidate_key
        ),
        "current_successor_evidence_key": (
            value.current_successor_evidence_key
        ),
        "current_successor_chunk_text_sha256": (
            value.current_successor_chunk_text_sha256
        ),
        "current_text_matches_successor": (
            value.current_text_matches_successor
        ),
        "same_key_as_future_m3": (
            value.same_key_as_future_m3
        ),
        "binding_key_collision_risk": (
            value.binding_key_collision_risk
        ),
    }


def historical_evidence_disposition_manifest_to_dict(
    value: HistoricalEvidenceDispositionManifest,
) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "hm1_report_id": value.hm1_report_id,
        "pfcr1_report_id": value.pfcr1_report_id,
        "entries": [
            historical_evidence_disposition_entry_to_dict(
                item
            )
            for item in value.entries
        ],
        "historical_evidence_disposition_manifest_id": (
            value
            .historical_evidence_disposition_manifest_id
        ),
    }


def historical_evidence_disposition_manifest_identity_payload_to_dict(
    value: HistoricalEvidenceDispositionManifest,
) -> dict[str, object]:
    payload = (
        historical_evidence_disposition_manifest_to_dict(
            value
        )
    )

    payload.pop(
        "historical_evidence_disposition_manifest_id"
    )

    return payload


def validate_historical_evidence_disposition_manifest(
    value: HistoricalEvidenceDispositionManifest,
) -> None:
    if (
        value.schema_version
        != HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION
    ):
        raise HistoricalEvidenceDispositionError(
            "Unsupported disposition schema_version."
        )

    case_id = canonical_uuid(
        value.case_id,
        field_name="case_id",
    )

    if case_id != value.case_id:
        raise HistoricalEvidenceDispositionError(
            "case_id must be canonical UUID text."
        )

    keys = [
        item.historical_evidence_key
        for item in value.entries
    ]

    if (
        keys != sorted(keys)
        or len(keys) != len(set(keys))
    ):
        raise HistoricalEvidenceDispositionError(
            "Disposition entries must use unique "
            "sorted historical evidence keys."
        )

    record_ids: set[str] = set()
    successors: set[str] = set()

    for item in value.entries:
        if not isinstance(
            item.relationship,
            HistoricalEvidenceRelationship,
        ):
            raise HistoricalEvidenceDispositionError(
                "relationship must be "
                "HistoricalEvidenceRelationship."
            )

        if (
            item.historical_binding_class
            is not BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        ):
            raise HistoricalEvidenceDispositionError(
                "Historical disposition cannot promote "
                "historical binding class."
            )

        expected_record_id = derive_sha256_id(
            {
                "case_id": value.case_id,
                "hm1_report_id": value.hm1_report_id,
                "historical_evidence_key": (
                    item.historical_evidence_key
                ),
            }
        )

        if (
            item.historical_record_id
            != expected_record_id
        ):
            raise HistoricalEvidenceDispositionError(
                "historical_record_id is not canonical."
            )

        if item.historical_record_id in record_ids:
            raise HistoricalEvidenceDispositionError(
                "Historical record IDs must be unique."
            )

        record_ids.add(
            item.historical_record_id
        )

        successor = (
            item.current_successor_evidence_key
        )

        if successor is not None:
            if successor in successors:
                raise HistoricalEvidenceDispositionError(
                    "Current successor evidence keys "
                    "must be unique."
                )

            successors.add(successor)

        if (
            item.relationship
            is HistoricalEvidenceRelationship
            .NO_DIRECT_CORRESPONDENCE
        ):
            if (
                successor is not None
                or (
                    item
                    .current_successor_chunk_text_sha256
                    is not None
                )
            ):
                raise HistoricalEvidenceDispositionError(
                    "No-direct disposition must not "
                    "carry current successor state."
                )

            if (
                item.current_text_matches_successor
                is not None
            ):
                raise HistoricalEvidenceDispositionError(
                    "No-direct disposition must not "
                    "claim text equality."
                )

            continue

        if (
            successor is None
            or (
                item.current_successor_chunk_text_sha256
                is None
            )
        ):
            raise HistoricalEvidenceDispositionError(
                "Direct disposition requires current "
                "successor state."
            )

        if (
            item.relationship
            is HistoricalEvidenceRelationship
            .SAME_KEY_SAME_TEXT
        ):
            if (
                successor
                != item.historical_evidence_key
                or (
                    item.current_text_matches_successor
                    is not True
                )
            ):
                raise HistoricalEvidenceDispositionError(
                    "SAME_KEY_SAME_TEXT invariant failed."
                )

        elif (
            item.relationship
            is HistoricalEvidenceRelationship
            .SAME_KEY_DIFFERENT_TEXT
        ):
            if (
                successor
                != item.historical_evidence_key
                or (
                    item.current_text_matches_successor
                    is not False
                )
            ):
                raise HistoricalEvidenceDispositionError(
                    "SAME_KEY_DIFFERENT_TEXT "
                    "invariant failed."
                )

        elif (
            item.relationship
            is HistoricalEvidenceRelationship
            .CHANGED_KEY_SAME_TEXT
        ):
            if (
                successor
                == item.historical_evidence_key
                or (
                    item.current_text_matches_successor
                    is not True
                )
            ):
                raise HistoricalEvidenceDispositionError(
                    "CHANGED_KEY_SAME_TEXT "
                    "invariant failed."
                )

    expected_manifest_id = derive_sha256_id(
        historical_evidence_disposition_manifest_identity_payload_to_dict(
            value
        )
    )

    if (
        value.historical_evidence_disposition_manifest_id
        != expected_manifest_id
    ):
        raise HistoricalEvidenceDispositionError(
            "Disposition manifest identity "
            "is not canonical."
        )


def build_historical_evidence_disposition_manifest(
    *,
    hm1_report: HistoricalMigrationReport,
    pfcr1_report: ProspectiveReingestionReport,
) -> HistoricalEvidenceDispositionManifest:
    """Build deterministic text-free disposition from HM1 and PFCR1."""

    case_id = _validate_inputs(
        hm1_report,
        pfcr1_report,
    )

    decisions: dict[
        str,
        HistoricalMigrationDecision,
    ] = {}

    for item in hm1_report.decisions:
        if item.evidence_key in decisions:
            raise HistoricalEvidenceDispositionError(
                "HM1 historical keys must be unique."
            )

        decisions[item.evidence_key] = item

    mappings: dict[
        str,
        ProspectiveLegacyKeyMapping,
    ] = {}

    for item in pfcr1_report.legacy_mappings:
        if item.historical_evidence_key in mappings:
            raise HistoricalEvidenceDispositionError(
                "PFCR1 historical mapping keys "
                "must be unique."
            )

        mappings[
            item.historical_evidence_key
        ] = item

    if set(decisions) != set(mappings):
        raise HistoricalEvidenceDispositionError(
            "HM1 decisions and PFCR1 legacy mappings "
            "must reconcile exactly."
        )

    entries = tuple(
        _build_entry(
            case_id=case_id,
            hm1_report_id=(
                hm1_report
                .historical_migration_report_id
            ),
            decision=decisions[key],
            mapping=mappings[key],
        )
        for key in sorted(decisions)
    )

    provisional = (
        HistoricalEvidenceDispositionManifest(
            schema_version=(
                HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION
            ),
            case_id=case_id,
            hm1_report_id=(
                hm1_report
                .historical_migration_report_id
            ),
            pfcr1_report_id=(
                pfcr1_report
                .prospective_reingestion_report_id
            ),
            entries=entries,
            historical_evidence_disposition_manifest_id=(
                "sha256:" + ("0" * 64)
            ),
        )
    )

    manifest = replace(
        provisional,
        historical_evidence_disposition_manifest_id=(
            derive_sha256_id(
                historical_evidence_disposition_manifest_identity_payload_to_dict(
                    provisional
                )
            )
        ),
    )

    validate_historical_evidence_disposition_manifest(
        manifest
    )

    return manifest


def dumps_historical_evidence_disposition_manifest(
    value: HistoricalEvidenceDispositionManifest,
) -> str:
    """Return canonical JSON without publishing it."""

    validate_historical_evidence_disposition_manifest(
        value
    )

    return canonical_json_bytes(
        historical_evidence_disposition_manifest_to_dict(
            value
        )
    ).decode("utf-8")


__all__ = [
    "HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION",
    "HistoricalEvidenceDispositionEntry",
    "HistoricalEvidenceDispositionError",
    "HistoricalEvidenceDispositionManifest",
    "HistoricalEvidenceRelationship",
    "build_historical_evidence_disposition_manifest",
    "dumps_historical_evidence_disposition_manifest",
    "historical_evidence_disposition_entry_to_dict",
    "historical_evidence_disposition_manifest_identity_payload_to_dict",
    "historical_evidence_disposition_manifest_to_dict",
    "validate_historical_evidence_disposition_manifest",
]
