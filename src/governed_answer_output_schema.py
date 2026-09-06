"""Strict Structured Output schema for governed analytical answers."""

from __future__ import annotations

import json

from typing import Any


def canonicalize_exact_duplicate_source_proposition_refs(
    raw_output: str,
) -> tuple[str, int]:
    """Remove only exact duplicate governed proposition coordinates.

    Structured Outputs constrains every reference item to an eligible frozen
    coordinate, but the supported schema subset cannot express array-item
    uniqueness. This transport canonicalizer therefore removes repeated copies
    of the *same* coordinate, preserving first-occurrence order and every other
    generated field. Malformed/unexpected output is returned unchanged so the
    existing fail-closed validator remains authoritative.
    """
    try:
        data = json.loads(raw_output)
    except (TypeError, json.JSONDecodeError):
        return raw_output, 0

    if not isinstance(data, dict):
        return raw_output, 0

    rows = data.get("statements")
    if not isinstance(rows, list):
        return raw_output, 0

    removed = 0
    changed = False
    normalized_rows: list[Any] = []

    for row in rows:
        if not isinstance(row, dict):
            return raw_output, 0

        refs = row.get("source_proposition_refs")
        if not isinstance(refs, list):
            return raw_output, 0

        seen: set[tuple[str, str, int]] = set()
        normalized_refs: list[Any] = []

        for ref in refs:
            if not isinstance(ref, dict):
                return raw_output, 0
            if set(ref) != {
                "issue_analysis_id",
                "element_id",
                "source_proposition_index",
            }:
                return raw_output, 0

            issue_analysis_id = ref.get("issue_analysis_id")
            element_id = ref.get("element_id")
            source_index = ref.get("source_proposition_index")

            if (
                not isinstance(issue_analysis_id, str)
                or not issue_analysis_id
                or not isinstance(element_id, str)
                or not element_id
                or not isinstance(source_index, int)
                or isinstance(source_index, bool)
                or source_index < 0
            ):
                return raw_output, 0

            coordinate = (issue_analysis_id, element_id, source_index)
            if coordinate in seen:
                removed += 1
                changed = True
                continue

            seen.add(coordinate)
            normalized_refs.append(ref)

        if len(normalized_refs) == len(refs):
            normalized_rows.append(row)
            continue

        normalized_row = dict(row)
        normalized_row["source_proposition_refs"] = normalized_refs
        normalized_rows.append(normalized_row)

    if not changed:
        return raw_output, 0

    normalized = dict(data)
    normalized["statements"] = normalized_rows
    return (
        json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        removed,
    )


def build_governed_answer_output_schema(context: Any) -> dict[str, Any]:
    inspected = set(context.inspected_evidence_keys)

    grouped: dict[str, dict[tuple[str, str], list[int]]] = {}
    for element in context.elements:
        for proposition in element.propositions:
            if not any(key in inspected for key in proposition.evidence_keys):
                continue
            ref = proposition.reference
            status_groups = grouped.setdefault(proposition.status, {})
            key = (ref.issue_analysis_id, ref.element_id)
            status_groups.setdefault(key, []).append(ref.source_proposition_index)

    if not grouped:
        raise ValueError(
            "No answer-eligible governed proposition coordinates are available for Structured Output."
        )

    statement_branches: list[dict[str, Any]] = []

    for status in sorted(grouped):
        ref_branches: list[dict[str, Any]] = []
        for (issue_analysis_id, element_id), indexes in sorted(grouped[status].items()):
            ref_branches.append(
                {
                    "type": "object",
                    "properties": {
                        "issue_analysis_id": {
                            "type": "string",
                            "enum": [issue_analysis_id],
                        },
                        "element_id": {
                            "type": "string",
                            "enum": [element_id],
                        },
                        "source_proposition_index": {
                            "type": "integer",
                            "enum": sorted(set(indexes)),
                        },
                    },
                    "required": [
                        "issue_analysis_id",
                        "element_id",
                        "source_proposition_index",
                    ],
                    "additionalProperties": False,
                }
            )

        statement_branches.append(
            {
                "type": "object",
                "properties": {
                    "statement_id": {"type": "string"},
                    "text": {"type": "string"},
                    "source_proposition_refs": {
                        "type": "array",
                        "items": {"anyOf": ref_branches},
                    },
                    "evidence_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_status": {
                        "type": "string",
                        "enum": [status],
                    },
                },
                "required": [
                    "statement_id",
                    "text",
                    "source_proposition_refs",
                    "evidence_keys",
                    "source_status",
                ],
                "additionalProperties": False,
            }
        )

    return {
        "type": "object",
        "properties": {
            "statements": {
                "type": "array",
                "items": {"anyOf": statement_branches},
            }
        },
        "required": ["statements"],
        "additionalProperties": False,
    }
