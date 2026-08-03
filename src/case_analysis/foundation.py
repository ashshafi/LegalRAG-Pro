"""Construction service for Sprint 2.4 Milestone 1 case foundations."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from .models import (
    CASE_SYNTHESIS_SCHEMA_VERSION,
    CASE_SYNTHESISER_VERSION,
    CaseAnalysisFoundation,
    derive_synthesis_id,
)
from .validation import validate_source_analysis_results


def build_case_analysis_foundation(
    results: Iterable[StructuredLegalAnalysisResult],
    *,
    created_at: datetime | None = None,
) -> CaseAnalysisFoundation:
    """Build one deterministic foundation from frozen Sprint 2.3 M5 results.

    The default ``created_at`` is derived from the latest immutable source
    analysis creation timestamp.  This keeps equivalent source sets byte-stable
    across input order and rebuilds while keeping ``created_at`` outside the
    synthesis identity calculation.  Callers may supply another timezone-aware
    metadata timestamp when required; doing so does not change ``synthesis_id``.
    """

    references = validate_source_analysis_results(results)
    case_id = references[0].case_id
    source_ids = tuple(item.issue_analysis_id for item in references)
    metadata_created_at = created_at or max(item.issue_created_at for item in references)

    synthesis_id = derive_synthesis_id(
        case_id=case_id,
        source_issue_analysis_ids=source_ids,
        schema_version=CASE_SYNTHESIS_SCHEMA_VERSION,
        synthesiser_version=CASE_SYNTHESISER_VERSION,
    )

    return CaseAnalysisFoundation(
        synthesis_id=synthesis_id,
        case_id=case_id,
        source_analyses=references,
        created_at=metadata_created_at,
        schema_version=CASE_SYNTHESIS_SCHEMA_VERSION,
        synthesiser_version=CASE_SYNTHESISER_VERSION,
    )


__all__ = ["build_case_analysis_foundation"]
