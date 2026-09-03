from pathlib import Path
import ui.solicitor_tasks as task_ui

SOURCE = Path(task_ui.__file__).read_text(encoding="utf-8")


def test_task_workspace_has_authorised_fields():
    for label in (
        "Tasks",
        "Open",
        "In progress",
        "Completed",
        "Deferred",
        "Priority",
        "Due date",
        "Assigned to",
        "Related issue",
        "Why this matters",
        "Origin",
        "Create task",
        "Update task",
    ):
        assert label in SOURCE


def test_task_ui_states_analytical_boundary():
    assert "does not change the legal assessment" in SOURCE
    assert "does not prove a proposition" in SOURCE
    assert "change the current case assessment" in SOURCE


def test_task_ui_does_not_expand_into_project_management():
    for forbidden in (
        "kanban",
        "dependency",
        "dependencies",
        "notification",
        "workload",
        "calendar integration",
    ):
        assert forbidden not in SOURCE.lower()

def test_task_workspace_suppresses_previous_analysis_tools():
    app_source = (
        Path(__file__).resolve().parents[1] / "src" / "app.py"
    ).read_text(encoding="utf-8")

    assert 'if not st.session_state.get("mw1_task_workspace_case_id"):' in app_source
    assert 'with st.expander("Previous analysis tools", expanded=False):' in app_source


def test_evidence_origin_is_solicitor_facing():
    assert "TaskOrigin.EVIDENCE" in SOURCE
    assert '"**Evidence**"' in SOURCE
    assert "origin_evidence_key" in SOURCE


def test_task_ui_does_not_duplicate_evidence_text():
    for forbidden in (
        "evidence_text", "source_text", "passage_text",
        "chunk_text", "exact_page_text",
    ):
        assert forbidden not in SOURCE


def test_evidence_task_requires_explicit_create_button():
    assert 'with st.expander("Create task", expanded=False):' in SOURCE
    assert 'st.form_submit_button(' in SOURCE
    assert '"Create task"' in SOURCE

def test_task_editing_batches_fields_until_explicit_submit():
    assert 'with st.form(' in SOURCE
    assert 'key=key + "::form"' in SOURCE
    assert 'key="mw1_update_form::" + task.task_id' in SOURCE
    assert 'st.form_submit_button(' in SOURCE
    assert '"Create task"' in SOURCE
    assert '"Save task"' in SOURCE
    assert 'if st.button("Create task"' not in SOURCE
    assert 'if st.button("Save task"' not in SOURCE


def test_chronology_origin_is_solicitor_facing_and_reference_only():
    assert "TaskOrigin.CHRONOLOGY" in SOURCE
    assert '"**Chronology event**"' in SOURCE
    assert "origin_chronology_event_id" in SOURCE
    for forbidden in (
        "event_description", "assertion_text", "event_evidence_keys", "event_citations",
    ):
        assert forbidden not in SOURCE


def test_chronology_creator_uses_same_batched_explicit_form():
    assert '_chronology_label(' in SOURCE
    assert 'origin_chronology_event_id=origin_chronology_event_id' in SOURCE
    assert 'with st.form(' in SOURCE
    assert 'st.form_submit_button(' in SOURCE
    assert 'if st.button("Create task"' not in SOURCE


def test_multi_issue_choice_is_inside_create_form():
    form = SOURCE.index("with st.form(")
    issue = SOURCE.index('resolved_issue_id = st.selectbox(', form)
    submit = SOURCE.index('st.form_submit_button(', issue)
    assert form < issue < submit


def test_chronology_origin_uses_solicitor_facing_event_type_without_losing_identity():
    assert task_ui._chronology_label(
        "event-uuid",
        "17 August 2026",
        "return_to_work",
    ) == "17 August 2026 · Return to work"
    assert task_ui._chronology_label(
        "event-uuid",
        None,
        None,
    ) == "Chronology event"

    # Immutable identity remains in the persisted task contract.
    assert "origin_chronology_event_id=origin_chronology_event_id" in SOURCE
