from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_d2_shell_modules_parse():
    for rel in ("src/ui/solicitor_shell.py", "src/ui/solicitor_documents.py", "src/ui/solicitor_drafts.py"):
        ast.parse(_source(rel), filename=rel)


def test_d2_shell_labels():
    source = _source("src/ui/solicitor_shell.py")

    for label in (
        "Overview",
        "Issues",
        "Chronology",
        "Evidence",
        "Documents",
        "People",
        "Audit",
        "Ask LegalRAG",
    ):
        assert f'"{label}"' in source

    assert "st.segmented_control(" in source
    assert "route_solicitor_view" in source


def test_d2_app_has_shell_and_new_routes():
    app = _source("src/app.py")
    assert "show_solicitor_shell(" in app
    assert "show_documents_workspace(" in app
    assert "show_drafts_workspace(" in app


def test_d2_sidebar_is_secondary_only():
    sidebar = _source("src/ui/sidebar.py")
    tree = ast.parse(sidebar)
    show = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "show_sidebar")
    segment = ast.get_source_segment(sidebar, show) or ""
    for obsolete in ("Matter workspace", "Case Operator", "Assistant", "Drafting", "Sources & Provenance", "Audit Trail"):
        assert obsolete not in segment
    assert "Documents in context" in segment


def test_work_language_when_case_operator_present():
    source = _source("src/ui/solicitor_shell.py")
    operator = _source("src/ui/case_operator.py")
    workflow = _source("src/ui/solicitor_workflow.py")

    # Current R6 deliberately keeps Case Operator as an explicit solicitor
    # route. The old D2 requirement to hide/rename that surface is retired.
    assert '"Case Operator"' in source
    assert 'st.title("Case Operator")' in operator
    assert "task" in workflow.casefold() or "work" in workflow.casefold()


if __name__ == "__main__":
    test_d2_shell_modules_parse()
    test_d2_shell_labels()
    test_d2_app_has_shell_and_new_routes()
    test_d2_sidebar_is_secondary_only()
    test_work_language_when_case_operator_present()
    print("UX_D2_STATIC_TESTS=PASS")
