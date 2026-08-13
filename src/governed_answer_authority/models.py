"""Immutable runtime contracts for governed analytical answer restraint."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AnalyticalAuthorityMode(StrEnum):
    """Controlled runtime state for analytical-authority handling."""

    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    APPLIED = "applied"
    INVALID_AUTHORITY = "invalid_authority"
    INVALID_OUTPUT = "invalid_analytical_output"


class GovernedAnswerAuthorityError(RuntimeError):
    """Base error for governed answer-authority integration."""


class GovernedAnswerAuthorityContextError(GovernedAnswerAuthorityError):
    """Raised when frozen authority cannot be projected losslessly."""


class GovernedAnswerBindingError(GovernedAnswerAuthorityError):
    """Raised when generated answer bindings do not validate."""


@dataclass(frozen=True, slots=True)
class PropositionReference:
    """Durable coordinate of one frozen M4 assessed proposition."""

    issue_analysis_id: str
    element_id: str
    source_proposition_index: int


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityProposition:
    """Read-only projection of one frozen assessed proposition."""

    reference: PropositionReference
    text: str
    status: str
    confidence: str
    evidence_keys: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityElement:
    """Read-only projection of one selected issue element."""

    element_id: str
    provisional_status: str
    analysis_confidence: str
    limitations: tuple[str, ...]
    unresolved_matters: tuple[str, ...]
    evidential_gaps_json: tuple[str, ...]
    propositions: tuple[RuntimeAuthorityProposition, ...]


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityEvidenceUse:
    """Lossless canonical U9B payload for one selected EvidenceUse."""

    issue_analysis_id: str
    element_id: str
    evidence_key: str
    payload_json: str


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityEvidenceAssessment:
    """Lossless canonical U9C-B1 payload relevant to the selected issue."""

    evidence_key: str
    payload_json: str


@dataclass(frozen=True, slots=True)
class AuthorityRoutingResult:
    """Selector-only routing resolution into one existing frozen analysis."""

    mode: AnalyticalAuthorityMode
    reason: str
    issue_analysis_id: str | None = None
    issue_definition_id: str | None = None
    issue_definition_version: str | None = None
    issue_name: str | None = None
    selector_version: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAnswerAuthorityContext:
    """Ephemeral immutable answer constraint; never persisted."""

    case_id: str
    authority_id: str
    activation_id: str
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    selector_version: str
    inspected_evidence_keys: tuple[str, ...]
    overall_limitations: tuple[str, ...]
    elements: tuple[RuntimeAuthorityElement, ...]
    evidence_uses: tuple[RuntimeAuthorityEvidenceUse, ...]
    evidence_assessments: tuple[RuntimeAuthorityEvidenceAssessment, ...]


@dataclass(frozen=True, slots=True)
class AnswerStatementBinding:
    """One generated substantive statement bound to frozen analytical coordinates."""

    statement_id: str
    statement_text: str
    source_proposition_refs: tuple[PropositionReference, ...]
    evidence_keys: tuple[str, ...]
    source_status: str


@dataclass(frozen=True, slots=True)
class ValidatedGovernedAnswer:
    """Generated answer whose every substantive statement has validated bindings."""

    answer: str
    bindings: tuple[AnswerStatementBinding, ...]
    relied_evidence_keys: tuple[str, ...]


__all__ = [
    "AnalyticalAuthorityMode",
    "AnswerStatementBinding",
    "AuthorityRoutingResult",
    "GovernedAnswerAuthorityContextError",
    "GovernedAnswerAuthorityError",
    "GovernedAnswerBindingError",
    "PropositionReference",
    "RuntimeAnswerAuthorityContext",
    "RuntimeAuthorityElement",
    "RuntimeAuthorityEvidenceAssessment",
    "RuntimeAuthorityEvidenceUse",
    "RuntimeAuthorityProposition",
    "ValidatedGovernedAnswer",
]
