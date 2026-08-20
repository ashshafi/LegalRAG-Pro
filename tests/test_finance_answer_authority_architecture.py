from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "finance_answer_authority"


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_production_boundary_is_exactly_six_files_and_contains_no_persistence_or_runtime_wiring():
    assert {p.name for p in PACKAGE.glob("*.py")} == {
        "__init__.py", "models.py", "context.py", "prompt.py", "bindings.py", "validation.py"
    }
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in PACKAGE.glob("*.py"))
    for forbidden in ("streamlit", "chromadb", "openai", "langchain", "sqlite3", "requests", "httpx", "read_blob(", "original_pdf_bytes"):
        assert forbidden not in text


def test_production_has_no_legal_source_evidence_provider_engine_or_f5_resolver_imports():
    imports = [name for path in PACKAGE.glob("*.py") for name in _imports(path)]
    forbidden_prefixes = (
        "case_management", "case_analysis", "legal_analysis", "case_reporting",
        "governed_issue_evidence", "governed_evidence_analysis", "governed_analytical_authority", "governed_answer_authority",
        "source_evidence", "finance_data", "finance_calculations.engine", "finance_calculations.calculations",
        "finance_evidence.capture", "finance_evidence.binding", "finance_evidence.resolver",
    )
    assert not [name for name in imports if name.startswith(forbidden_prefixes)]


def test_no_production_code_exposes_model_generated_substantive_text_field():
    prompt = (PACKAGE / "prompt.py").read_text(encoding="utf-8")
    bindings = (PACKAGE / "bindings.py").read_text(encoding="utf-8")
    assert '_CLAIM_FIELDS = {"claim_id", "claim_type", "authority_id", "selector"}' in bindings
    assert "No text/value/status/formula/provenance fields are allowed" in prompt
