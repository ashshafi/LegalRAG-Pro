from __future__ import annotations

import ast
from pathlib import Path

import governed_analytical_authority.provider as provider


PRODUCTION_FILES = (
    "__init__.py", "models.py", "identity.py", "serialization.py", "validation.py",
    "provider.py", "publication.py", "activation.py",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "chromadb", "openai", "streamlit", "retriever", "query_expander",
    "document_manager", "case_management", "legalrag", "ui",
)


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "governed_analytical_authority"


def test_b6_is_exact_eight_file_additive_production_package_with_no_forbidden_runtime_dependencies():
    root = _package_root()
    assert tuple(sorted(path.name for path in root.glob("*.py"))) == tuple(sorted(PRODUCTION_FILES))
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not [
            name for name in imports
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES)
        ], path.name


def test_runtime_provider_public_surface_is_read_only_and_has_no_selection_search_api():
    assert provider.__all__ == [
        "GovernedAnalyticalAuthorityProviderError",
        "load_active_governed_analytical_authority",
    ]
    forbidden = {"load_latest", "list_authorities", "choose_best", "load_newest", "fallback_to_previous", "repair", "publish", "activate", "save"}
    assert forbidden.isdisjoint(vars(provider))


def test_provider_source_contains_no_writer_or_analysis_builder_calls():
    path = _package_root() / "provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert not ({"replace", "rename", "write_text", "write_bytes", "publish_governed_analytical_authority", "activate_governed_analytical_authority", "build_case_matrices"} & calls)
