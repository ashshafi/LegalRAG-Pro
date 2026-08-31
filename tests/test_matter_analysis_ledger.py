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

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'MAL1_ROLE_AWARE_SELECTOR_VERSION = '
        '"matter-analysis-ledger-role-aware-selector/1.0"'
        in source
    )

    assert (
        '"SUPPORTING":\n'
        '                            tuple(\n'
        '                                element.supporting_evidence_keys'
        in source
    )

    assert (
        '"CONFLICTING":\n'
        '                            tuple(\n'
        '                                element.conflicting_evidence_keys'
        in source
    )

    assert (
        '"ADVERSE":\n'
        '                            tuple(\n'
        '                                element.adverse_evidence_keys'
        in source
    )

    assert (
        '"CORROBORATIVE":\n'
        '                            tuple(\n'
        '                                element.corroborative_evidence_keys'
        in source
    )


def test_contradiction_defaults_evidence_b_to_conflicting_role():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        'preferred_right_role = (\n'
        '                                "CONFLICTING"'
        in source
    )

    assert (
        '"Evidence B role"'
        in source
    )

    assert (
        '"Evidence B is filtered to "'
        in source
    )


def test_role_aware_proposal_is_dynamic_not_streamlit_form_bound():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    proposal_start = source.index(
        "proposal_key = ("
    )

    submit_end = source.index(
        "if submitted:",
        proposal_start,
    )

    proposal_source = source[
        proposal_start:
        submit_end
    ]

    assert (
        "with st.form("
        not in proposal_source
    )

    assert (
        "st.form_submit_button("
        not in proposal_source
    )

    assert (
        'st.button(\n'
        '                                "PROPOSE RELATIONSHIP"'
        in proposal_source
    )


def test_role_selector_counts_and_preserves_multi_role_membership():

    source = open(
        "src/ui/matter_analysis_ledger.py",
        encoding="utf-8",
    ).read()

    assert (
        "role_evidence_options = {"
        in source
    )

    assert (
        "for role, keys\n"
        "                        in role_evidence_options.items()"
        in source
    )

    assert (
        "role_evidence_options[\n"
        "                                right_role"
        in source
    )

    # The filtering source is the element's role-specific tuples,
    # not a single inferred role assigned globally to the evidence key.
    assert (
        "element.conflicting_evidence_keys"
        in source
    )



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
