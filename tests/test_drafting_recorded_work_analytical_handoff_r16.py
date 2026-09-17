from types import SimpleNamespace

from drafting_working_draft_generation import _recorded_work_generation_question


def test_recorded_work_is_included_verbatim_as_analytical_guidance():
    answer = "Principal Application Architect posted before 19 August 2026. Suitability remains unresolved."
    question = _recorded_work_generation_question(
        base_question="Draft Potential adjustment.",
        progress=SimpleNamespace(answer=answer),
    )
    assert answer in question
    assert "analytical guidance, not as evidence" in question
    assert "permitted immutable evidence" in question


def test_recorded_work_prompt_prioritises_timing_qualifications_and_contemporary_evidence():
    question = _recorded_work_generation_question(
        base_question="Draft.",
        progress=SimpleNamespace(answer="Recorded work."),
    )
    assert "task-specific contemporaneous evidence" in question
    assert "before, at and after" in question
    assert "actual availability, suitability, feasibility or acceptance" in question
    assert "older historical material as secondary context" in question
    assert "unresolved evidential gaps" in question
