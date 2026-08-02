"""Tests for controlled Sprint 2.3 issue-definition domain data."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.definitions import (  # noqa: E402
    DISCRIMINATION_ARISING_V1,
    EMPLOYER_KNOWLEDGE_V1,
    INITIAL_ISSUE_DEFINITIONS,
    LIMITATION_V1,
    REASONABLE_ADJUSTMENTS_V1,
)
from legal_analysis.enums import IssueDefinitionStatus  # noqa: E402
from legal_analysis.models import IssueDefinition, IssueElementDefinition  # noqa: E402


def test_initial_definitions_have_stable_ids_and_versions() -> None:
    assert [(item.definition_id, item.version) for item in INITIAL_ISSUE_DEFINITIONS] == [
        ("RA-001", "1.0"),
        ("DA-001", "1.0"),
        ("EK-001", "1.0"),
        ("LIM-001", "1.0"),
    ]


def test_reasonable_adjustments_element_order_is_controlled() -> None:
    assert [item.element_id for item in REASONABLE_ADJUSTMENTS_V1.elements] == [
        "RA-DISABILITY",
        "RA-KNOWLEDGE",
        "RA-WORKPLACE-CONTEXT",
        "RA-DISADVANTAGE",
        "RA-ADJUSTMENT",
        "RA-REASONABLENESS",
        "RA-FAILURE",
        "RA-TIMING",
    ]


def test_discrimination_arising_element_order_is_controlled() -> None:
    assert [item.element_id for item in DISCRIMINATION_ARISING_V1.elements] == [
        "DA-DISABILITY",
        "DA-SOMETHING-ARISING",
        "DA-UNFAVOURABLE-TREATMENT",
        "DA-CAUSATION",
        "DA-KNOWLEDGE",
        "DA-JUSTIFICATION",
        "DA-TIMING",
    ]


def test_employer_knowledge_element_order_is_controlled() -> None:
    assert [item.element_id for item in EMPLOYER_KNOWLEDGE_V1.elements] == [
        "EK-INFORMATION",
        "EK-RECIPIENT",
        "EK-DIRECT-KNOWLEDGE",
        "EK-CONSTRUCTIVE-KNOWLEDGE",
        "EK-DISADVANTAGE-KNOWLEDGE",
        "EK-CLAIMANT-ASSERTIONS",
        "EK-RESPONDENT-POSITION",
        "EK-UNRESOLVED",
        "EK-TIMING",
    ]


def test_limitation_element_order_is_controlled() -> None:
    assert [item.element_id for item in LIMITATION_V1.elements] == [
        "LIM-ACTS",
        "LIM-DATES",
        "LIM-SEPARATE-OR-CONSEQUENCE",
        "LIM-CONTINUING-CONDUCT",
        "LIM-END-DATE",
        "LIM-PRESENTATION",
        "LIM-DELAY-EXPLANATION",
        "LIM-RESPONDENT-POSITION",
        "LIM-PREJUDICE-EVIDENCE",
        "LIM-JE-FACTORS",
    ]


def test_every_definition_has_unique_element_ids_and_questions() -> None:
    for definition in INITIAL_ISSUE_DEFINITIONS:
        ids = [element.element_id for element in definition.elements]
        assert len(ids) == len(set(ids))
        assert all(element.question_to_determine.strip() for element in definition.elements)


def test_definition_rejects_duplicate_element_ids() -> None:
    element = IssueElementDefinition(
        element_id="TEST-ELEMENT",
        name="Test",
        question_to_determine="What must be determined?",
    )
    with pytest.raises(ValueError, match="unique"):
        IssueDefinition(
            definition_id="TST-001",
            name="Test issue",
            version="1.0",
            legal_framework=("Test framework",),
            description="A test definition.",
            elements=(element, element),
        )


def test_definition_rejects_invalid_version() -> None:
    with pytest.raises(ValueError, match="numeric version form"):
        replace(REASONABLE_ADJUSTMENTS_V1, version="latest")


def test_definition_rejects_untyped_status() -> None:
    with pytest.raises(ValueError, match="IssueDefinition.status"):
        replace(REASONABLE_ADJUSTMENTS_V1, status="active")  # type: ignore[arg-type]


def test_initial_definitions_are_active() -> None:
    assert all(
        item.status is IssueDefinitionStatus.ACTIVE for item in INITIAL_ISSUE_DEFINITIONS
    )


def test_analysis_can_be_validated_against_exact_definition_version() -> None:
    from uuid import uuid4

    from legal_analysis.models import IssueAnalysis
    from legal_analysis.validation import validate_analysis_against_definition

    analysis = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="Question",
        definition=REASONABLE_ADJUSTMENTS_V1,
    )

    validate_analysis_against_definition(analysis, REASONABLE_ADJUSTMENTS_V1)


def test_analysis_definition_validation_rejects_version_mismatch() -> None:
    from uuid import uuid4

    from legal_analysis.models import IssueAnalysis
    from legal_analysis.validation import validate_analysis_against_definition

    analysis = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="Question",
        definition=REASONABLE_ADJUSTMENTS_V1,
    )
    old_definition = replace(
        REASONABLE_ADJUSTMENTS_V1,
        version="0.9",
        status=IssueDefinitionStatus.DEPRECATED,
    )

    with pytest.raises(ValueError, match="version"):
        validate_analysis_against_definition(analysis, old_definition)


def test_analysis_definition_validation_rejects_silent_question_change() -> None:
    from uuid import uuid4

    from legal_analysis.models import ElementAnalysis, IssueAnalysis
    from legal_analysis.validation import validate_analysis_against_definition

    analysis = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="Question",
        definition=REASONABLE_ADJUSTMENTS_V1,
    )
    changed_first = ElementAnalysis(
        element_id=analysis.elements[0].element_id,
        element_name=analysis.elements[0].element_name,
        question_to_determine="A silently changed legal question?",
    )
    changed = replace(analysis, elements=(changed_first, *analysis.elements[1:]))

    with pytest.raises(ValueError, match="controlled issue definition"):
        validate_analysis_against_definition(changed, REASONABLE_ADJUSTMENTS_V1)
