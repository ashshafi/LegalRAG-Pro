from dataclasses import FrozenInstanceError

import pytest

from governed_answer_authority.models import (
    AnalyticalAuthorityMode,
    PropositionReference,
    RuntimeAuthorityProposition,
)


def test_modes_cover_exact_runtime_states():
    assert [item.value for item in AnalyticalAuthorityMode] == [
        "absent",
        "unavailable",
        "applied",
        "invalid_authority",
        "invalid_analytical_output",
    ]


def test_runtime_models_are_frozen():
    ref = PropositionReference("analysis", "element", 0)
    proposition = RuntimeAuthorityProposition(
        reference=ref,
        text="Frozen text",
        status="supported_but_not_established",
        confidence="medium",
        evidence_keys=("e1",),
        rationale="Frozen rationale",
    )
    with pytest.raises(FrozenInstanceError):
        proposition.text = "changed"  # type: ignore[misc]
