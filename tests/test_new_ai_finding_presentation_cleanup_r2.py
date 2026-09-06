from pathlib import Path
import ast
import hashlib

NEW_AI = Path("src/new_ai_finding.py")
CHAT = Path("src/ui/chat.py")


def _function_hash(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def test_key_findings_are_tightly_bounded():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    assert "give 3-5 concise bullets" in source
    assert "no more than two short sentences" in normalized
    assert "normally no more than about 45 words" in normalized
    assert "Do not reproduce the detailed evidence narrative" in normalized
    assert "principal source document/page reference(s)" in source


def test_detailed_analysis_and_new_finding_safeguards_remain():
    source = NEW_AI.read_text(encoding="utf-8-sig")
    normalized = " ".join(source.split())
    for required in (
        'Begin with the heading "## Key findings"',
        'Then use the heading "## Detailed analysis"',
        "requires professional review",
        "Do not say the Current Assessment has changed",
        "Do not expose authority hashes",
        "Do not invent missing text",
        "INTERMEDIATE MAP-PASS RULE:",
    ):
        assert required in source


def test_compact_provenance_heading_is_ascii_and_clean():
    source = CHAT.read_text(encoding="utf-8-sig")
    assert 'st.subheader("Sources & provenance")' in source
    assert 'st.subheader("?? Sources & provenance")' not in source
    assert "Full inspected-evidence, reference-resolution and technical provenance" in source


def test_frozen_audit_helpers_are_unchanged():
    assert _function_hash(CHAT, "_show_reference_findings") == "b4d4f25c50ab61cef75f90b8d5e75998ed2a1274c0d575d0e990b0cfb5c6fad7"
    assert _function_hash(CHAT, "_show_governed_answer_provenance") == "136d4ab3cb224f7daf67e6b6263d0046e896d025529c58208d0cd058d885a02c"
    assert _function_hash(CHAT, "_show_evidence_coverage") == "9bf705dfd37eb59a0e46d1b8308963ed01211458253bb10a6141ae65bfbad19e"
