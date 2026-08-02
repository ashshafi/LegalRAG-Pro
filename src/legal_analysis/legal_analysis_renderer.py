"""Deterministic Sprint 2.3 M5 structured legal-analysis renderer.

The renderer consumes an immutable M4 EvidenceAssessmentResult and creates a
new M5 structure.  It performs no retrieval, evidence remapping, role changes,
conflict resolution or gap generation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .definitions import INITIAL_ISSUE_DEFINITIONS
from .enums import AnalyticalRole, Confidence, EvidenceStatus, Materiality
from .evidence_assessment import (
    AssessedProposition,
    ElementEvidenceAssessment,
    EvidenceAssessment,
    EvidenceAssessmentResult,
    PropositionAssessmentStatus,
)
from .evidence_mapping import EvidenceMapping
from .legal_analysis import (
    LEGAL_ANALYSER_VERSION,
    ElementAnalysisStatus,
    ElementLegalAnalysis,
    EvidenceBackedStatement,
    IssueLevelSynthesis,
    StructuredLegalAnalysisResult,
)
from .legal_analysis_rules import (
    analysis_confidence_for,
    assert_profile_coverage,
    profile_for,
    provisional_analysis_for,
    provisional_status_for,
)


class StructuredLegalAnalysisRenderer:
    """Project frozen M4 evidential assessment into structured legal significance."""

    def __init__(self, *, analyser_version: str = LEGAL_ANALYSER_VERSION) -> None:
        version = analyser_version.strip()
        if not version:
            raise ValueError("analyser_version must not be empty.")
        self._analyser_version = version
        expected = {
            (definition.definition_id, definition.version, element.element_id)
            for definition in INITIAL_ISSUE_DEFINITIONS
            for element in definition.elements
        }
        assert_profile_coverage(expected)

    @property
    def analyser_version(self) -> str:
        return self._analyser_version

    def render(self, assessment_result: EvidenceAssessmentResult) -> StructuredLegalAnalysisResult:
        """Render M5 analysis without mutating or recomputing the frozen M4 state."""

        analysis = assessment_result.assessed_analysis
        element_models = {element.element_id: element for element in analysis.elements}
        mapping_by_key = _evidence_mapping_lookup(assessment_result)
        _validate_assessment_alignment(assessment_result)

        element_analyses: list[ElementLegalAnalysis] = []
        for assessment in assessment_result.element_assessments:
            element = element_models[assessment.element_id]
            profile = profile_for(
                analysis.issue_definition_id,
                analysis.issue_definition_version,
                assessment.element_id,
            )
            status = provisional_status_for(assessment)
            confidence = analysis_confidence_for(
                assessment.assessment_confidence,
                status,
            )

            established, supported, not_supported = _proposition_statements(
                assessment.assessed_propositions,
                mapping_by_key,
            )
            source_assertions = _source_assertion_statements(assessment)
            by_role = {
                role: _role_statements(assessment.by_role(role))
                for role in (
                    AnalyticalRole.ADVERSE,
                    AnalyticalRole.CORROBORATIVE,
                    AnalyticalRole.NEUTRAL,
                    AnalyticalRole.CONFLICTING,
                )
            }
            current_position = _current_evidential_position(assessment)
            limitations = _limitations(assessment, profile.key_caveat, source_assertions)
            provisional_analysis = provisional_analysis_for(profile, status)

            element_analyses.append(
                ElementLegalAnalysis(
                    issue_definition_id=analysis.issue_definition_id,
                    issue_definition_version=analysis.issue_definition_version,
                    element_id=assessment.element_id,
                    legal_question=element.question_to_determine,
                    current_evidential_position=current_position,
                    established_matters=established,
                    supported_matters=supported,
                    not_supported_matters=not_supported,
                    source_assertions=source_assertions,
                    adverse_material=by_role[AnalyticalRole.ADVERSE],
                    corroborative_material=by_role[AnalyticalRole.CORROBORATIVE],
                    contextual_material=by_role[AnalyticalRole.NEUTRAL],
                    conflicting_material=by_role[AnalyticalRole.CONFLICTING],
                    disputed_matters=assessment.disputed_matters,
                    legal_significance=profile.legal_relevance,
                    limitations=limitations,
                    unresolved_matters=assessment.unresolved_matters,
                    evidential_gaps=assessment.evidential_gaps,
                    provisional_status=status,
                    provisional_analysis=provisional_analysis,
                    analysis_confidence=confidence,
                    analyser_version=self._analyser_version,
                )
            )

        synthesis = _issue_synthesis(tuple(element_analyses))
        overall_limitations = _overall_limitations(tuple(element_analyses))
        return StructuredLegalAnalysisResult(
            assessment_result=assessment_result,
            element_analyses=tuple(element_analyses),
            issue_synthesis=synthesis,
            overall_limitations=overall_limitations,
            analyser_version=self._analyser_version,
        )


def _validate_assessment_alignment(result: EvidenceAssessmentResult) -> None:
    analysis = result.assessed_analysis
    expected = tuple(element.element_id for element in analysis.elements)
    actual = tuple(item.element_id for item in result.element_assessments)
    if expected != actual:
        raise ValueError("M5 requires exact frozen M4 element order.")
    mapped = result.mapping_result.analysis
    identity_fields = (
        "issue_analysis_id",
        "case_id",
        "issue_definition_id",
        "issue_definition_version",
        "schema_version",
        "created_at",
    )
    for field in identity_fields:
        if getattr(mapped, field) != getattr(analysis, field):
            raise ValueError(f"M5 detected inconsistent frozen analysis identity: {field}.")

    matching = [
        definition
        for definition in INITIAL_ISSUE_DEFINITIONS
        if definition.definition_id == analysis.issue_definition_id
        and definition.version == analysis.issue_definition_version
    ]
    if len(matching) != 1:
        raise ValueError(
            "M5 requires an exact registered issue-definition ID/version and will not improvise legal analysis."
        )
    definition = matching[0]
    defined_ids = tuple(item.element_id for item in definition.elements)
    if expected != defined_ids:
        raise ValueError("M5 requires exact controlled-definition element order and coverage.")
    defined_questions = {item.element_id: item.question_to_determine for item in definition.elements}
    for element in analysis.elements:
        if element.question_to_determine != defined_questions[element.element_id]:
            raise ValueError(
                f"M5 detected a changed controlled legal question for {element.element_id}."
            )


def _evidence_mapping_lookup(result: EvidenceAssessmentResult) -> dict[str, EvidenceMapping]:
    """Return one canonical mapping per stable M3 evidence key.

    M3 deliberately permits the same underlying chunk to be reused across
    several legal elements.  Separate retrieval/mapping occurrences can carry
    harmless differences in non-identity fields (for example summary wording
    or per-occurrence metadata), so M5 must not require full EvidenceReference
    equality.  It may canonicalise duplicate keys only when the durable source
    identity remains compatible; genuinely incompatible identities fail closed.
    """

    lookup: dict[str, EvidenceMapping] = {}
    for element_result in result.mapping_result.element_results:
        for mapping in element_result.mappings:
            key = mapping.evidence_key
            existing = lookup.get(key)
            if existing is not None:
                _assert_compatible_evidence_identity(
                    key,
                    existing,
                    mapping,
                )
                # Keep the first occurrence as the canonical traceability record.
                # M5 only needs stable source/citation identity for evidence-key
                # resolution; element-specific mapping state remains frozen in M3.
                continue
            lookup[key] = mapping
    return lookup


def _assert_compatible_evidence_identity(
    key: str,
    existing: EvidenceMapping,
    candidate: EvidenceMapping,
) -> None:
    """Fail closed when one evidence key points to incompatible source identity."""

    left = existing.evidence
    right = candidate.evidence

    conflicts: list[str] = []
    if left.chunk_id != right.chunk_id:
        conflicts.append("chunk_id")
    if left.document_name != right.document_name:
        conflicts.append("document_name")
    if left.page != right.page:
        conflicts.append("page")
    if left.citation != right.citation:
        conflicts.append("citation")
    if left.document_id and right.document_id and left.document_id != right.document_id:
        conflicts.append("document_id")

    if conflicts:
        fields = ", ".join(conflicts)
        raise ValueError(
            f"Evidence key {key!r} resolves to incompatible stable evidence identity "
            f"({fields})."
        )


def _statement_from_keys(
    text: str,
    evidence_keys: Iterable[str],
    mapping_by_key: dict[str, EvidenceMapping],
) -> EvidenceBackedStatement:
    keys = tuple(dict.fromkeys(evidence_keys))
    if not keys:
        raise ValueError("A material M5 factual proposition is missing M4 evidence keys.")
    citations: list[str] = []
    for key in keys:
        mapping = mapping_by_key.get(key)
        if mapping is None:
            raise ValueError(
                f"M5 cannot resolve M4 evidence key {key!r}; legal analysis fails closed."
            )
        citations.append(mapping.evidence.citation)
    return EvidenceBackedStatement(
        text=text,
        evidence_keys=keys,
        citations=tuple(citations),
    )


def _proposition_statements(
    propositions: tuple[AssessedProposition, ...],
    mapping_by_key: dict[str, EvidenceMapping],
) -> tuple[
    tuple[EvidenceBackedStatement, ...],
    tuple[EvidenceBackedStatement, ...],
    tuple[EvidenceBackedStatement, ...],
]:
    established: list[EvidenceBackedStatement] = []
    supported: list[EvidenceBackedStatement] = []
    not_supported: list[EvidenceBackedStatement] = []
    for proposition in propositions:
        if proposition.status is PropositionAssessmentStatus.UNRESOLVED:
            continue
        statement = _statement_from_keys(
            proposition.text,
            proposition.evidence_keys,
            mapping_by_key,
        )
        if proposition.status is PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE:
            established.append(statement)
        elif proposition.status is PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED:
            supported.append(statement)
        elif proposition.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
            not_supported.append(statement)
        # DISPUTED is represented by M4 DisputedMatter and conflicting material.
    return tuple(established), tuple(supported), tuple(not_supported)


def _role_statements(items: tuple[EvidenceAssessment, ...]) -> tuple[EvidenceBackedStatement, ...]:
    statements: list[EvidenceBackedStatement] = []
    for item in items:
        evidence = item.mapping.evidence
        text = evidence.summary
        if evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION:
            text = f"Source assertion: {text}"
        statements.append(
            EvidenceBackedStatement(
                text=text,
                evidence_keys=(item.mapping.evidence_key,),
                citations=(evidence.citation,),
            )
        )
    return tuple(statements)


def _source_assertion_statements(
    assessment: ElementEvidenceAssessment,
) -> tuple[EvidenceBackedStatement, ...]:
    items = tuple(
        item
        for item in assessment.evidence_assessments
        if item.mapping.evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION
    )
    return _role_statements(items)


def _current_evidential_position(assessment: ElementEvidenceAssessment) -> str:
    counts: defaultdict[str, int] = defaultdict(int)
    for proposition in assessment.assessed_propositions:
        counts[proposition.status.value] += 1
    role_counts: defaultdict[str, int] = defaultdict(int)
    for item in assessment.evidence_assessments:
        role_counts[item.analytical_role.value] += 1
    if not assessment.evidence_assessments:
        return (
            "M4 records no RELEVANT evidence for this element. The absence of mapped evidence is not treated as proof of the contrary proposition."
        )
    parts = [
        f"M4 assessed {len(assessment.evidence_assessments)} relevant evidence item(s)."
    ]
    if counts[PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE.value]:
        parts.append(
            f"{counts[PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE.value]} factual proposition(s) are established by the current evidence."
        )
    if counts[PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED.value]:
        parts.append(
            f"{counts[PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED.value]} proposition(s) are supported but not established."
        )
    if assessment.disputed_matters:
        parts.append(f"{len(assessment.disputed_matters)} material dispute(s) remain unresolved.")
    if role_counts[AnalyticalRole.ADVERSE.value]:
        parts.append(f"{role_counts[AnalyticalRole.ADVERSE.value]} adverse evidence item(s) are preserved.")
    if assessment.evidential_gaps:
        parts.append(f"{len(assessment.evidential_gaps)} material evidential gap(s) remain.")
    return " ".join(parts)


def _limitations(
    assessment: ElementEvidenceAssessment,
    key_caveat: str,
    source_assertions: tuple[EvidenceBackedStatement, ...],
) -> tuple[str, ...]:
    limitations: list[str] = [key_caveat]
    if source_assertions:
        limitations.append(
            "Source assertions establish that the assertion was made; they do not independently establish the truth of the asserted proposition."
        )
    if assessment.disputed_matters:
        limitations.append(
            "A material factual dispute remains and M5 does not resolve credibility or choose between the competing accounts."
        )
    if assessment.evidential_gaps:
        limitations.extend(
            f"Evidential gap: {gap.description}" for gap in assessment.evidential_gaps
        )
    limitations.extend(assessment.unresolved_matters)
    return tuple(dict.fromkeys(item for item in limitations if item.strip()))


def _issue_synthesis(
    elements: tuple[ElementLegalAnalysis, ...],
) -> IssueLevelSynthesis:
    buckets: dict[ElementAnalysisStatus, list[str]] = {
        status: [] for status in ElementAnalysisStatus
    }
    for item in elements:
        buckets[item.provisional_status].append(item.element_id)
    summary = (
        "This synthesis mechanically aggregates provisional element states from the frozen M4 assessment. "
        f"Well-supported factual areas: {len(buckets[ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD])}; "
        f"partially supported: {len(buckets[ElementAnalysisStatus.PARTIALLY_SUPPORTED])}; "
        f"disputed: {len(buckets[ElementAnalysisStatus.DISPUTED])}; "
        f"insufficiently evidenced: {len(buckets[ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED])}; "
        f"unresolved: {len(buckets[ElementAnalysisStatus.UNRESOLVED])}. "
        "The counts are not a merits score and do not determine liability."
    )
    return IssueLevelSynthesis(
        well_supported_elements=tuple(buckets[ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD]),
        partially_supported_elements=tuple(buckets[ElementAnalysisStatus.PARTIALLY_SUPPORTED]),
        disputed_elements=tuple(buckets[ElementAnalysisStatus.DISPUTED]),
        insufficiently_evidenced_elements=tuple(buckets[ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED]),
        unresolved_elements=tuple(buckets[ElementAnalysisStatus.UNRESOLVED]),
        summary=summary,
    )


def _overall_limitations(elements: tuple[ElementLegalAnalysis, ...]) -> tuple[str, ...]:
    limitations: list[str] = []
    for item in elements:
        for gap in item.evidential_gaps:
            if gap.materiality in {Materiality.HIGH, Materiality.MEDIUM}:
                limitations.append(f"{item.element_id}: {gap.description}")
        if item.provisional_status is ElementAnalysisStatus.DISPUTED:
            limitations.append(f"{item.element_id}: a material factual dispute remains unresolved.")
    if not limitations:
        limitations.append(
            "M5 remains a provisional legal-significance layer and does not determine whether any statutory element is satisfied."
        )
    return tuple(dict.fromkeys(limitations))


def format_legal_analysis_diagnostics(result: StructuredLegalAnalysisResult) -> str:
    """Return deterministic human-readable M5 acceptance diagnostics."""

    analysis = result.assessment_result.assessed_analysis
    lines = [
        f"Issue: {analysis.issue_definition_id}/{analysis.issue_definition_version} — {analysis.issue_name}",
        f"Mapper: {result.assessment_result.mapping_result.mapper_version}",
        f"Assessor: {result.assessment_result.assessor_version}",
        f"Analyser: {result.analyser_version}",
        f"Case: {analysis.case_id}",
        "",
    ]
    for item in result.element_analyses:
        lines.extend(
            (
                f"Element: {item.element_id}",
                "LEGAL QUESTION",
                item.legal_question,
                "CURRENT EVIDENTIAL POSITION",
                item.current_evidential_position,
            )
        )
        if item.established_matters:
            lines.append("ESTABLISHED FACTUAL MATTERS")
            for statement in item.established_matters:
                lines.append(f"- {statement.text}")
                lines.append(f"  Citations: {'; '.join(statement.citations)}")
        if item.supported_matters:
            lines.append("SUPPORTED BUT NOT ESTABLISHED")
            for statement in item.supported_matters:
                lines.append(f"- {statement.text}")
                lines.append(f"  Citations: {'; '.join(statement.citations)}")
        if item.source_assertions:
            lines.append("SOURCE ASSERTIONS")
            for statement in item.source_assertions:
                lines.append(f"- {statement.text}")
                lines.append(f"  Citations: {'; '.join(statement.citations)}")
        lines.extend(("LEGAL SIGNIFICANCE", item.legal_significance))
        if item.adverse_material:
            lines.append("COUNTERVAILING / ADVERSE MATERIAL")
            for statement in item.adverse_material:
                lines.append(f"- {statement.text}")
                lines.append(f"  Citations: {'; '.join(statement.citations)}")
        if item.conflicting_material or item.disputed_matters:
            lines.append("DISPUTED / CONFLICTING MATERIAL")
            for dispute in item.disputed_matters:
                lines.append(f"- {dispute.proposition}")
        if item.limitations:
            lines.append("LIMITATIONS")
            lines.extend(f"- {text}" for text in item.limitations)
        if item.unresolved_matters:
            lines.append("UNRESOLVED")
            lines.extend(f"- {text}" for text in item.unresolved_matters)
        if item.evidential_gaps:
            lines.append("EVIDENTIAL GAPS")
            for gap in item.evidential_gaps:
                lines.append(f"- {gap.description} [{gap.materiality.value.upper()}]")
        lines.extend(
            (
                "PROVISIONAL STATUS",
                item.provisional_status.value.upper(),
                "PROVISIONAL ANALYSIS",
                item.provisional_analysis,
                "ANALYSIS CONFIDENCE",
                item.analysis_confidence.value.upper(),
                "",
            )
        )
    lines.extend(("ISSUE-LEVEL SYNTHESIS", result.issue_synthesis.summary))
    if result.overall_limitations:
        lines.append("OVERALL LIMITATIONS")
        lines.extend(f"- {item}" for item in result.overall_limitations)
    return "\n".join(lines).rstrip()


__all__ = [
    "StructuredLegalAnalysisRenderer",
    "format_legal_analysis_diagnostics",
]
