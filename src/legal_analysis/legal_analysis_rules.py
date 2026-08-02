"""Deterministic legal-significance and provisional-status rules for M5.

Rules are keyed to the exact controlled issue-definition version and element.
They interpret, but never modify, the frozen M4 evidential state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .enums import AnalyticalRole, Confidence
from .evidence_assessment import ElementEvidenceAssessment, PropositionAssessmentStatus
from .legal_analysis import ElementAnalysisStatus


@dataclass(frozen=True, slots=True)
class LegalSignificanceProfile:
    """Controlled legal-significance template for one exact versioned element."""

    legal_relevance: str
    analysis_subject: str
    safe_analysis_pattern: str
    key_caveat: str
    prohibited_conclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "legal_relevance",
            "analysis_subject",
            "safe_analysis_pattern",
            "key_caveat",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty.")
            object.__setattr__(self, name, value)
        prohibited = tuple(
            dict.fromkeys(item.strip().casefold() for item in self.prohibited_conclusions if item.strip())
        )
        if not prohibited:
            raise ValueError("prohibited_conclusions must not be empty.")
        object.__setattr__(self, "prohibited_conclusions", prohibited)


def _p(
    relevance: str,
    subject: str,
    pattern: str,
    caveat: str,
    *prohibited: str,
) -> LegalSignificanceProfile:
    common = (
        "the statutory test is satisfied",
        "the element is satisfied",
        "the claim succeeds",
        "the claim fails",
    )
    return LegalSignificanceProfile(
        legal_relevance=relevance,
        analysis_subject=subject,
        safe_analysis_pattern=pattern,
        key_caveat=caveat,
        prohibited_conclusions=common + tuple(prohibited),
    )


LEGAL_SIGNIFICANCE_PROFILES: Final[dict[tuple[str, str, str], LegalSignificanceProfile]] = {
    # RA-001 / 1.0
    ("RA-001", "1.0", "RA-DISABILITY"): _p(
        "Evidence about the claimant's condition, duration and functional effects is relevant to the factual basis of the Equality Act disability question.",
        "the factual basis of disability at the relevant time",
        "The current evidential state may be used to describe the condition and functional effects shown by the record without deciding the statutory disability test.",
        "A diagnosis, sickness absence or reported impairment does not by itself amount to a final determination that the statutory disability definition is met.",
        "the claimant was legally disabled",
    ),
    ("RA-001", "1.0", "RA-KNOWLEDGE"): _p(
        "Information received, discussed or reasonably available to the employer may be relevant to actual or constructive knowledge of disability and the relevant disadvantage.",
        "the factual basis for employer knowledge relevant to the adjustment duty",
        "The current record may support provisional analysis of what health- or disadvantage-related information was available to relevant CACI personnel.",
        "General sickness awareness or rehabilitation involvement does not by itself establish knowledge of every diagnosis, functional effect or particular disadvantage.",
        "caci had legal knowledge",
        "caci knew about the disability",
    ),
    ("RA-001", "1.0", "RA-WORKPLACE-CONTEXT"): _p(
        "Evidence identifying workplace arrangements, requirements, physical circumstances or auxiliary-aid issues is relevant to defining the context in which an adjustment duty is said to arise.",
        "the workplace context said to engage the adjustment duty",
        "The record may identify the working arrangement or circumstance relied upon without determining its final statutory characterisation.",
        "A workplace circumstance being documented does not itself establish that it is a legally relevant PCP, physical feature or auxiliary-aid issue.",
        "a pcp is established",
    ),
    ("RA-001", "1.0", "RA-DISADVANTAGE"): _p(
        "Evidence of functional difficulty, comparative impact or work-related barriers is relevant to the factual basis of the alleged disadvantage.",
        "the factual basis of the alleged disability-related disadvantage",
        "The current record may describe reported or documented difficulties and their work-related effects provisionally.",
        "Reported difficulty does not by itself establish statutory substantial disadvantage or the required comparison.",
        "substantial disadvantage is established",
    ),
    ("RA-001", "1.0", "RA-ADJUSTMENT"): _p(
        "Evidence of proposed, requested or identifiable steps is relevant to determining what adjustments were available for consideration.",
        "the existence and content of proposed or identifiable adjustments",
        "The record may establish that a step such as home working, phased return or altered duties was proposed or discussed.",
        "The existence of a proposal does not establish that the step was effective, practicable or legally reasonable.",
        "home working was a reasonable adjustment",
        "the adjustment was reasonable",
    ),
    ("RA-001", "1.0", "RA-REASONABLENESS"): _p(
        "Evidence concerning effectiveness, practicability, operational impact, cost, resources, trials and alternatives may be relevant to the reasonableness inquiry.",
        "the factual considerations relevant to the reasonableness of a proposed adjustment",
        "The current record may identify facts bearing on practicability or effectiveness while leaving the legal evaluation for a later merits stage.",
        "A proposal, request or non-implementation does not by itself establish that an adjustment was legally reasonable or unreasonable.",
        "home working was a reasonable adjustment",
        "the adjustment was reasonable",
        "the adjustment was unreasonable",
    ),
    ("RA-001", "1.0", "RA-FAILURE"): _p(
        "Evidence of what the employer did, decided, implemented, refused or omitted is relevant to the factual basis of the alleged failure to take a step.",
        "the employer's factual acts or omissions concerning the proposed adjustment",
        "The record may establish particular decisions or omissions without characterising them as an unlawful failure.",
        "Non-implementation, refusal or delay does not by itself establish breach of the reasonable-adjustments duty.",
        "caci breached the duty to make reasonable adjustments",
        "caci failed unlawfully",
    ),
    ("RA-001", "1.0", "RA-TIMING"): _p(
        "Dates and periods of alleged acts or omissions are relevant to when the adjustment-related conduct occurred and to any later limitation analysis.",
        "the chronology of adjustment-related acts, omissions and alleged continuing conduct",
        "The current record may establish dates or periods while leaving their legal characterisation open.",
        "A sequence of events or ongoing consequences does not by itself establish conduct extending over a period.",
        "there was a continuing act",
    ),

    # DA-001 / 1.0
    ("DA-001", "1.0", "DA-DISABILITY"): _p(
        "Evidence about the claimant's condition, duration and functional effects is relevant to the factual basis of the disability requirement.",
        "the factual basis of disability at the relevant time",
        "The current record may describe the condition and functional effects without finally determining the statutory definition.",
        "Medical or sickness evidence alone does not amount to a final finding that the statutory disability definition is met.",
        "the claimant was legally disabled",
    ),
    ("DA-001", "1.0", "DA-SOMETHING-ARISING"): _p(
        "Evidence linking absence, behaviour, need, incapacity or another circumstance to disability is relevant to identifying the alleged 'something arising'.",
        "the factual link between disability and the identified consequence or circumstance",
        "The current record may support a provisional factual connection between disability and the circumstance relied upon.",
        "Temporal association or claimant assertion alone does not finally establish that the circumstance arose in consequence of disability for statutory purposes.",
        "something arising from disability is established",
    ),
    ("DA-001", "1.0", "DA-UNFAVOURABLE-TREATMENT"): _p(
        "Evidence identifying the act, decision or treatment relied upon is relevant to defining the alleged unfavourable treatment.",
        "the factual treatment relied upon as potentially unfavourable",
        "The current record may identify treatment capable of being relied upon without deciding its legal character or lawfulness.",
        "The occurrence of treatment does not by itself establish that it was legally unfavourable or discriminatory.",
        "unfavourable treatment is established",
        "this was unlawful unfavourable treatment",
    ),
    ("DA-001", "1.0", "DA-CAUSATION"): _p(
        "Evidence about reasons, sequence, stated explanations and links between the identified circumstance and treatment is relevant to factual causation.",
        "the factual connection between the something arising and the treatment relied upon",
        "The record may support or limit an argument about factual linkage while leaving the statutory causation question provisional.",
        "Sequence or correlation alone does not establish that treatment was because of the identified something arising from disability.",
        "section 15 is established",
        "causation is established",
    ),
    ("DA-001", "1.0", "DA-KNOWLEDGE"): _p(
        "Evidence about information available to the employer is relevant to the knowledge limitation in section 15(2).",
        "the factual basis for actual or constructive employer knowledge of disability",
        "The current record may support provisional analysis of information actually received or reasonably available to the employer.",
        "General awareness of sickness does not necessarily establish knowledge, actual or constructive, of the disability relied upon.",
        "caci had legal knowledge",
        "section 15 knowledge is established",
    ),
    ("DA-001", "1.0", "DA-JUSTIFICATION"): _p(
        "Evidence concerning the employer's stated aims, operational reasons, alternatives and proportionality-related facts is relevant to objective justification.",
        "the factual material potentially relevant to legitimate aim and proportionality",
        "The current record may identify justification-related facts or respondent explanations without deciding whether the statutory defence succeeds.",
        "Identifying an employer reason or aim does not establish that the treatment was a proportionate means of achieving a legitimate aim.",
        "objective justification is established",
        "the treatment was justified",
    ),
    ("DA-001", "1.0", "DA-TIMING"): _p(
        "Evidence identifying the treatment and its date is relevant to locating the alleged section 15 act in time and to later limitation analysis.",
        "the chronology of the treatment relied upon",
        "The current record may establish dates or periods without deciding any limitation question.",
        "A documented date does not determine whether a claim is legally in time.",
        "the claim is in time",
        "the claim is out of time",
    ),

    # EK-001 / 1.0
    ("EK-001", "1.0", "EK-INFORMATION"): _p(
        "Evidence of the condition, symptoms, functional effects or disability-related information defines the subject matter that could potentially have been known by the employer.",
        "the content of the disability-related information existing at the material time",
        "The current record may identify what health or functional information existed without assuming that CACI received it.",
        "The existence of medical or claimant information does not itself establish employer receipt or knowledge.",
        "caci knew about the disability",
    ),
    ("EK-001", "1.0", "EK-RECIPIENT"): _p(
        "Evidence identifying a recipient, acknowledgement, discussion or access route is relevant to who within the employer may have received particular information.",
        "which CACI personnel received or discussed relevant disability-related information",
        "The current record may support provisional identification of recipients where communications or acknowledgements are actually documented.",
        "Container ownership, general organisational access or involvement alone does not establish that a named decision-maker received particular information.",
        "caci had legal knowledge",
        "the manager received the report",
    ),
    ("EK-001", "1.0", "EK-DIRECT-KNOWLEDGE"): _p(
        "Direct receipt, acknowledgement, reply or discussion is relevant to the factual basis for actual employer knowledge.",
        "the factual basis for direct or actual employer knowledge",
        "The current record may support an argument about actual awareness to the extent that it documents specific information being received, acknowledged or discussed.",
        "General participation in rehabilitation or awareness of sickness does not by itself establish receipt of a specific diagnosis or recommendation.",
        "caci had legal knowledge",
        "caci knew about the disability",
    ),
    ("EK-001", "1.0", "EK-CONSTRUCTIVE-KNOWLEDGE"): _p(
        "Long-term absence, rehabilitation activity, insurer/OH involvement and other available information may be relevant to what the employer could reasonably have been expected to know or investigate.",
        "the factual material potentially relevant to constructive knowledge",
        "The current record may identify circumstances capable of supporting a constructive-knowledge argument without determining the legal standard.",
        "The presence of warning signs or available records does not itself establish constructive knowledge.",
        "constructive knowledge is established",
    ),
    ("EK-001", "1.0", "EK-DISADVANTAGE-KNOWLEDGE"): _p(
        "Evidence communicating travel difficulty, fatigue, anxiety, working limitations or adjustment need may be relevant to knowledge of the particular disadvantage relied upon.",
        "the employer's awareness of the particular work-related disadvantage",
        "The record may support provisional analysis of what difficulties or disadvantages were communicated to CACI.",
        "Knowledge of a health condition does not automatically establish knowledge of every particular disadvantage.",
        "knowledge of disadvantage is established",
    ),
    ("EK-001", "1.0", "EK-CLAIMANT-ASSERTIONS"): _p(
        "The claimant's assertions identify the knowledge case being advanced and the propositions requiring corroboration or limitation analysis.",
        "the claimant's asserted account of what the employer knew",
        "The current record may describe the claimant's asserted knowledge case while preserving its status as party evidence or source assertion.",
        "A claimant assertion establishes that the assertion was made, not that the employer in fact possessed the asserted knowledge.",
        "caci knew because the claimant says so",
    ),
    ("EK-001", "1.0", "EK-RESPONDENT-POSITION"): _p(
        "Respondent admissions, denials and pleaded positions are relevant to identifying what aspects of knowledge are accepted or put in issue.",
        "the respondent's position on employer knowledge",
        "The current record may identify the respondent's pleaded or documented stance without treating that stance as factual truth.",
        "A respondent denial or admission is evidence of its position and must be assessed alongside the wider record.",
        "the respondent position is true",
    ),
    ("EK-001", "1.0", "EK-UNRESOLVED"): _p(
        "Unresolved knowledge propositions identify the factual boundaries that prevent a stronger legal analysis of actual or constructive knowledge.",
        "the unresolved scope and content of employer knowledge",
        "The current record should preserve uncertainty over information, recipients or timing that M4 has not resolved.",
        "M5 must not fill unresolved knowledge questions by inference merely because the wider narrative would be coherent.",
        "caci had legal knowledge",
    ),
    ("EK-001", "1.0", "EK-TIMING"): _p(
        "Evidence of when information was received or awareness arose is relevant to whether knowledge existed at the time of the act, omission or period under examination.",
        "the chronology of alleged employer knowledge",
        "The current record may establish dates of communications or events while leaving the scope of knowledge at each date provisional.",
        "Chronology alone does not establish what was known or whether the legal knowledge test was met at the relevant time.",
        "caci had legal knowledge",
    ),

    # LIM-001 / 1.0
    ("LIM-001", "1.0", "LIM-ACTS"): _p(
        "Evidence identifying alleged acts or omissions is relevant to defining the conduct whose timing and legal character must later be analysed under section 123.",
        "the factual acts or omissions relied upon for limitation purposes",
        "The current record may identify alleged conduct without deciding whether each event was discriminatory or legally actionable.",
        "An alleged act or omission being documented does not itself establish a discriminatory act.",
        "the act was discriminatory",
    ),
    ("LIM-001", "1.0", "LIM-DATES"): _p(
        "Dates and periods attached to alleged acts or omissions form the factual chronology required for limitation analysis.",
        "the dates and periods of the alleged conduct",
        "The current record may establish dates while leaving their legal limitation significance open.",
        "A date does not itself determine when time legally began or whether a claim was timely.",
        "the claim is in time",
        "the claim is out of time",
    ),
    ("LIM-001", "1.0", "LIM-SEPARATE-OR-CONSEQUENCE"): _p(
        "Evidence about later events and the parties' characterisations is relevant to whether those events are relied upon as separate acts, continuing conduct or consequences of earlier conduct.",
        "the factual basis for competing separate-act, continuing-conduct or consequence characterisations",
        "The record may identify competing factual characterisations without choosing the legally correct one.",
        "M5 does not decide whether later events are separate acts, continuing conduct or mere consequences.",
        "later events were separate acts",
        "later events were only consequences",
    ),
    ("LIM-001", "1.0", "LIM-CONTINUING-CONDUCT"): _p(
        "Evidence of linked acts, repeated omissions, ongoing policies or later conduct may be relevant to the factual basis of a conduct-extending-over-a-period argument.",
        "the factual basis for a continuing-conduct argument",
        "The current record may show a sequence or pattern capable of supporting such an argument while leaving the legal characterisation unresolved.",
        "Continuing effects, consequences or repeated references to earlier events do not by themselves establish conduct extending over a period.",
        "there was a continuing act",
        "a continuing act existed",
    ),
    ("LIM-001", "1.0", "LIM-END-DATE"): _p(
        "Evidence identifying the last alleged act or omission is relevant to the proposed end date of any conduct said to extend over a period.",
        "the factual end date advanced for alleged continuing conduct",
        "The current record may identify a candidate final event or omission without deciding that the conduct legally continued until that date.",
        "An end date becomes legally significant only if the alleged continuing-conduct characterisation is later accepted.",
        "the continuing act ended on",
    ),
    ("LIM-001", "1.0", "LIM-PRESENTATION"): _p(
        "Claim-presentation and ACAS Early Conciliation dates are relevant to the procedural chronology against which limitation arguments are assessed.",
        "the factual claim-presentation and ACAS chronology",
        "The current record may establish procedural dates without deciding whether the claim was legally presented in time.",
        "Procedural dates alone do not resolve the characterisation or extension questions that may affect limitation.",
        "the claim is in time",
        "the claim is out of time",
    ),
    ("LIM-001", "1.0", "LIM-DELAY-EXPLANATION"): _p(
        "Evidence explaining delay is relevant to the factual circumstances that may later be considered in a just-and-equitable extension analysis.",
        "the factual explanation advanced for delay",
        "The current record may identify reasons advanced for delay and evidence bearing on them without determining their legal weight.",
        "The existence of an explanation does not establish that an extension should be granted.",
        "time should be extended",
        "an extension should be granted",
    ),
    ("LIM-001", "1.0", "LIM-RESPONDENT-POSITION"): _p(
        "The respondent's pleaded or documented limitation position is relevant to identifying the competing characterisation of acts, dates and timeliness.",
        "the respondent's limitation position",
        "The current record may identify the respondent's limitation case without treating its characterisation as established fact.",
        "A pleaded limitation position records the respondent's case; it does not itself determine the correct legal outcome.",
        "the respondent is correct on limitation",
    ),
    ("LIM-001", "1.0", "LIM-PREJUDICE-EVIDENCE"): _p(
        "Evidence concerning evidential cogency, lost material, delay effects and prejudice to either party may be relevant to later discretionary analysis.",
        "the factual prejudice and evidential-cogency considerations arising from delay",
        "The current record may identify prejudice-related facts without balancing them to a final discretionary outcome.",
        "M5 does not decide which party suffers greater legal prejudice or whether that consideration determines an extension.",
        "prejudice requires an extension",
    ),
    ("LIM-001", "1.0", "LIM-JE-FACTORS"): _p(
        "Evidence concerning the length/reasons for delay, disability or health circumstances, prejudice, cogency and party conduct may be relevant to a just-and-equitable extension analysis.",
        "the factual matters potentially relevant to a just-and-equitable extension",
        "The current record may identify relevant discretionary factors without balancing them to a final result.",
        "M5 does not decide whether it would be just and equitable to extend time.",
        "time should be extended",
        "it is just and equitable to extend time",
    ),
}


_STATUS_CEILING: Final[dict[ElementAnalysisStatus, Confidence]] = {
    ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD: Confidence.HIGH,
    ElementAnalysisStatus.PARTIALLY_SUPPORTED: Confidence.MEDIUM,
    ElementAnalysisStatus.DISPUTED: Confidence.MEDIUM,
    ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED: Confidence.LOW,
    ElementAnalysisStatus.UNRESOLVED: Confidence.LOW,
}
_CONFIDENCE_RANK: Final[dict[Confidence, int]] = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


def profile_for(issue_definition_id: str, version: str, element_id: str) -> LegalSignificanceProfile:
    """Return the exact versioned legal-significance profile or fail closed."""

    key = (issue_definition_id.strip(), version.strip(), element_id.strip())
    try:
        return LEGAL_SIGNIFICANCE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(
            "No M5 legal-significance profile exists for "
            f"{key[0]}/{key[1]}/{key[2]}; M5 will not improvise legal reasoning."
        ) from exc


def provisional_status_for(assessment: ElementEvidenceAssessment) -> ElementAnalysisStatus:
    """Derive a conservative M5 status without changing any M4 status."""

    statuses = tuple(item.status for item in assessment.assessed_propositions)
    roles = {item.analytical_role for item in assessment.evidence_assessments}

    if assessment.disputed_matters or PropositionAssessmentStatus.DISPUTED in statuses:
        return ElementAnalysisStatus.DISPUTED

    if not assessment.evidence_assessments:
        return ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED

    established = statuses.count(PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE)
    supported = statuses.count(PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)
    adverse_or_conflicting = bool(
        {AnalyticalRole.ADVERSE, AnalyticalRole.CONFLICTING} & roles
    )
    has_material_gap = bool(assessment.evidential_gaps)
    has_unresolved = bool(assessment.unresolved_matters)

    if (
        established >= 1
        and assessment.assessment_confidence is Confidence.HIGH
        and not has_material_gap
        and not has_unresolved
        and not adverse_or_conflicting
    ):
        return ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD

    if established >= 1 or supported >= 1:
        return ElementAnalysisStatus.PARTIALLY_SUPPORTED

    only_non_supporting = all(
        status in {
            PropositionAssessmentStatus.UNRESOLVED,
            PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
        }
        for status in statuses
    ) if statuses else True
    if only_non_supporting and roles <= {AnalyticalRole.NEUTRAL, AnalyticalRole.ADVERSE}:
        return ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED

    return ElementAnalysisStatus.UNRESOLVED


def analysis_confidence_for(
    m4_confidence: Confidence,
    status: ElementAnalysisStatus,
) -> Confidence:
    """Cap M5 confidence at both the M4 level and the M5-status ceiling."""

    ceiling = _STATUS_CEILING[status]
    return (
        m4_confidence
        if _CONFIDENCE_RANK[m4_confidence] <= _CONFIDENCE_RANK[ceiling]
        else ceiling
    )


def provisional_analysis_for(
    profile: LegalSignificanceProfile,
    status: ElementAnalysisStatus,
) -> str:
    """Render a deterministic non-merits provisional analysis."""

    subject = profile.analysis_subject
    if status is ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD:
        lead = (
            f"The frozen evidential record provides comparatively strong factual support relevant to {subject}."
        )
    elif status is ElementAnalysisStatus.PARTIALLY_SUPPORTED:
        lead = (
            f"The frozen evidential record provides partial factual support relevant to {subject}, but material limitations remain."
        )
    elif status is ElementAnalysisStatus.DISPUTED:
        lead = (
            f"The frozen evidential record contains a material factual dispute relevant to {subject}; M5 does not resolve credibility."
        )
    elif status is ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED:
        lead = (
            f"The current mapped and assessed record is insufficiently evidenced for a secure provisional analysis of {subject}."
        )
    else:
        lead = f"The current evidential position remains unresolved as to {subject}."

    # The guard applies to the generated analytical proposition itself. The
    # controlled caveat may quote a prohibited conclusion in expressly
    # negative form (for example, "does not determine whether time should be
    # extended"), which must not be mistaken for an affirmative merits result.
    generated = f"{lead} {profile.safe_analysis_pattern}"
    _assert_safe_text(generated, profile)
    return f"{generated} {profile.key_caveat}"


def _assert_safe_text(text: str, profile: LegalSignificanceProfile) -> None:
    folded = " ".join(text.casefold().split())
    for prohibited in profile.prohibited_conclusions:
        if prohibited in folded:
            raise ValueError(
                f"M5 generated prohibited merits language: {prohibited!r}."
            )


def assert_profile_coverage(expected_keys: set[tuple[str, str, str]]) -> None:
    """Fail unless M5 has exact profile coverage and no silent extras."""

    actual = set(LEGAL_SIGNIFICANCE_PROFILES)
    if actual != expected_keys:
        missing = sorted(expected_keys - actual)
        extra = sorted(actual - expected_keys)
        raise ValueError(f"M5 profile coverage mismatch; missing={missing}, extra={extra}.")


__all__ = [
    "LEGAL_SIGNIFICANCE_PROFILES",
    "LegalSignificanceProfile",
    "analysis_confidence_for",
    "assert_profile_coverage",
    "profile_for",
    "provisional_analysis_for",
    "provisional_status_for",
]
