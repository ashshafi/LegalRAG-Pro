from __future__ import annotations

from types import SimpleNamespace

import pytest

from controlled_agentic_analysis_gaps import CAA2Error, _scope_gap_candidates


def candidate(candidate_id: str, issue: str, element: str):
    return SimpleNamespace(
        candidate_id=candidate_id,
        issue_analysis_id=issue,
        element_id=element,
    )


def test_no_candidate_scope_preserves_complete_projection_exactly():
    values = (
        candidate("c1", "i1", "e1"),
        candidate("c2", "i2", "e2"),
    )
    assert _scope_gap_candidates(values, candidate_scope=None) is values


def test_candidate_scope_selects_exact_issue_element_subset_in_original_order():
    first = candidate("c1", "i1", "e1")
    second = candidate("c2", "i1", "e2")
    third = candidate("c3", "i1", "e1")
    fourth = candidate("c4", "i2", "e1")
    values = (first, second, third, fourth)

    scoped = _scope_gap_candidates(
        values,
        candidate_scope=("i1", "e1"),
    )

    assert scoped == (first, third)
    assert scoped[0] is first
    assert scoped[1] is third


@pytest.mark.parametrize(
    "scope",
    (
        (),
        ("i1",),
        ("i1", "e1", "extra"),
        ["i1", "e1"],
        ("", "e1"),
        ("i1", ""),
        (" ", "e1"),
        ("i1", " "),
        (1, "e1"),
        ("i1", 2),
    ),
)
def test_invalid_candidate_scope_fails_closed(scope):
    values = (candidate("c1", "i1", "e1"),)
    with pytest.raises(CAA2Error, match="candidate_scope"):
        _scope_gap_candidates(values, candidate_scope=scope)


def test_candidate_scope_that_matches_no_deterministic_candidate_fails_closed():
    values = (
        candidate("c1", "i1", "e1"),
        candidate("c2", "i2", "e2"),
    )
    with pytest.raises(CAA2Error, match="does not resolve"):
        _scope_gap_candidates(
            values,
            candidate_scope=("missing-issue", "missing-element"),
        )
