from types import SimpleNamespace

from governed_answer_authority.models import AnalyticalAuthorityMode
from governed_answer_authority.routing import route_question_to_active_authority


CASE_ID = "11111111-1111-4111-8111-111111111111"


class Selector:
    def __init__(self, selection):
        self.selection = selection
        self.calls = []

    def select(self, question, *, case_id=None):
        self.calls.append((question, case_id))
        return self.selection


def selected(issue_id="RA-001", version="1.0", *, ambiguities=()):
    primary = SimpleNamespace(
        issue_definition_id=issue_id,
        issue_definition_version=version,
        issue_name="Reasonable adjustments",
    )
    return SimpleNamespace(
        primary_issue=primary,
        ambiguities=ambiguities,
        selector_version="selector/1.0",
    )


def authority(*results):
    return SimpleNamespace(
        structured_legal_analysis_results=results,
        manifest=SimpleNamespace(
            source_analysis_ids=tuple(result.issue_analysis_id for result in results)
        ),
    )


def result(issue_id="RA-001", version="1.0", analysis_id="a1"):
    return SimpleNamespace(
        case_id=CASE_ID,
        issue_definition_id=issue_id,
        issue_definition_version=version,
        issue_analysis_id=analysis_id,
    )


def test_exact_one_match_is_applied_and_selector_is_routing_only():
    selector = Selector(selected())
    routed = route_question_to_active_authority(
        question="Should adjustments have been made?",
        case_id=CASE_ID,
        authority=authority(result()),
        selector=selector,
    )
    assert routed.mode is AnalyticalAuthorityMode.APPLIED
    assert routed.issue_analysis_id == "a1"
    assert selector.calls == [("Should adjustments have been made?", CASE_ID)]


def test_zero_match_is_unavailable():
    routed = route_question_to_active_authority(
        question="Question",
        case_id=CASE_ID,
        authority=authority(result("EK-001")),
        selector=Selector(selected()),
    )
    assert routed.mode is AnalyticalAuthorityMode.UNAVAILABLE


def test_multiple_compatible_matches_are_unavailable_not_heuristically_chosen():
    routed = route_question_to_active_authority(
        question="Question",
        case_id=CASE_ID,
        authority=authority(result(analysis_id="a1"), result(analysis_id="a2")),
        selector=Selector(selected()),
    )
    assert routed.mode is AnalyticalAuthorityMode.UNAVAILABLE


def test_selector_ambiguity_is_unavailable():
    routed = route_question_to_active_authority(
        question="Broad question",
        case_id=CASE_ID,
        authority=authority(result()),
        selector=Selector(selected(ambiguities=(SimpleNamespace(),))),
    )
    assert routed.mode is AnalyticalAuthorityMode.UNAVAILABLE
