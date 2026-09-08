from __future__ import annotations

import ast
from pathlib import Path


CASE_OPERATOR = Path(
    "src/ui/case_operator.py"
)
SIDEBAR = Path(
    "src/ui/sidebar.py"
)


def _module_source() -> str:
    return CASE_OPERATOR.read_text(
        encoding="utf-8-sig"
    )


def _function_source(
    name: str,
) -> str:
    source = _module_source()
    tree = ast.parse(
        source
    )

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == name
    ]

    assert len(
        matches
    ) == 1

    return (
        ast.get_source_segment(
            source,
            matches[0],
        )
        or ""
    )


def _visible_strings(
    source: str,
) -> str:
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
        "text_area",
        "selectbox",
        "button",
        "form_submit_button",
        "checkbox",
        "number_input",
        "expander",
        "code",
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

    return "\n".join(
        strings
    ).lower()


def test_saved_working_draft_review_requires_exact_explicit_selection():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        '"Working draft to review"'
        in source
    )
    assert (
        "index=None"
        in source
    )
    assert (
        "_render_working_draft_professional_review("
        in source
    )
    assert (
        "draft_id"
        in source
    )


def test_preview_holds_exact_target_and_decision_passes_expected_target():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    assert (
        "prepare_working_draft_professional_release("
        in source
    )
    assert (
        '"target_id"'
        in source
    )
    assert (
        "_DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY"
        in source
    )
    assert (
        "record_working_draft_professional_release("
        in source
    )
    assert (
        "expected_target_id="
        in source
    )
    assert (
        "previewed_target_id"
        in source
    )

    prepare_index = source.index(
        "prepare_working_draft_professional_release("
    )
    store_index = source.index(
        "_DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY",
        prepare_index,
    )
    release_index = source.index(
        "record_working_draft_professional_release("
    )
    expected_index = source.index(
        "expected_target_id=",
        release_index,
    )

    assert (
        prepare_index
        < store_index
        < release_index
        < expected_index
    )


def test_decision_reloads_exact_draft_authority_and_authenticated_reviewer():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    release_index = source.index(
        "record_working_draft_professional_release("
    )
    decision_prefix = source[
        :release_index
    ]

    assert (
        decision_prefix.count(
            "_load_exact_saved_working_draft("
        )
        >= 2
    )
    assert (
        decision_prefix.count(
            "load_active_governed_analytical_authority("
        )
        >= 2
    )
    assert (
        decision_prefix.count(
            "_current_professional_reviewer_reference("
        )
        >= 2
    )


def test_authenticated_reviewer_uses_access_checked_canonical_email():
    source = _function_source(
        "_current_professional_reviewer_reference"
    )

    for token in (
        "current_user_identity",
        "require_access",
        '"email"',
        "reviewer_reference",
    ):
        assert token in source


def test_every_review_evaluation_is_rendered_in_solicitor_language():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    assert (
        "authority_evaluations"
        in source
    )
    assert (
        "zip("
        in source
    )
    assert (
        "strict=True"
        in source
    )
    assert (
        "_professional_review_check_presentation("
        in source
    )
def test_not_authorized_blocks_approval_but_rejection_remains_available():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    assert (
        '== "NOT_AUTHORIZED"'
        in source
    )
    assert (
        '"Approve for reliance"'
        in source
    )
    assert (
        "disabled=has_not_authorized"
        in source
    )
    assert (
        '"Reject wording"'
        in source
    )


def test_professional_gate_inputs_are_explicit_before_approval():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    for token in (
        "factual_basis_reviewed",
        "legal_authorities_reviewed",
        "unverified_authorities_remaining",
        "professional_judgment_completed",
        "court_or_tribunal_reliance",
        "review_note",
    ):
        assert token in source

    assert (
        "WorkProductReleaseDecision.APPROVED_FOR_RELIANCE"
        in source
    )
    assert (
        "WorkProductReleaseDecision.REJECTED"
        in source
    )


def test_obvious_invalid_decisions_fail_before_release_call():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    release_index = source.index(
        "record_working_draft_professional_release("
    )

    for message in (
        "Enter a professional review note",
        "reviewed the factual basis",
        "reviewed the legal authorities",
        "no unverified legal authorities",
        "applied professional judgment",
        "Rejected wording cannot be marked",
    ):
        assert (
            source.index(
                message
            )
            < release_index
        )


def test_release_error_clears_review_snapshot_and_requires_fresh_review():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    release_index = source.index(
        "record_working_draft_professional_release("
    )
    tail = source[
        release_index:
    ]

    assert (
        "_clear_drafting_professional_review_state()"
        in tail
    )
    assert (
        "Prepare a fresh professional review"
        in tail
    )


def test_review_ui_does_not_mutate_working_draft_task_scope_or_authority():
    source = (
        _function_source(
            "_render_saved_working_drafts"
        )
        + "\n"
        + _function_source(
            "_render_working_draft_professional_review"
        )
    ).lower()

    forbidden = (
        "record_working_draft(",
        "record_prepared_working_draft(",
        "update_task(",
        "append_task_work_progress(",
        "append_task_work_retrieval_receipt(",
        "record_task_work_authority_scope(",
        "activate_authority",
        "publish_authority",
        "record_work_product_release(",
    )

    assert not any(
        token in source
        for token in forbidden
    )


def test_professional_review_ui_uses_solicitor_facing_language():
    source = (
        _function_source(
            "_render_saved_working_drafts"
        )
        + "\n"
        + _function_source(
            "_render_working_draft_professional_review"
        )
    )
    visible = _visible_strings(
        source
    )

    for forbidden in (
        "d1-i4",
        "target_id",
        "scope_binding_id",
        "not_authorized",
        "approved_for_reliance",
        "sha256:",
        "release state machine",
    ):
        assert forbidden not in visible


def test_standalone_drafting_sidebar_remains_disabled():
    sidebar = SIDEBAR.read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(
        sidebar
    )

    matches = []

    for call in ast.walk(
        tree
    ):
        if not isinstance(
            call,
            ast.Call,
        ):
            continue

        if not (
            isinstance(
                call.func,
                ast.Attribute,
            )
            and call.func.attr == "button"
        ):
            continue

        if not call.args:
            continue

        try:
            label = ast.literal_eval(
                call.args[0]
            )
        except Exception:
            continue

        if not (
            isinstance(
                label,
                str,
            )
            and "Drafting" in label
        ):
            continue

        disabled = None

        for keyword in call.keywords:
            if keyword.arg != "disabled":
                continue

            try:
                disabled = ast.literal_eval(
                    keyword.value
                )
            except Exception:
                disabled = None

        matches.append(
            (
                label,
                disabled,
            )
        )

    assert len(
        matches
    ) == 1

    assert (
        matches[0][1]
        is True
    )

def test_professional_review_caution_copy_is_reliance_specific():
    helper = _function_source(
        "_professional_review_check_presentation"
    )
    renderer = _function_source(
        "_render_working_draft_professional_review"
    )
    drafting_mapper = _function_source(
        "_drafting_check_presentation"
    )

    assert (
        "before approving it for reliance"
        in helper
    )
    assert (
        "before saving"
        in drafting_mapper
    )
    assert (
        "_professional_review_check_presentation("
        in renderer
    )
    assert (
        "_drafting_check_presentation("
        not in renderer
    )


def test_professional_review_visible_copy_is_reliance_specific():
    source = _function_source(
        "_professional_review_check_presentation"
    )

    assert (
        "before approving it for reliance"
        in source
    )

    assert (
        "Review this wording carefully before saving."
        in source
    )

    assert (
        "message = message.replace("
        in source
    )
