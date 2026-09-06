from pathlib import Path
from types import SimpleNamespace

from governed_answer_output_schema import build_governed_answer_output_schema


def _prop(status, element, index, *evidence):
    return SimpleNamespace(
        status=status,
        evidence_keys=tuple(evidence),
        reference=SimpleNamespace(
            issue_analysis_id="issue-1",
            element_id=element,
            source_proposition_index=index,
        ),
    )


def test_schema_separates_statement_branches_by_frozen_status():
    context = SimpleNamespace(
        inspected_evidence_keys=("e1", "e2", "e3"),
        elements=(
            SimpleNamespace(
                propositions=(
                    _prop("supported", "el-a", 0, "e1"),
                    _prop("supported", "el-b", 2, "e2"),
                    _prop("unresolved", "el-a", 1, "e3"),
                    _prop("supported", "el-c", 4, "not-inspected"),
                )
            ),
        ),
    )

    schema = build_governed_answer_output_schema(context)
    branches = schema["properties"]["statements"]["items"]["anyOf"]

    by_status = {
        branch["properties"]["source_status"]["enum"][0]: branch
        for branch in branches
    }
    assert set(by_status) == {"supported", "unresolved"}

    supported_refs = by_status["supported"]["properties"]["source_proposition_refs"]["items"]["anyOf"]
    supported_elements = {
        ref["properties"]["element_id"]["enum"][0]: tuple(
            ref["properties"]["source_proposition_index"]["enum"]
        )
        for ref in supported_refs
    }
    assert supported_elements == {"el-a": (0,), "el-b": (2,)}
    assert "el-c" not in supported_elements

    unresolved_refs = by_status["unresolved"]["properties"]["source_proposition_refs"]["items"]["anyOf"]
    assert len(unresolved_refs) == 1
    assert unresolved_refs[0]["properties"]["element_id"]["enum"] == ["el-a"]
    assert unresolved_refs[0]["properties"]["source_proposition_index"]["enum"] == [1]


def test_legalrag_uses_status_aware_schema_and_keeps_fail_closed_validator():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "build_governed_answer_output_schema(analytical_context)" in source
    assert "validate_answer_statement_bindings(" in source
    assert 'reasoning={"effort": INTERACTIVE_REASONING_EFFORT}' in source
    assert "store=False" in source
