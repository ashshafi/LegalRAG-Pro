"""Parse and fail-closed validate generated analytical statement bindings."""

from __future__ import annotations

import json
from typing import Any

from .models import (
    AnswerStatementBinding,
    GovernedAnswerBindingError,
    PropositionReference,
    RuntimeAnswerAuthorityContext,
    ValidatedGovernedAnswer,
)


_ROOT_KEYS = {"statements"}
_STATEMENT_KEYS = {
    "statement_id",
    "text",
    "source_proposition_refs",
    "evidence_keys",
    "source_status",
}
_REF_KEYS = {"issue_analysis_id", "element_id", "source_proposition_index"}


def _require_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GovernedAnswerBindingError(f"{label} must be a JSON object.")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise GovernedAnswerBindingError(f"{label} has an unexpected field set.")


def _proposition_index(context: RuntimeAnswerAuthorityContext) -> dict[PropositionReference, Any]:
    index: dict[PropositionReference, Any] = {}
    for element in context.elements:
        for proposition in element.propositions:
            if proposition.reference in index:
                raise GovernedAnswerBindingError("Authority context contains a duplicate proposition coordinate.")
            index[proposition.reference] = proposition
    return index


def _parse_reference(value: Any) -> PropositionReference:
    obj = _require_object(value, label="source_proposition_ref")
    _require_exact_keys(obj, _REF_KEYS, label="source_proposition_ref")
    issue_analysis_id = obj["issue_analysis_id"]
    element_id = obj["element_id"]
    source_index = obj["source_proposition_index"]
    if not isinstance(issue_analysis_id, str) or not issue_analysis_id:
        raise GovernedAnswerBindingError("issue_analysis_id must be a non-empty string.")
    if not isinstance(element_id, str) or not element_id:
        raise GovernedAnswerBindingError("element_id must be a non-empty string.")
    if not isinstance(source_index, int) or isinstance(source_index, bool) or source_index < 0:
        raise GovernedAnswerBindingError("source_proposition_index must be a non-negative integer.")
    return PropositionReference(issue_analysis_id, element_id, source_index)


def validate_answer_statement_bindings(
    *,
    raw_output: str,
    context: RuntimeAnswerAuthorityContext,
) -> ValidatedGovernedAnswer:
    """Validate every generated substantive statement against frozen authority."""

    try:
        data = json.loads(raw_output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise GovernedAnswerBindingError("Analytical output is not strict JSON.") from exc

    root = _require_object(data, label="analytical output")
    _require_exact_keys(root, _ROOT_KEYS, label="analytical output")
    rows = root["statements"]
    if not isinstance(rows, list) or not rows:
        raise GovernedAnswerBindingError("statements must be a non-empty JSON array.")

    propositions = _proposition_index(context)
    inspected = set(context.inspected_evidence_keys)
    statement_ids: set[str] = set()
    bindings: list[AnswerStatementBinding] = []
    rendered: list[str] = []
    relied_order: list[str] = []
    relied_seen: set[str] = set()

    for row in rows:
        obj = _require_object(row, label="statement")
        _require_exact_keys(obj, _STATEMENT_KEYS, label="statement")

        statement_id = obj["statement_id"]
        if not isinstance(statement_id, str) or not statement_id.strip():
            raise GovernedAnswerBindingError("statement_id must be a non-empty string.")
        if statement_id in statement_ids:
            raise GovernedAnswerBindingError("statement_id values must be unique.")
        statement_ids.add(statement_id)

        statement_text = obj["text"]
        if not isinstance(statement_text, str) or not statement_text.strip():
            raise GovernedAnswerBindingError("text must be a non-empty string.")
        statement_text = statement_text.strip()

        refs_raw = obj["source_proposition_refs"]
        if not isinstance(refs_raw, list) or not refs_raw:
            raise GovernedAnswerBindingError("source_proposition_refs must be non-empty.")
        refs = tuple(_parse_reference(item) for item in refs_raw)
        if len(set(refs)) != len(refs):
            raise GovernedAnswerBindingError("source_proposition_refs must be unique.")

        resolved = []
        for ref in refs:
            proposition = propositions.get(ref)
            if proposition is None:
                raise GovernedAnswerBindingError("Unknown frozen proposition coordinate.")
            resolved.append(proposition)

        statuses = {item.status for item in resolved}
        if len(statuses) != 1:
            raise GovernedAnswerBindingError(
                "Referenced propositions must share one frozen proposition status."
            )

        # Retain the existing generated JSON shape for backwards compatibility,
        # but never trust generated semantic metadata that is exactly derivable
        # from the frozen proposition coordinates.
        source_status_raw = obj["source_status"]
        if not isinstance(source_status_raw, str):
            raise GovernedAnswerBindingError("source_status must be a string.")

        evidence_raw = obj["evidence_keys"]
        if (
            not isinstance(evidence_raw, list)
            or not evidence_raw
            or any(not isinstance(item, str) or not item for item in evidence_raw)
        ):
            raise GovernedAnswerBindingError(
                "evidence_keys must be a non-empty string array."
            )
        if len(set(evidence_raw)) != len(evidence_raw):
            raise GovernedAnswerBindingError("evidence_keys must be unique.")

        source_status = next(iter(statuses))

        canonical_evidence_keys: list[str] = []
        canonical_seen: set[str] = set()
        for proposition in resolved:
            for evidence_key in proposition.evidence_keys:
                if evidence_key in inspected and evidence_key not in canonical_seen:
                    canonical_seen.add(evidence_key)
                    canonical_evidence_keys.append(evidence_key)

        evidence_keys = tuple(canonical_evidence_keys)

        bound_key_set = set(evidence_keys)
        proposition_keys = {
            evidence_key
            for proposition in resolved
            for evidence_key in proposition.evidence_keys
        }
        if not bound_key_set.issubset(proposition_keys):
            raise GovernedAnswerBindingError("Binding cites evidence outside its frozen propositions.")
        if not bound_key_set.issubset(inspected):
            raise GovernedAnswerBindingError("Binding cites evidence outside the U8 inspected answer population.")
        for proposition in resolved:
            attached = set(proposition.evidence_keys)
            if not attached.intersection(bound_key_set):
                raise GovernedAnswerBindingError(
                    "Every referenced proposition must be grounded by at least one cited evidence key."
                )

        binding = AnswerStatementBinding(
            statement_id=statement_id,
            statement_text=statement_text,
            source_proposition_refs=refs,
            evidence_keys=evidence_keys,
            source_status=source_status,
        )
        bindings.append(binding)
        rendered.append(f"[{source_status}] {statement_text}")

        for evidence_key in evidence_keys:
            if evidence_key not in relied_seen:
                relied_seen.add(evidence_key)
                relied_order.append(evidence_key)

    answer = "\n\n".join(rendered)
    if context.overall_limitations:
        answer += "\n\nFrozen analytical limitations:\n" + "\n".join(
            f"- {item}" for item in context.overall_limitations
        )

    return ValidatedGovernedAnswer(
        answer=answer,
        bindings=tuple(bindings),
        relied_evidence_keys=tuple(relied_order),
    )


def answer_statement_bindings_payload(
    bindings: tuple[AnswerStatementBinding, ...],
) -> list[dict[str, Any]]:
    """Return deterministic serialisable metadata for validated bindings."""

    return [
        {
            "statement_id": binding.statement_id,
            "text": binding.statement_text,
            "source_proposition_refs": [
                {
                    "issue_analysis_id": ref.issue_analysis_id,
                    "element_id": ref.element_id,
                    "source_proposition_index": ref.source_proposition_index,
                }
                for ref in binding.source_proposition_refs
            ],
            "evidence_keys": list(binding.evidence_keys),
            "source_status": binding.source_status,
        }
        for binding in bindings
    ]


__all__ = [
    "answer_statement_bindings_payload",
    "validate_answer_statement_bindings",
]
