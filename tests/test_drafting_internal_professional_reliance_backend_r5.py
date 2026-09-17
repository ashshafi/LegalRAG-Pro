from pathlib import Path
import ast

TARGET = Path("src/drafting_working_draft_release_orchestration.py")


def _source(text, node):
    return ast.get_source_segment(text, node) or ""


def _function(text, name):
    tree = ast.parse(text)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_not_authorized_is_review_metadata_not_an_absolute_backend_blocker():
    text = TARGET.read_text(encoding="utf-8-sig")
    policy = _function(text, "assert_working_draft_release_decision_allowed")
    src = _source(text, policy)

    assert 'and "NOT_AUTHORIZED" in results' not in src
    assert "working_draft_authority_results(" in src
    assert "return decision_value" in src
    assert "do not by themselves prevent internal professional reliance" in src


def test_existing_governed_release_guards_remain_in_place():
    text = TARGET.read_text(encoding="utf-8-sig")
    record = _function(text, "record_working_draft_professional_release")
    src = _source(text, record)

    for required in (
        "expected_target_id",
        "publish_artifact",
        "load_binding",
        "read_artifact",
        "assert_working_draft_release_decision_allowed",
        "record_work_product_release",
        "factual_basis_reviewed",
        "legal_authorities_reviewed",
        "unverified_authorities_remaining",
        "professional_judgment_completed",
        "court_or_tribunal_reliance",
    ):
        assert required in src


def test_module_contract_no_longer_claims_not_authorized_is_absolute_prohibition():
    text = TARGET.read_text(encoding="utf-8-sig")

    assert "Drafting-specific NOT_AUTHORIZED approval prohibition" not in text
    assert "Current Assessment authorization checks as professional-review metadata" in text
