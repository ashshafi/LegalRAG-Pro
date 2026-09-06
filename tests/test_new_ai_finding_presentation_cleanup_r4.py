from pathlib import Path

NEW_AI = Path("src/new_ai_finding.py")


def test_final_key_findings_contract_is_complete():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    for required in (
        'Begin with the heading "## Key findings"',
        "give 3-5 concise bullets",
        "no more than two short sentences",
        "normally no more than about 45 words",
        "principal source document/page reference(s)",
        "Do not reproduce the detailed evidence narrative",
        'Then use the heading "## Detailed analysis"',
    ):
        assert required in normalized


def test_map_pass_and_governance_safeguards_are_preserved():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    for required in (
        "INTERMEDIATE MAP-PASS RULE:",
        "Follow the map-pass output format",
        "Preserve every material source/page finding",
        "requires professional review",
        "Do not say the Current Assessment has changed",
        "Do not expose authority hashes",
        "Do not invent missing text",
    ):
        assert required in source
