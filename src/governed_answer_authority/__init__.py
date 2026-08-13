"""Read-only runtime integration of active governed analytical authority."""

from .bindings import answer_statement_bindings_payload, validate_answer_statement_bindings
from .context import build_constrained_governed_answer_prompt, build_runtime_authority_context
from .models import (
    AnalyticalAuthorityMode,
    AnswerStatementBinding,
    AuthorityRoutingResult,
    GovernedAnswerAuthorityContextError,
    GovernedAnswerAuthorityError,
    GovernedAnswerBindingError,
    PropositionReference,
    RuntimeAnswerAuthorityContext,
    RuntimeAuthorityElement,
    RuntimeAuthorityEvidenceAssessment,
    RuntimeAuthorityEvidenceUse,
    RuntimeAuthorityProposition,
    ValidatedGovernedAnswer,
)
from .routing import route_question_to_active_authority

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
    "answer_statement_bindings_payload",
    "build_constrained_governed_answer_prompt",
    "build_runtime_authority_context",
    "route_question_to_active_authority",
    "validate_answer_statement_bindings",
]
