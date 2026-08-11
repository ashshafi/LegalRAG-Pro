"""Deterministic JSON serialization for U9B governed issue-evidence bindings."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from .models import (
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedPropositionLink,
    GovernedSearchCoverage,
)
from .validation import validate_governed_issue_evidence_map


def dumps_governed_issue_evidence_map(value: GovernedIssueEvidenceMap) -> str:
    """Serialize one validated U9B binding to canonical JSON."""

    validate_governed_issue_evidence_map(value)
    return json.dumps(
        asdict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _coverage(data: dict[str, Any]) -> GovernedSearchCoverage:
    return GovernedSearchCoverage(
        schema_version=str(data["schema_version"]),
        search_mode=str(data["search_mode"]),
        text_match_mode=str(data["text_match_mode"]),
        query_sha256=str(data["query_sha256"]),
        case_document_count=int(data["case_document_count"]),
        case_page_count=int(data["case_page_count"]),
        case_chunk_count=int(data["case_chunk_count"]),
        scope_document_count=int(data["scope_document_count"]),
        scope_page_count=int(data["scope_page_count"]),
        scope_chunk_count=int(data["scope_chunk_count"]),
        documents_completely_expanded=int(data["documents_completely_expanded"]),
        pages_inspected=int(data["pages_inspected"]),
        chunks_inspected=int(data["chunks_inspected"]),
        candidate_document_ids=tuple(str(item) for item in data["candidate_document_ids"]),
        searched_document_ids=tuple(str(item) for item in data["searched_document_ids"]),
        filters_applied=tuple(str(item) for item in data["filters_applied"]),
        matched_evidence_keys=tuple(str(item) for item in data["matched_evidence_keys"]),
        completion=str(data["completion"]),
        case_corpus_complete=bool(data["case_corpus_complete"]),
        negative_finding_scope=str(data["negative_finding_scope"]),
        negative_finding_permitted=bool(data["negative_finding_permitted"]),
    )


def _evidence(data: dict[str, Any]) -> GovernedEvidenceRef:
    return GovernedEvidenceRef(
        evidence_key=str(data["evidence_key"]),
        source_document_instance_id=str(data["source_document_instance_id"]),
        source_snapshot_id=str(data["source_snapshot_id"]),
        original_filename=str(data["original_filename"]),
        original_blob_sha256=str(data["original_blob_sha256"]),
        extraction_profile_id=str(data["extraction_profile_id"]),
        chunking_profile_id=str(data["chunking_profile_id"]),
        page_number=int(data["page_number"]),
        page_text_sha256=str(data["page_text_sha256"]),
        extraction_method=str(data["extraction_method"]),
        chunk_ordinal=int(data["chunk_ordinal"]),
        chunk_id=str(data["chunk_id"]),
        evidence_binding_id=str(data["evidence_binding_id"]),
        binding_class=str(data["binding_class"]),
        bound_text_role=str(data["bound_text_role"]),
        chunk_text_sha256=str(data["chunk_text_sha256"]),
        chunk_text_byte_length=int(data["chunk_text_byte_length"]),
        citation=str(data["citation"]),
        evidence_role=str(data["evidence_role"]),
        role_rule_id=str(data["role_rule_id"]),
        role_basis=str(data["role_basis"]),
        source_type=str(data["source_type"]),
        source_label=str(data["source_label"]),
        provenance_method=str(data["provenance_method"]),
        primary_tier=int(data["primary_tier"]),
        primary_label=str(data["primary_label"]),
    )


def _proposition(data: dict[str, Any]) -> GovernedPropositionLink:
    return GovernedPropositionLink(
        source_proposition_index=int(data["source_proposition_index"]),
        text=str(data["text"]),
        status=str(data["status"]),
        confidence=str(data["confidence"]),
        rationale=str(data["rationale"]),
        evidence_keys=tuple(str(item) for item in data["evidence_keys"]),
    )


def _use(data: dict[str, Any]) -> GovernedEvidenceUse:
    return GovernedEvidenceUse(
        issue_analysis_id=str(data["issue_analysis_id"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        element_id=str(data["element_id"]),
        element_ordinal=int(data["element_ordinal"]),
        evidence_key=str(data["evidence_key"]),
        analytical_role=str(data["analytical_role"]),
        mapping_relevance=str(data["mapping_relevance"]),
        mapping_confidence=str(data["mapping_confidence"]),
        mapping_rationale=str(data["mapping_rationale"]),
        assessment_confidence=str(data["assessment_confidence"]),
        assessment_rationale=str(data["assessment_rationale"]),
        citation=str(data["citation"]),
        proposition_links=tuple(_proposition(item) for item in data["proposition_links"]),
    )


def loads_governed_issue_evidence_map(payload: str) -> GovernedIssueEvidenceMap:
    """Load canonical U9B JSON and validate the reconstructed object."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Governed issue-evidence JSON must contain an object.")

    result = GovernedIssueEvidenceMap(
        schema_version=str(data["schema_version"]),
        builder_version=str(data["builder_version"]),
        case_id=str(data["case_id"]),
        source_synthesis_id=str(data["source_synthesis_id"]),
        source_matrices_schema_version=str(data["source_matrices_schema_version"]),
        source_matrix_builder_version=str(data["source_matrix_builder_version"]),
        source_analysis_ids=tuple(str(item) for item in data["source_analysis_ids"]),
        coverage=_coverage(data["coverage"]),
        bindings=tuple(
            GovernedEvidenceUseBinding(
                evidence=_evidence(item["evidence"]),
                use=_use(item["use"]),
            )
            for item in data["bindings"]
        ),
        unmapped_evidence=tuple(_evidence(item) for item in data["unmapped_evidence"]),
    )
    validate_governed_issue_evidence_map(result)
    return result


__all__ = [
    "dumps_governed_issue_evidence_map",
    "loads_governed_issue_evidence_map",
]
