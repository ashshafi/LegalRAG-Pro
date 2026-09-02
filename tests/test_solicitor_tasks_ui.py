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
