"""Capture-only U8 exhaustive evidence adapter for the frozen analytical mapper.

This module adapts one already-materialised, complete U8 ``CaseEvidenceSearchResult``
into the existing retriever-shaped callable consumed by ``ElementEvidenceMapper``.
It performs no search, ranking, retrieval, publication, activation, or analytical
classification.  Every mapper call receives the same complete U8 evidence population
in the same governed order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_TIER_KEY,
)
from evidence_answer import (
    EVIDENCE_ROLE_BASIS_KEY,
    EVIDENCE_ROLE_KEY,
    EVIDENCE_ROLE_RULE_KEY,
    GOVERNED_DISCOVERY_RANK_KEY,
    GOVERNED_SEARCH_MODE_KEY,
)
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchMode,
    NegativeFindingScope,
)
from evidence_semantics import (
    KNOWLEDGE_SIGNAL_KEY,
    KNOWLEDGE_SIGNAL_LABEL_KEY,
    PROVENANCE_BASIS_KEY,
    PROVENANCE_CONFIDENCE_KEY,
    PROVENANCE_WARNING_KEY,
    SEMANTIC_SOURCE_LABEL_KEY,
    SEMANTIC_SOURCE_TYPE_KEY,
    enrich_evidence_semantics,
)


U8_EXHAUSTIVE_MAPPER_INPUT_POLICY_VERSION = (
    "governed-u8-exhaustive-mapper-input/1.0"
)

_ALL_EVIDENCE_FILTER = "text_match=all_evidence"
_FULL_CHAIN_BOUND = "full_chain_bound"
_CHUNK_TEXT = "chunk_text"


class GovernedAnalyticalCaptureError(RuntimeError):
    """Raised when U8 exhaustive evidence cannot be adapted without weakening scope."""


@dataclass(frozen=True, slots=True)
class _MapperRow:
    evidence_key: str
    text: str
    metadata_items: tuple[tuple[str, Any], ...]

    def metadata(self) -> dict[str, Any]:
        """Return a fresh mutable metadata dictionary for one mapper call."""

        return dict(self.metadata_items)


class U8ExhaustiveMapperInput:
    """Immutable capture policy over one validated U8 exhaustive evidence result.

    The source result is consumed only at construction.  The adapter retains a
    lossless retriever-shaped projection of the U8 rows and returns a fresh copy on
    every call so downstream deterministic semantic enrichment cannot mutate either
    the source result or later calls.
    """

    __slots__ = ("_case_id", "_rows")

    def __init__(self, source: CaseEvidenceSearchResult) -> None:
        try:
            rows = _validate_and_project(source)
        except GovernedAnalyticalCaptureError:
            raise
        except Exception as exc:
            raise GovernedAnalyticalCaptureError(
                "Unable to establish an exact U8 exhaustive mapper-input authority."
            ) from exc

        self._case_id = source.case_id
        self._rows = rows

    @property
    def case_id(self) -> str:
        """Canonical case identifier bound to this capture input."""

        return self._case_id

    @property
    def policy_version(self) -> str:
        """Explicit exhaustive-candidate admission policy version."""

        return U8_EXHAUSTIVE_MAPPER_INPUT_POLICY_VERSION

    @property
    def evidence_count(self) -> int:
        """Number of governed U8 evidence rows exposed to every mapper call."""

        return len(self._rows)

    def retrieve(
        self,
        question: str,
        selected_documents: Sequence[str] | None = None,
        n_results: int = 10,
        *,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the complete U8 corpus in the frozen mapper's callable shape.

        ``question`` and ``n_results`` are accepted only for interface compatibility.
        They never filter, rank, or truncate the governed exhaustive population.
        Document-scoped selection is prohibited because it would weaken the capture
        authority from case-corpus complete to a partial evidence scope.
        """

        del question, n_results

        if selected_documents is not None:
            raise GovernedAnalyticalCaptureError(
                "U8 exhaustive mapper input forbids selected_documents; the full case "
                "corpus must reach the frozen mapper unchanged."
            )
        if case_id is None or _canonical_uuid(case_id, field_name="case_id") != self._case_id:
            raise GovernedAnalyticalCaptureError(
                "Mapper call case_id does not match the U8 exhaustive capture case."
            )

        base = _fresh_result(self._rows)
        original_metadata = tuple(dict(item) for item in base["metadatas"][0])

        try:
            enriched = enrich_evidence_semantics(base)
        except Exception as exc:
            raise GovernedAnalyticalCaptureError(
                "Deterministic evidence-semantic enrichment failed for U8 exhaustive input."
            ) from exc

        _validate_enrichment(enriched, rows=self._rows, original_metadata=original_metadata)
        return enriched


def build_u8_exhaustive_mapper_input(
    source: CaseEvidenceSearchResult,
) -> U8ExhaustiveMapperInput:
    """Build a fail-closed mapper input from one already-created U8 exhaustive result."""

    return U8ExhaustiveMapperInput(source)


def _validate_and_project(source: CaseEvidenceSearchResult) -> tuple[_MapperRow, ...]:
    if not isinstance(source, CaseEvidenceSearchResult):
        raise GovernedAnalyticalCaptureError(
            "Capture input must be a CaseEvidenceSearchResult."
        )

    case_id = _canonical_uuid(source.case_id, field_name="source.case_id")
    if source.case_id != case_id:
        raise GovernedAnalyticalCaptureError("U8 capture case_id is not canonical.")

    receipt = source.receipt
    if receipt.case_id != case_id:
        raise GovernedAnalyticalCaptureError("U8 result and receipt case identities differ.")
    if source.search_mode is not EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        raise GovernedAnalyticalCaptureError("U8 capture source is not EXHAUSTIVE_EVIDENCE.")
    if receipt.search_mode is not EvidenceSearchMode.EXHAUSTIVE_EVIDENCE:
        raise GovernedAnalyticalCaptureError("U8 capture receipt is not EXHAUSTIVE_EVIDENCE.")
    if receipt.completion is not EvidenceSearchCompletion.COMPLETE:
        raise GovernedAnalyticalCaptureError("U8 exhaustive capture receipt is incomplete.")
    if not receipt.case_corpus_complete:
        raise GovernedAnalyticalCaptureError("U8 exhaustive capture does not cover the case corpus.")
    if receipt.negative_finding_scope is not NegativeFindingScope.CASE_CORPUS:
        raise GovernedAnalyticalCaptureError("U8 exhaustive receipt lacks CASE_CORPUS scope.")
    if not receipt.negative_finding_permitted:
        raise GovernedAnalyticalCaptureError("U8 exhaustive receipt does not prove complete coverage.")
    if tuple(receipt.candidate_document_ids):
        raise GovernedAnalyticalCaptureError("U8 exhaustive capture cannot have candidate documents.")
    if tuple(receipt.filters_applied) != (_ALL_EVIDENCE_FILTER,):
        raise GovernedAnalyticalCaptureError(
            "U8 exhaustive capture must use only text_match=all_evidence with no role filter."
        )

    count_pairs = (
        (receipt.scope_document_count, receipt.case_document_count, "document"),
        (receipt.scope_page_count, receipt.case_page_count, "page"),
        (receipt.scope_chunk_count, receipt.case_chunk_count, "chunk"),
        (receipt.documents_completely_expanded, receipt.scope_document_count, "expanded document"),
        (receipt.pages_inspected, receipt.scope_page_count, "inspected page"),
        (receipt.chunks_inspected, receipt.scope_chunk_count, "inspected chunk"),
    )
    for observed, expected, label in count_pairs:
        if observed != expected:
            raise GovernedAnalyticalCaptureError(
                f"U8 exhaustive {label} count does not prove complete case-corpus inspection."
            )

    document_ids: list[str] = []
    projected: list[tuple[_MapperRow, Any, Any, str, str]] = []
    page_count = 0

    for classified_document in source.documents:
        document = classified_document.document
        if document.case_id != case_id:
            raise GovernedAnalyticalCaptureError("U8 document belongs to a different case.")
        document_id = _canonical_uuid(
            document.source_document_instance_id,
            field_name="source_document_instance_id",
        )
        if document.source_document_instance_id != document_id:
            raise GovernedAnalyticalCaptureError("U8 source-document identity is not canonical.")
        if document_id in document_ids:
            raise GovernedAnalyticalCaptureError("U8 exhaustive source contains duplicate documents.")
        document_ids.append(document_id)

        if len(classified_document.pages) != document.page_count:
            raise GovernedAnalyticalCaptureError("U8 classified page count changed the document surface.")
        if tuple(item.page for item in classified_document.pages) != document.pages:
            raise GovernedAnalyticalCaptureError("U8 classified pages changed or reordered the document surface.")

        page_count += len(classified_document.pages)
        chunk_count = 0
        for role_page in classified_document.pages:
            page = role_page.page
            if len(role_page.chunks) != len(page.chunks):
                raise GovernedAnalyticalCaptureError("U8 role classification changed page chunk count.")
            if tuple(item.chunk for item in role_page.chunks) != page.chunks:
                raise GovernedAnalyticalCaptureError("U8 role classification changed or reordered chunks.")

            for role_chunk in role_page.chunks:
                chunk = role_chunk.chunk
                classification = role_chunk.classification
                if getattr(chunk.binding_class, "value", None) != _FULL_CHAIN_BOUND:
                    raise GovernedAnalyticalCaptureError(
                        "U8 analytical capture requires FULL_CHAIN_BOUND evidence."
                    )
                if getattr(chunk.bound_text_role, "value", None) != _CHUNK_TEXT:
                    raise GovernedAnalyticalCaptureError(
                        "U8 analytical capture requires CHUNK_TEXT source binding."
                    )
                if not isinstance(chunk.evidence_key, str) or not chunk.evidence_key:
                    raise GovernedAnalyticalCaptureError("U8 evidence_key must be non-empty text.")
                if not isinstance(chunk.text, str):
                    raise GovernedAnalyticalCaptureError("U8 governed chunk text must be text.")
                if len(chunk.text.encode("utf-8")) != chunk.chunk_text_byte_length:
                    raise GovernedAnalyticalCaptureError(
                        "U8 governed chunk byte length does not match its immutable metadata."
                    )

                metadata = {
                    "case_id": case_id,
                    "file": document.original_filename,
                    "page": chunk.page_number,
                    "chunk": chunk.chunk_ordinal,
                    EVIDENCE_SOURCE_TYPE_KEY: classified_document.document_source_type.value,
                    EVIDENCE_SOURCE_LABEL_KEY: classified_document.document_source_label,
                    EVIDENCE_CLASSIFICATION_METHOD_KEY: classified_document.document_source_method,
                    CHUNK_SOURCE_TYPE_KEY: classification.source_type.value,
                    CHUNK_SOURCE_LABEL_KEY: classification.source_label,
                    CHUNK_PROVENANCE_METHOD_KEY: classification.provenance_method,
                    PRIMARY_SOURCE_TIER_KEY: classification.primary_tier,
                    PRIMARY_SOURCE_LABEL_KEY: classification.primary_label,
                    "source_evidence_binding_id": chunk.evidence_binding_id,
                    "source_snapshot_id": document.source_snapshot_id,
                    "source_document_instance_id": document_id,
                    "source_chunk_sha256": chunk.chunk_text_sha256,
                    "source_page_text_sha256": page.page_text_sha256,
                    "source_original_blob_sha256": document.original_blob_sha256,
                    "source_binding_class": chunk.binding_class.value,
                    EVIDENCE_ROLE_KEY: classification.role.value,
                    EVIDENCE_ROLE_RULE_KEY: classification.rule_id,
                    EVIDENCE_ROLE_BASIS_KEY: classification.basis,
                    GOVERNED_DISCOVERY_RANK_KEY: None,
                    GOVERNED_SEARCH_MODE_KEY: source.search_mode.value,
                }
                row = _MapperRow(
                    evidence_key=chunk.evidence_key,
                    text=chunk.text,
                    metadata_items=tuple(metadata.items()),
                )
                projected.append(
                    (row, chunk, classification, document_id, document.original_filename)
                )
                chunk_count += 1

        if chunk_count != document.evidence_chunk_count:
            raise GovernedAnalyticalCaptureError("U8 document chunk count changed during projection.")

    if len(source.documents) != receipt.scope_document_count:
        raise GovernedAnalyticalCaptureError("U8 exhaustive document tuple does not match receipt.")
    if page_count != receipt.scope_page_count:
        raise GovernedAnalyticalCaptureError("U8 exhaustive page surface does not match receipt.")
    if len(projected) != receipt.scope_chunk_count:
        raise GovernedAnalyticalCaptureError("U8 exhaustive chunk surface does not match receipt.")
    if tuple(document_ids) != tuple(receipt.searched_document_ids):
        raise GovernedAnalyticalCaptureError("U8 exhaustive searched-document order is inconsistent.")

    keys = tuple(item[0].evidence_key for item in projected)
    if len(set(keys)) != len(keys):
        raise GovernedAnalyticalCaptureError("U8 exhaustive evidence keys are not unique.")
    if keys != tuple(receipt.matched_evidence_keys):
        raise GovernedAnalyticalCaptureError(
            "U8 exhaustive matched-evidence receipt does not equal the complete chunk sequence."
        )
    if len(source.matches) != len(projected):
        raise GovernedAnalyticalCaptureError(
            "U8 exhaustive ALL_EVIDENCE result must contain one match for every governed chunk."
        )

    for match, item in zip(source.matches, projected, strict=True):
        _, chunk, classification, document_id, filename = item
        if (
            match.source_document_instance_id != document_id
            or match.original_filename != filename
            or match.chunk != chunk
            or match.classification != classification
        ):
            raise GovernedAnalyticalCaptureError(
                "U8 exhaustive match sequence does not reconcile with the complete document surface."
            )

    return tuple(item[0] for item in projected)


def _fresh_result(rows: tuple[_MapperRow, ...]) -> dict[str, Any]:
    return {
        "ids": [[row.evidence_key for row in rows]],
        "documents": [[row.text for row in rows]],
        "metadatas": [[row.metadata() for row in rows]],
    }


def _validate_enrichment(
    enriched: dict[str, Any],
    *,
    rows: tuple[_MapperRow, ...],
    original_metadata: tuple[dict[str, Any], ...],
) -> None:
    if not isinstance(enriched, dict):
        raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment returned a non-dictionary.")

    expected_ids = [row.evidence_key for row in rows]
    expected_documents = [row.text for row in rows]
    if enriched.get("ids") != [expected_ids]:
        raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment changed U8 evidence identity/order.")
    if enriched.get("documents") != [expected_documents]:
        raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment changed U8 source text/order.")

    metadatas = enriched.get("metadatas")
    if not isinstance(metadatas, list) or len(metadatas) != 1 or not isinstance(metadatas[0], list):
        raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment returned malformed metadata rows.")
    if len(metadatas[0]) != len(rows):
        raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment changed U8 row count.")

    required_semantic_keys = (
        SEMANTIC_SOURCE_TYPE_KEY,
        SEMANTIC_SOURCE_LABEL_KEY,
        PROVENANCE_BASIS_KEY,
        PROVENANCE_CONFIDENCE_KEY,
        PROVENANCE_WARNING_KEY,
        KNOWLEDGE_SIGNAL_KEY,
        KNOWLEDGE_SIGNAL_LABEL_KEY,
    )

    for before, after in zip(original_metadata, metadatas[0], strict=True):
        if not isinstance(after, dict):
            raise GovernedAnalyticalCaptureError("Evidence-semantic enrichment returned non-object metadata.")
        for key, value in before.items():
            if key not in after or after[key] != value:
                raise GovernedAnalyticalCaptureError(
                    f"Evidence-semantic enrichment changed governed U8 metadata field {key!r}."
                )
        for key in required_semantic_keys:
            if key not in after:
                raise GovernedAnalyticalCaptureError(
                    f"Evidence-semantic enrichment omitted required mapper metadata field {key!r}."
                )


def _canonical_uuid(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise GovernedAnalyticalCaptureError(f"{field_name} must be a canonical UUID string.")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise GovernedAnalyticalCaptureError(
            f"{field_name} must be a canonical UUID string."
        ) from exc
    canonical = str(parsed)
    if value != canonical:
        raise GovernedAnalyticalCaptureError(f"{field_name} must use canonical UUID spelling.")
    return canonical


__all__ = [
    "GovernedAnalyticalCaptureError",
    "U8_EXHAUSTIVE_MAPPER_INPUT_POLICY_VERSION",
    "U8ExhaustiveMapperInput",
    "build_u8_exhaustive_mapper_input",
]
