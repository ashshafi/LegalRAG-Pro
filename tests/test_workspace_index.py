from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

import workspace_index as wi


CASE_ID = "11111111-1111-4111-8111-111111111111"
ISSUE_ID = "22222222-2222-4222-8222-222222222222"
FINDING_ID = "33333333-3333-4333-8333-333333333333"
EVENT_ID = "44444444-4444-4444-8444-444444444444"
ASSERTION_ID = "55555555-5555-4555-8555-555555555555"
CONFLICT_ID = "66666666-6666-4666-8666-666666666666"
GAP_ID = "77777777-7777-4777-8777-777777777777"
RISK_ID = "88888888-8888-4888-8888-888888888888"
QUESTION_ID = "99999999-9999-4999-8999-999999999999"
STATEMENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CITATION_ID = "chunk-1"


def _status(value="supported"):
    return NS(raw_value=value, label=value.title(), explanation="Controlled explanation", qualification_code="Q")


def _projection(*, ambiguous_element=False, unknown_risk_conflict=False):
    statement = NS(
        report_statement_id=STATEMENT_ID,
        category="supported",
        text="Straße café a.*",
        evidence_keys=(CITATION_ID,),
        citation_ids=(CITATION_ID,),
    )
    element = NS(
        issue_analysis_id=ISSUE_ID,
        element_id="E-1",
        element_name="Element One",
        legal_question="Question?",
        analysis_status=_status(),
        analysis_confidence=_status("medium"),
        established_matters=(),
        supported_matters=(statement,),
        not_supported_matters=(),
        source_assertions=(),
        unresolved_matters=(),
        legal_significance="Significance",
        provisional_analysis="Provisional",
        linked_direct_finding_ids=(FINDING_ID,),
        linked_higher_order_finding_ids=(),
        linked_gap_ids=(GAP_ID,),
        linked_risk_ids=(RISK_ID,),
    )
    provenance = (NS(citation_ids=(CITATION_ID,)),)
    finding = NS(
        finding_id=FINDING_ID,
        finding_type="direct",
        scope="element",
        analytical_bases=("basis",),
        status=_status(),
        confidence=_status("medium"),
        summary="Finding summary",
        origin="direct",
        category="finding",
        issue_ids=(ISSUE_ID,),
        element_coordinates=((ISSUE_ID, "E-1"),),
        related_finding_ids=(),
        provenance=provenance,
        citation_ids=(CITATION_ID,),
        controlled_explanation="Explanation",
    )
    issue = NS(
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DEF-1",
        issue_definition_version="1.0",
        issue_name="Issue One",
        original_user_question="Original?",
        issue_summary="Issue summary",
        position_status=_status(),
        confidence=_status("medium"),
        material_finding_ids=(FINDING_ID,),
        conflict_ids=(CONFLICT_ID,),
        gap_ids=(GAP_ID,),
        risk_ids=(RISK_ID,),
        elements=(element,),
        direct_findings=(finding,),
        higher_order_findings=(),
    )
    issues = [issue]
    element_coords = [f"{ISSUE_ID}|E-1"]
    if ambiguous_element:
        issue2_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        element2 = NS(**{
            **element.__dict__,
            "issue_analysis_id": issue2_id,
            "established_matters": (),
            "supported_matters": (),
            "not_supported_matters": (),
            "source_assertions": (),
            "linked_direct_finding_ids": (),
            "linked_higher_order_finding_ids": (),
            "linked_gap_ids": (),
            "linked_risk_ids": (),
        })
        issue2 = NS(**{**issue.__dict__, "issue_analysis_id": issue2_id, "issue_name": "Issue Two", "elements": (element2,), "direct_findings": (), "material_finding_ids": (), "conflict_ids": (), "gap_ids": (), "risk_ids": ()})
        issues.append(issue2)
        element_coords.append(f"{issue2_id}|E-1")
    assertion = NS(
        event_id=EVENT_ID,
        assertion_id=ASSERTION_ID,
        description="Assertion",
        issue_analysis_id=ISSUE_ID,
        element_id="E-1",
        evidence_key=CITATION_ID,
        citation_id=CITATION_ID,
        source_proposition_index=0,
        occurrence_status=_status(),
        timing_status=_status("established"),
        confidence=_status("medium"),
        temporal_extent=None,
        extraction_basis="basis",
    )
    event = NS(
        event_id=EVENT_ID,
        description="Event description",
        normalized_event_core="event core",
        event_type="meeting",
        occurrence_status=_status(),
        timing_status=_status("established"),
        confidence=_status("medium"),
        canonical_temporal_extent=None,
        participants=("SMITH", "Smith"),
        evidence_keys=(CITATION_ID,),
        citation_ids=(CITATION_ID,),
        related_issue_ids=(ISSUE_ID,),
        related_element_coordinates=((ISSUE_ID, "E-1"),),
        assertions=(assertion,),
    )
    conflict = NS(
        conflict_id=CONFLICT_ID,
        conflict_type="conflict",
        scope="issue",
        subject="Subject",
        status=_status("disputed"),
        materiality=_status("medium"),
        side_a=provenance,
        side_b=(),
        related_issue_ids=(ISSUE_ID,),
        citation_ids=(CITATION_ID,),
    )
    gap = NS(
        gap_id=GAP_ID,
        gap_type="gap",
        scope="element",
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DEF-1",
        issue_definition_version="1.0",
        element_id="E-1",
        description="Gap",
        materiality=_status("medium"),
        unresolved_question="Unresolved?",
        provenance=provenance,
        citation_ids=(CITATION_ID,),
        related_finding_ids=(FINDING_ID,),
    )
    risk_conflict = "cccccccc-cccc-4ccc-8ccc-cccccccccccc" if unknown_risk_conflict else CONFLICT_ID
    risk = NS(
        risk_id=RISK_ID,
        risk_type="risk",
        scope="issue",
        materiality=_status("medium"),
        description="Risk",
        classification_explanation="Neutral",
        basis_finding_ids=(FINDING_ID,),
        conflict_ids=(risk_conflict,),
        gap_ids=(GAP_ID,),
        affected_issue_ids=(ISSUE_ID,),
        provenance=provenance,
        citation_ids=(CITATION_ID,),
    )
    question = NS(
        question_id=QUESTION_ID,
        question="Priority question",
        priority=_status("medium"),
        basis_type="gap",
        affected_issue_ids=(ISSUE_ID,),
        affected_element_ids=("E-1",),
        finding_ids=(FINDING_ID,),
        gap_ids=(GAP_ID,),
        conflict_ids=(CONFLICT_ID,),
        provenance=provenance,
        citation_ids=(CITATION_ID,),
    )
    citation = NS(
        citation_id=CITATION_ID,
        evidence_key=CITATION_ID,
        citation="Citation text",
        document_name="Doc.pdf",
        document_id="doc-1",
        page=2,
        chunk_id=CITATION_ID,
        date="2005-07-05",
        author="Dr Smith",
        parties=("CACI Ltd",),
        source_type="medical",
        evidence_status="primary",
        provenance_type="source",
        provenance_basis="exact",
        provenance_confidence="high",
        evidence_use_coordinates=((ISSUE_ID, "E-1", CITATION_ID),),
    )
    manifest = NS(
        manifest_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        ordered_issue_ids=tuple(item.issue_analysis_id for item in issues),
        ordered_element_coordinates=tuple(element_coords),
        ordered_finding_ids=(FINDING_ID,),
        ordered_event_ids=(EVENT_ID,),
        ordered_event_assertion_coordinates=(f"{EVENT_ID}|{ASSERTION_ID}",),
        ordered_conflict_ids=(CONFLICT_ID,),
        ordered_gap_ids=(GAP_ID,),
        ordered_risk_ids=(RISK_ID,),
        ordered_question_ids=(QUESTION_ID,),
        ordered_citation_ids=(CITATION_ID,),
    )
    return NS(
        report_projection_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        projection_payload_sha256="f" * 64,
        case_header=NS(case_id=CASE_ID, claimant="Claimant", respondent="CACI Ltd"),
        issues=tuple(issues),
        chronology=(event,),
        cross_issue_findings=(finding,),
        conflicts=(conflict,),
        gaps=(gap,),
        risks=(risk,),
        priority_questions=(question,),
        citations=(citation,),
        manifest=manifest,
    )


@pytest.fixture(autouse=True)
def _skip_m51_validation(monkeypatch):
    monkeypatch.setattr(wi, "validate_case_report_projection", lambda projection: None)


def test_identity_maps_order_backlinks_and_groups_are_exact():
    index = wi.build_workspace_index(_projection())
    assert index.version == wi.WORKSPACE_INDEX_VERSION
    assert tuple(key.primary_id for key in index.issue_keys) == (ISSUE_ID,)
    assert index.element_keys[0] == wi.WorkspaceObjectKey("element", ISSUE_ID, "E-1")
    assert index.statement_keys == (wi.WorkspaceObjectKey("statement", STATEMENT_ID),)
    assert index.finding_keys == (wi.WorkspaceObjectKey("finding", FINDING_ID),)
    citation_key = wi.WorkspaceObjectKey("citation", CITATION_ID)
    assert any(link.source.kind == "statement" for link in index.backlinks[citation_key])
    assert index.document_group_keys == (wi.DocumentGroupKey("Doc.pdf", "doc-1"),)
    assert index.recorded_name_values == (
        "Claimant",
        "CACI Ltd",
        "SMITH",
        "Smith",
        "Dr Smith",
    )
    assert index.recorded_names["SMITH"] != index.recorded_names["Smith"]


def test_cross_issue_finding_is_one_identity_and_forward_links_resolve():
    index = wi.build_workspace_index(_projection())
    assert len(index.findings_by_id) == 1
    finding_key = wi.WorkspaceObjectKey("finding", FINDING_ID)
    fields = {field for field, _target in index.outgoing[finding_key]}
    assert "FindingReport.issue_ids" in fields
    assert "FindingReport.element_coordinates" in fields
    assert "FindingReport.citation_ids" in fields


def test_unknown_exact_target_fails_closed():
    with pytest.raises(wi.WorkspaceIndexError, match="unknown workspace object"):
        wi.build_workspace_index(_projection(unknown_risk_conflict=True))


def test_priority_element_ambiguity_is_link_level_fail_closed():
    index = wi.build_workspace_index(_projection(ambiguous_element=True))
    assert index.unresolved_priority_element_ids[QUESTION_ID] == ("E-1",)
    question_key = wi.WorkspaceObjectKey("question", QUESTION_ID)
    assert not any(
        field == "PriorityQuestionReport.affected_element_ids"
        for field, _target in index.outgoing[question_key]
    )


@pytest.mark.parametrize(
    ("query", "candidates", "expected"),
    [
        ("STRASSE", ("Straße",), True),
        ("e\u0301", ("é",), True),
        ("cafe", ("café",), False),
        ("a.*", ("value a.* literal",), True),
        ("a.*", ("aaaa",), False),
        (" a  b ", ("a  b",), True),
        ("a b", ("a  b",), False),
        ("   ", ("anything",), True),
    ],
)
def test_literal_search_contract(query, candidates, expected):
    assert wi.literal_query_matches(query, candidates) is expected


def test_literal_filtering_can_preserve_input_order_without_scores():
    values = ("Zulu Smith", "alpha", "SMITH Beta")
    result = tuple(value for value in values if wi.literal_query_matches("smith", (value,)))
    assert result == ("Zulu Smith", "SMITH Beta")



def test_exact_same_projection_object_reuses_validated_workspace_index(monkeypatch):
    calls = {"count": 0}

    def validate(_projection):
        calls["count"] += 1

    monkeypatch.setattr(wi, "validate_case_report_projection", validate)
    wi._WORKSPACE_INDEX_CACHE.clear()
    wi._WORKSPACE_INDEX_CACHE_ORDER.clear()

    projection = _projection()
    first = wi.build_workspace_index(projection)
    second = wi.build_workspace_index(projection)

    assert second is first
    assert calls["count"] == 1


def test_distinct_projection_object_with_same_declared_identity_is_revalidated(monkeypatch):
    calls = {"count": 0}

    def validate(_projection):
        calls["count"] += 1

    monkeypatch.setattr(wi, "validate_case_report_projection", validate)
    wi._WORKSPACE_INDEX_CACHE.clear()
    wi._WORKSPACE_INDEX_CACHE_ORDER.clear()

    first_projection = _projection()
    second_projection = _projection()

    first = wi.build_workspace_index(first_projection)
    second = wi.build_workspace_index(second_projection)

    assert first is not second
    assert calls["count"] == 2
