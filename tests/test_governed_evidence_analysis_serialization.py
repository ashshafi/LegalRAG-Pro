import json

import pytest

from governed_evidence_analysis.identity import (
    derive_governed_evidential_analysis_id,
    source_u9b_sha256,
)
from governed_evidence_analysis.models import (
    GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
    GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
    GovernedEvidenceAssessment,
    GovernedEvidenceObservation,
    GovernedEvidenceObservationType,
    GovernedEvidenceUseCoordinate,
    GovernedEvidentialAnalysis,
)
from governed_evidence_analysis.serialization import (
    dumps_governed_evidential_analysis,
    loads_governed_evidential_analysis,
)
from governed_issue_evidence.models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedSearchCoverage,
)


def _source_and_analysis():
    coverage = GovernedSearchCoverage(
        schema_version="1.0", search_mode="exhaustive_evidence", text_match_mode="all_evidence",
        query_sha256="sha256:" + "0" * 64, case_document_count=1, case_page_count=1,
        case_chunk_count=1, scope_document_count=1, scope_page_count=1, scope_chunk_count=1,
        documents_completely_expanded=1, pages_inspected=1, chunks_inspected=1,
        candidate_document_ids=(), searched_document_ids=("doc-1",),
        filters_applied=("text_match=all_evidence",), matched_evidence_keys=("evidence-1",),
        completion="complete", case_corpus_complete=True, negative_finding_scope="case_corpus",
        negative_finding_permitted=True,
    )
    evidence = GovernedEvidenceRef(
        evidence_key="evidence-1", source_document_instance_id="doc-1", source_snapshot_id="snap-1",
        original_filename="Employer.pdf", original_blob_sha256="sha256:" + "1" * 64,
        extraction_profile_id="extract-v1", chunking_profile_id="chunk-v1", page_number=1,
        page_text_sha256="sha256:" + "2" * 64, extraction_method="pypdf_text", chunk_ordinal=0,
        chunk_id="chunk-1", evidence_binding_id="binding-1", binding_class="full_chain_bound",
        bound_text_role="chunk_text", chunk_text_sha256="sha256:" + "3" * 64,
        chunk_text_byte_length=10, citation="Employer.pdf, p.1", evidence_role="primary_source",
        role_rule_id="primary.direct_source_type", role_basis="Frozen U8 rule.",
        source_type="employer_record", source_label="Employer record", provenance_method="filename",
        primary_tier=1, primary_label="Primary",
    )
    use = GovernedEvidenceUse(
        issue_analysis_id="analysis-1", issue_definition_id="EK-001", issue_definition_version="1.0",
        element_id="EK-KNOWLEDGE", element_ordinal=0, evidence_key="evidence-1", analytical_role="adverse",
        mapping_relevance="relevant", mapping_confidence="high", mapping_rationale="Frozen mapping.",
        assessment_confidence="medium", assessment_rationale="Frozen assessment.",
        citation="Employer.pdf, p.1", proposition_links=(),
    )
    source = GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id="case-1", source_synthesis_id="synthesis-1",
        source_matrices_schema_version="case-matrices-schema/1.0",
        source_matrix_builder_version="case-matrix-builder/1.0", source_analysis_ids=("analysis-1",),
        coverage=coverage, bindings=(GovernedEvidenceUseBinding(evidence=evidence, use=use),),
        unmapped_evidence=(),
    )
    coordinate = GovernedEvidenceUseCoordinate("analysis-1", "EK-KNOWLEDGE", "evidence-1")
    observations = tuple(sorted((
        GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_BOUND),
        GovernedEvidenceObservation(GovernedEvidenceObservationType.PRIMARY_SOURCE_BOUND),
        GovernedEvidenceObservation(GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT, coordinate),
    ), key=lambda item: (item.observation_type.value, "" if item.use_coordinate is None else item.use_coordinate.issue_analysis_id)))
    source_sha = source_u9b_sha256(source)
    analysis = GovernedEvidentialAnalysis(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id="case-1", source_u9b_sha256=source_sha,
        analysis_id=derive_governed_evidential_analysis_id(
            schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
            identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
            case_id="case-1", source_u9b_sha256_value=source_sha,
        ),
        evidence_assessments=(GovernedEvidenceAssessment("evidence-1", (coordinate,), observations),),
    )
    return source, analysis


def test_canonical_round_trip_and_strict_unknown_or_duplicate_json_keys():
    source, analysis = _source_and_analysis()
    payload = dumps_governed_evidential_analysis(analysis, source)
    restored = loads_governed_evidential_analysis(payload, source)
    assert restored == analysis
    assert dumps_governed_evidential_analysis(restored, source) == payload

    data = json.loads(payload)
    data["unexpected"] = True
    with pytest.raises(ValueError, match="invalid keys"):
        loads_governed_evidential_analysis(json.dumps(data), source)

    duplicate = payload[:-1] + ',"case_id":"case-1"}'
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        loads_governed_evidential_analysis(duplicate, source)
