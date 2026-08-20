from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
FINANCE_DATA = ROOT / "src" / "finance_data"

FORBIDDEN_IMPORT_PREFIXES = (
    "case_management",
    "legal_analysis",
    "case_analysis",
    "case_reporting",
    "governed_analytical_authority",
    "governed_answer_authority",
    "governed_evidence_analysis",
    "governed_issue_evidence",
    "evidence_answer",
    "evidence_roles",
    "ui",
    "streamlit",
    "chromadb",
    "openai",
    "langchain",
    "requests",
    "httpx",
    "pandas",
    "numpy",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_finance_data_has_only_finance_domain_and_stdlib_architecture() -> None:
    for path in FINANCE_DATA.glob("*.py"):
        for module in _imports(path):
            assert not module.startswith(FORBIDDEN_IMPORT_PREFIXES), (path.name, module)


def test_finance_data_contains_no_network_or_calculation_authority() -> None:
    forbidden_text = (
        "enterprise_value",
        "net_debt",
        "ev_ebitda",
        "ev_revenue",
        "revenue_growth",
        "ebitda_margin",
        "discounted_cash_flow",
        "urllib",
        "socket",
    )
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in FINANCE_DATA.glob("*.py"))
    for term in forbidden_text:
        assert term not in source


def test_f2_is_additive_and_does_not_modify_f1_contract_files() -> None:
    expected_f1 = {
        "__init__.py": "ef71cdbd03a2baa2b87823e1fbd4dbb573ed047b810734136aa80cb8e8f126bc",
        "models.py": "115019e2ca734154a63eab1eb64051c1137791556b185e4090d5509a109b0910",
        "identity.py": "b04b227304847bced8cba6ec29fe42a6319b0700675b6d0faf55ae6aa092230b",
        "serialization.py": "cd0d7ae7b7df2fc84c2e92949e8a01018b69cc00fe1a95e883ee239d33163a59",
        "validation.py": "e0fc093864593d1b70285b7a99903b5b89f7080ceeeac6f9e9fa522a9d55dc84",
    }
    import hashlib

    for name, expected in expected_f1.items():
        observed = hashlib.sha256((ROOT / "src" / "finance_domain" / name).read_bytes()).hexdigest()
        assert observed == expected
