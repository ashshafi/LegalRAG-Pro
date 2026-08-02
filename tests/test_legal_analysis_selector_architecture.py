"""Architectural-boundary tests for Sprint 2.3 Milestone 2."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS  # noqa: E402
from legal_analysis.registry import build_default_registry  # noqa: E402
from legal_analysis.selector import DeterministicIssueSelector  # noqa: E402


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_selector_has_no_openai_retrieval_or_ui_dependency() -> None:
    forbidden = {
        "openai",
        "retriever",
        "retrieval_quality",
        "evidence_reranking",
        "chromadb",
        "streamlit",
        "ui",
        "legalrag",
    }
    for filename in ("selection.py", "selector.py"):
        imports = _imports_for(SRC_PATH / "legal_analysis" / filename)
        assert not (imports & forbidden), (filename, imports & forbidden)


def test_selector_does_not_mutate_registry_or_definitions() -> None:
    registry = build_default_registry()
    before_objects = registry.list_definitions()
    before = tuple(repr(item) for item in before_objects)

    selector = DeterministicIssueSelector(registry)
    selector.select("What evidence shows CACI knew about my disability?")
    selector.select("Is my claim out of time if the failures continued?")

    after_objects = registry.list_definitions()
    after = tuple(repr(item) for item in after_objects)
    assert after == before
    assert after_objects == before_objects
    assert {item.key for item in INITIAL_ISSUE_DEFINITIONS} == {
        item.key for item in before_objects
    }


def test_selector_can_only_return_registered_issue_ids() -> None:
    registry = build_default_registry()
    registered = {item.definition_id for item in registry.list_definitions()}
    selector = DeterministicIssueSelector(registry)

    for question in (
        "What evidence shows CACI knew about my disability?",
        "Should CACI have allowed me to work from home because of my disability?",
        "Was I treated unfavourably because of something arising from my disability?",
        "Is my claim out of time if the failures continued?",
        "Was what happened to me discriminatory?",
    ):
        result = selector.select(question)
        ids = {item.issue_definition_id for item in result.all_selected_issues()}
        ids.update(item.issue_definition_id for item in result.not_selected_issues)
        for ambiguity in result.ambiguities:
            ids.update(ambiguity.candidate_issue_definition_ids)
        assert ids <= registered


def test_selection_is_not_issue_analysis_population() -> None:
    result = DeterministicIssueSelector().select(
        "What evidence shows CACI knew about my disability?"
    )
    assert not hasattr(result, "elements")
    assert not hasattr(result, "supporting_evidence")
    assert not hasattr(result, "legal_analysis")


def test_milestone_2_adds_no_chat_or_ui_file() -> None:
    names = {path.name for path in (SRC_PATH / "legal_analysis").glob("*.py")}
    assert "chat.py" not in names
    assert "ui.py" not in names


def test_existing_m1_source_files_remain_unchanged_from_m1_snapshot() -> None:
    # The work tree was copied from the frozen M1 snapshot; only selection.py
    # and selector.py are allowed additions in src/legal_analysis for M2.
    m1_root = Path("/mnt/data/legalrag_s23_m1_verify/src/legal_analysis")
    current_root = SRC_PATH / "legal_analysis"
    for path in m1_root.glob("*.py"):
        assert _sha256(path) == _sha256(current_root / path.name), path.name
