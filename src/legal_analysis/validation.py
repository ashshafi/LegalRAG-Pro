"""Validation helpers for Sprint 2.3 structured analysis domain data."""

from __future__ import annotations

from .models import IssueAnalysis, IssueDefinition


def validate_issue_definition(definition: IssueDefinition) -> None:
    """Validate a controlled issue definition.

    Dataclass construction performs field-level validation. This function is an
    explicit service boundary for registry/loading code and checks relationships
    that must remain stable across the definition as a whole.
    """

    if len({element.element_id for element in definition.elements}) != len(
        definition.elements
    ):
        raise ValueError("IssueDefinition contains duplicate element IDs.")
    for element in definition.elements:
        if not element.question_to_determine.strip():
            raise ValueError(
                f"IssueDefinition element {element.element_id!r} lacks a question to determine."
            )


def validate_issue_analysis(analysis: IssueAnalysis) -> None:
    """Validate cross-record invariants for an IssueAnalysis."""

    if len({element.element_id for element in analysis.elements}) != len(
        analysis.elements
    ):
        raise ValueError("IssueAnalysis contains duplicate element IDs.")
    for element in analysis.elements:
        for gap in element.evidential_gaps:
            if gap.related_element_id != element.element_id:
                raise ValueError(
                    f"Gap {gap.gap_id} references {gap.related_element_id!r} but is stored under {element.element_id!r}."
                )


def validate_analysis_against_definition(
    analysis: IssueAnalysis,
    definition: IssueDefinition,
) -> None:
    """Validate that an analysis record uses the exact controlled definition it names."""

    validate_issue_analysis(analysis)
    validate_issue_definition(definition)
    if analysis.issue_definition_id != definition.definition_id:
        raise ValueError("IssueAnalysis definition ID does not match the supplied definition.")
    if analysis.issue_definition_version != definition.version:
        raise ValueError("IssueAnalysis definition version does not match the supplied definition.")
    if analysis.issue_name != definition.name:
        raise ValueError("IssueAnalysis issue name does not match the controlled definition.")
    if analysis.legal_framework != definition.legal_framework:
        raise ValueError("IssueAnalysis legal framework does not match the controlled definition.")
    analysis_elements = tuple(
        (element.element_id, element.element_name, element.question_to_determine)
        for element in analysis.elements
    )
    definition_elements = tuple(
        (element.element_id, element.name, element.question_to_determine)
        for element in definition.elements
    )
    if analysis_elements != definition_elements:
        raise ValueError(
            "IssueAnalysis elements/order do not match the controlled issue definition."
        )
