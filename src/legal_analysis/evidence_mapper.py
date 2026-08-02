"""Element-specific evidence mapper for Sprint 2.3 Milestone 3.

The mapper consumes the frozen Sprint 2.2 retriever through a narrow callable
interface.  It does not implement vector search, reranking, provenance, or
source classification itself.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, Protocol

from evidence_classification import EvidenceSourceType
from .enums import (
    AnalysisStatus,
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from .evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from .models import ElementAnalysis, EvidenceReference, IssueAnalysis, IssueDefinition
from .registry import DEFAULT_ISSUE_DEFINITION_REGISTRY, IssueDefinitionRegistry
from .search_profiles import (
    DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY,
    ELEMENT_CANDIDATE_LIMIT,
    ELEMENT_MAPPER_VERSION,
    ELEMENT_RETAIN_LIMIT,
    ElementSearchProfile,
    ElementSearchProfileRegistry,
)
from .selection import IssueSelection, validate_selection_against_registry
from .validation import validate_analysis_against_definition


SEMANTIC_SOURCE_TYPE_KEY = "semantic_source_type"
PROVENANCE_BASIS_KEY = "provenance_basis"
PROVENANCE_CONFIDENCE_KEY = "provenance_confidence"
KNOWLEDGE_SIGNAL_KEY = "knowledge_signal"


class RetrievalCallable(Protocol):
    def __call__(
        self,
        question: str,
        selected_documents: Sequence[str] | None = None,
        n_results: int = 10,
        *,
        case_id: str | None = None,
    ) -> dict[str, Any]: ...


def _default_retrieval_callable(
    question: str,
    selected_documents: Sequence[str] | None = None,
    n_results: int = 10,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    # The bridge lives outside ``legal_analysis`` so the frozen M1 package
    # remains importable without retrieval/OpenAI dependencies.
    adapter = importlib.import_module("legal_analysis_retrieval_adapter")
    return adapter.retrieve_for_legal_analysis(
        question,
        selected_documents,
        n_results=n_results,
        case_id=case_id,
    )


class ElementEvidenceMapper:
    """Map frozen-retriever evidence to elements of one selected primary issue."""

    def __init__(
        self,
        *,
        issue_registry: IssueDefinitionRegistry = DEFAULT_ISSUE_DEFINITION_REGISTRY,
        profile_registry: ElementSearchProfileRegistry = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY,
        retrieval_callable: RetrievalCallable = _default_retrieval_callable,
        mapper_version: str = ELEMENT_MAPPER_VERSION,
        candidate_limit: int = ELEMENT_CANDIDATE_LIMIT,
        retain_limit: int = ELEMENT_RETAIN_LIMIT,
    ) -> None:
        self._issue_registry = issue_registry
        self._profile_registry = profile_registry
        self._retrieval = retrieval_callable
        self._mapper_version = mapper_version
        self._candidate_limit = candidate_limit
        self._retain_limit = retain_limit
        if candidate_limit < 1 or retain_limit < 1:
            raise ValueError("candidate_limit and retain_limit must be positive.")
        if retain_limit > candidate_limit:
            raise ValueError("retain_limit cannot exceed candidate_limit.")
        issue_registry.validate()
        profile_registry.validate()

    @property
    def mapper_version(self) -> str:
        return self._mapper_version

    def map_primary_issue(
        self,
        *,
        case_id: str,
        user_question: str,
        selection: IssueSelection,
        selected_documents: Sequence[str] | None = None,
    ) -> MappedIssueAnalysis:
        """Build a preliminary IssueAnalysis populated only with mapped evidence."""

        case_id = case_id.strip()
        if not case_id:
            raise ValueError("case_id must not be empty.")
        if selection.primary_issue is None:
            raise ValueError("Milestone 3 requires a PRIMARY IssueSelection.")
        if selection.case_id is not None and selection.case_id != case_id:
            raise ValueError("IssueSelection.case_id does not match the requested case_id.")
        if selection.user_question.strip() != user_question.strip():
            raise ValueError("user_question must match the IssueSelection question.")

        validate_selection_against_registry(selection, self._issue_registry)
        primary = selection.primary_issue
        definition = self._issue_registry.get_definition(
            primary.issue_definition_id,
            primary.issue_definition_version,
        )
        profiles = self._profile_registry.profiles_for_definition(definition)

        element_analyses: list[ElementAnalysis] = []
        element_results: list[ElementMappingResult] = []

        for element, profile in zip(definition.elements, profiles, strict=True):
            query = build_element_search_query(
                user_question=user_question,
                definition=definition,
                element_name=element.name,
                profile=profile,
            )
            raw = self._retrieval(
                query,
                selected_documents,
                n_results=self._candidate_limit,
                case_id=case_id,
            )
            candidates = _retrieval_rows(raw)
            mapping_decisions: list[EvidenceMapping] = []
            retained: list[EvidenceReference] = []
            seen_relevant: set[str] = set()

            for candidate in candidates:
                evidence = evidence_reference_from_retrieval(candidate)
                relevance, confidence, rationale = assess_element_relevance(
                    evidence=evidence,
                    raw_text=candidate.text,
                    profile=profile,
                )
                mapping = EvidenceMapping(
                    evidence=evidence,
                    issue_definition_id=definition.definition_id,
                    issue_definition_version=definition.version,
                    element_id=element.element_id,
                    relevance=relevance,
                    mapping_confidence=confidence,
                    mapping_rationale=rationale,
                    mapper_version=self._mapper_version,
                )
                mapping_decisions.append(mapping)
                if relevance is EvidenceRelevance.RELEVANT:
                    key = mapping.evidence_key
                    if key not in seen_relevant and len(retained) < self._retain_limit:
                        seen_relevant.add(key)
                        retained.append(evidence)

            element_analyses.append(
                ElementAnalysis(
                    element_id=element.element_id,
                    element_name=element.name,
                    question_to_determine=element.question_to_determine,
                    # M3 deliberately uses NEUTRAL for relevant evidence because
                    # supporting/adverse evaluation belongs to M4.
                    neutral_evidence=tuple(retained),
                )
            )
            element_results.append(
                ElementMappingResult(
                    element_id=element.element_id,
                    search_query=query,
                    mappings=tuple(mapping_decisions),
                )
            )

        analysis = IssueAnalysis(
            case_id=case_id,
            issue_definition_id=definition.definition_id,
            issue_definition_version=definition.version,
            issue_name=definition.name,
            user_question=user_question,
            legal_framework=definition.legal_framework,
            elements=tuple(element_analyses),
            analysis_status=AnalysisStatus.PRELIMINARY,
        )
        validate_analysis_against_definition(analysis, definition)
        return MappedIssueAnalysis(
            analysis=analysis,
            element_results=tuple(element_results),
            mapper_version=self._mapper_version,
        )


def build_element_search_query(
    *,
    user_question: str,
    definition: IssueDefinition,
    element_name: str,
    profile: ElementSearchProfile,
) -> str:
    """Build a factual evidence-search query without encoding a merits conclusion."""

    return (
        f"User question: {user_question.strip()}\n"
        f"Controlled issue: {definition.name} ({definition.definition_id}/{definition.version})\n"
        f"Element: {element_name} ({profile.element_id})\n"
        f"Evidence search objective: {profile.search_objective}\n"
        "Retrieve factual records relevant to this element. Do not assume the legal element is satisfied."
    )


class _RetrievalRow:
    __slots__ = ("chunk_id", "text", "metadata")

    def __init__(self, chunk_id: str | None, text: str, metadata: dict[str, Any]) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata


def _retrieval_rows(results: dict[str, Any]) -> tuple[_RetrievalRow, ...]:
    documents = _first_row(results.get("documents"))
    metadatas = _first_row(results.get("metadatas"))
    ids = _first_row(results.get("ids"))
    length = min(len(documents), len(metadatas))
    rows: list[_RetrievalRow] = []
    for index in range(length):
        metadata = metadatas[index] if isinstance(metadatas[index], dict) else {}
        chunk_id = None
        if index < len(ids) and ids[index] is not None:
            chunk_id = str(ids[index])
        rows.append(_RetrievalRow(chunk_id, str(documents[index] or ""), dict(metadata)))
    return tuple(rows)


def evidence_reference_from_retrieval(row: _RetrievalRow) -> EvidenceReference:
    """Convert one semantically enriched Sprint 2.2 result into M1 evidence."""

    metadata = row.metadata
    file_name = str(metadata.get("file") or "Unknown document").strip()
    page = _coerce_positive_int(metadata.get("page"))
    source_type = _source_type(
        metadata.get(SEMANTIC_SOURCE_TYPE_KEY)
        or metadata.get("chunk_source_type")
        or metadata.get("evidence_source_type")
    )
    basis = _enum_or_default(
        ProvenanceBasis,
        metadata.get(PROVENANCE_BASIS_KEY),
        ProvenanceBasis.UNKNOWN,
    )
    provenance_confidence = _enum_or_default(
        ProvenanceConfidence,
        metadata.get(PROVENANCE_CONFIDENCE_KEY),
        ProvenanceConfidence.LOW,
    )
    evidence_status = _evidence_status(source_type, metadata)
    citation = str(metadata.get("citation") or _citation(file_name, page)).strip()
    parties = _parties(metadata.get("parties"))
    evidence_date = _parse_date(metadata.get("date"))
    return EvidenceReference(
        document_id=_optional_text(metadata.get("document_id")),
        document_name=file_name,
        page=page,
        chunk_id=row.chunk_id,
        summary=row.text.strip() or "Retrieved evidence excerpt",
        source_type=source_type,
        provenance_type=source_type,
        provenance_basis=basis,
        provenance_confidence=provenance_confidence,
        evidence_status=evidence_status,
        analytical_role=AnalyticalRole.NEUTRAL,
        date=evidence_date,
        author=_optional_text(metadata.get("author")),
        parties=parties,
        citation=citation,
    )


def assess_element_relevance(
    *,
    evidence: EvidenceReference,
    raw_text: str,
    profile: ElementSearchProfile,
) -> tuple[EvidenceRelevance, Confidence, str]:
    """Deterministically assess relevance to one controlled element."""

    haystack = _normalise(
        " ".join(
            part
            for part in (
                evidence.document_name,
                evidence.author or "",
                raw_text,
            )
            if part
        )
    )
    term_hits = tuple(term for term in profile.search_terms if term in haystack)
    phrase_hits = tuple(phrase for phrase in profile.strong_phrases if phrase in haystack)
    required_hits = tuple(item for item in profile.required_any if item in haystack)
    source_hint = evidence.source_type in profile.source_type_hints

    if profile.required_any and not required_hits:
        # A source-type match or one general term can make the candidate worth
        # preserving for inspection, but cannot satisfy a profile with an
        # explicit factual gate (e.g. direct knowledge/causation).
        if source_hint and (term_hits or phrase_hits):
            return (
                EvidenceRelevance.POTENTIALLY_RELEVANT,
                Confidence.LOW,
                "Potentially relevant by source/context, but the profile's required factual signal is absent.",
            )
        return (
            EvidenceRelevance.NOT_RELEVANT,
            Confidence.LOW,
            "The excerpt does not contain the profile's required factual signal.",
        )

    score = len(term_hits) + (3 * len(phrase_hits)) + (1 if source_hint else 0)
    if score >= 5 or (phrase_hits and source_hint):
        signal = phrase_hits[0] if phrase_hits else term_hits[0]
        return (
            EvidenceRelevance.RELEVANT,
            Confidence.HIGH,
            f"Directly matches the element search profile through '{signal}' and corroborating context.",
        )
    if score >= 2:
        signal = phrase_hits[0] if phrase_hits else term_hits[0]
        return (
            EvidenceRelevance.RELEVANT,
            Confidence.MEDIUM,
            f"Matches the element search profile through '{signal}' and related context.",
        )
    if score == 1:
        signal = term_hits[0] if term_hits else "source type"
        return (
            EvidenceRelevance.POTENTIALLY_RELEVANT,
            Confidence.LOW,
            f"Only a limited element-relevance signal was found ({signal}).",
        )
    return (
        EvidenceRelevance.NOT_RELEVANT,
        Confidence.LOW,
        "No controlled element-relevance signal was found in the excerpt.",
    )


def _evidence_status(
    source_type: EvidenceSourceType,
    metadata: dict[str, Any],
) -> EvidenceStatus:
    if str(metadata.get(KNOWLEDGE_SIGNAL_KEY) or "") == "source_assertion":
        return EvidenceStatus.SOURCE_ASSERTION
    if source_type in {
        EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        EvidenceSourceType.CLAIMANT_SUBMISSION,
    }:
        return EvidenceStatus.CLAIMANT_EVIDENCE
    if source_type is EvidenceSourceType.EMPLOYER_RECORD:
        return EvidenceStatus.EMPLOYER_EVIDENCE
    if source_type is EvidenceSourceType.INDEPENDENT_MEDICAL:
        return EvidenceStatus.INDEPENDENT_MEDICAL_EVIDENCE
    if source_type is EvidenceSourceType.OCCUPATIONAL_HEALTH:
        return EvidenceStatus.OCCUPATIONAL_HEALTH_EVIDENCE
    if source_type is EvidenceSourceType.INSURER_RECORD:
        return EvidenceStatus.INSURER_EVIDENCE
    if source_type is EvidenceSourceType.TRIBUNAL_RECORD:
        return EvidenceStatus.TRIBUNAL_RECORD
    if source_type in {
        EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT,
        EvidenceSourceType.RESPONDENT_SUBMISSION,
    }:
        return EvidenceStatus.RESPONDENT_EVIDENCE
    # Mixed/unclassified/secondary material is deliberately conservative: M3
    # records what the source says without upgrading the proposition to fact.
    return EvidenceStatus.SOURCE_ASSERTION


def _source_type(value: Any) -> EvidenceSourceType:
    try:
        return EvidenceSourceType(str(value).strip())
    except ValueError:
        return EvidenceSourceType.OTHER


def _enum_or_default(enum_type: type, value: Any, default: Any) -> Any:
    try:
        return enum_type(str(value).strip())
    except (ValueError, TypeError):
        return default


def _citation(file_name: str, page: int | None) -> str:
    return f"{file_name}, p.{page}" if page is not None else file_name


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _parties(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9:@]+", " ", value.casefold()).split())


def _first_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


__all__ = [
    "ElementEvidenceMapper",
    "RetrievalCallable",
    "assess_element_relevance",
    "build_element_search_query",
    "evidence_reference_from_retrieval",
]
