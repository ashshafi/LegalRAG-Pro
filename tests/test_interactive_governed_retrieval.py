from pathlib import Path

def test_fast_path_precedes_document_complete_expansion():
    s = Path("src/evidence_answer/governed_retrieval.py").read_text(encoding="utf-8-sig")
    a = s.index("if interactive_semantic_only:")
    b = s.index("search_result = search_service(", a)
    block = s[a:b]
    assert "semantic_results=semantic_results" in block
    assert "search_result=None" in block
    assert "answer_results=semantic_results" in block

def test_legalrag_requests_fast_path_and_handles_no_complete_receipt():
    s = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "interactive_semantic_only=True" in s
    assert s.count("if governed_evidence.search_result is not None") == 2
    assert "else governed_evidence.semantic_receipt" in s

def test_complete_and_exhaustive_paths_remain():
    s = Path("src/evidence_answer/governed_retrieval.py").read_text(encoding="utf-8-sig")
    assert "mode=EvidenceSearchMode.DOCUMENT_COMPLETE" in s
    assert "mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE" in s
