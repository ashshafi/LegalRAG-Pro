from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib

import pytest

from evidence_classification import EvidenceSourceType
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_roles.models import (
    DocumentEvidenceRoleInspection,
    EvidenceRole,
    EvidenceRoleChunk,
    EvidenceRoleClassification,
    EvidenceRoleCount,
    EvidenceRolePage,
)
from evidence_search.models import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchMatch,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    NegativeFindingScope,
)
from governed_issue_evidence import build_governed_issue_evidence_map
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOC_ID = "22222222-2222-4222-8222-222222222222"


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _chunk(ordinal: int) -> DocumentEvidenceChunk:
    text = f"Employer record {ordinal}"
    return DocumentEvidenceChunk(
        page_number=1,
        chunk_ordinal=ordinal,
        chunk_id=f"evidence-{ordinal}",
        evidence_key=f"evidence-{ordinal}",
        evidence_binding_id=_digest(f"binding:{ordinal}"),
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        chunk_text_sha256=_digest(f"chunk:{ordinal}:{text}"),
        chunk_text_byte_length=len(text.encode("utf-8")),
        text=text,
    )


CHUNK_1 = _chunk(0)
CHUNK_2 = _chunk(1)

PAGE = DocumentEvidencePage(
    page_number=1,
    extraction_method=ExtractionMethod.PYPDF_TEXT,
    page_text_sha256=_digest("page:1"),
    page_text_byte_length=35,
    text="Employer record 0\nEmployer record 1",
    chunks=(CHUNK_1, CHUNK_2),
)

DOCUMENT = DocumentEvidenceInspection(
    case_id=CASE_ID,
    source_document_instance_id=DOC_ID,
    source_snapshot_id=_digest("snapshot"),
    original_filename="Employer letter.pdf",
    original_blob_sha256=_digest("original"),
    original_byte_length=1234,
    extraction_profile_id="pdf-page-extraction/1.0",
    chunking_profile_id="recursive-character-text-splitter/1.0",
    page_count=1,
    evidence_chunk_count=2,
    pages=(PAGE,),
)


def _classification(role: EvidenceRole) -> EvidenceRoleClassification:
    return EvidenceRoleClassification(
        role=role,
        rule_id="primary.direct_source_type",
        basis="Existing U8 role decision.",
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        source_label="Employer record",
        provenance_method="chunk-leading-sender",
        primary_tier=1,
        primary_label="Primary",
    )


CLASS_1 = _classification(EvidenceRole.PRIMARY_SOURCE)
CLASS_2 = _classification(EvidenceRole.MIXED)

ROLE_PAGE = EvidenceRolePage(
    page=PAGE,
    chunks=(
        EvidenceRoleChunk(chunk=CHUNK_1, classification=CLASS_1),
        EvidenceRoleChunk(chunk=CHUNK_2, classification=CLASS_2),
    ),
)

ROLE_DOCUMENT = DocumentEvidenceRoleInspection(
    document=DOCUMENT,
    document_source_type=EvidenceSourceType.EMPLOYER_RECORD,
    document_source_label="Employer record",
    document_source_method="filename",
    pages=(ROLE_PAGE,),
    role_counts=tuple(
        EvidenceRoleCount(
            role=role,
            count=1 if role in (EvidenceRole.PRIMARY_SOURCE, EvidenceRole.MIXED) else 0,
        )
        for role in EvidenceRole
    ),
)

RECEIPT = EvidenceSearchReceipt(
    schema_version="1.0",
    case_id=CASE_ID,
    search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    query_sha256=_digest("query"),
    case_document_count=1,
    case_page_count=1,
    case_chunk_count=2,
    scope_document_count=1,
    scope_page_count=1,
    scope_chunk_count=2,
    documents_completely_expanded=1,
    pages_inspected=1,
    chunks_inspected=2,
    candidate_document_ids=(),
    searched_document_ids=(DOC_ID,),
    filters_applied=("text_match=all_evidence",),
    matched_evidence_keys=(CHUNK_1.evidence_key, CHUNK_2.evidence_key),
    completion=EvidenceSearchCompletion.COMPLETE,
    case_corpus_complete=True,
    negative_finding_scope=NegativeFindingScope.CASE_CORPUS,
    negative_finding_permitted=True,
)

SEARCH_RESULT = CaseEvidenceSearchResult(
    case_id=CASE_ID,
    query="",
    search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
    documents=(ROLE_DOCUMENT,),
    matches=(
        EvidenceSearchMatch(
            source_document_instance_id=DOC_ID,
            original_filename=DOCUMENT.original_filename,
            chunk=CHUNK_1,
            classification=CLASS_1,
        ),
        EvidenceSearchMatch(
            source_document_instance_id=DOC_ID,
            original_filename=DOCUMENT.original_filename,
            chunk=CHUNK_2,
            classification=CLASS_2,
        ),
    ),
    receipt=RECEIPT,
)


@dataclass(frozen=True)
class FakeProposition:
    source_proposition_index: int
    text: str
    status: str
    confidence: str
    rationale: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class FakeUse:
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    element_ordinal: int
    evidence_key: str
    analytical_role: str
    mapping_relevance: str
    mapping_confidence: str
    mapping_rationale: str
    assessment_confidence: str
    assessment_rationale: str
    citation: str
    proposition_links: tuple[FakeProposition, ...]


@dataclass(frozen=True)
class FakeRecord:
    evidence_key: str
    document_id: str | None
    document_name: str
    page: int
    chunk_id: str
    citation: str
    uses: tuple[FakeUse, ...]


@dataclass(frozen=True)
class FakeMatrices:
    schema_version: str
    case_id: str
    synthesis_id: str
    source_analysis_ids: tuple[str, ...]
    issue_matrix: tuple[object, ...]
    evidence_matrix: tuple[FakeRecord, ...]
    matrix_builder_version: str


USE = FakeUse(
    issue_analysis_id="analysis-1",
    issue_definition_id="EK-001",
    issue_definition_version="1.0",
    element_id="EK-DIRECT-KNOWLEDGE",
    element_ordinal=0,
    evidence_key=CHUNK_1.evidence_key,
    analytical_role="supporting",
    mapping_relevance="relevant",
    mapping_confidence="high",
    mapping_rationale="Existing deterministic mapping.",
    assessment_confidence="medium",
    assessment_rationale="Existing deterministic assessment.",
    citation="Employer letter.pdf, p.1",
    proposition_links=(
        FakeProposition(
            source_proposition_index=0,
            text="The employer received the communication.",
            status="supported_but_not_established",
            confidence="medium",
            rationale="Frozen proposition rationale.",
            evidence_keys=(CHUNK_1.evidence_key,),
        ),
    ),
)

MATRICES = FakeMatrices(
    schema_version="case-matrices-schema/1.0",
    case_id=CASE_ID,
    synthesis_id="synthesis-1",
    source_analysis_ids=("analysis-z", "analysis-1"),
    issue_matrix=(),
    evidence_matrix=(
        FakeRecord(
            evidence_key=CHUNK_1.evidence_key,
            document_id=None,
            document_name=DOCUMENT.original_filename,
            page=1,
            chunk_id=CHUNK_1.chunk_id,
            citation="Employer letter.pdf, p.1",
            uses=(USE,),
        ),
    ),
    matrix_builder_version="case-matrix-builder/1.0",
)


def test_complete_u8_evidence_binds_existing_use_and_retains_unmapped_evidence():
    result = build_governed_issue_evidence_map(
        search_result=SEARCH_RESULT,
        matrices=MATRICES,
    )

    assert result.source_analysis_ids == ("analysis-z", "analysis-1")
    assert len(result.bindings) == 1
    binding = result.bindings[0]

    assert binding.evidence.evidence_key == CHUNK_1.evidence_key
    assert binding.evidence.evidence_role == "primary_source"
    assert binding.evidence.citation == "Employer letter.pdf, p.1"
    assert binding.use.analytical_role == "supporting"
    assert binding.use.identity == (
        "analysis-1",
        "EK-DIRECT-KNOWLEDGE",
        CHUNK_1.evidence_key,
    )

    assert result.unmapped_evidence_keys == (CHUNK_2.evidence_key,)
    assert result.unmapped_evidence[0].evidence_role == "mixed"


def test_caller_document_and_match_order_change_fails_closed_not_reinterpreted():
    reordered = CaseEvidenceSearchResult(
        case_id=SEARCH_RESULT.case_id,
        query=SEARCH_RESULT.query,
        search_mode=SEARCH_RESULT.search_mode,
        documents=SEARCH_RESULT.documents,
        matches=tuple(reversed(SEARCH_RESULT.matches)),
        receipt=SEARCH_RESULT.receipt,
    )

    with pytest.raises(ValueError, match="match order differs"):
        build_governed_issue_evidence_map(
            search_result=reordered,
            matrices=MATRICES,
        )


def test_frozen_analytical_evidence_missing_from_complete_u8_authority_fails_closed():
    missing_use = replace(USE, evidence_key="missing-evidence")
    missing_record = replace(
        MATRICES.evidence_matrix[0],
        evidence_key="missing-evidence",
        chunk_id="missing-evidence",
        uses=(missing_use,),
    )
    matrices = replace(MATRICES, evidence_matrix=(missing_record,))

    with pytest.raises(
        ValueError,
        match="absent from complete governed U8 authority",
    ):
        build_governed_issue_evidence_map(
            search_result=SEARCH_RESULT,
            matrices=matrices,
        )


def test_filtered_exhaustive_authority_fails_closed():
    filtered_receipt = replace(
        RECEIPT,
        filters_applied=("text_match=all_evidence", "roles=primary_source"),
    )
    filtered = replace(SEARCH_RESULT, receipt=filtered_receipt)

    with pytest.raises(ValueError, match="forbids role/text filtering"):
        build_governed_issue_evidence_map(
            search_result=filtered,
            matrices=MATRICES,
        )
