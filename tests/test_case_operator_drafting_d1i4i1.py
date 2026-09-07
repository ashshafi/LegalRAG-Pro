from __future__ import annotations

import ast
import inspect
from pathlib import Path

import ui.case_operator as module


def _source(function):
    return inspect.getsource(
        function
    )


def test_internal_authority_results_are_mapped_to_solicitor_language():
    kind, message = (
        module._drafting_check_presentation(
            "ALIGNED"
        )
    )

    assert kind == "success"
    assert "current case assessment" in message.lower()
    assert "aligned" not in message.lower()

    kind, message = (
        module._drafting_check_presentation(
            "CAUTION"
        )
    )

    assert kind == "warning"
    assert "review" in message.lower()
    assert "caution" not in message.lower()

    kind, message = (
        module._drafting_check_presentation(
            "NOT_AUTHORIZED"
        )
    )

    assert kind == "error"
    assert "not approved for reliance" in message.lower()
    assert "not_authorized" not in message.lower()


def test_context_binding_is_exact_and_case_task_scoped():
    value = {
        "case_id": "case",
        "task_id": "task",
        "progress_id": "progress",
        "scope_binding_id": "scope",
        "element_id": "element",
    }

    assert module._drafting_context_matches(
        value,
        case_id="case",
        task_id="task",
        progress_id="progress",
        scope_binding_id="scope",
        element_id="element",
    )

    assert not module._drafting_context_matches(
        value,
        case_id="other",
        task_id="task",
    )

    assert not module._drafting_context_matches(
        value,
        case_id="case",
        task_id="task",
        progress_id="other",
    )


def test_generate_and_save_are_separate_explicit_actions():
    source = _source(
        module._render_drafting_workflow
    )

    assert source.count(
        "generate_working_draft_candidate("
    ) == 1

    assert source.count(
        "prepare_generated_working_draft("
    ) == 1

    assert source.count(
        "record_prepared_working_draft("
    ) == 1

    assert source.count(
        '"Generate draft"'
    ) == 1

    assert source.count(
        '"Save as working draft"'
    ) == 1

    tree = ast.parse(
        source
    )

    generate_blocks = tuple(
        node
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.If,
        )
        and isinstance(
            node.test,
            ast.Name,
        )
        and node.test.id
        == "generate_clicked"
    )

    save_blocks = tuple(
        node
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.If,
        )
        and isinstance(
            node.test,
            ast.Name,
        )
        and node.test.id
        == "save_clicked"
    )

    assert len(
        generate_blocks
    ) == 1

    assert len(
        save_blocks
    ) == 1

    def called_names(node):
        names = []

        for child in ast.walk(
            node
        ):
            if not isinstance(
                child,
                ast.Call,
            ):
                continue

            if isinstance(
                child.func,
                ast.Name,
            ):
                names.append(
                    child.func.id
                )

            elif isinstance(
                child.func,
                ast.Attribute,
            ):
                names.append(
                    child.func.attr
                )

        return tuple(
            names
        )

    generate_calls = called_names(
        generate_blocks[0]
    )

    save_calls = called_names(
        save_blocks[0]
    )

    assert (
        "generate_working_draft_candidate"
        in generate_calls
    )

    assert (
        "prepare_generated_working_draft"
        in generate_calls
    )

    assert (
        "record_prepared_working_draft"
        not in generate_calls
    )

    assert (
        "record_prepared_working_draft"
        in save_calls
    )

    assert (
        "generate_working_draft_candidate"
        not in save_calls
    )

    assert (
        "prepare_generated_working_draft"
        not in save_calls
    )

    assert "record_working_draft(" not in source


def test_generate_uses_canonical_client_model_and_reasoning_configuration():
    source = _source(
        module._render_drafting_workflow
    )

    assert "client=" in source

    assert (
        "_legal_answer_provider_client()"
        in source
    )

    assert "openai_client" not in source

    assert (
        "INTERACTIVE_CHAT_MODEL"
        in source
    )

    assert (
        "INTERACTIVE_REASONING_EFFORT"
        in source
    )


def test_generation_requires_explicit_work_and_focus_selection():
    source = _source(
        module._render_drafting_workflow
    )

    assert '"Work to draft from"' in source
    assert '"Draft focus"' in source

    # Both selectboxes deliberately begin with no selection.
    assert source.count(
        "index=None"
    ) >= 2


def test_fresh_action_context_rechecks_access_progress_receipt_scope_and_authority():
    source = _source(
        module._load_drafting_action_context
    )

    required = (
        "current_user_identity",
        "require_access",
        "load_task_work_progress",
        "load_task_work_retrieval_receipts",
        "load_task_work_authority_scope",
        "load_active_governed_analytical_authority",
        "resolve_task_work_authority_scope",
    )

    for token in required:
        assert token in source


def test_case_operator_places_drafting_after_professional_scope_capture():
    source = _source(
        module._render_approved_task_execution
    )

    scope_at = source.index(
        "_render_task_work_scope_capture("
    )

    drafting_at = source.index(
        "_render_drafting_workflow("
    )

    substantive_at = source.index(
        "substantive_history ="
    )

    assert scope_at < drafting_at < substantive_at


def test_drafting_ui_does_not_mutate_task_current_assessment_or_release_state():
    source = _source(
        module._render_drafting_workflow
    ).lower()

    forbidden = (
        "update_task(",
        "append_task_work_progress(",
        "append_task_work_retrieval_receipt(",
        "record_task_work_authority_scope(",
        "work_product_release",
        "record_work_product_release",
        "activate_authority",
        "publish_authority",
    )

    assert not any(
        token in source
        for token in forbidden
    )


def test_solicitor_visible_drafting_strings_do_not_expose_internal_stage_names():
    source = _source(
        module._render_drafting_workflow
    )

    tree = ast.parse(
        source
    )

    visible_methods = {
        "markdown",
        "caption",
        "error",
        "warning",
        "info",
        "success",
        "write",
        "subheader",
        "title",
        "text_input",
        "text_area",
        "selectbox",
        "button",
        "form_submit_button",
        "spinner",
        "expander",
    }

    strings = []

    for call in ast.walk(
        tree
    ):
        if not isinstance(
            call,
            ast.Call,
        ):
            continue

        if not isinstance(
            call.func,
            ast.Attribute,
        ):
            continue

        if (
            call.func.attr
            not in visible_methods
        ):
            continue

        values = list(
            call.args
        )

        values.extend(
            keyword.value
            for keyword
            in call.keywords
        )

        for value in values:
            for node in ast.walk(
                value
            ):
                if (
                    isinstance(
                        node,
                        ast.Constant,
                    )
                    and isinstance(
                        node.value,
                        str,
                    )
                ):
                    strings.append(
                        node.value
                    )

    visible_text = "\n".join(
        strings
    ).lower()

    for forbidden in (
        "r68",
        "d1-i1",
        "d1-i3",
        "authority hash",
        "safe-set intersection",
        "scope_binding_id",
    ):
        assert forbidden not in visible_text

    # The exact governance binding remains internal even though it is not
    # rendered as solicitor-facing terminology.
    assert (
        '"scope_binding_id"'
        in source
    )


def test_standalone_drafting_sidebar_remains_disabled():
    sidebar = Path(
        "src/ui/sidebar.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    marker = sidebar.find(
        '"✍ Drafting"'
    )

    assert marker >= 0

    window = sidebar[
        marker:
        marker + 500
    ]

    assert "disabled=True" in window