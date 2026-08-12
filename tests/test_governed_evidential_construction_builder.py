"""Synthetic contract tests for deterministic U9B-to-U9C-B1 construction."""

from __future__ import annotations

import copy

from governed_evidence_analysis import (
    GovernedEvidenceObservationType,
    derive_governed_evidential_analysis_id,
    dumps_governed_evidential_analysis,
    loads_governed_evidential_analysis,
    source_u9b_sha256,
    validate_governed_evidential_analysis,
)
from governed_evidential_construction import build_governed_evidential_analysis
from governed_issue_evidence import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedSearchCoverage,
)


CASE_ID = "12345678-1234-4234-8234-123456789abc"


def _evidence(key: str, *, role: str, document: str) -> GovernedEvidenceRef:
    digest = "a" * 64 if key.endswith("a") else "b" * 64
    return GovernedEvidenceRef(
        evidence_key=key,
        source_document_instance_id=f"source-{key}",
        source_snapshot_id=f"snapshot-{key}",
        original_filename=f"{document}.pdf",
        original_blob_sha256="sha256:" + digest,
        extraction_profile_id="pdf-page-extraction/1.0",
        chunking_profile_id="recursive-character-text-splitter/1.0",
        page_number=1,
        page_text_sha256="sha256:" + digest,
        extraction_method="pypdf_text",
        chunk_ordinal=0,
        chunk_id=key,
        evidence_binding_id=f"binding-{key}",
        binding_class="full_chain_bound",
        bound_text_role="chunk_text",
        chunk_text_sha256="sha256:" + digest,
        chunk_text_byte_length=10,
        citation=f"{document}.pdf, p.1",
        evidence_role=role,
        role_rule_id="role-rule/1.0",
        role_basis="synthetic fixture",
        source_type="synthetic",
        source_label="Synthetic",
        provenance_method="synthetic",
        primary_tier=1 if role == "primary_source" else 0,
        primary_label="Primary" if role == "primary_source" else "Other",
    )


def _use(
    *,
    issue_analysis_id: str,
    issue_definition_id: str,
    element_id: str,
    element_ordinal: int,
    evidence_key: str,
    role: str,
) -> GovernedEvidenceUse:
    return GovernedEvidenceUse(
        issue_analysis_id=issue_analysis_id,
        issue_definition_id=issue_definition_id,
        issue_definition_version="1.0",
        element_id=element_id,
        element_ordinal=element_ordinal,
        evidence_key=evidence_key,
        analytical_role=role,
        mapping_relevance="relevant",
        mapping_confidence="high",
        mapping_rationale="synthetic mapping",
        assessment_confidence="medium",
        assessment_rationale="synthetic assessment",
        citation=f"{evidence_key}.pdf, p.1",
        proposition_links=(),
    )


def _source_u9b() -> GovernedIssueEvidenceMap:
    evidence_a = _evidence("evidence-a", role="primary_source", document="alpha")
    evidence_b = _evidence("evidence-b", role="primary_source", document="beta")
    evidence_c = _evidence("evidence-c", role="other", document="gamma")
    evidence_d = _evidence("evidence-d", role="other", document="delta")

    bindings = (
        GovernedEvidenceUseBinding(
            evidence=evidence_a,
            use=_use(
                issue_analysis_id="analysis-a",
                issue_definition_id="A-001",
                element_id="A-ELEMENT-1",
                element_ordinal=0,
                evidence_key="evidence-a",
                role="supporting",
            ),
        ),
        GovernedEvidenceUseBinding(
            evidence=evidence_a,
            use=_use(
                issue_analysis_id="analysis-a",
                issue_definition_id="A-001",
                element_id="A-ELEMENT-2",
                element_ordinal=1,
                evidence_key="evidence-a",
                role="adverse",
            ),
        ),
        GovernedEvidenceUseBinding(
            evidence=evidence_c,
            use=_use(
                issue_analysis_id="analysis-b",
                issue_definition_id="B-001",
                element_id="B-ELEMENT-1",
                element_ordinal=0,
                evidence_key="evidence-c",
                role="conflicting",
            ),
        ),
    )
    coverage = GovernedSearchCoverage(
        schema_version="evidence-search-receipt/1.0",
        search_mode="exhaustive_evidence",
        text_match_mode="all_evidence",
        query_sha256="sha256:" + "0" * 64,
        case_document_count=2,
        case_page_count=4,
        case_chunk_count=4,
        scope_document_count=2,
        scope_page_count=4,
        scope_chunk_count=4,
        documents_completely_expanded=2,
        pages_inspected=4,
        chunks_inspected=4,
        candidate_document_ids=(),
        searched_document_ids=("doc-1", "doc-2"),
        filters_applied=("text_match=all_evidence",),
        matched_evidence_keys=("evidence-a", "evidence-b", "evidence-c", "evidence-d"),
        completion="complete",
        case_corpus_complete=True,
        negative_finding_scope="case_corpus",
        negative_finding_permitted=True,
    )
    return GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id=CASE_ID,
        source_synthesis_id="synthesis-1",
        source_matrices_schema_version="case-matrices-schema/1.0",
        source_matrix_builder_version="case-matrix-builder/1.0",
        source_analysis_ids=("analysis-a", "analysis-b"),
        coverage=coverage,
        bindings=bindings,
        unmapped_evidence=(evidence_b, evidence_d),
    )


def _types(result, key: str) -> tuple[GovernedEvidenceObservationType, ...]:
    assessment = next(item for item in result.evidence_assessments if item.evidence_key == key)
    return tuple(item.observation_type for item in assessment.observations)


def test_builder_constructs_exact_frozen_u9c_b1_observations() -> None:
    source = _source_u9b()
    result = build_governed_evidential_analysis(source)

    assert tuple(item.evidence_key for item in result.evidence_assessments) == (
        "evidence-a",
        "evidence-b",
        "evidence-c",
        "evidence-d",
    )

    types_a = set(_types(result, "evidence-a"))
    assert types_a == {
        GovernedEvidenceObservationType.ANALYTICALLY_BOUND,
        GovernedEvidenceObservationType.PRIMARY_SOURCE_BOUND,
        GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT,
    }
    types_b = set(_types(result, "evidence-b"))
    assert types_b == {
        GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED,
        GovernedEvidenceObservationType.PRIMARY_SOURCE_UNMAPPED,
    }
    types_c = set(_types(result, "evidence-c"))
    assert types_c == {
        GovernedEvidenceObservationType.ANALYTICALLY_BOUND,
        GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT,
    }
    assert _types(result, "evidence-d") == (
        GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED,
    )

    assessment_a = result.evidence_assessments[0]
    adverse = next(
        item
        for item in assessment_a.observations
        if item.observation_type == GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT
    )
    assert adverse.use_coordinate is not None
    assert adverse.use_coordinate.issue_analysis_id == "analysis-a"
    assert adverse.use_coordinate.element_id == "A-ELEMENT-2"
    assert adverse.use_coordinate.evidence_key == "evidence-a"


def test_builder_binds_frozen_public_fingerprint_identity_validation_and_serialization() -> None:
    source = _source_u9b()
    result = build_governed_evidential_analysis(source)

    assert result.source_u9b_sha256 == source_u9b_sha256(source)
    assert result.analysis_id == derive_governed_evidential_analysis_id(
        schema_version=result.schema_version,
        identity_version=result.identity_version,
        case_id=result.case_id,
        source_u9b_sha256_value=result.source_u9b_sha256,
    )
    validate_governed_evidential_analysis(result, source)

    payload = dumps_governed_evidential_analysis(result, source)
    restored = loads_governed_evidential_analysis(payload, source)
    assert restored == result
    assert dumps_governed_evidential_analysis(restored, source) == payload


def test_builder_is_repeatable_and_does_not_mutate_frozen_u9b() -> None:
    source = _source_u9b()
    before = copy.deepcopy(source)

    first = build_governed_evidential_analysis(source)
    second = build_governed_evidential_analysis(source)

    assert source == before
    assert first == second
    assert dumps_governed_evidential_analysis(first, source) == dumps_governed_evidential_analysis(
        second,
        source,
    )


def test_supporting_role_creates_no_new_use_level_observation() -> None:
    source = _source_u9b()
    result = build_governed_evidential_analysis(source)
    assessment = result.evidence_assessments[0]

    role_observations = [
        item
        for item in assessment.observations
        if item.use_coordinate is not None
    ]
    assert len(role_observations) == 1
    assert role_observations[0].observation_type == GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT
    assert role_observations[0].use_coordinate is not None
    assert role_observations[0].use_coordinate.element_id == "A-ELEMENT-2"
