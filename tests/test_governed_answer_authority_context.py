import hashlib
import json

import pytest
from dataclasses import dataclass
from enum import StrEnum
from types import SimpleNamespace

import governed_answer_authority.context as context_module
from governed_answer_authority.context import (
    build_constrained_governed_answer_prompt,
    build_runtime_authority_context,
)
from governed_answer_authority.models import AnalyticalAuthorityMode, AuthorityRoutingResult


CASE_ID = "11111111-1111-4111-8111-111111111111"


class Status(StrEnum):
    SUPPORTED = "supported_but_not_established"


@dataclass(frozen=True)
class Use:
    issue_analysis_id: str
    element_id: str
    evidence_key: str
    analytical_role: str = "supporting"


@dataclass(frozen=True)
class Coordinate:
    issue_analysis_id: str
    element_id: str
    evidence_key: str


@dataclass(frozen=True)
class Assessment:
    evidence_key: str
    use_coordinates: tuple[Coordinate, ...]
    observations: tuple[str, ...]


def make_authority():
    propositions = (
        SimpleNamespace(
            text="first frozen proposition",
            status=Status.SUPPORTED,
            confidence=SimpleNamespace(value="medium"),
            evidence_keys=("e1",),
            rationale="r1",
        ),
        SimpleNamespace(
            text="second frozen proposition",
            status=Status.SUPPORTED,
            confidence=SimpleNamespace(value="medium"),
            evidence_keys=("e2",),
            rationale="r2",
        ),
    )
    element_assessment = SimpleNamespace(
        element_id="RA-DUTY",
        assessed_propositions=propositions,
        evidential_gaps=(),
    )
    element_analysis = SimpleNamespace(
        element_id="RA-DUTY",
        provisional_status=SimpleNamespace(value="partially_supported"),
        analysis_confidence=SimpleNamespace(value="medium"),
        limitations=("limitation",),
        unresolved_matters=("unresolved",),
    )
    selected = SimpleNamespace(
        case_id=CASE_ID,
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        assessment_result=SimpleNamespace(element_assessments=(element_assessment,)),
        element_analyses=(element_analysis,),
        overall_limitations=("overall limitation",),
    )
    binding = SimpleNamespace(
        use=Use("a1", "RA-DUTY", "e1"),
        evidence=SimpleNamespace(evidence_key="e1"),
    )
    u9c = SimpleNamespace(
        assessments=(Assessment("e1", (Coordinate("a1", "RA-DUTY", "e1"),), ("obs",)),)
    )
    return SimpleNamespace(
        structured_legal_analysis_results=(selected,),
        manifest=SimpleNamespace(authority_id="sha256:" + "a" * 64),
        active_pointer=SimpleNamespace(activation_id="sha256:" + "b" * 64),
        governed_issue_evidence_map=SimpleNamespace(bindings=(binding,)),
        governed_evidential_analysis=SimpleNamespace(evidence_assessments=u9c.assessments),
    )


def test_context_preserves_native_proposition_order_and_coordinates():
    routing = AuthorityRoutingResult(
        mode=AnalyticalAuthorityMode.APPLIED,
        reason="exact",
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
    )
    context = build_runtime_authority_context(
        authority=make_authority(),
        routing=routing,
        inspected_evidence_keys=("e1", "e2"),
    )
    propositions = context.elements[0].propositions
    assert [p.reference.source_proposition_index for p in propositions] == [0, 1]
    assert [p.text for p in propositions] == [
        "first frozen proposition",
        "second frozen proposition",
    ]
    assert context.evidence_uses[0].evidence_key == "e1"
    assert json.loads(context.evidence_assessments[0].payload_json)["evidence_key"] == "e1"


def test_prompt_allows_only_bound_conservative_answer_prose_and_forbids_reconstruction():
    routing = AuthorityRoutingResult(
        mode=AnalyticalAuthorityMode.APPLIED,
        reason="exact",
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
    )
    context = build_runtime_authority_context(
        authority=make_authority(),
        routing=routing,
        inspected_evidence_keys=("e1",),
    )
    prompt = build_constrained_governed_answer_prompt(base_prompt="U8 BASE", context=context)
    assert "U8 BASE" in prompt
    assert "Do not retrieve, remap, reassess, rerender, rebuild" in prompt
    assert "organise, explain, summarise and conservatively paraphrase" in prompt
    assert "Every substantive answer statement" in prompt
    assert '"text": non-empty answer statement written for the user' in prompt
    assert '"source_proposition_index" value must be a non-negative integer (0 or greater)' in prompt
    assert 'each proposition_semantics row\'s "status" value is the exact frozen proposition' in prompt
    assert '"source_status": must exactly equal the "status" value of every referenced' in prompt
    assert 'when all referenced rows have the same "status" value' in prompt


def _prompt_context(*, inspected_evidence_keys=("e1",)):
    routing = AuthorityRoutingResult(
        mode=AnalyticalAuthorityMode.APPLIED,
        reason="exact",
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
    )
    return build_runtime_authority_context(
        authority=make_authority(),
        routing=routing,
        inspected_evidence_keys=inspected_evidence_keys,
    )


def _payload_for(context):
    return context_module._context_payload(context)


def _reconstruct_propositions(payload):
    table = payload["evidence_key_table"]
    rows = payload["proposition_semantics"]
    reconstructed = []
    for element in payload["elements"]:
        for source_index, semantic_index in element["proposition_coordinate_semantic_refs"]:
            row = rows[semantic_index]
            reconstructed.append(
                (
                    element["element_id"],
                    source_index,
                    row["text"],
                    row["status"],
                    row["confidence"],
                    tuple(table[index] for index in row["evidence_key_indexes"]),
                    row["rationale"],
                )
            )
    return reconstructed


def test_compact_prompt_projection_reconstructs_every_proposition_exactly():
    context = _prompt_context()
    payload = _payload_for(context)

    expected = [
        (
            element.element_id,
            proposition.reference.source_proposition_index,
            proposition.text,
            proposition.status,
            proposition.confidence,
            proposition.evidence_keys,
            proposition.rationale,
        )
        for element in context.elements
        for proposition in element.propositions
    ]
    assert _reconstruct_propositions(payload) == expected
    assert tuple(
        payload["evidence_key_table"][index]
        for index in payload["inspected_evidence_key_indexes"]
    ) == context.inspected_evidence_keys


def test_compact_prompt_projection_preserves_uninspected_proposition_key_attachment():
    context = _prompt_context(inspected_evidence_keys=("e1",))
    payload = _payload_for(context)

    assert payload["evidence_key_table"] == ["e1", "e2"]
    assert payload["inspected_evidence_key_indexes"] == [0]
    reconstructed = _reconstruct_propositions(payload)
    assert reconstructed[1][5] == ("e2",)


def test_compact_prompt_projection_excludes_raw_u9b_u9c_payloads_but_binds_them():
    context = _prompt_context()
    payload = _payload_for(context)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert "payload_json" not in serialized
    uses_json = context_module._canonical_json(context.evidence_uses)
    assessments_json = context_module._canonical_json(context.evidence_assessments)
    assert payload["provenance_binding"]["evidence_uses"] == {
        "count": len(context.evidence_uses),
        "sha256": hashlib.sha256(uses_json.encode("utf-8")).hexdigest(),
    }
    assert payload["provenance_binding"]["evidence_assessments"] == {
        "count": len(context.evidence_assessments),
        "sha256": hashlib.sha256(assessments_json.encode("utf-8")).hexdigest(),
    }


def test_compact_prompt_projection_deduplicates_exact_semantic_bodies():
    context = _prompt_context(inspected_evidence_keys=("e1", "e2"))
    first = context.elements[0].propositions[0]
    duplicate = first.__class__(
        reference=first.reference.__class__(
            issue_analysis_id=first.reference.issue_analysis_id,
            element_id=first.reference.element_id,
            source_proposition_index=2,
        ),
        text=first.text,
        status=first.status,
        confidence=first.confidence,
        evidence_keys=first.evidence_keys,
        rationale=first.rationale,
    )
    element = context.elements[0]
    duplicated_element = element.__class__(
        element_id=element.element_id,
        provisional_status=element.provisional_status,
        analysis_confidence=element.analysis_confidence,
        limitations=element.limitations,
        unresolved_matters=element.unresolved_matters,
        evidential_gaps_json=element.evidential_gaps_json,
        propositions=element.propositions + (duplicate,),
    )
    duplicated_context = context.__class__(
        case_id=context.case_id,
        authority_id=context.authority_id,
        activation_id=context.activation_id,
        issue_analysis_id=context.issue_analysis_id,
        issue_definition_id=context.issue_definition_id,
        issue_definition_version=context.issue_definition_version,
        issue_name=context.issue_name,
        selector_version=context.selector_version,
        inspected_evidence_keys=context.inspected_evidence_keys,
        overall_limitations=context.overall_limitations,
        elements=(duplicated_element,),
        evidence_uses=context.evidence_uses,
        evidence_assessments=context.evidence_assessments,
    )

    payload = _payload_for(duplicated_context)
    assert len(payload["proposition_semantics"]) == 2
    assert payload["elements"][0]["proposition_coordinate_semantic_refs"] == [
        [0, 0],
        [1, 1],
        [2, 0],
    ]


def test_compact_projection_is_smaller_than_lossless_runtime_payload():
    context = _prompt_context(inspected_evidence_keys=("e1",))
    compact = json.dumps(
        _payload_for(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    lossless = context_module._canonical_json(context)

    assert len(compact.encode("utf-8")) < len(lossless.encode("utf-8"))

def _answer_payload_for(context):
    return context_module._answer_prompt_payload(context)


def test_answer_prompt_projection_excludes_ungrounded_proposition_without_changing_full_context():
    context = _prompt_context(inspected_evidence_keys=("e1",))

    full_payload = _payload_for(context)
    answer_payload = _answer_payload_for(context)

    assert _reconstruct_propositions(full_payload)[1][5] == ("e2",)
    assert answer_payload["evidence_key_table"] == ["e1"]
    assert answer_payload["elements"][0]["proposition_coordinate_semantic_refs"] == [[0, 0]]
    assert answer_payload["proposition_semantics"] == [
        {
            "text": "first frozen proposition",
            "status": Status.SUPPORTED.value,
            "confidence": "medium",
            "evidence_key_indexes": [0],
            "rationale": "r1",
        }
    ]


def test_answer_prompt_projection_preserves_original_source_index_without_renumbering():
    context = _prompt_context(inspected_evidence_keys=("e2",))

    answer_payload = _answer_payload_for(context)

    assert answer_payload["evidence_key_table"] == ["e2"]
    assert answer_payload["elements"][0]["proposition_coordinate_semantic_refs"] == [[1, 0]]
    assert answer_payload["proposition_semantics"][0]["text"] == "second frozen proposition"


def test_answer_prompt_projection_exposes_only_inspected_intersection_for_eligible_proposition():
    context = _prompt_context(inspected_evidence_keys=("e1",))
    element = context.elements[0]
    first = element.propositions[0]
    mixed_first = first.__class__(
        reference=first.reference,
        text=first.text,
        status=first.status,
        confidence=first.confidence,
        evidence_keys=("e1", "e2"),
        rationale=first.rationale,
    )
    mixed_element = element.__class__(
        element_id=element.element_id,
        provisional_status=element.provisional_status,
        analysis_confidence=element.analysis_confidence,
        limitations=element.limitations,
        unresolved_matters=element.unresolved_matters,
        evidential_gaps_json=element.evidential_gaps_json,
        propositions=(mixed_first, element.propositions[1]),
    )
    mixed_context = context.__class__(
        case_id=context.case_id,
        authority_id=context.authority_id,
        activation_id=context.activation_id,
        issue_analysis_id=context.issue_analysis_id,
        issue_definition_id=context.issue_definition_id,
        issue_definition_version=context.issue_definition_version,
        issue_name=context.issue_name,
        selector_version=context.selector_version,
        inspected_evidence_keys=context.inspected_evidence_keys,
        overall_limitations=context.overall_limitations,
        elements=(mixed_element,),
        evidence_uses=context.evidence_uses,
        evidence_assessments=context.evidence_assessments,
    )

    full_payload = _payload_for(mixed_context)
    answer_payload = _answer_payload_for(mixed_context)

    assert _reconstruct_propositions(full_payload)[0][5] == ("e1", "e2")
    assert answer_payload["evidence_key_table"] == ["e1"]
    assert answer_payload["proposition_semantics"][0]["evidence_key_indexes"] == [0]
    answer_evidence = tuple(
        answer_payload["evidence_key_table"][index]
        for row in answer_payload["proposition_semantics"]
        for index in row["evidence_key_indexes"]
    )
    assert answer_evidence == ("e1",)


def test_answer_prompt_projection_fails_closed_when_no_proposition_has_inspected_grounding():
    context = _prompt_context(inspected_evidence_keys=("foreign",))

    with pytest.raises(
        context_module.GovernedAnswerAuthorityContextError,
        match="No answer-eligible frozen propositions",
    ):
        _answer_payload_for(context)

    with pytest.raises(
        context_module.GovernedAnswerAuthorityContextError,
        match="No answer-eligible frozen propositions",
    ):
        build_constrained_governed_answer_prompt(base_prompt="U8 BASE", context=context)


def test_answer_prompt_projection_is_deterministic_and_preserves_frozen_semantics():
    context = _prompt_context(inspected_evidence_keys=("e1",))

    first = _answer_payload_for(context)
    second = _answer_payload_for(context)

    assert first == second
    assert json.dumps(
        first,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == json.dumps(
        second,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    semantic = first["proposition_semantics"][0]
    source = context.elements[0].propositions[0]
    assert semantic["text"] == source.text
    assert semantic["status"] == source.status
    assert semantic["confidence"] == source.confidence
    assert semantic["rationale"] == source.rationale


def test_constrained_prompt_uses_only_answer_eligible_projection():
    context = _prompt_context(inspected_evidence_keys=("e1",))

    prompt = build_constrained_governed_answer_prompt(base_prompt="U8 BASE", context=context)

    assert "governed-answer-authority/answer-eligible-compact-v1" in prompt
    assert "first frozen proposition" in prompt
    assert "second frozen proposition" not in prompt
    assert '"e1"' in prompt
    assert '"e2"' not in prompt
    assert "original frozen proposition index and is never renumbered" in prompt
    assert "already inside the U8-inspected answer population" in prompt

