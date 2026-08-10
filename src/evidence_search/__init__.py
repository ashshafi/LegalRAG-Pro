"""Governed evidence-search orchestration and coverage receipts."""

from .models import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchMatch,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    EvidenceTextMatchMode,
    NegativeFindingScope,
)
from .orchestrator import (
    EvidenceSearchError,
    record_semantic_discovery,
    search_case_evidence,
)

__all__ = [
    "CaseEvidenceSearchResult",
    "EvidenceSearchCompletion",
    "EvidenceSearchError",
    "EvidenceSearchMatch",
    "EvidenceSearchMode",
    "EvidenceSearchReceipt",
    "EvidenceTextMatchMode",
    "NegativeFindingScope",
    "record_semantic_discovery",
    "search_case_evidence",
]
