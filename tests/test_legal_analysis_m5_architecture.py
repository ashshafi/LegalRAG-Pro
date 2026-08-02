from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "legal_analysis"


def test_m5_surface_is_only_three_additive_runtime_modules():
    for name in ("legal_analysis.py", "legal_analysis_rules.py", "legal_analysis_renderer.py"):
        assert (SRC / name).exists()


def test_m5_modules_do_not_import_retrieval_openai_chroma_or_streamlit():
    text = "\n".join(
        (SRC / name).read_text(encoding="utf-8")
        for name in ("legal_analysis.py", "legal_analysis_rules.py", "legal_analysis_renderer.py")
    ).casefold()
    forbidden = (
        "import retriever",
        "from retriever",
        "chromadb",
        "openai",
        "streamlit",
        "evidence_mapper",
        "legal_analysis_retrieval_adapter",
    )
    assert not any(item in text for item in forbidden)


def test_m5_does_not_reexport_through_frozen_init():
    init_text = (SRC / "__init__.py").read_text(encoding="utf-8")
    assert "StructuredLegalAnalysisRenderer" not in init_text
    assert "ElementLegalAnalysis" not in init_text
    assert "ElementAnalysisStatus" not in init_text


def test_m5_does_not_modify_m4_proposition_enum_location():
    m4 = (SRC / "evidence_assessment.py").read_text(encoding="utf-8")
    assert "class PropositionAssessmentStatus" in m4
    m5 = (SRC / "legal_analysis.py").read_text(encoding="utf-8")
    assert "class PropositionAssessmentStatus" not in m5
    assert "class ElementAnalysisStatus" in m5


def test_m5_renderer_contains_no_retrieval_method_calls():
    text = (SRC / "legal_analysis_renderer.py").read_text(encoding="utf-8").casefold()
    for forbidden in ("retrieve(", "query_collection", "embedding", "search_profile"):
        assert forbidden not in text
