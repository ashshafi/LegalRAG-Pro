"""Governed legal-answer evidence orchestration for U8F.

This package is the narrow bridge between the existing semantic discovery
retriever and the deterministic U8B-U8D governed evidence surface.  It does
not redefine source-evidence storage, evidence-role classification, or legal
analysis semantics.
"""

from .governed_retrieval import (
    GOVERNED_DISCOVERY_N_RESULTS,
    EVIDENCE_ROLE_BASIS_KEY,
    EVIDENCE_ROLE_KEY,
    EVIDENCE_ROLE_RULE_KEY,
    GOVERNED_DISCOVERY_RANK_KEY,
    GOVERNED_SEARCH_MODE_KEY,
    GovernedAnswerEvidence,
    GovernedAnswerEvidenceError,
    build_governed_answer_prompt,
    prepare_governed_answer_evidence,
)

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
