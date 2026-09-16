from __future__ import annotations

from dataclasses import dataclass

import pytest

from case_management.access import (
    MatterAccessContext,
    MatterMembership,
    MatterMutationError,
    MatterRole,
    MembershipStatus,
    UserIdentity,
)
from governed_agentic_investigation_v2 import (
    GovernedAgenticDecisionV2,
    GovernedAgenticInvestigationV2Error,
    append_governed_agentic_investigation_v2_professional_decision,
    append_governed_agentic_investigation_v2_receipt,
    build_governed_agentic_investigation_v2_plan,
    combine_governed_agentic_investigation_v2_results,
    load_governed_agentic_investigation_v2_receipts,
)

CASE = "case-1"
TASK = "task-1"


@dataclass(frozen=True)
class FakeTask:
    case_id: str = CASE
    task_id: str = TASK
    title: str = "Investigate the pleaded factual basis"
    issue_name: str = "Knowledge and return to work"
    why_it_matters: str = "Test the pleaded account against contemporaneous records."
    originating_question: str = "What did the employer know and when?"


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


def _plan():
    return build_governed_agentic_investigation_v2_plan(
        FakeTask(),
        objective="Compare the pleaded account with the contemporaneous 2005 records.",
    )


def _results():
    return [
        governed_result("Frame."),
        governed_result("Support."),
        governed_result("Adverse."),
        governed_result("Contradictions."),
        governed_result("Gaps."),
    ]


def test_v2_plan_is_explicit_bounded_and_task_bound():
    plan = _plan()
    assert plan.case_id == CASE
    assert plan.task_id == TASK
    assert len(plan.steps) == 5
    assert [step.step_id for step in plan.steps] == [
        "frame-propositions-and-chronology",
        "supporting-evidence",
        "adverse-qualifying-evidence",
        "contradictions-connections",
        "gaps-professional-actions",
    ]
    assert all("Current Assessment" in step.question for step in plan.steps)
    assert all("Professional investigation objective" in step.question for step in plan.steps)


def test_v2_plan_identity_is_deterministic_and_objective_sensitive():
    first = _plan()
    second = _plan()
    other = build_governed_agentic_investigation_v2_plan(
        FakeTask(),
        objective="Investigate the provenance of the alleged no-contact request.",
    )
    assert first.plan_id == second.plan_id
    assert first.plan_id != other.plan_id


def test_v2_objective_is_required_and_bounded():
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        build_governed_agentic_investigation_v2_plan(FakeTask(), objective="")
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        build_governed_agentic_investigation_v2_plan(
            FakeTask(), objective="x" * 2001
        )


def test_v2_combination_is_proposal_only_and_aggregates_governed_metadata():
    plan = _plan()
    results = _results()
    results[0]["gac2_elapsed_seconds"] = 1.25
    results[1]["analytical_activation_id"] = "sha256:activation-2"
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    assert combined["gac2_proposal"] is True
    assert combined["gac2_step_count"] == 5
    assert combined["gac2_objective"] == plan.objective
    assert "proposed task work only" in combined["answer"].lower()
    assert "does not complete the task" in combined["answer"].lower()
    assert combined["relied_evidence_keys"] == ["e1"]
    assert combined["gac2_step_summaries"][0]["elapsed_seconds"] == 1.25
    assert len(combined["gac2_analytical_activation_ids"]) == 2
    assert "analytical_activation_id" not in combined


def test_v2_authority_drift_fails_closed():
    plan = _plan()
    results = _results()
    results[2]["analytical_authority_id"] = "sha256:other"
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        combine_governed_agentic_investigation_v2_results(
            plan=plan,
            step_results=results,
        )


@pytest.mark.parametrize("role", [MatterRole.OWNER, MatterRole.SOLICITOR])
def test_v2_execution_receipt_append_and_load(tmp_path, role):
    task = FakeTask()
    plan = _plan()
    results = _results()
    results[0]["gac2_elapsed_seconds"] = 1.5
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    receipt = append_governed_agentic_investigation_v2_receipt(
        case_id=CASE,
        access=access_for(role),
        task_id=TASK,
        plan=plan,
        step_results=results,
        proposed_result=combined,
        root=tmp_path,
        task_loader=lambda case_id: (task,),
    )
    loaded = load_governed_agentic_investigation_v2_receipts(
        CASE, TASK, root=tmp_path
    )
    assert [item.receipt_id for item in loaded] == [receipt.receipt_id]
    assert loaded[0].objective == plan.objective
    assert loaded[0].step_records[0]["elapsed_seconds"] == 1.5


@pytest.mark.parametrize("role", [MatterRole.REVIEWER, MatterRole.READ_ONLY])
def test_v2_receipt_denies_non_mutation_roles(tmp_path, role):
    plan = _plan()
    results = _results()
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(MatterMutationError):
        append_governed_agentic_investigation_v2_receipt(
            case_id=CASE,
            access=access_for(role),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (FakeTask(),),
        )


def test_v2_cross_matter_access_fails_closed(tmp_path):
    plan = _plan()
    results = _results()
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        append_governed_agentic_investigation_v2_receipt(
            case_id=CASE,
            access=access_for(MatterRole.OWNER, case_id="other-case"),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (FakeTask(),),
        )


def test_v2_missing_task_fails_closed(tmp_path):
    plan = _plan()
    results = _results()
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        append_governed_agentic_investigation_v2_receipt(
            case_id=CASE,
            access=access_for(MatterRole.OWNER),
            task_id=TASK,
            plan=plan,
            step_results=results,
            proposed_result=combined,
            root=tmp_path,
            task_loader=lambda case_id: (),
        )


def test_v2_accept_reject_are_receipt_bound_and_idempotent(tmp_path):
    plan = _plan()
    results = _results()
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    access = access_for(MatterRole.OWNER)
    receipt = append_governed_agentic_investigation_v2_receipt(
        case_id=CASE,
        access=access,
        task_id=TASK,
        plan=plan,
        step_results=results,
        proposed_result=combined,
        root=tmp_path,
        task_loader=lambda case_id: (FakeTask(),),
    )

    accepted = append_governed_agentic_investigation_v2_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecisionV2.ACCEPTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )
    accepted_again = append_governed_agentic_investigation_v2_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecisionV2.ACCEPTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )
    rejected = append_governed_agentic_investigation_v2_professional_decision(
        case_id=CASE,
        access=access,
        task_id=TASK,
        receipt_id=receipt.receipt_id,
        decision=GovernedAgenticDecisionV2.REJECTED,
        reviewer_reference="owner@example.test",
        root=tmp_path,
    )

    assert accepted.decision is GovernedAgenticDecisionV2.ACCEPTED
    assert accepted_again.decision_id == accepted.decision_id
    assert rejected.decision is GovernedAgenticDecisionV2.REJECTED
    assert len((tmp_path / CASE / "decisions.jsonl").read_text().splitlines()) == 2


def test_v2_decision_requires_real_receipt(tmp_path):
    with pytest.raises(GovernedAgenticInvestigationV2Error):
        append_governed_agentic_investigation_v2_professional_decision(
            case_id=CASE,
            access=access_for(MatterRole.OWNER),
            task_id=TASK,
            receipt_id="sha256:missing",
            decision=GovernedAgenticDecisionV2.ACCEPTED,
            reviewer_reference="owner@example.test",
            root=tmp_path,
        )


def test_v2_compact_summaries_are_bounded():
    plan = _plan()
    results = _results()
    results[0]["answer"] = "Evidence sentence. " * 80
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    summary = combined["gac2_step_summaries"][0]["summary"]
    assert len(summary) <= 420
    assert summary.endswith("…")
