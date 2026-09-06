from pathlib import Path

NEW_AI = Path("src/new_ai_finding.py")


def test_compact_key_findings_contract_is_complete_and_ascii_stable():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    assert "give 3-5 concise bullets" in source
    assert "no more than two short sentences" in normalized
    assert "normally no more than about 45 words" in normalized
    assert "principal source document/page reference(s)" in source
    assert "Do not reproduce the detailed evidence narrative" in normalized
    assert "absent from the detailed analysis" in source


def test_final_and_map_pass_boundaries_remain():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    assert 'Begin with the heading "## Key findings"' in source
    assert 'Then use the heading "## Detailed analysis"' in source
    assert "INTERMEDIATE MAP-PASS RULE:" in source
    assert "Follow the map-pass output format" in source
    assert "requires professional review" in source
    assert "Do not say the Current Assessment has changed" in source
