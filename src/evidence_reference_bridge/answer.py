"""Attach deterministic whole-case reference findings to governed chat answers.

U8F-C2 deliberately leaves the frozen U8F ``legalrag.ask`` implementation and
U8F-C1 resolver unchanged.  The Streamlit chat calls this additive wrapper.
The legal answer is generated first through U8F; reference findings are then
resolved separately against a COMPLETE U8D whole-case search and exposed as
structured UI metadata.  The deterministic findings are never strengthened or
invented by the LLM.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

from evidence_references import (
    CaseEvidenceReferenceResolution,
    EvidenceReferenceResolution,
    EvidenceReferenceResolutionError,
    EvidenceReferenceResolutionReceipt,
    EvidenceReferenceResolutionStatus,
    resolve_evidence_references,
)
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    EvidenceTextMatchMode,
    NegativeFindingScope,
    search_case_evidence,
)
from legalrag import ask as legalrag_ask


AnswerService = Callable[..., dict[str, Any]]
SearchService = Callable[..., CaseEvidenceSearchResult]

_SAFE_WARNING = (
    "Referenced-evidence resolution could not be verified. "
    "No missing-reference finding has been made."
)


def ask_with_reference_findings(
    question: str,
    selected_documents: Sequence[str] | None = None,
    *,
    case_id: str | None = None,
    answer_service: AnswerService = legalrag_ask,
    search_service: SearchService = search_case_evidence,
) -> dict[str, Any]:
    """Run the frozen U8F answer path and add deterministic reference findings."""

    result = answer_service(question, selected_documents, case_id=case_id)
    if case_id is None:
        return result

    mode = result.get("retrieval_mode")
    if mode not in {
        EvidenceSearchMode.DOCUMENT_COMPLETE.value,
        EvidenceSearchMode.EXHAUSTIVE_EVIDENCE.value,
    }:
        return result

    try:
        scope_evidence_keys = _answer_scope_evidence_keys(result)
        exhaustive = search_service(
            case_id=case_id,
            query="",
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
            candidate_document_ids=(),
            text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
        )
        _validate_exhaustive(exhaustive, expected_case_id=case_id)
        whole_case = resolve_evidence_references(exhaustive)
        scoped = _filter_to_answer_scope(whole_case, scope_evidence_keys)
        payload = _payload(scoped)
    except (EvidenceSearchError, EvidenceReferenceResolutionError, TypeError, ValueError) as exc:
        updated = dict(result)
        updated["evidence_reference_resolution"] = None
        updated["evidence_reference_resolution_warning"] = _SAFE_WARNING
        updated["evidence_reference_resolution_error_type"] = type(exc).__name__
        return updated

    updated = dict(result)
    updated["evidence_reference_resolution"] = payload
    updated["evidence_reference_resolution_warning"] = None
    return updated


def _answer_scope_evidence_keys(result: dict[str, Any]) -> tuple[str, ...]:
    search_results = result.get("search_results")
    if not isinstance(search_results, dict):
        raise TypeError("Governed answer search_results must be a dictionary.")
    rows = search_results.get("ids")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list):
        raise TypeError("Governed answer evidence IDs must contain one query row.")
    values = tuple(rows[0])
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("Governed answer evidence IDs must be non-empty strings.")
    if len(set(values)) != len(values):
        raise ValueError("Governed answer evidence IDs must be unique.")
    return values


def _validate_exhaustive(result: CaseEvidenceSearchResult, *, expected_case_id: str) -> None:
    receipt = result.receipt
    if result.case_id != expected_case_id or receipt.case_id != expected_case_id:
        raise EvidenceSearchError("Reference-resolution whole-case search returned the wrong case.")
    if result.search_mode is not EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        raise EvidenceSearchError("Reference-resolution search is not EXHAUSTIVE_EVIDENCE.")
    if receipt.completion is not EvidenceSearchCompletion.COMPLETE:
        raise EvidenceSearchError("Reference-resolution whole-case search is incomplete.")
    if not receipt.case_corpus_complete:
        raise EvidenceSearchError("Reference-resolution whole-case corpus is incomplete.")
    if receipt.negative_finding_scope is not NegativeFindingScope.CASE_CORPUS:
        raise EvidenceSearchError("Reference-resolution coverage lacks CASE_CORPUS authority.")
    if not receipt.negative_finding_permitted:
        raise EvidenceSearchError("Reference-resolution coverage does not permit scoped findings.")


def _filter_to_answer_scope(
    whole_case: CaseEvidenceReferenceResolution,
    scope_evidence_keys: tuple[str, ...],
) -> CaseEvidenceReferenceResolution:
    wanted = set(scope_evidence_keys)
    findings = tuple(
        item
        for item in whole_case.resolutions
        if item.reference.source_evidence_key in wanted
    )
    counts = Counter(item.status for item in findings)
    receipt = whole_case.receipt
    filtered_receipt = EvidenceReferenceResolutionReceipt(
        schema_version=receipt.schema_version,
        case_id=receipt.case_id,
        search_mode=receipt.search_mode,
        searched_document_ids=receipt.searched_document_ids,
        documents_completely_expanded=receipt.documents_completely_expanded,
        pages_inspected=receipt.pages_inspected,
        chunks_inspected=receipt.chunks_inspected,
        case_corpus_complete=receipt.case_corpus_complete,
        possible_not_located_permitted=receipt.possible_not_located_permitted,
        reference_count=len(findings),
        resolved_count=counts[EvidenceReferenceResolutionStatus.RESOLVED],
        ambiguous_count=counts[EvidenceReferenceResolutionStatus.AMBIGUOUS],
        possible_not_located_count=counts[
            EvidenceReferenceResolutionStatus.POSSIBLE_REFERENCED_BUT_NOT_LOCATED
        ],
        unresolved_count=counts[EvidenceReferenceResolutionStatus.UNRESOLVED_REFERENCE],
    )
    return CaseEvidenceReferenceResolution(
        case_id=whole_case.case_id,
        resolutions=findings,
        receipt=filtered_receipt,
    )


def _payload(resolution: CaseEvidenceReferenceResolution) -> dict[str, Any]:
    receipt = resolution.receipt
    return {
        "case_id": resolution.case_id,
        "receipt": {
            "search_mode": receipt.search_mode.value,
            "searched_document_ids": list(receipt.searched_document_ids),
            "documents_completely_expanded": receipt.documents_completely_expanded,
            "pages_inspected": receipt.pages_inspected,
            "chunks_inspected": receipt.chunks_inspected,
            "case_corpus_complete": receipt.case_corpus_complete,
            "possible_not_located_permitted": receipt.possible_not_located_permitted,
            "reference_count": receipt.reference_count,
            "resolved_count": receipt.resolved_count,
            "ambiguous_count": receipt.ambiguous_count,
            "possible_not_located_count": receipt.possible_not_located_count,
            "unresolved_count": receipt.unresolved_count,
        },
        "findings": [_finding_payload(item) for item in resolution.resolutions],
    }


def _finding_payload(item: EvidenceReferenceResolution) -> dict[str, Any]:
    reference = item.reference
    return {
        "reference_id": reference.reference_id,
        "kind": reference.kind.value,
        "reference_text": reference.raw_reference_text,
        "normalized_target": reference.normalized_target,
        "source_document_instance_id": reference.source_document_instance_id,
        "source_filename": reference.source_filename,
        "source_evidence_key": reference.source_evidence_key,
        "source_page_number": reference.source_page_number,
        "source_chunk_ordinal": reference.source_chunk_ordinal,
        "status": item.status.name,
        "matched_document_ids": list(item.matched_document_ids),
        "matched_evidence_keys": list(item.matched_evidence_keys),
        "basis": item.basis,
    }


__all__ = ["ask_with_reference_findings"]
