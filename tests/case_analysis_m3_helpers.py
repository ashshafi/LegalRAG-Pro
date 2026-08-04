from __future__ import annotations

from dataclasses import replace
from datetime import date

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result
from legal_analysis.enums import Confidence, EvidenceStatus
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus


def proposition(
    text: str,
    evidence_keys: tuple[str, ...],
    *,
    status: PropositionAssessmentStatus = PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
    confidence: Confidence = Confidence.HIGH,
    rationale: str = "Synthetic chronology proposition.",
) -> AssessedProposition:
    return AssessedProposition(
        text=text,
        status=status,
        confidence=confidence,
        evidence_keys=evidence_keys,
        rationale=rationale,
    )


def dated_evidence(*, key: str, summary: str, source_date: date | None = None, **kwargs):
    value = evidence(key=key, summary=summary, **kwargs)
    return replace(value, date=source_date)


def source_assertion_evidence(*, key: str, summary: str, **kwargs):
    return evidence(
        key=key,
        summary=summary,
        evidence_status=EvidenceStatus.SOURCE_ASSERTION,
        **kwargs,
    )


def inputs(*results):
    frozen = tuple(results)
    foundation = build_case_analysis_foundation(frozen)
    matrices = build_case_matrices(foundation, frozen)
    return foundation, matrices, frozen


__all__ = [
    "dated_evidence",
    "evidence",
    "inputs",
    "make_m5_result",
    "proposition",
    "source_assertion_evidence",
]
