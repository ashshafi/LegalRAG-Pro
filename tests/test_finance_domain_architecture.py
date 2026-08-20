import ast
from pathlib import Path

FINANCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "finance_domain"
ALLOWED_EXTERNAL_IMPORT = "source_evidence.identity"
BANNED_PREFIXES = (
    "case_management",
    "legal_analysis",
    "case_analysis",
    "governed_analytical_authority",
    "governed_answer_authority",
    "governed_evidence_analysis",
    "governed_issue_evidence",
    "case_reporting",
    "evidence_answer",
    "evidence_roles",
    "ui",
)


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_f1_finance_domain_has_exact_authorised_production_paths():
    assert sorted(path.name for path in FINANCE_ROOT.glob("*.py")) == [
        "__init__.py",
        "identity.py",
        "models.py",
        "serialization.py",
        "validation.py",
    ]


def test_f1_has_no_legal_domain_imports():
    for path in FINANCE_ROOT.glob("*.py"):
        for module in _imports(path):
            assert not module.startswith(BANNED_PREFIXES), (path.name, module)


def test_f1_only_shares_the_narrow_source_identity_seam():
    source_imports = []
    for path in FINANCE_ROOT.glob("*.py"):
        for module in _imports(path):
            if module.startswith("source_evidence"):
                source_imports.append((path.name, module))
    assert source_imports == [("identity.py", ALLOWED_EXTERNAL_IMPORT)]


def test_f1_contains_no_runtime_provider_ui_database_or_llm_imports():
    banned = ("chromadb", "streamlit", "openai", "langchain", "sqlite3", "requests", "httpx")
    for path in FINANCE_ROOT.glob("*.py"):
        for module in _imports(path):
            assert not module.startswith(banned), (path.name, module)
