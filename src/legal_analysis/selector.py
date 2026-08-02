"""Deterministic registry-constrained legal issue routing.

Sprint 2.3 Milestone 2 intentionally routes questions only. It performs no
retrieval, evidence assessment, or merits analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .enums import Confidence
from .registry import (
    DEFAULT_ISSUE_DEFINITION_REGISTRY,
    IssueDefinitionRegistry,
)
from .selection import (
    ISSUE_SELECTOR_VERSION,
    IssueSelection,
    IssueSelectionAmbiguity,
    IssueSelectionRole,
    SelectedIssue,
    validate_selection_against_registry,
)


def _normalize_question(question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    if not normalized:
        raise ValueError("user_question must not be empty.")
    return normalized


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


_KNOWLEDGE_PHRASES = (
    "knowledge",
    "aware",
    "awareness",
    "constructive knowledge",
    "notice of my disability",
    "notice of the disability",
)
_KNOWLEDGE_FOCUS_PATTERNS = (
    r"\bwhat\b.{0,50}\b(?:know|knew|aware)\b",
    r"\bdid\b.{0,50}\b(?:know|knew)\b",
    r"\bwas\b.{0,50}\baware\b",
    r"\bwere\b.{0,50}\baware\b",
    r"\bcan\b.{0,50}\bknowledge\b",
)

_ADJUSTMENT_PHRASES = (
    "reasonable adjustment",
    "reasonable adjustments",
    "work from home",
    "working from home",
    "home working",
    "phased return",
    "phase return",
    "changed duties",
    "adjustment",
    "adjustments",
    "accommodate",
    "accommodation",
    "workplace disadvantage",
)
_ADJUSTMENT_FOCUS_PATTERNS = (
    r"\b(?:fail|failed|failure)\b.{0,30}\breasonable adjustments?\b",
    r"\bshould\b.{0,60}\b(?:work from home|home working|adjustment|adjustments|accommodat)",
    r"\b(?:make|made|provide|provided|allow|allowed)\b.{0,35}\badjustments?\b",
)

_DA_PHRASES = (
    "discrimination arising",
    "unfavourable treatment",
    "unfavorable treatment",
    "treated unfavourably",
    "treated unfavorably",
    "something arising from my disability",
    "something arising from disability",
    "something caused by my disability",
    "because of something caused by my disability",
    "absence caused by disability",
    "sickness-related treatment",
)
_DA_FOCUS_PATTERNS = (
    r"\btreated\b.{0,35}\bunfavou?rably\b",
    r"\bunfavou?rable treatment\b",
    r"\bbecause of\b.{0,55}\b(?:arising|caused)\b.{0,30}\bdisabilit",
)

_LIMITATION_PHRASES = (
    "out of time",
    "time limit",
    "limitation",
    "continuing act",
    "continuing failure",
    "continuing omission",
    "conduct extending over a period",
    "just and equitable",
    "still in time",
    "date of claim",
)
_LIMITATION_FOCUS_PATTERNS = (
    r"\b(?:is|was|would)\b.{0,45}\b(?:claim|case)\b.{0,25}\bout of time\b",
    r"\b(?:in time|out of time|time limit|limitation)\b",
    r"\bif\b.{0,50}\b(?:continued|continuing)\b",
)

_BROAD_DISCRIMINATION_PHRASES = (
    "discriminatory",
    "discrimination",
    "unlawful discrimination",
)

_UNSUPPORTED_CONTRACT_PHRASES = (
    "breach my employment contract",
    "breach of contract",
    "contractual claim",
    "contract claim",
)
_UNSUPPORTED_DISMISSAL_PHRASES = (
    "unfair dismissal",
    "unfairly dismissed",
    "wrongful dismissal",
)


@dataclass(frozen=True, slots=True)
class _SignalState:
    knowledge: bool
    adjustment: bool
    discrimination_arising: bool
    limitation: bool
    knowledge_focus: bool
    adjustment_focus: bool
    discrimination_arising_focus: bool
    limitation_focus: bool
    broad_discrimination: bool
    unsupported_contract: bool
    unsupported_dismissal: bool


class DeterministicIssueSelector:
    """Select registered legal issues using transparent deterministic rules."""

    def __init__(
        self,
        registry: IssueDefinitionRegistry = DEFAULT_ISSUE_DEFINITION_REGISTRY,
        *,
        selector_version: str = ISSUE_SELECTOR_VERSION,
    ) -> None:
        self._registry = registry
        self._selector_version = selector_version
        # Fail early if a supplied registry is malformed.
        self._registry.validate()

    @property
    def selector_version(self) -> str:
        return self._selector_version

    def select(self, user_question: str, *, case_id: str | None = None) -> IssueSelection:
        """Route a question to registered issues without analysing its merits."""

        normalized = _normalize_question(user_question)
        signals = self._signals(normalized)

        if signals.unsupported_contract or signals.unsupported_dismissal:
            selection = self._unsupported_selection(
                user_question=user_question,
                normalized=normalized,
                case_id=case_id,
                signals=signals,
            )
            validate_selection_against_registry(selection, self._registry)
            return selection

        if self._is_broad_ambiguous_discrimination(signals):
            selection = self._ambiguous_discrimination_selection(
                user_question=user_question,
                normalized=normalized,
                case_id=case_id,
            )
            validate_selection_against_registry(selection, self._registry)
            return selection

        primary_id = self._choose_primary(signals)
        related_ids = self._choose_related(primary_id, signals)

        if primary_id is None:
            selection = self._unsupported_or_unclear_selection(
                user_question=user_question,
                normalized=normalized,
                case_id=case_id,
            )
            validate_selection_against_registry(selection, self._registry)
            return selection

        primary = self._selected_issue(
            primary_id,
            IssueSelectionRole.PRIMARY,
            self._primary_rationale(primary_id, signals),
            self._primary_confidence(primary_id, signals),
        )
        related = tuple(
            self._selected_issue(
                issue_id,
                IssueSelectionRole.RELATED,
                self._related_rationale(issue_id, primary_id, signals),
                Confidence.MEDIUM,
            )
            for issue_id in related_ids
        )
        used_ids = {primary_id, *related_ids}
        not_selected = self._not_selected(used_ids)
        confidence = primary.confidence
        selection = IssueSelection(
            user_question=user_question,
            normalized_question=normalized,
            case_id=case_id,
            primary_issue=primary,
            related_issues=related,
            not_selected_issues=not_selected,
            ambiguities=(),
            selection_rationale=(
                f"The question is routed primarily to {primary.issue_definition_id}/{primary.issue_definition_version} "
                f"because {primary.selection_rationale[0].lower() + primary.selection_rationale[1:]}"
            ),
            confidence=confidence,
            selector_version=self._selector_version,
        )
        validate_selection_against_registry(selection, self._registry)
        return selection

    def _signals(self, text: str) -> _SignalState:
        knowledge = _contains_any(text, _KNOWLEDGE_PHRASES) or bool(
            re.search(r"\b(?:know|knew|known)\b", text)
        )
        adjustment = _contains_any(text, _ADJUSTMENT_PHRASES)
        discrimination_arising = _contains_any(text, _DA_PHRASES)
        limitation = _contains_any(text, _LIMITATION_PHRASES) or bool(
            re.search(r"\b(?:continued|continuing)\b", text)
            and re.search(r"\b(?:claim|failure|omission|act|time)\b", text)
        )
        return _SignalState(
            knowledge=knowledge,
            adjustment=adjustment,
            discrimination_arising=discrimination_arising,
            limitation=limitation,
            knowledge_focus=_matches_any(text, _KNOWLEDGE_FOCUS_PATTERNS),
            adjustment_focus=_matches_any(text, _ADJUSTMENT_FOCUS_PATTERNS),
            discrimination_arising_focus=_matches_any(text, _DA_FOCUS_PATTERNS),
            limitation_focus=_matches_any(text, _LIMITATION_FOCUS_PATTERNS),
            broad_discrimination=_contains_any(text, _BROAD_DISCRIMINATION_PHRASES),
            unsupported_contract=_contains_any(text, _UNSUPPORTED_CONTRACT_PHRASES),
            unsupported_dismissal=_contains_any(text, _UNSUPPORTED_DISMISSAL_PHRASES),
        )

    @staticmethod
    def _is_broad_ambiguous_discrimination(signals: _SignalState) -> bool:
        return (
            signals.broad_discrimination
            and not signals.adjustment
            and not signals.discrimination_arising
            and not signals.limitation
            and not signals.knowledge_focus
        )

    @staticmethod
    def _choose_primary(signals: _SignalState) -> str | None:
        # Focus-sensitive rules deliberately precede general topic signals.
        if signals.knowledge_focus:
            return "EK-001"
        if signals.adjustment_focus:
            return "RA-001"
        if signals.discrimination_arising_focus:
            return "DA-001"
        if signals.limitation_focus and not signals.adjustment_focus:
            return "LIM-001"

        # Explicit combined reasonable-adjustment + limitation questions use the
        # substantive adjustment issue as primary and limitation as related.
        if signals.adjustment and signals.limitation:
            return "RA-001"
        if signals.discrimination_arising:
            return "DA-001"
        if signals.adjustment:
            return "RA-001"
        if signals.limitation:
            return "LIM-001"
        if signals.knowledge:
            return "EK-001"
        return None

    @staticmethod
    def _choose_related(primary_id: str | None, signals: _SignalState) -> tuple[str, ...]:
        if primary_id is None:
            return ()

        related: list[str] = []
        if primary_id == "EK-001":
            # Knowledge is a controlled component of the reasonable-adjustments
            # definition, so a disability-knowledge question legitimately flags RA.
            related.append("RA-001")
            if signals.discrimination_arising:
                related.append("DA-001")
            if signals.limitation:
                related.append("LIM-001")
        elif primary_id == "RA-001":
            # Knowledge is related where disability/knowledge context is inherent
            # or expressly raised. The user need not say the word "knowledge".
            related.append("EK-001")
            if signals.limitation:
                related.append("LIM-001")
            if signals.discrimination_arising:
                related.append("DA-001")
        elif primary_id == "DA-001":
            related.append("EK-001")
            if signals.limitation:
                related.append("LIM-001")
        elif primary_id == "LIM-001":
            if signals.adjustment:
                related.append("RA-001")
            if signals.knowledge:
                related.append("EK-001")
            if signals.discrimination_arising:
                related.append("DA-001")

        return tuple(dict.fromkeys(item for item in related if item != primary_id))

    def _selected_issue(
        self,
        issue_id: str,
        role: IssueSelectionRole,
        rationale: str,
        confidence: Confidence,
    ) -> SelectedIssue:
        definition = self._registry.get_definition(issue_id)
        return SelectedIssue(
            issue_definition_id=definition.definition_id,
            issue_definition_version=definition.version,
            issue_name=definition.name,
            selection_role=role,
            selection_rationale=rationale,
            confidence=confidence,
        )

    def _not_selected(self, used_ids: set[str]) -> tuple[SelectedIssue, ...]:
        return tuple(
            SelectedIssue(
                issue_definition_id=definition.definition_id,
                issue_definition_version=definition.version,
                issue_name=definition.name,
                selection_role=IssueSelectionRole.NOT_SELECTED,
                selection_rationale=(
                    "The question does not make this registered issue sufficiently central to select it."
                ),
                confidence=Confidence.HIGH,
            )
            for definition in self._registry.list_definitions(active_only=True)
            if definition.definition_id not in used_ids
        )

    @staticmethod
    def _primary_confidence(primary_id: str, signals: _SignalState) -> Confidence:
        focus = {
            "EK-001": signals.knowledge_focus,
            "RA-001": signals.adjustment_focus,
            "DA-001": signals.discrimination_arising_focus,
            "LIM-001": signals.limitation_focus,
        }[primary_id]
        return Confidence.HIGH if focus else Confidence.MEDIUM

    @staticmethod
    def _primary_rationale(primary_id: str, signals: _SignalState) -> str:
        if primary_id == "EK-001":
            return "The question's principal focus is what the employer knew or was aware of about disability-related information."
        if primary_id == "RA-001":
            if signals.limitation:
                return "The question principally asks about an alleged reasonable-adjustments failure, while also raising timing."
            return "The question principally asks whether a workplace adjustment should have been made or considered."
        if primary_id == "DA-001":
            return "The question principally concerns unfavourable treatment because of something arising from disability."
        return "The question principally concerns limitation, time limits, or alleged conduct continuing over time."

    @staticmethod
    def _related_rationale(issue_id: str, primary_id: str, signals: _SignalState) -> str:
        if issue_id == "RA-001":
            return "Reasonable adjustments is related because employer knowledge can be relevant to whether the adjustment duty is engaged."
        if issue_id == "EK-001":
            if primary_id == "DA-001":
                return "Employer knowledge is related because the registered discrimination-arising definition includes a knowledge question."
            return "Employer knowledge is related because the registered reasonable-adjustments definition includes knowledge of disability and relevant disadvantage."
        if issue_id == "LIM-001":
            return "Limitation is related because the question also raises whether the alleged act or failure continued or remains in time."
        return "Discrimination arising from disability is related because the question also refers to unfavourable treatment linked to disability consequences."

    def _unsupported_selection(
        self,
        *,
        user_question: str,
        normalized: str,
        case_id: str | None,
        signals: _SignalState,
    ) -> IssueSelection:
        if signals.unsupported_contract:
            topic = "a contractual issue"
        else:
            topic = "a dismissal issue"
        return IssueSelection(
            user_question=user_question,
            normalized_question=normalized,
            case_id=case_id,
            primary_issue=None,
            related_issues=(),
            not_selected_issues=self._not_selected(set()),
            ambiguities=(),
            selection_rationale=(
                f"The question appears to concern {topic} that is not represented in the current controlled issue-definition registry."
            ),
            confidence=Confidence.HIGH,
            selector_version=self._selector_version,
        )

    def _ambiguous_discrimination_selection(
        self,
        *,
        user_question: str,
        normalized: str,
        case_id: str | None,
    ) -> IssueSelection:
        ambiguity = IssueSelectionAmbiguity(
            description="The discrimination question does not identify the legal mechanism relied upon.",
            candidate_issue_definition_ids=("RA-001", "DA-001"),
            reason=(
                "The wording does not distinguish a failure to make reasonable adjustments from unfavourable treatment arising from disability."
            ),
            materiality=Confidence.HIGH,
        )
        return IssueSelection(
            user_question=user_question,
            normalized_question=normalized,
            case_id=case_id,
            primary_issue=None,
            related_issues=(),
            not_selected_issues=self._not_selected({"RA-001", "DA-001"}),
            ambiguities=(ambiguity,),
            selection_rationale=(
                "The question is too broad to choose between the registered reasonable-adjustments and discrimination-arising definitions without additional legal focus."
            ),
            confidence=Confidence.LOW,
            selector_version=self._selector_version,
        )

    def _unsupported_or_unclear_selection(
        self,
        *,
        user_question: str,
        normalized: str,
        case_id: str | None,
    ) -> IssueSelection:
        return IssueSelection(
            user_question=user_question,
            normalized_question=normalized,
            case_id=case_id,
            primary_issue=None,
            related_issues=(),
            not_selected_issues=self._not_selected(set()),
            ambiguities=(),
            selection_rationale=(
                "No registered issue definition can be selected reliably from the question as written."
            ),
            confidence=Confidence.LOW,
            selector_version=self._selector_version,
        )


DEFAULT_ISSUE_SELECTOR = DeterministicIssueSelector()


def select_issues(
    user_question: str,
    *,
    case_id: str | None = None,
    registry: IssueDefinitionRegistry = DEFAULT_ISSUE_DEFINITION_REGISTRY,
) -> IssueSelection:
    """Convenience wrapper for deterministic registry-constrained routing."""

    selector = (
        DEFAULT_ISSUE_SELECTOR
        if registry is DEFAULT_ISSUE_DEFINITION_REGISTRY
        else DeterministicIssueSelector(registry)
    )
    return selector.select(user_question, case_id=case_id)


__all__ = [
    "DEFAULT_ISSUE_SELECTOR",
    "DeterministicIssueSelector",
    "select_issues",
]
