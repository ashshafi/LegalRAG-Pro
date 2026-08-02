"""Conservative deterministic evidential-assessment rules for Sprint 2.3 M4."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Final, Iterable

from evidence_classification import EvidenceSourceType

from .enums import AnalyticalRole, Confidence, EvidenceStatus, Materiality
from .evidence_assessment import AssessedProposition, EvidenceAssessment, PropositionAssessmentStatus
from .evidence_mapping import EvidenceMapping
from .models import DisputedMatter, EvidentialGap, EvidenceReference


_WORD_RE = re.compile(r"[a-z0-9]+")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{4})\b",
    re.IGNORECASE,
)

_CLAIMANT_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset({
    EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
    EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
    EvidenceSourceType.CLAIMANT_SUBMISSION,
})
_RESPONDENT_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset({
    EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT,
    EvidenceSourceType.RESPONDENT_SUBMISSION,
})
_INDEPENDENT_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset({
    EvidenceSourceType.INDEPENDENT_MEDICAL,
    EvidenceSourceType.OCCUPATIONAL_HEALTH,
    EvidenceSourceType.INSURER_RECORD,
    EvidenceSourceType.TRIBUNAL_RECORD,
})
_DIRECT_RECORD_STATUSES: Final[frozenset[EvidenceStatus]] = frozenset({
    EvidenceStatus.DOCUMENTED_FACT,
    EvidenceStatus.EMPLOYER_EVIDENCE,
    EvidenceStatus.INDEPENDENT_MEDICAL_EVIDENCE,
    EvidenceStatus.OCCUPATIONAL_HEALTH_EVIDENCE,
    EvidenceStatus.INSURER_EVIDENCE,
    EvidenceStatus.TRIBUNAL_RECORD,
})
_DENIAL_PHRASES: Final[tuple[str, ...]] = (
    "deny", "denied", "denies", "not aware", "unaware", "no knowledge", "did not know",
    "did not receive", "never received", "not received", "was not sent",
    "no record of", "not informed", "no continuing", "single act", "out of time",
)


@dataclass(frozen=True, slots=True)
class GapRule:
    description: str
    reason: str
    target: str
    materiality: Materiality = Materiality.MEDIUM


_GAP_RULES: Final[dict[str, GapRule]] = {
    "EK-RECIPIENT": GapRule(
        "Direct evidence identifying which CACI recipient received the relevant disability information.",
        "The current mapped evidence does not include a sufficiently direct recipient/receipt record.",
        "Underlying email header, acknowledgement, meeting record or manager response identifying receipt.",
        Materiality.HIGH,
    ),
    "EK-DIRECT-KNOWLEDGE": GapRule(
        "Direct contemporaneous acknowledgement by CACI of the specific disability-related information relied upon.",
        "Current evidence does not directly establish receipt, acknowledgement or discussion of the specific information.",
        "CACI email, OH referral, manager acknowledgement or contemporaneous meeting record.",
        Materiality.HIGH,
    ),
    "EK-DISADVANTAGE-KNOWLEDGE": GapRule(
        "Direct evidence of what CACI was told about the particular disadvantage relied upon.",
        "The mapped evidence does not directly record communication or acknowledgement of the particular disadvantage.",
        "Correspondence or OH/manager record identifying the disadvantage and recipient.",
        Materiality.HIGH,
    ),
    "RA-KNOWLEDGE": GapRule(
        "Direct evidence of the disability/disadvantage information communicated to CACI.",
        "The mapped evidence does not directly establish the content received or acknowledged by the employer.",
        "Employer acknowledgement, OH referral or correspondence showing receipt of the relevant information.",
        Materiality.HIGH,
    ),
    "RA-REASONABLENESS": GapRule(
        "Evidence addressing the practical effectiveness and feasibility of the proposed adjustment.",
        "The current mapped evidence does not directly address enough practical factors to assess the proposal evidentially.",
        "OH recommendation, operational assessment, trial evidence or contemporaneous feasibility discussion.",
        Materiality.MEDIUM,
    ),
    "RA-FAILURE": GapRule(
        "Direct record of the employer's decision, response or omission concerning the proposed adjustment.",
        "The current mapped evidence does not directly record what decision was made or why.",
        "Employer response, decision record, meeting note or correspondence addressing the adjustment.",
        Materiality.HIGH,
    ),
    "LIM-PRESENTATION": GapRule(
        "Reliable record of the relevant claim-presentation and ACAS Early Conciliation dates.",
        "The current mapped evidence does not contain a sufficiently direct procedural date record.",
        "ET1 receipt/presentation record and ACAS Early Conciliation certificate.",
        Materiality.HIGH,
    ),
    "LIM-RESPONDENT-POSITION": GapRule(
        "Direct respondent pleading or correspondence setting out the limitation position.",
        "The current mapped evidence does not contain a clear respondent statement of the limitation case.",
        "ET3, Grounds of Resistance or respondent written submission on limitation.",
        Materiality.MEDIUM,
    ),
    "DA-JUSTIFICATION": GapRule(
        "Direct respondent evidence identifying the asserted legitimate aim and proportionality case.",
        "The mapped evidence does not clearly identify the respondent's justification case.",
        "ET3/Grounds of Resistance, decision record or respondent submission addressing justification.",
        Materiality.MEDIUM,
    ),
}


def evidence_with_role(evidence: EvidenceReference, role: AnalyticalRole) -> EvidenceReference:
    """Return a role-adjusted copy without mutating frozen M3 evidence."""
    return replace(evidence, analytical_role=role)


def assessment_role(mapping: EvidenceMapping) -> tuple[AnalyticalRole, Confidence, str]:
    """Conservatively classify the evidential role of one RELEVANT M3 mapping."""
    evidence = mapping.evidence
    text = _normalise(evidence.summary)

    if _is_explicit_adverse(evidence, text):
        return (
            AnalyticalRole.ADVERSE,
            _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM),
            "The mapped source expressly records a denial or contrary position relevant to this element.",
        )

    if evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION:
        return (
            AnalyticalRole.SUPPORTING,
            _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM),
            "The source makes a relevant assertion, but the underlying proposition is not independently established by that assertion alone.",
        )

    if evidence.source_type in _RESPONDENT_TYPES:
        return (
            AnalyticalRole.NEUTRAL,
            _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM),
            "The respondent source is relevant to the element, but no deterministic rule establishes that it supports or contradicts a specific proposition.",
        )

    if mapping.mapping_confidence is Confidence.HIGH and evidence.evidence_status in _DIRECT_RECORD_STATUSES:
        return (
            AnalyticalRole.SUPPORTING,
            Confidence.HIGH,
            "A direct/non-derivative mapped record bears on the factual subject of this element with high mapping confidence.",
        )

    if evidence.source_type in _INDEPENDENT_TYPES and mapping.mapping_confidence in {Confidence.HIGH, Confidence.MEDIUM}:
        return (
            AnalyticalRole.SUPPORTING,
            mapping.mapping_confidence,
            "An independent or third-party record is relevant to the factual subject of the element; corroborative status is assigned only if another source independently records the same matter.",
        )

    if evidence.source_type in _CLAIMANT_TYPES:
        return (
            AnalyticalRole.SUPPORTING,
            _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM),
            "Claimant-authored evidence is relevant to the factual proposition but remains party evidence rather than independent confirmation.",
        )

    return (
        AnalyticalRole.NEUTRAL,
        _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM),
        "The item is relevant to the element but its evidential direction cannot be classified safely by deterministic rules.",
    )


def assess_proposition(
    mapping: EvidenceMapping,
    role: AnalyticalRole,
    *,
    element_id: str | None = None,
) -> AssessedProposition:
    """Create a conservative factual proposition assessment.

    A high-confidence direct source is *not* enough by itself to create an
    established proposition.  Establishment also requires a deterministic,
    element-specific factual signal.  Otherwise the item remains supporting
    but not established.
    """
    evidence = mapping.evidence
    element_id = element_id or mapping.element_id
    established_fact = _element_specific_established_fact(element_id, mapping)
    proposition = established_fact or _record_proposition(evidence)

    if role is AnalyticalRole.CONFLICTING:
        status = PropositionAssessmentStatus.DISPUTED
        confidence = Confidence.MEDIUM
        rationale = "The source is part of a material conflict and cannot be treated as resolving the proposition."
    elif role is AnalyticalRole.ADVERSE:
        status = PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED
        confidence = _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM)
        rationale = "The mapped evidence supports a contrary/limiting factual position, but M4 does not determine ultimate truth."
    elif evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION:
        status = PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED
        confidence = _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM)
        rationale = "The evidence establishes that the source makes the assertion, not that the asserted proposition is true."
    elif (
        role is AnalyticalRole.SUPPORTING
        and mapping.mapping_confidence is Confidence.HIGH
        and evidence.evidence_status in _DIRECT_RECORD_STATUSES
        and established_fact is not None
    ):
        status = PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE
        confidence = Confidence.HIGH
        rationale = "The direct record expresses an element-specific factual proposition that can be stated without extending beyond the source's documented content."
    elif role in {AnalyticalRole.SUPPORTING, AnalyticalRole.CORROBORATIVE}:
        status = PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED
        confidence = _cap_confidence(mapping.mapping_confidence, Confidence.MEDIUM)
        rationale = "The evidence supports the proposition or account but does not independently establish the element-specific factual proposition beyond its documented content."
    else:
        status = PropositionAssessmentStatus.UNRESOLVED
        confidence = Confidence.LOW
        rationale = "The mapped item is relevant context but does not safely establish an element-specific factual proposition."

    return AssessedProposition(
        text=proposition,
        status=status,
        confidence=confidence,
        evidence_keys=(mapping.evidence_key,),
        rationale=rationale,
    )


def apply_corroboration(assessments: Iterable[EvidenceAssessment]) -> tuple[EvidenceAssessment, ...]:
    """Promote independent overlapping support to corroborative, never by source count alone."""
    items = tuple(assessments)
    converted: list[EvidenceAssessment] = []
    for index, item in enumerate(items):
        evidence = item.mapping.evidence
        if item.analytical_role is not AnalyticalRole.SUPPORTING or evidence.source_type not in _INDEPENDENT_TYPES:
            converted.append(item)
            continue
        overlaps = any(
            other.mapping.evidence_key != item.mapping.evidence_key
            and other.analytical_role is AnalyticalRole.SUPPORTING
            and _independent_source_family(other.mapping.evidence) != _independent_source_family(evidence)
            and _token_overlap(
                _claim_key(evidence.summary),
                _claim_key(other.mapping.evidence.summary),
            ) >= 0.25
            for other_index, other in enumerate(items)
            if other_index != index
        )
        if overlaps:
            converted.append(
                EvidenceAssessment(
                    mapping=item.mapping,
                    analytical_role=AnalyticalRole.CORROBORATIVE,
                    assessment_confidence=_cap_confidence(item.assessment_confidence, Confidence.MEDIUM),
                    assessment_rationale="An independent source materially overlaps another supporting source and is treated as corroborative rather than independent proof of the whole element.",
                )
            )
        else:
            converted.append(item)
    return tuple(converted)


def _independent_source_family(evidence: EvidenceReference) -> str:
    if evidence.source_type in _CLAIMANT_TYPES:
        return "claimant"
    if evidence.source_type in _RESPONDENT_TYPES or evidence.source_type is EvidenceSourceType.EMPLOYER_RECORD:
        return "respondent-employer"
    if evidence.source_type is EvidenceSourceType.INDEPENDENT_MEDICAL:
        return "medical"
    if evidence.source_type is EvidenceSourceType.OCCUPATIONAL_HEALTH:
        return "oh"
    if evidence.source_type is EvidenceSourceType.INSURER_RECORD:
        return "insurer"
    if evidence.source_type is EvidenceSourceType.TRIBUNAL_RECORD:
        return "tribunal"
    return evidence.source_type.value


def detect_conflict(
    element_id: str,
    assessments: Iterable[EvidenceAssessment],
) -> tuple[tuple[EvidenceAssessment, ...], DisputedMatter | None]:
    """Detect only explicit incompatible positions on the same factual proposition.

    Different parties, different documents, silence, or loose lexical overlap are
    insufficient.  Both sides must express materially incompatible positions on
    an identifiable common proposition topic.
    """
    items = tuple(assessments)
    claimant_positions: list[tuple[EvidenceAssessment, str]] = []
    respondent_positions: list[tuple[EvidenceAssessment, str]] = []

    for item in items:
        evidence = item.mapping.evidence
        text = _normalise(evidence.summary)
        if _is_claimant_position(evidence, text):
            for topic in _affirmative_topics(text):
                claimant_positions.append((item, topic))
        if _is_respondent_position(evidence, text):
            for topic in _negative_topics(text):
                respondent_positions.append((item, topic))

    shared_topics = {
        left_topic
        for _, left_topic in claimant_positions
        for _, right_topic in respondent_positions
        if left_topic == right_topic
    }
    if not shared_topics:
        return items, None

    # One structured dispute per element in M4 v1.0: choose the first stable
    # shared topic and include only sources that address that same proposition.
    topic = sorted(shared_topics)[0]
    claimant = [item for item, item_topic in claimant_positions if item_topic == topic]
    contrary = [item for item, item_topic in respondent_positions if item_topic == topic]
    conflict_keys = {a.mapping.evidence_key for a in claimant + contrary}
    converted = tuple(
        EvidenceAssessment(
            mapping=item.mapping,
            analytical_role=AnalyticalRole.CONFLICTING,
            assessment_confidence=Confidence.MEDIUM,
            assessment_rationale=f"The source takes a materially incompatible position on the same factual proposition ({_topic_label(topic)}); M4 does not resolve credibility.",
        )
        if item.mapping.evidence_key in conflict_keys else item
        for item in items
    )
    dispute = DisputedMatter(
        proposition=f"Whether {_topic_label(topic)} remains disputed.",
        claimant_position=f"Claimant material contains an affirmative position concerning {_topic_label(topic)}.",
        respondent_position=f"Respondent/employer material contains an incompatible denial concerning {_topic_label(topic)}.",
        claimant_evidence=tuple(evidence_with_role(a.mapping.evidence, AnalyticalRole.CONFLICTING) for a in claimant),
        respondent_evidence=tuple(evidence_with_role(a.mapping.evidence, AnalyticalRole.CONFLICTING) for a in contrary),
        presently_established="The current record establishes that materially incompatible positions are recorded on the same factual proposition.",
        remains_unresolved="M4 does not determine which account is correct or resolve credibility.",
    )
    return converted, dispute


def gap_for_element(
    element_id: str,
    assessments: Iterable[EvidenceAssessment],
) -> EvidentialGap | None:
    """Create a specific material gap only where the element policy justifies it.

    Gap wording distinguishes a missing source category from an available source
    whose mapped excerpt does not establish the required fact.
    """
    rule = _GAP_RULES.get(element_id)
    if rule is None:
        return None
    items = tuple(assessments)
    if _has_required_element_fact(element_id, items):
        return None

    description, reason, target = _gap_wording(element_id, items, rule)
    return EvidentialGap(
        description=description,
        related_element_id=element_id,
        materiality=rule.materiality,
        reason=reason,
        suggested_evidence_target=target,
    )


def _has_required_element_fact(element_id: str, items: Iterable[EvidenceAssessment]) -> bool:
    for assessment in items:
        mapping = assessment.mapping
        evidence = mapping.evidence
        if assessment.analytical_role not in {
            AnalyticalRole.SUPPORTING,
            AnalyticalRole.CORROBORATIVE,
            AnalyticalRole.ADVERSE,
        }:
            continue
        if evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION:
            continue
        text = _normalise(evidence.summary)

        if element_id in {"EK-RECIPIENT", "EK-DIRECT-KNOWLEDGE", "RA-KNOWLEDGE"}:
            if _direct_employer_communication_fact(evidence, text):
                return True
        elif element_id == "EK-DISADVANTAGE-KNOWLEDGE":
            if _direct_employer_communication_fact(evidence, text) and _contains_any(
                text,
                "disadvantage", "difficulty", "travel", "commut", "fatigue", "anxiety", "work from home", "home working", "phased return",
            ):
                return True
        elif element_id == "RA-REASONABLENESS":
            if _contains_any(text, "feasible", "feasibility", "effective", "effectiveness", "operational", "trial", "practicable", "practical") and _adjustment_signal(text):
                return True
        elif element_id == "RA-FAILURE":
            if evidence.source_type is EvidenceSourceType.EMPLOYER_RECORD and _contains_any(
                text, "refused", "declined", "rejected", "approved", "agreed", "decision", "will not", "cannot accommodate", "can accommodate",
            ) and _adjustment_signal(text):
                return True
        elif element_id == "LIM-PRESENTATION":
            if _procedural_source(evidence) and _procedural_date_fact(evidence, text):
                return True
        elif element_id == "LIM-RESPONDENT-POSITION":
            if _respondent_source_present(evidence) and _limitation_position_signal(text):
                return True
        elif element_id == "DA-JUSTIFICATION":
            if _respondent_source_present(evidence) and _contains_any(
                text, "legitimate aim", "proportionate", "proportionality", "justification", "objectively justified",
            ):
                return True
    return False


def _gap_wording(element_id: str, items: tuple[EvidenceAssessment, ...], rule: GapRule) -> tuple[str, str, str]:
    evidences = tuple(item.mapping.evidence for item in items)

    if element_id == "LIM-RESPONDENT-POSITION" and any(_respondent_source_present(ev) for ev in evidences):
        return (
            "Specific limitation position within the mapped respondent pleading or correspondence.",
            "Respondent pleading/correspondence is present in the mapped evidence, but the assessed excerpt does not clearly state the material limitation position required for this element.",
            "The relevant ET3/Grounds of Resistance/respondent passage stating the limitation case, including the act/date/continuing-conduct position relied upon.",
        )

    if element_id == "LIM-PRESENTATION" and any(_procedural_source(ev) for ev in evidences):
        return (
            "Specific claim-presentation and/or ACAS Early Conciliation date information within the mapped procedural material.",
            "Procedural/ACAS material is present in the mapped evidence, but the assessed excerpt does not clearly establish the required presentation or Early Conciliation date(s).",
            "The passage or certificate field recording the relevant ET1 presentation/receipt and ACAS Early Conciliation dates.",
        )

    if element_id == "DA-JUSTIFICATION" and any(_respondent_source_present(ev) for ev in evidences):
        return (
            "Specific justification case within the mapped respondent material.",
            "Respondent material is present, but the assessed excerpt does not clearly identify the asserted legitimate aim and proportionality case.",
            "The respondent passage expressly setting out the legitimate aim and proportionality/justification case.",
        )

    return rule.description, rule.reason, rule.target


def _element_specific_established_fact(element_id: str, mapping: EvidenceMapping) -> str | None:
    evidence = mapping.evidence
    if mapping.mapping_confidence is not Confidence.HIGH:
        return None
    if evidence.evidence_status not in _DIRECT_RECORD_STATUSES:
        return None
    if evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION:
        return None

    text = _normalise(evidence.summary)

    if element_id == "EK-RECIPIENT" and _direct_employer_communication_fact(evidence, text):
        return "The direct correspondence records communication or receipt of health/return-to-work information involving identifiable CACI personnel."
    if element_id == "EK-DIRECT-KNOWLEDGE" and _direct_employer_communication_fact(evidence, text):
        return "The direct correspondence records CACI personnel receiving, acknowledging, replying to, or discussing health/return-to-work information."
    if element_id in {"EK-INFORMATION", "RA-DISABILITY", "DA-DISABILITY"} and _medical_condition_fact(evidence, text):
        return "The direct medical/insurer record documents a health condition or health-related functional information concerning the claimant."
    if element_id in {"RA-ADJUSTMENT", "RA-PROPOSED-ADJUSTMENT"} and _adjustment_signal(text):
        phrase = _first_adjustment_phrase(text)
        return f"The direct record documents a proposal or request concerning {phrase}."
    if element_id == "RA-KNOWLEDGE" and _direct_employer_communication_fact(evidence, text):
        return "The direct correspondence records CACI personnel receiving or discussing health/adjustment-related information."
    if element_id == "LIM-PRESENTATION" and _procedural_source(evidence) and _procedural_date_fact(evidence, text):
        date_text = _first_date(evidence.summary) or (evidence.date.isoformat() if evidence.date else "a procedural date")
        return f"The mapped procedural record records {date_text} in the claim/ACAS procedural context."
    if element_id in {"LIM-DATES", "LIM-ACTS"}:
        date_text = _first_date(evidence.summary)
        if date_text and _contains_any(text, "letter", "email", "meeting", "act", "omission", "decision", "failure", "event"):
            return f"The direct record documents a relevant event or communication dated {date_text}."
    return None


def _direct_employer_communication_fact(evidence: EvidenceReference, text: str) -> bool:
    employer_link = evidence.source_type is EvidenceSourceType.EMPLOYER_RECORD or evidence.evidence_status is EvidenceStatus.EMPLOYER_EVIDENCE
    communication = _contains_any(
        text,
        "received", "receipt", "acknowledged", "acknowledge", "replied", "reply", "discussed", "discussion", "sent to", "emailed", "informed", "told",
    )
    health_context = _contains_any(
        text,
        "medical", "health", "disability", "psychiatr", "sickness", "return to work", "return-to-work", "phased return", "adjustment", "occupational health", "unum",
    )
    return employer_link and communication and health_context


def _medical_condition_fact(evidence: EvidenceReference, text: str) -> bool:
    source_ok = evidence.source_type in {
        EvidenceSourceType.INDEPENDENT_MEDICAL,
        EvidenceSourceType.OCCUPATIONAL_HEALTH,
        EvidenceSourceType.INSURER_RECORD,
    }
    condition = _contains_any(
        text,
        "diagnos", "condition", "psychiatr", "mental health", "depression", "anxiety", "personality disorder", "incapacity", "unfit for work", "fit for work",
    )
    return source_ok and condition


def _adjustment_signal(text: str) -> bool:
    return _contains_any(
        text,
        "reasonable adjustment", "adjustment", "work from home", "home working", "working from home", "phased return", "reduced hours", "changed duties", "flexible working",
    )


def _first_adjustment_phrase(text: str) -> str:
    for phrase in (
        "working from home", "work from home", "home working", "a phased return", "phased return", "reduced hours", "changed duties", "flexible working", "an adjustment",
    ):
        if phrase in text:
            return phrase
    return "an adjustment"


def _procedural_source(evidence: EvidenceReference) -> bool:
    text = _normalise(f"{evidence.document_name} {evidence.summary}")
    return evidence.source_type is EvidenceSourceType.TRIBUNAL_RECORD or _contains_any(
        text,
        "acas", "early conciliation", "et1", "claim form", "employment tribunal", "tribunal claim",
    )


def _procedural_date_fact(evidence: EvidenceReference, text: str) -> bool:
    if not _contains_any(text, "acas", "early conciliation", "et1", "presented", "presentation", "claim form", "receipt", "received"):
        return False
    return evidence.date is not None or _first_date(evidence.summary) is not None


def _respondent_source_present(evidence: EvidenceReference) -> bool:
    if evidence.source_type in _RESPONDENT_TYPES or evidence.evidence_status is EvidenceStatus.RESPONDENT_EVIDENCE:
        return True
    text = _normalise(evidence.document_name)
    return _contains_any(text, "et3", "grounds of resistance", "respondent submission", "respondent's submission", "respondent position")


def _limitation_position_signal(text: str) -> bool:
    return _contains_any(
        text,
        "out of time", "time limit", "limitation", "continuing act", "continuing conduct", "conduct extending over", "just and equitable", "section 123", "s.123", "separate act", "single act",
    )


def _is_claimant_position(evidence: EvidenceReference, text: str) -> bool:
    if evidence.source_type not in _CLAIMANT_TYPES and evidence.evidence_status is not EvidenceStatus.CLAIMANT_EVIDENCE:
        return False
    # A known non-claimant author overrides a claimant-container classification
    # for conflict detection without mutating provenance itself.
    if evidence.author and not _claimant_author(evidence.author):
        return False
    if _known_non_claimant_name(evidence.document_name):
        return False
    return bool(_affirmative_topics(text))


def _is_respondent_position(evidence: EvidenceReference, text: str) -> bool:
    if not (_respondent_source_present(evidence) or evidence.evidence_status is EvidenceStatus.EMPLOYER_EVIDENCE):
        return False
    return bool(_negative_topics(text))


def _affirmative_topics(text: str) -> frozenset[str]:
    topics: set[str] = set()
    if _contains_any(text, "received", "was received", "sent to", "sent caci", "provided to", "emailed to", "gave caci", "told caci", "informed caci") and _contains_any(
        text, "medical", "recommendation", "report", "diagnosis", "information", "condition", "adjustment",
    ):
        topics.add("receipt-of-information")
    if _contains_any(text, "knew", "aware", "had knowledge", "was informed") and _contains_any(
        text, "disability", "condition", "medical", "recommendation", "adjustment", "health",
    ):
        topics.add("knowledge-awareness")
    if _contains_any(text, "continued", "continuing", "ongoing", "remained", "continued failure", "continuing omission") and _contains_any(
        text, "failure", "omission", "conduct", "act", "adjustment", "discrimination",
    ):
        topics.add("continuing-conduct")
    return frozenset(topics)


def _negative_topics(text: str) -> frozenset[str]:
    topics: set[str] = set()
    receipt_object = _contains_any(
        text, "medical", "recommendation", "report", "diagnosis", "information", "condition", "adjustment",
    )
    explicit_non_receipt = _contains_any(text, "did not receive", "never received", "not received", "was not sent", "no record of receipt")
    denied_receipt = _contains_any(text, "deny", "denied", "denies") and _contains_any(text, "receive", "received", "receipt")
    if receipt_object and (explicit_non_receipt or denied_receipt):
        topics.add("receipt-of-information")
    if _contains_any(text, "not aware", "unaware", "no knowledge", "did not know", "not informed") and _contains_any(
        text, "disability", "condition", "medical", "recommendation", "adjustment", "health",
    ):
        topics.add("knowledge-awareness")
    if _contains_any(text, "no continuing", "single act", "one-off", "not continuing", "ended in") and _contains_any(
        text, "failure", "omission", "conduct", "act", "adjustment", "discrimination",
    ):
        topics.add("continuing-conduct")
    return frozenset(topics)


def _topic_label(topic: str) -> str:
    return {
        "receipt-of-information": "the relevant medical/adjustment information was received by CACI",
        "knowledge-awareness": "CACI had the relevant knowledge or awareness",
        "continuing-conduct": "the alleged failure or conduct continued over time",
    }.get(topic, topic.replace("-", " "))


def _claimant_author(author: str) -> bool:
    value = _normalise(author)
    return "arshad" in value or "shafi" in value or value in {"claimant", "mr shafi"}


def _known_non_claimant_name(document_name: str) -> bool:
    value = _normalise(document_name)
    return _contains_any(value, "terry williamson", "alison brooks", "caci hr", "head of hr", "line manager")


def _is_explicit_adverse(evidence: EvidenceReference, text: str) -> bool:
    if not any(phrase in text for phrase in _DENIAL_PHRASES):
        return False
    return evidence.source_type in _RESPONDENT_TYPES or evidence.evidence_status in {
        EvidenceStatus.RESPONDENT_EVIDENCE,
        EvidenceStatus.EMPLOYER_EVIDENCE,
    }


def _record_proposition(evidence: EvidenceReference) -> str:
    label = evidence.evidence_status.value.replace("_", " ")
    return f"The mapped {label} contains factual material relevant to this element; M4 does not promote the raw excerpt itself into an established proposition."


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _claim_key(value: str) -> str:
    return " ".join(_WORD_RE.findall(value.casefold()))


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_WORD_RE.findall(left))
    right_tokens = set(_WORD_RE.findall(right))
    stop = {"the", "and", "that", "this", "with", "from", "were", "was", "have", "had", "for", "not", "i", "a", "an", "it", "my", "about", "caci", "claimant", "respondent", "employer"}
    left_tokens -= stop
    right_tokens -= stop
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _first_date(value: str) -> str | None:
    match = _DATE_RE.search(value)
    return match.group(0) if match else None


def _contains_any(value: str, *phrases: str) -> bool:
    return any(phrase in value for phrase in phrases)


def _cap_confidence(value: Confidence, cap: Confidence) -> Confidence:
    rank = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
    return value if rank[value] <= rank[cap] else cap


__all__ = [
    "GapRule",
    "apply_corroboration",
    "assess_proposition",
    "assessment_role",
    "detect_conflict",
    "evidence_with_role",
    "gap_for_element",
]
