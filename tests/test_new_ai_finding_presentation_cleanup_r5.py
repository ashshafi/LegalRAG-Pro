from pathlib import Path

NEW_AI = Path("src/new_ai_finding.py")
CHAT = Path("src/ui/chat.py")


def test_compactness_contract_is_present_after_whitespace_normalization():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    assert "give 3-5 concise bullets" in normalized
    assert "no more than two short sentences" in normalized
    assert "normally no more than about 45 words" in normalized
    assert "Do not reproduce the detailed evidence narrative" in normalized
    assert 'Then use the heading "## Detailed analysis"' in normalized


def test_wrapper_headings_are_ascii_clean():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    assert "FINAL SOLICITOR-FACING OUTPUT ORDER - MANDATORY:" in source
    assert "NEW AI FINDING - SOURCE COMPARISON" in source
    assert "FINAL SOLICITOR-FACING OUTPUT ORDER ? MANDATORY:" not in source
    assert "NEW AI FINDING ? SOURCE COMPARISON" not in source


def test_compact_provenance_heading_remains_ascii_clean():
    source = CHAT.read_text(encoding="utf-8-sig")
    assert 'st.subheader("Sources & provenance")' in source
    assert 'st.subheader("?? Sources & provenance")' not in source
