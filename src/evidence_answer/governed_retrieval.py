"""Governed answer-retrieval bridge for document-complete U8 evidence.

The existing vector retriever remains semantic discovery only.  For case-scoped
answers this module converts its source-bound document identities into complete
U8D document inspection before any evidence is supplied to the answer prompt.
Explicit exhaustive requests bypass semantic candidate selection and inspect the
requested governed scope directly.

A semantic miss is never treated as proof that evidence does not exist.  Search
coverage and negative-finding scope come only from the U8D receipt.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_TIER_KEY,
)
from document_catalog import DocumentCatalogEntry, DocumentCatalogError, list_case_documents
from explicit_document_location import (
    ExplicitDocumentLocationResult,
    merge_explicit_with_semantic_results,
    resolve_explicit_document_location,
)
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    EvidenceTextMatchMode,
    NegativeFindingScope,
    record_semantic_discovery,
    search_case_evidence,
)
from semantic_reasoning import build_semantic_context, build_semantic_legal_prompt


GOVERNED_DISCOVERY_N_RESULTS: Final[int] = 30
EVIDENCE_ROLE_KEY: Final[str] = "u8_evidence_role"
EVIDENCE_ROLE_RULE_KEY: Final[str] = "u8_evidence_role_rule"
EVIDENCE_ROLE_BASIS_KEY: Final[str] = "u8_evidence_role_basis"
GOVERNED_DISCOVERY_RANK_KEY: Final[str] = "u8_semantic_discovery_rank"
GOVERNED_SEARCH_MODE_KEY: Final[str] = "u8_governed_search_mode"

_EXHAUSTIVE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bexhaustiv(?:e|ely)\b", re.IGNORECASE),
    re.compile(r"\b(?:entire|whole|complete)\s+(?:case\s+)?corpus\b", re.IGNORECASE),
    re.compile(r"\ball\s+(?:the\s+)?(?:supporting\s+)?evidence\b", re.IGNORECASE),
    re.compile(r"\bevery\s+(?:indexed\s+)?(?:communication|email|letter|document|record|chunk)\b", re.IGNORECASE),
    re.compile(r"\ball\s+(?:communications|emails|letters|correspondence|documents|records)\b", re.IGNORECASE),
    re.compile(r"\benumerate\s+every\b", re.IGNORECASE),
    re.compile(r"\bsearch\s+(?:the\s+)?(?:entire|whole|complete|full)\b", re.IGNORECASE),
    re.compile(r"\b(?:is|was|there(?:'s| is)?)\s+no\s+evidence\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:supporting\s+)?evidence\b", re.IGNORECASE),
    re.compile(r"\bany\s+(?:supporting\s+)?evidence\b", re.IGNORECASE),
)


class GovernedAnswerEvidenceError(RuntimeError):
    """Raised when answer evidence cannot be proven through the governed U8 path."""


@dataclass(frozen=True, slots=True)
class GovernedAnswerEvidence:
    """Complete answer evidence plus the search receipts that justify its scope."""

    case_id: str
    question: str
    search_mode: EvidenceSearchMode
    semantic_results: dict[str, Any] | None
    semantic_receipt: EvidenceSearchReceipt | None
    search_result: CaseEvidenceSearchResult | None
    answer_results: dict[str, Any]
    explicit_location: ExplicitDocumentLocationResult | None = None


@dataclass(frozen=True, slots=True)
class _SemanticRow:
    """One source-bound semantic discovery row."""

    evidence_key: str
    document_text: str
    metadata: dict[str, Any]
    source_document_instance_id: str
    rank: int


SemanticRetriever = Callable[..., dict[str, Any]]
SearchService = Callable[..., CaseEvidenceSearchResult]
DiscoveryRecorder = Callable[..., EvidenceSearchReceipt]
CatalogService = Callable[..., tuple[DocumentCatalogEntry, ...]]


def prepare_governed_answer_evidence(
    *,
    question: str,
    selected_documents: Sequence[str] | None,
    case_id: str,
    semantic_retriever: SemanticRetriever | None = None,
    search_service: SearchService = search_case_evidence,
    discovery_recorder: DiscoveryRecorder = record_semantic_discovery,
    catalog_service: CatalogService = list_case_documents,
    interactive_semantic_only: bool = False,
) -> GovernedAnswerEvidence:
    """Prepare complete governed evidence for one case-scoped legal answer.

    Normal questions use the existing semantic retriever only to discover
    governed document identities, then completely expand every discovered
    document through U8D.  Explicit exhaustive questions inspect the requested
    governed document scope directly and therefore do not rely on semantic
    top-k candidate selection.

    Args:
        question: Original user question.
        selected_documents: Optional exact filenames selected in the UI.
        case_id: Active governed case UUID.
        semantic_retriever: Existing semantic discovery callable.
        search_service: U8D search boundary.
        discovery_recorder: U8D semantic coverage receipt boundary.
        catalog_service: Governed case document catalog boundary.

    Returns:
        Complete evidence, answer-compatible result rows, and auditable receipts.

    Raises:
        GovernedAnswerEvidenceError: If source-bound discovery or complete
            expansion cannot be reconciled exactly.
    """

    case = _canonical_uuid(case_id, field_name="case_id")
    query = _required_text(question, field_name="question")

    try:
        if _requires_exhaustive_search(query):
            search_result = _run_exhaustive_scope(
                case_id=case,
                question=query,
                selected_documents=selected_documents,
                search_service=search_service,
                catalog_service=catalog_service,
            )
            answer_results = _build_answer_results(search_result, discovery_ranks={})
            return GovernedAnswerEvidence(
                case_id=case,
                question=query,
                search_mode=search_result.search_mode,
                semantic_results=None,
                semantic_receipt=None,
                search_result=search_result,
                answer_results=answer_results,
            )

        retriever_callable = semantic_retriever
        if retriever_callable is None:
            from retriever import retrieve as default_retriever

            semantic_results = default_retriever(
                query,
                selected_documents,
                n_results=GOVERNED_DISCOVERY_N_RESULTS,
                case_id=case,
                expand_search_query=not interactive_semantic_only,
            )
        else:
            semantic_results = retriever_callable(
                query,
                selected_documents,
                n_results=GOVERNED_DISCOVERY_N_RESULTS,
                case_id=case,
            )
        semantic_rows = _parse_semantic_results(semantic_results, expected_case_id=case)

        # Explicit source references are resolved independently of semantic similarity.
        explicit_location = resolve_explicit_document_location(
            question=query,
            case_id=case,
            selected_documents=selected_documents,
            catalog_service=catalog_service,
        )
        if explicit_location is not None:
            # Resolve identity/location here, but let the existing complete U8
            # path construct the canonical governed evidence metadata.
            explicit_document_ids = (
                explicit_location.source_document_instance_id,
            )
        else:
            explicit_document_ids = ()

        candidate_ids = _candidate_document_ids(semantic_rows)
        if explicit_document_ids:
            candidate_ids = tuple(
                dict.fromkeys((*explicit_document_ids, *candidate_ids))
            )
        if not candidate_ids:
            raise GovernedAnswerEvidenceError(
                "Semantic discovery returned no governed source-bound document candidates. "
                "No negative finding is permitted from that partial search."
            )

        semantic_receipt = discovery_recorder(
            case_id=case,
            query=query,
            candidate_document_ids=candidate_ids,
        )
        _validate_semantic_receipt(
            semantic_receipt,
            case_id=case,
            candidate_ids=candidate_ids,
        )

        if interactive_semantic_only:
            if explicit_location is None:
                return GovernedAnswerEvidence(
                    case_id=case,
                    question=query,
                    search_mode=semantic_receipt.search_mode,
                    semantic_results=semantic_results,
                    semantic_receipt=semantic_receipt,
                    search_result=None,
                    answer_results=semantic_results,
                )

        search_result = search_service(
            case_id=case,
            query=query,
            mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
            candidate_document_ids=candidate_ids,
            text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
        )
        _validate_complete_search_result(
            search_result,
            case_id=case,
            expected_candidates=candidate_ids,
        )
        _verify_semantic_rows_belong_to_expanded_documents(semantic_rows, search_result)

        discovery_ranks = _document_discovery_ranks(semantic_rows)
        answer_results = _build_answer_results(search_result, discovery_ranks=discovery_ranks)
        return GovernedAnswerEvidence(
            case_id=case,
            question=query,
            search_mode=search_result.search_mode,
            semantic_results=semantic_results,
            semantic_receipt=semantic_receipt,
            search_result=search_result,
            answer_results=answer_results,
            explicit_location=explicit_location,
        )
    except GovernedAnswerEvidenceError:
        raise
    except (DocumentCatalogError, EvidenceSearchError, TypeError, ValueError) as exc:
        raise GovernedAnswerEvidenceError(
            "Governed answer evidence could not be established completely."
        ) from exc


def build_governed_answer_prompt(
    *,
    question: str,
    evidence: GovernedAnswerEvidence,
    enriched_results: dict[str, Any],
) -> str:
    """Build the legal-answer prompt with U8 role and coverage safeguards."""

    receipt = evidence.search_result.receipt
    _validate_complete_search_result(
        evidence.search_result,
        case_id=evidence.case_id,
        expected_candidates=(
            receipt.searched_document_ids
            if evidence.search_mode is EvidenceSearchMode.DOCUMENT_COMPLETE
            else ()
        ),
    )

    semantic_context = build_semantic_context(enriched_results)
    role_lines = _role_audit_lines(enriched_results)
    coverage = _coverage_text(evidence)
    context = "\n\n".join(
        part for part in (coverage, role_lines, semantic_context) if part.strip()
    )

    negative_rule = _negative_finding_rule(receipt)
    rules = f"""
U8 GOVERNED DOCUMENT-COMPLETE EVIDENCE RULES
The evidence below is not merely the semantic top-k excerpt set. Relevant
case documents were identified through the recorded search mode and every
governed page/chunk in the resulting U8 search scope was inspected before this
answer context was built.

PRIMARY-SOURCE PRIORITY
Treat Evidence role: primary_source as the strongest direct evidential layer
for factual propositions. Commentary, witness summaries, relevance notes,
chronologies, cover/index material and cross-references may explain or point to
evidence, but they must not silently substitute for an available underlying
primary communication or record. Mixed and unclassified material must be
presented cautiously.

DOCUMENT-COMPLETE DISCIPLINE
Do not infer that an omitted semantic hit means evidence is absent. Once a
document is in the governed search scope, consider its complete supplied page
and chunk surface, including primary material that was not itself a semantic
hit.

NEGATIVE-FINDING DISCIPLINE
{negative_rule}
Never write an unqualified statement such as "there is no evidence" unless the
coverage receipt proves the entire governed case corpus was completely searched.
""".strip()

    base_prompt = build_semantic_legal_prompt(question=question, context=context)
    return f"{rules}\n\n{base_prompt}"


def _run_exhaustive_scope(
    *,
    case_id: str,
    question: str,
    selected_documents: Sequence[str] | None,
    search_service: SearchService,
    catalog_service: CatalogService,
) -> CaseEvidenceSearchResult:
    selected = tuple(
        name.strip()
        for name in (selected_documents or ())
        if isinstance(name, str) and name.strip()
    )
    if not selected:
        result = search_service(
            case_id=case_id,
            query=question,
            mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
            text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
        )
        _validate_complete_search_result(result, case_id=case_id, expected_candidates=())
        return result

    catalog = tuple(catalog_service(case_id))
    selected_ids = _selected_document_ids(catalog, selected)
    result = search_service(
        case_id=case_id,
        query=question,
        mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        candidate_document_ids=selected_ids,
        text_match_mode=EvidenceTextMatchMode.ALL_EVIDENCE,
    )
    _validate_complete_search_result(
        result,
        case_id=case_id,
        expected_candidates=selected_ids,
    )
    return result


def _selected_document_ids(
    catalog: tuple[DocumentCatalogEntry, ...],
    selected_documents: tuple[str, ...],
) -> tuple[str, ...]:
    by_name: dict[str, list[DocumentCatalogEntry]] = {}
    for entry in catalog:
        by_name.setdefault(entry.original_filename, []).append(entry)

    requested = set(selected_documents)
    missing = sorted(name for name in requested if name not in by_name)
    if missing:
        raise GovernedAnswerEvidenceError(
            "Selected document scope contains filenames that are not present in the governed catalog."
        )
    if any(len(by_name[name]) != 1 for name in requested):
        raise GovernedAnswerEvidenceError(
            "Selected document scope is ambiguous in the governed catalog."
        )

    return tuple(
        entry.source_document_instance_id
        for entry in catalog
        if entry.original_filename in requested
    )


def _parse_semantic_results(
    results: dict[str, Any],
    *,
    expected_case_id: str,
) -> tuple[_SemanticRow, ...]:
    if not isinstance(results, dict):
        raise GovernedAnswerEvidenceError("Semantic discovery result must be a dictionary.")

    ids = _single_query_row(results.get("ids"), field_name="ids")
    documents = _single_query_row(results.get("documents"), field_name="documents")
    metadatas = _single_query_row(results.get("metadatas"), field_name="metadatas")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise GovernedAnswerEvidenceError(
            "Semantic discovery IDs, documents and metadata counts do not reconcile."
        )

    seen_evidence: set[str] = set()
    rows: list[_SemanticRow] = []
    for rank, (evidence_key, document, metadata) in enumerate(
        zip(ids, documents, metadatas),
        start=1,
    ):
        if not isinstance(evidence_key, str) or not evidence_key:
            raise GovernedAnswerEvidenceError("Semantic discovery returned an invalid evidence key.")
        if evidence_key in seen_evidence:
            raise GovernedAnswerEvidenceError("Semantic discovery returned a duplicate evidence key.")
        seen_evidence.add(evidence_key)
        if not isinstance(document, str):
            raise GovernedAnswerEvidenceError("Semantic discovery returned non-text evidence.")
        if not isinstance(metadata, dict):
            raise GovernedAnswerEvidenceError("Semantic discovery returned invalid metadata.")
        metadata_case = _canonical_uuid(metadata.get("case_id"), field_name="metadata case_id")
        if metadata_case != expected_case_id:
            raise GovernedAnswerEvidenceError(
                "Semantic discovery returned evidence outside the requested case."
            )
        document_id = _canonical_uuid(
            metadata.get("source_document_instance_id"),
            field_name="source_document_instance_id",
        )
        rows.append(
            _SemanticRow(
                evidence_key=evidence_key,
                document_text=document,
                metadata=dict(metadata),
                source_document_instance_id=document_id,
                rank=rank,
            )
        )
    return tuple(rows)


def _candidate_document_ids(rows: tuple[_SemanticRow, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        if row.source_document_instance_id in seen:
            continue
        seen.add(row.source_document_instance_id)
        ordered.append(row.source_document_instance_id)
    return tuple(ordered)


def _validate_semantic_receipt(
    receipt: EvidenceSearchReceipt,
    *,
    case_id: str,
    candidate_ids: tuple[str, ...],
) -> None:
    if receipt.case_id != case_id:
        raise GovernedAnswerEvidenceError("Semantic discovery receipt identifies the wrong case.")
    if receipt.search_mode is not EvidenceSearchMode.SEMANTIC_DISCOVERY:
        raise GovernedAnswerEvidenceError("Semantic discovery receipt has the wrong mode.")
    if receipt.completion is not EvidenceSearchCompletion.PARTIAL:
        raise GovernedAnswerEvidenceError("Semantic discovery receipt must remain PARTIAL.")
    if receipt.negative_finding_permitted:
        raise GovernedAnswerEvidenceError("Semantic discovery cannot permit negative findings.")
    if receipt.negative_finding_scope is not NegativeFindingScope.NONE:
        raise GovernedAnswerEvidenceError("Semantic discovery receipt has an invalid negative scope.")
    if set(receipt.candidate_document_ids) != set(candidate_ids):
        raise GovernedAnswerEvidenceError("Semantic discovery receipt lost candidate documents.")


def _validate_complete_search_result(
    result: CaseEvidenceSearchResult,
    *,
    case_id: str,
    expected_candidates: tuple[str, ...],
) -> None:
    if result.case_id != case_id:
        raise GovernedAnswerEvidenceError("Complete evidence search returned the wrong case.")
    if result.search_mode not in {
        EvidenceSearchMode.DOCUMENT_COMPLETE,
        EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    }:
        raise GovernedAnswerEvidenceError("Answer evidence did not use a complete U8 search mode.")
    receipt = result.receipt
    if receipt.completion is not EvidenceSearchCompletion.COMPLETE:
        raise GovernedAnswerEvidenceError("Answer evidence search is not complete.")
    if not receipt.negative_finding_permitted:
        raise GovernedAnswerEvidenceError("Complete answer evidence search lacks scoped finding authority.")
    if receipt.pages_inspected != receipt.scope_page_count:
        raise GovernedAnswerEvidenceError("Answer evidence did not inspect every scoped page.")
    if receipt.chunks_inspected != receipt.scope_chunk_count:
        raise GovernedAnswerEvidenceError("Answer evidence did not inspect every scoped chunk.")
    if receipt.documents_completely_expanded != receipt.scope_document_count:
        raise GovernedAnswerEvidenceError("Answer evidence did not expand every scoped document.")
    actual_ids = tuple(doc.document.source_document_instance_id for doc in result.documents)
    if actual_ids != receipt.searched_document_ids:
        raise GovernedAnswerEvidenceError("Answer evidence documents do not match the search receipt.")
    if expected_candidates and set(actual_ids) != set(expected_candidates):
        raise GovernedAnswerEvidenceError("Answer evidence lost one or more intended candidate documents.")
    if result.search_mode is EvidenceSearchMode.EXHAUSTIVE_EVIDENCE and not receipt.case_corpus_complete:
        raise GovernedAnswerEvidenceError("Exhaustive answer evidence did not complete the case corpus.")


def _verify_semantic_rows_belong_to_expanded_documents(
    rows: tuple[_SemanticRow, ...],
    search_result: CaseEvidenceSearchResult,
) -> None:
    ownership: dict[str, str] = {}
    for document in search_result.documents:
        document_id = document.document.source_document_instance_id
        for page in document.pages:
            for item in page.chunks:
                evidence_key = item.chunk.evidence_key
                if evidence_key in ownership:
                    raise GovernedAnswerEvidenceError(
                        "Complete evidence surface contains a duplicate evidence identity."
                    )
                ownership[evidence_key] = document_id

    for row in rows:
        actual_document_id = ownership.get(row.evidence_key)
        if actual_document_id is None:
            raise GovernedAnswerEvidenceError(
                "A semantic discovery row is absent from its completely expanded governed document."
            )
        if actual_document_id != row.source_document_instance_id:
            raise GovernedAnswerEvidenceError(
                "Semantic discovery metadata identifies the wrong governed document."
            )


def _document_discovery_ranks(rows: tuple[_SemanticRow, ...]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for row in rows:
        ranks.setdefault(row.source_document_instance_id, row.rank)
    return ranks


def _build_answer_results(
    result: CaseEvidenceSearchResult,
    *,
    discovery_ranks: dict[str, int],
) -> dict[str, Any]:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for document in result.documents:
        value = document.document
        for page in document.pages:
            page_value = page.page
            for item in page.chunks:
                chunk = item.chunk
                classification = item.classification
                ids.append(chunk.evidence_key)
                documents.append(chunk.text)
                metadatas.append(
                    {
                        "case_id": result.case_id,
                        "file": value.original_filename,
                        "page": chunk.page_number,
                        "chunk": chunk.chunk_ordinal,
                        EVIDENCE_SOURCE_TYPE_KEY: document.document_source_type.value,
                        EVIDENCE_SOURCE_LABEL_KEY: document.document_source_label,
                        EVIDENCE_CLASSIFICATION_METHOD_KEY: document.document_source_method,
                        CHUNK_SOURCE_TYPE_KEY: classification.source_type.value,
                        CHUNK_SOURCE_LABEL_KEY: classification.source_label,
                        CHUNK_PROVENANCE_METHOD_KEY: classification.provenance_method,
                        PRIMARY_SOURCE_TIER_KEY: classification.primary_tier,
                        PRIMARY_SOURCE_LABEL_KEY: classification.primary_label,
                        "source_evidence_binding_id": chunk.evidence_binding_id,
                        "source_snapshot_id": value.source_snapshot_id,
                        "source_document_instance_id": value.source_document_instance_id,
                        "source_chunk_sha256": chunk.chunk_text_sha256,
                        "source_page_text_sha256": page_value.page_text_sha256,
                        "source_original_blob_sha256": value.original_blob_sha256,
                        "source_binding_class": chunk.binding_class.value,
                        EVIDENCE_ROLE_KEY: classification.role.value,
                        EVIDENCE_ROLE_RULE_KEY: classification.rule_id,
                        EVIDENCE_ROLE_BASIS_KEY: classification.basis,
                        GOVERNED_DISCOVERY_RANK_KEY: discovery_ranks.get(
                            value.source_document_instance_id
                        ),
                        GOVERNED_SEARCH_MODE_KEY: result.search_mode.value,
                    }
                )

    if len(ids) != result.receipt.scope_chunk_count:
        raise GovernedAnswerEvidenceError(
            "Answer result conversion did not retain every completely inspected chunk."
        )
    if len(set(ids)) != len(ids):
        raise GovernedAnswerEvidenceError("Answer result conversion contains duplicate evidence keys.")

    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
    }


def _role_audit_lines(results: dict[str, Any]) -> str:
    metadatas = _single_query_row(results.get("metadatas"), field_name="metadatas")
    if not metadatas:
        return ""
    lines = ["U8 EVIDENCE ROLE AUDIT"]
    for index, metadata in enumerate(metadatas, start=1):
        if not isinstance(metadata, dict):
            raise GovernedAnswerEvidenceError("Answer metadata is invalid.")
        lines.append(
            "Evidence E{index}: role={role}; role_rule={rule}; role_basis={basis}; "
            "governed_document={document}; semantic_discovery_rank={rank}".format(
                index=index,
                role=metadata.get(EVIDENCE_ROLE_KEY, "unclassified"),
                rule=metadata.get(EVIDENCE_ROLE_RULE_KEY, "unknown"),
                basis=metadata.get(EVIDENCE_ROLE_BASIS_KEY, "unknown"),
                document=metadata.get("source_document_instance_id", "unknown"),
                rank=metadata.get(GOVERNED_DISCOVERY_RANK_KEY, "not-applicable"),
            )
        )
    return "\n".join(lines)


def _coverage_text(evidence: GovernedAnswerEvidence) -> str:
    receipt = evidence.search_result.receipt
    semantic_text = "not used (explicit exhaustive governed search)"
    if evidence.semantic_receipt is not None:
        semantic_text = (
            f"PARTIAL discovery; {len(evidence.semantic_receipt.candidate_document_ids)} "
            "governed candidate document(s); negative finding not permitted at discovery stage"
        )
    return "\n".join(
        (
            "U8 GOVERNED SEARCH COVERAGE",
            f"Semantic discovery: {semantic_text}",
            f"Complete search mode: {receipt.search_mode.value}",
            f"Completion: {receipt.completion.value}",
            "Documents completely expanded: "
            f"{receipt.documents_completely_expanded}/{receipt.scope_document_count}",
            f"Pages inspected: {receipt.pages_inspected}/{receipt.scope_page_count}",
            f"Chunks inspected: {receipt.chunks_inspected}/{receipt.scope_chunk_count}",
            f"Whole governed case corpus complete: {'yes' if receipt.case_corpus_complete else 'no'}",
            f"Negative-finding scope: {receipt.negative_finding_scope.value}",
        )
    )


def _negative_finding_rule(receipt: EvidenceSearchReceipt) -> str:
    if not receipt.negative_finding_permitted:
        return (
            "The search receipt does not permit a negative finding. Do not state or imply that "
            "supporting evidence is absent."
        )
    if receipt.negative_finding_scope is NegativeFindingScope.CASE_CORPUS:
        return (
            "The complete governed case corpus was searched. If the supplied evidence genuinely "
            "does not support a proposition, the permitted formulation is: "
            '"No supporting evidence was identified in the searched case corpus."'
        )
    if receipt.negative_finding_scope is NegativeFindingScope.SEARCHED_SCOPE:
        return (
            "Only the completely expanded searched document scope is covered. Any negative finding "
            "must be limited to: "
            '"No supporting evidence was identified in the completely searched candidate documents." '
            "Do not generalise that statement to the entire case corpus."
        )
    raise GovernedAnswerEvidenceError("Complete receipt has no valid negative-finding scope.")


def _requires_exhaustive_search(question: str) -> bool:
    return any(pattern.search(question) for pattern in _EXHAUSTIVE_PATTERNS)


def _single_query_row(value: Any, *, field_name: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
        raise GovernedAnswerEvidenceError(
            f"{field_name} must contain exactly one query row."
        )
    return value[0]


def _canonical_uuid(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedAnswerEvidenceError(f"{field_name} must be a valid UUID.")
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise GovernedAnswerEvidenceError(f"{field_name} must be a valid UUID.") from exc
    return str(parsed)


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedAnswerEvidenceError(f"{field_name} must not be empty.")
    return value


__all__ = [
    "GOVERNED_DISCOVERY_N_RESULTS",
    "EVIDENCE_ROLE_BASIS_KEY",
    "EVIDENCE_ROLE_KEY",
    "EVIDENCE_ROLE_RULE_KEY",
    "GOVERNED_DISCOVERY_RANK_KEY",
    "GOVERNED_SEARCH_MODE_KEY",
    "GovernedAnswerEvidence",
    "GovernedAnswerEvidenceError",
    "build_governed_answer_prompt",
    "prepare_governed_answer_evidence",
]
