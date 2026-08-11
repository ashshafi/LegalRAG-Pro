from dataclasses import replace

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
from governed_evidence_analysis.validation import (
    GovernedEvidentialAnalysisValidationError,
    validate_governed_evidential_analysis,
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


def _evidence(key: str, *, role: str, ordinal: int) -> GovernedEvidenceRef:
    return GovernedEvidenceRef(
        evidence_key=key, source_document_instance_id="doc-1", source_snapshot_id="snap-1",
        original_filename="Case file.pdf", original_blob_sha256="sha256:" + "1" * 64,
        extraction_profile_id="extract-v1", chunking_profile_id="chunk-v1", page_number=1,
        page_text_sha256="sha256:" + "2" * 64, extraction_method="pypdf_text", chunk_ordinal=ordinal,
        chunk_id=f"chunk-{ordinal}", evidence_binding_id=f"binding-{ordinal}",
        binding_class="full_chain_bound", bound_text_role="chunk_text",
        chunk_text_sha256="sha256:" + str(3 + ordinal) * 64, chunk_text_byte_length=10,
        citation="Case file.pdf, p.1", evidence_role=role,
        role_rule_id="primary.direct_source_type" if role == "primary_source" else "mixed.rule",
        role_basis="Frozen U8 rule.", source_type="employer_record" if role == "primary_source" else "mixed",
        source_label="Employer record" if role == "primary_source" else "Mixed source",
        provenance_method="filename", primary_tier=1 if role == "primary_source" else 2,
        primary_label="Primary" if role == "primary_source" else "Mixed",
    )


def _use(element_id: str, ordinal: int, *, role: str) -> GovernedEvidenceUse:
    return GovernedEvidenceUse(
        issue_analysis_id="analysis-1", issue_definition_id="EK-001", issue_definition_version="1.0",
        element_id=element_id, element_ordinal=ordinal, evidence_key="evidence-1", analytical_role=role,
        mapping_relevance="relevant", mapping_confidence="high", mapping_rationale="Frozen mapping.",
        assessment_confidence="medium", assessment_rationale="Frozen assessment.",
        citation="Case file.pdf, p.1", proposition_links=(),
    )


def _source() -> GovernedIssueEvidenceMap:
    coverage = GovernedSearchCoverage(
        schema_version="1.0", search_mode="exhaustive_evidence", text_match_mode="all_evidence",
        query_sha256="sha256:" + "0" * 64, case_document_count=1, case_page_count=1,
        case_chunk_count=3, scope_document_count=1, scope_page_count=1, scope_chunk_count=3,
        documents_completely_expanded=1, pages_inspected=1, chunks_inspected=3,
        candidate_document_ids=(), searched_document_ids=("doc-1",),
        filters_applied=("text_match=all_evidence",),
        matched_evidence_keys=("evidence-1", "evidence-2", "evidence-3"),
        completion="complete", case_corpus_complete=True, negative_finding_scope="case_corpus",
        negative_finding_permitted=True,
    )
    e1 = _evidence("evidence-1", role="primary_source", ordinal=0)
    return GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id="case-1", source_synthesis_id="synthesis-1",
        source_matrices_schema_version="case-matrices-schema/1.0",
        source_matrix_builder_version="case-matrix-builder/1.0", source_analysis_ids=("analysis-1",),
        coverage=coverage,
        bindings=(
            GovernedEvidenceUseBinding(evidence=e1, use=_use("EK-A", 0, role="adverse")),
            GovernedEvidenceUseBinding(evidence=e1, use=_use("EK-B", 1, role="conflicting")),
        ),
        unmapped_evidence=(
            _evidence("evidence-2", role="mixed", ordinal=1),
            _evidence("evidence-3", role="primary_source", ordinal=2),
        ),
    )


def _obs(*items: GovernedEvidenceObservation) -> tuple[GovernedEvidenceObservation, ...]:
    return tuple(sorted(items, key=lambda item: (
        item.observation_type.value,
        "" if item.use_coordinate is None else item.use_coordinate.issue_analysis_id,
        "" if item.use_coordinate is None else item.use_coordinate.element_id,
        "" if item.use_coordinate is None else item.use_coordinate.evidence_key,
    )))


def _analysis(source: GovernedIssueEvidenceMap) -> GovernedEvidentialAnalysis:
    a = GovernedEvidenceUseCoordinate("analysis-1", "EK-A", "evidence-1")
    b = GovernedEvidenceUseCoordinate("analysis-1", "EK-B", "evidence-1")
    source_sha = source_u9b_sha256(source)
    return GovernedEvidentialAnalysis(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id="case-1", source_u9b_sha256=source_sha,
        analysis_id=derive_governed_evidential_analysis_id(
            schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
            identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
            case_id="case-1", source_u9b_sha256_value=source_sha,
        ),
        evidence_assessments=(
            GovernedEvidenceAssessment(
                "evidence-1", (a, b),
                _obs(
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_BOUND),
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.PRIMARY_SOURCE_BOUND),
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT, a),
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT, b),
                ),
            ),
            GovernedEvidenceAssessment(
                "evidence-2", (),
                _obs(GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED)),
            ),
            GovernedEvidenceAssessment(
                "evidence-3", (),
                _obs(
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED),
                    GovernedEvidenceObservation(GovernedEvidenceObservationType.PRIMARY_SOURCE_UNMAPPED),
                ),
            ),
        ),
    )


def test_complete_source_bound_overlay_is_valid_and_does_not_mutate_u9b():
    source = _source()
    before = source
    analysis = _analysis(source)
    validate_governed_evidential_analysis(analysis, source)
    assert source == before
    assert analysis.evidence_assessments[2].observations[-1].observation_type is GovernedEvidenceObservationType.PRIMARY_SOURCE_UNMAPPED


def test_missing_or_foreign_overlay_state_fails_closed():
    source = _source()
    analysis = _analysis(source)

    missing = replace(analysis, evidence_assessments=analysis.evidence_assessments[:-1])
    with pytest.raises(GovernedEvidentialAnalysisValidationError, match="exactly cover"):
        validate_governed_evidential_analysis(missing, source)

    wrong_coordinate = GovernedEvidenceUseCoordinate("analysis-1", "EK-FOREIGN", "evidence-1")
    broken_first = replace(
        analysis.evidence_assessments[0],
        use_coordinates=(wrong_coordinate,),
    )
    broken = replace(analysis, evidence_assessments=(broken_first,) + analysis.evidence_assessments[1:])
    with pytest.raises(GovernedEvidentialAnalysisValidationError, match="exactly match"):
        validate_governed_evidential_analysis(broken, source)


def test_source_fingerprint_and_role_observation_semantics_fail_closed():
    source = _source()
    analysis = _analysis(source)

    bad_sha = replace(analysis, source_u9b_sha256="sha256:" + "f" * 64)
    with pytest.raises(GovernedEvidentialAnalysisValidationError, match="canonical frozen U9B"):
        validate_governed_evidential_analysis(bad_sha, source)

    first = analysis.evidence_assessments[0]
    stripped = replace(
        first,
        observations=tuple(
            item for item in first.observations
            if item.observation_type is not GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT
        ),
    )
    broken = replace(analysis, evidence_assessments=(stripped,) + analysis.evidence_assessments[1:])
    with pytest.raises(GovernedEvidentialAnalysisValidationError, match="deterministic frozen U9B facts"):
        validate_governed_evidential_analysis(broken, source)
