"""Deterministic M5.1 projection over frozen M1-M4.5 analytical state."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Iterable

from case_analysis.models import CaseAnalysisFoundation
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis.m2.matrices import CaseMatrices, EvidenceUse, IssueElementRecord
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.models import CaseChronology, TemporalExtent
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m4.models import (
    AnalyticalBasis,
    CaseSynthesis,
    DisputedMatterRef,
    ElementRef,
    EvidenceUseRef,
    EventAssertionRef,
    EventRef,
    EvidentialGapRef,
    FindingType,
    IssueRef,
    PropositionRef,
    SynthesisProvenanceRef,
)
from case_analysis.m4.serialization import dumps_case_synthesis
from case_analysis.m4.validation import validate_case_synthesis
from legal_analysis.enums import Confidence, Materiality

from .identity import (
    canonical_json_bytes,
    derive_manifest_id,
    derive_report_projection_id,
    derive_report_statement_id,
    fingerprint_metadata,
    sha256_text,
)
from .models import (
    MANDATORY_SECTION_KEYS,
    REPORT_MANIFEST_BUILDER_VERSION,
    REPORT_MANIFEST_SCHEMA_VERSION,
    REPORT_PROJECTION_SCHEMA_VERSION,
    REPORT_PROJECTOR_VERSION,
    SECTION_KEYS,
    AnalyticalLineageReport,
    CaseHeaderReport,
    CaseReportMetadata,
    CaseReportProjection,
    CitationRecord,
    ConflictReport,
    ElementReport,
    EventAssertionReport,
    EventReport,
    FindingReport,
    GapReport,
    GlossaryEntry,
    IssueReport,
    ManifestSection,
    OverallStateReport,
    PriorityQuestionReport,
    ReportManifest,
    ReportStatement,
    ResolvedProvenance,
    RiskReport,
    StatusView,
    TemporalExtentReport,
)
from .serialization import (
    projection_semantic_payload_from_parts,
    report_manifest_semantic_payload_to_dict,
)

_COUNT_QUALIFICATION = (
    "Counts are inventory only. They are not a merits score, probability estimate, "
    "ranking or recommendation."
)
_MATERIALITY_MEDIUM = (
    "MEDIUM is the neutral classification required by the current durable model where "
    "no comparative materiality signal survives. It is not a comparative statement of "
    "legal importance, seriousness, urgency or predicted impact."
)
_PRIORITY_MEDIUM = (
    "MEDIUM is the neutral M4.4 value used where the frozen analytical state provides "
    "no comparative question ranking. It is not an urgency, ordering or importance recommendation."
)
_CONFIDENCE_EXPLANATION = (
    "Confidence is the frozen analytical confidence ceiling recorded by the engine. "
    "It is not a probability of legal success, a probability that a fact is true, or "
    "a source-credibility score."
)
_RISK_EXPLANATION = (
    "This is a classification of an existing frozen analytical deficiency, not a "
    "predictive litigation-risk score."
)
_IDENTITY_ONLY_GAP = (
    "This provenance retains only the frozen upstream evidential-gap identity and "
    "issue/element coordinate. Discarded semantic detail is not reconstructed."
)
_IDENTITY_ONLY_DISPUTE = (
    "This provenance retains only the frozen upstream disputed-matter identity and "
    "issue/element coordinate. Claimant/respondent sides are not reconstructed."
)

_OVERALL_EXPLANATIONS = {
    "well_developed": "The frozen synthesis classifies every issue position as well supported on the current analytical record. This is an analytical-development state, not a prediction of legal success.",
    "partially_developed": "The frozen synthesis contains partially supported or unresolved issue state and does not classify the whole analytical record as fully developed. This is not a merits score.",
    "evidence_incomplete": "At least one issue is classified as evidence incomplete under the frozen deterministic precedence rules. This does not independently mean the claim is weak.",
    "materially_disputed": "At least one issue is classified as materially disputed in the frozen synthesis. The report does not decide which position is correct.",
}
_ISSUE_EXPLANATIONS = {
    "well_supported": "The issue's frozen element state satisfies the engine's current-record support rule. It is not a finding that the legal claim succeeds.",
    "partially_supported": "The issue contains support but does not satisfy the engine's well-supported condition.",
    "materially_disputed": "Frozen element state includes material dispute. No credibility decision is made.",
    "evidence_incomplete": "Frozen element state includes insufficiently evidenced material.",
    "unresolved": "Frozen element state remains unresolved without a higher-precedence disputed or incomplete classification.",
}
_ELEMENT_EXPLANATIONS = {
    "well_supported_on_current_record": "The element is well supported under the frozen current-record rule. This is not a court finding.",
    "partially_supported": "The element contains support but does not satisfy the frozen well-supported condition.",
    "disputed": "The frozen element state is disputed. The report makes no credibility decision.",
    "insufficiently_evidenced": "The frozen element state remains insufficiently evidenced.",
    "unresolved": "The frozen element state remains unresolved.",
}
_FINDING_EXPLANATIONS = {
    "established_by_frozen_state": "The exact frozen provenance permits the finding to be represented at the established level defined by the engine. This is not a court finding.",
    "supported_by_frozen_state": "The exact frozen provenance supports the finding but does not establish it at the higher level.",
    "disputed_in_frozen_state": "The underlying analytical state remains disputed.",
    "unresolved_in_frozen_state": "The underlying analytical state remains unresolved.",
}
_EVENT_OCCURRENCE_EXPLANATIONS = {
    "established": "The frozen chronology records occurrence at the established level. This remains distinct from timing status.",
    "supported": "The frozen chronology supports occurrence but does not establish it at the higher level.",
    "disputed": "The occurrence remains disputed in the frozen chronology.",
    "unresolved": "The occurrence remains unresolved in the frozen chronology.",
}
_TIMING_EXPLANATIONS = {
    "established": "The timing is established under the frozen chronology rules. This does not upgrade occurrence status.",
    "supported": "The timing is supported but not established at the higher level.",
    "disputed": "The timing remains disputed.",
    "unknown": "The frozen chronology does not establish a canonical time for this item.",
}
_M45_EXPLANATIONS = {
    AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS.value: "The element contains more than one distinct frozen supporting proposition family. This represents proposition breadth, not source multiplicity.",
    AnalyticalBasis.CORROBORATED_EVIDENCE.value: "One exact frozen proposition family is represented through more than one distinct canonical evidence key. This represents source multiplicity for one proposition family and does not establish truth or credibility.",
    AnalyticalBasis.ADVERSE_EVIDENCE.value: "The frozen evidence matrix contains exact EvidenceUse relationships classified upstream as adverse for this element. The report does not decide that the adverse material is correct.",
    AnalyticalBasis.CONFLICTING_EVIDENCE.value: "The frozen evidence matrix contains exact EvidenceUse relationships classified upstream as participating in a material conflict. The report does not reconstruct the conflict sides.",
    AnalyticalBasis.CROSS_ISSUE_COVERAGE.value: "The same canonical frozen evidence source participates through EvidenceUse relationships in more than one issue analysis. This is shared analytical provenance, not issue dependency, corroboration, causation or legal significance.",
    AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE.value: "This particular existing frozen supporting finding's complete material provenance resolves to one canonical evidence identity. This is not a global claim that no other relevant or similar evidence exists elsewhere in the case.",
}
_M45_BASES = frozenset(_M45_EXPLANATIONS)


def _label(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _status(value, explanations: dict[str, str], *, prefix: str) -> StatusView:
    raw = value.value if hasattr(value, "value") else str(value)
    return StatusView(
        raw_value=raw,
        label=_label(raw),
        explanation=explanations.get(raw, f"Frozen analytical value: {raw}."),
        qualification_code=f"{prefix}:{raw}",
    )


def _confidence(value: Confidence) -> StatusView:
    return StatusView(
        raw_value=value.value,
        label=_label(value.value),
        explanation=_CONFIDENCE_EXPLANATION,
        qualification_code=f"confidence:{value.value}",
    )


def _materiality(value: Materiality) -> StatusView:
    explanation = _MATERIALITY_MEDIUM if value is Materiality.MEDIUM else (
        f"{_label(value.value)} is the exact frozen materiality value. The report does not convert it into outcome prediction."
    )
    return StatusView(value.value, _label(value.value), explanation, f"materiality:{value.value}")


def _priority(value) -> StatusView:
    explanation = _PRIORITY_MEDIUM if value.value == "medium" else (
        f"{_label(value.value)} is the exact frozen priority value. The report does not create a new ordering."
    )
    return StatusView(value.value, _label(value.value), explanation, f"priority:{value.value}")


def _minimum_confidence(values: Iterable[Confidence]) -> Confidence:
    rank = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
    values = tuple(values)
    return min(values, key=lambda item: rank[item]) if values else Confidence.LOW


def _temporal(value: TemporalExtent | None) -> TemporalExtentReport | None:
    if value is None:
        return None
    end = value.end
    return TemporalExtentReport(
        kind=value.kind.value,
        start_year=value.start.year,
        start_month=value.start.month,
        start_day=value.start.day,
        start_precision=value.start.precision.value,
        end_year=end.year if end else None,
        end_month=end.month if end else None,
        end_day=end.day if end else None,
        end_precision=end.precision.value if end else None,
        display_text=value.display_text,
    )


def _hash_text(payload: str) -> str:
    return sha256(payload.encode("utf-8")).hexdigest()


def _statement(
    *,
    issue_id: str,
    element_id: str,
    category: str,
    text: str,
    evidence_keys: tuple[str, ...] = (),
    citation_ids: tuple[str, ...] = (),
) -> ReportStatement:
    return ReportStatement(
        report_statement_id=derive_report_statement_id(
            issue_analysis_id=issue_id,
            element_id=element_id,
            category=category,
            text=text,
            evidence_keys=evidence_keys,
            citation_ids=citation_ids,
        ),
        category=category,
        text=text,
        evidence_keys=evidence_keys,
        citation_ids=citation_ids,
    )


def _make_statement(issue_id: str, element_id: str, category: str, value) -> ReportStatement:
    return _statement(
        issue_id=issue_id,
        element_id=element_id,
        category=category,
        text=value.text,
        evidence_keys=tuple(value.evidence_keys),
        citation_ids=tuple(value.evidence_keys),
    )


def _citation(record) -> CitationRecord:
    return CitationRecord(
        citation_id=record.evidence_key,
        evidence_key=record.evidence_key,
        citation=record.citation,
        document_id=record.document_id,
        document_name=record.document_name,
        page=record.page,
        chunk_id=record.chunk_id,
        date=record.date.isoformat() if record.date is not None else None,
        author=record.author,
        parties=record.parties,
        source_type=record.source_type.value,
        evidence_status=record.evidence_status.value,
        provenance_type=record.provenance_type.value,
        provenance_basis=record.provenance_basis.value,
        provenance_confidence=record.provenance_confidence.value,
        evidence_use_coordinates=tuple(use.identity for use in record.uses),
    )


def _resolve_provenance(
    ref: SynthesisProvenanceRef,
    *,
    issue_by_id,
    element_by_identity,
    use_by_identity,
    evidence_by_key,
    event_by_id,
    assertion_by_identity,
) -> ResolvedProvenance:
    target = ref.target
    if isinstance(target, IssueRef):
        issue = issue_by_id[target.issue_analysis_id]
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.issue_analysis_id, target.issue_definition_id, target.issue_definition_version),
            display_label=issue.issue_name,
        )
    if isinstance(target, ElementRef):
        element = element_by_identity[(target.issue_analysis_id, target.element_id)]
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.issue_analysis_id, target.element_id),
            display_label=f"{element.element_name}: {element.legal_question}",
        )
    if isinstance(target, EvidenceUseRef):
        use = use_by_identity[target.identity]
        record = evidence_by_key[target.evidence_key]
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=target.identity,
            display_label=f"{record.citation} — {use.element_id}",
            citation_ids=(target.evidence_key,),
            raw_role_or_status=use.analytical_role.value,
        )
    if isinstance(target, PropositionRef):
        use = use_by_identity[target.evidence_use_ref.identity]
        try:
            link = next(
                item
                for item in use.proposition_links
                if item.source_proposition_index == target.source_proposition_index
            )
        except StopIteration as exc:
            raise ValueError("PropositionRef does not resolve at its exact source index.") from exc
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(*target.evidence_use_ref.identity, str(target.source_proposition_index)),
            display_label=link.text,
            citation_ids=(target.evidence_use_ref.evidence_key,),
            raw_role_or_status=link.status.value,
        )
    if isinstance(target, EventRef):
        event = event_by_id[target.event_id]
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.event_id,),
            display_label=event.description,
            citation_ids=tuple(event.evidence_keys),
            raw_role_or_status=f"occurrence={event.event_status.value};timing={event.timing_status.value}",
        )
    if isinstance(target, EventAssertionRef):
        assertion = assertion_by_identity[(target.event_id, target.assertion_id)]
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.event_id, target.assertion_id),
            display_label=assertion.description,
            citation_ids=(assertion.evidence_key,),
            raw_role_or_status=f"occurrence={assertion.event_status.value};timing={assertion.timing_status.value}",
        )
    if isinstance(target, EvidentialGapRef):
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.issue_analysis_id, target.element_id, target.gap_id),
            display_label=f"Upstream evidential-gap identity {target.gap_id}",
            identity_only=True,
            qualification_text=_IDENTITY_ONLY_GAP,
        )
    if isinstance(target, DisputedMatterRef):
        return ResolvedProvenance(
            provenance_type=ref.reference_type.value,
            identity=(target.issue_analysis_id, target.element_id, target.disputed_matter_id),
            display_label=f"Upstream disputed-matter identity {target.disputed_matter_id}",
            identity_only=True,
            qualification_text=_IDENTITY_ONLY_DISPUTE,
        )
    raise ValueError(f"Unsupported provenance target {type(target)!r}.")


def _resolved_tuple(refs, **lookups) -> tuple[ResolvedProvenance, ...]:
    return tuple(_resolve_provenance(ref, **lookups) for ref in refs)


def _citation_ids(values: Iterable[ResolvedProvenance]) -> tuple[str, ...]:
    return tuple(sorted({item for value in values for item in value.citation_ids}))


def _finding_coordinates(refs: tuple[ResolvedProvenance, ...], event_by_id, assertion_by_identity):
    issue_ids: set[str] = set()
    element_coords: set[tuple[str, str]] = set()
    for ref in refs:
        kind = ref.provenance_type
        ident = ref.identity
        if kind in {"issue", "element", "evidence_use", "proposition", "evidential_gap", "disputed_matter"}:
            issue_ids.add(ident[0])
        if kind in {"element", "evidence_use", "proposition", "evidential_gap", "disputed_matter"}:
            element_coords.add((ident[0], ident[1]))
        if kind == "event":
            event = event_by_id[ident[0]]
            issue_ids.update(event.related_issue_analysis_ids)
            element_coords.update((item.issue_analysis_id, item.element_id) for item in event.assertions)
        if kind == "event_assertion":
            assertion = assertion_by_identity[(ident[0], ident[1])]
            issue_ids.add(assertion.issue_analysis_id)
            element_coords.add((assertion.issue_analysis_id, assertion.element_id))
    return tuple(sorted(issue_ids)), tuple(sorted(element_coords))


def _finding_report(value, *, direct_ids: set[str], lookups) -> FindingReport:
    resolved = _resolved_tuple(value.provenance_refs, **lookups)
    issue_ids, element_coords = _finding_coordinates(
        resolved,
        lookups["event_by_id"],
        lookups["assertion_by_identity"],
    )
    bases = tuple(item.value for item in value.analytical_bases)
    origin = "direct_m4_2" if value.finding_id in direct_ids else "higher_order_m4_5"
    if value.finding_type is FindingType.SUPPORTING_FEATURE:
        category = "supporting_features"
    elif value.finding_type is FindingType.LIMITING_FEATURE:
        category = "limiting_features"
    else:
        category = "cross_issue_structural_features"
    explanations = tuple(_M45_EXPLANATIONS[item] for item in bases if item in _M45_EXPLANATIONS)
    return FindingReport(
        finding_id=value.finding_id,
        finding_type=value.finding_type.value,
        scope=value.scope.value,
        analytical_bases=bases,
        status=_status(value.status, _FINDING_EXPLANATIONS, prefix="finding_status"),
        confidence=_confidence(value.confidence),
        summary=value.summary,
        origin=origin,
        category=category,
        issue_ids=issue_ids,
        element_coordinates=element_coords,
        related_finding_ids=value.related_finding_ids,
        provenance=resolved,
        citation_ids=_citation_ids(resolved),
        controlled_explanation=" ".join(explanations),
    )


def _element_report(
    issue_id: str,
    value: IssueElementRecord,
    *,
    finding_reports: tuple[FindingReport, ...],
    direct_ids: set[str],
    gaps,
    risks,
) -> ElementReport:
    coord = (issue_id, value.element_id)
    linked_findings = tuple(item for item in finding_reports if coord in item.element_coordinates)
    direct = tuple(item.finding_id for item in linked_findings if item.finding_id in direct_ids)
    higher = tuple(item.finding_id for item in linked_findings if item.finding_id not in direct_ids)
    linked_gaps = tuple(item.gap_id for item in gaps if item.issue_analysis_id == issue_id and item.element_id == value.element_id)
    gap_set = set(linked_gaps)
    linked_risks = tuple(
        item.risk_id
        for item in risks
        if issue_id in item.affected_issue_ids and (not item.gap_ids or bool(gap_set.intersection(item.gap_ids)))
    )
    return ElementReport(
        issue_analysis_id=issue_id,
        element_id=value.element_id,
        element_name=value.element_name,
        legal_question=value.legal_question,
        analysis_status=_status(value.analysis_status, _ELEMENT_EXPLANATIONS, prefix="element_status"),
        analysis_confidence=_confidence(value.analysis_confidence),
        established_matters=tuple(_make_statement(issue_id, value.element_id, "established", item) for item in value.established_matters),
        supported_matters=tuple(_make_statement(issue_id, value.element_id, "supported", item) for item in value.supported_matters),
        not_supported_matters=tuple(_make_statement(issue_id, value.element_id, "not_supported", item) for item in value.not_supported_matters),
        source_assertions=tuple(_make_statement(issue_id, value.element_id, "source_assertion", item) for item in value.source_assertions),
        unresolved_matters=value.unresolved_matters,
        legal_significance=value.legal_significance,
        provisional_analysis=value.provisional_analysis,
        linked_direct_finding_ids=direct,
        linked_higher_order_finding_ids=higher,
        linked_gap_ids=linked_gaps,
        linked_risk_ids=linked_risks,
    )


def _event_report(event, evidence_by_key) -> EventReport:
    assertions = tuple(
        EventAssertionReport(
            event_id=event.event_id,
            assertion_id=item.assertion_id,
            description=item.description,
            issue_analysis_id=item.issue_analysis_id,
            element_id=item.element_id,
            evidence_key=item.evidence_key,
            citation_id=item.evidence_key,
            source_proposition_index=item.source_proposition_index,
            occurrence_status=_status(item.event_status, _EVENT_OCCURRENCE_EXPLANATIONS, prefix="event_occurrence"),
            timing_status=_status(item.timing_status, _TIMING_EXPLANATIONS, prefix="event_timing"),
            confidence=_confidence(item.confidence),
            temporal_extent=_temporal(item.temporal_extent),
            extraction_basis=item.extraction_basis.value,
        )
        for item in event.assertions
    )
    for key in event.evidence_keys:
        if key not in evidence_by_key:
            raise ValueError(f"Chronology evidence key {key!r} does not resolve in M2.")
    return EventReport(
        event_id=event.event_id,
        description=event.description,
        normalized_event_core=event.normalized_event_core,
        event_type=event.event_type.value,
        occurrence_status=_status(event.event_status, _EVENT_OCCURRENCE_EXPLANATIONS, prefix="event_occurrence"),
        timing_status=_status(event.timing_status, _TIMING_EXPLANATIONS, prefix="event_timing"),
        confidence=_confidence(_minimum_confidence(item.confidence for item in event.assertions)),
        canonical_temporal_extent=_temporal(event.canonical_temporal_extent),
        participants=event.participants,
        evidence_keys=event.evidence_keys,
        citation_ids=event.evidence_keys,
        related_issue_ids=event.related_issue_analysis_ids,
        related_element_coordinates=tuple(
            sorted({(item.issue_analysis_id, item.element_id) for item in event.assertions})
        ),
        assertions=assertions,
    )


def _status_pairs(item_id: str, *views: StatusView) -> tuple[tuple[str, str], ...]:
    return tuple((f"{item_id}:{index}", value.raw_value) for index, value in enumerate(views))


def _qualification_pairs(item_id: str, *views: StatusView) -> tuple[tuple[str, str], ...]:
    return tuple((f"{item_id}:{index}", value.qualification_code) for index, value in enumerate(views))


def _build_manifest(
    *,
    report_projection_id: str,
    projection_payload_sha256: str,
    case_header: CaseHeaderReport,
    lineage: AnalyticalLineageReport,
    overall_state: OverallStateReport,
    issues: tuple[IssueReport, ...],
    chronology: tuple[EventReport, ...],
    cross_issue_findings: tuple[FindingReport, ...],
    conflicts: tuple[ConflictReport, ...],
    gaps: tuple[GapReport, ...],
    risks: tuple[RiskReport, ...],
    questions: tuple[PriorityQuestionReport, ...],
    citations: tuple[CitationRecord, ...],
    glossary: tuple[GlossaryEntry, ...],
) -> ReportManifest:
    issue_ids = tuple(item.issue_analysis_id for item in issues)
    element_coords = tuple(f"{issue.issue_analysis_id}|{element.element_id}" for issue in issues for element in issue.elements)
    all_findings_by_id = {
        item.finding_id: item
        for issue in issues
        for item in (*issue.direct_findings, *issue.higher_order_findings)
    }
    # Reproduce the frozen CaseSynthesis canonical finding order.
    finding_ids = tuple(
        item.finding_id
        for item in sorted(
            all_findings_by_id.values(),
            key=lambda value: (value.scope, value.finding_type, value.finding_id),
        )
    )
    event_ids = tuple(item.event_id for item in chronology)
    assertion_coords = tuple(f"{event.event_id}|{item.assertion_id}" for event in chronology for item in event.assertions)
    conflict_ids = tuple(item.conflict_id for item in conflicts)
    gap_ids = tuple(item.gap_id for item in gaps)
    risk_ids = tuple(item.risk_id for item in risks)
    question_ids = tuple(item.question_id for item in questions)
    citation_ids = tuple(item.citation_id for item in citations)

    status_inventory: list[tuple[str, str]] = []
    qualification_inventory: list[tuple[str, str]] = []
    status_inventory.extend(_status_pairs("overall_state", overall_state.state))
    qualification_inventory.extend(_qualification_pairs("overall_state", overall_state.state))
    for issue in issues:
        status_inventory.extend(_status_pairs(issue.issue_analysis_id, issue.position_status, issue.confidence))
        qualification_inventory.extend(_qualification_pairs(issue.issue_analysis_id, issue.position_status, issue.confidence))
        for element in issue.elements:
            item_id = f"{issue.issue_analysis_id}|{element.element_id}"
            status_inventory.extend(_status_pairs(item_id, element.analysis_status, element.analysis_confidence))
            qualification_inventory.extend(_qualification_pairs(item_id, element.analysis_status, element.analysis_confidence))
    for finding_id in finding_ids:
        item = all_findings_by_id[finding_id]
        status_inventory.extend(_status_pairs(item.finding_id, item.status, item.confidence))
        qualification_inventory.extend(_qualification_pairs(item.finding_id, item.status, item.confidence))
    for event in chronology:
        status_inventory.extend(_status_pairs(event.event_id, event.occurrence_status, event.timing_status, event.confidence))
        qualification_inventory.extend(_qualification_pairs(event.event_id, event.occurrence_status, event.timing_status, event.confidence))
        for assertion in event.assertions:
            status_inventory.extend(_status_pairs(assertion.assertion_id, assertion.occurrence_status, assertion.timing_status, assertion.confidence))
            qualification_inventory.extend(_qualification_pairs(assertion.assertion_id, assertion.occurrence_status, assertion.timing_status, assertion.confidence))
    for item in conflicts:
        status_inventory.extend(_status_pairs(item.conflict_id, item.status, item.materiality))
        qualification_inventory.extend(_qualification_pairs(item.conflict_id, item.status, item.materiality))
    for item in gaps:
        status_inventory.extend(_status_pairs(item.gap_id, item.materiality))
        qualification_inventory.extend(_qualification_pairs(item.gap_id, item.materiality))
    for item in risks:
        status_inventory.extend(_status_pairs(item.risk_id, item.materiality))
        qualification_inventory.extend(_qualification_pairs(item.risk_id, item.materiality))
    for item in questions:
        status_inventory.extend(_status_pairs(item.question_id, item.priority))
        qualification_inventory.extend(_qualification_pairs(item.question_id, item.priority))

    section_items = {
        "report_header": (case_header.case_id,),
        "analytical_lineage": (lineage.foundation_synthesis_id,),
        "overall_state": ("overall_state",),
        "issues": (*issue_ids, *element_coords, *finding_ids),
        "chronology": (*event_ids, *assertion_coords),
        "cross_issue_findings": tuple(item.finding_id for item in cross_issue_findings),
        "conflicts": conflict_ids,
        "evidence_gaps": gap_ids,
        "risk_areas": risk_ids,
        "priority_questions": question_ids,
        "evidence_appendix": citation_ids,
        "glossary": tuple(item.code for item in glossary),
    }
    section_citations = {
        "report_header": (),
        "analytical_lineage": (),
        "overall_state": (),
        "issues": tuple(sorted({citation for issue in issues for finding in (*issue.direct_findings, *issue.higher_order_findings) for citation in finding.citation_ids})),
        "chronology": tuple(sorted({citation for event in chronology for citation in event.citation_ids})),
        "cross_issue_findings": tuple(sorted({citation for finding in cross_issue_findings for citation in finding.citation_ids})),
        "conflicts": tuple(sorted({citation for item in conflicts for citation in item.citation_ids})),
        "evidence_gaps": tuple(sorted({citation for item in gaps for citation in item.citation_ids})),
        "risk_areas": tuple(sorted({citation for item in risks for citation in item.citation_ids})),
        "priority_questions": tuple(sorted({citation for item in questions for citation in item.citation_ids})),
        "evidence_appendix": citation_ids,
        "glossary": (),
    }
    issue_statuses = tuple(
        value.raw_value
        for issue in issues
        for value in (
            issue.position_status,
            issue.confidence,
            *(status for element in issue.elements for status in (element.analysis_status, element.analysis_confidence)),
            *(status for finding in (*issue.direct_findings, *issue.higher_order_findings) for status in (finding.status, finding.confidence)),
        )
    )
    issue_qualifications = tuple(
        value.qualification_code
        for issue in issues
        for value in (
            issue.position_status,
            issue.confidence,
            *(status for element in issue.elements for status in (element.analysis_status, element.analysis_confidence)),
            *(status for finding in (*issue.direct_findings, *issue.higher_order_findings) for status in (finding.status, finding.confidence)),
        )
    )
    chronology_statuses = tuple(
        value.raw_value
        for event in chronology
        for value in (
            event.occurrence_status,
            event.timing_status,
            event.confidence,
            *(status for assertion in event.assertions for status in (assertion.occurrence_status, assertion.timing_status, assertion.confidence)),
        )
    )
    chronology_qualifications = tuple(
        value.qualification_code
        for event in chronology
        for value in (
            event.occurrence_status,
            event.timing_status,
            event.confidence,
            *(status for assertion in event.assertions for status in (assertion.occurrence_status, assertion.timing_status, assertion.confidence)),
        )
    )
    cross_issue_statuses = tuple(
        status.raw_value for item in cross_issue_findings for status in (item.status, item.confidence)
    )
    cross_issue_qualifications = tuple(
        status.qualification_code for item in cross_issue_findings for status in (item.status, item.confidence)
    )
    section_statuses = {
        "report_header": (),
        "analytical_lineage": (),
        "overall_state": (overall_state.state.raw_value,),
        "issues": issue_statuses,
        "chronology": chronology_statuses,
        "cross_issue_findings": cross_issue_statuses,
        "conflicts": tuple(value.raw_value for item in conflicts for value in (item.status, item.materiality)),
        "evidence_gaps": tuple(item.materiality.raw_value for item in gaps),
        "risk_areas": tuple(item.materiality.raw_value for item in risks),
        "priority_questions": tuple(item.priority.raw_value for item in questions),
        "evidence_appendix": (),
        "glossary": (),
    }
    section_qualifications = {
        "report_header": (),
        "analytical_lineage": (),
        "overall_state": (overall_state.state.qualification_code,),
        "issues": issue_qualifications,
        "chronology": chronology_qualifications,
        "cross_issue_findings": cross_issue_qualifications,
        "conflicts": tuple(value.qualification_code for item in conflicts for value in (item.status, item.materiality)),
        "evidence_gaps": tuple(item.materiality.qualification_code for item in gaps),
        "risk_areas": tuple(item.materiality.qualification_code for item in risks),
        "priority_questions": tuple(item.priority.qualification_code for item in questions),
        "evidence_appendix": (),
        "glossary": tuple(item.code for item in glossary),
    }
    sections = tuple(
        ManifestSection(
            section_id=key,
            section_key=key,
            ordinal=index,
            ordered_item_ids=tuple(section_items[key]),
            ordered_citation_ids=tuple(section_citations[key]),
            raw_status_values=section_statuses[key],
            qualification_codes=section_qualifications[key],
            is_mandatory=key in MANDATORY_SECTION_KEYS,
            is_empty=not bool(section_items[key]),
        )
        for index, key in enumerate(SECTION_KEYS)
    )
    placeholder = ReportManifest(
        manifest_id="00000000-0000-4000-8000-000000000000",
        report_projection_id=report_projection_id,
        projection_payload_sha256=projection_payload_sha256,
        ordered_section_ids=SECTION_KEYS,
        sections=sections,
        ordered_issue_ids=issue_ids,
        ordered_element_coordinates=element_coords,
        ordered_finding_ids=finding_ids,
        ordered_event_ids=event_ids,
        ordered_event_assertion_coordinates=assertion_coords,
        ordered_conflict_ids=conflict_ids,
        ordered_gap_ids=gap_ids,
        ordered_risk_ids=risk_ids,
        ordered_question_ids=question_ids,
        ordered_citation_ids=citation_ids,
        raw_status_inventory=tuple(status_inventory),
        qualification_inventory=tuple(qualification_inventory),
    )
    manifest_payload_sha = sha256(
        canonical_json_bytes(report_manifest_semantic_payload_to_dict(placeholder))
    ).hexdigest()
    return replace(
        placeholder,
        manifest_id=derive_manifest_id(
            report_projection_id=report_projection_id,
            projection_payload_sha256=projection_payload_sha256,
            manifest_payload_sha256=manifest_payload_sha,
        ),
    )


def build_case_report_projection(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
    synthesis: CaseSynthesis,
    metadata: CaseReportMetadata | None = None,
) -> CaseReportProjection:
    """Build and validate one immutable deterministic reporting projection."""

    validate_case_synthesis(
        synthesis,
        foundation=foundation,
        matrices=matrices,
        chronology=chronology,
    )
    if chronology.source_analysis_ids != foundation.source_issue_analysis_ids:
        raise ValueError("Chronology source-analysis set does not match the frozen foundation.")

    foundation_sha = _hash_text(dumps_case_analysis_foundation(foundation))
    matrices_sha = _hash_text(dumps_case_matrices(matrices))
    chronology_sha = _hash_text(dumps_case_chronology(chronology))
    synthesis_sha = _hash_text(dumps_case_synthesis(synthesis))
    metadata_sha = fingerprint_metadata(metadata)

    report_projection_id = derive_report_projection_id(
        case_id=foundation.case_id,
        source_synthesis_id=synthesis.synthesis_id,
        source_foundation_sha256=foundation_sha,
        source_matrices_sha256=matrices_sha,
        source_chronology_sha256=chronology_sha,
        source_synthesis_sha256=synthesis_sha,
        source_metadata_sha256=metadata_sha,
    )

    case_header = CaseHeaderReport(
        case_id=foundation.case_id,
        case_name=metadata.case_name if metadata else None,
        case_number=metadata.case_number if metadata else None,
        claimant=metadata.claimant if metadata else None,
        respondent=metadata.respondent if metadata else None,
        case_status=metadata.case_status if metadata else None,
        court_or_tribunal=metadata.court_or_tribunal if metadata else None,
    )
    lineage = AnalyticalLineageReport(
        foundation_synthesis_id=foundation.synthesis_id,
        foundation_schema_version=foundation.schema_version,
        foundation_synthesiser_version=foundation.synthesiser_version,
        matrices_schema_version=matrices.schema_version,
        matrices_builder_version=matrices.matrix_builder_version,
        chronology_schema_version=chronology.schema_version,
        chronology_builder_version=chronology.chronology_builder_version,
        synthesis_schema_version=synthesis.schema_version,
        synthesis_builder_version=synthesis.synthesiser_version,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        issue_definition_lineage=tuple(
            (item.issue_analysis_id, item.issue_definition_id, item.issue_definition_version)
            for item in foundation.source_analyses
        ),
    )

    issue_by_id = {item.issue_analysis_id: item for item in matrices.issue_matrix}
    element_by_identity = {
        (issue.issue_analysis_id, element.element_id): element
        for issue in matrices.issue_matrix
        for element in issue.element_records
    }
    evidence_by_key = {item.evidence_key: item for item in matrices.evidence_matrix}
    use_by_identity: dict[tuple[str, str, str], EvidenceUse] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.identity in use_by_identity:
                raise ValueError(f"Duplicate EvidenceUse identity {use.identity!r}.")
            use_by_identity[use.identity] = use
    event_by_id = {item.event_id: item for item in chronology.events}
    assertion_by_identity = {
        (event.event_id, item.assertion_id): item
        for event in chronology.events
        for item in event.assertions
    }
    lookups = {
        "issue_by_id": issue_by_id,
        "element_by_identity": element_by_identity,
        "use_by_identity": use_by_identity,
        "evidence_by_key": evidence_by_key,
        "event_by_id": event_by_id,
        "assertion_by_identity": assertion_by_identity,
    }

    citations = tuple(_citation(item) for item in matrices.evidence_matrix)
    direct_ids = {item for position in synthesis.issue_positions for item in position.material_finding_ids}
    finding_reports = tuple(
        _finding_report(item, direct_ids=direct_ids, lookups=lookups)
        for item in synthesis.findings
    )
    finding_by_id = {item.finding_id: item for item in finding_reports}

    conflict_reports = tuple(
        ConflictReport(
            conflict_id=item.conflict_id,
            conflict_type=item.conflict_type.value,
            scope=item.scope.value,
            subject=item.subject,
            status=_status(item.status, _FINDING_EXPLANATIONS, prefix="finding_status"),
            materiality=_materiality(item.materiality),
            side_a=_resolved_tuple(item.side_a_refs, **lookups),
            side_b=_resolved_tuple(item.side_b_refs, **lookups),
            related_issue_ids=item.related_issue_ids,
            citation_ids=_citation_ids((*_resolved_tuple(item.side_a_refs, **lookups), *_resolved_tuple(item.side_b_refs, **lookups))),
        )
        for item in synthesis.conflicts
    )
    gap_reports = tuple(
        GapReport(
            gap_id=item.gap_id,
            gap_type=item.gap_type.value,
            scope=item.scope.value,
            issue_analysis_id=item.issue_analysis_id,
            issue_definition_id=item.issue_definition_id,
            issue_definition_version=item.issue_definition_version,
            element_id=item.element_id,
            description=item.description,
            materiality=_materiality(item.materiality),
            unresolved_question=item.unresolved_question,
            provenance=_resolved_tuple(item.provenance_refs, **lookups),
            citation_ids=_citation_ids(_resolved_tuple(item.provenance_refs, **lookups)),
            related_finding_ids=item.related_finding_ids,
        )
        for item in synthesis.gaps
    )
    risk_reports = tuple(
        RiskReport(
            risk_id=item.risk_id,
            risk_type=item.risk_type.value,
            scope=item.scope.value,
            materiality=_materiality(item.materiality),
            description=item.description,
            classification_explanation=_RISK_EXPLANATION,
            basis_finding_ids=item.basis_finding_ids,
            conflict_ids=item.conflict_ids,
            gap_ids=item.gap_ids,
            affected_issue_ids=item.affected_issue_ids,
            provenance=_resolved_tuple(item.provenance_refs, **lookups),
            citation_ids=_citation_ids(_resolved_tuple(item.provenance_refs, **lookups)),
        )
        for item in synthesis.risks
    )
    question_reports = tuple(
        PriorityQuestionReport(
            question_id=item.question_id,
            question=item.question,
            priority=_priority(item.priority),
            basis_type=item.basis_type.value,
            affected_issue_ids=item.affected_issue_ids,
            affected_element_ids=item.affected_element_ids,
            finding_ids=item.finding_ids,
            gap_ids=item.gap_ids,
            conflict_ids=item.conflict_ids,
            provenance=_resolved_tuple(item.provenance_refs, **lookups),
            citation_ids=_citation_ids(_resolved_tuple(item.provenance_refs, **lookups)),
        )
        for item in synthesis.priority_questions
    )

    issues: list[IssueReport] = []
    for position in synthesis.issue_positions:
        issue = issue_by_id[position.issue_analysis_id]
        direct_findings = tuple(finding_by_id[item] for item in position.material_finding_ids)
        higher_findings = tuple(
            item
            for item in finding_reports
            if item.finding_id not in direct_ids and position.issue_analysis_id in item.issue_ids
        )
        elements = tuple(
            _element_report(
                position.issue_analysis_id,
                element,
                finding_reports=finding_reports,
                direct_ids=direct_ids,
                gaps=synthesis.gaps,
                risks=synthesis.risks,
            )
            for element in issue.element_records
        )
        issues.append(
            IssueReport(
                issue_analysis_id=position.issue_analysis_id,
                issue_definition_id=position.issue_definition_id,
                issue_definition_version=position.issue_definition_version,
                issue_name=position.issue_name,
                original_user_question=issue.original_user_question,
                issue_summary=issue.issue_summary,
                position_status=_status(position.position_status, _ISSUE_EXPLANATIONS, prefix="issue_position"),
                confidence=_confidence(position.confidence),
                material_finding_ids=position.material_finding_ids,
                conflict_ids=position.conflict_ids,
                gap_ids=position.gap_ids,
                risk_ids=position.risk_ids,
                elements=elements,
                direct_findings=direct_findings,
                higher_order_findings=higher_findings,
            )
        )
    issue_reports = tuple(issues)
    chronology_reports = tuple(_event_report(item, evidence_by_key) for item in chronology.events)
    cross_issue = tuple(item for item in finding_reports if item.finding_type == FindingType.CROSS_ISSUE_FEATURE.value)
    overall = OverallStateReport(
        state=_status(synthesis.overall_state, _OVERALL_EXPLANATIONS, prefix="overall_state"),
        issue_count=len(issue_reports),
        element_count=sum(len(item.elements) for item in issue_reports),
        event_count=len(chronology_reports),
        finding_count=len(finding_reports),
        conflict_count=len(conflict_reports),
        gap_count=len(gap_reports),
        risk_count=len(risk_reports),
        priority_question_count=len(question_reports),
        citation_count=len(citations),
        count_qualification=_COUNT_QUALIFICATION,
    )
    glossary = tuple(
        GlossaryEntry(code=code, label=_label(code.split(":", 1)[-1]), explanation=explanation)
        for code, explanation in (
            ("neutral_materiality:medium", _MATERIALITY_MEDIUM),
            ("neutral_priority:medium", _PRIORITY_MEDIUM),
            ("confidence", _CONFIDENCE_EXPLANATION),
            ("occurrence_timing_separation", "Occurrence status and timing status are independent. Established timing does not upgrade occurrence."),
            ("identity_only_gap", _IDENTITY_ONLY_GAP),
            ("identity_only_dispute", _IDENTITY_ONLY_DISPUTE),
        )
    )

    payload = projection_semantic_payload_from_parts(
        schema_version=REPORT_PROJECTION_SCHEMA_VERSION,
        projector_version=REPORT_PROJECTOR_VERSION,
        source_synthesis_id=synthesis.synthesis_id,
        source_foundation_sha256=foundation_sha,
        source_matrices_sha256=matrices_sha,
        source_chronology_sha256=chronology_sha,
        source_synthesis_sha256=synthesis_sha,
        source_metadata_sha256=metadata_sha,
        case_header=case_header,
        lineage=lineage,
        overall_state=overall,
        issues=issue_reports,
        chronology=chronology_reports,
        cross_issue_findings=cross_issue,
        conflicts=conflict_reports,
        gaps=gap_reports,
        risks=risk_reports,
        priority_questions=question_reports,
        citations=citations,
        glossary=glossary,
    )
    payload_sha = sha256(canonical_json_bytes(payload)).hexdigest()
    manifest = _build_manifest(
        report_projection_id=report_projection_id,
        projection_payload_sha256=payload_sha,
        case_header=case_header,
        lineage=lineage,
        overall_state=overall,
        issues=issue_reports,
        chronology=chronology_reports,
        cross_issue_findings=cross_issue,
        conflicts=conflict_reports,
        gaps=gap_reports,
        risks=risk_reports,
        questions=question_reports,
        citations=citations,
        glossary=glossary,
    )
    projection = CaseReportProjection(
        report_projection_id=report_projection_id,
        source_synthesis_id=synthesis.synthesis_id,
        source_foundation_sha256=foundation_sha,
        source_matrices_sha256=matrices_sha,
        source_chronology_sha256=chronology_sha,
        source_synthesis_sha256=synthesis_sha,
        source_metadata_sha256=metadata_sha,
        projection_payload_sha256=payload_sha,
        case_header=case_header,
        lineage=lineage,
        overall_state=overall,
        issues=issue_reports,
        chronology=chronology_reports,
        cross_issue_findings=cross_issue,
        conflicts=conflict_reports,
        gaps=gap_reports,
        risks=risk_reports,
        priority_questions=question_reports,
        citations=citations,
        glossary=glossary,
        manifest=manifest,
    )
    from .validation import validate_case_report_projection

    validate_case_report_projection(projection)
    return projection


__all__ = ["build_case_report_projection"]
