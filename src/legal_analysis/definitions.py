"""Versioned controlled legal issue definitions for Sprint 2.3 Milestone 1.

These objects are domain data, not prompt text. A substantive future change to
an existing legal definition must be introduced as a new version rather than by
silently changing the meaning of an existing ID/version pair.
"""

from __future__ import annotations

from .models import IssueDefinition, IssueElementDefinition


def _element(
    element_id: str,
    name: str,
    question: str,
    *notes: str,
) -> IssueElementDefinition:
    return IssueElementDefinition(
        element_id=element_id,
        name=name,
        question_to_determine=question,
        notes=tuple(notes),
    )


REASONABLE_ADJUSTMENTS_V1 = IssueDefinition(
    definition_id="RA-001",
    name="Reasonable adjustments",
    version="1.0",
    legal_framework=(
        "Equality Act 2010 ss.20-21",
        "Equality Act 2010 Schedule 8 (work)",
    ),
    description=(
        "Analyse the duty to make reasonable adjustments by separating disability, "
        "knowledge, the relevant workplace context, disadvantage, potential steps, "
        "reasonableness, alleged failure and timing."
    ),
    elements=(
        _element(
            "RA-DISABILITY",
            "Disability",
            "Was the claimant disabled within the meaning of the Equality Act at the relevant time?",
        ),
        _element(
            "RA-KNOWLEDGE",
            "Employer knowledge",
            "Did the employer know, or could it reasonably have been expected to know, of the disability and relevant disadvantage?",
        ),
        _element(
            "RA-WORKPLACE-CONTEXT",
            "Relevant workplace context",
            "What provision, criterion or practice, physical feature, auxiliary-aid issue, arrangement or workplace circumstance is said to engage the adjustment duty?",
        ),
        _element(
            "RA-DISADVANTAGE",
            "Substantial disadvantage",
            "What substantial disadvantage did the claimant experience in comparison with a person who was not disabled?",
        ),
        _element(
            "RA-ADJUSTMENT",
            "Potential adjustment",
            "What adjustment was proposed, requested, identified or otherwise reasonably available for consideration?",
        ),
        _element(
            "RA-REASONABLENESS",
            "Reasonableness",
            "What evidence bears on whether the proposed or identifiable adjustment was reasonable in the circumstances?",
        ),
        _element(
            "RA-FAILURE",
            "Employer act or omission",
            "What did the employer do or fail to do in relation to the proposed or identifiable adjustment?",
        ),
        _element(
            "RA-TIMING",
            "Timing and continuing conduct",
            "When did the alleged act or omission occur, and is any continuing conduct alleged?",
        ),
    ),
)


DISCRIMINATION_ARISING_V1 = IssueDefinition(
    definition_id="DA-001",
    name="Discrimination arising from disability",
    version="1.0",
    legal_framework=("Equality Act 2010 s.15",),
    description=(
        "Analyse alleged unfavourable treatment because of something arising in "
        "consequence of disability, including knowledge and justification."
    ),
    elements=(
        _element(
            "DA-DISABILITY",
            "Disability",
            "Was the claimant disabled within the meaning of the Equality Act at the relevant time?",
        ),
        _element(
            "DA-SOMETHING-ARISING",
            "Something arising from disability",
            "What fact, consequence, behaviour, absence, need or circumstance is said to have arisen in consequence of the disability?",
        ),
        _element(
            "DA-UNFAVOURABLE-TREATMENT",
            "Unfavourable treatment",
            "What treatment is alleged to have been unfavourable?",
        ),
        _element(
            "DA-CAUSATION",
            "Causative relationship",
            "Was the unfavourable treatment because of the identified something arising in consequence of disability?",
        ),
        _element(
            "DA-KNOWLEDGE",
            "Employer knowledge",
            "Did the employer know, or could it reasonably have been expected to know, that the claimant had the disability?",
        ),
        _element(
            "DA-JUSTIFICATION",
            "Objective justification",
            "What legitimate aim and proportionality case is advanced for the treatment, and what evidence bears on it?",
        ),
        _element(
            "DA-TIMING",
            "Relevant act and date",
            "What act or treatment is relied upon and when did it occur?",
        ),
    ),
)


EMPLOYER_KNOWLEDGE_V1 = IssueDefinition(
    definition_id="EK-001",
    name="Employer knowledge of disability",
    version="1.0",
    legal_framework=(
        "Equality Act 2010 s.15(2)",
        "Equality Act 2010 Schedule 8 (work-related reasonable-adjustment knowledge provisions)",
    ),
    description=(
        "Analyse what the employer actually or constructively knew, who received "
        "relevant information, what remains assertion or inference, and when."
    ),
    elements=(
        _element(
            "EK-INFORMATION",
            "Relevant condition or information",
            "What disability-related condition, symptoms, functional effects or other relevant information existed at the material time?",
        ),
        _element(
            "EK-RECIPIENT",
            "Recipient within the employer",
            "Who within the employer is shown to have received, discussed or had access to relevant information, and in what capacity?",
        ),
        _element(
            "EK-DIRECT-KNOWLEDGE",
            "Direct evidence of knowledge",
            "What contemporaneous evidence directly records receipt, acknowledgement, discussion or awareness of relevant disability information?",
        ),
        _element(
            "EK-CONSTRUCTIVE-KNOWLEDGE",
            "Constructive-knowledge material",
            "What facts may bear on what the employer could reasonably have been expected to know?",
        ),
        _element(
            "EK-DISADVANTAGE-KNOWLEDGE",
            "Knowledge of relevant disadvantage",
            "Where legally relevant, what evidence addresses whether the employer knew or could reasonably have been expected to know of the relevant disadvantage?",
        ),
        _element(
            "EK-CLAIMANT-ASSERTIONS",
            "Claimant assertions",
            "What does the claimant assert the employer knew, and what evidence independently supports or limits those assertions?",
        ),
        _element(
            "EK-RESPONDENT-POSITION",
            "Respondent position",
            "What does the respondent admit, deny or put in issue about knowledge?",
        ),
        _element(
            "EK-UNRESOLVED",
            "Unresolved knowledge propositions",
            "Which propositions about employer knowledge remain disputed or inferential on the current evidence?",
        ),
        _element(
            "EK-TIMING",
            "Relevant timing",
            "When is each item of alleged employer knowledge said to have arisen and for which act, omission or period is it relevant?",
        ),
    ),
)


LIMITATION_V1 = IssueDefinition(
    definition_id="LIM-001",
    name="Limitation, continuing act and just and equitable extension",
    version="1.0",
    legal_framework=("Equality Act 2010 s.123",),
    description=(
        "Analyse limitation by mapping alleged acts and omissions, dates, competing "
        "continuing-conduct characterisations, delay explanations and extension factors."
    ),
    elements=(
        _element(
            "LIM-ACTS",
            "Alleged acts or omissions",
            "What discriminatory acts or omissions are alleged?",
        ),
        _element(
            "LIM-DATES",
            "Dates of acts or omissions",
            "What date or period is attributed to each alleged act or omission?",
        ),
        _element(
            "LIM-SEPARATE-OR-CONSEQUENCE",
            "Separate acts or consequences",
            "Are later events alleged to be separate discriminatory acts, continuing conduct, or consequences of earlier acts?",
        ),
        _element(
            "LIM-CONTINUING-CONDUCT",
            "Conduct extending over a period",
            "What evidence and legal characterisation support or undermine an allegation of conduct extending over a period?",
        ),
        _element(
            "LIM-END-DATE",
            "End of alleged continuing conduct",
            "If continuing conduct is alleged, when is that conduct said to have ended?",
        ),
        _element(
            "LIM-PRESENTATION",
            "Claim and ACAS timing",
            "What are the relevant claim-presentation and ACAS Early Conciliation dates, where applicable?",
        ),
        _element(
            "LIM-DELAY-EXPLANATION",
            "Explanation for delay",
            "What explanation is advanced for any delay in presenting the claim?",
        ),
        _element(
            "LIM-RESPONDENT-POSITION",
            "Respondent limitation position",
            "How does the respondent characterise the relevant acts, dates and limitation position?",
        ),
        _element(
            "LIM-PREJUDICE-EVIDENCE",
            "Prejudice and evidential considerations",
            "What evidence bears on prejudice, evidential cogency or the practical effect of delay on either party?",
        ),
        _element(
            "LIM-JE-FACTORS",
            "Just and equitable extension factors",
            "What matters are relied upon as relevant to whether any extension of time would be just and equitable?",
        ),
    ),
)


INITIAL_ISSUE_DEFINITIONS: tuple[IssueDefinition, ...] = (
    REASONABLE_ADJUSTMENTS_V1,
    DISCRIMINATION_ARISING_V1,
    EMPLOYER_KNOWLEDGE_V1,
    LIMITATION_V1,
)
