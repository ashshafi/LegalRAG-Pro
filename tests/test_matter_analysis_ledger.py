from types import SimpleNamespace

import pytest

from matter_analysis_ledger import (
    MatterAnalysisLedgerError,
    RelationshipReviewState,
    RelationshipType,
    build_matter_analysis_ledger,
    current_relationships,
    derive_relationship_id,
    load_relationship_events,
    propose_relationship,
    review_relationship,
)


CASE = "case-1"
AUTHORITY = "authority-1"
ISSUE = "issue-1"
ELEMENT = "element-1"


def test_relationship_identity_is_pair_order_independent():

    first = derive_relationship_id(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E001",
        right_evidence_key="E002",
    )

    second = derive_relationship_id(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E002",
        right_evidence_key="E001",
    )

    assert first == second


def test_propose_then_approve_is_append_only(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E001",
        right_evidence_key="E002",
        rationale=(
            "The propositions cannot "
            "both be correct."
        ),
        root=tmp_path,
        created_at=(
            "2026-08-30T22:00:00+00:00"
        ),
    )

    assert (
        proposed.state
        is RelationshipReviewState.PROPOSED
    )

    approved = review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.APPROVED,
        root=tmp_path,
        created_at=(
            "2026-08-30T22:01:00+00:00"
        ),
    )

    events = load_relationship_events(
        case_id=CASE,
        authority_id=AUTHORITY,
        root=tmp_path,
    )

    assert len(events) == 2

    assert (
        events[0].state
        is RelationshipReviewState.PROPOSED
    )

    assert (
        events[1].state
        is RelationshipReviewState.APPROVED
    )

    assert (
        approved.previous_event_id
        == proposed.event_id
    )

    current = current_relationships(
        events
    )

    assert current == (
        approved,
    )


def test_terminal_review_cannot_be_silently_changed(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CORROBORATES,
        left_evidence_key="E003",
        right_evidence_key="E004",
        rationale=(
            "Independent records support "
            "the same proposition."
        ),
        root=tmp_path,
    )

    review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.REJECTED,
        root=tmp_path,
    )

    with pytest.raises(
        MatterAnalysisLedgerError,
        match="already been reviewed",
    ):

        review_relationship(
            case_id=CASE,
            authority_id=AUTHORITY,
            relationship_id=
                proposed.relationship_id,
            decision=
                RelationshipReviewState.APPROVED,
            root=tmp_path,
        )


def test_rejected_coordinate_cannot_be_silently_reproposed(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E010",
        right_evidence_key="E011",
        rationale="First review.",
        root=tmp_path,
    )

    review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.REJECTED,
        root=tmp_path,
    )

    with pytest.raises(
        MatterAnalysisLedgerError,
        match="review history",
    ):

        propose_relationship(
            case_id=CASE,
            authority_id=AUTHORITY,
            issue_analysis_id=ISSUE,
            element_id=ELEMENT,
            relationship_type=
                RelationshipType.CORROBORATES,
            left_evidence_key="E010",
            right_evidence_key="E011",
            rationale="Silent retry.",
            root=tmp_path,
        )


def test_projection_reuses_existing_matrix_roles():

    status = SimpleNamespace(
        value="DISPUTED"
    )

    confidence = SimpleNamespace(
        value="MEDIUM"
    )

    element = SimpleNamespace(
        element_id=
            ELEMENT,

        element_name=
            "Knowledge",

        legal_question=
            "Did the employer know?",

        analysis_status=
            status,

        analysis_confidence=
            confidence,

        supporting_evidence_keys=
            ("E001",),

        adverse_evidence_keys=
            ("E002",),

        corroborative_evidence_keys=
            ("E003",),

        neutral_evidence_keys=
            ("E004",),

        conflicting_evidence_keys=
            ("E005",),

        evidential_gap_ids=
            ("G001",),

        unresolved_matters=
            (
                "Exact date unresolved",
            ),

        provisional_analysis=
            "Knowledge remains disputed.",
    )

    issue = SimpleNamespace(
        issue_analysis_id=
            ISSUE,

        issue_definition_id=
            "definition-1",

        issue_definition_version=
            "1.0",

        issue_name=
            "Employer knowledge",

        issue_summary=
            "Knowledge is disputed.",

        element_records=
            (
                element,
            ),
    )

    authority = SimpleNamespace(
        manifest=
            SimpleNamespace(
                case_id=
                    CASE,

                authority_id=
                    AUTHORITY,
            ),

        case_matrices=
            SimpleNamespace(
                issue_matrix=
                    (
                        issue,
                    ),
            ),
    )

    ledger = build_matter_analysis_ledger(
        authority=
            authority,
    )

    projected = (
        ledger
        .issues[0]
        .elements[0]
    )

    assert (
        projected.supporting_evidence_keys
        == ("E001",)
    )

    assert (
        projected.adverse_evidence_keys
        == ("E002",)
    )

    assert (
        projected.corroborative_evidence_keys
        == ("E003",)
    )

    assert (
        projected.conflicting_evidence_keys
        == ("E005",)
    )

    assert (
        projected.evidential_gap_ids
        == ("G001",)
    )

    assert (
        projected.analytical_status
        == "DISPUTED"
    )


def test_app_renders_ledger_after_existing_legal_issue_dashboard():

    source = open(
        "src/app.py",
        encoding="utf-8",
    ).read()

    dashboard = source.index(
        "show_legal_issue_dashboard(active_case_id)"
    )

    ledger = source.index(
        "show_matter_analysis_ledger(active_case_id)",
        dashboard,
    )

    assert (
        dashboard
        < ledger
    )


def test_ui_module_imports():

    import ui.matter_analysis_ledger

    assert (
        ui.matter_analysis_ledger
        is not None
    )



def test_human_evidence_selector_uses_existing_authority_metadata():

    from ui.matter_analysis_ledger import (
        _build_evidence_display_index,
        _format_evidence_option,
    )

    evidence = SimpleNamespace(
        evidence_key="E001",
        source_filename="HR correspondence.pdf",
        page_number=2,
        chunk_text=(
            "The employer received the medical "
            "information before the relevant decision."
        ),
    )

    authority = SimpleNamespace(
        governed_issue_evidence_map=
            SimpleNamespace(
                bindings=(
                    evidence,
                ),
            ),

        governed_evidential_analysis=
            None,

        structured_legal_analysis_results=
            (),

        case_matrices=
            None,
    )

    index = _build_evidence_display_index(
        authority,
        {
            "E001"
        },
    )

    label = _format_evidence_option(
        "E001",
        index,
        {
            "E001": (
                "SUPPORTING",
            )
        },
    )

    assert "SUPPORTING" in label
    assert "HR correspondence.pdf" in label
    assert "p.2" in label
    assert "employer received" in label
    assert "E001" in label


def test_human_evidence_selector_preserves_exact_key_fallback():

    from ui.matter_analysis_ledger import (
        _format_evidence_option,
    )

    key = (
        "8081166d-9889-40bb-8add-"
        "5d0893037ff0__Applicant"
    )

    label = _format_evidence_option(
        key,
        {},
        {
            key: (
                "ADVERSE",
            )
        },
    )

    assert "ADVERSE" in label
    assert "Applicant" in label


def test_mal1_heading_is_ascii_safe():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'st.header(\n'
        '        "Issue Review & Decisions"\n'
        '    )'
        in source
    )

    assert (
        "Technical system: Matter Analysis Ledger."
        in source
    )




def test_exact_binding_metadata_does_not_bleed_between_evidence_keys():

    from types import SimpleNamespace

    from ui.matter_analysis_ledger import (
        _build_evidence_display_index,
    )


    first = SimpleNamespace(
        evidence_key="E-A",
        original_filename="A.pdf",
        page_number=1,
        citation="A.pdf, p.1",
        chunk_text="Exact text from A.",
    )

    second = SimpleNamespace(
        evidence_key="E-B",
        original_filename="B.pdf",
        page_number=7,
        citation="B.pdf, p.7",
        chunk_text="Exact text from B.",
    )


    authority = SimpleNamespace(
        governed_issue_evidence_map=
            SimpleNamespace(
                bindings=(
                    SimpleNamespace(
                        evidence=first
                    ),
                    SimpleNamespace(
                        evidence=second
                    ),
                )
            ),

        # Deliberately poisoned unrelated containers.
        governed_evidential_analysis=
            SimpleNamespace(
                original_filename=
                    "WRONG.pdf",
                page_number=
                    999,
                evidence_key=
                    "E-A",
            ),

        structured_legal_analysis_results=
            (
                SimpleNamespace(
                    original_filename=
                        "ALSO-WRONG.pdf",
                    evidence_key=
                        "E-B",
                ),
            ),

        case_matrices=
            None,
    )


    index = _build_evidence_display_index(
        authority,
        {
            "E-A",
            "E-B",
        },
    )


    assert index["E-A"]["source"] == "A.pdf"
    assert index["E-A"]["page"] == "p.1"
    assert index["E-A"]["excerpt"] == "Exact text from A."

    assert index["E-B"]["source"] == "B.pdf"
    assert index["E-B"]["page"] == "p.7"
    assert index["E-B"]["excerpt"] == "Exact text from B."

    assert "WRONG" not in repr(index)
    assert "999" not in repr(index)


def test_exact_binding_reads_only_hash_verified_chunk_text():

    import hashlib
    from types import SimpleNamespace

    from ui.matter_analysis_ledger import (
        _build_evidence_display_index,
    )


    raw = (
        b"The employer received the exact "
        b"governed medical evidence."
    )

    digest = hashlib.sha256(
        raw
    ).hexdigest()


    class FakeStore:

        def read_blob(
            self,
            requested_digest,
        ):

            assert requested_digest == digest

            return raw


    evidence = SimpleNamespace(
        evidence_key="E-HASH",
        original_filename="medical.pdf",
        page_number=4,
        citation="medical.pdf, p.4",
        chunk_text_sha256=digest,
        chunk_text_byte_length=len(raw),
    )


    authority = SimpleNamespace(
        governed_issue_evidence_map=
            SimpleNamespace(
                bindings=(
                    SimpleNamespace(
                        evidence=evidence
                    ),
                )
            )
    )


    index = _build_evidence_display_index(
        authority,
        {
            "E-HASH"
        },
        store=FakeStore(),
    )


    assert (
        index["E-HASH"]["source"]
        == "medical.pdf"
    )

    assert (
        index["E-HASH"]["page"]
        == "p.4"
    )

    assert (
        "employer received"
        in index["E-HASH"]["excerpt"]
    )


def test_inconsistent_duplicate_governed_reference_fails_closed():

    from types import SimpleNamespace

    from ui.matter_analysis_ledger import (
        _build_evidence_display_index,
    )


    first = SimpleNamespace(
        evidence_key="E-CONFLICT",
        original_filename="one.pdf",
        page_number=1,
        chunk_text="first",
    )

    second = SimpleNamespace(
        evidence_key="E-CONFLICT",
        original_filename="two.pdf",
        page_number=2,
        chunk_text="second",
    )


    authority = SimpleNamespace(
        governed_issue_evidence_map=
            SimpleNamespace(
                bindings=(
                    SimpleNamespace(
                        evidence=first
                    ),
                    SimpleNamespace(
                        evidence=second
                    ),
                )
            )
    )


    index = _build_evidence_display_index(
        authority,
        {
            "E-CONFLICT"
        },
    )


    assert "E-CONFLICT" not in index



def test_pending_relationship_review_is_visually_prioritised():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_REVIEW_CLARITY_VERSION = '
        '"matter-analysis-ledger-review-clarity/1.0"'
        in source
    )

    assert (
        "PENDING RELATIONSHIP REVIEW"
        in source
    )

    assert (
        '"APPROVE THIS RELATIONSHIP"'
        in source
    )

    assert (
        '"REJECT THIS RELATIONSHIP"'
        in source
    )

    assert (
        "Optional reviewer note for this relationship"
        in source
    )


def test_pending_relationship_hides_second_proposal_form():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "pending_relationships = tuple("
        in source
    )

    assert (
        "if pending_relationships:"
        in source
    )

    assert (
        "New proposal controls are hidden"
        in source
    )

    assert (
        "elif len(evidence_options) >= 2:"
        in source
    )


def test_pending_relationship_uses_professional_evidence_display():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        '_show_selected_evidence(\n'
        '                                "Evidence A",'
        in source
    )

    assert (
        '_show_selected_evidence(\n'
        '                                "Evidence B",'
        in source
    )

    assert (
        "**Reason for proposed relationship**"
        in source
    )


def test_why_raw_evidence_keys_are_collapsed():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "technical evidence keys"
        in source
    )

    assert (
        "Technical evidence identifiers only."
        in source
    )

    assert (
        "expanded=False"
        in source
    )



def test_role_aware_selector_filters_from_element_role_fields():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src/ui/matter_analysis_ledger.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    assignment = next(
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "role_evidence_options"
            for target in node.targets
        )
    )

    assert isinstance(assignment.value, ast.Dict)

    expected = {
        "SUPPORTING": "supporting_evidence_keys",
        "ADVERSE": "adverse_evidence_keys",
        "CORROBORATIVE": "corroborative_evidence_keys",
        "CONFLICTING": "conflicting_evidence_keys",
        "NEUTRAL/CONTEXT": "neutral_evidence_keys",
    }

    actual = {}
    for key_node, value_node in zip(
        assignment.value.keys,
        assignment.value.values,
        strict=True,
    ):
        assert isinstance(key_node, ast.Constant)
        assert isinstance(key_node.value, str)
        assert isinstance(value_node, ast.Call)
        assert isinstance(value_node.func, ast.Name)
        assert value_node.func.id == "tuple"
        assert len(value_node.args) == 1
        attribute = value_node.args[0]
        assert isinstance(attribute, ast.Attribute)
        assert isinstance(attribute.value, ast.Name)
        assert attribute.value.id == "element"
        actual[key_node.value] = attribute.attr

    assert actual == expected

    helper_source = ast.get_source_segment(source, helper)
    assert "if keys" in helper_source
    assert "role_evidence_options.items()" in helper_source


def test_contradiction_defaults_evidence_b_to_conflicting_role():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src/ui/matter_analysis_ledger.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    helper_source = ast.get_source_segment(source, helper)

    assert "RelationshipType.CONTRADICTS.value" in helper_source
    assert '"CONFLICTING"' in helper_source
    assert '"ADVERSE"' in helper_source
    assert '"CORROBORATIVE"' in helper_source
    assert "preferred_right_role" in helper_source

    conditional = next(
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.If)
        and "RelationshipType.CONTRADICTS.value"
        in ast.get_source_segment(source, node.test)
    )

    contradiction_source = ast.get_source_segment(source, conditional)
    assert '"CONFLICTING"' in contradiction_source
    assert '"ADVERSE"' in contradiction_source


def test_role_aware_proposal_is_staged_streamlit_form_bound():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src/ui/matter_analysis_ledger.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    def call_name(call):
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            return call.func.value.id + "." + call.func.attr
        if isinstance(call.func, ast.Name):
            return call.func.id
        return None

    def label(call):
        if (
            call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        ):
            return call.args[0].value
        return None

    forms = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and call_name(node) == "_matter_entry_form"
    ]
    assert len(forms) == 3

    submits = [
        label(node)
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and call_name(node) == "_matter_form_submit_button"
    ]

    assert submits.count("SET RELATIONSHIP TYPE") == 1
    assert submits.count("SET EVIDENCE ROLES") == 1
    assert submits.count("PROPOSE RELATIONSHIP") == 1

    direct_buttons = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and call_name(node) == "st.button"
    ]
    assert direct_buttons == []


def test_role_selector_counts_and_preserves_multi_role_membership():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src/ui/matter_analysis_ledger.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_relationship_proposal_editor"
    )

    helper_source = ast.get_source_segment(source, helper)

    # Each governed role is projected independently from its own element field.
    # An evidence key may therefore legitimately occur in more than one role;
    # no set/dedup projection is introduced here.
    assert "role_evidence_options.items()" in helper_source
    assert "set(" not in helper_source
    assert "len(role_evidence_options[role])" in helper_source

    selectboxes = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "selectbox"
    ]

    labels = []
    for call in selectboxes:
        if (
            call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        ):
            labels.append(call.args[0].value)

    assert "Evidence A role" in labels
    assert "Evidence B role" in labels



def test_focused_workspace_shows_one_issue_and_one_element_at_a_time():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_FOCUSED_WORKSPACE_VERSION = '
        '"matter-analysis-ledger-focused-workspace/1.0"'
        in source
    )

    assert (
        '"Issue Review & Decisions"'
        in source
    )

    assert '"Issue to review"' in source
    assert '"Focus area"' in source

    assert (
        "for issue in (\n"
        "        selected_issue,\n"
        "    ):"
        in source
    )

    assert (
        "for element in (\n"
        "                selected_element,\n"
        "            ):"
        in source
    )


def test_focused_workspace_hides_proposal_editor_until_requested():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        '"+ Propose relationship"'
        in source
    )

    assert (
        "proposal_visibility_key"
        in source
    )

    assert (
        "if not st.toggle("
        in source
    )

    assert (
        "MAL1_ROLE_AWARE_SELECTOR_VERSION"
        in source
    )

    assert (
        "MAL1_REVIEW_CLARITY_VERSION"
        in source
    )



def test_terminal_relationship_history_is_compact_by_default():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_COMPACT_HISTORY_VERSION = '
        '"matter-analysis-ledger-compact-history/1.0"'
        in source
    )

    assert (
        "def _show_terminal_relationship_summary("
        in source
    )

    # Presentation label intentionally includes Markdown emphasis.
    assert (
        '"**Reason rejected**"'
        in source
    )

    assert '"View evidence details"' in source
    assert '"View relationship record"' in source

    assert (
        "relationship.state\n"
        "                                is not RelationshipReviewState.PROPOSED"
        in source
    )


def test_pending_relationship_controls_are_preserved():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert '"APPROVE THIS RELATIONSHIP"' in source
    assert '"REJECT THIS RELATIONSHIP"' in source
    assert "PENDING RELATIONSHIP REVIEW" in source


def test_compact_history_retains_complete_record_on_demand():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert "relationship.proposal_rationale" in source
    assert "relationship.left_evidence_key" in source
    assert "relationship.right_evidence_key" in source
    assert "relationship.actor" in source
    assert "relationship.created_at" in source
    assert "_show_selected_evidence(" in source



def test_findings_gaps_uncertainty_workspace_projects_existing_state():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_FINDINGS_GAPS_UNCERTAINTY_VERSION = '
        '"matter-analysis-ledger-findings-gaps-uncertainty/1.0"'
        in source
    )

    assert (
        '"### Findings, gaps & uncertainty"'
        in source
    )

    assert (
        '"**Current position:** "'
        in source
    )

    assert (
        '"Current governed explanation"'
        in source
    )

    assert (
        '"Supporting evidence"'
        in source
    )

    assert (
        '"Conflicting evidence"'
        in source
    )

    assert (
        '"Formal gaps"'
        in source
    )

    assert (
        '"Unresolved matters"'
        in source
    )


def test_findings_workspace_projects_reviewed_mal_relationships():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "approved_contradictions = tuple("
        in source
    )

    assert (
        "approved_corroborations = tuple("
        in source
    )

    assert (
        "rejected_relationships = tuple("
        in source
    )

    assert (
        "pending_relationship_summaries = tuple("
        in source
    )

    assert (
        "RelationshipReviewState.APPROVED"
        in source
    )

    assert (
        "RelationshipReviewState.REJECTED"
        in source
    )

    assert (
        "RelationshipType.CONTRADICTS"
        in source
    )

    assert (
        '"Approved contradictions: "'
        in source
    )


def test_findings_workspace_is_projection_only_and_removes_five_column_clutter():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "st.columns(\n"
        "                            2\n"
        "                        )"
        in source
    )

    assert (
        "c1, c2, c3, c4, c5"
        not in source
    )

    assert (
        "st.columns(\n"
        "                        5\n"
        "                    )"
        not in source
    )

    assert (
        "propose_relationship("
        in source
    )

    assert (
        "review_relationship("
        in source
    )

    # The new workspace itself introduces no persistence call.
    workspace_start = source.index(
        "# FINDINGS / GAPS / UNCERTAINTY"
    )

    workspace_end = source.index(
        "# WHY?",
        workspace_start,
    )

    workspace_source = source[
        workspace_start:
        workspace_end
    ]

    assert (
        "propose_relationship("
        not in workspace_source
    )

    assert (
        "review_relationship("
        not in workspace_source
    )

    assert (
        "openai"
        not in workspace_source.lower()
    )

    assert (
        "chromadb"
        not in workspace_source.lower()
    )



def test_analytical_change_proposal_requires_explicit_review():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_ANALYTICAL_CHANGE_PROPOSAL_VERSION = '
        '"matter-analysis-ledger-analytical-change-proposal/1.0"'
        in source
    )

    assert (
        '"### Analytical change proposal"'
        in source
    )

    assert (
        '"+ Propose analytical change"'
        in source
    )

    assert (
        '"PROPOSE ANALYTICAL CHANGE"'
        in source
    )

    assert (
        '"APPROVE CHANGE PROPOSAL"'
        in source
    )

    assert (
        '"REJECT CHANGE PROPOSAL"'
        in source
    )


def test_approved_change_proposal_does_not_silently_replace_authority():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "does not silently "
        in source
    )

    assert (
        "The current frozen analytical "
        in source
    )

    assert (
        "publish_governed_analytical_authority"
        not in source
    )

    assert (
        "activate_governed_analytical_authority"
        not in source
    )


def test_change_proposal_is_bound_to_reviewed_relationship_basis():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "basis_relationship_ids = tuple("
        in source
    )

    assert (
        "approved_contradictions"
        in source
    )

    assert (
        "approved_corroborations"
        in source
    )

    assert (
        "Resolve the pending evidence-relationship "
        in source
    )



def test_challenge_this_finding_is_read_only_adversarial_projection():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_CHALLENGE_FINDING_VERSION = '
        '"matter-analysis-ledger-challenge-finding/1.0"'
        in source
    )

    assert (
        '"### Challenge this finding"'
        in source
    )

    assert (
        '"+ Challenge this finding"'
        in source
    )

    assert (
        '"**Position being challenged:** "'
        in source
    )

    assert (
        '"**Questions the finding must withstand**"'
        in source
    )

    assert (
        '"Challenge signal: contrary or unresolved "'
        in source
    )


def test_challenge_view_projects_all_material_weakness_signals():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    challenge_start = source.index(
        "# CHALLENGE THIS FINDING"
    )

    challenge_end = source.index(
        "# ANALYTICAL CHANGE PROPOSAL",
        challenge_start,
    )

    challenge = source[
        challenge_start:
        challenge_end
    ]

    assert (
        "element.adverse_evidence_keys"
        in challenge
    )

    assert (
        "element.conflicting_evidence_keys"
        in challenge
    )

    assert (
        "approved_contradictions"
        in challenge
    )

    assert (
        "element.unresolved_matters"
        in challenge
    )

    assert (
        "element.evidential_gap_ids"
        in challenge
    )

    assert (
        "approved_corroborations"
        in challenge
    )


def test_challenge_view_cannot_mutate_analysis_or_review_history():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    challenge_start = source.index(
        "# CHALLENGE THIS FINDING"
    )

    challenge_end = source.index(
        "# ANALYTICAL CHANGE PROPOSAL",
        challenge_start,
    )

    challenge = source[
        challenge_start:
        challenge_end
    ].lower()

    for forbidden in (
        "propose_relationship(",
        "review_relationship(",
        "propose_analytical_change(",
        "review_analytical_change(",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
        "openai",
        "chromadb",
    ):

        assert (
            forbidden
            not in challenge
        )


def test_challenge_view_requires_no_new_persistent_model():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "ChallengeProposalEvent"
        not in source
    )

    assert (
        "ChallengeFindingEvent"
        not in source
    )

    assert (
        "challenge-events.jsonl"
        not in source
    )

    assert (
        '"Unresolved matters to test"'
        in source
    )

    assert (
        '"Formal gaps to test"'
        in source
    )



def test_work_product_authority_checker_is_structured_and_read_only():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_WORK_PRODUCT_AUTHORITY_CHECKER_VERSION = '
        '"matter-analysis-ledger-work-product-authority-checker/1.0"'
        in source
    )

    assert (
        '"### Work-product authority checker"'
        in source
    )

    assert (
        '"+ Check work product"'
        in source
    )

    assert (
        '"CHECK AGAINST CURRENT AUTHORITY"'
        in source
    )

    assert (
        '"ALIGNED WITH CURRENT AUTHORITY"'
        in source
    )

    assert (
        '"NOT AUTHORIZED BY CURRENT "'
        in source
    )


def test_work_product_checker_uses_frozen_status_confidence_and_evidence():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    start = source.index(
        "# WORK-PRODUCT AUTHORITY CHECKER"
    )

    end = source.index(
        "# ANALYTICAL CHANGE PROPOSAL",
        start,
    )

    checker = source[
        start:
        end
    ]

    assert (
        "element.analytical_status"
        in checker
    )

    assert (
        "element.analytical_confidence"
        in checker
    )

    assert (
        "element.supporting_evidence_keys"
        in checker
    )

    assert (
        "element.adverse_evidence_keys"
        in checker
    )

    assert (
        "element.conflicting_evidence_keys"
        in checker
    )

    assert (
        "approved_contradictions"
        in checker
    )

    assert (
        "element.unresolved_matters"
        in checker
    )


def test_work_product_checker_has_no_mutation_path():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    start = source.index(
        "# WORK-PRODUCT AUTHORITY CHECKER"
    )

    end = source.index(
        "# ANALYTICAL CHANGE PROPOSAL",
        start,
    )

    checker = source[
        start:
        end
    ].lower()

    for forbidden in (
        "propose_relationship(",
        "review_relationship(",
        "propose_analytical_change(",
        "review_analytical_change(",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
        "openai",
        "chromadb",
    ):

        assert forbidden not in checker
