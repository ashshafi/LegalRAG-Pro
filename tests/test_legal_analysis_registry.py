"""Tests for the versioned legal issue-definition registry."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.definitions import (  # noqa: E402
    INITIAL_ISSUE_DEFINITIONS,
    REASONABLE_ADJUSTMENTS_V1,
)
from legal_analysis.enums import IssueDefinitionStatus  # noqa: E402
from legal_analysis.registry import IssueDefinitionRegistry, build_default_registry  # noqa: E402


def test_default_registry_lists_all_four_definitions() -> None:
    registry = build_default_registry()

    assert [(item.definition_id, item.version) for item in registry.list_definitions()] == [
        ("DA-001", "1.0"),
        ("EK-001", "1.0"),
        ("LIM-001", "1.0"),
        ("RA-001", "1.0"),
    ]


def test_registry_gets_exact_version() -> None:
    registry = build_default_registry()

    definition = registry.get_definition("RA-001", "1.0")

    assert definition is REASONABLE_ADJUSTMENTS_V1


def test_registry_gets_current_active_version_without_silent_substitution() -> None:
    old = replace(
        REASONABLE_ADJUSTMENTS_V1,
        version="0.9",
        status=IssueDefinitionStatus.DEPRECATED,
    )
    registry = IssueDefinitionRegistry((old, REASONABLE_ADJUSTMENTS_V1))

    assert registry.get_definition("RA-001").version == "1.0"
    assert registry.get_definition("RA-001", "0.9").version == "0.9"
    assert registry.versions("RA-001") == ("0.9", "1.0")


def test_registry_rejects_duplicate_id_version_pair() -> None:
    registry = IssueDefinitionRegistry(INITIAL_ISSUE_DEFINITIONS)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(REASONABLE_ADJUSTMENTS_V1)


def test_registry_rejects_second_active_version_for_same_id() -> None:
    registry = IssueDefinitionRegistry((REASONABLE_ADJUSTMENTS_V1,))
    new_active = replace(REASONABLE_ADJUSTMENTS_V1, version="2.0")

    with pytest.raises(ValueError, match="already has an active version"):
        registry.register(new_active)


def test_registry_does_not_fall_back_to_unknown_version() -> None:
    registry = build_default_registry()

    with pytest.raises(KeyError, match="Unknown issue definition"):
        registry.get_definition("RA-001", "9.9")


def test_registry_does_not_substitute_another_issue() -> None:
    registry = build_default_registry()

    with pytest.raises(KeyError, match="No active issue definition"):
        registry.get_definition("XYZ-999")


def test_registry_validation_passes_for_initial_domain_data() -> None:
    registry = build_default_registry()
    registry.validate()
