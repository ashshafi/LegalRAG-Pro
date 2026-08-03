from __future__ import annotations

from pathlib import Path

import case_analysis


PACKAGE_ROOT = Path(case_analysis.__file__).resolve().parent


def test_m1_runtime_surface_contains_only_approved_foundation_modules():
    runtime_files = {
        path.name
        for path in PACKAGE_ROOT.glob("*.py")
        if path.name != "__pycache__"
    }
    assert runtime_files == {
        "__init__.py",
        "models.py",
        "validation.py",
        "serialization.py",
        "foundation.py",
    }


def test_case_analysis_has_no_retrieval_llm_or_ui_dependencies():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE_ROOT.glob("*.py"))
    lowered = combined.casefold()

    for prohibited in (
        "import chromadb",
        "from chromadb",
        "import openai",
        "from openai",
        "import streamlit",
        "from streamlit",
        "from retriever",
        "import retriever",
        "legal_analysis_retrieval_adapter",
    ):
        assert prohibited not in lowered


def test_m1_does_not_define_later_sprint_24_product_models():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE_ROOT.glob("*.py"))

    for future_type in (
        "CaseEvent",
        "IssueMatrix",
        "EvidenceMatrix",
        "CaseGap",
        "CaseConflict",
        "CaseDependency",
        "CaseAnalyticalSynthesis",
    ):
        assert f"class {future_type}" not in combined
