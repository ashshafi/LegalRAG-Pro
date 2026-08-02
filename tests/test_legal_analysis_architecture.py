"""Architectural boundary tests for Sprint 2.3 Milestone 1."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY  # noqa: E402


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_legal_analysis_package_has_no_openai_or_retrieval_dependency() -> None:
    package = SRC_PATH / "legal_analysis"
    forbidden = {"openai", "retriever", "retrieval_quality", "evidence_reranking"}

    for path in package.glob("*.py"):
        assert not (_imports_for(path) & forbidden), path.name


def test_default_registry_can_be_loaded_without_api_calls() -> None:
    assert len(DEFAULT_ISSUE_DEFINITION_REGISTRY.list_definitions()) == 4


def test_milestone_1_does_not_add_chat_or_ui_modules() -> None:
    package_files = {path.name for path in (SRC_PATH / "legal_analysis").glob("*.py")}

    assert "chat.py" not in package_files
    assert "ui.py" not in package_files


def test_domain_foundation_files_are_standard_library_plus_public_evidence_type() -> None:
    package = SRC_PATH / "legal_analysis"
    allowed_project_imports = {"evidence_classification", "legal_analysis"}

    for path in package.glob("*.py"):
        imports = _imports_for(path)
        project_like = {
            name
            for name in imports
            if name
            in {
                "chunk_provenance",
                "evidence_classification",
                "evidence_display",
                "evidence_reasoning",
                "evidence_reranking",
                "evidence_semantics",
                "legalrag",
                "retrieval_quality",
                "retriever",
                "semantic_reasoning",
                "ui",
            }
        }
        assert project_like <= allowed_project_imports, (path.name, project_like)

