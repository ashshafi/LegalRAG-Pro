from pathlib import Path

from new_ai_finding import wrap_source_comparison_new_ai_finding_prompt


def test_final_source_comparison_requires_key_findings_before_detail():
    prompt = wrap_source_comparison_new_ai_finding_prompt(
        base_prompt="DIRECT GOVERNED COMPLETE EVIDENCE",
        question="Compare paragraphs 27-30.",
    )
    normalized = " ".join(prompt.split())
    assert "FINAL SOLICITOR-FACING OUTPUT ORDER - MANDATORY:" in prompt
    assert 'Begin with the heading "## Key findings"' in prompt
    assert 'Then use the heading "## Detailed analysis"' in prompt
    assert "give 3-5 concise bullets" in normalized
    assert "no more than two short sentences" in normalized
    assert "normally no more than about 45 words" in normalized
    assert "principal source document/page reference(s)" in normalized
    assert prompt.index("## Key findings") < prompt.index("## Detailed analysis")
    assert "requires professional review" in prompt
    assert "Do not say the Current Assessment has changed" in prompt


def test_bounded_map_pass_does_not_request_final_executive_summary():
    prompt = wrap_source_comparison_new_ai_finding_prompt(
        base_prompt=(
            "LEGALRAG GOVERNED LARGE-MATTER MAP PASS\n"
            "FINDING | evidence_key=<key> | file=<file> | page=<page>"
        ),
        question="Compare paragraphs 27-30.",
    )
    assert "INTERMEDIATE MAP-PASS RULE:" in prompt
    assert "Follow the map-pass output format" in prompt
    assert "Do not write\nthe executive summary" in prompt
    assert "FINAL SOLICITOR-FACING OUTPUT ORDER ? MANDATORY:" not in prompt
    assert "Preserve every material source/page finding" in prompt


def test_final_wrapper_retains_existing_source_comparison_safeguards():
    prompt = wrap_source_comparison_new_ai_finding_prompt(
        base_prompt="GOVERNED COMPLETE EVIDENCE",
        question="Compare paragraphs 27-30.",
    )
    for required in (
        "NOT the Current Assessment",
        "requires professional review",
        "name the source document and page",
        "Distinguish contemporaneous primary evidence",
        "do not overstate what it proves",
        "Do not expose authority hashes",
        "Do not invent missing text",
    ):
        assert required in prompt


def test_bounded_and_legalrag_routing_files_are_not_part_of_this_slice():
    # This test documents the intended boundary; the PowerShell gate additionally
    # hashes these files before and after execution.
    source = Path("src/new_ai_finding.py").read_text(encoding="utf-8-sig")
    assert "LEGALRAG GOVERNED LARGE-MATTER MAP PASS" in source
    assert "FINAL SOLICITOR-FACING OUTPUT ORDER" in source
