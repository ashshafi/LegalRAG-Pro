"""Evidence-centric frozen-state projection for Sprint 2.4 Milestone 2."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from legal_analysis.evidence_assessment import EvidenceAssessment
from legal_analysis.evidence_mapping import EvidenceRelevance
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult
from legal_analysis.models import EvidenceReference

from .evidence_identity import assert_compatible_canonical_evidence
from .matrices import CaseEvidenceRecord, EvidencePropositionLink, EvidenceUse


@dataclass(frozen=True, slots=True)
class _EvidenceOccurrence:
    issue_definition_id: str
    issue_definition_version: str
    issue_analysis_id: str
    element_ordinal: int
    evidence_assessment_ordinal: int
    assessment: EvidenceAssessment
    proposition_links: tuple[EvidencePropositionLink, ...]

    @property
    def evidence_key(self) -> str:
        return self.assessment.mapping.evidence_key

    @property
    def evidence(self) -> EvidenceReference:
        return self.assessment.mapping.evidence

    @property
    def rank(self) -> tuple[str, str, str, int, int]:
        return (
            self.issue_definition_id,
            self.issue_definition_version,
            self.issue_analysis_id,
            self.element_ordinal,
            self.evidence_assessment_ordinal,
        )


def _proposition_links(element_assessment, evidence_key: str) -> tuple[EvidencePropositionLink, ...]:
    links: list[EvidencePropositionLink] = []
    for index, proposition in enumerate(element_assessment.assessed_propositions):
        if evidence_key not in proposition.evidence_keys:
            continue
        links.append(
            EvidencePropositionLink(
                source_proposition_index=index,
                text=proposition.text,
                status=proposition.status,
                confidence=proposition.confidence,
                rationale=proposition.rationale,
                evidence_keys=proposition.evidence_keys,
            )
        )
    return tuple(links)


def _occurrences(results: Iterable[StructuredLegalAnalysisResult]) -> tuple[_EvidenceOccurrence, ...]:
    values: list[_EvidenceOccurrence] = []
    for result in results:
        assessment_result = result.assessment_result
        for element_ordinal, element in enumerate(assessment_result.element_assessments):
            for evidence_ordinal, assessment in enumerate(element.evidence_assessments):
                mapping = assessment.mapping
                if mapping.relevance is not EvidenceRelevance.RELEVANT:
                    raise ValueError(
                        "M4 EvidenceAssessment must reference an M3 RELEVANT mapping; "
                        "M2 will not promote loose M3 candidates into case evidence."
                    )
                values.append(
                    _EvidenceOccurrence(
                        issue_definition_id=result.issue_definition_id,
                        issue_definition_version=result.issue_definition_version,
                        issue_analysis_id=result.issue_analysis_id,
                        element_ordinal=element_ordinal,
                        evidence_assessment_ordinal=evidence_ordinal,
                        assessment=assessment,
                        proposition_links=_proposition_links(element, mapping.evidence_key),
                    )
                )
    return tuple(sorted(values, key=lambda item: item.rank))


def _use_from_occurrence(item: _EvidenceOccurrence) -> EvidenceUse:
    assessment = item.assessment
    mapping = assessment.mapping
    return EvidenceUse(
        issue_analysis_id=item.issue_analysis_id,
        issue_definition_id=item.issue_definition_id,
        issue_definition_version=item.issue_definition_version,
        element_id=mapping.element_id,
        element_ordinal=item.element_ordinal,
        evidence_key=mapping.evidence_key,
        analytical_role=assessment.analytical_role,
        mapping_relevance=mapping.relevance,
        mapping_confidence=mapping.mapping_confidence,
        mapping_rationale=mapping.mapping_rationale,
        assessment_confidence=assessment.assessment_confidence,
        assessment_rationale=assessment.assessment_rationale,
        proposition_links=item.proposition_links,
        citation=mapping.evidence.citation,
    )


def _assert_same_use_state(existing: EvidenceUse, candidate: EvidenceUse) -> None:
    if existing.identity != candidate.identity:
        raise ValueError("EvidenceUse compatibility called for different logical use identities.")
    comparable_fields = (
        "issue_definition_id",
        "issue_definition_version",
        "element_ordinal",
        "analytical_role",
        "mapping_relevance",
        "mapping_confidence",
        "mapping_rationale",
        "assessment_confidence",
        "assessment_rationale",
        "proposition_links",
        "citation",
    )
    conflicts = [
        field_name
        for field_name in comparable_fields
        if getattr(existing, field_name) != getattr(candidate, field_name)
    ]
    if conflicts:
        raise ValueError(
            f"EvidenceUse {existing.identity!r} has incompatible frozen relationship state "
            f"({', '.join(conflicts)})."
        )


def build_evidence_matrix(
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[CaseEvidenceRecord, ...]:
    """Build one canonical evidence record per stable M3 evidence key."""

    by_key: dict[str, list[_EvidenceOccurrence]] = defaultdict(list)
    for occurrence in _occurrences(tuple(results)):
        by_key[occurrence.evidence_key].append(occurrence)

    records: list[CaseEvidenceRecord] = []
    for evidence_key in sorted(by_key):
        occurrences = tuple(sorted(by_key[evidence_key], key=lambda item: item.rank))
        canonical = occurrences[0]
        for occurrence in occurrences[1:]:
            assert_compatible_canonical_evidence(
                evidence_key,
                canonical.evidence,
                occurrence.evidence,
            )

        use_by_identity: dict[tuple[str, str, str], EvidenceUse] = {}
        for occurrence in occurrences:
            use = _use_from_occurrence(occurrence)
            existing = use_by_identity.get(use.identity)
            if existing is None:
                use_by_identity[use.identity] = use
            else:
                _assert_same_use_state(existing, use)

        uses = tuple(
            sorted(
                use_by_identity.values(),
                key=lambda item: (
                    item.issue_definition_id,
                    item.issue_definition_version,
                    item.issue_analysis_id,
                    item.element_ordinal,
                    item.element_id,
                ),
            )
        )
        evidence = canonical.evidence
        records.append(
            CaseEvidenceRecord(
                evidence_key=evidence_key,
                document_id=evidence.document_id,
                document_name=evidence.document_name,
                page=evidence.page,
                chunk_id=evidence.chunk_id,
                citation=evidence.citation,
                source_type=evidence.source_type,
                evidence_status=evidence.evidence_status,
                provenance_type=evidence.provenance_type or evidence.source_type,
                provenance_basis=evidence.provenance_basis,
                provenance_confidence=evidence.provenance_confidence,
                date=evidence.date,
                author=evidence.author,
                parties=evidence.parties,
                uses=uses,
            )
        )
    return tuple(records)


__all__ = ["build_evidence_matrix"]
