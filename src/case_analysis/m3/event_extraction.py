"""Calibrated source-event-first chronology extraction for Sprint 2.4 M3.

Calibration v1.1 discovers factual source events once per canonical M2 evidence
item and only afterwards projects those events through the frozen M2
``EvidenceUse`` relationships.  M4 proposition links remain the evidential
boundary: raw summary text may enrich proposition-anchored evidence, but cannot
create a chronology event merely because it contains a date or interesting
wording.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Final
from uuid import UUID, uuid5

from legal_analysis.enums import AnalyticalRole, EvidenceStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult
from legal_analysis.models import EvidenceReference
from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY

from case_analysis.m2.evidence_identity import assert_compatible_canonical_evidence
from case_analysis.m2.matrices import CaseEvidenceRecord, CaseMatrices, EvidencePropositionLink, EvidenceUse

from .date_parsing import first_temporal_expression, parse_temporal_expressions
from .models import (
    CHRONOLOGY_PROFILE_VERSION,
    DatePrecision,
    EventAssertion,
    EventStatus,
    EventType,
    ExtractionBasis,
    PartialDate,
    TemporalExtent,
    TemporalKind,
    TimingStatus,
)

CHRONOLOGY_EXTRACTION_POLICY_VERSION: Final[str] = "chronology-extraction-policy/1.1"
_ASSERTION_NAMESPACE: Final[UUID] = UUID("9343f1d8-3f19-4ed1-b38e-9c81b471d9b1")


@dataclass(frozen=True, slots=True)
class EventSignalRule:
    """One versioned profile permission for a calibrated factual predicate.

    ``signals`` contains factual-predicate IDs rather than free-form lexical
    triggers.  The field name is retained for source compatibility with the
    experimental M3 implementation; source-event discovery itself is performed
    by the global calibrated predicate registry below.
    """

    event_type: EventType
    signals: tuple[str, ...]
    communication_event: bool = False

    def __post_init__(self) -> None:
        cleaned = tuple(str(item).strip() for item in self.signals if str(item).strip())
        if not cleaned:
            raise ValueError("EventSignalRule.signals must not be empty.")
        object.__setattr__(self, "signals", cleaned)


@dataclass(frozen=True, slots=True)
class EventExtractionProfile:
    """Exact versioned projection policy for one controlled legal element."""

    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    event_capable: bool
    rules: tuple[EventSignalRule, ...] = ()
    allow_proposition_only: bool = False
    profile_version: str = CHRONOLOGY_PROFILE_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "profile_version",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty.")
        object.__setattr__(self, "rules", tuple(self.rules))
        if self.event_capable and not self.rules:
            raise ValueError("Event-capable profiles require at least one predicate rule.")
        if not self.event_capable and (self.rules or self.allow_proposition_only):
            raise ValueError("Disabled profiles must not define projection behaviour.")

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.issue_definition_id,
            self.issue_definition_version,
            self.element_id,
        )

    @property
    def predicate_ids(self) -> frozenset[str]:
        return frozenset(item for rule in self.rules for item in rule.signals)


@dataclass(frozen=True, slots=True)
class _FactualPredicate:
    """Deterministic factual materiality rule used before legal projection."""

    predicate_id: str
    event_type: EventType
    action_patterns: tuple[str, ...]
    object_markers: tuple[str, ...] = ()
    communication_event: bool = False
    header_date_eligible: bool = False
    contextual_date_eligible: bool = False
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.predicate_id.strip():
            raise ValueError("predicate_id must not be empty.")
        if not self.action_patterns:
            raise ValueError("Factual predicates require action patterns.")


@dataclass(frozen=True, slots=True)
class _SourceUnit:
    block_ordinal: int
    clause_ordinal: int
    subevent_ordinal: int
    text: str
    block_text: str

    @property
    def coordinate(self) -> tuple[int, int, int]:
        return (self.block_ordinal, self.clause_ordinal, self.subevent_ordinal)


@dataclass(frozen=True, slots=True)
class _SourceEventCandidate:
    """Private factual event discovered before any issue/element projection."""

    source_unit_coordinate: tuple[int, int, int]
    evidence_key: str
    description: str
    normalized_event_core: str
    predicate_id: str
    event_type: EventType
    temporal_extent: TemporalExtent | None
    extraction_basis: ExtractionBasis
    direct_anchor_fingerprints: frozenset[str] = frozenset()
    timing_anchor_fingerprints: frozenset[str] = frozenset()
    source_event_ordinal: int = -1

    @property
    def sort_key(self) -> tuple[int, int, int, int, str, str, str]:
        predicate = _PREDICATES[self.predicate_id]
        return (
            *self.source_unit_coordinate,
            predicate.priority,
            self.event_type.value,
            self.normalized_event_core,
            self.description.casefold(),
        )


@dataclass(frozen=True, slots=True)
class _EvidenceOccurrence:
    issue_definition_id: str
    issue_definition_version: str
    issue_analysis_id: str
    element_ordinal: int
    evidence_assessment_ordinal: int
    evidence_key: str
    evidence: EvidenceReference

    @property
    def rank(self) -> tuple[str, str, str, int, int]:
        return (
            self.issue_definition_id,
            self.issue_definition_version,
            self.issue_analysis_id,
            self.element_ordinal,
            self.evidence_assessment_ordinal,
        )


# ---------------------------------------------------------------------------
# Controlled factual predicates
# ---------------------------------------------------------------------------


def _predicate(
    predicate_id: str,
    event_type: EventType,
    *action_patterns: str,
    objects: tuple[str, ...] = (),
    communication: bool = False,
    header_date: bool = False,
    contextual_date: bool = False,
    priority: int = 100,
) -> _FactualPredicate:
    return _FactualPredicate(
        predicate_id=predicate_id,
        event_type=event_type,
        action_patterns=tuple(action_patterns),
        object_markers=tuple(item.casefold() for item in objects),
        communication_event=communication,
        header_date_eligible=header_date,
        contextual_date_eligible=contextual_date,
        priority=priority,
    )


_PREDICATE_VALUES: Final[tuple[_FactualPredicate, ...]] = (
    _predicate(
        "employment.change",
        EventType.EMPLOYMENT,
        r"\b(?:demoted|regraded|downgraded|dismissed|promoted)\b",
        r"\b(?:salary|pay|role|grade|duties?)\s+(?:was|were|had been)?\s*(?:reduced|cut|changed|removed)\b",
        r"\b(?:reduced|cut)\s+(?:his|her|the claimant'?s)?\s*(?:salary|pay)\b",
        objects=("role", "grade", "salary", "pay", "duties", "admin"),
        contextual_date=True,
        priority=10,
    ),
    _predicate(
        "medical.deterioration",
        EventType.MEDICAL,
        r"\b(?:relapsed|suffered a relapse|experienced a relapse|condition deteriorated|health deteriorated|became unfit)\b",
        r"\b(?:relapse|deterioration)\s+(?:followed|occurred|happened|was reported)\b",
        r"\b(?:caused|resulted in|led to|triggered)\s+(?:a\s+)?(?:catastrophic\s+|severe\s+|significant\s+)?relapse\b",
        objects=("relapse", "relapsed", "condition", "health", "incapacity", "unfit", "medical"),
        contextual_date=True,
        priority=12,
    ),
    _predicate(
        "medical.assessment",
        EventType.MEDICAL,
        r"\b(?:diagnosed|assessed|examined|certified|found|concluded|advised)\b",
        r"\b(?:fit|unfit)\s+for\s+work\b",
        objects=("medical", "doctor", "gp", "psychiat", "occupational health", "oh", "fit for work", "unfit for work", "diagnosis"),
        priority=18,
    ),
    _predicate(
        "adjustment.request_or_decision",
        EventType.ADJUSTMENT_PROPOSAL,
        r"\b(?:requested|asked for|proposed|offered|agreed|approved|implemented|refused|declined|rejected)\b",
        r"\b(?:proposal|request)\b",
        objects=("phased return", "phased-return", "home working", "work from home", "remote working", "remote work", "flexible hours", "reduced hours", "workplace adjustment", "reasonable adjustment"),
        communication=True,
        header_date=True,
        priority=20,
    ),
    _predicate(
        "return_to_work.meeting",
        EventType.RETURN_TO_WORK,
        r"\b(?:meeting\s+(?:occurred|took place|was held|may have occurred)|met|attended\s+(?:a|the)?\s*meeting)\b",
        objects=("return-to-work", "return to work", "rehabilitation", "work trial", "phased return"),
        contextual_date=True,
        priority=22,
    ),
    _predicate(
        "return_to_work.rehabilitation",
        EventType.RETURN_TO_WORK,
        r"\b(?:began|commenced|started|ended|stopped|abandoned|attempted|undertook|returned)\b",
        objects=("rehabilitation", "return-to-work", "return to work", "work trial", "phased return"),
        contextual_date=True,
        priority=24,
    ),
    _predicate(
        "capability.action",
        EventType.CAPABILITY,
        r"\b(?:commenced|started|initiated|issued|sent|invited|reviewed|referred|requested|ended|closed|meeting occurred|meeting took place|meeting was held)\b",
        objects=("capability", "employment status review", "medical evidence", "occupational health referral", "oh referral"),
        communication=True,
        header_date=True,
        priority=26,
    ),
    _predicate(
        "payroll.communication",
        EventType.COMMUNICATION,
        r"\b(?:requested|asked for|sent|emailed|provided|supplied|withheld|responded|replied|failed to provide|not supplied|missing|forwarded)\b",
        r"\b(?:response|reply|email)\s+from\b",
        r"\b(?:will|shall)\s+(?:ensure\s+)?[^.;]{0,80}\bforwarded\b",
        objects=("payslip", "payslips", "payroll"),
        communication=True,
        header_date=True,
        contextual_date=True,
        priority=28,
    ),
    _predicate(
        "tribunal.procedure",
        EventType.TRIBUNAL_PROCEDURAL,
        r"\b(?:commenced|started|presented|submitted|filed|issued|ordered|listed|accepted|rejected|served|received)\b",
        objects=("acas", "early conciliation", "et1", "et3", "claim", "response", "tribunal", "hearing", "order"),
        communication=True,
        header_date=True,
        priority=30,
    ),
    _predicate(
        "knowledge.communication",
        EventType.COMMUNICATION,
        r"\b(?:informed|told|received|acknowledged|discussed|emailed|sent|notified|replied)\b",
        objects=("medical", "condition", "health", "incapacity", "disability", "fit note", "report", "occupational health", "oh"),
        communication=True,
        header_date=True,
        priority=35,
    ),
    _predicate(
        "work.communication",
        EventType.COMMUNICATION,
        r"\b(?:sent|emailed|wrote|replied|discussed|communicated|requested|asked|continued|carry on)\b",
        objects=("vf specification", "return-to-work", "return to work", "rehabilitation", "work plan", "phased return", "work arrangements", "work email"),
        communication=True,
        header_date=True,
        priority=40,
    ),
    _predicate(
        "absence.period",
        EventType.ABSENCE,
        r"\b(?:was absent|remained absent|began absence|commenced absence|ceased work|could not work|was unable to work|off work|absence continued|continued)\b",
        objects=("absence", "sickness", "work", "incapacity"),
        contextual_date=True,
        priority=45,
    ),
    _predicate(
        "benefit.action",
        EventType.BENEFIT,
        r"\b(?:paid|ceased|stopped|started|commenced|awarded|withdrawn|cancelled|ended)\b",
        objects=("phi", "income protection", "benefit", "benefits", "unum", "simply health"),
        contextual_date=True,
        priority=48,
    ),
)

_PREDICATES: Final[dict[str, _FactualPredicate]] = {
    item.predicate_id: item for item in _PREDICATE_VALUES
}
if len(_PREDICATES) != len(_PREDICATE_VALUES):
    raise RuntimeError("Duplicate chronology factual-predicate IDs are not permitted.")


# ---------------------------------------------------------------------------
# Exact versioned legal-use projection profiles
# ---------------------------------------------------------------------------


def _projection_rule(*predicate_ids: str) -> EventSignalRule:
    ids = tuple(predicate_ids)
    if not ids:
        raise ValueError("Projection rules require predicate IDs.")
    unknown = tuple(item for item in ids if item not in _PREDICATES)
    if unknown:
        raise ValueError(f"Unknown factual predicate IDs: {unknown!r}.")
    event_types = {_PREDICATES[item].event_type for item in ids}
    # EventSignalRule retains one event_type only for compatibility/diagnostics;
    # projection is based on the predicate IDs themselves.
    event_type = sorted(event_types, key=lambda item: item.value)[0]
    return EventSignalRule(
        event_type=event_type,
        signals=ids,
        communication_event=any(_PREDICATES[item].communication_event for item in ids),
    )


def _profile(
    issue_id: str,
    element_id: str,
    *predicate_ids: str,
    allow_proposition_only: bool = False,
) -> EventExtractionProfile:
    return EventExtractionProfile(
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        element_id=element_id,
        event_capable=bool(predicate_ids),
        rules=(_projection_rule(*predicate_ids),) if predicate_ids else (),
        allow_proposition_only=allow_proposition_only,
    )


def _disabled(issue_id: str, element_id: str) -> EventExtractionProfile:
    return EventExtractionProfile(
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        element_id=element_id,
        event_capable=False,
    )


# Profiles now constrain source-event compatibility/projection; they no longer
# independently discover factual occurrences.
_PROFILES: Final[tuple[EventExtractionProfile, ...]] = (
    _profile("RA-001", "RA-DISABILITY", "medical.deterioration", "medical.assessment", allow_proposition_only=True),
    _profile("RA-001", "RA-KNOWLEDGE", "knowledge.communication", "medical.assessment", "work.communication", allow_proposition_only=True),
    _disabled("RA-001", "RA-WORKPLACE-CONTEXT"),
    _profile("RA-001", "RA-DISADVANTAGE", "absence.period", "medical.deterioration"),
    _profile("RA-001", "RA-ADJUSTMENT", "adjustment.request_or_decision", "return_to_work.rehabilitation", "work.communication", allow_proposition_only=True),
    _disabled("RA-001", "RA-REASONABLENESS"),
    _profile("RA-001", "RA-FAILURE", "adjustment.request_or_decision", allow_proposition_only=True),
    _profile("RA-001", "RA-TIMING", "return_to_work.meeting", "return_to_work.rehabilitation", "adjustment.request_or_decision", "work.communication", "capability.action", "employment.change"),

    _profile("DA-001", "DA-DISABILITY", "medical.deterioration", "medical.assessment", allow_proposition_only=True),
    _profile("DA-001", "DA-SOMETHING-ARISING", "absence.period", "medical.deterioration", allow_proposition_only=True),
    _profile("DA-001", "DA-UNFAVOURABLE-TREATMENT", "employment.change", "capability.action", "benefit.action", allow_proposition_only=True),
    _disabled("DA-001", "DA-CAUSATION"),
    _profile("DA-001", "DA-KNOWLEDGE", "knowledge.communication", "work.communication", allow_proposition_only=True),
    _disabled("DA-001", "DA-JUSTIFICATION"),
    _profile("DA-001", "DA-TIMING", "employment.change", "capability.action", "work.communication", "adjustment.request_or_decision", "medical.deterioration"),

    _profile("EK-001", "EK-INFORMATION", "medical.deterioration", "medical.assessment", "knowledge.communication", allow_proposition_only=True),
    _profile("EK-001", "EK-RECIPIENT", "knowledge.communication", "work.communication", allow_proposition_only=True),
    _profile("EK-001", "EK-DIRECT-KNOWLEDGE", "knowledge.communication", "work.communication", "medical.assessment", allow_proposition_only=True),
    _disabled("EK-001", "EK-CONSTRUCTIVE-KNOWLEDGE"),
    _profile("EK-001", "EK-DISADVANTAGE-KNOWLEDGE", "knowledge.communication", "work.communication", "absence.period", allow_proposition_only=True),
    _disabled("EK-001", "EK-CLAIMANT-ASSERTIONS"),
    _disabled("EK-001", "EK-RESPONDENT-POSITION"),
    _disabled("EK-001", "EK-UNRESOLVED"),
    _profile("EK-001", "EK-TIMING", "work.communication", "knowledge.communication", "return_to_work.meeting", "return_to_work.rehabilitation", "adjustment.request_or_decision", "employment.change", "medical.deterioration"),

    _profile("LIM-001", "LIM-ACTS", *_PREDICATES.keys(), allow_proposition_only=True),
    _profile("LIM-001", "LIM-DATES", *_PREDICATES.keys(), allow_proposition_only=True),
    _disabled("LIM-001", "LIM-SEPARATE-OR-CONSEQUENCE"),
    _profile("LIM-001", "LIM-CONTINUING-CONDUCT", "absence.period", "benefit.action", "capability.action", "return_to_work.rehabilitation", "employment.change"),
    _profile("LIM-001", "LIM-END-DATE", "absence.period", "benefit.action", "capability.action", "return_to_work.rehabilitation", "employment.change"),
    _profile("LIM-001", "LIM-PRESENTATION", "tribunal.procedure", allow_proposition_only=True),
    _profile("LIM-001", "LIM-DELAY-EXPLANATION", "medical.deterioration", "medical.assessment", "absence.period"),
    _profile("LIM-001", "LIM-RESPONDENT-POSITION", "tribunal.procedure"),
    _disabled("LIM-001", "LIM-PREJUDICE-EVIDENCE"),
)

CHRONOLOGY_PROFILES: Final[dict[tuple[str, str, str], EventExtractionProfile]] = {
    item.key: item for item in _PROFILES
}


def _known_element_keys() -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (definition.definition_id, definition.version, element.element_id)
        for definition in DEFAULT_ISSUE_DEFINITION_REGISTRY.list_definitions()
        for element in definition.elements
    )


KNOWN_ELEMENT_KEYS: Final[frozenset[tuple[str, str, str]]] = _known_element_keys()

if len(CHRONOLOGY_PROFILES) != len(_PROFILES):
    raise RuntimeError("Duplicate chronology profile keys are not permitted.")
_unknown_profile_keys = frozenset(CHRONOLOGY_PROFILES).difference(KNOWN_ELEMENT_KEYS)
if _unknown_profile_keys:
    raise RuntimeError(
        "Chronology profiles reference unknown controlled elements: "
        + ", ".join(repr(item) for item in sorted(_unknown_profile_keys))
    )


def profile_for(issue_id: str, version: str, element_id: str) -> EventExtractionProfile:
    """Return an explicitly required exact versioned profile or fail closed."""

    key = (issue_id, version, element_id)
    if key not in KNOWN_ELEMENT_KEYS:
        raise ValueError(f"Unknown controlled legal element {key!r}.")
    try:
        return CHRONOLOGY_PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"No chronology extraction profile is registered for {key!r}.") from exc


def optional_profile_for(
    issue_id: str,
    version: str,
    element_id: str,
) -> EventExtractionProfile | None:
    """Return a profile, or ``None`` for a valid deliberately unprofiled element."""

    key = (issue_id, version, element_id)
    if key not in KNOWN_ELEMENT_KEYS:
        raise ValueError(f"Unknown controlled legal element {key!r}.")
    return CHRONOLOGY_PROFILES.get(key)


# ---------------------------------------------------------------------------
# Text quality and source-unit helpers
# ---------------------------------------------------------------------------

_GENERIC_MARKERS = (
    "contains factual material relevant to this element",
    "mapped evidence contains",
    "current evidence does not",
    "current record does not",
    "relevant event or communication dated",
    "factual material relevant",
    "proposal or request concerning an adjustment",
    "proposal or request concerning phased return",
    "proposal or request concerning home working",
)
_PREFIXES = (
    "the direct record documents ",
    "the direct correspondence records ",
    "the mapped procedural record records ",
    "the source records that ",
    "the source records an assertion that ",
    "the evidence supports that ",
)
_WORDS = re.compile(r"[a-z0-9]+")
_CLAUSE_SPLIT = re.compile(r"(?:(?<=[.!?])\s+|\s*[;•]\s*)")
_STRUCTURAL_HEADING = re.compile(
    r"^(?:section|part|chapter|appendix|exhibit|schedule|annex|contents?|table of contents)\b",
    re.I,
)
_METADATA_LINE = re.compile(r"^(?:from|sent|date|to|cc|subject)\s*:\s*", re.I)
_EMAIL_HEADER_LINE = re.compile(r"^(?P<name>from|sent|date|to|cc|subject)\s*:\s*(?P<value>.*)$", re.I)
_INLINE_EMAIL_HEADER = re.compile(
    r"(?<![A-Za-z])(?P<name>from|sent|date|to|cc|subject)\s*:\s*"
    r"(?P<value>.*?)(?=(?<![A-Za-z])(?:from|sent|date|to|cc|subject)\s*:|$)",
    re.I | re.S,
)
_EMAIL_ADDRESS = re.compile(r"<[^>]+>|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_INCOMPLETE_DATE_TAIL = re.compile(r"\b(?:on|dated|since|from|until|between)\s+\d{1,2}\.?\s*$", re.I)
_MONTH_CONTINUATION = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{4}\b",
    re.I,
)
_INCOMPLETE_CLAUSE_END = re.compile(
    r"(?:\.{3}|…|\b(?:and|or|but|then|the|a|an|to|of|for|from|with|about|"
    r"regarding|that|this|these|those|its|their|his|her)\.?\s*)$",
    re.I,
)
_PURPOSE_OR_DEPENDENT = re.compile(
    r"^(?:that|so that|in order that|to ensure(?: that)?|for the purpose of|"
    r"of|rather than|instead of|which|whereas|while|because|although|"
    r"with a view to|in relation to|as regards|as to)\b",
    re.I,
)
_LEGAL_CONCLUSION_RE = re.compile(
    r"\b(?:in breach of|breached|unlawful(?:ly)?|discriminat(?:ion|ory)|"
    r"contrary to|failed to comply with|statutory (?:test|duty)|liability|"
    r"prima facie|out of time|time[- ]barred|limitation position|"
    r"section\s+\d+|s\.\s*\d+)\b",
    re.I,
)
_LEGAL_ARGUMENT_TRANSITION_RE = re.compile(
    r"[,;]\s*(?:as such|accordingly|therefore|consequently|for that reason)\b",
    re.I,
)
_CONDITIONAL_COMMENTARY_RE = re.compile(
    r"(?:^|[,;]\s*)(?:if|unless|provided that|subject to)\b|"
    r"\bi believe\b|\bshould be considered\b|\bi ask that .*?reasons? be explained\b",
    re.I,
)
_PLEADING_POSITION_MARKERS = (
    "the claimant has failed to provide",
    "claimant has failed to provide",
    "the respondent contends",
    "respondent contends",
    "the respondent says",
    "respondent says",
    "the respondent denies",
    "respondent denies",
    "it is denied",
    "the claimant alleges",
    "claimant alleges",
    "the respondent submits",
    "respondent submits",
    "it is submitted",
    "the respondent avers",
    "respondent avers",
    "the claimant submits",
    "claimant submits",
    "the claimant's case is",
    "the respondent's case is",
)
_PROCEDURAL_EVENT_MARKERS = (
    "et1", "et3", "claim presented", "claim submitted", "response presented",
    "filed", "submitted", "accepted", "rejected", "listed", "ordered",
    "served", "commenced early conciliation",
)
_HEADING_MARKERS = (
    "medical background",
    "factual background",
    "documents relevant to",
    "relevant documents",
    "information requested",
    "long-term sickness absence policy",
    "long term sickness absence policy",
    "policy and procedure",
    "catastrophic relapse and permanent incapacity",
)
_EXACT_HEADING_LABELS = (
    "reasonable adjustments & information requested",
    "reasonable adjustments and information requested",
)
_BOILERPLATE_MARKERS = (
    "if you have received this transmission in error",
    "you have received this transmission in error",
    "received this transmission in error",
    "if you have received this email in error",
    "you have received this email in error",
    "received this email in error",
    "if you are not the intended recipient",
    "you are not the intended recipient",
    "not the intended recipient",
    "transmission in error",
    "email in error",
    "message in error",
    "this electronic message contains information",
    "this message and any attachments are confidential",
    "unauthorised use, disclosure or copying",
    "please notify the sender immediately",
    "please delete this message",
    "notify acas immediately",
    "acas working for everyone",
    "consider the environment before printing",
    "virus-free",
    "computer viruses",
)
_GENERIC_EVENT_DESCRIPTIONS = (
    "a proposal or request concerning an adjustment",
    "proposal or request concerning an adjustment",
    "a proposal or request concerning phased return",
    "proposal or request concerning phased return",
    "a proposal or request concerning home working",
    "proposal or request concerning home working",
    "an employment-related event occurred",
    "a communication was sent",
)
_DOCUMENT_MARKERS = (
    "document", "documents", "record", "records", "information", "evidence", "copy", "copies"
)
_AUTOREPLY_MARKERS = (
    "automatic reply", "auto reply", "out of office", "out-of-office", "away from the office"
)
_EMAIL_ENVELOPE_RE = re.compile(
    r"^email\s+\d+\s*[–—-]\s*.+?\((?P<date>[^)]*\d{4}[^)]*)\)",
    re.I,
)
_SECTION_BOUNDARY_RE = re.compile(
    r"^(?:relevance to|cross-reference|summary of|exhibits?|source and provenance)\b",
    re.I,
)
_TRAILING_INCOMPLETE_CONTINUATION_RE = re.compile(
    r"[,;]\s*(?:and|or|but|then)\b.*$",
    re.I,
)


def _normalise(value: str) -> str:
    return " ".join(str(value).casefold().replace("–", "-").replace("—", "-").split())


def _contains_marker(normalised_text: str, marker: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(marker.casefold()) + r"(?![a-z0-9])"
    return re.search(pattern, normalised_text) is not None


def _clean_clause(value: str) -> str:
    cleaned = " ".join(str(value).strip().split())
    cleaned = re.sub(r"^[\-–—*]+\s*", "", cleaned)
    return cleaned.strip(" ,;:-")


def _is_generic_proposition(text: str) -> bool:
    normal = _normalise(text)
    return any(marker in normal for marker in _GENERIC_MARKERS)


def _is_boilerplate(value: str) -> bool:
    normal = _normalise(value)
    return any(marker in normal for marker in _BOILERPLATE_MARKERS)


def _is_incomplete_date_clause(value: str) -> bool:
    if parse_temporal_expressions(value):
        return False
    return _INCOMPLETE_DATE_TAIL.search(_clean_clause(value)) is not None


def _is_incomplete_clause(value: str) -> bool:
    cleaned = _clean_clause(value)
    if not cleaned:
        return True
    if _INCOMPLETE_CLAUSE_END.search(cleaned):
        return True
    return cleaned.count("(") != cleaned.count(")") or cleaned.count("[") != cleaned.count("]")


def _is_pleading_position_without_procedural_event(value: str) -> bool:
    normal = _normalise(value)
    if not any(marker in normal for marker in _PLEADING_POSITION_MARKERS):
        return False
    return not any(_contains_marker(normal, marker) for marker in _PROCEDURAL_EVENT_MARKERS)


def _factual_clause(value: str) -> str:
    cleaned = _clean_clause(value)
    match = _LEGAL_CONCLUSION_RE.search(cleaned)
    if match and match.start() >= 12:
        prefix = cleaned[:match.start()]
        transitions = tuple(_LEGAL_ARGUMENT_TRANSITION_RE.finditer(prefix))
        if transitions:
            prefix = prefix[:transitions[-1].start()]
        if _clean_clause(prefix):
            cleaned = prefix
    return _clean_clause(cleaned)


def _is_legal_commentary(value: str) -> bool:
    if _LEGAL_CONCLUSION_RE.search(value) is None:
        return False
    normal = _normalise(value)
    return not any(_contains_marker(normal, marker) for marker in _PROCEDURAL_EVENT_MARKERS)


def _looks_like_heading_or_label(value: str) -> bool:
    cleaned = _clean_clause(value)
    if not cleaned:
        return True
    normal = _normalise(cleaned)
    if _STRUCTURAL_HEADING.match(cleaned):
        return True
    if normal in _EXACT_HEADING_LABELS:
        return True
    words = _WORDS.findall(normal)
    if not words:
        return True
    has_action = any(_predicate_matches(cleaned, predicate) for predicate in _PREDICATE_VALUES)
    if any(marker in normal for marker in _HEADING_MARKERS) and not has_action:
        return True
    letters = "".join(character for character in cleaned if character.isalpha())
    if letters and letters.isupper() and len(words) <= 12 and not has_action:
        return True
    if "&" in cleaned and len(words) <= 12 and not has_action:
        return True
    if len(words) <= 12 and normal.endswith((" background", " policy", " procedure")) and not has_action:
        return True
    return False


def _is_generic_event_description(value: str) -> bool:
    normal = _normalise(value)
    return any(normal == marker or normal.startswith(marker + " ") for marker in _GENERIC_EVENT_DESCRIPTIONS)


def _is_conditional_or_background(value: str) -> bool:
    cleaned = _clean_clause(value)
    if _PURPOSE_OR_DEPENDENT.search(cleaned):
        return True
    if _CONDITIONAL_COMMENTARY_RE.search(cleaned):
        # A completed transaction may still be factual even inside a conditional-looking clause.
        return not bool(re.search(
            r"\b(?:requested|proposed|offered|agreed|approved|implemented|refused|declined|rejected|"
            r"sent|emailed|issued|filed|presented|submitted|commenced|provided|demoted|regraded|relapsed)\b",
            cleaned,
            re.I,
        ))
    return False


def _is_long_document_request(value: str) -> bool:
    normal = _normalise(value)
    if not any(_contains_marker(normal, marker) for marker in _DOCUMENT_MARKERS):
        return False
    if not re.search(r"\b(?:request(?:ed)?|ask(?:ed)?|provide|copies of|any records)\b", normal):
        return False
    # Specific concise payslip/payroll transactions remain material.
    if any(_contains_marker(normal, marker) for marker in ("payslip", "payslips", "payroll")):
        if len(value) <= 220 and value.count(",") <= 1 and value.count(";") == 0:
            return False
    return (
        len(value) > 220
        or value.count(",") >= 2
        or value.count(";") >= 1
        or normal.count("copies of") >= 2
        or "any records" in normal
        or (" and " in normal and sum(_contains_marker(normal, marker) for marker in _DOCUMENT_MARKERS) >= 2)
    )


def _complete_factual_prefix(value: str) -> str:
    """Return a complete factual prefix without guessing a truncated tail."""

    cleaned = _factual_clause(value)
    if not cleaned or not _is_incomplete_clause(cleaned):
        return cleaned
    matches = tuple(_TRAILING_INCOMPLETE_CONTINUATION_RE.finditer(cleaned))
    for match in reversed(matches):
        prefix = _clean_clause(cleaned[:match.start()])
        if len(prefix) >= 10 and not _is_incomplete_clause(prefix):
            return prefix
    return cleaned


def _substantive_text(value: str) -> bool:
    cleaned = _factual_clause(value)
    if len(cleaned) < 10:
        return False
    if _is_boilerplate(cleaned) or _looks_like_heading_or_label(cleaned):
        return False
    if _is_incomplete_date_clause(cleaned) or _is_incomplete_clause(cleaned):
        return False
    if _is_generic_event_description(cleaned) or _is_long_document_request(cleaned):
        return False
    if _is_conditional_or_background(cleaned):
        return False
    if _is_pleading_position_without_procedural_event(cleaned):
        return False
    if _is_legal_commentary(cleaned):
        return False
    return True


def _base_from_proposition(text: str) -> str:
    cleaned = _clean_clause(text)
    lowered = cleaned.casefold()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if cleaned.casefold().startswith("that "):
        cleaned = cleaned[5:]
    return cleaned.rstrip(".")


def _remove_dates(value: str) -> str:
    text = value
    for item in reversed(parse_temporal_expressions(text)):
        text = text[:item.start_offset] + " " + text[item.end_offset:]
    return text


def _event_core(value: str) -> str:
    cleaned = _remove_dates(_base_from_proposition(value))
    normal = _normalise(cleaned)
    normal = re.sub(r"^(?:the source records that|the source records an assertion that|the evidence supports that)\s+", "", normal)
    normal = re.sub(r"[^a-z0-9£]+", " ", normal)
    return " ".join(normal.split()).strip()


def _normalise_wrapped_date(left: str, right: str) -> str:
    left_clean = _clean_clause(left)
    right_clean = _clean_clause(right)
    if _INCOMPLETE_DATE_TAIL.search(left_clean) and _MONTH_CONTINUATION.match(right_clean):
        left_clean = left_clean.rstrip(".")
    return _clean_clause(f"{left_clean} {right_clean}")


def _header_fields(summary: str) -> dict[str, str]:
    values: dict[str, str] = {}
    source = str(summary)
    for raw_line in source.splitlines():
        match = _EMAIL_HEADER_LINE.match(raw_line.strip())
        if match is None:
            continue
        key = match.group("name").casefold()
        value = _clean_clause(match.group("value"))
        if value and key not in values:
            values[key] = value

    flattened = " ".join(source.splitlines())
    for match in _INLINE_EMAIL_HEADER.finditer(flattened):
        key = match.group("name").casefold()
        value = _clean_clause(match.group("value"))
        if not value or key in values:
            continue
        values[key] = value
    return values


def _safe_sender_label(value: str) -> str:
    cleaned = _EMAIL_ADDRESS.sub("", _clean_clause(value))
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = _clean_clause(cleaned)
    if not cleaned or cleaned.casefold() in {"you", "me", "unknown", "sender"} or len(cleaned) > 80:
        return ""
    return cleaned


def _safe_header_subject(value: str) -> str:
    cleaned = _clean_clause(re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", value, flags=re.I))
    if not cleaned:
        return ""
    # Flattened final Subject fields may absorb the body. Keep only a short
    # leading subject phrase when it is identifiable.
    for known in (
        "VF specification",
        "Phased return",
        "Return-to-work discussion",
        "Return to work",
        "Payslips",
        "Payroll",
        "Capability review",
        "ACAS Early Conciliation",
        "ET1",
        "ET3",
    ):
        if cleaned.casefold().startswith(known.casefold()):
            return known
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    words = _WORDS.findall(first_sentence)
    if len(first_sentence) > 100 or len(words) > 12:
        return ""
    if _is_boilerplate(first_sentence) or _looks_like_heading_or_label(first_sentence):
        return ""
    if any(marker in _normalise(first_sentence) for marker in _AUTOREPLY_MARKERS):
        return ""
    return first_sentence.rstrip(".")


def _header_temporal_extent(summary: str) -> TemporalExtent | None:
    fields = _header_fields(summary)
    values: list[TemporalExtent] = []
    for key in ("sent", "date"):
        if key not in fields:
            continue
        parsed = parse_temporal_expressions(fields[key])
        if len(parsed) == 1:
            values.append(parsed[0].extent)
    if not values:
        return None
    first = values[0]
    return first if all(item == first for item in values[1:]) else None


def _source_date_extent(evidence: EvidenceReference) -> TemporalExtent | None:
    if evidence.date is None:
        return None
    partial = PartialDate(
        year=evidence.date.year,
        month=evidence.date.month,
        day=evidence.date.day,
        precision=DatePrecision.EXACT,
    )
    return TemporalExtent(
        kind=TemporalKind.POINT,
        start=partial,
        original_text=partial.display_text,
    )


def _body_text(summary: str) -> str:
    """Return body-oriented text while retaining useful flattened Subject tails."""

    source = str(summary)
    lines = source.splitlines()
    if len(lines) > 1:
        body_lines = [line for line in lines if not _METADATA_LINE.match(line.strip())]
        return "\n".join(body_lines)

    # For flattened Outlook extraction, remove From/Sent/Date/To/Cc fields but
    # keep the Subject tail because it may contain the only surviving body text.
    flattened = source
    matches = tuple(_INLINE_EMAIL_HEADER.finditer(flattened))
    if not matches:
        return flattened
    subject_match = next((item for item in matches if item.group("name").casefold() == "subject"), None)
    if subject_match is not None:
        return _clean_clause(subject_match.group("value"))
    return ""


def _coalesced_body_blocks(summary: str) -> tuple[str, ...]:
    lines = tuple(_clean_clause(item) for item in re.split(r"\r?\n+", _body_text(summary)))
    values: list[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer:
            values.append(buffer)
            buffer = ""

    for line in lines:
        if not line:
            flush()
            continue
        if _is_boilerplate(line) or _looks_like_heading_or_label(line):
            flush()
            continue
        if not buffer:
            buffer = line
            continue
        if _is_incomplete_date_clause(buffer) and _MONTH_CONTINUATION.match(line):
            buffer = _normalise_wrapped_date(buffer, line)
            continue
        if not re.search(r"[.!?]\s*$", buffer):
            buffer = _clean_clause(f"{buffer} {line}")
            continue
        flush()
        buffer = line
    flush()
    return tuple(values)


def _source_units_from_blocks(blocks: tuple[str, ...]) -> tuple[_SourceUnit, ...]:
    values: list[_SourceUnit] = []
    for block_ordinal, block in enumerate(blocks):
        clauses = tuple(
            _clean_clause(item)
            for item in _CLAUSE_SPLIT.split(block)
            if _clean_clause(item)
        )
        for clause_ordinal, clause in enumerate(clauses):
            factual = _factual_clause(clause)
            if not factual:
                continue
            values.append(
                _SourceUnit(
                    block_ordinal=block_ordinal,
                    clause_ordinal=clause_ordinal,
                    subevent_ordinal=0,
                    text=factual,
                    block_text=block,
                )
            )
    return tuple(values)


def _source_units(summary: str) -> tuple[_SourceUnit, ...]:
    return _source_units_from_blocks(_coalesced_body_blocks(summary))


def _email_envelope_temporal_extent(
    blocks: tuple[str, ...],
    block_ordinal: int,
) -> TemporalExtent | None:
    """Return a nearby explicit Email-N envelope date for communication body text."""

    lower = max(0, block_ordinal - 6)
    for index in range(block_ordinal, lower - 1, -1):
        block = blocks[index]
        if index != block_ordinal and _SECTION_BOUNDARY_RE.match(block):
            break
        match = _EMAIL_ENVELOPE_RE.match(block)
        if match is None:
            continue
        parsed = parse_temporal_expressions(match.group("date"))
        if len(parsed) == 1:
            return parsed[0].extent
        return None
    return None


# ---------------------------------------------------------------------------
# Predicate matching and source-event discovery
# ---------------------------------------------------------------------------


def _predicate_action_match(text: str, predicate: _FactualPredicate) -> re.Match[str] | None:
    for pattern in predicate.action_patterns:
        match = re.search(pattern, text, re.I)
        if match is not None:
            return match
    return None


def _predicate_matches(text: str, predicate: _FactualPredicate) -> bool:
    if _predicate_action_match(text, predicate) is None:
        return False
    if not predicate.object_markers:
        return True
    normal = _normalise(text)
    return any(_contains_marker(normal, marker) for marker in predicate.object_markers)


def _link_fingerprint(link: EvidencePropositionLink) -> str:
    return "|".join(
        (
            str(link.source_proposition_index),
            _normalise(link.text),
            link.status.value,
            link.confidence.value,
            ",".join(link.evidence_keys),
        )
    )


def _all_links(record: CaseEvidenceRecord) -> tuple[EvidencePropositionLink, ...]:
    by_value: dict[tuple[int, str, str, str, tuple[str, ...]], EvidencePropositionLink] = {}
    for use in record.uses:
        for link in use.proposition_links:
            key = (
                link.source_proposition_index,
                link.text,
                link.status.value,
                link.confidence.value,
                link.evidence_keys,
            )
            by_value.setdefault(key, link)
    return tuple(
        sorted(
            by_value.values(),
            key=lambda item: (
                _normalise(item.text),
                item.status.value,
                item.confidence.value,
                item.source_proposition_index,
                item.evidence_keys,
            ),
        )
    )


def _specific_proposition_predicates(
    link: EvidencePropositionLink,
    allowed: frozenset[str],
) -> tuple[_FactualPredicate, ...]:
    if _is_generic_proposition(link.text):
        return ()
    text = _factual_clause(_base_from_proposition(link.text))
    if not _substantive_text(text):
        return ()
    values = [
        _PREDICATES[predicate_id]
        for predicate_id in allowed
        if _predicate_matches(text, _PREDICATES[predicate_id])
    ]
    return tuple(sorted(values, key=lambda item: (item.priority, item.predicate_id)))


def _block_temporal_extent(unit: _SourceUnit) -> TemporalExtent | None:
    values = tuple(item.extent for item in parse_temporal_expressions(unit.block_text))
    if not values:
        return None
    first = values[0]
    return first if all(item == first for item in values[1:]) else None


def _source_unit_temporal_extent(
    unit: _SourceUnit,
    predicate: _FactualPredicate,
    evidence: EvidenceReference,
    *,
    envelope_temporal_extent: TemporalExtent | None = None,
) -> TemporalExtent | None:
    explicit = first_temporal_expression(unit.text)
    if explicit is not None:
        return explicit
    if predicate.contextual_date_eligible:
        contextual = _block_temporal_extent(unit)
        if contextual is not None:
            return contextual
    if predicate.header_date_eligible and predicate.communication_event:
        return (
            envelope_temporal_extent
            or _header_temporal_extent(evidence.summary)
            or _source_date_extent(evidence)
        )
    return None


def _prefer_predicates(matches: tuple[_FactualPredicate, ...]) -> tuple[_FactualPredicate, ...]:
    """Remove generic communication duplicates when a substantive predicate matches."""

    if not matches:
        return ()
    non_communication = tuple(item for item in matches if item.event_type is not EventType.COMMUNICATION)
    if non_communication:
        return non_communication
    # Several distinct communication predicates may be relevant, but one source
    # clause should have one factual identity. Keep the most specific/lowest-priority.
    return (min(matches, key=lambda item: (item.priority, item.predicate_id)),)


def _is_communication_envelope_label(value: str) -> bool:
    normal = _normalise(value)
    return bool(re.search(r"(?:^|\b)(?:email|response|reply)\s+from\b", normal))


def _collapse_envelope_label_candidates(
    values: tuple[_SourceEventCandidate, ...],
) -> tuple[_SourceEventCandidate, ...]:
    """Prefer substantive body content over a same-block communication label."""

    removed: set[int] = set()
    for index, candidate in enumerate(values):
        if index in removed or not _is_communication_envelope_label(candidate.description):
            continue
        for other_index, other in enumerate(values):
            if other_index == index or other_index in removed:
                continue
            if candidate.predicate_id != other.predicate_id:
                continue
            if candidate.source_unit_coordinate[0] != other.source_unit_coordinate[0]:
                continue
            if candidate.temporal_extent != other.temporal_extent:
                continue
            if _is_communication_envelope_label(other.description):
                continue
            removed.add(index)
            break
    return tuple(item for index, item in enumerate(values) if index not in removed)


def _body_candidates(
    record: CaseEvidenceRecord,
    evidence: EvidenceReference,
    discoverable: frozenset[str],
) -> tuple[_SourceEventCandidate, ...]:
    values: list[_SourceEventCandidate] = []
    blocks = _coalesced_body_blocks(evidence.summary)
    for unit in _source_units_from_blocks(blocks):
        description = _complete_factual_prefix(unit.text)
        if not _substantive_text(description):
            continue
        matches = tuple(
            sorted(
                (
                    _PREDICATES[predicate_id]
                    for predicate_id in discoverable
                    if _predicate_matches(description, _PREDICATES[predicate_id])
                ),
                key=lambda item: (item.priority, item.predicate_id),
            )
        )
        selected = _prefer_predicates(matches)
        for subevent_ordinal, predicate in enumerate(selected):
            envelope_temporal = (
                _email_envelope_temporal_extent(blocks, unit.block_ordinal)
                if predicate.communication_event
                else None
            )
            temporal = _source_unit_temporal_extent(
                unit,
                predicate,
                evidence,
                envelope_temporal_extent=envelope_temporal,
            )
            coordinate = (unit.block_ordinal, unit.clause_ordinal, subevent_ordinal)
            values.append(
                _SourceEventCandidate(
                    source_unit_coordinate=coordinate,
                    evidence_key=record.evidence_key,
                    description=description,
                    normalized_event_core=_event_core(description),
                    predicate_id=predicate.predicate_id,
                    event_type=predicate.event_type,
                    temporal_extent=temporal,
                    extraction_basis=ExtractionBasis.PROPOSITION_WITH_EVIDENCE_ENRICHMENT,
                )
            )
    return _collapse_envelope_label_candidates(tuple(values))


def _proposition_candidates(
    record: CaseEvidenceRecord,
    allowed: frozenset[str],
    links: tuple[EvidencePropositionLink, ...],
) -> tuple[_SourceEventCandidate, ...]:
    raw: list[tuple[str, _SourceEventCandidate]] = []
    for link in links:
        if link.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
            continue
        text = _factual_clause(_base_from_proposition(link.text))
        fingerprint = _link_fingerprint(link)
        for predicate in _specific_proposition_predicates(link, allowed):
            if _is_generic_event_description(text):
                continue
            temporal = first_temporal_expression(text)
            raw.append(
                (
                    fingerprint,
                    _SourceEventCandidate(
                        source_unit_coordinate=(1_000_000, 0, 0),
                        evidence_key=record.evidence_key,
                        description=text,
                        normalized_event_core=_event_core(text),
                        predicate_id=predicate.predicate_id,
                        event_type=predicate.event_type,
                        temporal_extent=temporal,
                        extraction_basis=ExtractionBasis.PROPOSITION,
                        direct_anchor_fingerprints=frozenset({fingerprint}),
                        timing_anchor_fingerprints=frozenset({fingerprint}) if temporal is not None else frozenset(),
                    ),
                )
            )

    # Combine equivalent proposition-only events independently of legal-use/link ordering.
    grouped: dict[tuple[str, str, TemporalExtent | None], list[tuple[str, _SourceEventCandidate]]] = defaultdict(list)
    for fingerprint, candidate in raw:
        grouped[(candidate.predicate_id, candidate.normalized_event_core, candidate.temporal_extent)].append(
            (fingerprint, candidate)
        )

    values: list[_SourceEventCandidate] = []
    for proposition_ordinal, key in enumerate(sorted(grouped, key=lambda item: (item[0], item[1], str(item[2])))):
        group = grouped[key]
        candidate = min(group, key=lambda item: item[1].description.casefold())[1]
        direct = frozenset(item[0] for item in group)
        timing = frozenset(
            item[0]
            for item in group
            if item[1].temporal_extent is not None
        )
        values.append(
            _SourceEventCandidate(
                source_unit_coordinate=(1_000_000, proposition_ordinal, 0),
                evidence_key=candidate.evidence_key,
                description=candidate.description,
                normalized_event_core=candidate.normalized_event_core,
                predicate_id=candidate.predicate_id,
                event_type=candidate.event_type,
                temporal_extent=candidate.temporal_extent,
                extraction_basis=ExtractionBasis.PROPOSITION,
                direct_anchor_fingerprints=direct,
                timing_anchor_fingerprints=timing,
            )
        )
    return tuple(values)




def _object_signature(text: str, predicate: _FactualPredicate) -> frozenset[str]:
    normal = _normalise(text).replace("-", " ")
    values = set()
    for marker in predicate.object_markers:
        canonical = _normalise(marker).replace("-", " ")
        if _contains_marker(normal, canonical):
            values.add(canonical)
    return frozenset(values)


def _merge_proposition_candidates_into_body(
    body: tuple[_SourceEventCandidate, ...],
    proposition: tuple[_SourceEventCandidate, ...],
) -> tuple[_SourceEventCandidate, ...]:
    """Prefer body events while preserving exact proposition anchoring metadata.

    A specific proposition that describes the same material subject as a richer
    body event must not create a duplicate event.  Exact factual-core matches
    preserve direct anchoring; broader body enrichment remains conservatively
    capped at supported status.
    """

    mutable = list(body)
    remaining: list[_SourceEventCandidate] = []
    for prop in proposition:
        predicate = _PREDICATES[prop.predicate_id]
        prop_objects = _object_signature(prop.description, predicate)
        match_index: int | None = None
        exact_core = False
        for index, candidate in enumerate(mutable):
            if candidate.predicate_id != prop.predicate_id:
                continue
            if candidate.normalized_event_core == prop.normalized_event_core:
                match_index = index
                exact_core = True
                break
            body_objects = _object_signature(candidate.description, predicate)
            if prop_objects and body_objects and prop_objects.intersection(body_objects):
                match_index = index
                break
        if match_index is None:
            remaining.append(prop)
            continue

        existing = mutable[match_index]
        direct = existing.direct_anchor_fingerprints
        timing = existing.timing_anchor_fingerprints
        if exact_core:
            direct = direct | prop.direct_anchor_fingerprints
            if existing.temporal_extent == prop.temporal_extent:
                timing = timing | prop.timing_anchor_fingerprints
        mutable[match_index] = _SourceEventCandidate(
            source_unit_coordinate=existing.source_unit_coordinate,
            evidence_key=existing.evidence_key,
            description=existing.description,
            normalized_event_core=existing.normalized_event_core,
            predicate_id=existing.predicate_id,
            event_type=existing.event_type,
            temporal_extent=existing.temporal_extent,
            extraction_basis=existing.extraction_basis,
            direct_anchor_fingerprints=direct,
            timing_anchor_fingerprints=timing,
        )

    return tuple(mutable + remaining)

def _header_topic(summary: str, subject: str) -> tuple[str, str] | None:
    searchable = _normalise(f"{subject} {summary}")
    topics = (
        (("vf specification",), "the VF specification", "work.communication"),
        (("phased return",), "a phased return", "work.communication"),
        (("return-to-work", "return to work"), "return-to-work arrangements", "work.communication"),
        (("payslip", "payslips", "payroll", "joanna eaton"), "payslips", "payroll.communication"),
        (("capability review", "capability process"), "the capability review", "capability.action"),
    )
    for markers, label, predicate_id in topics:
        if any(_contains_marker(searchable, marker) for marker in markers):
            return label, predicate_id
    return None


def _header_topic_represented_by_body(
    label: str,
    body_candidates: tuple[_SourceEventCandidate, ...],
) -> bool:
    """Return whether a substantive body event already represents the header topic."""

    topic = _normalise(label).replace("-", " ")
    for candidate in body_candidates:
        text = _normalise(candidate.description).replace("-", " ")
        if topic and topic in text:
            return True
        if "return to work" in topic and candidate.event_type in {
            EventType.RETURN_TO_WORK,
            EventType.ADJUSTMENT_PROPOSAL,
        }:
            return True
        if "phased return" in topic and candidate.event_type in {
            EventType.RETURN_TO_WORK,
            EventType.ADJUSTMENT_PROPOSAL,
        }:
            return True
        if "payslip" in topic and candidate.predicate_id == "payroll.communication":
            return True
        if "capability" in topic and candidate.event_type is EventType.CAPABILITY:
            return True
        if "vf specification" in topic and candidate.predicate_id == "work.communication":
            return True
    return False


def _header_fallback_candidate(
    record: CaseEvidenceRecord,
    evidence: EvidenceReference,
    allowed: frozenset[str],
    body_candidates: tuple[_SourceEventCandidate, ...],
) -> _SourceEventCandidate | None:
    temporal = _header_temporal_extent(evidence.summary) or _source_date_extent(evidence)
    if temporal is None:
        return None
    fields = _header_fields(evidence.summary)
    raw_subject = fields.get("subject", "")
    if any(marker in _normalise(raw_subject) for marker in _AUTOREPLY_MARKERS):
        return None
    subject = _safe_header_subject(raw_subject)
    topic = _header_topic(evidence.summary, subject)
    if topic is None:
        return None
    label, predicate_id = topic
    if predicate_id not in allowed:
        return None

    # A stronger substantive body event already represents the material
    # communication/topic, so a wrapper event would be redundant.
    if any(item.predicate_id == predicate_id for item in body_candidates):
        return None
    if _header_topic_represented_by_body(label, body_candidates):
        return None

    sender = _safe_sender_label(fields.get("from", ""))
    description = (
        f"{sender} sent an email concerning {label}."
        if sender
        else f"An email concerning {label} was sent."
    )
    return _SourceEventCandidate(
        source_unit_coordinate=(2_000_000, 0, 0),
        evidence_key=record.evidence_key,
        description=description,
        normalized_event_core=_event_core(description),
        predicate_id=predicate_id,
        event_type=EventType.COMMUNICATION if predicate_id != "capability.action" else EventType.CAPABILITY,
        temporal_extent=temporal,
        extraction_basis=ExtractionBasis.PROPOSITION_WITH_EVIDENCE_ENRICHMENT,
    )


def _candidate_duplicate_key(candidate: _SourceEventCandidate) -> tuple[str, str, TemporalExtent | None]:
    return (candidate.predicate_id, candidate.normalized_event_core, candidate.temporal_extent)


def _discover_source_events(
    record: CaseEvidenceRecord,
    evidence: EvidenceReference,
) -> tuple[_SourceEventCandidate, ...]:
    links = _all_links(record)
    if not links:
        return ()
    discoverable = frozenset(_PREDICATES)

    body = _body_candidates(record, evidence, discoverable)
    proposition = _proposition_candidates(record, discoverable, links)
    discovered = _merge_proposition_candidates_into_body(body, proposition)
    header = _header_fallback_candidate(record, evidence, discoverable, body)

    ordered_input = list(discovered)
    if header is not None:
        ordered_input.append(header)

    # Deduplicate exact source representations while preserving body-first
    # priority over proposition/header fallbacks.
    chosen: dict[tuple[str, str, TemporalExtent | None], _SourceEventCandidate] = {}
    for candidate in sorted(ordered_input, key=lambda item: item.sort_key):
        key = _candidate_duplicate_key(candidate)
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = candidate
            continue
        # Preserve direct proposition anchors even when the body supplied the
        # preferred factual wording/coordinate.
        chosen[key] = _SourceEventCandidate(
            source_unit_coordinate=min(existing.source_unit_coordinate, candidate.source_unit_coordinate),
            evidence_key=existing.evidence_key,
            description=existing.description,
            normalized_event_core=existing.normalized_event_core,
            predicate_id=existing.predicate_id,
            event_type=existing.event_type,
            temporal_extent=existing.temporal_extent,
            extraction_basis=existing.extraction_basis,
            direct_anchor_fingerprints=existing.direct_anchor_fingerprints | candidate.direct_anchor_fingerprints,
            timing_anchor_fingerprints=existing.timing_anchor_fingerprints | candidate.timing_anchor_fingerprints,
        )

    values = tuple(sorted(chosen.values(), key=lambda item: item.sort_key))
    return tuple(
        _SourceEventCandidate(
            source_unit_coordinate=item.source_unit_coordinate,
            evidence_key=item.evidence_key,
            description=item.description,
            normalized_event_core=item.normalized_event_core,
            predicate_id=item.predicate_id,
            event_type=item.event_type,
            temporal_extent=item.temporal_extent,
            extraction_basis=item.extraction_basis,
            direct_anchor_fingerprints=item.direct_anchor_fingerprints,
            timing_anchor_fingerprints=item.timing_anchor_fingerprints,
            source_event_ordinal=ordinal,
        )
        for ordinal, item in enumerate(values)
    )


# ---------------------------------------------------------------------------
# Canonical source evidence and downstream M2 projection
# ---------------------------------------------------------------------------


def _canonical_evidence_lookup(
    results: tuple[StructuredLegalAnalysisResult, ...],
) -> dict[str, EvidenceReference]:
    occurrences: list[_EvidenceOccurrence] = []
    for result in results:
        for element_ordinal, element in enumerate(result.assessment_result.element_assessments):
            for evidence_ordinal, assessment in enumerate(element.evidence_assessments):
                occurrences.append(
                    _EvidenceOccurrence(
                        issue_definition_id=result.issue_definition_id,
                        issue_definition_version=result.issue_definition_version,
                        issue_analysis_id=result.issue_analysis_id,
                        element_ordinal=element_ordinal,
                        evidence_assessment_ordinal=evidence_ordinal,
                        evidence_key=assessment.mapping.evidence_key,
                        evidence=assessment.mapping.evidence,
                    )
                )
    by_key: dict[str, list[_EvidenceOccurrence]] = defaultdict(list)
    for occurrence in sorted(occurrences, key=lambda item: item.rank):
        by_key[occurrence.evidence_key].append(occurrence)

    values: dict[str, EvidenceReference] = {}
    for evidence_key, items in by_key.items():
        canonical = items[0].evidence
        for item in items[1:]:
            assert_compatible_canonical_evidence(evidence_key, canonical, item.evidence)
        values[evidence_key] = canonical
    return values


def _profile_allows_candidate(profile: EventExtractionProfile, candidate: _SourceEventCandidate) -> bool:
    return profile.event_capable and candidate.predicate_id in profile.predicate_ids


def _link_factually_anchors_candidate(
    link: EvidencePropositionLink,
    candidate: _SourceEventCandidate,
) -> bool:
    if link.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
        return False
    if candidate.evidence_key not in link.evidence_keys:
        return False
    if _is_generic_proposition(link.text):
        return True

    predicate = _PREDICATES[candidate.predicate_id]
    proposition_text = _factual_clause(_base_from_proposition(link.text))
    if _predicate_matches(proposition_text, predicate):
        return True
    normal = _normalise(proposition_text)
    return any(_contains_marker(normal, marker) for marker in predicate.object_markers)


def _generic_exceptional_compatible(
    candidate: _SourceEventCandidate,
    candidates: tuple[_SourceEventCandidate, ...],
) -> bool:
    """Conservatively bind a generic proposition to one factual subject family."""

    material = tuple(
        item for item in candidates
        if item.extraction_basis is not ExtractionBasis.PROPOSITION
    ) or candidates
    families = {item.predicate_id for item in material}
    return families == {candidate.predicate_id}


def _projection_mode(
    profile: EventExtractionProfile | None,
    link: EvidencePropositionLink,
    candidate: _SourceEventCandidate,
    candidates: tuple[_SourceEventCandidate, ...],
) -> str:
    if profile is None:
        return "refused"
    if link.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
        return "refused"
    if candidate.evidence_key not in link.evidence_keys:
        return "refused"

    if profile.event_capable:
        if not _profile_allows_candidate(profile, candidate):
            return "refused"
        return "normal" if _link_factually_anchors_candidate(link, candidate) else "refused"

    if _is_generic_proposition(link.text):
        return "exceptional" if _generic_exceptional_compatible(candidate, candidates) else "refused"
    return "exceptional" if _link_factually_anchors_candidate(link, candidate) else "refused"


def _timing_anchor_matches_candidate(
    link: EvidencePropositionLink,
    candidate: _SourceEventCandidate,
    candidates: tuple[_SourceEventCandidate, ...],
) -> bool:
    fingerprint = _link_fingerprint(link)
    if fingerprint in candidate.timing_anchor_fingerprints:
        return True
    if candidate.temporal_extent is None:
        return False
    parsed = parse_temporal_expressions(link.text)
    if len(parsed) != 1 or parsed[0].extent != candidate.temporal_extent:
        return False
    matching = tuple(
        item for item in candidates
        if item.temporal_extent == candidate.temporal_extent
    )
    return len(matching) == 1


def _qualified_description(
    base: str,
    status: EventStatus,
    *,
    source_assertion: bool = False,
) -> str:
    cleaned = _clean_clause(base).rstrip(".")
    lowered = cleaned[0].lower() + cleaned[1:] if cleaned else cleaned
    if status is EventStatus.DISPUTED:
        return f"The source records a disputed account that {lowered}."
    if status is EventStatus.UNRESOLVED:
        return f"The source contains unresolved material suggesting that {lowered}."
    if source_assertion:
        normal = _normalise(cleaned)
        if not normal.startswith(("the claimant states", "the respondent states", "the witness statement records")):
            return f"The source records an assertion that {lowered}."
    return f"{cleaned}."


def _status_for(
    link: EvidencePropositionLink,
    use: EvidenceUse,
    evidence: EvidenceReference,
    *,
    directly_anchored: bool,
) -> EventStatus | None:
    if link.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
        return None
    if link.status is PropositionAssessmentStatus.DISPUTED or use.analytical_role is AnalyticalRole.CONFLICTING:
        return EventStatus.DISPUTED
    if link.status is PropositionAssessmentStatus.UNRESOLVED:
        return EventStatus.UNRESOLVED
    if link.status is PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED:
        return EventStatus.SUPPORTED
    if evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION or not directly_anchored:
        return EventStatus.SUPPORTED
    return EventStatus.ESTABLISHED


def _timing_status(
    link: EvidencePropositionLink,
    use: EvidenceUse,
    evidence: EvidenceReference,
    *,
    temporal: TemporalExtent | None,
    timing_directly_anchored: bool,
) -> TimingStatus:
    if temporal is None:
        return TimingStatus.UNKNOWN
    if link.status is PropositionAssessmentStatus.DISPUTED or use.analytical_role is AnalyticalRole.CONFLICTING:
        return TimingStatus.DISPUTED
    if (
        link.status is PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE
        and timing_directly_anchored
        and evidence.evidence_status is not EvidenceStatus.SOURCE_ASSERTION
    ):
        return TimingStatus.ESTABLISHED
    return TimingStatus.SUPPORTED


def assertion_id_for(use: EvidenceUse, link: EvidencePropositionLink, ordinal: int) -> str:
    """Return deterministic assertion identity using the shared source-event ordinal."""

    material = "|".join(
        (
            use.issue_analysis_id,
            use.element_id,
            str(link.source_proposition_index),
            use.evidence_key,
            str(ordinal),
            CHRONOLOGY_PROFILE_VERSION,
        )
    )
    return str(uuid5(_ASSERTION_NAMESPACE, material))


def extract_event_assertions(
    matrices: CaseMatrices,
    results: tuple[StructuredLegalAnalysisResult, ...],
) -> tuple[EventAssertion, ...]:
    """Discover source events once, then project only through frozen M2 uses."""

    canonical_evidence = _canonical_evidence_lookup(results)
    assertions: list[EventAssertion] = []

    for record in matrices.evidence_matrix:
        try:
            evidence = canonical_evidence[record.evidence_key]
        except KeyError as exc:
            raise ValueError(
                f"Canonical M2 evidence key {record.evidence_key!r} cannot resolve to frozen M4 evidence."
            ) from exc

        candidates = _discover_source_events(record, evidence)
        if not candidates:
            continue

        for use in record.uses:
            profile = optional_profile_for(
                use.issue_definition_id,
                use.issue_definition_version,
                use.element_id,
            )

            for candidate in candidates:
                for link in use.proposition_links:
                    projection_mode = _projection_mode(profile, link, candidate, candidates)
                    if projection_mode == "refused":
                        continue
                    fingerprint = _link_fingerprint(link)
                    directly_anchored = fingerprint in candidate.direct_anchor_fingerprints
                    timing_direct = _timing_anchor_matches_candidate(link, candidate, candidates)
                    status = _status_for(
                        link,
                        use,
                        evidence,
                        directly_anchored=directly_anchored,
                    )
                    if status is None:
                        continue
                    timing = _timing_status(
                        link,
                        use,
                        evidence,
                        temporal=candidate.temporal_extent,
                        timing_directly_anchored=timing_direct,
                    )
                    assertions.append(
                        EventAssertion(
                            assertion_id=assertion_id_for(
                                use,
                                link,
                                candidate.source_event_ordinal,
                            ),
                            issue_analysis_id=use.issue_analysis_id,
                            issue_definition_id=use.issue_definition_id,
                            issue_definition_version=use.issue_definition_version,
                            element_id=use.element_id,
                            source_proposition_index=link.source_proposition_index,
                            evidence_key=use.evidence_key,
                            extraction_ordinal=candidate.source_event_ordinal,
                            description=_qualified_description(
                                candidate.description,
                                status,
                                source_assertion=evidence.evidence_status is EvidenceStatus.SOURCE_ASSERTION,
                            ),
                            normalized_event_core=candidate.normalized_event_core,
                            event_type=candidate.event_type,
                            event_status=status,
                            confidence=link.confidence,
                            temporal_extent=candidate.temporal_extent,
                            timing_status=timing,
                            participants=(),
                            extraction_basis=candidate.extraction_basis,
                            profile_version=(profile.profile_version if profile is not None else CHRONOLOGY_PROFILE_VERSION),
                        )
                    )

    # Assertion identity includes proposition coordinates; duplicates therefore
    # indicate an internal projection defect rather than legitimate reuse.
    by_id: dict[str, EventAssertion] = {}
    for assertion in assertions:
        existing = by_id.get(assertion.assertion_id)
        if existing is None:
            by_id[assertion.assertion_id] = assertion
        elif existing != assertion:
            raise ValueError(f"Chronology assertion identity collision {assertion.assertion_id!r}.")
    return tuple(sorted(by_id.values(), key=lambda item: item.source_coordinate))


__all__ = [
    "CHRONOLOGY_EXTRACTION_POLICY_VERSION",
    "CHRONOLOGY_PROFILES",
    "EventExtractionProfile",
    "EventSignalRule",
    "assertion_id_for",
    "extract_event_assertions",
    "optional_profile_for",
    "profile_for",
]
