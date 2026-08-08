from __future__ import annotations

import ast
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from source_evidence.historical_disposition import (
    HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION,
    HistoricalEvidenceDispositionError,
    HistoricalEvidenceRelationship,
    build_historical_evidence_disposition_manifest,
    dumps_historical_evidence_disposition_manifest,
    historical_evidence_disposition_manifest_identity_payload_to_dict,
    validate_historical_evidence_disposition_manifest,
)
from source_evidence.identity import (
    canonical_json_bytes,
    derive_sha256_id,
    sha256_bytes,
)
from source_evidence.migration import (
    HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
    HistoricalMigrationDecision,
    HistoricalMigrationDecisionCode,
    HistoricalMigrationReport,
    HistoricalMigrationSourceObservation,
    historical_migration_report_to_dict,
)
from source_evidence.models import BindingClass
from source_evidence.reingestion_transition import (
    PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION,
    ProspectiveLegacyKeyMapping,
    ProspectiveReingestionReport,
    prospective_reingestion_report_to_dict,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"

ZERO_ID = "sha256:" + ("0" * 64)


def _frozen_report_canonical_json_bytes(
    payload: object,
) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(text: str) -> str:
    return sha256_bytes(
        text.encode("utf-8")
    )


def _decision(
    *,
    historical_key: str,
    candidate_key: str,
    historical_text_sha: str,
    collision: bool,
    document_name: str = "evidence.pdf",
) -> HistoricalMigrationDecision:
    return HistoricalMigrationDecision(
        case_id=CASE_ID,
        evidence_key=historical_key,
        document_name=document_name,
        document_id=None,
        page=1,
        chunk_id=historical_key,
        referencing_report_projection_ids=(),
        existing_evidence_binding_id=None,
        existing_binding_class=None,
        existing_projection_binding_manifest_ids=(),
        existing_projection_entry_classes=(),
        observation=HistoricalMigrationSourceObservation(
            current_chroma_row_count=1,
            current_chroma_document_sha256=(
                historical_text_sha
            ),
            current_chroma_metadata_fingerprint=(
                _sha(f"metadata:{historical_key}")
            ),
            current_pdf_candidate_count=1,
            current_pdf_sha256=_sha(
                f"pdf:{document_name}"
            ),
            current_pdf_byte_length=100,
            retained_historical_text_sha256=None,
        ),
        m3_case_scoped_evidence_key_candidate=(
            candidate_key
        ),
        same_key_as_future_m3=(
            historical_key == candidate_key
        ),
        binding_key_collision_risk=collision,
        maximum_historical_binding_class=(
            BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        ),
        full_chain_projection_eligible=False,
        forward_reingestible=True,
        decision_code=(
            HistoricalMigrationDecisionCode
            .BINDING_KEY_COLLISION_RISK
            if collision
            else HistoricalMigrationDecisionCode
            .LEGACY_KEY_DIFFERS_FROM_M3_KEY
        ),
        blockers=(
            (
                HistoricalMigrationDecisionCode
                .BINDING_KEY_COLLISION_RISK
                .value,
                HistoricalMigrationDecisionCode
                .HISTORICAL_ORIGINAL_IDENTITY_MISSING
                .value,
            )
            if collision
            else (
                HistoricalMigrationDecisionCode
                .HISTORICAL_ORIGINAL_IDENTITY_MISSING
                .value,
            )
        ),
        recommended_next_action=(
            "defer_binding_publication"
            if collision
            else (
                "preserve_historical_key_"
                "consider_forward_reingestion"
            )
        ),
    )


def _mapping(
    *,
    historical_key: str,
    candidate_key: str,
    historical_text_sha: str,
    prospective_text_sha: str | None,
    actual_exists: bool,
    collision: bool,
    document_name: str = "evidence.pdf",
) -> ProspectiveLegacyKeyMapping:
    match = (
        historical_text_sha
        == prospective_text_sha
        if (
            historical_text_sha is not None
            and prospective_text_sha is not None
        )
        else None
    )

    return ProspectiveLegacyKeyMapping(
        historical_evidence_key=historical_key,
        document_name=document_name,
        prospective_candidate_key=candidate_key,
        actual_prospective_key_exists=actual_exists,
        same_key_as_future_m3=(
            historical_key == candidate_key
        ),
        binding_key_collision_risk=collision,
        historical_current_chroma_text_sha256=(
            historical_text_sha
        ),
        prospective_chunk_text_sha256=(
            prospective_text_sha
        ),
        current_text_matches_prospective_chunk=(
            match
        ),
    )


def _hm1_report(
    decisions: tuple[
        HistoricalMigrationDecision,
        ...,
    ],
) -> HistoricalMigrationReport:
    provisional = HistoricalMigrationReport(
        schema_version=(
            HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION
        ),
        case_id=CASE_ID,
        projection_ids=(),
        decisions=tuple(decisions),
        historical_migration_report_id=ZERO_ID,
    )

    payload = historical_migration_report_to_dict(
        provisional
    )

    payload.pop(
        "historical_migration_report_id"
    )

    return replace(
        provisional,
        historical_migration_report_id=(
            "sha256:"
            + sha256_bytes(
                _frozen_report_canonical_json_bytes(payload)
            )
        ),
    )


def _pfcr1_report(
    *,
    hm1: HistoricalMigrationReport,
    mappings: tuple[
        ProspectiveLegacyKeyMapping,
        ...,
    ],
) -> ProspectiveReingestionReport:
    same = sum(
        1
        for item in mappings
        if (
            item.actual_prospective_key_exists
            and item.same_key_as_future_m3
        )
    )

    changed = sum(
        1
        for item in mappings
        if (
            item.actual_prospective_key_exists
            and item.same_key_as_future_m3 is False
        )
    )

    no_direct = sum(
        1
        for item in mappings
        if not item.actual_prospective_key_exists
    )

    prospective_count = same + changed

    provisional = ProspectiveReingestionReport(
        schema_version=(
            PROSPECTIVE_REINGESTION_REPORT_SCHEMA_VERSION
        ),
        case_id=CASE_ID,
        hm1_report_id=(
            hm1.historical_migration_report_id
        ),
        historical_provenance_changed=False,
        prospective_source_chain_created=True,
        active_derived_index_changed=False,
        legacy_active_row_count=len(mappings),
        legacy_target_row_count=len(mappings),
        legacy_collision_risk_count=sum(
            1
            for item in mappings
            if item.binding_key_collision_risk
        ),
        legacy_key_different_count=changed,
        current_document_count=0,
        documents_capture_ready=0,
        documents_blocked=0,
        prospective_manifest_count=0,
        prospective_row_count=prospective_count,
        exact_shadow_row_count=prospective_count,
        missing_shadow_row_count=0,
        conflicting_shadow_row_count=0,
        unexpected_shadow_row_count=0,
        legacy_shadow_row_count=0,
        same_key_correspondence_count=same,
        changed_key_correspondence_count=changed,
        no_direct_correspondence_count=no_direct,
        all_rows_source_bound=True,
        all_documents_complete=True,
        all_active_collection_populations_accounted=True,
        collection_complete_for_cutover=True,
        unaccounted_active_row_ids=(),
        documents=(),
        legacy_mappings=tuple(mappings),
        blockers=(),
        prospective_reingestion_report_id=ZERO_ID,
    )

    payload = (
        prospective_reingestion_report_to_dict(
            provisional
        )
    )

    payload.pop(
        "prospective_reingestion_report_id"
    )

    return replace(
        provisional,
        prospective_reingestion_report_id=(
            "sha256:"
            + sha256_bytes(
                _frozen_report_canonical_json_bytes(payload)
            )
        ),
    )


def _build(
    decisions: tuple[
        HistoricalMigrationDecision,
        ...,
    ],
    mappings: tuple[
        ProspectiveLegacyKeyMapping,
        ...,
    ],
):
    hm1 = _hm1_report(decisions)

    pfcr1 = _pfcr1_report(
        hm1=hm1,
        mappings=mappings,
    )

    manifest = (
        build_historical_evidence_disposition_manifest(
            hm1_report=hm1,
            pfcr1_report=pfcr1,
        )
    )

    return hm1, pfcr1, manifest


def test_all_four_relationship_classes_preserve_historical_provenance() -> None:
    same_same_sha = _sha("same-same")
    same_diff_historical_sha = _sha(
        "historical"
    )
    same_diff_current_sha = _sha(
        "current"
    )
    changed_sha = _sha("changed")

    decisions = (
        _decision(
            historical_key="a-same-same",
            candidate_key="a-same-same",
            historical_text_sha=same_same_sha,
            collision=True,
        ),
        _decision(
            historical_key="b-same-different",
            candidate_key="b-same-different",
            historical_text_sha=(
                same_diff_historical_sha
            ),
            collision=True,
        ),
        _decision(
            historical_key="c-old-key",
            candidate_key="c-new-key",
            historical_text_sha=changed_sha,
            collision=False,
        ),
        _decision(
            historical_key="d-historical-only",
            candidate_key="d-historical-only",
            historical_text_sha=_sha(
                "historical-only"
            ),
            collision=True,
        ),
    )

    mappings = (
        _mapping(
            historical_key="a-same-same",
            candidate_key="a-same-same",
            historical_text_sha=same_same_sha,
            prospective_text_sha=same_same_sha,
            actual_exists=True,
            collision=True,
        ),
        _mapping(
            historical_key="b-same-different",
            candidate_key="b-same-different",
            historical_text_sha=(
                same_diff_historical_sha
            ),
            prospective_text_sha=(
                same_diff_current_sha
            ),
            actual_exists=True,
            collision=True,
        ),
        _mapping(
            historical_key="c-old-key",
            candidate_key="c-new-key",
            historical_text_sha=changed_sha,
            prospective_text_sha=changed_sha,
            actual_exists=True,
            collision=False,
        ),
        _mapping(
            historical_key="d-historical-only",
            candidate_key="d-historical-only",
            historical_text_sha=_sha(
                "historical-only"
            ),
            prospective_text_sha=None,
            actual_exists=False,
            collision=True,
        ),
    )

    _, _, manifest = _build(
        decisions,
        mappings,
    )

    assert (
        manifest.schema_version
        == HISTORICAL_EVIDENCE_DISPOSITION_SCHEMA_VERSION
    )

    assert [
        item.relationship
        for item in manifest.entries
    ] == [
        HistoricalEvidenceRelationship
        .SAME_KEY_SAME_TEXT,
        HistoricalEvidenceRelationship
        .SAME_KEY_DIFFERENT_TEXT,
        HistoricalEvidenceRelationship
        .CHANGED_KEY_SAME_TEXT,
        HistoricalEvidenceRelationship
        .NO_DIRECT_CORRESPONDENCE,
    ]

    assert all(
        item.historical_binding_class
        is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        for item in manifest.entries
    )

    assert (
        manifest.entries[0]
        .current_successor_evidence_key
        == "a-same-same"
    )

    assert (
        manifest.entries[1]
        .current_successor_evidence_key
        == "b-same-different"
    )

    assert (
        manifest.entries[2]
        .current_successor_evidence_key
        == "c-new-key"
    )

    assert (
        manifest.entries[3]
        .current_successor_evidence_key
        is None
    )


def test_manifest_is_deterministic_and_canonically_identified() -> None:
    text_sha = _sha("exact")

    decisions = (
        _decision(
            historical_key="key-1",
            candidate_key="key-1",
            historical_text_sha=text_sha,
            collision=True,
        ),
    )

    mappings = (
        _mapping(
            historical_key="key-1",
            candidate_key="key-1",
            historical_text_sha=text_sha,
            prospective_text_sha=text_sha,
            actual_exists=True,
            collision=True,
        ),
    )

    _, _, first = _build(
        decisions,
        mappings,
    )

    _, _, second = _build(
        decisions,
        mappings,
    )

    assert first == second

    assert (
        first.historical_evidence_disposition_manifest_id
        == derive_sha256_id(
            historical_evidence_disposition_manifest_identity_payload_to_dict(
                first
            )
        )
    )

    assert (
        dumps_historical_evidence_disposition_manifest(
            first
        )
        == dumps_historical_evidence_disposition_manifest(
            second
        )
    )


def test_governed_745_row_shape_is_exact() -> None:
    decisions: list[
        HistoricalMigrationDecision
    ] = []

    mappings: list[
        ProspectiveLegacyKeyMapping
    ] = []

    # 304 same-key / same-text.
    for index in range(304):
        key = f"same-same-{index:03d}"
        sha = _sha(f"text:{key}")

        decisions.append(
            _decision(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=sha,
                collision=True,
            )
        )

        mappings.append(
            _mapping(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=sha,
                prospective_text_sha=sha,
                actual_exists=True,
                collision=True,
            )
        )

    # 59 same-key / different-text.
    for index in range(59):
        key = f"same-different-{index:03d}"

        historical_sha = _sha(
            f"historical:{key}"
        )

        current_sha = _sha(
            f"current:{key}"
        )

        decisions.append(
            _decision(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=historical_sha,
                collision=True,
            )
        )

        mappings.append(
            _mapping(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=historical_sha,
                prospective_text_sha=current_sha,
                actual_exists=True,
                collision=True,
            )
        )

    # 30 changed-key / same-text.
    for index in range(30):
        old_key = f"changed-old-{index:03d}"
        new_key = f"changed-new-{index:03d}"
        sha = _sha(f"text:{old_key}")

        decisions.append(
            _decision(
                historical_key=old_key,
                candidate_key=new_key,
                historical_text_sha=sha,
                collision=False,
            )
        )

        mappings.append(
            _mapping(
                historical_key=old_key,
                candidate_key=new_key,
                historical_text_sha=sha,
                prospective_text_sha=sha,
                actual_exists=True,
                collision=False,
            )
        )

    # 352 historical-only / no direct row.
    for index in range(352):
        key = f"historical-only-{index:03d}"
        sha = _sha(f"text:{key}")

        decisions.append(
            _decision(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=sha,
                collision=True,
            )
        )

        mappings.append(
            _mapping(
                historical_key=key,
                candidate_key=key,
                historical_text_sha=sha,
                prospective_text_sha=None,
                actual_exists=False,
                collision=True,
            )
        )

    _, _, manifest = _build(
        tuple(decisions),
        tuple(mappings),
    )

    counts = Counter(
        item.relationship
        for item in manifest.entries
    )

    assert len(manifest.entries) == 745

    assert counts == {
        HistoricalEvidenceRelationship
        .SAME_KEY_SAME_TEXT: 304,
        HistoricalEvidenceRelationship
        .SAME_KEY_DIFFERENT_TEXT: 59,
        HistoricalEvidenceRelationship
        .CHANGED_KEY_SAME_TEXT: 30,
        HistoricalEvidenceRelationship
        .NO_DIRECT_CORRESPONDENCE: 352,
    }

    successors = [
        item.current_successor_evidence_key
        for item in manifest.entries
        if (
            item.current_successor_evidence_key
            is not None
        )
    ]

    assert len(successors) == 393
    assert len(set(successors)) == 393

    assert sum(
        item.binding_key_collision_risk
        for item in manifest.entries
    ) == 715

    assert all(
        item.historical_binding_class
        is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        for item in manifest.entries
    )


def test_hm1_pfcr1_text_sha_disagreement_fails_closed() -> None:
    historical_sha = _sha("historical")

    decision = _decision(
        historical_key="key-1",
        candidate_key="key-1",
        historical_text_sha=historical_sha,
        collision=True,
    )

    mapping = _mapping(
        historical_key="key-1",
        candidate_key="key-1",
        historical_text_sha=_sha(
            "different-historical-hash"
        ),
        prospective_text_sha=historical_sha,
        actual_exists=True,
        collision=True,
    )

    hm1 = _hm1_report((decision,))

    pfcr1 = _pfcr1_report(
        hm1=hm1,
        mappings=(mapping,),
    )

    with pytest.raises(
        HistoricalEvidenceDispositionError,
        match="historical text SHA differs",
    ):
        build_historical_evidence_disposition_manifest(
            hm1_report=hm1,
            pfcr1_report=pfcr1,
        )


def test_historical_full_chain_promotion_fails_closed() -> None:
    sha = _sha("text")

    decision = replace(
        _decision(
            historical_key="key-1",
            candidate_key="key-1",
            historical_text_sha=sha,
            collision=True,
        ),
        maximum_historical_binding_class=(
            BindingClass.FULL_CHAIN_BOUND
        ),
        full_chain_projection_eligible=True,
    )

    mapping = _mapping(
        historical_key="key-1",
        candidate_key="key-1",
        historical_text_sha=sha,
        prospective_text_sha=sha,
        actual_exists=True,
        collision=True,
    )

    hm1 = _hm1_report((decision,))

    pfcr1 = _pfcr1_report(
        hm1=hm1,
        mappings=(mapping,),
    )

    with pytest.raises(
        HistoricalEvidenceDispositionError,
        match="Historical evidence must remain",
    ):
        build_historical_evidence_disposition_manifest(
            hm1_report=hm1,
            pfcr1_report=pfcr1,
        )


def test_duplicate_current_successor_fails_validation() -> None:
    sha_a = _sha("a")
    sha_b = _sha("b")

    decisions = (
        _decision(
            historical_key="old-a",
            candidate_key="new-key",
            historical_text_sha=sha_a,
            collision=False,
        ),
        _decision(
            historical_key="old-b",
            candidate_key="new-key",
            historical_text_sha=sha_b,
            collision=False,
        ),
    )

    mappings = (
        _mapping(
            historical_key="old-a",
            candidate_key="new-key",
            historical_text_sha=sha_a,
            prospective_text_sha=sha_a,
            actual_exists=True,
            collision=False,
        ),
        _mapping(
            historical_key="old-b",
            candidate_key="new-key",
            historical_text_sha=sha_b,
            prospective_text_sha=sha_b,
            actual_exists=True,
            collision=False,
        ),
    )

    hm1 = _hm1_report(decisions)

    pfcr1 = _pfcr1_report(
        hm1=hm1,
        mappings=mappings,
    )

    with pytest.raises(
        HistoricalEvidenceDispositionError,
        match="successor evidence keys must be unique",
    ):
        build_historical_evidence_disposition_manifest(
            hm1_report=hm1,
            pfcr1_report=pfcr1,
        )


def test_tampered_manifest_id_fails_validation() -> None:
    sha = _sha("text")

    _, _, manifest = _build(
        (
            _decision(
                historical_key="key-1",
                candidate_key="key-1",
                historical_text_sha=sha,
                collision=True,
            ),
        ),
        (
            _mapping(
                historical_key="key-1",
                candidate_key="key-1",
                historical_text_sha=sha,
                prospective_text_sha=sha,
                actual_exists=True,
                collision=True,
            ),
        ),
    )

    with pytest.raises(
        HistoricalEvidenceDispositionError,
        match="manifest identity",
    ):
        validate_historical_evidence_disposition_manifest(
            replace(
                manifest,
                historical_evidence_disposition_manifest_id=ZERO_ID,
            )
        )



def test_frozen_upstream_report_identity_accepts_non_ascii_payload() -> None:
    payload = {
        "value": "\u00e9vidence\u2013report",
    }

    frozen_bytes = (
        _frozen_report_canonical_json_bytes(
            payload
        )
    )

    assert frozen_bytes != canonical_json_bytes(
        payload
    )

    text_sha = _sha("unicode-report-text")
    document_name = "\u00e9vidence\u2013report.pdf"

    decision = _decision(
        historical_key="unicode-key",
        candidate_key="unicode-key",
        historical_text_sha=text_sha,
        collision=True,
        document_name=document_name,
    )

    mapping = _mapping(
        historical_key="unicode-key",
        candidate_key="unicode-key",
        historical_text_sha=text_sha,
        prospective_text_sha=text_sha,
        actual_exists=True,
        collision=True,
        document_name=document_name,
    )

    _, _, manifest = _build(
        (decision,),
        (mapping,),
    )

    assert len(manifest.entries) == 1

    assert (
        manifest.entries[0].document_name
        == document_name
    )

def test_hm2_2_module_has_no_chroma_store_or_publication_dependency() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "source_evidence"
        / "historical_disposition.py"
    )

    source = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
        ):
            imports.add(node.module)

    forbidden_import_components = {
        "chromadb",
        "store",
        "ingestion",
        "capture",
        "resolver",
        "production_cutover",
        "production_shadow_build",
    }

    assert not any(
        forbidden_import_components.intersection(
            imported.split(".")
        )
        for imported in imports
    )

    forbidden_source_terms = (
        "SourceEvidenceStore",
        "PersistentClient",
        "publish_evidence_binding",
        "publish_document_manifest",
        "publish_analysis_receipt",
        "publish_projection_binding",
    )

    assert not any(
        term in source
        for term in forbidden_source_terms
    )
