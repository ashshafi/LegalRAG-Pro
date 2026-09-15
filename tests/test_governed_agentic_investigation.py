from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from new_ai_finding import is_source_comparison_new_ai_finding

from case_management.access import (
    MatterAccessContext,
    MatterMembership,
    MatterMutationError,
    MatterRole,
    MembershipStatus,
    UserIdentity,
)
from governed_agentic_investigation import (
    GovernedAgenticDecision,
    GovernedAgenticInvestigationError,
    append_governed_agentic_investigation_receipt,
    append_governed_agentic_professional_decision,
    build_governed_agentic_investigation_plan,
    combine_governed_agentic_step_results,
    load_governed_agentic_investigation_receipts,
    profile_governed_agentic_step_result,
    build_governed_agentic_performance_profile,
)

CASE = "case-1"
TASK = "task-1"


@dataclass(frozen=True)
class FakeTask:
    case_id: str = CASE
    task_id: str = TASK
    title: str = "Resolve limitation chronology"
    issue_name: str = "Limitation"
    why_it_matters: str = "Establish the best supported chronology and unresolved gaps."
    originating_question: str = "What is the strongest chronology evidence?"


def access_for(role: MatterRole, *, active: bool = True, case_id: str = CASE):
    user = UserIdentity.from_email(f"{role.value}@example.test")
    membership = MatterMembership(
        case_id=case_id,
        user_id=user.user_id,
        role=role,
        status=MembershipStatus.ACTIVE if active else MembershipStatus.REVOKED,
    )
    return MatterAccessContext(user=user, membership=membership)


def governed_result(
    answer: str,
    *,
    authority: str = "sha256:authority",
    activation: str = "sha256:activation",
):
    return {
        "answer": answer,
        "sources": [{"file": "doc.pdf", "page": 1, "evidence_key": "e1"}],
        "relied_evidence_keys": ["e1"],
        "answer_scope_evidence_keys": ["e1"],
        "answer_statement_bindings": [],
        "analytical_authority_id": authority,
        "analytical_activation_id": activation,
        "analytical_authority_mode": "governed",
    }


def test_plan_is_bounded_and_task_bound():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    assert plan.case_id == CASE
    assert plan.task_id == TASK
    assert len(plan.steps) == 3
    assert [step.step_id for step in plan.steps] == [
        "supporting-evidence",
        "contrary-evidence",
        "gaps-next-action",
    ]
    assert all(
        "Do not change the Current Assessment" in step.question
        for step in plan.steps
    )


def test_combined_proposal_is_not_completion_or_approval():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=[
            governed_result("A", activation="a1"),
            governed_result("B", activation="a2"),
            governed_result("C", activation="a3"),
        ],
    )
    assert combined["gac1_proposal"] is True
    assert combined["gac1_step_count"] == 3
    assert "proposed task work only" in combined["answer"].lower()
    assert "does not complete the task" in combined["answer"].lower()
    assert combined["relied_evidence_keys"] == ["e1"]
    assert combined["gac1_analytical_activation_ids"] == ["a1", "a2", "a3"]
    assert "analytical_activation_id" not in combined


def test_authority_drift_fails_closed():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    with pytest.raises(GovernedAgenticInvestigationError):
        combine_governed_agentic_step_results(
            plan=plan,
            step_results=[
                governed_result("A"),
                governed_result("B", authority="sha256:other"),
                governed_result("C"),
            ],
        )


@pytest.mark.parametrize("role", [MatterRole.OWNER, MatterRole.SOLICITOR])
def test_execution_receipt_append_and_load(tmp_path, role):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    receipt = append_governed_agentic_investigation_receipt(
        case_id=CASE,
        access=access_for(role),
        task_id=TASK,
        plan=plan,
        step_results=results,
        proposed_result=combined,
        root=tmp_path,
        task_loader=lambda case_id: (task,),
    )
    loaded = load_governed_agentic_investigation_receipts(
        CASE,
        TASK,
        root=tmp_path,
    )
    assert [item.receipt_id for item in loaded] == [receipt.receipt_id]
    assert loaded[0].proposed_work_result == combined["answer"]


@pytest.mark.parametrize("role", [MatterRole.REVIEWER, MatterRole.READ_ONLY])
def test_receipt_denies_non_mutation_roles(tmp_path, role):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(MatterMutationError):
        append_governed_agentic_investigation_receipt(
            case_id=CASE,
            access=access_for(role),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (task,),
        )


def test_revoked_owner_is_denied(tmp_path):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(MatterMutationError):
        append_governed_agentic_investigation_receipt(
            case_id=CASE,
            access=access_for(MatterRole.OWNER, active=False),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (task,),
        )


def test_cross_matter_access_fails_closed(tmp_path):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(GovernedAgenticInvestigationError):
        append_governed_agentic_investigation_receipt(
            case_id=CASE,
            access=access_for(MatterRole.OWNER, case_id="other-case"),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (task,),
        )


def test_missing_task_fails_closed(tmp_path):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(GovernedAgenticInvestigationError):
        append_governed_agentic_investigation_receipt(
            case_id=CASE,
            access=access_for(MatterRole.OWNER),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (),
        )


def test_accept_reject_decisions_reference_receipt_and_are_idempotent(tmp_path):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [governed_result("A"), governed_result("B"), governed_result("C")]
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=results,
    )
    access = access_for(MatterRole.OWNER)
    receipt = append_governed_agentic_investigation_receipt(
        case_id=CASE,
        access=access,
        task_id=TASK,
        plan=plan,
        step_results=results,
        proposed_result=combined,
        root=tmp_path,
        task_loader=lambda case_id: (task,),
    )

    accepted = append_governed_agentic_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecision.ACCEPTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )
    accepted_again = append_governed_agentic_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecision.ACCEPTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )
    rejected = append_governed_agentic_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecision.REJECTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )
    assert accepted.decision is GovernedAgenticDecision.ACCEPTED
    assert accepted_again.decision_id == accepted.decision_id
    assert rejected.decision is GovernedAgenticDecision.REJECTED

    lines = (
        tmp_path / CASE / "decisions.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_decision_requires_real_receipt(tmp_path):
    with pytest.raises(GovernedAgenticInvestigationError):
        append_governed_agentic_professional_decision(
            case_id=CASE,
            access=access_for(MatterRole.OWNER),
            task_id=TASK,
            receipt_id="sha256:missing",
            decision=GovernedAgenticDecision.ACCEPTED,
            reviewer_reference="owner@example.test",
            root=tmp_path,
        )



def test_compact_summaries_are_bounded_and_present():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    long_answer = "Evidence sentence. " * 80
    combined = combine_governed_agentic_step_results(
        plan=plan,
        step_results=[
            governed_result(long_answer),
            governed_result("Contrary evidence."),
            governed_result("Remaining gap."),
        ],
    )
    summaries = combined["gac1_step_summaries"]
    assert len(summaries) == 3
    assert summaries[0]["title"] == plan.steps[0].title
    assert len(summaries[0]["summary"]) <= 420
    assert summaries[0]["summary"].endswith("…")


def test_execution_receipt_preserves_optional_elapsed_seconds(tmp_path):
    task = FakeTask()
    plan = build_governed_agentic_investigation_plan(task)
    results = [
        {**governed_result("A"), "gac1_elapsed_seconds": 1.25},
        {**governed_result("B"), "gac1_elapsed_seconds": 2.5},
        {**governed_result("C"), "gac1_elapsed_seconds": 3.75},
    ]
    combined = combine_governed_agentic_step_results(plan=plan, step_results=results)
    receipt = append_governed_agentic_investigation_receipt(
        case_id=CASE,
        access=access_for(MatterRole.OWNER),
        task_id=TASK,
        plan=plan,
        step_results=results,
        proposed_result=combined,
        root=tmp_path,
        task_loader=lambda case_id: (task,),
    )
    assert [row["elapsed_seconds"] for row in receipt.step_records] == [1.25, 2.5, 3.75]



def test_performance_profile_exposes_reference_expansion_and_zero_relied_keys():
    result = governed_result("Detailed answer")
    result["sources"] = [
        {"file": "doc.pdf", "page": 1, "evidence_key": f"e{i}"}
        for i in range(250)
    ]
    result["relied_evidence_keys"] = []
    result["answer_scope_evidence_keys"] = [f"e{i}" for i in range(5)]
    result["retrieval_mode"] = "exhaustive_evidence"
    result["evidence_search_receipt"] = {
        "search_mode": "exhaustive_evidence",
        "documents_inspected": 60,
        "pages_inspected": 900,
        "chunks_inspected": 3060,
        "case_corpus_complete": True,
    }
    profile = profile_governed_agentic_step_result(
        step_id="contrary-evidence",
        title="Contrary evidence",
        elapsed_seconds=95.0,
        result=result,
    )
    assert profile["deduped_source_count"] == 250
    assert profile["unique_file_page_count"] == 1
    assert profile["file_page_expansion_ratio"] == 250.0
    assert profile["relied_evidence_key_count"] == 0
    assert "LARGE_SOURCE_ENVELOPE_GE_200" in profile["flags"]
    assert "LARGE_SOURCE_ENVELOPE_WITH_ZERO_RELIED_KEYS" in profile["flags"]
    assert "SOURCE_REFERENCE_EXPANSION_GE_5X" in profile["flags"]


def test_aggregate_performance_profile_detects_latency_outlier_and_overhead():
    steps = [
        {"step_id": "s1", "title": "S1", "elapsed_seconds": 30.0, "flags": []},
        {"step_id": "s2", "title": "S2", "elapsed_seconds": 95.0, "flags": ["LARGE_SOURCE_ENVELOPE_GE_200"]},
        {"step_id": "s3", "title": "S3", "elapsed_seconds": 31.0, "flags": []},
    ]
    profile = build_governed_agentic_performance_profile(
        step_profiles=steps,
        phase_seconds={
            "plan_build": 0.1,
            "step_calls_and_validation": 156.0,
            "combine": 0.2,
            "matter_access": 0.1,
            "receipt_append": 0.1,
            "session_prepare": 0.1,
            "server_pre_rerun_total": 197.0,
        },
    )
    assert profile["slowest_step_id"] == "s2"
    assert "STEP_LATENCY_OUTLIER_GE_1_75X_MEDIAN" in profile["flags"]
    assert "LARGE_SOURCE_ENVELOPE_GE_200" in profile["flags"]
    assert profile["phase_seconds"]["unaccounted_server_seconds"] > 40
    assert "UNACCOUNTED_SERVER_OVERHEAD_GE_5S" in profile["flags"]


# ---------------------------------------------------------------------------
# GAC1-R10-R2: Step 2 routing/performance repair
# Corrects the R10-R1 TEST HARNESS only; product mutation remains Step 2 only.
# ---------------------------------------------------------------------------

def test_gac1_r10_r2_step2_is_adverse_scan_not_explicit_source_comparison_route():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    step = next(item for item in plan.steps if item.step_id == "contrary-evidence")

    # This deliberately supplies the deterministic state that would be sufficient
    # for the narrow New-AI-Finding source-comparison route IF the question carried
    # a source-comparison cue. The GAC1 Step 2 adverse scan must still route False.
    resolved_explicit_state = SimpleNamespace(
        search_result=SimpleNamespace(),
        semantic_results={"ids": [["e1"]]},
    )
    assert not is_source_comparison_new_ai_finding(
        question=step.question,
        evidence=resolved_explicit_state,
    )


def test_gac1_r10_r2_step2_avoids_every_existing_source_comparison_cue():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    step = next(item for item in plan.steps if item.step_id == "contrary-evidence")
    text = f" {step.question.casefold()} "

    # Exact existing production cue family from src/new_ai_finding.py.
    cues = (
        "compare",
        "contradiction",
        "contradict",
        "inconsistent",
        "inconsistency",
        "conflict",
        "versus",
        " vs ",
        "against",
        "reconcile",
    )
    assert all(cue not in text for cue in cues)
    assert "adverse or qualifying evidence" in step.question
    assert "materially weakens, limits, or creates risk" in step.question


def test_gac1_r10_r2_step1_and_step3_wording_remain_r9_exact():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    by_id = {step.step_id: step for step in plan.steps}

    # R10-R1 accidentally asserted a literal backslash-n sequence ("\\n")
    # instead of actual newlines. R10-R2 binds the real R9 suffixes.
    exact_step1_suffix = (
        "\n\nStep 1: Identify and assess the strongest contemporaneous evidence "
        "that supports resolving this approved task. Distinguish evidence from inference "
        "and identify any material limitations."
    )
    exact_step3_suffix = (
        "\n\nStep 3: Taking the task and governed evidence together, identify what "
        "remains unresolved, what additional evidence (if any) is genuinely required, "
        "and the next professional action. Do not state that the task is complete."
    )
    assert by_id["supporting-evidence"].question.endswith(exact_step1_suffix)
    assert by_id["gaps-next-action"].question.endswith(exact_step3_suffix)


def test_gac1_r10_r2_plan_shape_and_titles_remain_r9_exact():
    plan = build_governed_agentic_investigation_plan(FakeTask())
    assert [(step.step_id, step.title) for step in plan.steps] == [
        ("supporting-evidence", "Evidence supporting the task proposition"),
        ("contrary-evidence", "Contrary or qualifying evidence"),
        ("gaps-next-action", "Remaining gaps and recommended professional next action"),
    ]
