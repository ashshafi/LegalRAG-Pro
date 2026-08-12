"""Static architecture tests for the additive U9B-to-U9C-B1 constructor."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "governed_evidential_construction"


def test_constructor_package_is_exact_two_file_additive_surface() -> None:
    assert {path.name for path in PACKAGE.glob("*.py")} == {"__init__.py", "builder.py"}
    init_source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    assert '__all__ = ["build_governed_evidential_analysis"]' in init_source


def test_builder_uses_only_frozen_public_u9b_and_u9c_b1_apis() -> None:
    source = (PACKAGE / "builder.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: list[str] = []
    imported_names: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            imported_names.extend((module, alias.name) for alias in node.names)

    assert set(imported_modules) <= {
        "__future__",
        "collections",
        "governed_evidence_analysis",
        "governed_issue_evidence",
    }
    assert all(
        module in {"governed_evidence_analysis", "governed_issue_evidence"}
        for module, _ in imported_names
        if module.startswith(("governed_evidence_analysis", "governed_issue_evidence"))
    )
    assert not any(name.startswith("_") for _, name in imported_names)

    forbidden_roots = {
        "chromadb",
        "openai",
        "streamlit",
        "retriever",
        "query_expander",
        "document_manager",
        "source_evidence",
        "evidence_search",
        "legal_analysis",
        "case_analysis",
        "case_management",
        "governed_analytical_authority",
        "governed_analytical_capture",
        "sqlite3",
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "requests",
        "urllib",
    }
    assert not {module.split(".", 1)[0] for module in imported_modules} & forbidden_roots


def test_builder_has_no_io_publication_activation_or_analytical_engine_capability() -> None:
    source = (PACKAGE / "builder.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    call_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            call_names.add(node.func.attr)

    forbidden_calls = {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "remove",
        "rename",
        "replace",
        "connect",
        "query",
        "search",
        "retrieve",
        "map_primary_issue",
        "assess",
        "render",
        "build_case_analysis_foundation",
        "build_case_matrices",
        "build_governed_issue_evidence_map",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
    }
    assert not call_names & forbidden_calls
    assert "validate_governed_issue_evidence_map" in call_names
    assert "source_u9b_sha256" in call_names
    assert "derive_governed_evidential_analysis_id" in call_names
    assert "validate_governed_evidential_analysis" in call_names


def test_existing_source_tree_does_not_depend_on_new_constructor_package() -> None:
    references = []
    for path in SRC.rglob("*.py"):
        if PACKAGE in path.parents:
            continue
        if "governed_evidential_construction" in path.read_text(encoding="utf-8"):
            references.append(path.relative_to(ROOT).as_posix())
    assert references == []
