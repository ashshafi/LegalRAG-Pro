from __future__ import annotations

import ast
from pathlib import Path

M3 = Path(__file__).parents[1] / "src" / "case_analysis" / "m3"


def test_m3_has_only_the_seven_approved_runtime_modules():
    assert {item.name for item in M3.glob("*.py")} == {
        "models.py",
        "date_parsing.py",
        "event_extraction.py",
        "event_identity.py",
        "chronology.py",
        "chronology_validation.py",
        "chronology_serialization.py",
    }


def test_m3_has_no_forbidden_runtime_dependencies():
    forbidden = {
        "retriever",
        "retrieval_quality",
        "evidence_reranking",
        "query_expander",
        "chromadb",
        "openai",
        "streamlit",
        "features.timeline",
    }
    for path in M3.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(
            name == item or name.startswith(item + ".")
            for name in imported
            for item in forbidden
        ), f"Forbidden dependency in {path.name}: {sorted(imported)}"


def test_frozen_packages_do_not_import_case_analysis_m3():
    roots = [
        Path(__file__).parents[1] / "src" / "legal_analysis",
        Path(__file__).parents[1] / "src" / "case_analysis" / "m2",
    ]
    for root in roots:
        for path in root.glob("*.py"):
            assert "case_analysis.m3" not in path.read_text(encoding="utf-8")
