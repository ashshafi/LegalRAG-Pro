"""Element evidential assessor for Sprint 2.3 Milestone 4.

Consumes immutable M3 mappings and produces a new assessed M1 IssueAnalysis.
No retrieval, search-profile execution or evidence remapping occurs here.
"""

from __future__ import annotations

from dataclasses import replace

from .assessment_rules import (
    apply_corroboration,
    assess_proposition,
    assessment_role,
    detect_conflict,
    evidence_with_role,
    gap_for_element,
)
from .enums import AnalysisStatus, AnalyticalRole, Confidence
from .evidence_assessment import (
    ELEMENT_ASSESSOR_VERSION,
    ElementEvidenceAssessment,
    EvidenceAssessment,
    EvidenceAssessmentResult,
    PropositionAssessmentStatus,
)
from .evidence_mapping import EvidenceRelevance, MappedIssueAnalysis
from .models import ElementAnalysis, IssueAnalysis
from .validation import validate_issue_analysis


class ElementEvidenceAssessor:
    """Deterministically assess the evidential significance of M3 mappings."""

    def __init__(self, *, assessor_version: str = ELEMENT_ASSESSOR_VERSION) -> None:
        version = assessor_version.strip()
        if not version:
            raise ValueError("assessor_version must not be empty.")
        self._assessor_version = version

    @property
    def assessor_version(self) -> str:
        return self._assessor_version

    def assess(self, mapping_result: MappedIssueAnalysis) -> EvidenceAssessmentResult:
        """Assess only M3 RELEVANT mappings and preserve all M3 identity/order."""
        original = mapping_result.analysis
        original_elements = {element.element_id: element for element in original.elements}
        assessed_elements: list[ElementAnalysis] = []
        element_assessments: list[ElementEvidenceAssessment] = []
        any_conflict = False

        for element_result in mapping_result.element_results:
            original_element = original_elements[element_result.element_id]
            initial: list[EvidenceAssessment] = []
            for mapping in element_result.mappings:
                if mapping.relevance is not EvidenceRelevance.RELEVANT:
                    continue
                role, confidence, rationale = assessment_role(mapping)
                initial.append(
                    EvidenceAssessment(
                        mapping=mapping,
                        analytical_role=role,
                        assessment_confidence=confidence,
                        assessment_rationale=rationale,
                    )
                )

            corroborated = apply_corroboration(initial)
            evidence_assessments, dispute = detect_conflict(element_result.element_id, corroborated)
            any_conflict = any_conflict or dispute is not None
            assessed_propositions = tuple(
                assess_proposition(
                    item.mapping,
                    item.analytical_role,
                    element_id=element_result.element_id,
                )
                for item in evidence_assessments
            )
            gap = gap_for_element(element_result.element_id, evidence_assessments)
            gaps = (gap,) if gap is not None else ()
            disputes = (dispute,) if dispute is not None else ()

            established = tuple(
                proposition.text
                for proposition in assessed_propositions
                if proposition.status is PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE
            )
            unresolved = _unresolved_matters(
                element=original_element,
                propositions=assessed_propositions,
                has_dispute=dispute is not None,
                has_gap=gap is not None,
            )
            assessment_confidence = _element_confidence(
                evidence_assessments,
                has_dispute=dispute is not None,
                has_gap=gap is not None,
            )
            rationale = _element_rationale(
                evidence_assessments,
                established_count=len(established),
                has_dispute=dispute is not None,
                has_gap=gap is not None,
            )

            role_buckets = {
                role: tuple(
                    evidence_with_role(item.mapping.evidence, role)
                    for item in evidence_assessments
                    if item.analytical_role is role
                )
                for role in (
                    AnalyticalRole.SUPPORTING,
                    AnalyticalRole.ADVERSE,
                    AnalyticalRole.CORROBORATIVE,
                    AnalyticalRole.NEUTRAL,
                    AnalyticalRole.CONFLICTING,
                )
            }

            assessed_element = ElementAnalysis(
                element_id=original_element.element_id,
                element_name=original_element.element_name,
                question_to_determine=original_element.question_to_determine,
                # M4-local AssessedProposition intentionally does not overload
                # the frozen M1 Proposition model.
                propositions=original_element.propositions,
                supporting_evidence=role_buckets[AnalyticalRole.SUPPORTING],
                adverse_evidence=role_buckets[AnalyticalRole.ADVERSE],
                corroborative_evidence=role_buckets[AnalyticalRole.CORROBORATIVE],
                neutral_evidence=role_buckets[AnalyticalRole.NEUTRAL],
                conflicting_evidence=role_buckets[AnalyticalRole.CONFLICTING],
                disputed_matters=disputes,
                inferences=original_element.inferences,
                evidential_gaps=gaps,
                respondent_position=original_element.respondent_position,
                legal_analysis=None,
                assessment=rationale,
                confidence=assessment_confidence,
            )
            assessed_elements.append(assessed_element)
            element_assessments.append(
                ElementEvidenceAssessment(
                    element_id=original_element.element_id,
                    evidence_assessments=evidence_assessments,
                    assessed_propositions=assessed_propositions,
                    disputed_matters=disputes,
                    evidential_gaps=gaps,
                    presently_established=established,
                    unresolved_matters=unresolved,
                    assessment_confidence=assessment_confidence,
                    assessment_rationale=rationale,
                )
            )

        status = AnalysisStatus.CONFLICTING_EVIDENCE if any_conflict else AnalysisStatus.EVIDENCE_INCOMPLETE
        assessed_analysis = IssueAnalysis(
            case_id=original.case_id,
            issue_definition_id=original.issue_definition_id,
            issue_definition_version=original.issue_definition_version,
            issue_name=original.issue_name,
            user_question=original.user_question,
            legal_framework=original.legal_framework,
            elements=tuple(assessed_elements),
            analysis_status=status,
            issue_analysis_id=original.issue_analysis_id,
            created_at=original.created_at,
            schema_version=original.schema_version,
        )
        validate_issue_analysis(assessed_analysis)
        return EvidenceAssessmentResult(
            mapping_result=mapping_result,
            assessed_analysis=assessed_analysis,
            element_assessments=tuple(element_assessments),
            assessor_version=self._assessor_version,
        )


def _element_confidence(
    assessments: tuple[EvidenceAssessment, ...],
    *,
    has_dispute: bool,
    has_gap: bool,
) -> Confidence:
    if not assessments:
        return Confidence.LOW
    if has_dispute:
        return Confidence.MEDIUM
    high = sum(item.assessment_confidence is Confidence.HIGH for item in assessments)
    medium = sum(item.assessment_confidence is Confidence.MEDIUM for item in assessments)
    if high >= 1 and not has_gap:
        return Confidence.HIGH
    if high >= 1 or medium >= 2:
        return Confidence.MEDIUM
    return Confidence.LOW


def _element_rationale(
    assessments: tuple[EvidenceAssessment, ...],
    *,
    established_count: int,
    has_dispute: bool,
    has_gap: bool,
) -> str:
    if not assessments:
        return "No M3 RELEVANT evidence is currently mapped to this element; M4 makes no substantive inference from that absence."
    roles = {item.analytical_role for item in assessments}
    parts = [f"Assessed {len(assessments)} M3 relevant evidence item(s) without rerunning retrieval or remapping evidence."]
    if established_count:
        parts.append(f"{established_count} source-level documented proposition(s) are established by the current direct record.")
    if AnalyticalRole.CORROBORATIVE in roles:
        parts.append("Independent material provides corroborative context without being treated as conclusive proof.")
    if has_dispute:
        parts.append("Materially conflicting party evidence is preserved as disputed and credibility is not resolved.")
    if has_gap:
        parts.append("A specific material evidential gap remains on this element.")
    return " ".join(parts)


def _unresolved_matters(
    *,
    element: ElementAnalysis,
    propositions: tuple,
    has_dispute: bool,
    has_gap: bool,
) -> tuple[str, ...]:
    unresolved: list[str] = []
    if not propositions:
        unresolved.append(
            f"No current M3 relevant evidence resolves the factual question: {element.question_to_determine}"
        )
    elif any(
        proposition.status in {
            PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
            PropositionAssessmentStatus.UNRESOLVED,
            PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
        }
        for proposition in propositions
    ):
        unresolved.append(
            f"The mapped evidence does not fully resolve: {element.question_to_determine}"
        )
    if has_dispute:
        unresolved.append("A material conflict remains unresolved; M4 does not determine credibility.")
    if has_gap:
        unresolved.append("The identified material evidential gap remains unresolved on the current mapped record.")
    return tuple(dict.fromkeys(unresolved))


def format_assessment_diagnostics(result: EvidenceAssessmentResult) -> str:
    """Return deterministic human-readable M4 acceptance diagnostics."""
    analysis = result.assessed_analysis
    lines = [
        f"Issue: {analysis.issue_definition_id}/{analysis.issue_definition_version} — {analysis.issue_name}",
        f"Mapper: {result.mapping_result.mapper_version}",
        f"Assessor: {result.assessor_version}",
        f"Case: {analysis.case_id}",
        f"Status: {analysis.analysis_status.value}",
        "",
    ]
    by_id = {item.element_id: item for item in analysis.elements}
    for assessment in result.element_assessments:
        element = by_id[assessment.element_id]
        lines.append(f"Element: {element.element_id} — {element.element_name}")
        for role in (
            AnalyticalRole.SUPPORTING,
            AnalyticalRole.ADVERSE,
            AnalyticalRole.CORROBORATIVE,
            AnalyticalRole.NEUTRAL,
            AnalyticalRole.CONFLICTING,
        ):
            items = assessment.by_role(role)
            if not items:
                continue
            lines.append(role.value.upper())
            for item in items:
                ev = item.mapping.evidence
                page = f", p.{ev.page}" if ev.page is not None else ""
                lines.append(f"- [{ev.evidence_status.value}] {ev.document_name}{page}")
                lines.append(f"  Assessment confidence: {item.assessment_confidence.value.upper()}")
                lines.append(f"  Assessment: {item.assessment_rationale}")
        if assessment.presently_established:
            lines.append("PRESENTLY ESTABLISHED (source-level facts)")
            for item in assessment.presently_established:
                lines.append(f"- {item}")
        if assessment.unresolved_matters:
            lines.append("UNRESOLVED")
            for item in assessment.unresolved_matters:
                lines.append(f"- {item}")
        if assessment.evidential_gaps:
            lines.append("EVIDENTIAL GAPS")
            for gap in assessment.evidential_gaps:
                lines.append(f"- {gap.description} [{gap.materiality.value.upper()}]")
                lines.append(f"  Reason: {gap.reason}")
        lines.append(f"Element confidence: {assessment.assessment_confidence.value.upper()}")
        lines.append(f"Rationale: {assessment.assessment_rationale}")
        lines.append("")
    return "\n".join(lines).rstrip()


__all__ = ["ElementEvidenceAssessor", "format_assessment_diagnostics"]
