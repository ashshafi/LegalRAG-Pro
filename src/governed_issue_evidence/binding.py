"""Deterministic U8-to-existing-analysis evidence binding for U9B."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from evidence_search.models import (
    CaseEvidenceSearchResult,
    EvidenceSearchMode,
    EvidenceTextMatchMode,
)

from .models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceRef,
    GovernedEvidenceUse,
    GovernedEvidenceUseBinding,
    GovernedIssueEvidenceMap,
    GovernedPropositionLink,
    GovernedSearchCoverage,
)
from .validation import (
    GovernedIssueEvidenceValidationError,
    validate_governed_issue_evidence_map,
)

if TYPE_CHECKING:
    from case_analysis.m2.matrices import CaseMatrices


class GovernedIssueEvidenceBindingError(ValueError):
    """Raised when governed U8 evidence cannot bind safely to frozen analysis."""


def _value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return _value(value)


def _coverage(search_result: CaseEvidenceSearchResult) -> GovernedSearchCoverage:
    receipt = search_result.receipt
    filters = tuple(str(item) for item in receipt.filters_applied)
    text_match_mode = ""
    for item in filters:
        if item.startswith("text_match="):
            text_match_mode = item.split("=", 1)[1]
            break

    return GovernedSearchCoverage(
        schema_version=str(receipt.schema_version),
        search_mode=_value(receipt.search_mode),
        text_match_mode=text_match_mode,
        query_sha256=str(receipt.query_sha256),
        case_document_count=int(receipt.case_document_count),
        case_page_count=int(receipt.case_page_count),
        case_chunk_count=int(receipt.case_chunk_count),
        scope_document_count=int(receipt.scope_document_count),
        scope_page_count=int(receipt.scope_page_count),
        scope_chunk_count=int(receipt.scope_chunk_count),
        documents_completely_expanded=int(receipt.documents_completely_expanded),
        pages_inspected=int(receipt.pages_inspected),
        chunks_inspected=int(receipt.chunks_inspected),
        candidate_document_ids=tuple(str(item) for item in receipt.candidate_document_ids),
        searched_document_ids=tuple(str(item) for item in receipt.searched_document_ids),
        filters_applied=filters,
        matched_evidence_keys=tuple(str(item) for item in receipt.matched_evidence_keys),
        completion=_value(receipt.completion),
        case_corpus_complete=bool(receipt.case_corpus_complete),
        negative_finding_scope=_value(receipt.negative_finding_scope),
        negative_finding_permitted=bool(receipt.negative_finding_permitted),
    )


def _governed_evidence(
    search_result: CaseEvidenceSearchResult,
) -> dict[str, GovernedEvidenceRef]:
    if search_result.case_id != search_result.receipt.case_id:
        raise GovernedIssueEvidenceBindingError(
            "U8 result case_id does not match its coverage receipt."
        )
    if search_result.search_mode is not EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        raise GovernedIssueEvidenceBindingError(
            "U9B v1 accepts only U8 EXHAUSTIVE_EVIDENCE results."
        )
    if search_result.receipt.search_mode is not EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        raise GovernedIssueEvidenceBindingError(
            "U8 receipt search mode does not match U9B authority."
        )

    coverage = _coverage(search_result)
    if coverage.text_match_mode != EvidenceTextMatchMode.ALL_EVIDENCE.value:
        raise GovernedIssueEvidenceBindingError(
            "U9B v1 requires unfiltered U8 ALL_EVIDENCE authority."
        )
    if coverage.filters_applied != ("text_match=all_evidence",):
        raise GovernedIssueEvidenceBindingError(
            "U9B v1 forbids role/text filtering of governed evidence."
        )
    if coverage.completion != "complete" or not coverage.case_corpus_complete:
        raise GovernedIssueEvidenceBindingError(
            "U9B v1 requires complete U8 case-corpus coverage."
        )

    refs: dict[str, GovernedEvidenceRef] = {}
    role_surface_by_key = {}
    observed_document_ids: list[str] = []
    observed_keys: list[str] = []
    page_count = 0
    chunk_count = 0

    for role_document in search_result.documents:
        document = role_document.document
        if document.case_id != search_result.case_id:
            raise GovernedIssueEvidenceBindingError(
                "U8 document belongs to a different case."
            )
        document_id = str(document.source_document_instance_id)
        if document_id in observed_document_ids:
            raise GovernedIssueEvidenceBindingError(
                "Duplicate source_document_instance_id in U8 result."
            )
        observed_document_ids.append(document_id)

        if len(role_document.pages) != document.page_count:
            raise GovernedIssueEvidenceBindingError(
                "U8 role inspection changed the governed page count."
            )
        if tuple(item.page for item in role_document.pages) != document.pages:
            raise GovernedIssueEvidenceBindingError(
                "U8 role inspection changed or reordered governed pages."
            )

        for role_page in role_document.pages:
            page = role_page.page
            page_count += 1
            source_keys = tuple(chunk.evidence_key for chunk in page.chunks)
            role_keys = tuple(item.chunk.evidence_key for item in role_page.chunks)
            if source_keys != role_keys:
                raise GovernedIssueEvidenceBindingError(
                    "U8 role inspection changed governed chunk ordering or identity."
                )

            for role_chunk in role_page.chunks:
                chunk = role_chunk.chunk
                classification = role_chunk.classification
                chunk_count += 1

                if chunk.page_number != page.page_number:
                    raise GovernedIssueEvidenceBindingError(
                        "U8 chunk/page coordinates are inconsistent."
                    )
                evidence_key = str(chunk.evidence_key)
                if not evidence_key:
                    raise GovernedIssueEvidenceBindingError(
                        "U8 evidence_key must be non-empty."
                    )
                if evidence_key in refs:
                    raise GovernedIssueEvidenceBindingError(
                        "Duplicate evidence_key in governed U8 case corpus."
                    )

                citation = f"{document.original_filename}, p.{chunk.page_number}"
                evidence = GovernedEvidenceRef(
                    evidence_key=evidence_key,
                    source_document_instance_id=document_id,
                    source_snapshot_id=str(document.source_snapshot_id),
                    original_filename=str(document.original_filename),
                    original_blob_sha256=str(document.original_blob_sha256),
                    extraction_profile_id=str(document.extraction_profile_id),
                    chunking_profile_id=str(document.chunking_profile_id),
                    page_number=int(page.page_number),
                    page_text_sha256=str(page.page_text_sha256),
                    extraction_method=_value(page.extraction_method),
                    chunk_ordinal=int(chunk.chunk_ordinal),
                    chunk_id=str(chunk.chunk_id),
                    evidence_binding_id=str(chunk.evidence_binding_id),
                    binding_class=_value(chunk.binding_class),
                    bound_text_role=_value(chunk.bound_text_role),
                    chunk_text_sha256=str(chunk.chunk_text_sha256),
                    chunk_text_byte_length=int(chunk.chunk_text_byte_length),
                    citation=citation,
                    evidence_role=_value(classification.role),
                    role_rule_id=str(classification.rule_id),
                    role_basis=str(classification.basis),
                    source_type=_value(classification.source_type),
                    source_label=str(classification.source_label),
                    provenance_method=str(classification.provenance_method),
                    primary_tier=int(classification.primary_tier),
                    primary_label=str(classification.primary_label),
                )
                refs[evidence_key] = evidence
                role_surface_by_key[evidence_key] = (document_id, str(document.original_filename), chunk, classification)
                observed_keys.append(evidence_key)

    if len(observed_document_ids) != coverage.case_document_count:
        raise GovernedIssueEvidenceBindingError(
            "U8 receipt document count does not match governed documents."
        )
    if page_count != coverage.case_page_count:
        raise GovernedIssueEvidenceBindingError(
            "U8 receipt page count does not match governed pages."
        )
    if chunk_count != coverage.case_chunk_count:
        raise GovernedIssueEvidenceBindingError(
            "U8 receipt chunk count does not match governed chunks."
        )
    if tuple(coverage.searched_document_ids) != tuple(observed_document_ids):
        raise GovernedIssueEvidenceBindingError(
            "U8 searched_document_ids do not match governed document order."
        )
    if tuple(coverage.matched_evidence_keys) != tuple(observed_keys):
        raise GovernedIssueEvidenceBindingError(
            "U8 ALL_EVIDENCE receipt does not preserve every governed chunk in order."
        )

    matches = tuple(search_result.matches)
    if len(matches) != len(observed_keys):
        raise GovernedIssueEvidenceBindingError(
            "U8 ALL_EVIDENCE matches do not cover every governed chunk."
        )
    if tuple(str(item.chunk.evidence_key) for item in matches) != tuple(observed_keys):
        raise GovernedIssueEvidenceBindingError(
            "U8 ALL_EVIDENCE match order differs from the governed surface."
        )
    for match in matches:
        evidence_key = str(match.chunk.evidence_key)
        expected = role_surface_by_key.get(evidence_key)
        if expected is None:
            raise GovernedIssueEvidenceBindingError(
                "U8 match is not present in the governed document surface."
            )
        document_id, filename, chunk, classification = expected
        if (
            str(match.source_document_instance_id) != document_id
            or str(match.original_filename) != filename
            or match.chunk != chunk
            or match.classification != classification
        ):
            raise GovernedIssueEvidenceBindingError(
                "U8 match disagrees with its governed document/role surface."
            )

    return refs


def _proposition_links(use: Any) -> tuple[GovernedPropositionLink, ...]:
    links = []
    seen_indexes: set[int] = set()
    for item in tuple(getattr(use, "proposition_links", ())):
        index = int(item.source_proposition_index)
        if index in seen_indexes:
            raise GovernedIssueEvidenceBindingError(
                "Duplicate source proposition index in frozen EvidenceUse."
            )
        seen_indexes.add(index)
        links.append(
            GovernedPropositionLink(
                source_proposition_index=index,
                text=str(item.text),
                status=_value(item.status),
                confidence=_value(item.confidence),
                rationale=str(item.rationale),
                evidence_keys=tuple(str(key) for key in item.evidence_keys),
            )
        )
    return tuple(sorted(links, key=lambda item: item.source_proposition_index))


def _governed_use(use: Any, *, evidence_key: str) -> GovernedEvidenceUse:
    if str(use.evidence_key) != evidence_key:
        raise GovernedIssueEvidenceBindingError(
            "Frozen EvidenceUse evidence_key does not match its CaseEvidenceRecord."
        )
    return GovernedEvidenceUse(
        issue_analysis_id=str(use.issue_analysis_id),
        issue_definition_id=str(use.issue_definition_id),
        issue_definition_version=str(use.issue_definition_version),
        element_id=str(use.element_id),
        element_ordinal=int(use.element_ordinal),
        evidence_key=evidence_key,
        analytical_role=_value(use.analytical_role),
        mapping_relevance=_value(use.mapping_relevance),
        mapping_confidence=_value(use.mapping_confidence),
        mapping_rationale=str(use.mapping_rationale),
        assessment_confidence=_value(use.assessment_confidence),
        assessment_rationale=str(use.assessment_rationale),
        citation=str(use.citation),
        proposition_links=_proposition_links(use),
    )


def _assert_m2_identity_compatible(record: Any, evidence: GovernedEvidenceRef) -> None:
    chunk_id = _optional_text(getattr(record, "chunk_id", None))
    if chunk_id and chunk_id != evidence.chunk_id:
        raise GovernedIssueEvidenceBindingError(
            "Frozen analytical chunk_id conflicts with governed U8 evidence."
        )

    document_name = _optional_text(getattr(record, "document_name", None))
    if document_name and document_name != evidence.original_filename:
        raise GovernedIssueEvidenceBindingError(
            "Frozen analytical document_name conflicts with governed U8 evidence."
        )

    page = getattr(record, "page", None)
    if page is not None and int(page) != evidence.page_number:
        raise GovernedIssueEvidenceBindingError(
            "Frozen analytical page conflicts with governed U8 evidence."
        )

    citation = _optional_text(getattr(record, "citation", None))
    if citation and citation != evidence.citation:
        raise GovernedIssueEvidenceBindingError(
            "Frozen analytical citation conflicts with governed U8 evidence."
        )

    # M2 document_id is a legacy/optional analytical field. It is not the
    # immutable U8 source_document_instance_id and U9B does not reinterpret it.


def build_governed_issue_evidence_map(
    *,
    search_result: CaseEvidenceSearchResult,
    matrices: "CaseMatrices",
) -> GovernedIssueEvidenceMap:
    """Bind complete governed U8 evidence to exact pre-existing M2 EvidenceUses.

    U9B creates no retrieval, new issue, new element, proposition, or analytical
    role. U8 is the evidential authority; frozen M2 coordinates are the
    analytical-relationship authority.
    """

    if str(matrices.case_id) != search_result.case_id:
        raise GovernedIssueEvidenceBindingError(
            "CaseMatrices and U8 search result belong to different cases."
        )

    governed = _governed_evidence(search_result)
    source_analysis_ids = tuple(str(item) for item in matrices.source_analysis_ids)
    if not source_analysis_ids or len(set(source_analysis_ids)) != len(source_analysis_ids):
        raise GovernedIssueEvidenceBindingError(
            "CaseMatrices source_analysis_ids are empty or duplicated."
        )

    bindings: list[GovernedEvidenceUseBinding] = []
    analytical_keys: set[str] = set()
    use_identities: set[tuple[str, str, str]] = set()
    record_keys: set[str] = set()

    records = tuple(
        sorted(tuple(matrices.evidence_matrix), key=lambda item: str(item.evidence_key))
    )
    for record in records:
        evidence_key = str(record.evidence_key)
        if evidence_key in record_keys:
            raise GovernedIssueEvidenceBindingError(
                "Duplicate CaseEvidenceRecord evidence_key in frozen matrices."
            )
        record_keys.add(evidence_key)

        evidence = governed.get(evidence_key)
        if evidence is None:
            raise GovernedIssueEvidenceBindingError(
                "Frozen analytical evidence is absent from complete governed U8 authority: "
                + evidence_key
            )
        _assert_m2_identity_compatible(record, evidence)

        uses = tuple(record.uses)
        if not uses:
            raise GovernedIssueEvidenceBindingError(
                "CaseEvidenceRecord has no frozen analytical uses."
            )

        for raw_use in uses:
            use = _governed_use(raw_use, evidence_key=evidence_key)
            if use.issue_analysis_id not in source_analysis_ids:
                raise GovernedIssueEvidenceBindingError(
                    "EvidenceUse resolves outside CaseMatrices source_analysis_ids."
                )
            if use.identity in use_identities:
                raise GovernedIssueEvidenceBindingError(
                    "Duplicate frozen EvidenceUse identity encountered."
                )
            use_identities.add(use.identity)
            bindings.append(GovernedEvidenceUseBinding(evidence=evidence, use=use))

        analytical_keys.add(evidence_key)

    bindings.sort(
        key=lambda item: (
            item.use.issue_definition_id,
            item.use.issue_definition_version,
            item.use.issue_analysis_id,
            item.use.element_ordinal,
            item.use.element_id,
            item.use.evidence_key,
        )
    )

    unmapped = tuple(
        governed[key]
        for key in sorted(set(governed).difference(analytical_keys))
    )

    result = GovernedIssueEvidenceMap(
        schema_version=GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
        builder_version=GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
        case_id=search_result.case_id,
        source_synthesis_id=str(matrices.synthesis_id),
        source_matrices_schema_version=str(matrices.schema_version),
        source_matrix_builder_version=str(matrices.matrix_builder_version),
        source_analysis_ids=source_analysis_ids,
        coverage=_coverage(search_result),
        bindings=tuple(bindings),
        unmapped_evidence=unmapped,
    )
    try:
        validate_governed_issue_evidence_map(result)
    except GovernedIssueEvidenceValidationError as exc:
        raise GovernedIssueEvidenceBindingError(str(exc)) from exc
    return result


__all__ = [
    "GovernedIssueEvidenceBindingError",
    "build_governed_issue_evidence_map",
]
