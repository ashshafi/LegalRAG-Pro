from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
DATASET = ROOT / "src" / "finance_data" / "immutable_dataset.py"
PROVIDER = ROOT / "src" / "finance_data" / "immutable_provider.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "streamlit",
    "openai",
    "langchain",
    "chromadb",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "finance_comps",
    "finance_reporting",
    "finance_evidence",
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


def test_immutable_provider_boundary_has_no_forbidden_dependencies() -> None:
    for path in (DATASET, PROVIDER):
        for module in _imports(path):
            assert not module.startswith(FORBIDDEN_IMPORT_PREFIXES), (path.name, module)


def test_immutable_provider_has_no_selection_or_activation_authority() -> None:
    provider_source = PROVIDER.read_text(encoding="utf-8")
    dataset_source = DATASET.read_text(encoding="utf-8")
    combined = provider_source + "\n" + dataset_source

    assert "target_company_id" not in combined
    assert "comparable_company_ids" not in combined
    assert "streamlit" not in combined.lower()
    assert "report_projections" not in combined
    assert "FinanceReportProjection" not in combined
    assert "build_comparable_company_analysis" not in combined


def test_candidate_is_additive_and_uses_distinct_schema() -> None:
    source = DATASET.read_text(encoding="utf-8")
    assert 'IMMUTABLE_DATASET_SCHEMA_VERSION: Final[str] = "finance-immutable-dataset/1.0"' in source
    assert "finance-frozen-dataset/1.0" not in source
