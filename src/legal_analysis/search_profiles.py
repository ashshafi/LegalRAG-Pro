"""Controlled element-specific evidence search profiles for Sprint 2.3 M3.

Profiles are versioned mapping configuration, not legal definitions.  They tell
Milestone 3 what factual material to look for for each element while leaving the
meaning and ordering of the controlled M1 issue definitions untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable

from evidence_classification import EvidenceSourceType

from .models import IssueDefinition
from .registry import DEFAULT_ISSUE_DEFINITION_REGISTRY, IssueDefinitionRegistry

ELEMENT_MAPPER_VERSION: Final[str] = "element-mapper/1.0"
ELEMENT_CANDIDATE_LIMIT: Final[int] = 8
ELEMENT_RETAIN_LIMIT: Final[int] = 5


@dataclass(frozen=True, slots=True)
class ElementSearchProfile:
    """Controlled retrieval/mapping profile for one exact legal element."""

    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    search_objective: str
    search_terms: tuple[str, ...]
    strong_phrases: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    source_type_hints: tuple[EvidenceSourceType, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "search_objective",
        ):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty.")
            object.__setattr__(self, field_name, value)
        for field_name in ("search_terms", "strong_phrases", "required_any"):
            values = tuple(
                dict.fromkeys(
                    item.strip().casefold()
                    for item in getattr(self, field_name)
                    if item and item.strip()
                )
            )
            object.__setattr__(self, field_name, values)
        object.__setattr__(self, "source_type_hints", tuple(self.source_type_hints))
        if not self.search_terms and not self.strong_phrases:
            raise ValueError("A search profile needs search_terms or strong_phrases.")
        if any(not isinstance(item, EvidenceSourceType) for item in self.source_type_hints):
            raise ValueError("source_type_hints must contain EvidenceSourceType values.")

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.issue_definition_id,
            self.issue_definition_version,
            self.element_id,
        )


def _p(
    issue_id: str,
    element_id: str,
    objective: str,
    terms: Iterable[str],
    *,
    phrases: Iterable[str] = (),
    required: Iterable[str] = (),
    sources: Iterable[EvidenceSourceType] = (),
) -> ElementSearchProfile:
    return ElementSearchProfile(
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        element_id=element_id,
        search_objective=objective,
        search_terms=tuple(terms),
        strong_phrases=tuple(phrases),
        required_any=tuple(required),
        source_type_hints=tuple(sources),
    )


_MEDICAL = (
    EvidenceSourceType.INDEPENDENT_MEDICAL,
    EvidenceSourceType.OCCUPATIONAL_HEALTH,
    EvidenceSourceType.INSURER_RECORD,
)
_EMPLOYER = (
    EvidenceSourceType.EMPLOYER_RECORD,
    EvidenceSourceType.MIXED_CORRESPONDENCE,
)
_CLAIMANT = (
    EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
    EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
    EvidenceSourceType.CLAIMANT_SUBMISSION,
)
_RESPONDENT = (
    EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT,
    EvidenceSourceType.RESPONDENT_SUBMISSION,
    EvidenceSourceType.EMPLOYER_RECORD,
)


INITIAL_ELEMENT_SEARCH_PROFILES: Final[tuple[ElementSearchProfile, ...]] = (
    # RA-001 — Reasonable adjustments
    _p(
        "RA-001", "RA-DISABILITY",
        "Locate records describing the claimant's disability, diagnosis, symptoms, duration or functional effects at the relevant time.",
        ("disability", "diagnosis", "psychiatric", "mental health", "symptoms", "condition", "incapacity", "functional"),
        phrases=("long term", "long-term", "substantial adverse", "psychiatric condition"),
        sources=_MEDICAL + _CLAIMANT,
    ),
    _p(
        "RA-001", "RA-KNOWLEDGE",
        "Locate communications or records showing what CACI personnel received, discussed, acknowledged or could reasonably have known about disability and relevant disadvantage.",
        ("aware", "knowledge", "knew", "received", "discussed", "acknowledged", "health", "disability", "medical", "return to work", "adjustment"),
        phrases=("confirmed receipt", "discussed with", "occupational health", "return to work"),
        required=("aware", "knowledge", "knew", "received", "discussed", "acknowledged", "to:", "cc:"),
        sources=_EMPLOYER + _MEDICAL,
    ),
    _p(
        "RA-001", "RA-WORKPLACE-CONTEXT",
        "Locate evidence describing the workplace arrangement, requirement, working pattern, location, duties or other circumstance said to create the adjustment context.",
        ("workplace", "working", "office", "commute", "travel", "duties", "hours", "role", "attendance", "home working", "hybrid", "work from home"),
        phrases=("work from home", "home working", "working hours", "job description", "return to work"),
        sources=_EMPLOYER + _CLAIMANT,
    ),
    _p(
        "RA-001", "RA-DISADVANTAGE",
        "Locate evidence describing the practical or functional disadvantage caused by the workplace circumstance for the claimant.",
        ("disadvantage", "difficulty", "unable", "cannot", "anxiety", "fatigue", "travel", "commute", "symptoms", "impact", "barrier"),
        phrases=("substantial disadvantage", "difficulty travelling", "unable to", "could not"),
        sources=_MEDICAL + _CLAIMANT,
    ),
    _p(
        "RA-001", "RA-ADJUSTMENT",
        "Locate proposed, requested or discussed adjustments such as home working, phased return, changed hours, duties or workplace support.",
        ("adjustment", "home working", "work from home", "phased return", "reduced hours", "flexible", "support", "changed duties", "hybrid"),
        phrases=("reasonable adjustment", "phased return", "work from home", "home working", "flexible working"),
        sources=_EMPLOYER + _MEDICAL + _CLAIMANT,
    ),
    _p(
        "RA-001", "RA-REASONABLENESS",
        "Locate evidence bearing on practicality, effectiveness, cost, operational impact, medical benefit or feasibility of a proposed adjustment.",
        ("reasonable", "practical", "feasible", "effective", "cost", "operational", "impact", "recommend", "trial", "review", "phased", "support"),
        phrases=("reasonable adjustment", "phased return", "medical recommendation", "operational requirements"),
        sources=_EMPLOYER + _MEDICAL,
    ),
    _p(
        "RA-001", "RA-FAILURE",
        "Locate evidence of what CACI did, refused, omitted, stopped, failed to consider or failed to implement concerning an adjustment.",
        ("refused", "declined", "failed", "failure", "did not", "no response", "stopped", "withdrawn", "not implemented", "not considered", "omission"),
        phrases=("failed to", "did not respond", "not implemented", "no occupational health", "no contact"),
        sources=_EMPLOYER + _CLAIMANT,
    ),
    _p(
        "RA-001", "RA-TIMING",
        "Locate dates and periods for adjustment requests, employer responses, omissions, return-to-work attempts and any alleged continuing conduct.",
        ("date", "2005", "2026", "since", "until", "continued", "continuing", "period", "return to work", "request", "response"),
        phrases=("continuing failure", "continuing omission", "return to work", "since 2005"),
        sources=_EMPLOYER + _CLAIMANT + _MEDICAL,
    ),

    # DA-001 — Discrimination arising from disability
    _p(
        "DA-001", "DA-DISABILITY",
        "Locate records describing the claimant's disability, diagnosis, symptoms, duration or functional effects at the relevant time.",
        ("disability", "diagnosis", "psychiatric", "mental health", "symptoms", "condition", "incapacity", "functional"),
        phrases=("psychiatric condition",),
        sources=_MEDICAL + _CLAIMANT,
    ),
    _p(
        "DA-001", "DA-SOMETHING-ARISING",
        "Locate evidence of absence, conduct, capability, attendance, symptoms, needs or other circumstances said to arise from disability.",
        ("absence", "sickness", "incapacity", "symptoms", "attendance", "capability", "conduct", "need", "return to work", "because of disability"),
        phrases=("long-term sickness", "sickness absence", "arising from disability", "because of disability"),
        sources=_MEDICAL + _CLAIMANT + _EMPLOYER,
    ),
    _p(
        "DA-001", "DA-UNFAVOURABLE-TREATMENT",
        "Locate the act, decision or treatment alleged to be unfavourable, including capability action, loss of benefits, demotion, refusal or other detriment.",
        ("unfavourable", "treatment", "demotion", "capability", "benefit", "removed", "cancelled", "refused", "dismiss", "detriment", "decision"),
        phrases=("unfavourable treatment", "capability review", "removed benefit", "cancelled benefit"),
        sources=_EMPLOYER + _CLAIMANT + _RESPONDENT,
    ),
    _p(
        "DA-001", "DA-CAUSATION",
        "Locate evidence connecting the alleged treatment to sickness absence, incapacity, symptoms, capability or another matter arising from disability.",
        ("because", "due to", "absence", "sickness", "incapacity", "capability", "result", "arising"),
        phrases=("because of", "due to", "as a result of", "arising from"),
        required=("because of", "due to", "as a result of", "arising from"),
        sources=_EMPLOYER + _RESPONDENT + _CLAIMANT,
    ),
    _p(
        "DA-001", "DA-KNOWLEDGE",
        "Locate communications or records showing what CACI personnel received, discussed or knew about the claimant's disability.",
        ("aware", "knowledge", "knew", "received", "discussed", "acknowledged", "health", "disability", "medical"),
        phrases=("confirmed receipt", "discussed with", "occupational health"),
        required=("aware", "knowledge", "knew", "received", "discussed", "acknowledged", "to:", "cc:"),
        sources=_EMPLOYER + _MEDICAL,
    ),
    _p(
        "DA-001", "DA-JUSTIFICATION",
        "Locate the employer's stated aims, business reasons, alternatives, proportionality considerations and evidence relied upon to justify the treatment.",
        ("justify", "justification", "legitimate aim", "proportionate", "business", "operational", "reason", "necessity", "alternative", "capability"),
        phrases=("legitimate aim", "proportionate means", "business reason", "operational requirement"),
        sources=_RESPONDENT,
    ),
    _p(
        "DA-001", "DA-TIMING",
        "Locate the date or period of each alleged unfavourable act or treatment and related communications.",
        ("date", "since", "until", "period", "decision", "letter", "email", "capability", "demotion", "benefit"),
        phrases=("dated", "on 17 july 2026", "since 2005"),
        sources=_EMPLOYER + _CLAIMANT + _RESPONDENT,
    ),

    # EK-001 — Employer knowledge
    _p(
        "EK-001", "EK-INFORMATION",
        "Locate records describing the claimant's disability-related condition, symptoms, diagnosis, incapacity or functional effects existing at the material time.",
        ("disability", "diagnosis", "psychiatric", "mental health", "symptoms", "condition", "incapacity", "functional"),
        phrases=("psychiatric condition", "long term incapacity"),
        sources=_MEDICAL + _CLAIMANT,
    ),
    _p(
        "EK-001", "EK-RECIPIENT",
        "Locate communications identifying CACI managers, HR or other personnel who received, discussed, copied or had access to relevant health information.",
        ("to:", "cc:", "manager", "human resources", "hr", "director", "received", "sent", "copied", "discussed"),
        phrases=("head of hr", "hr director", "discussed with", "sent to", "copied to"),
        required=("health", "medical", "disability", "diagnosis", "psychiatric", "occupational health", "recommendation", "symptoms", "condition", "incapacity"),
        sources=_EMPLOYER + _MEDICAL,
    ),
    _p(
        "EK-001", "EK-DIRECT-KNOWLEDGE",
        "Locate contemporaneous communications directly recording receipt, acknowledgement, discussion or awareness by CACI personnel of relevant disability or health information.",
        ("received", "receipt", "acknowledged", "discussed", "aware", "knew", "confirmed", "to:", "cc:", "health", "medical", "disability"),
        phrases=("confirmed receipt", "we received", "i received", "discussed with", "aware of"),
        required=("received", "receipt", "acknowledged", "discussed", "aware", "knew", "confirmed", "to:", "cc:"),
        sources=_EMPLOYER,
    ),
    _p(
        "EK-001", "EK-CONSTRUCTIVE-KNOWLEDGE",
        "Locate facts that may bear on what CACI could reasonably have been expected to know, including prolonged absence, insurer/OH involvement and rehabilitation activity.",
        ("incapacity", "unum", "insurer", "occupational health", "rehabilitation", "return to work", "medical"),
        phrases=("long-term absence", "long term absence", "return to work", "occupational health", "rehabilitation plan"),
        sources=_EMPLOYER + _MEDICAL,
    ),
    _p(
        "EK-001", "EK-DISADVANTAGE-KNOWLEDGE",
        "Locate communications showing what CACI knew or was told about travel, attendance, functional difficulties, disadvantage or adjustment needs.",
        ("difficulty", "disadvantage", "travel", "commute", "attendance", "fatigue", "anxiety", "unable", "adjustment", "home working", "phased return"),
        phrases=("work from home", "home working", "phased return", "difficulty travelling"),
        sources=_EMPLOYER + _MEDICAL + _CLAIMANT,
    ),
    _p(
        "EK-001", "EK-CLAIMANT-ASSERTIONS",
        "Locate claimant-authored evidence stating what the claimant says CACI knew about disability, recommendations, disadvantage or adjustment needs.",
        ("i believe", "i state", "caci knew", "caci was aware", "fully aware", "my disability", "my condition", "my adjustments"),
        phrases=("caci knew", "caci was aware", "fully aware", "i state that"),
        sources=_CLAIMANT,
    ),
    _p(
        "EK-001", "EK-RESPONDENT-POSITION",
        "Locate CACI/respondent material admitting, denying, limiting or otherwise putting employer knowledge in issue.",
        ("deny", "denies", "not aware", "no knowledge", "admit", "knowledge", "disability", "respondent", "grounds of resistance", "et3"),
        phrases=("the respondent denies", "no knowledge", "not aware", "grounds of resistance"),
        sources=_RESPONDENT,
    ),
    _p(
        "EK-001", "EK-UNRESOLVED",
        "Locate material showing that propositions about CACI's knowledge are disputed, asserted, inferential or not directly acknowledged.",
        ("dispute", "disputed", "assert", "aware", "knew", "no evidence", "not established", "denied", "inference"),
        phrases=("not established", "no direct evidence", "the respondent denies", "caci knew"),
        sources=_CLAIMANT + _RESPONDENT + _EMPLOYER,
    ),
    _p(
        "EK-001", "EK-TIMING",
        "Locate dates showing when health information, return-to-work material or alleged knowledge reached CACI and the period to which it relates.",
        ("date", "2001", "2005", "2026", "received", "sent", "email", "letter", "return to work", "since", "period"),
        phrases=("dated", "return to work", "since 2005"),
        sources=_EMPLOYER + _MEDICAL + _CLAIMANT,
    ),

    # LIM-001 — Limitation / continuing conduct / J&E
    _p(
        "LIM-001", "LIM-ACTS",
        "Locate the discriminatory acts or omissions alleged by the claimant, including decisions, refusals, failures, withdrawals or continuing omissions.",
        ("act", "omission", "failed", "failure", "refused", "demotion", "withdrawn", "cancelled", "no contact", "capability", "discrimination"),
        phrases=("failed to", "continuing omission", "continuing failure", "no contact"),
        sources=_CLAIMANT + _EMPLOYER + _RESPONDENT,
    ),
    _p(
        "LIM-001", "LIM-DATES",
        "Locate dates and periods attributed to each alleged act, omission, decision or event relevant to limitation.",
        ("date", "dated", "2001", "2005", "2021", "2024", "2025", "2026", "since", "until", "period"),
        phrases=("dated", "since 2005", "presented on", "claim submitted"),
        sources=_CLAIMANT + _EMPLOYER + _RESPONDENT + (EvidenceSourceType.TRIBUNAL_RECORD,),
    ),
    _p(
        "LIM-001", "LIM-SEPARATE-OR-CONSEQUENCE",
        "Locate material characterising later events as separate acts, continuing conduct, continuing omissions or consequences of earlier conduct.",
        ("separate act", "consequence", "continuing", "ongoing", "omission", "later", "result", "effect"),
        phrases=("continuing act", "continuing omission", "conduct extending over a period", "mere consequence"),
        sources=_CLAIMANT + _RESPONDENT + (EvidenceSourceType.TRIBUNAL_RECORD,),
    ),
    _p(
        "LIM-001", "LIM-CONTINUING-CONDUCT",
        "Locate factual material relied upon for or against an allegation that discriminatory conduct or omission extended over a period.",
        ("continuing", "ongoing", "since", "throughout", "no contact", "omission", "remained", "continued", "period"),
        phrases=("continuing act", "continuing omission", "conduct extending over a period", "since 2005"),
        sources=_CLAIMANT + _RESPONDENT + _EMPLOYER,
    ),
    _p(
        "LIM-001", "LIM-END-DATE",
        "Locate the date on which any alleged continuing conduct or omission is said to have ended or remained ongoing.",
        ("ended", "ceased", "until", "ongoing", "continued", "end date", "termination", "still employed", "present"),
        phrases=("continued until", "remains ongoing", "still employed", "ceased on"),
        sources=_CLAIMANT + _EMPLOYER + _RESPONDENT,
    ),
    _p(
        "LIM-001", "LIM-PRESENTATION",
        "Locate claim-presentation, ET1 and ACAS Early Conciliation dates relevant to limitation calculations.",
        ("et1", "acas", "early conciliation", "presented", "submitted", "claim date", "certificate", "tribunal"),
        phrases=("early conciliation", "acas certificate", "claim presented", "et1 presented"),
        sources=(EvidenceSourceType.TRIBUNAL_RECORD, EvidenceSourceType.CLAIMANT_SUBMISSION),
    ),
    _p(
        "LIM-001", "LIM-DELAY-EXPLANATION",
        "Locate the claimant's explanation and supporting material for delay in presenting the claim.",
        ("delay", "unable", "health", "psychiatric", "incapacity", "explanation", "late", "did not understand", "medical"),
        phrases=("explanation for delay", "medical delay", "unable to bring", "psychiatric incapacity"),
        sources=_CLAIMANT + _MEDICAL,
    ),
    _p(
        "LIM-001", "LIM-RESPONDENT-POSITION",
        "Locate the respondent's pleaded or documented limitation position, including dates, time-bar arguments and characterisation of alleged acts.",
        ("out of time", "time barred", "limitation", "2005", "respondent", "grounds of resistance", "et3", "continuing act", "jurisdiction"),
        phrases=("out of time", "time barred", "grounds of resistance", "no continuing act"),
        sources=_RESPONDENT,
    ),
    _p(
        "LIM-001", "LIM-PREJUDICE-EVIDENCE",
        "Locate material bearing on evidential cogency, unavailable witnesses/records, retained records or prejudice caused by the passage of time.",
        ("prejudice", "records", "documents", "witness", "memory", "available", "retained", "destroyed", "delay", "cogency"),
        phrases=("evidential prejudice", "records retained", "records available", "passage of time"),
        sources=_CLAIMANT + _RESPONDENT + _EMPLOYER,
    ),
    _p(
        "LIM-001", "LIM-JE-FACTORS",
        "Locate material relied upon in relation to a just-and-equitable extension, including delay explanation, prejudice, knowledge, conduct and evidential factors.",
        ("just and equitable", "extension", "delay", "prejudice", "health", "reason", "knowledge", "evidence", "conduct"),
        phrases=("just and equitable", "extension of time", "reason for delay"),
        sources=_CLAIMANT + _RESPONDENT + _MEDICAL,
    ),
)


class ElementSearchProfileRegistry:
    """Registry of exact issue-version/element search profiles."""

    def __init__(
        self,
        profiles: Iterable[ElementSearchProfile] = (),
        *,
        issue_registry: IssueDefinitionRegistry = DEFAULT_ISSUE_DEFINITION_REGISTRY,
    ) -> None:
        self._issue_registry = issue_registry
        self._profiles: dict[tuple[str, str, str], ElementSearchProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: ElementSearchProfile) -> None:
        definition = self._issue_registry.get_definition(
            profile.issue_definition_id,
            profile.issue_definition_version,
        )
        valid_element_ids = {item.element_id for item in definition.elements}
        if profile.element_id not in valid_element_ids:
            raise ValueError(
                f"Unknown element {profile.element_id!r} for {definition.definition_id}/{definition.version}."
            )
        if profile.key in self._profiles:
            raise ValueError(f"Duplicate element search profile: {profile.key!r}.")
        self._profiles[profile.key] = profile

    def get_profile(
        self,
        issue_definition_id: str,
        issue_definition_version: str,
        element_id: str,
    ) -> ElementSearchProfile:
        key = (
            issue_definition_id.strip().upper(),
            issue_definition_version.strip(),
            element_id.strip(),
        )
        try:
            return self._profiles[key]
        except KeyError as exc:
            raise KeyError(f"No element search profile registered for {key!r}.") from exc

    def profiles_for_definition(
        self,
        definition: IssueDefinition,
    ) -> tuple[ElementSearchProfile, ...]:
        return tuple(
            self.get_profile(definition.definition_id, definition.version, element.element_id)
            for element in definition.elements
        )

    def validate(self) -> None:
        for definition in self._issue_registry.list_definitions(active_only=True):
            expected = tuple(element.element_id for element in definition.elements)
            actual = tuple(
                profile.element_id
                for profile in self.profiles_for_definition(definition)
            )
            if actual != expected:
                raise ValueError(
                    f"Search-profile coverage/order mismatch for {definition.definition_id}/{definition.version}."
                )


DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY = ElementSearchProfileRegistry(
    INITIAL_ELEMENT_SEARCH_PROFILES
)
DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.validate()


__all__ = [
    "DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY",
    "ELEMENT_CANDIDATE_LIMIT",
    "ELEMENT_MAPPER_VERSION",
    "ELEMENT_RETAIN_LIMIT",
    "ElementSearchProfile",
    "ElementSearchProfileRegistry",
    "INITIAL_ELEMENT_SEARCH_PROFILES",
]
