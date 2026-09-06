from pathlib import Path
from types import SimpleNamespace

from ui.case_operator import (
    attention_issues,
    build_follow_up_question,
    build_issue_investigation_question,
    build_operator_review_question,
    extract_next_investigation,
    issue_attention_points,
    opening_priority_reason,
    select_opening_issue,
)


def _element(status="unresolved", *, unresolved=(), gaps=(), question="What happened?"):
    return SimpleNamespace(
        provisional_status=status,
        unresolved_matters=unresolved,
        evidential_gaps=gaps,
        question=question,
        legal_question=question,
        element_name=question,
    )


def _issue(name, elements, limitations=(), issue_id="issue-1"):
    return SimpleNamespace(
        issue_name=name,
        issue_analysis_id=issue_id,
        elements=tuple(elements),
        overall_limitations=tuple(limitations),
    )


def test_attention_points_clean_broken_leading_question_marker():
    issue = _issue(
        "Knowledge",
        (_element(unresolved=("? Who at CACI knew what and when?",)),),
    )
    assert issue_attention_points(issue)[0] == "Who at CACI knew what and when?"


def test_attention_queue_is_canonical_not_re_ranked():
    a = _issue("First", (_element(unresolved=("A",)),), issue_id="a")
    b = _issue("Second", (_element(status="well_supported"),), issue_id="b")
    c = _issue("Third", (_element(gaps=("C",)),), issue_id="c")
    dashboard = SimpleNamespace(issues=(a, b, c))
    assert [item.issue_name for item in attention_issues(dashboard)] == ["First", "Third"]


def test_gateway_issue_is_selected_before_issue_with_more_open_points():
    knowledge = _issue(
        "Employer knowledge of disability",
        tuple(_element(unresolved=(f"K{i}",)) for i in range(10)),
        issue_id="knowledge",
    )
    limitation = _issue(
        "Limitation, continuing act and just and equitable extension",
        (_element(unresolved=("L1",)),),
        issue_id="limitation",
    )
    dashboard = SimpleNamespace(issues=(knowledge, limitation))
    assert select_opening_issue(dashboard) is limitation
    assert opening_priority_reason(limitation) == "procedural / gateway risk"


def test_first_step_prompt_is_focused_and_has_machine_marker():
    issue = _issue("Limitation", (_element(unresolved=("L",)),))
    prompt = build_issue_investigation_question(issue, autonomous=True)
    assert "single legal issue" in prompt
    assert "normally no more than 700 words" in prompt
    assert "NEXT_INVESTIGATION:" in prompt
    assert "Do not silently change the Current Assessment" in prompt


def test_opening_compatibility_prompt_uses_selected_focused_issue():
    limitation = _issue("Limitation", (_element(unresolved=("L",)),))
    dashboard = SimpleNamespace(issues=(limitation,))
    prompt = build_operator_review_question(dashboard)
    assert "ISSUE\nLimitation" in prompt
    assert "NEXT_INVESTIGATION:" in prompt


def test_extract_next_investigation_requires_exactly_one_marker():
    answer = "Findings\nNEXT_INVESTIGATION: Obtain the July 2005 role documents."
    assert extract_next_investigation(answer) == "Obtain the July 2005 role documents."
    assert extract_next_investigation("No marker") is None
    assert extract_next_investigation(
        "NEXT_INVESTIGATION: One\nNEXT_INVESTIGATION: Two"
    ) is None


def test_follow_up_allows_exact_selected_investigation():
    issue = _issue("Limitation", (_element(unresolved=("L",)),))
    prompt = build_follow_up_question(issue, "Compare the July 2005 role documents.")
    assert "Compare the July 2005 role documents." in prompt
    assert "Carry out that investigation now" in prompt
    assert "WHAT REMAINS UNKNOWN" in prompt


def test_case_operator_task_creation_requires_explicit_user_approval():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    assert source.count("create_task(") == 1
    assert "Approve and create task" in source
    assert "Dismiss proposal" in source
    assert "if not approve:" in source
    assert source.index("if not approve:") < source.index("task = create_task(")
    assert "activate_authority" not in source
    assert "publish_authority" not in source
def test_operator_has_two_step_autonomous_loop():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    assert "def _run_autonomous_opening(" in source
    assert "step 1 of 2" in source
    assert "step 2 of 2" in source
    assert "extract_next_investigation(answer)" in source
    assert "build_follow_up_question(issue, next_investigation)" in source


def test_sidebar_and_legal_issues_binding_remain_present():
    sidebar = Path("src/ui/sidebar.py").read_text(encoding="utf-8-sig")
    issues = Path("src/ui/swd1_issue_workspace.py").read_text(encoding="utf-8-sig")
    assert '"Case Operator"' in sidebar
    assert "from ui.case_operator import show_case_operator" in issues
    assert "show_case_operator(active_case_id, authority_loader=authority_loader)" in issues


def test_extract_next_investigation_accepts_governed_status_prefix():
    answer = (
        "[supported_but_not_established] First-step analysis.\n\n"
        "[unresolved] NEXT_INVESTIGATION: Can the claimant produce a dated schedule?"
    )
    assert (
        extract_next_investigation(answer)
        == "Can the claimant produce a dated schedule?"
    )


def test_extract_next_investigation_still_requires_unique_marker_with_status_prefix():
    answer = (
        "[unresolved] NEXT_INVESTIGATION: One question\n"
        "[unresolved] NEXT_INVESTIGATION: Another question"
    )
    assert extract_next_investigation(answer) is None


def test_working_view_strips_governed_status_prefixes_without_changing_raw_answer():
    from ui.case_operator import _solicitor_answer_text

    raw = (
        "[supported_but_not_established] First proposition.\n\n"
        "[unresolved] Second proposition."
    )
    display = _solicitor_answer_text(raw)
    assert display == "First proposition.\n\nSecond proposition."
    assert raw.startswith("[supported_but_not_established]")


def test_r7_parser_accepts_status_prefixed_machine_marker_without_consuming_newlines():
    from ui.case_operator import extract_next_investigation, _solicitor_answer_text

    raw = (
        "[supported_but_not_established] First proposition.\n\n"
        "[unresolved] NEXT_INVESTIGATION: Obtain the dated schedule."
    )

    assert extract_next_investigation(raw) == "Obtain the dated schedule."
    assert _solicitor_answer_text(raw) == (
        "First proposition.\n\nNEXT_INVESTIGATION: Obtain the dated schedule."
    )


def test_extract_recommended_next_action_from_validated_working_text():
    from ui.case_operator import extract_recommended_next_action

    answer = (
        "[supported] WHAT I FOUND: something.\n\n"
        "[unresolved] RECOMMENDED NEXT ACTION: Prepare a dated act/omission schedule "
        "and verify the ET1 and ACAS dates.\n\n"
        "Frozen analytical limitations:\n- LIM-X: unresolved."
    )
    assert extract_recommended_next_action(answer) == (
        "Prepare a dated act/omission schedule and verify the ET1 and ACAS dates."
    )


def test_default_proposed_task_title_for_limitation():
    from ui.case_operator import default_proposed_task_title

    assert default_proposed_task_title(
        "Limitation, continuing act and just and equitable extension"
    ) == "Prepare limitation act/omission schedule"


def test_task_creation_is_explicitly_approval_gated():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert source.count("create_task(") == 1
    approve_pos = source.index("if not approve:")
    create_pos = source.index("task = create_task(")
    assert approve_pos < create_pos
    assert "Approve and create task" in source
    assert "Dismiss proposal" in source
    assert "access = CaseRepository().require_access(" in source
    assert "origin=TaskOrigin.NEXT_LEGAL_ACTION" in source


def test_autonomous_trace_preserves_issue_identity_for_approved_task():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    assert '"issue_analysis_id": issue_analysis_id' in source
    assert "_render_proposed_task(" in source


def test_attention_cleanup_removes_corrupted_question_prefixes_without_touching_content():
    from ui.case_operator import _clean_open_point

    assert _clean_open_point("? The mapped evidence does not fully resolve this.") == (
        "The mapped evidence does not fully resolve this."
    )
    assert _clean_open_point("?? Was the adjustment implemented?") == (
        "Was the adjustment implemented?"
    )
    assert _clean_open_point("\uFFFD\uFFFD Employer knowledge remains disputed.") == (
        "Employer knowledge remains disputed."
    )
    assert _clean_open_point("\u2753 What happened next?") == "What happened next?"


def test_approved_task_has_direct_open_matter_tasks_handoff():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert '"Open matter tasks"' in source
    assert 'st.session_state["mw1_task_workspace_case_id"] = case_id' in source
    assert 'st.session_state.pop("case_operator_workspace_case_id", None)' in source
    approved_pos = source.index(
        'st.session_state.get(_PROPOSAL_CREATED_KEY) == fingerprint'
    )
    handoff_pos = source.index('"Open matter tasks"', approved_pos)
    assert approved_pos < handoff_pos


def test_case_operator_working_labels_are_ascii_stable():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    sidebar = Path("src/ui/sidebar.py").read_text(encoding="utf-8-sig")

    assert '"Case Operator"' in sidebar
    assert '"?? Case Operator"' not in sidebar
    assert '"? Back to Legal Issues"' not in source
    assert "Step 1 ? focused issue review" not in source




def test_task_execution_prompt_uses_approved_task_contract():
    from types import SimpleNamespace
    from ui.case_operator import build_task_execution_question
    from solicitor_tasks import TaskStatus

    task = SimpleNamespace(
        title="Prepare limitation act/omission schedule",
        issue_name="Limitation",
        originating_question="Identify every alleged CACI act or omission.",
        why_it_matters="Particularise the limitation case.",
        status=TaskStatus.OPEN,
    )
    prompt = build_task_execution_question(task)

    assert "Prepare limitation act/omission schedule" in prompt
    assert "Identify every alleged CACI act or omission." in prompt
    assert "Particularise the limitation case." in prompt
    assert "Do not silently change the Current Assessment or task state." in prompt
    assert "TASK_OUTCOME: COMPLETE" in prompt
    assert "TASK_OUTCOME: CONTINUE" in prompt
    assert "TASK_OUTCOME: BLOCKED" in prompt


def test_task_outcome_parser_accepts_governed_status_prefix():
    from ui.case_operator import extract_task_outcome

    assert extract_task_outcome(
        "[supported] Work result.\n\n[unresolved] TASK_OUTCOME: CONTINUE"
    ) == "CONTINUE"
    assert extract_task_outcome("TASK_OUTCOME: COMPLETE") == "COMPLETE"
    assert extract_task_outcome(
        "TASK_OUTCOME: COMPLETE\nTASK_OUTCOME: CONTINUE"
    ) is None


def test_working_task_does_not_automatically_update_status():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    work_pos = source.index('"Work selected task"')
    result_call = source.index("_run_question(case_id, documents, question)", work_pos)
    rerun_pos = source.index("st.rerun()", result_call)
    work_block = source[work_pos:rerun_pos]
    assert "_update_task_status(" not in work_block
    assert "update_task(" not in work_block


def test_task_status_mutation_is_explicitly_user_gated():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert source.count("update_task(") == 1
    assert '"Approve completion"' in source
    assert '"Mark in progress"' in source
    assert "status=TaskStatus.COMPLETED" in source
    assert "status=TaskStatus.IN_PROGRESS" in source
    assert "CaseRepository().require_access(" in source
    assert "access=access" in source


def test_task_execution_reuses_existing_governed_question_path():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert "def _render_approved_task_execution(" in source
    assert "build_task_execution_question(selected_task)" in source
    assert "_run_question(case_id, documents, question)" in source
    assert "ask_with_reference_findings(question, documents, case_id=case_id)" in source


def test_r15_residual_question_marker_rendering_is_removed():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert 'st.write("? " + point)' not in source
    assert '" ? no unique NEXT_INVESTIGATION' not in source
    assert '+ " ? "' not in source


def test_task_continuation_prompt_uses_latest_persisted_progress():
    from types import SimpleNamespace
    from task_work_progress import TaskWorkOutcome
    from ui.case_operator import build_task_continuation_question

    task = SimpleNamespace(
        title="Prepare limitation act/omission schedule",
        issue_name="Limitation",
        originating_question="Identify the acts and omissions.",
        why_it_matters="Particularise limitation accurately.",
        status=SimpleNamespace(value="in_progress"),
    )
    history = (
        SimpleNamespace(
            answer="The ET1 presentation date remains unresolved.",
            outcome=TaskWorkOutcome.CONTINUE,
        ),
    )

    prompt = build_task_continuation_question(task, history)

    assert "Continue this already-approved IN-PROGRESS matter task" in prompt
    assert "The ET1 presentation date remains unresolved." in prompt
    assert "single highest-value unresolved" in prompt
    assert "Do not merely repeat the previous result." in prompt
    assert "TASK_OUTCOME: COMPLETE" in prompt


def test_task_continuation_falls_back_to_first_execution_without_history():
    from types import SimpleNamespace
    from ui.case_operator import (
        build_task_continuation_question,
        build_task_execution_question,
    )

    task = SimpleNamespace(
        title="Task",
        issue_name="Issue",
        originating_question="Question",
        why_it_matters="Reason",
        status=SimpleNamespace(value="in_progress"),
    )
    assert build_task_continuation_question(task, ()) == build_task_execution_question(task)


def test_task_work_persistence_is_separate_from_task_status_mutation():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert "append_task_work_progress(" in source
    assert "load_task_work_progress(" in source
    persist_start = source.index("def _persist_task_work_result(")
    persist_end = source.index("\ndef ", persist_start + 1)
    persist_block = source[persist_start:persist_end]
    assert "update_task(" not in persist_block
    assert "TaskStatus.COMPLETED" not in persist_block
    assert "TaskStatus.IN_PROGRESS" not in persist_block


def test_explicit_work_action_records_progress_before_rerun():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    fn_start = source.index("def _render_approved_task_execution(")
    run_pos = source.index("_run_question(case_id, documents, question)", fn_start)
    persist_pos = source.index("_persist_task_work_result(", run_pos)
    rerun_pos = source.index("st.rerun()", persist_pos)
    assert run_pos < persist_pos < rerun_pos


def test_in_progress_history_uses_continue_label():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert '"Continue selected task"' in source
    assert "selected_task.status is TaskStatus.IN_PROGRESS" in source
    assert "build_task_continuation_question(" in source
    assert "_substantive_task_work_history(history)" in source


def test_task_work_history_is_rendered_from_persisted_store():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert "history = load_task_work_progress(case_id, selected_task_id)" in source
    assert "_render_task_work_history(history=history)" in source
    assert '"Previous task work"' in source


def test_r21_does_not_change_task_schema_or_authority():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    progress = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")

    assert "activate_authority" not in source
    assert "publish_authority" not in source
    assert "update_task(" not in progress
    assert '"TASK_UPDATED"' not in progress


def test_extract_next_task_investigation_requires_one_unique_marker():
    from ui.case_operator import extract_next_task_investigation

    assert (
        extract_next_task_investigation(
            "Work remains.\nNEXT_TASK_INVESTIGATION: Verify the ET1 presentation date.\n"
            "TASK_OUTCOME: CONTINUE"
        )
        == "Verify the ET1 presentation date."
    )
    assert extract_next_task_investigation("No marker") is None
    assert (
        extract_next_task_investigation(
            "NEXT_TASK_INVESTIGATION: One\nNEXT_TASK_INVESTIGATION: Two"
        )
        is None
    )


def test_extract_next_task_investigation_accepts_status_prefix():
    from ui.case_operator import extract_next_task_investigation

    assert (
        extract_next_task_investigation(
            "[partially_supported] NEXT_TASK_INVESTIGATION: Verify ACAS certificate dates."
        )
        == "Verify ACAS certificate dates."
    )


def test_continuation_uses_exact_durable_next_investigation():
    from types import SimpleNamespace
    from task_work_progress import TaskWorkOutcome
    from ui.case_operator import build_task_continuation_question

    task = SimpleNamespace(
        title="Prepare limitation act/omission schedule",
        issue_name="Limitation",
        why_it_matters="Particularise limitation accurately.",
    )
    history = (
        SimpleNamespace(
            answer=(
                "Prior work.\n"
                "NEXT_TASK_INVESTIGATION: Verify the ET1 presentation date from the filed ET1.\n"
                "TASK_OUTCOME: CONTINUE"
            ),
            outcome=TaskWorkOutcome.CONTINUE,
        ),
    )

    prompt = build_task_continuation_question(task, history)

    assert "EXACT NEXT TASK INVESTIGATION" in prompt
    assert "Verify the ET1 presentation date from the filed ET1." in prompt
    assert "Work that exact investigation now." in prompt
    assert "do not restart the task from zero" in prompt.lower()


def test_continuation_without_legacy_marker_uses_transitional_selection():
    from types import SimpleNamespace
    from task_work_progress import TaskWorkOutcome
    from ui.case_operator import build_task_continuation_question

    task = SimpleNamespace(
        title="Task",
        issue_name="Issue",
        why_it_matters="Reason",
    )
    history = (
        SimpleNamespace(
            answer="Legacy R21 durable result without a next-task marker.",
            outcome=TaskWorkOutcome.CONTINUE,
        ),
    )

    prompt = build_task_continuation_question(task, history)

    assert "transitional continuation only" in prompt
    assert "single highest-value unresolved sub-investigation" in prompt


def test_first_task_run_requires_durable_next_marker_on_continue():
    from types import SimpleNamespace
    from ui.case_operator import build_task_execution_question

    task = SimpleNamespace(
        title="Task",
        issue_name="Issue",
        originating_question="Question",
        why_it_matters="Reason",
        status=SimpleNamespace(value="open"),
    )
    prompt = build_task_execution_question(task)

    assert "NEXT_TASK_INVESTIGATION: <one focused next investigation>" in prompt
    assert "TASK_OUTCOME: CONTINUE" in prompt


def test_r22_reuses_answer_persistence_without_schema_change():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    progress = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")
    tasks = Path("src/solicitor_tasks.py").read_text(encoding="utf-8-sig")

    assert "extract_next_task_investigation(" in source
    assert "NEXT_TASK_INVESTIGATION:" in source
    assert "next_task_investigation" not in progress
    assert "next_task_investigation" not in tasks
    assert "update_task(" not in progress


def test_r23_continuation_parses_marker_before_cleaning_answer():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert 'raw_previous_answer = getattr(latest, "answer", "")' in source
    assert "previous_answer = _clean(raw_previous_answer)" in source
    assert "durable_next = extract_next_task_investigation(raw_previous_answer)" in source
    assert "durable_next = extract_next_task_investigation(previous_answer)" not in source
