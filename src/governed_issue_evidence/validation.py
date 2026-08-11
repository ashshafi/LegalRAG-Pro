"""Fail-closed validation for U9B governed issue-evidence bindings."""

from __future__ import annotations

from .models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedIssueEvidenceMap,
)


class GovernedIssueEvidenceValidationError(ValueError):
    """Raised when a U9B binding violates the frozen authority boundary."""


def validate_governed_issue_evidence_map(value: GovernedIssueEvidenceMap) -> None:
    """Validate one deterministic U9B binding without retrieving or inferring evidence."""

    if value.schema_version != GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION:
        raise GovernedIssueEvidenceValidationError("Unsupported governed issue-evidence schema.")
    if value.builder_version != GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION:
        raise GovernedIssueEvidenceValidationError("Unsupported governed issue-evidence builder.")
    if not value.case_id.strip():
        raise GovernedIssueEvidenceValidationError("case_id must be non-empty.")
    if not value.source_synthesis_id.strip():
        raise GovernedIssueEvidenceValidationError("source_synthesis_id must be non-empty.")
    if not value.source_matrices_schema_version.strip():
        raise GovernedIssueEvidenceValidationError(
            "source_matrices_schema_version must be non-empty."
        )
    if not value.source_matrix_builder_version.strip():
        raise GovernedIssueEvidenceValidationError(
            "source_matrix_builder_version must be non-empty."
        )

    source_ids = tuple(value.source_analysis_ids)
    if not source_ids or any(not item.strip() for item in source_ids):
        raise GovernedIssueEvidenceValidationError(
            "source_analysis_ids must contain non-empty analytical identities."
        )
    if len(set(source_ids)) != len(source_ids):
        raise GovernedIssueEvidenceValidationError(
            "source_analysis_ids must preserve a unique frozen source set."
        )

    coverage = value.coverage
    if coverage.search_mode != "exhaustive_evidence":
        raise GovernedIssueEvidenceValidationError(
            "U9B v1 requires U8 EXHAUSTIVE_EVIDENCE authority."
        )
    if coverage.text_match_mode != "all_evidence":
        raise GovernedIssueEvidenceValidationError(
            "U9B v1 requires U8 ALL_EVIDENCE text matching."
        )
    if coverage.filters_applied != ("text_match=all_evidence",):
        raise GovernedIssueEvidenceValidationError(
            "U9B v1 forbids filtered U8 evidence authority."
        )
    if coverage.completion != "complete":
        raise GovernedIssueEvidenceValidationError("U9B requires a COMPLETE U8 search.")
    if not coverage.case_corpus_complete:
        raise GovernedIssueEvidenceValidationError(
            "U9B requires complete case-corpus U8 coverage."
        )
    if coverage.negative_finding_scope != "case_corpus":
        raise GovernedIssueEvidenceValidationError(
            "Complete U9B authority must carry CASE_CORPUS negative-finding scope."
        )
    if not coverage.negative_finding_permitted:
        raise GovernedIssueEvidenceValidationError(
            "Complete U9B authority must preserve U8 negative-finding permission."
        )
    if coverage.candidate_document_ids:
        raise GovernedIssueEvidenceValidationError(
            "EXHAUSTIVE_EVIDENCE authority cannot contain candidate_document_ids."
        )

    counts = (
        coverage.case_document_count,
        coverage.case_page_count,
        coverage.case_chunk_count,
        coverage.scope_document_count,
        coverage.scope_page_count,
        coverage.scope_chunk_count,
        coverage.documents_completely_expanded,
        coverage.pages_inspected,
        coverage.chunks_inspected,
    )
    if any(item < 0 for item in counts):
        raise GovernedIssueEvidenceValidationError("Coverage counts must be non-negative.")
    if coverage.scope_document_count != coverage.case_document_count:
        raise GovernedIssueEvidenceValidationError("Case document coverage is incomplete.")
    if coverage.scope_page_count != coverage.case_page_count:
        raise GovernedIssueEvidenceValidationError("Case page coverage is incomplete.")
    if coverage.scope_chunk_count != coverage.case_chunk_count:
        raise GovernedIssueEvidenceValidationError("Case chunk coverage is incomplete.")
    if coverage.documents_completely_expanded != coverage.case_document_count:
        raise GovernedIssueEvidenceValidationError("Not every case document was expanded.")
    if coverage.pages_inspected != coverage.case_page_count:
        raise GovernedIssueEvidenceValidationError("Not every case page was inspected.")
    if coverage.chunks_inspected != coverage.case_chunk_count:
        raise GovernedIssueEvidenceValidationError("Not every case chunk was inspected.")

    if len(coverage.searched_document_ids) != coverage.case_document_count:
        raise GovernedIssueEvidenceValidationError(
            "searched_document_ids does not cover the complete case corpus."
        )
    if len(set(coverage.searched_document_ids)) != len(coverage.searched_document_ids):
        raise GovernedIssueEvidenceValidationError(
            "searched_document_ids contains duplicates."
        )
    if len(coverage.matched_evidence_keys) != coverage.case_chunk_count:
        raise GovernedIssueEvidenceValidationError(
            "matched_evidence_keys does not cover every governed chunk."
        )
    if len(set(coverage.matched_evidence_keys)) != len(coverage.matched_evidence_keys):
        raise GovernedIssueEvidenceValidationError(
            "matched_evidence_keys contains duplicates."
        )

    binding_identities: set[tuple[str, str, str]] = set()
    evidence_by_key = {}
    proposition_payload_by_coordinate = {}

    for binding in value.bindings:
        evidence = binding.evidence
        use = binding.use

        if evidence.evidence_key != use.evidence_key:
            raise GovernedIssueEvidenceValidationError(
                "Binding evidence key does not match its EvidenceUse."
            )
        if use.issue_analysis_id not in source_ids:
            raise GovernedIssueEvidenceValidationError(
                "EvidenceUse resolves outside source_analysis_ids."
            )
        if use.identity in binding_identities:
            raise GovernedIssueEvidenceValidationError(
                "Duplicate frozen EvidenceUse identity in U9B binding."
            )
        binding_identities.add(use.identity)

        existing = evidence_by_key.get(evidence.evidence_key)
        if existing is not None and existing != evidence:
            raise GovernedIssueEvidenceValidationError(
                "One evidence_key resolved to incompatible U8 evidence references."
            )
        evidence_by_key[evidence.evidence_key] = evidence

        indexes = tuple(item.source_proposition_index for item in use.proposition_links)
        if tuple(sorted(indexes)) != indexes:
            raise GovernedIssueEvidenceValidationError(
                "Proposition links must remain in source-proposition order."
            )
        if len(set(indexes)) != len(indexes):
            raise GovernedIssueEvidenceValidationError(
                "Duplicate source proposition index inside one EvidenceUse."
            )

        for proposition in use.proposition_links:
            if use.evidence_key not in proposition.evidence_keys:
                raise GovernedIssueEvidenceValidationError(
                    "EvidenceUse proposition link does not name its evidence_key."
                )
            coordinate = (
                use.issue_analysis_id,
                use.element_id,
                proposition.source_proposition_index,
            )
            payload = (
                proposition.text,
                proposition.status,
                proposition.confidence,
                proposition.rationale,
                proposition.evidence_keys,
            )
            prior = proposition_payload_by_coordinate.get(coordinate)
            if prior is not None and prior != payload:
                raise GovernedIssueEvidenceValidationError(
                    "One frozen proposition coordinate has inconsistent payloads."
                )
            proposition_payload_by_coordinate[coordinate] = payload

    binding_sort = tuple(
        (
            item.use.issue_definition_id,
            item.use.issue_definition_version,
            item.use.issue_analysis_id,
            item.use.element_ordinal,
            item.use.element_id,
            item.use.evidence_key,
        )
        for item in value.bindings
    )
    if tuple(sorted(binding_sort)) != binding_sort:
        raise GovernedIssueEvidenceValidationError(
            "Bindings must be in deterministic analytical order."
        )

    unmapped_keys = tuple(item.evidence_key for item in value.unmapped_evidence)
    if tuple(sorted(unmapped_keys)) != unmapped_keys:
        raise GovernedIssueEvidenceValidationError(
            "Unmapped U8 evidence must be ordered by evidence_key."
        )
    if len(set(unmapped_keys)) != len(unmapped_keys):
        raise GovernedIssueEvidenceValidationError(
            "Unmapped U8 evidence contains duplicate evidence keys."
        )
    if set(unmapped_keys).intersection(evidence_by_key):
        raise GovernedIssueEvidenceValidationError(
            "An evidence key cannot be both analytically bound and unmapped."
        )

    governed_keys = set(coverage.matched_evidence_keys)
    represented_keys = set(evidence_by_key).union(unmapped_keys)
    if governed_keys != represented_keys:
        raise GovernedIssueEvidenceValidationError(
            "U9B did not preserve the complete governed U8 evidence-key set."
        )


__all__ = [
    "GovernedIssueEvidenceValidationError",
    "validate_governed_issue_evidence_map",
]
