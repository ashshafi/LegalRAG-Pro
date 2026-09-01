from __future__ import annotations

import pytest

from features.timeline import extract_timeline_events, sort_events
import ui.matter_analysis_ledger as ledger_ui


def _results(text: str, *, file: str = "evidence.pdf", page=1):
    return {
        "documents": [[text]],
        "metadatas": [[{"file": file, "page": page}]],
    }


def test_legacy_timeline_rejects_arbitrary_four_digit_tokens_and_legal_years():
    text = (
        "Times 0930 and 1730. Reference 1828. Born 1961. "
        "ERA 1996 and EqA 2010. Case number 2207441/2025."
    )
    assert extract_timeline_events(_results(text)) == []


def test_legacy_timeline_rejects_fake_alphabetic_month_token():
    assert extract_timeline_events(_results("20 EqA 2010")) == []


def test_legacy_timeline_accepts_valid_exact_dates_and_contextual_years():
    events = extract_timeline_events(
        _results(
            "On 17 July 2026 the letter was sent. "
            "During 2005 a return-to-work process occurred."
        )
    )
    assert {event["date"] for event in events} == {"17 July 2026", "2005"}


def test_legacy_timeline_rejects_invalid_calendar_date():
    assert extract_timeline_events(_results("31/02/2025 impossible date")) == []


def test_legacy_timeline_deduplicates_same_date_file_and_page():
    events = extract_timeline_events(
        _results("17 July 2026. The date 17/07/2026 appears again.")
    )
    assert len(events) == 1


def test_legacy_timeline_sorting_is_chronological():
    events = [
        {"date": "24 July 2026", "file": "b", "page": 2, "event": "later"},
        {"date": "2005", "file": "a", "page": 1, "event": "earlier"},
    ]
    assert [event["date"] for event in sort_events(events)] == ["2005", "24 July 2026"]


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}

    def selectbox(self, label, options, *, format_func=None, key=None):
        value = self.session_state[key]
        assert value in options
        return value


def test_stable_selectbox_uses_semantic_state_key_as_widget_value(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)

    selected = ledger_ui._stable_selectbox(
        label="Issue to review",
        options=("issue-a", "issue-b"),
        default_value="issue-a",
        format_func=str,
        state_key="issue-state",
    )

    assert selected == "issue-a"
    assert fake.session_state["issue-state"] == "issue-a"


def test_issue_selection_survives_dependent_focus_rerun(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)

    assert ledger_ui._stable_selectbox(
        label="Issue to review",
        options=("issue-a", "issue-b"),
        default_value="issue-a",
        format_func=str,
        state_key="issue-state",
    ) == "issue-a"

    fake.session_state["issue-state"] = "issue-b"

    assert ledger_ui._stable_selectbox(
        label="Issue to review",
        options=("issue-a", "issue-b"),
        default_value="issue-a",
        format_func=str,
        state_key="issue-state",
    ) == "issue-b"

    assert ledger_ui._stable_selectbox(
        label="Focus area",
        options=("focus-1", "focus-2"),
        default_value="focus-1",
        format_func=str,
        state_key="focus-state-issue-b",
    ) == "focus-1"

    fake.session_state["focus-state-issue-b"] = "focus-2"

    assert ledger_ui._stable_selectbox(
        label="Focus area",
        options=("focus-1", "focus-2"),
        default_value="focus-1",
        format_func=str,
        state_key="focus-state-issue-b",
    ) == "focus-2"

    assert ledger_ui._stable_selectbox(
        label="Issue to review",
        options=("issue-a", "issue-b"),
        default_value="issue-a",
        format_func=str,
        state_key="issue-state",
    ) == "issue-b"


def test_focus_state_is_independent_per_issue(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)

    fake.session_state["focus-state-issue-a"] = "a2"
    fake.session_state["focus-state-issue-b"] = "b1"

    assert ledger_ui._stable_selectbox(
        label="Focus area",
        options=("a1", "a2"),
        default_value="a1",
        format_func=str,
        state_key="focus-state-issue-a",
    ) == "a2"

    assert ledger_ui._stable_selectbox(
        label="Focus area",
        options=("b1", "b2"),
        default_value="b1",
        format_func=str,
        state_key="focus-state-issue-b",
    ) == "b1"


def test_stable_selectbox_repairs_stale_semantic_value(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)
    fake.session_state["issue-state"] = "removed-issue"

    selected = ledger_ui._stable_selectbox(
        label="Issue to review",
        options=("issue-a", "issue-b"),
        default_value="issue-b",
        format_func=str,
        state_key="issue-state",
    )

    assert selected == "issue-b"
    assert fake.session_state["issue-state"] == "issue-b"


def test_stable_selectbox_rejects_invalid_default(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)

    with pytest.raises(ValueError, match="default_value"):
        ledger_ui._stable_selectbox(
            label="Focus area",
            options=("a", "b"),
            default_value="missing",
            format_func=str,
            state_key="focus-state",
        )
