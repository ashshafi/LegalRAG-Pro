from governed_issue_evidence.models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedIssueEvidenceMap,
    GovernedSearchCoverage,
)
from governed_issue_evidence.serialization import (
    dumps_governed_issue_evidence_map,
    loads_governed_issue_evidence_map,
)


def test_canonical_round_trip_for_unmapped_complete_u8_evidence():
    coverage = GovernedSearchCoverage(
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

    evidence = GovernedEvidenceRef(
        evidence_key="evidence-1",
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
        chunk_id="evidence-1",
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

    value = GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id="case-1",
        source_synthesis_id="synthesis-1",
        source_matrices_schema_version="case-matrices-schema/1.0",
        source_matrix_builder_version="case-matrix-builder/1.0",
        source_analysis_ids=("analysis-z", "analysis-1"),
        coverage=coverage,
        bindings=(),
        unmapped_evidence=(evidence,),
    )

    payload = dumps_governed_issue_evidence_map(value)
    restored = loads_governed_issue_evidence_map(payload)

    assert restored == value
    assert restored.source_analysis_ids == ("analysis-z", "analysis-1")
    assert dumps_governed_issue_evidence_map(restored) == payload
