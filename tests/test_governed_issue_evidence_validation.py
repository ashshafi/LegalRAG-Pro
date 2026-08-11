from dataclasses import replace

import pytest

from governed_issue_evidence.models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedPropositionLink,
    GovernedSearchCoverage,
)
from governed_issue_evidence.validation import (
    GovernedIssueEvidenceValidationError,
    validate_governed_issue_evidence_map,
)


def _coverage() -> GovernedSearchCoverage:
    return GovernedSearchCoverage(
        schema_version="1.0",
        search_mode="exhaustive_evidence",
        text_match_mode="all_evidence",
        query_sha256="sha256:" + "0" * 64,
        case_document_count=1,
        case_page_count=1,
        case_chunk_count=1,
        scope_document_count=1,
        scope_page_count=1,
        scope_chunk_count=1,
        documents_completely_expanded=1,
        pages_inspected=1,
        chunks_inspected=1,
        candidate_document_ids=(),
        searched_document_ids=("doc-1",),
        filters_applied=("text_match=all_evidence",),
        matched_evidence_keys=("evidence-1",),
        completion="complete",
        case_corpus_complete=True,
        negative_finding_scope="case_corpus",
        negative_finding_permitted=True,
    )


def _evidence(key: str = "evidence-1") -> GovernedEvidenceRef:
    return GovernedEvidenceRef(
        evidence_key=key,
        source_document_instance_id="doc-1",
        source_snapshot_id="snapshot-1",
        original_filename="Employer letter.pdf",
        original_blob_sha256="sha256:" + "1" * 64,
        extraction_profile_id="extract-v1",
        chunking_profile_id="chunk-v1",
        page_number=1,
        page_text_sha256="sha256:" + "2" * 64,
        extraction_method="pypdf_text",
        chunk_ordinal=0,
        chunk_id=key,
        evidence_binding_id="binding-1",
        binding_class="full_chain_bound",
        bound_text_role="chunk_text",
        chunk_text_sha256="sha256:" + "3" * 64,
        chunk_text_byte_length=10,
        citation="Employer letter.pdf, p.1",
        evidence_role="primary_source",
        role_rule_id="primary.direct_source_type",
        role_basis="Frozen U8 rule.",
        source_type="employer_record",
        source_label="Employer record",
        provenance_method="filename",
        primary_tier=1,
        primary_label="Primary",
    )


def _proposition(
    text: str = "Frozen proposition.",
    *,
    evidence_keys: tuple[str, ...] = ("evidence-1",),
) -> GovernedPropositionLink:
    return GovernedPropositionLink(
        source_proposition_index=0,
        text=text,
        status="supported_but_not_established",
        confidence="medium",
        rationale="Frozen rationale.",
        evidence_keys=evidence_keys,
    )


def _use(
    evidence_key: str = "evidence-1",
    *,
    proposition_text: str = "Frozen proposition.",
    proposition_evidence_keys: tuple[str, ...] = ("evidence-1",),
) -> GovernedEvidenceUse:
    return GovernedEvidenceUse(
        issue_analysis_id="analysis-1",
        issue_definition_id="EK-001",
        issue_definition_version="1.0",
        element_id="EK-DIRECT-KNOWLEDGE",
        element_ordinal=0,
        evidence_key=evidence_key,
        analytical_role="supporting",
        mapping_relevance="relevant",
        mapping_confidence="high",
        mapping_rationale="Frozen mapping.",
        assessment_confidence="medium",
        assessment_rationale="Frozen assessment.",
        citation="Employer letter.pdf, p.1",
        proposition_links=(
            _proposition(
                proposition_text,
                evidence_keys=proposition_evidence_keys,
            ),
        ),
    )


def _map() -> GovernedIssueEvidenceMap:
    return GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id="case-1",
        source_synthesis_id="synthesis-1",
        source_matrices_schema_version="case-matrices-schema/1.0",
        source_matrix_builder_version="case-matrix-builder/1.0",
        source_analysis_ids=("analysis-z", "analysis-1"),
        coverage=_coverage(),
        bindings=(
            GovernedEvidenceUseBinding(
                evidence=_evidence(),
                use=_use(),
            ),
        ),
        unmapped_evidence=(),
    )


def test_valid_map_preserves_source_analysis_order_and_duplicate_use_fails_closed():
    value = _map()
    validate_governed_issue_evidence_map(value)
    assert value.source_analysis_ids == ("analysis-z", "analysis-1")

    duplicated = replace(
        value,
        bindings=(value.bindings[0], value.bindings[0]),
    )

    with pytest.raises(
        GovernedIssueEvidenceValidationError,
        match="Duplicate frozen EvidenceUse",
    ):
        validate_governed_issue_evidence_map(duplicated)


def test_partial_or_non_all_evidence_authority_fails_closed():
    value = _map()

    partial = replace(
        value,
        coverage=replace(
            value.coverage,
            search_mode="document_complete",
            case_corpus_complete=False,
            negative_finding_scope="searched_scope",
        ),
    )
    with pytest.raises(
        GovernedIssueEvidenceValidationError,
        match="EXHAUSTIVE_EVIDENCE",
    ):
        validate_governed_issue_evidence_map(partial)

    filtered = replace(
        value,
        coverage=replace(
            value.coverage,
            filters_applied=("text_match=all_evidence", "roles=primary_source"),
        ),
    )
    with pytest.raises(
        GovernedIssueEvidenceValidationError,
        match="forbids filtered",
    ):
        validate_governed_issue_evidence_map(filtered)


def test_cross_use_same_proposition_coordinate_must_have_identical_payload():
    value = _map()
    shared_keys = ("evidence-1", "evidence-2")
    first_use = _use(proposition_evidence_keys=shared_keys)
    second_use = _use(
        evidence_key="evidence-2",
        proposition_text="Conflicting proposition payload.",
        proposition_evidence_keys=shared_keys,
    )
    second_evidence = replace(
        _evidence("evidence-2"),
        chunk_ordinal=1,
        evidence_binding_id="binding-2",
        chunk_text_sha256="sha256:" + "4" * 64,
    )
    broken = replace(
        value,
        coverage=replace(
            value.coverage,
            case_chunk_count=2,
            scope_chunk_count=2,
            chunks_inspected=2,
            matched_evidence_keys=("evidence-1", "evidence-2"),
        ),
        bindings=(
            GovernedEvidenceUseBinding(
                evidence=value.bindings[0].evidence,
                use=first_use,
            ),
            GovernedEvidenceUseBinding(
                evidence=second_evidence,
                use=second_use,
            ),
        ),
    )

    with pytest.raises(
        GovernedIssueEvidenceValidationError,
        match="proposition coordinate",
    ):
        validate_governed_issue_evidence_map(broken)
