from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "evidence_reference_bridge"
FILES = (PACKAGE / "__init__.py", PACKAGE / "answer.py")

FROZEN_SHA256 = {
    "legalrag.py": "993e04816c3fab000bf34e1f27e57fe13642f0c7c71c7185c6f879a3158b1194",
    "ui/evidence_inspection.py": "118b70e33966e8a125eacad9374355e001862e1d345062e38a89fef284e61d73",
    "evidence_references/__init__.py": "b386f3ff336e1f90cbee3da33caef01b28e25ed0835f3ca526efb9fc6fee793a",
    "evidence_references/models.py": "7e269f320382fd14cb6e15dc18f51f0f6e7747485c5805f2db9bb362b8409bf4",
    "evidence_references/resolver.py": "0c982e616aca02cc52999fc29a746f7c443100ccdbb791e89ef2257a0467bf25",
}

PROHIBITED_IMPORTS = {
    "chromadb",
    "openai",
    "streamlit",
    "document_manager",
    "document_upload",
    "index_documents",
    "ocr",
    "case_analysis",
    "legal_analysis",
    "case_reporting",
    "workspace_index",
    "source_evidence",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_u8fc2_preserves_frozen_u8f_and_u8fc1_production_boundaries():
    for relative, expected in FROZEN_SHA256.items():
        assert _sha(SRC / relative) == expected, relative


def test_u8fc2_is_additive_bridge_plus_existing_chat_integration_only():
    assert sorted(path.name for path in PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "answer.py",
    ]
    chat = (SRC / "ui" / "chat.py").read_text(encoding="utf-8")
    assert "from evidence_reference_bridge import ask_with_reference_findings" in chat
    assert "result = ask_with_reference_findings(" in chat


def test_u8fc2_bridge_has_no_direct_chroma_openai_source_store_or_analysis_dependency():
    for path in FILES:
        assert _roots(path).isdisjoint(PROHIBITED_IMPORTS), (path, _roots(path))


def test_u8fc2_bridge_uses_frozen_u8f_answer_and_u8d_u8fc1_boundaries():
    source = (PACKAGE / "answer.py").read_text(encoding="utf-8")
    assert "from legalrag import ask as legalrag_ask" in source
    assert "EvidenceSearchMode.EXHAUSTIVE_EVIDENCE" in source
    assert "resolve_evidence_references" in source
    assert "POSSIBLE_REFERENCED_BUT_NOT_LOCATED" in source
    assert "No missing-reference finding has been made" in source
