"""Lossless ephemeral projection of frozen analytical authority for answer restraint."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import json
from typing import Any

from .models import (
    AnalyticalAuthorityMode,
    AuthorityRoutingResult,
    GovernedAnswerAuthorityContextError,
    PropositionReference,
    RuntimeAnswerAuthorityContext,
    RuntimeAuthorityElement,
    RuntimeAuthorityEvidenceAssessment,
    RuntimeAuthorityEvidenceUse,
    RuntimeAuthorityProposition,
)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    raise GovernedAnswerAuthorityContextError(
        f"Unsupported frozen analytical payload type: {type(value).__name__}."
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _selected_result(authority: Any, issue_analysis_id: str) -> Any:
    matches = tuple(
        result
        for result in authority.structured_legal_analysis_results
        if result.issue_analysis_id == issue_analysis_id
    )
    if len(matches) != 1:
        raise GovernedAnswerAuthorityContextError(
            "Selected issue_analysis_id does not resolve uniquely inside the active authority."
        )
    return matches[0]


def build_runtime_authority_context(
    *,
    authority: Any,
    routing: AuthorityRoutingResult,
    inspected_evidence_keys: tuple[str, ...],
) -> RuntimeAnswerAuthorityContext:
    """Project one routed frozen analysis without creating analytical state."""

    if routing.mode is not AnalyticalAuthorityMode.APPLIED or not routing.issue_analysis_id:
        raise GovernedAnswerAuthorityContextError("Applied routing is required to build authority context.")
    if len(set(inspected_evidence_keys)) != len(inspected_evidence_keys):
        raise GovernedAnswerAuthorityContextError("U8 inspected evidence keys are not unique.")

    selected = _selected_result(authority, routing.issue_analysis_id)
    assessment_by_element = {
        item.element_id: item
        for item in selected.assessment_result.element_assessments
    }
    analysis_by_element = {item.element_id: item for item in selected.element_analyses}
    if set(assessment_by_element) != set(analysis_by_element):
        raise GovernedAnswerAuthorityContextError(
            "M4 element assessment set and M5 element analysis set do not match."
        )

    elements: list[RuntimeAuthorityElement] = []
    for element_assessment in selected.assessment_result.element_assessments:
        element_analysis = analysis_by_element[element_assessment.element_id]
        propositions = tuple(
            RuntimeAuthorityProposition(
                reference=PropositionReference(
                    issue_analysis_id=selected.issue_analysis_id,
                    element_id=element_assessment.element_id,
                    source_proposition_index=index,
                ),
                text=str(proposition.text),
                status=_enum_value(proposition.status),
                confidence=_enum_value(proposition.confidence),
                evidence_keys=tuple(str(key) for key in proposition.evidence_keys),
                rationale=str(proposition.rationale),
            )
            for index, proposition in enumerate(element_assessment.assessed_propositions)
        )
        elements.append(
            RuntimeAuthorityElement(
                element_id=element_assessment.element_id,
                provisional_status=_enum_value(element_analysis.provisional_status),
                analysis_confidence=_enum_value(element_analysis.analysis_confidence),
                limitations=tuple(str(item) for item in element_analysis.limitations),
                unresolved_matters=tuple(str(item) for item in element_analysis.unresolved_matters),
                evidential_gaps_json=tuple(
                    _canonical_json(item) for item in element_assessment.evidential_gaps
                ),
                propositions=propositions,
            )
        )

    evidence_uses = tuple(
        RuntimeAuthorityEvidenceUse(
            issue_analysis_id=str(binding.use.issue_analysis_id),
            element_id=str(binding.use.element_id),
            evidence_key=str(binding.use.evidence_key),
            payload_json=_canonical_json(binding.use),
        )
        for binding in authority.governed_issue_evidence_map.bindings
        if binding.use.issue_analysis_id == selected.issue_analysis_id
    )

    evidence_assessments: list[RuntimeAuthorityEvidenceAssessment] = []
    for assessment in authority.governed_evidential_analysis.evidence_assessments:
        coordinates = tuple(assessment.use_coordinates)
        if not any(
            coordinate.issue_analysis_id == selected.issue_analysis_id
            for coordinate in coordinates
        ):
            continue
        evidence_assessments.append(
            RuntimeAuthorityEvidenceAssessment(
                evidence_key=str(assessment.evidence_key),
                payload_json=_canonical_json(assessment),
            )
        )

    return RuntimeAnswerAuthorityContext(
        case_id=selected.case_id,
        authority_id=authority.manifest.authority_id,
        activation_id=authority.active_pointer.activation_id,
        issue_analysis_id=selected.issue_analysis_id,
        issue_definition_id=selected.issue_definition_id,
        issue_definition_version=selected.issue_definition_version,
        issue_name=routing.issue_name or selected.issue_definition_id,
        selector_version=routing.selector_version or "",
        inspected_evidence_keys=tuple(inspected_evidence_keys),
        overall_limitations=tuple(str(item) for item in selected.overall_limitations),
        elements=tuple(elements),
        evidence_uses=evidence_uses,
        evidence_assessments=tuple(evidence_assessments),
    )


def _evidence_key_table(
    context: RuntimeAnswerAuthorityContext,
) -> tuple[tuple[str, ...], dict[str, int]]:
    keys: list[str] = []
    indexes: dict[str, int] = {}

    def add(key: str) -> None:
        if key not in indexes:
            indexes[key] = len(keys)
            keys.append(key)

    for element in context.elements:
        for proposition in element.propositions:
            for key in proposition.evidence_keys:
                add(key)
    for key in context.inspected_evidence_keys:
        add(key)
    return tuple(keys), indexes


def _collection_binding(items: tuple[Any, ...]) -> dict[str, Any]:
    payload = _canonical_json(items)
    return {
        "count": len(items),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _compact_prompt_payload(context: RuntimeAnswerAuthorityContext) -> dict[str, Any]:
    evidence_key_table, key_indexes = _evidence_key_table(context)
    semantic_rows: list[dict[str, Any]] = []
    semantic_indexes: dict[tuple[Any, ...], int] = {}
    elements: list[dict[str, Any]] = []

    for element in context.elements:
        coordinate_refs: list[list[int]] = []
        for proposition in element.propositions:
            evidence_key_indexes = tuple(
                key_indexes[key] for key in proposition.evidence_keys
            )
            semantic_key = (
                proposition.text,
                proposition.status,
                proposition.confidence,
                evidence_key_indexes,
                proposition.rationale,
            )
            semantic_index = semantic_indexes.get(semantic_key)
            if semantic_index is None:
                semantic_index = len(semantic_rows)
                semantic_indexes[semantic_key] = semantic_index
                semantic_rows.append(
                    {
                        "text": proposition.text,
                        "status": proposition.status,
                        "confidence": proposition.confidence,
                        "evidence_key_indexes": list(evidence_key_indexes),
                        "rationale": proposition.rationale,
                    }
                )
            coordinate_refs.append(
                [
                    proposition.reference.source_proposition_index,
                    semantic_index,
                ]
            )

        elements.append(
            {
                "element_id": element.element_id,
                "provisional_status": element.provisional_status,
                "analysis_confidence": element.analysis_confidence,
                "limitations": list(element.limitations),
                "unresolved_matters": list(element.unresolved_matters),
                "evidential_gaps_json": list(element.evidential_gaps_json),
                "proposition_coordinate_semantic_refs": coordinate_refs,
            }
        )

    return {
        "projection_schema": "governed-answer-authority/reversible-compact-v1",
        "case_id": context.case_id,
        "authority_id": context.authority_id,
        "activation_id": context.activation_id,
        "issue_analysis_id": context.issue_analysis_id,
        "issue_definition_id": context.issue_definition_id,
        "issue_definition_version": context.issue_definition_version,
        "issue_name": context.issue_name,
        "selector_version": context.selector_version,
        "evidence_key_table": list(evidence_key_table),
        "inspected_evidence_key_indexes": [
            key_indexes[key] for key in context.inspected_evidence_keys
        ],
        "overall_limitations": list(context.overall_limitations),
        "elements": elements,
        "proposition_semantics": semantic_rows,
        "provenance_binding": {
            "evidence_uses": _collection_binding(context.evidence_uses),
            "evidence_assessments": _collection_binding(context.evidence_assessments),
            "rule": (
                "Lossless U9B/U9C provenance remains in runtime context outside "
                "the model prompt and is not answer content."
            ),
        },
    }


def _validate_compact_prompt_payload(
    *,
    context: RuntimeAnswerAuthorityContext,
    payload: dict[str, Any],
) -> None:
    try:
        if payload.get("projection_schema") != "governed-answer-authority/reversible-compact-v1":
            raise ValueError("projection schema mismatch")

        identity_fields = (
            "case_id",
            "authority_id",
            "activation_id",
            "issue_analysis_id",
            "issue_definition_id",
            "issue_definition_version",
            "issue_name",
            "selector_version",
        )
        for field_name in identity_fields:
            if payload.get(field_name) != getattr(context, field_name):
                raise ValueError(f"identity mismatch: {field_name}")

        table = payload["evidence_key_table"]
        if (
            not isinstance(table, list)
            or not all(isinstance(key, str) for key in table)
            or len(table) != len(set(table))
        ):
            raise ValueError("evidence-key table is invalid")

        inspected_indexes = payload["inspected_evidence_key_indexes"]
        reconstructed_inspected = tuple(table[index] for index in inspected_indexes)
        if reconstructed_inspected != context.inspected_evidence_keys:
            raise ValueError("inspected evidence-key reconstruction mismatch")

        if tuple(payload["overall_limitations"]) != context.overall_limitations:
            raise ValueError("overall limitations mismatch")

        encoded_elements = payload["elements"]
        if len(encoded_elements) != len(context.elements):
            raise ValueError("element count mismatch")
        semantic_rows = payload["proposition_semantics"]

        for source_element, encoded_element in zip(
            context.elements, encoded_elements, strict=True
        ):
            for field_name in (
                "element_id",
                "provisional_status",
                "analysis_confidence",
            ):
                if encoded_element[field_name] != getattr(source_element, field_name):
                    raise ValueError(f"element field mismatch: {field_name}")
            for field_name in (
                "limitations",
                "unresolved_matters",
                "evidential_gaps_json",
            ):
                if tuple(encoded_element[field_name]) != getattr(source_element, field_name):
                    raise ValueError(f"element sequence mismatch: {field_name}")

            coordinate_refs = encoded_element["proposition_coordinate_semantic_refs"]
            if len(coordinate_refs) != len(source_element.propositions):
                raise ValueError("proposition coordinate count mismatch")

            for source_proposition, coordinate_ref in zip(
                source_element.propositions, coordinate_refs, strict=True
            ):
                if (
                    source_proposition.reference.issue_analysis_id != context.issue_analysis_id
                    or source_proposition.reference.element_id != source_element.element_id
                ):
                    raise ValueError("proposition reference identity mismatch")
                if (
                    not isinstance(coordinate_ref, list)
                    or len(coordinate_ref) != 2
                    or coordinate_ref[0]
                    != source_proposition.reference.source_proposition_index
                ):
                    raise ValueError("proposition coordinate mismatch")
                semantic_row = semantic_rows[coordinate_ref[1]]
                reconstructed_keys = tuple(
                    table[index] for index in semantic_row["evidence_key_indexes"]
                )
                reconstructed = (
                    semantic_row["text"],
                    semantic_row["status"],
                    semantic_row["confidence"],
                    reconstructed_keys,
                    semantic_row["rationale"],
                )
                expected = (
                    source_proposition.text,
                    source_proposition.status,
                    source_proposition.confidence,
                    source_proposition.evidence_keys,
                    source_proposition.rationale,
                )
                if reconstructed != expected:
                    raise ValueError("proposition semantic reconstruction mismatch")

        provenance = payload["provenance_binding"]
        for field_name, items in (
            ("evidence_uses", context.evidence_uses),
            ("evidence_assessments", context.evidence_assessments),
        ):
            binding = provenance[field_name]
            expected = _collection_binding(items)
            if binding != expected:
                raise ValueError(f"provenance binding mismatch: {field_name}")

        def contains_payload_json_key(value: Any) -> bool:
            if isinstance(value, dict):
                return "payload_json" in value or any(
                    contains_payload_json_key(item) for item in value.values()
                )
            if isinstance(value, list):
                return any(contains_payload_json_key(item) for item in value)
            return False

        if contains_payload_json_key(payload):
            raise ValueError("raw provenance payload key leaked into prompt projection")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise GovernedAnswerAuthorityContextError(
            "Compact frozen analytical prompt projection is not exactly reversible."
        ) from exc


def _context_payload(context: RuntimeAnswerAuthorityContext) -> dict[str, Any]:
    payload = _compact_prompt_payload(context)
    _validate_compact_prompt_payload(context=context, payload=payload)
    return payload


def _answer_prompt_payload(context: RuntimeAnswerAuthorityContext) -> dict[str, Any]:
    """Project only frozen proposition coordinates that can produce valid answer bindings."""

    inspected = set(context.inspected_evidence_keys)
    eligible_keys_by_coordinate: dict[tuple[str, int], tuple[str, ...]] = {}
    used_keys: set[str] = set()

    for element in context.elements:
        for proposition in element.propositions:
            eligible_keys = tuple(
                key for key in proposition.evidence_keys if key in inspected
            )
            if not eligible_keys:
                continue
            coordinate = (
                proposition.reference.element_id,
                proposition.reference.source_proposition_index,
            )
            eligible_keys_by_coordinate[coordinate] = eligible_keys
            used_keys.update(eligible_keys)

    if not eligible_keys_by_coordinate:
        raise GovernedAnswerAuthorityContextError(
            "No answer-eligible frozen propositions are grounded by U8-inspected evidence."
        )

    evidence_key_table = tuple(
        key for key in context.inspected_evidence_keys if key in used_keys
    )
    key_indexes = {key: index for index, key in enumerate(evidence_key_table)}
    semantic_rows: list[dict[str, Any]] = []
    semantic_indexes: dict[tuple[Any, ...], int] = {}
    elements: list[dict[str, Any]] = []

    for element in context.elements:
        coordinate_refs: list[list[int]] = []
        for proposition in element.propositions:
            coordinate = (
                proposition.reference.element_id,
                proposition.reference.source_proposition_index,
            )
            eligible_keys = eligible_keys_by_coordinate.get(coordinate)
            if eligible_keys is None:
                continue

            evidence_key_indexes = tuple(key_indexes[key] for key in eligible_keys)
            semantic_key = (
                proposition.text,
                proposition.status,
                proposition.confidence,
                evidence_key_indexes,
                proposition.rationale,
            )
            semantic_index = semantic_indexes.get(semantic_key)
            if semantic_index is None:
                semantic_index = len(semantic_rows)
                semantic_indexes[semantic_key] = semantic_index
                semantic_rows.append(
                    {
                        "text": proposition.text,
                        "status": proposition.status,
                        "confidence": proposition.confidence,
                        "evidence_key_indexes": list(evidence_key_indexes),
                        "rationale": proposition.rationale,
                    }
                )
            coordinate_refs.append(
                [
                    proposition.reference.source_proposition_index,
                    semantic_index,
                ]
            )

        if coordinate_refs:
            elements.append(
                {
                    "element_id": element.element_id,
                    "provisional_status": element.provisional_status,
                    "analysis_confidence": element.analysis_confidence,
                    "limitations": list(element.limitations),
                    "unresolved_matters": list(element.unresolved_matters),
                    "evidential_gaps_json": list(element.evidential_gaps_json),
                    "proposition_coordinate_semantic_refs": coordinate_refs,
                }
            )

    payload = {
        "projection_schema": "governed-answer-authority/answer-eligible-compact-v1",
        "case_id": context.case_id,
        "authority_id": context.authority_id,
        "activation_id": context.activation_id,
        "issue_analysis_id": context.issue_analysis_id,
        "issue_definition_id": context.issue_definition_id,
        "issue_definition_version": context.issue_definition_version,
        "issue_name": context.issue_name,
        "selector_version": context.selector_version,
        "evidence_key_table": list(evidence_key_table),
        "overall_limitations": list(context.overall_limitations),
        "elements": elements,
        "proposition_semantics": semantic_rows,
        "provenance_binding": {
            "evidence_uses": _collection_binding(context.evidence_uses),
            "evidence_assessments": _collection_binding(context.evidence_assessments),
            "rule": (
                "Lossless U9B/U9C provenance remains in runtime context outside "
                "the model prompt and is not answer content."
            ),
        },
    }
    _validate_answer_prompt_payload(context=context, payload=payload)
    return payload


def _validate_answer_prompt_payload(
    *,
    context: RuntimeAnswerAuthorityContext,
    payload: dict[str, Any],
) -> None:
    """Verify that the model-visible projection contains only answer-eligible coordinates."""

    try:
        if (
            payload.get("projection_schema")
            != "governed-answer-authority/answer-eligible-compact-v1"
        ):
            raise ValueError("answer projection schema mismatch")

        identity_fields = (
            "case_id",
            "authority_id",
            "activation_id",
            "issue_analysis_id",
            "issue_definition_id",
            "issue_definition_version",
            "issue_name",
            "selector_version",
        )
        for field_name in identity_fields:
            if payload.get(field_name) != getattr(context, field_name):
                raise ValueError(f"answer projection identity mismatch: {field_name}")

        inspected = set(context.inspected_evidence_keys)
        expected_eligible: list[
            tuple[RuntimeAuthorityElement, RuntimeAuthorityProposition, tuple[str, ...]]
        ] = []
        used_keys: set[str] = set()
        for element in context.elements:
            for proposition in element.propositions:
                eligible_keys = tuple(
                    key for key in proposition.evidence_keys if key in inspected
                )
                if eligible_keys:
                    expected_eligible.append((element, proposition, eligible_keys))
                    used_keys.update(eligible_keys)

        if not expected_eligible:
            raise ValueError("answer projection has no eligible propositions")

        expected_table = tuple(
            key for key in context.inspected_evidence_keys if key in used_keys
        )
        table = payload["evidence_key_table"]
        if (
            not isinstance(table, list)
            or tuple(table) != expected_table
            or len(table) != len(set(table))
        ):
            raise ValueError("answer evidence-key table mismatch")
        if any(key not in inspected for key in table):
            raise ValueError("uninspected evidence key leaked into answer projection")

        if tuple(payload["overall_limitations"]) != context.overall_limitations:
            raise ValueError("answer projection overall limitations mismatch")

        expected_elements = tuple(
            element
            for element in context.elements
            if any(
                any(key in inspected for key in proposition.evidence_keys)
                for proposition in element.propositions
            )
        )
        encoded_elements = payload["elements"]
        if len(encoded_elements) != len(expected_elements):
            raise ValueError("answer projection element count mismatch")

        semantic_rows = payload["proposition_semantics"]
        used_semantic_indexes: set[int] = set()
        observed_coordinates: list[
            tuple[RuntimeAuthorityElement, RuntimeAuthorityProposition, tuple[str, ...]]
        ] = []

        for source_element, encoded_element in zip(
            expected_elements, encoded_elements, strict=True
        ):
            for field_name in (
                "element_id",
                "provisional_status",
                "analysis_confidence",
            ):
                if encoded_element[field_name] != getattr(source_element, field_name):
                    raise ValueError(
                        f"answer projection element field mismatch: {field_name}"
                    )
            for field_name in (
                "limitations",
                "unresolved_matters",
                "evidential_gaps_json",
            ):
                if tuple(encoded_element[field_name]) != getattr(source_element, field_name):
                    raise ValueError(
                        f"answer projection element sequence mismatch: {field_name}"
                    )

            source_by_index = {
                proposition.reference.source_proposition_index: proposition
                for proposition in source_element.propositions
            }
            for coordinate_ref in encoded_element["proposition_coordinate_semantic_refs"]:
                if not isinstance(coordinate_ref, list) or len(coordinate_ref) != 2:
                    raise ValueError("answer proposition coordinate is invalid")

                source_index, semantic_index = coordinate_ref
                source_proposition = source_by_index.get(source_index)
                if source_proposition is None:
                    raise ValueError("answer proposition coordinate is not frozen")

                eligible_keys = tuple(
                    key for key in source_proposition.evidence_keys if key in inspected
                )
                if not eligible_keys:
                    raise ValueError("ungrounded proposition leaked into answer projection")

                semantic_row = semantic_rows[semantic_index]
                used_semantic_indexes.add(semantic_index)
                reconstructed_keys = tuple(
                    table[index] for index in semantic_row["evidence_key_indexes"]
                )
                if reconstructed_keys != eligible_keys:
                    raise ValueError("answer proposition evidence intersection mismatch")

                reconstructed = (
                    semantic_row["text"],
                    semantic_row["status"],
                    semantic_row["confidence"],
                    semantic_row["rationale"],
                )
                expected = (
                    source_proposition.text,
                    source_proposition.status,
                    source_proposition.confidence,
                    source_proposition.rationale,
                )
                if reconstructed != expected:
                    raise ValueError("answer proposition frozen semantics changed")

                observed_coordinates.append(
                    (source_element, source_proposition, eligible_keys)
                )

        if observed_coordinates != expected_eligible:
            raise ValueError("answer proposition eligibility/order mismatch")
        if used_semantic_indexes != set(range(len(semantic_rows))):
            raise ValueError("unused answer proposition semantic row exists")

        provenance = payload["provenance_binding"]
        for field_name, items in (
            ("evidence_uses", context.evidence_uses),
            ("evidence_assessments", context.evidence_assessments),
        ):
            if provenance[field_name] != _collection_binding(items):
                raise ValueError(
                    f"answer projection provenance binding mismatch: {field_name}"
                )

        def contains_payload_json_key(value: Any) -> bool:
            if isinstance(value, dict):
                return "payload_json" in value or any(
                    contains_payload_json_key(item) for item in value.values()
                )
            if isinstance(value, list):
                return any(contains_payload_json_key(item) for item in value)
            return False

        if contains_payload_json_key(payload):
            raise ValueError("raw provenance payload key leaked into answer projection")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise GovernedAnswerAuthorityContextError(
            "Answer-eligible frozen analytical prompt projection is invalid."
        ) from exc


def build_constrained_governed_answer_prompt(
    *,
    base_prompt: str,
    context: RuntimeAnswerAuthorityContext,
) -> str:
    """Add the frozen analytical restraint and statement-binding contract to U8."""

    payload = json.dumps(
        _answer_prompt_payload(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"""{base_prompt}

GOVERNED ACTIVE ANALYTICAL AUTHORITY — READ-ONLY CONSTRAINT

The following JSON is an answer-eligible compact projection of the already-active
frozen analytical authority for the single controlled issue selected for this question.
It is not a request to reanalyse evidence. The full frozen runtime authority remains
unchanged outside this model-visible projection.

Projection decoding:
- evidence_key_table contains only U8-inspected governed evidence keys that are
  attached to at least one answer-eligible frozen proposition shown below.
- each element's proposition_coordinate_semantic_refs item is
  [source_proposition_index, proposition_semantic_index]; source_proposition_index is
  the original frozen proposition index and is never renumbered.
- only proposition coordinates with at least one attached U8-inspected evidence key
  are present; elements with no such proposition are omitted from this answer projection.
- proposition_semantics stores each eligible exact semantic body once; its
  evidence_key_indexes resolve only to the inspected evidence attached to that
  proposition.
- each proposition_semantics row's "status" value is the exact frozen proposition
  status for every proposition coordinate that references that row.
- provenance_binding authenticates lossless U9B/U9C runtime provenance that is
  deliberately retained outside the model prompt and is not answer content.

{payload}

MANDATORY ANALYTICAL RULES

1. Do not retrieve, remap, reassess, rerender, rebuild or invent analytical state.
2. Do not upgrade a proposition's frozen status or confidence.
3. Do not resolve a dispute, fill an evidential gap, or remove a frozen limitation.
4. U9C observations are provenance/structural observations only. Never convert them
   into credibility, reliability, evidential weight, truthfulness or merits findings.
5. You may rely only on proposition coordinates present above. Every coordinate
   present above is deterministically answer-eligible because it has inspected grounding.
6. You may rely only on evidence keys attached to a referenced frozen proposition
   through that semantic row's evidence_key_indexes. Every evidence key visible in this
   projection is already inside the U8-inspected answer population.
7. You may organise, explain, summarise and conservatively paraphrase the frozen
   analytical state, and connect it to the user's wording. You may not infer a new
   proposition or state a stronger proposition than the frozen sources support.
8. Every substantive answer statement must be returned as one bound statement item.
   No substantive analytical prose may appear outside the bound statement array.
9. If one statement references several propositions, every referenced proposition must
   have at least one cited evidence key in that same statement.

RETURN FORMAT — STRICT JSON ONLY

Return exactly one JSON object with exactly one key, "statements".
"statements" must be a JSON array. Each item must contain exactly:

- "statement_id": non-empty unique string
- "text": non-empty answer statement written for the user
- "source_proposition_refs": non-empty array of objects containing exactly
  "issue_analysis_id", "element_id", "source_proposition_index"; the
  "source_proposition_index" value must be a non-negative integer (0 or greater)
- "evidence_keys": non-empty unique array of governed evidence-key strings
- "source_status": must exactly equal the "status" value of every referenced
  proposition_semantics row; a statement may combine proposition references only
  when all referenced rows have the same "status" value

The text must preserve all frozen qualifications, disputes, limitations and uncertainty
relevant to the referenced propositions. Do not return Markdown fences or any fields
outside this schema.
"""


__all__ = [
    "build_constrained_governed_answer_prompt",
    "build_runtime_authority_context",
]
