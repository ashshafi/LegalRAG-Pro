from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from legal_issue_dashboard import (
    LegalIssueDashboardError,
    build_legal_issue_dashboard,
)


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
APP = SRC / "app.py"
SIDEBAR = SRC / "ui" / "sidebar.py"
CORE = SRC / "legal_issue_dashboard.py"
UI = SRC / "ui" / "legal_issue_dashboard.py"

CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
OTHER_CASE_ID = "9081166d-9889-40bb-8add-5d0893037ff0"


class Value:
    def __init__(self, value: str):
        self.value = value


def _statement(text: str):
    return SimpleNamespace(
        text=text,
        evidence_keys=("evidence-key-1",),
        citations=("Example.pdf, p.1",),
    )


def _gap(element_id: str):
    return SimpleNamespace(
        gap_id="gap-" + element_id,
        description="Missing direct evidence for " + element_id,
        related_element_id=element_id,
        materiality=Value("medium"),
        reason="The frozen record does not contain the required direct record.",
        suggested_evidence_target="Direct contemporaneous record",
    )


def _dispute(element_id: str):
    return SimpleNamespace(
        disputed_matter_id="dispute-" + element_id,
        proposition="Disputed proposition for " + element_id,
        claimant_position="Claimant position",
        respondent_position="Respondent position",
    )


def _matrix_element(
    element_id: str,
    *,
    supporting=(),
    adverse=(),
    corroborative=(),
    neutral=(),
    conflicting=(),
):
    return SimpleNamespace(
        element_id=element_id,
        supporting_evidence_keys=tuple(supporting),
        adverse_evidence_keys=tuple(adverse),
        corroborative_evidence_keys=tuple(corroborative),
        neutral_evidence_keys=tuple(neutral),
        conflicting_evidence_keys=tuple(conflicting),
    )


def _element(
    element_id: str,
    *,
    status: str,
    confidence: str,
    roles: tuple[str, ...],
):
    analysis_element = SimpleNamespace(
        element_id=element_id,
        element_name="Element " + element_id,
    )
    legal_element = SimpleNamespace(
        element_id=element_id,
        legal_question="Question " + element_id,
        current_evidential_position="Frozen position " + element_id,
        provisional_status=Value(status),
        analysis_confidence=Value(confidence),
        established_matters=(_statement("Established " + element_id),),
        supported_matters=(_statement("Supported " + element_id),),
        not_supported_matters=(_statement("Not supported " + element_id),),
        source_assertions=(_statement("Source assertion " + element_id),),
        adverse_material=(_statement("Adverse " + element_id),),
        corroborative_material=(_statement("Corroborative " + element_id),),
        contextual_material=(_statement("Context " + element_id),),
        conflicting_material=(_statement("Conflict " + element_id),),
        disputed_matters=(_dispute(element_id),),
        legal_significance="Legal significance " + element_id,
        limitations=("Limitation " + element_id,),
        unresolved_matters=("Unresolved " + element_id,),
        evidential_gaps=(_gap(element_id),),
        provisional_analysis="Provisional analysis " + element_id,
    )

    role_keys = {
        "supporting": [],
        "adverse": [],
        "corroborative": [],
        "neutral": [],
        "conflicting": [],
    }
    assessments = []
    for index, role in enumerate(roles, start=1):
        evidence_key = f"{element_id}-{role}-{index}"
        assessments.append(
            SimpleNamespace(
                analytical_role=Value(role),
                evidence_key=evidence_key,
            )
        )
        role_keys[role].append(evidence_key)

    m4_element = SimpleNamespace(
        element_id=element_id,
        evidence_assessments=tuple(assessments),
    )
    matrix_element = _matrix_element(
        element_id,
        supporting=role_keys["supporting"],
        adverse=role_keys["adverse"],
        corroborative=role_keys["corroborative"],
        neutral=role_keys["neutral"],
        conflicting=role_keys["conflicting"],
    )
    return analysis_element, legal_element, m4_element, matrix_element


def _result(
    issue_id: str,
    issue_name: str,
    index: int,
    *,
    case_id: str = CASE_ID,
    status: str = "partially_supported",
    confidence: str = "medium",
    roles: tuple[str, ...] = ("supporting", "adverse", "neutral"),
):
    element_id = issue_id.replace("-001", "-ELEMENT")
    analysis_element, legal_element, m4_element, matrix_element = _element(
        element_id,
        status=status,
        confidence=confidence,
        roles=roles,
    )
    assessed_analysis = SimpleNamespace(
        case_id=case_id,
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        issue_name=issue_name,
        user_question="Question for " + issue_id,
        elements=(analysis_element,),
    )
    synthesis = SimpleNamespace(
        well_supported_elements=(),
        partially_supported_elements=(element_id,) if status == "partially_supported" else (),
        disputed_elements=(element_id,) if status == "disputed" else (),
        insufficiently_evidenced_elements=(
            (element_id,) if status == "insufficiently_evidenced" else ()
        ),
        unresolved_elements=(element_id,) if status == "unresolved" else (),
        summary="Frozen synthesis " + issue_id,
    )
    result = SimpleNamespace(
        case_id=case_id,
        issue_analysis_id=f"00000000-0000-4000-8000-{index:012d}",
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        assessment_result=SimpleNamespace(
            assessed_analysis=assessed_analysis,
            element_assessments=(m4_element,),
        ),
        element_analyses=(legal_element,),
        issue_synthesis=synthesis,
        overall_limitations=("Overall limitation " + issue_id,),
    )
    matrix_issue = SimpleNamespace(
        issue_analysis_id=result.issue_analysis_id,
        issue_definition_id=issue_id,
        issue_definition_version="1.0",
        element_records=(matrix_element,),
    )
    return result, matrix_issue


def _authority(pairs, *, case_id: str = CASE_ID):
    authority_id = "sha256:" + "a" * 64
    results = tuple(pair[0] for pair in pairs)
    matrix_issues = tuple(pair[1] for pair in pairs)
    return SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=case_id,
            authority_id=authority_id,
        ),
        active_pointer=SimpleNamespace(
            case_id=case_id,
            authority_id=authority_id,
            activation_id="sha256:" + "b" * 64,
        ),
        structured_legal_analysis_results=results,
        case_matrices=SimpleNamespace(
            case_id=case_id,
            issue_matrix=matrix_issues,
        ),
    )


def _four_pairs():
    return (
        _result("DA-001", "Discrimination arising from disability", 1),
        _result("EK-001", "Employer knowledge of disability", 2),
        _result(
            "LIM-001",
            "Limitation, continuing act and just and equitable extension",
            3,
        ),
        _result("RA-001", "Reasonable adjustments", 4),
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.add(node.func.attr)
    return result


def test_four_governed_issues_project_exactly():
    dashboard = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority(_four_pairs()),
    )
    assert dashboard.case_id == CASE_ID
    assert dashboard.schema_version == "legal-issue-dashboard/1.2"
    assert [issue.issue_definition_id for issue in dashboard.issues] == [
        "DA-001",
        "EK-001",
        "LIM-001",
        "RA-001",
    ]
    assert [issue.issue_name for issue in dashboard.issues] == [
        "Discrimination arising from disability",
        "Employer knowledge of disability",
        "Limitation, continuing act and just and equitable extension",
        "Reasonable adjustments",
    ]


def test_cross_case_authority_fails_closed():
    with pytest.raises(LegalIssueDashboardError, match="active case"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=_authority(_four_pairs(), case_id=OTHER_CASE_ID),
        )


def test_cross_case_result_fails_closed():
    pairs = list(_four_pairs())
    pairs[0] = _result(
        "DA-001",
        "Discrimination arising from disability",
        1,
        case_id=OTHER_CASE_ID,
    )
    with pytest.raises(LegalIssueDashboardError, match="cross-case"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=_authority(pairs),
        )


def test_duplicate_governed_issue_identity_fails_closed():
    pairs = list(_four_pairs())
    pairs[1] = _result("DA-001", "Duplicate", 99)
    with pytest.raises(LegalIssueDashboardError, match="Duplicate governed issue"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=_authority(pairs),
        )


def test_matrix_issue_order_or_identity_mismatch_fails_closed():
    pairs = list(_four_pairs())
    authority = _authority(pairs)
    authority.case_matrices.issue_matrix = tuple(
        reversed(authority.case_matrices.issue_matrix)
    )
    with pytest.raises(LegalIssueDashboardError, match="identity or order"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=authority,
        )


def test_unique_role_counts_come_from_case_matrix_keys():
    pair = _result(
        "EK-001",
        "Employer knowledge of disability",
        2,
        roles=("supporting", "supporting", "adverse", "conflicting", "neutral"),
    )
    issue = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority((pair,)),
    ).issues[0]

    assert issue.synthesis_counts.partially_supported == 1
    assert issue.confidence_counts.medium == 1
    assert issue.evidence_counts.supporting == 2
    assert issue.evidence_counts.adverse == 1
    assert issue.evidence_counts.conflicting == 1
    assert issue.evidence_counts.neutral == 1
    assert issue.evidence_counts.corroborative == 0
    assert issue.evidence_counts.distinct_any_role == 5
    assert issue.evidential_gap_count == 1
    assert issue.unresolved_matter_count == 1


def test_issue_counts_deduplicate_same_evidence_key_across_elements():
    result, matrix_issue = _result(
        "EK-001",
        "Employer knowledge of disability",
        2,
        roles=("supporting",),
    )

    first_analysis = result.assessment_result.assessed_analysis.elements[0]
    first_legal = result.element_analyses[0]
    first_m4 = result.assessment_result.element_assessments[0]
    first_matrix = matrix_issue.element_records[0]

    second_id = "EK-SECOND"
    second_analysis = SimpleNamespace(
        element_id=second_id,
        element_name="Second element",
    )
    second_legal = SimpleNamespace(
        **{
            **first_legal.__dict__,
            "element_id": second_id,
            "legal_question": "Second question",
        }
    )
    second_m4 = SimpleNamespace(
        element_id=second_id,
        evidence_assessments=(
            SimpleNamespace(
                analytical_role=Value("supporting"),
                evidence_key=first_matrix.supporting_evidence_keys[0],
            ),
        ),
    )
    second_matrix = _matrix_element(
        second_id,
        supporting=(first_matrix.supporting_evidence_keys[0],),
    )

    result.assessment_result.assessed_analysis.elements = (
        first_analysis,
        second_analysis,
    )
    result.element_analyses = (first_legal, second_legal)
    result.assessment_result.element_assessments = (first_m4, second_m4)
    result.issue_synthesis.partially_supported_elements = (
        first_analysis.element_id,
        second_id,
    )
    matrix_issue.element_records = (first_matrix, second_matrix)

    issue = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority(((result, matrix_issue),)),
    ).issues[0]

    assert len(issue.elements) == 2
    assert issue.elements[0].evidence_counts.supporting == 1
    assert issue.elements[1].evidence_counts.supporting == 1
    assert issue.evidence_counts.supporting == 1
    assert issue.evidence_counts.distinct_any_role == 1


def test_role_specific_unique_counts_must_not_be_summed_as_distinct_total():
    result, matrix_issue = _result(
        "RA-001",
        "Reasonable adjustments",
        4,
        roles=("supporting", "adverse"),
    )
    element = matrix_issue.element_records[0]
    shared = "shared-evidence-key"
    element.supporting_evidence_keys = (shared,)
    element.adverse_evidence_keys = (shared,)

    issue = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority(((result, matrix_issue),)),
    ).issues[0]

    assert issue.evidence_counts.supporting == 1
    assert issue.evidence_counts.adverse == 1
    assert issue.evidence_counts.role_memberships == 2
    assert issue.evidence_counts.distinct_any_role == 1


def test_duplicate_matrix_key_within_element_fails_closed():
    pair = _result(
        "EK-001",
        "Employer knowledge of disability",
        2,
        roles=("supporting",),
    )
    pair[1].element_records[0].supporting_evidence_keys = ("dup", "dup")
    with pytest.raises(LegalIssueDashboardError, match="Duplicate supporting"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=_authority((pair,)),
        )


def test_frozen_text_and_traceability_are_copied_without_rewording():
    issue = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority((_four_pairs()[3],)),
    ).issues[0]
    element = issue.elements[0]

    assert element.current_evidential_position == "Frozen position RA-ELEMENT"
    assert element.supported_matters[0].text == "Supported RA-ELEMENT"
    assert element.supported_matters[0].evidence_keys == ("evidence-key-1",)
    assert element.supported_matters[0].citations == ("Example.pdf, p.1",)
    assert element.adverse_material[0].text == "Adverse RA-ELEMENT"
    assert element.conflicting_material[0].text == "Conflict RA-ELEMENT"
    assert element.limitations == ("Limitation RA-ELEMENT",)
    assert element.unresolved_matters == ("Unresolved RA-ELEMENT",)
    assert element.provisional_analysis == "Provisional analysis RA-ELEMENT"


def test_element_order_mismatch_fails_closed():
    pair = _result("EK-001", "Employer knowledge of disability", 2)
    pair[1].element_records = (
        _matrix_element("WRONG-ELEMENT"),
    )
    with pytest.raises(LegalIssueDashboardError, match="order/identity"):
        build_legal_issue_dashboard(
            active_case_id=CASE_ID,
            authority=_authority((pair,)),
        )


def test_core_has_no_streamlit_retrieval_openai_chroma_or_writer_dependencies():
    roots = _imports(CORE)
    assert roots.isdisjoint(
        {
            "streamlit",
            "openai",
            "chromadb",
            "retriever",
            "evidence_search",
            "evidence_retrieval",
        }
    )
    assert _calls(CORE).isdisjoint(
        {
            "publish_governed_analytical_authority",
            "activate_governed_analytical_authority",
            "build_case_matrices",
            "build_governed_issue_evidence_map",
            "build_governed_evidential_analysis",
        }
    )


def test_ui_uses_only_read_only_authority_provider_and_no_unsafe_rendering():
    roots = _imports(UI)

    assert "streamlit" in roots
    assert "governed_analytical_authority" in roots

    assert roots.isdisjoint(
        {
            "openai",
            "chromadb",
            "retriever",
            "evidence_search",
        }
    )

    source = UI.read_text(
        encoding="utf-8"
    )

    assert (
        "load_active_governed_analytical_authority"
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

    assert "unsafe_allow_html" not in source
    assert ".markdown(" not in source
    assert ".html(" not in source
    assert ".download_button(" not in source

    assert 'Evidence considered' in source
    assert 'Evidence against / qualifying' in source
    assert '"Supporting uses"' not in source




def test_app_route_order_is_unchanged_u8_dashboard_m7_workspace_reports():
    source = APP.read_text(encoding="utf-8")

    u8 = source.index(
        'if st.session_state.get("u8_evidence_inspection_view", False):'
    )
    dashboard = source.index(
        'elif st.session_state.get("ppr3_legal_issue_dashboard_view", False):'
    )
    m7 = source.index(
        'elif st.session_state.get("m7_source_evidence_view", False):'
    )
    workspace = source.index(
        'elif st.session_state.get("m6_workspace_view")'
    )
    reports = source.index(
        'elif st.session_state.get("m55_main_view", "assistant") == "reports"'
    )

    assert u8 < dashboard < m7 < workspace < reports
    assert "show_swd1_issue_workspace(active_case_id)" in source
    assert "show_legal_issue_dashboard(active_case_id)" not in source


def test_sidebar_contract_is_unchanged():
    tree = ast.parse(SIDEBAR.read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar"
    ]
    assert len(functions) == 1
    function = functions[0]
    assert [arg.arg for arg in function.args.args] == ["active_case_id"]
    assert [arg.arg for arg in function.args.kwonlyargs] == ["reports_available"]

    source = SIDEBAR.read_text(encoding="utf-8")
    assert "\u2696\ufe0f Legal Issues" in source
    assert 'st.session_state["ppr3_legal_issue_dashboard_view"] = True' in source

def test_dashboard_metric_layout_uses_rows_of_at_most_two_columns():
    source = UI.read_text(
        encoding="utf-8"
    )

    assert "def _show_metric_rows(" in source
    assert "range(0, len(metrics), 2)" in source
    assert "st.columns(len(row))" in source

    assert "st.columns(5)" not in source
    assert "st.columns(3)" not in source

    assert '"Disputed elements"' in source
    assert '"Partially supported"' in source
    assert 'Evidence considered' in source
    assert 'Evidence against / qualifying' in source




def test_dashboard_element_preserves_exact_frozen_case_matrix_role_key_tuples():
    pair = _result(
        "EK-001",
        "Employer knowledge of disability",
        2,
        roles=("supporting", "supporting", "adverse", "corroborative", "neutral", "conflicting"),
    )
    matrix_element = pair[1].element_records[0]
    element = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority((pair,)),
    ).issues[0].elements[0]

    assert element.supporting_evidence_keys == matrix_element.supporting_evidence_keys
    assert element.adverse_evidence_keys == matrix_element.adverse_evidence_keys
    assert element.corroborative_evidence_keys == matrix_element.corroborative_evidence_keys
    assert element.neutral_evidence_keys == matrix_element.neutral_evidence_keys
    assert element.conflicting_evidence_keys == matrix_element.conflicting_evidence_keys


def test_same_evidence_identity_is_preserved_across_multiple_projected_roles():
    result, matrix_issue = _result(
        "RA-001",
        "Reasonable adjustments",
        4,
        roles=("supporting", "adverse"),
    )
    shared = "shared-evidence-key"
    matrix_issue.element_records[0].supporting_evidence_keys = (shared,)
    matrix_issue.element_records[0].adverse_evidence_keys = (shared,)

    element = build_legal_issue_dashboard(
        active_case_id=CASE_ID,
        authority=_authority(((result, matrix_issue),)),
    ).issues[0].elements[0]

    assert element.supporting_evidence_keys == (shared,)
    assert element.adverse_evidence_keys == (shared,)



def test_dashboard_ui_is_summary_only_and_defers_detailed_review():

    source = UI.read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def show_legal_issue_dashboard("
    )

    end = source.index(
        '__all__ =',
        start,
    )

    rendered = source[
        start:
        end
    ]

    assert (
        'LEGAL_ISSUE_SUMMARY_UI_VERSION = '
        '"legal-issue-summary-ui/1.0"'
        in source
    )

    assert (
        'Choose a legal issue to see the current assessment, evidence and any action that needs your attention.'
        in rendered
    )

    assert (
        'Open Issue assessment above'
        in rendered
    )

    assert (
        "_show_element(element)"
        not in rendered
    )

    assert (
        'Audit trail'
        in rendered
    )



def test_compact_summary_hides_long_frozen_text_by_default():

    source = UI.read_text(
        encoding="utf-8"
    )

    assert (
        'LEGAL_ISSUE_COMPACT_SUMMARY_VERSION = '
        '"legal-issue-compact-summary/1.0"'
        in source
    )

    assert '"About this assessment"' in source
    assert "issue.issue_summary" in source
    assert "The concise metrics below are the normal working view." in source


# ---------------------------------------------------------------------------
# SWD1-I3 focused projection tests
# ---------------------------------------------------------------------------

def test_swd1_i3_projects_frozen_evidence_assessment_without_reordering():
    from types import SimpleNamespace as NS

    from legal_issue_dashboard import build_swd1_evidence_items

    p1 = NS(
        text="The direct record documents a relevant communication.",
        status="established_by_current_evidence",
        confidence="high",
        rationale="Direct record only.",
        evidence_keys=("e1",),
    )
    p2 = NS(
        text="A second proposition is supported.",
        status="supported_but_not_established",
        confidence="medium",
        rationale="Supported but not established.",
        evidence_keys=("e2",),
    )

    def raw_item(key, role, citation, status):
        evidence = NS(
            chunk_id=key,
            citation=citation,
            document_name=citation.split(",")[0],
            page=1,
            evidence_status=status,
            provenance_type="employer_record",
            source_type="employer_record",
            summary="Relevant source passage.",
        )
        return NS(
            analytical_role=role,
            assessment_confidence="medium",
            assessment_rationale="Frozen rationale " + key,
            mapping=NS(evidence=evidence),
        )

    element = NS(
        element_id="EK-X",
        assessed_propositions=(p1, p2),
        evidence_assessments=(
            raw_item("e1", "supporting", "Doc A, p.1", "employer_evidence"),
            raw_item("e2", "adverse", "Doc B, p.1", "respondent_evidence"),
        ),
    )
    result = NS(
        issue_analysis_id="issue-1",
        assessment_result=NS(element_assessments=(element,)),
    )
    authority = NS(structured_legal_analysis_results=(result,))

    projected = build_swd1_evidence_items(
        authority=authority,
        issue_analysis_id="issue-1",
        element_id="EK-X",
    )

    assert tuple(item.evidence_key for item in projected) == ("e1", "e2")
    assert tuple(item.analytical_role for item in projected) == (
        "supporting",
        "adverse",
    )
    assert projected[0].assessment_rationale == "Frozen rationale e1"
    assert projected[0].citation == "Doc A, p.1"
    assert projected[0].proposition_links[0].text == p1.text
    assert projected[1].proposition_links[0].text == p2.text


def test_swd1_i3_projection_does_not_create_priority_or_merits_fields():
    import dataclasses

    from legal_issue_dashboard import DashboardEvidenceItem

    names = {field.name for field in dataclasses.fields(DashboardEvidenceItem)}

    assert "priority" not in names
    assert "rank" not in names
    assert "score" not in names
    assert "merits" not in names
    assert {
        "analytical_role",
        "assessment_confidence",
        "assessment_rationale",
        "citation",
        "evidence_status",
        "summary",
        "proposition_links",
    } <= names


def test_swd1_i3_projection_returns_empty_when_legacy_result_has_no_assessment():
    from types import SimpleNamespace as NS

    from legal_issue_dashboard import build_swd1_evidence_items

    authority = NS(
        structured_legal_analysis_results=(
            NS(issue_analysis_id="issue-1", assessment_result=None),
        )
    )

    assert build_swd1_evidence_items(
        authority=authority,
        issue_analysis_id="issue-1",
        element_id="EK-X",
    ) == ()
