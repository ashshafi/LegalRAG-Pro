"""Model tests plus frozen/synthetic B6 bundle helpers used by the dedicated suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

from case_analysis.m2.matrix_serialization import loads_case_matrices
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
from governed_analytical_authority.models import (
    GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
    GovernedAnalyticalAuthorityActivationAction,
    GovernedAnalyticalAuthorityActivationReceipt,
    GovernedAnalyticalAuthorityActivePointer,
    GovernedAnalyticalAuthorityManifest,
)
from governed_analytical_authority.serialization import (
    loads_structured_legal_analysis_results,
)


FROZEN_M5_SHA256 = "32000cc37740b9cc238a6a3a90869e121ba8932f158fe5238533086f4f10f6f6"


def _fixture_path() -> Path:
    configured = os.environ.get("LEGALRAG_B6_FIXTURE_ROOT")
    root = Path(configured) if configured else Path(__file__).resolve().parent / "fixtures"
    return root / "shafi_m3_frozen_analytical_snapshot_v1_0.json"


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _evidence_ref(record) -> GovernedEvidenceRef:
    key = record.evidence_key
    digest_a = "sha256:" + "a" * 64
    digest_b = "sha256:" + "b" * 64
    digest_c = "sha256:" + "c" * 64
    return GovernedEvidenceRef(
        evidence_key=key,
        source_document_instance_id=record.document_id or f"doc::{record.document_name}",
        source_snapshot_id=digest_a,
        original_filename=record.document_name,
        original_blob_sha256=digest_b,
        extraction_profile_id="test-extraction/1.0",
        chunking_profile_id="test-chunking/1.0",
        page_number=record.page or 1,
        page_text_sha256=digest_c,
        extraction_method="text",
        chunk_ordinal=0,
        chunk_id=record.chunk_id or key,
        evidence_binding_id="sha256:" + "d" * 64,
        binding_class="full_chain_bound",
        bound_text_role="chunk_text",
        chunk_text_sha256="sha256:" + "e" * 64,
        chunk_text_byte_length=max(1, len(record.citation.encode("utf-8"))),
        citation=record.citation,
        evidence_role="secondary_source",
        role_rule_id="test-role/1.0",
        role_basis="B6 deterministic synthetic governed reference.",
        source_type=record.source_type.value,
        source_label=record.source_type.value,
        provenance_method=record.provenance_basis.value,
        primary_tier=2,
        primary_label="secondary",
    )


def _u9b_from_matrices(matrices) -> GovernedIssueEvidenceMap:
    evidence_by_key = {record.evidence_key: _evidence_ref(record) for record in matrices.evidence_matrix}
    bindings = []
    for record in matrices.evidence_matrix:
        evidence = evidence_by_key[record.evidence_key]
        for use in record.uses:
            links = tuple(
                GovernedPropositionLink(
                    source_proposition_index=item.source_proposition_index,
                    text=item.text,
                    status=item.status.value,
                    confidence=item.confidence.value,
                    rationale=item.rationale,
                    evidence_keys=item.evidence_keys,
                )
                for item in use.proposition_links
            )
            bindings.append(
                GovernedEvidenceUseBinding(
                    evidence=evidence,
                    use=GovernedEvidenceUse(
                        issue_analysis_id=use.issue_analysis_id,
                        issue_definition_id=use.issue_definition_id,
                        issue_definition_version=use.issue_definition_version,
                        element_id=use.element_id,
                        element_ordinal=use.element_ordinal,
                        evidence_key=use.evidence_key,
                        analytical_role=use.analytical_role.value,
                        mapping_relevance=use.mapping_relevance.value,
                        mapping_confidence=use.mapping_confidence.value,
                        mapping_rationale=use.mapping_rationale,
                        assessment_confidence=use.assessment_confidence.value,
                        assessment_rationale=use.assessment_rationale,
                        citation=use.citation,
                        proposition_links=links,
                    ),
                )
            )
    bindings = tuple(
        sorted(
            bindings,
            key=lambda item: (
                item.use.issue_definition_id,
                item.use.issue_definition_version,
                item.use.issue_analysis_id,
                item.use.element_ordinal,
                item.use.element_id,
                item.use.evidence_key,
            ),
        )
    )
    keys = tuple(sorted(evidence_by_key))
    count = len(keys)
    coverage = GovernedSearchCoverage(
        schema_version="governed-complete-search-coverage/1.0",
        search_mode="exhaustive_evidence",
        text_match_mode="all_evidence",
        query_sha256="sha256:" + "f" * 64,
        case_document_count=1,
        case_page_count=count,
        case_chunk_count=count,
        scope_document_count=1,
        scope_page_count=count,
        scope_chunk_count=count,
        documents_completely_expanded=1,
        pages_inspected=count,
        chunks_inspected=count,
        candidate_document_ids=(),
        searched_document_ids=("synthetic-governed-document",),
        filters_applied=("text_match=all_evidence",),
        matched_evidence_keys=keys,
        completion="complete",
        case_corpus_complete=True,
        negative_finding_scope="case_corpus",
        negative_finding_permitted=True,
    )
    return GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id=matrices.case_id,
        source_synthesis_id=matrices.synthesis_id,
        source_matrices_schema_version=matrices.schema_version,
        source_matrix_builder_version=matrices.matrix_builder_version,
        source_analysis_ids=matrices.source_analysis_ids,
        coverage=coverage,
        bindings=bindings,
        unmapped_evidence=(),
    )


def _u9c_from_u9b(u9b: GovernedIssueEvidenceMap) -> GovernedEvidentialAnalysis:
    by_key: dict[str, list[GovernedEvidenceUse]] = {key: [] for key in u9b.coverage.matched_evidence_keys}
    for binding in u9b.bindings:
        by_key[binding.evidence.evidence_key].append(binding.use)
    assessments = []
    for key in sorted(by_key):
        uses = tuple(
            sorted(
                (
                    GovernedEvidenceUseCoordinate(
                        issue_analysis_id=use.issue_analysis_id,
                        element_id=use.element_id,
                        evidence_key=key,
                    )
                    for use in by_key[key]
                )
            )
        )
        observations = [
            GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_BOUND)
        ]
        for use, coordinate in zip(sorted(by_key[key], key=lambda item: (item.issue_analysis_id, item.element_id, item.evidence_key)), uses, strict=True):
            if use.analytical_role == "adverse":
                observations.append(
                    GovernedEvidenceObservation(
                        GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT,
                        use_coordinate=coordinate,
                    )
                )
            elif use.analytical_role == "conflicting":
                observations.append(
                    GovernedEvidenceObservation(
                        GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT,
                        use_coordinate=coordinate,
                    )
                )
        observations_tuple = tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.observation_type.value,
                    "" if item.use_coordinate is None else item.use_coordinate.issue_analysis_id,
                    "" if item.use_coordinate is None else item.use_coordinate.element_id,
                    "" if item.use_coordinate is None else item.use_coordinate.evidence_key,
                ),
            )
        )
        assessments.append(
            GovernedEvidenceAssessment(
                evidence_key=key,
                use_coordinates=uses,
                observations=observations_tuple,
            )
        )
    source_sha = source_u9b_sha256(u9b)
    analysis_id = derive_governed_evidential_analysis_id(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id=u9b.case_id,
        source_u9b_sha256_value=source_sha,
    )
    return GovernedEvidentialAnalysis(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id=u9b.case_id,
        source_u9b_sha256=source_sha,
        analysis_id=analysis_id,
        evidence_assessments=tuple(assessments),
    )


def _bundle():
    snapshot = json.loads(_fixture_path().read_text(encoding="utf-8"))
    m5_payload = _canonical_json(snapshot["components"]["m5_results"])
    matrices_payload = _canonical_json(snapshot["components"]["matrices"])
    results = loads_structured_legal_analysis_results(m5_payload)
    matrices = loads_case_matrices(matrices_payload)
    u9b = _u9b_from_matrices(matrices)
    u9c = _u9c_from_u9b(u9b)
    return results, matrices, u9b, u9c


def _patch_roots(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "governed_analytical_authorities"
    import governed_analytical_authority.activation as activation
    import governed_analytical_authority.provider as provider
    import governed_analytical_authority.publication as publication

    monkeypatch.setattr(activation, "_authority_root", lambda: root)
    monkeypatch.setattr(provider, "_authority_root", lambda: root)
    monkeypatch.setattr(publication, "_authority_root", lambda: root)
    return root


def test_model_contracts_are_immutable_and_non_substantive():
    manifest = GovernedAnalyticalAuthorityManifest(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
        identity_version=GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
        case_id="11111111-1111-4111-8111-111111111111",
        structured_legal_analysis_results_sha256="sha256:" + "1" * 64,
        case_matrices_sha256="sha256:" + "2" * 64,
        governed_issue_evidence_map_sha256="sha256:" + "3" * 64,
        governed_evidential_analysis_sha256="sha256:" + "4" * 64,
        source_analysis_ids=("22222222-2222-4222-8222-222222222222",),
        authority_id="sha256:" + "5" * 64,
    )
    pointer = GovernedAnalyticalAuthorityActivePointer(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
        case_id=manifest.case_id,
        authority_id=manifest.authority_id,
        authority_manifest_sha256="sha256:" + "6" * 64,
        activation_id="sha256:" + "7" * 64,
    )
    receipt = GovernedAnalyticalAuthorityActivationReceipt(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
        case_id=manifest.case_id,
        activation_id=pointer.activation_id,
        action=GovernedAnalyticalAuthorityActivationAction.ACTIVATE,
        previous_activation_id=None,
        previous_authority_id=None,
        new_authority_id=manifest.authority_id,
        previous_active_pointer_sha256=None,
        new_active_pointer_sha256="sha256:" + "8" * 64,
    )
    assert manifest.source_analysis_ids == ("22222222-2222-4222-8222-222222222222",)
    assert pointer.authority_id == manifest.authority_id
    assert receipt.action is GovernedAnalyticalAuthorityActivationAction.ACTIVATE
    assert not hasattr(manifest, "confidence")
    assert not hasattr(pointer, "question")
    assert not hasattr(receipt, "summary")
