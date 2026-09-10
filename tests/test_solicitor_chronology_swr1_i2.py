from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ui import workspace


def _status(raw: str, label: str, explanation: str):
    return NS(raw_value=raw, label=label, explanation=explanation, qualification_code="TECH-CODE")


def _event():
    return NS(
        event_id="event-123",
        event_type="return_to_work",
        description="CACI HR confirms a seven-week phased return.",
        normalized_event_core="technical-core",
        canonical_temporal_extent=NS(display_text="16 May 2005"),
        participants=("Christine McCarroll", "Nigel Phillips", "Unum"),
        occurrence_status=_status("supported", "Supported", "The occurrence is supported by the frozen record."),
        timing_status=_status("supported", "Supported", "The timing is supported by the frozen record."),
        confidence=_status("medium", "Medium", "The analytical confidence is medium."),
        related_issue_ids=("issue-knowledge",),
        citation_ids=("citation-h6",),
        related_element_coordinates=(("issue-knowledge", "DA-KNOWLEDGE"),),
        assertions=(),
    )


def _index():
    return NS(
        issues_by_id={"issue-knowledge": NS(issue_name="Employer knowledge of disability")},
        citations_by_id={
            "citation-h6": NS(
                citation="Appendix H6 – Insurer-Supported Return to Work (RTW) Plan – May 2005.pdf, p.1",
                document_name="Appendix H6 – Insurer-Supported Return to Work (RTW) Plan – May 2005.pdf",
                page=1,
            )
        },
    )


def test_i2_human_helpers_use_only_frozen_display_values():
    event = _event()
    index = _index()
    assert workspace._chronology_time(event) == "16 May 2005"
    assert workspace._chronology_issue_names(index, event) == ("Employer knowledge of disability",)
    assert workspace._chronology_source_rows(index, event) == (("citation-h6", "Appendix H6 – Insurer-Supported Return to Work (RTW) Plan – May 2005.pdf, p.1"),)
    assert workspace._chronology_status_display(event.occurrence_status) == ("Supported", "The occurrence is supported by the frozen record.")


def test_i2_filter_labels_hide_raw_codes_but_preserve_values():
    event = _event()
    index = _index()
    assert workspace._chronology_status_filter_label((event,), "occurrence_status", "supported") == "Supported"
    assert workspace._chronology_status_filter_label((event,), "confidence", "medium") == "Medium"
    assert workspace._chronology_issue_filter_label(index, "issue-knowledge") == "Employer knowledge of disability"


def test_i2_uncertain_status_is_not_promoted_or_rewritten():
    uncertain = _status("uncertain", "Uncertain", "The frozen record does not establish the occurrence conclusively.")
    assert workspace._chronology_status_display(uncertain) == ("Uncertain", "The frozen record does not establish the occurrence conclusively.")


def test_i2_open_source_routes_to_existing_m7_exact_citation(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}
        def rerun(self):
            raise RuntimeError("rerun")
    fake = FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake)
    with pytest.raises(RuntimeError, match="rerun"):
        workspace._open_chronology_source("citation-h6")
    assert fake.session_state["m7_source_evidence_citation_id"] == "citation-h6"
    assert fake.session_state["m7_source_evidence_view"] is True
    assert fake.session_state["m6_workspace_view"] is None
    assert fake.session_state["m55_main_view"] == "assistant"


def test_i2_default_renderer_is_solicitor_facing_and_audit_retains_identity():
    source = Path("src/ui/workspace.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    render = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_render_chronology")
    segment = ast.get_source_segment(source, render)
    assert segment is not None
    audit_token = 'with st.expander("Technical / audit details", expanded=False):'
    assert audit_token in segment
    default, audit = segment.split(audit_token, 1)
    for required in ("**What the record shows**", "**People**", "**Relevant to**", "**Status**", "**Source**", "Occurrence: ", "Timing: ", "Assessment confidence: ", "Open source", "_render_chronology_task_creator("):
        assert required in default
    for technical in ('_text("Event ID"', '_text("Normalised event core"', '_text("Citation IDs"', '_text("Related issue IDs"', "Assertion ID:", '_text("Issue analysis ID"', '_text("Element ID"', '_text("Evidence key"', '_text("Citation ID"'):
        assert technical not in default
        assert technical in audit


def test_i2_filters_present_human_labels_without_changing_exact_filter_keys():
    source = Path("src/ui/workspace.py").read_text(encoding="utf-8-sig")
    for key in ("m6_chronology_event_types", "m6_chronology_participants", "m6_chronology_occurrence_statuses", "m6_chronology_timing_statuses", "m6_chronology_confidences", "m6_chronology_issue_ids"):
        assert f'key="{key}"' in source
    render_start = source.index("def _render_chronology(")
    render_end = source.index("\ndef ", render_start + 5)
    assert source[render_start:render_end].count("format_func=") >= 5


def test_i2_workspace_has_no_direct_source_pdf_retrieval_or_ai_dependency():
    source = Path("src/ui/workspace.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"openai", "chromadb", "document_manager", "retriever", "source_evidence"}
    assert not {name for name in imported if name.split(".", 1)[0] in forbidden}
    assert 'st.session_state["m7_source_evidence_citation_id"]' in source
    assert 'st.session_state["m7_source_evidence_view"] = True' in source
