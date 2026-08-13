import json

import pytest

from governed_answer_authority.bindings import validate_answer_statement_bindings
from governed_answer_authority.models import (
    GovernedAnswerBindingError,
    PropositionReference,
    RuntimeAnswerAuthorityContext,
    RuntimeAuthorityElement,
    RuntimeAuthorityProposition,
)


def context():
    proposition = RuntimeAuthorityProposition(
        reference=PropositionReference("a1", "E1", 0),
        text="Frozen proposition text.",
        status="supported_but_not_established",
        confidence="medium",
        evidence_keys=("e1", "e2"),
        rationale="Frozen rationale.",
    )
    element = RuntimeAuthorityElement(
        element_id="E1",
        provisional_status="partially_supported",
        analysis_confidence="medium",
        limitations=(),
        unresolved_matters=(),
        evidential_gaps_json=(),
        propositions=(proposition,),
    )
    return RuntimeAnswerAuthorityContext(
        case_id="11111111-1111-4111-8111-111111111111",
        authority_id="sha256:" + "a" * 64,
        activation_id="sha256:" + "b" * 64,
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
        inspected_evidence_keys=("e1",),
        overall_limitations=("Frozen limitation.",),
        elements=(element,),
        evidence_uses=(),
        evidence_assessments=(),
    )


def raw(*, evidence_keys=("e1",), status="supported_but_not_established", index=0, text="CACI records support the point, but do not establish it conclusively."):
    return json.dumps({
        "statements": [{
            "statement_id": "S1",
            "text": text,
            "source_proposition_refs": [{
                "issue_analysis_id": "a1",
                "element_id": "E1",
                "source_proposition_index": index,
            }],
            "evidence_keys": list(evidence_keys),
            "source_status": status,
        }]
    })


def test_valid_binding_preserves_bound_generated_statement_text():
    result = validate_answer_statement_bindings(raw_output=raw(), context=context())
    assert result.answer.startswith(
        "[supported_but_not_established] CACI records support the point, but do not establish it conclusively."
    )
    assert "Frozen limitation." in result.answer
    assert result.relied_evidence_keys == ("e1",)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        raw(index=99),
    ],
)
def test_invalid_binding_fails_closed(payload):
    with pytest.raises(GovernedAnswerBindingError):
        validate_answer_statement_bindings(raw_output=payload, context=context())


def test_each_referenced_proposition_is_canonically_grounded():
    first = RuntimeAuthorityProposition(
        reference=PropositionReference("a1", "E1", 0),
        text="First frozen proposition.",
        status="supported_but_not_established",
        confidence="medium",
        evidence_keys=("e1",),
        rationale="r1",
    )
    second = RuntimeAuthorityProposition(
        reference=PropositionReference("a1", "E1", 1),
        text="Second frozen proposition.",
        status="supported_but_not_established",
        confidence="medium",
        evidence_keys=("e2",),
        rationale="r2",
    )
    element = RuntimeAuthorityElement(
        element_id="E1",
        provisional_status="partially_supported",
        analysis_confidence="medium",
        limitations=(),
        unresolved_matters=(),
        evidential_gaps_json=(),
        propositions=(first, second),
    )
    ctx = RuntimeAnswerAuthorityContext(
        case_id="11111111-1111-4111-8111-111111111111",
        authority_id="sha256:" + "a" * 64,
        activation_id="sha256:" + "b" * 64,
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
        inspected_evidence_keys=("e1", "e2"),
        overall_limitations=(),
        elements=(element,),
        evidence_uses=(),
        evidence_assessments=(),
    )
    payload = json.dumps({
        "statements": [{
            "statement_id": "S1",
            "text": "A summary combining both propositions.",
            "source_proposition_refs": [
                {"issue_analysis_id": "a1", "element_id": "E1", "source_proposition_index": 0},
                {"issue_analysis_id": "a1", "element_id": "E1", "source_proposition_index": 1},
            ],
            "evidence_keys": ["e1"],
            "source_status": "supported_but_not_established",
        }]
    })
    result = validate_answer_statement_bindings(
        raw_output=payload,
        context=ctx,
    )
    assert result.relied_evidence_keys == ("e1", "e2")
    assert result.answer.startswith("[supported_but_not_established]")


def test_generated_status_and_foreign_evidence_are_canonicalized():
    result = validate_answer_statement_bindings(
        raw_output=raw(
            status="established",
            evidence_keys=("foreign",),
        ),
        context=context(),
    )

    assert result.answer.startswith("[supported_but_not_established]")
    assert result.relied_evidence_keys == ("e1",)


def test_generated_uninspected_evidence_is_not_allowed_into_canonical_binding():
    result = validate_answer_statement_bindings(
        raw_output=raw(evidence_keys=("e2",)),
        context=context(),
    )

    assert result.relied_evidence_keys == ("e1",)


def _two_proposition_context(
    *,
    inspected_evidence_keys=("e1", "e2"),
    second_status="supported_but_not_established",
):
    first = RuntimeAuthorityProposition(
        reference=PropositionReference("a1", "E1", 0),
        text="First frozen proposition.",
        status="supported_but_not_established",
        confidence="medium",
        evidence_keys=("e1",),
        rationale="r1",
    )
    second = RuntimeAuthorityProposition(
        reference=PropositionReference("a1", "E1", 1),
        text="Second frozen proposition.",
        status=second_status,
        confidence="medium",
        evidence_keys=("e2",),
        rationale="r2",
    )
    element = RuntimeAuthorityElement(
        element_id="E1",
        provisional_status="partially_supported",
        analysis_confidence="medium",
        limitations=(),
        unresolved_matters=(),
        evidential_gaps_json=(),
        propositions=(first, second),
    )
    return RuntimeAnswerAuthorityContext(
        case_id="11111111-1111-4111-8111-111111111111",
        authority_id="sha256:" + "a" * 64,
        activation_id="sha256:" + "b" * 64,
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
        inspected_evidence_keys=tuple(inspected_evidence_keys),
        overall_limitations=(),
        elements=(element,),
        evidence_uses=(),
        evidence_assessments=(),
    )


def _two_proposition_raw():
    return json.dumps({
        "statements": [{
            "statement_id": "S1",
            "text": "A conservative summary of both frozen propositions.",
            "source_proposition_refs": [
                {
                    "issue_analysis_id": "a1",
                    "element_id": "E1",
                    "source_proposition_index": 0,
                },
                {
                    "issue_analysis_id": "a1",
                    "element_id": "E1",
                    "source_proposition_index": 1,
                },
            ],
            "evidence_keys": ["foreign"],
            "source_status": "established",
        }]
    })


def test_multi_reference_canonical_evidence_order_is_deterministic():
    result = validate_answer_statement_bindings(
        raw_output=_two_proposition_raw(),
        context=_two_proposition_context(),
    )

    assert result.relied_evidence_keys == ("e1", "e2")
    assert result.answer.startswith("[supported_but_not_established]")


def test_reference_without_inspected_attached_evidence_fails_closed():
    with pytest.raises(GovernedAnswerBindingError):
        validate_answer_statement_bindings(
            raw_output=_two_proposition_raw(),
            context=_two_proposition_context(
                inspected_evidence_keys=("e1",),
            ),
        )


def test_mixed_frozen_status_references_fail_closed():
    with pytest.raises(GovernedAnswerBindingError):
        validate_answer_statement_bindings(
            raw_output=_two_proposition_raw(),
            context=_two_proposition_context(
                second_status="established",
            ),
        )


def test_duplicate_proposition_references_still_fail_closed():
    payload = json.loads(raw())
    ref = payload["statements"][0]["source_proposition_refs"][0]
    payload["statements"][0]["source_proposition_refs"] = [ref, dict(ref)]

    with pytest.raises(GovernedAnswerBindingError):
        validate_answer_statement_bindings(
            raw_output=json.dumps(payload),
            context=context(),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_status", 1),
        ("evidence_keys", [1]),
        ("evidence_keys", []),
    ],
)
def test_generated_metadata_shape_remains_fail_closed(field, value):
    payload = json.loads(raw())
    payload["statements"][0][field] = value

    with pytest.raises(GovernedAnswerBindingError):
        validate_answer_statement_bindings(
            raw_output=json.dumps(payload),
            context=context(),
        )
