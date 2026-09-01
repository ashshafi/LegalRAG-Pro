from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def call_name(call):
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return call.func.value.id + "." + call.func.attr
    return None

def label(call):
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None

def load_fn(rel, fn_name):
    source = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == fn_name
    )
    calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)]
    return source, parents, calls

def inside_form(node, parents):
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.With):
            for item in current.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and call_name(expr) == "st.form":
                    return True
    return False

INPUT_WIDGET_CALLS = {
    "st.text_input",
    "st.text_area",
    "st.selectbox",
    "st.multiselect",
    "st.radio",
    "st.checkbox",
    "st.toggle",
    "st.number_input",
    "st.date_input",
    "st.time_input",
    "st.slider",
    "st.select_slider",
    "st.file_uploader",
    "st.data_editor",
}

def input_widget_matches(calls, wanted):
    return [
        call
        for call in calls
        if label(call) == wanted
        and call_name(call) in INPUT_WIDGET_CALLS
    ]

def assert_in_form(rel, fn_name, labels):
    _, parents, calls = load_fn(rel, fn_name)
    for wanted in labels:
        matches = input_widget_matches(calls, wanted)
        assert matches, (rel, fn_name, wanted)
        assert all(inside_form(call, parents) for call in matches)

def assert_outside_form(rel, fn_name, wanted):
    _, parents, calls = load_fn(rel, fn_name)
    matches = input_widget_matches(calls, wanted)
    assert matches, (rel, fn_name, wanted)
    assert all(not inside_form(call, parents) for call in matches)

def test_chat_is_submit_batched_with_legacy_test_double_compatibility():
    source = (ROOT / "src/ui/chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_chat"
    )

    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
    ]
    labels = [label(call) for call in calls]

    assert "Ask a legal question" in labels
    assert "\U0001f50d Ask" in labels
    assert "with _question_form():" in source
    assert '_question_text_area(' in source
    submit_calls = [
        call
        for call in calls
        if isinstance(call.func, ast.Name)
        and call.func.id == "_question_form_submit_button"
        and label(call) == "\U0001f50d Ask"
    ]
    assert len(submit_calls) == 1

    # Production Streamlit takes the form/text-area path; historical lightweight
    # test doubles can use their existing text_input/button methods.
    assert 'getattr(st, "form", None)' in source
    assert 'getattr(st, "text_area", None)' in source
    assert 'getattr(st, "form_submit_button", None)' in source
    assert "return st.text_input(label, **kwargs)" in source
    assert "return st.button(label)" in source

    assert 'st.button("\\U0001f50d Ask")' not in source

def test_workspace_filters_are_batched_but_navigation_is_immediate():
    assert_in_form("src/ui/workspace.py", "_render_traceability", ("Object type", "Literal search"))
    assert_in_form("src/ui/workspace.py", "_render_evidence", (
        "Literal search", "Document group", "Source type", "Evidence status",
        "Provenance type", "Provenance confidence", "Author", "Party", "Issue ID",
    ))
    assert_in_form("src/ui/workspace.py", "_render_chronology", (
        "Literal search", "Event type", "Participant", "Occurrence raw status",
        "Timing raw status", "Confidence raw status", "Related issue ID",
    ))
    assert_in_form("src/ui/workspace.py", "_render_people", ("Literal search", "Occurrence context"))
    assert_outside_form("src/ui/workspace.py", "_render_traceability", "Frozen object")
    assert_outside_form("src/ui/workspace.py", "show_workspace", "Workspace view")

def test_finance_filters_are_batched_but_navigation_is_immediate():
    assert_in_form("src/ui/finance_workspace.py", "_render_matrix",
                   ("Literal search", "Company IDs", "Metric codes", "Raw statuses"))
    assert_in_form("src/ui/finance_workspace.py", "_render_evidence",
                   ("Literal search", "Source channels", "Binding classes"))
    assert_in_form("src/ui/finance_workspace.py", "_render_traceability",
                   ("Object kind", "Literal search"))
    assert_outside_form("src/ui/finance_workspace.py", "_render_traceability", "Frozen object")
    assert_outside_form("src/ui/finance_workspace.py", "_render_finance_workspace_analyst", "Workspace view")

def test_no_openai_calls_added_to_patched_ui_modules():
    for rel in ("src/ui/chat.py", "src/ui/workspace.py", "src/ui/finance_workspace.py"):
        source = (ROOT / rel).read_text(encoding="utf-8").casefold()
        assert "responses.create" not in source
        assert "embeddings.create" not in source
        assert "create_default_openai_client" not in source
