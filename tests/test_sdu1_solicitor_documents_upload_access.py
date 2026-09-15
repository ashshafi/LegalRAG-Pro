from __future__ import annotations

import ast
import inspect
from pathlib import Path

from document_upload import upload_case_pdf


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "ui" / "solicitor_documents.py"


def test_solicitor_documents_upload_supplies_validated_access() -> None:
    text = TARGET.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "upload_case_pdf")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "upload_case_pdf"
            )
        )
    ]
    assert len(calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    assert "case_id" in keywords
    assert "access" in keywords

    case_value = keywords["case_id"]
    assert isinstance(case_value, ast.Name)
    assert case_value.id == "active_case_id"

    access_value = keywords["access"]
    assert isinstance(access_value, ast.Call)
    assert isinstance(access_value.func, ast.Attribute)
    assert access_value.func.attr == "require_access"
    assert isinstance(access_value.func.value, ast.Call)
    assert isinstance(access_value.func.value.func, ast.Name)
    assert access_value.func.value.func.id == "CaseRepository"

    identity_arg, matter_arg = access_value.args
    assert isinstance(identity_arg, ast.Call)
    assert isinstance(identity_arg.func, ast.Name)
    assert identity_arg.func.id == "current_user_identity"
    assert isinstance(matter_arg, ast.Name)
    assert matter_arg.id == "active_case_id"


def test_upload_service_access_remains_keyword_only() -> None:
    signature = inspect.signature(upload_case_pdf)
    assert "access" in signature.parameters
    assert signature.parameters["access"].kind is inspect.Parameter.KEYWORD_ONLY
