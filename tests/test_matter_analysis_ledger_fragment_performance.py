from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/ui/matter_analysis_ledger.py"


def test_matter_ledger_renderer_is_streamlit_fragment_bounded():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_matter_ledger_fragment"
    )
    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    assert [
        node.id
        for node in ledger.decorator_list
        if isinstance(node, ast.Name)
    ] == ["_matter_ledger_fragment"]

    helper_source = ast.get_source_segment(source, helper)
    assert 'getattr(st, "fragment", None)' in helper_source
    assert "return function" in helper_source
    assert "return fragment(function)" in helper_source


def test_matter_ledger_dynamic_relationship_controls_remain_interactive_widgets():
    source = UI.read_text(encoding="utf-8")

    for label in (
        "+ Check work product",
        "Status expressed by the work product",
        "Confidence expressed by the work product",
        "Governed evidence cited",
        "+ Propose analytical change",
        "Proposed analytical status",
        "Proposed confidence",
        "+ Propose relationship",
        "Relationship",
        "Evidence A role",
        "Evidence item A",
        "Evidence B role",
        "Evidence item B",
        "Why are these evidence items related?",
    ):
        assert label in source


def test_fragment_release_does_not_add_openai_or_network_calls():
    source = UI.read_text(encoding="utf-8").casefold()

    assert "responses.create" not in source
    assert "embeddings.create" not in source
    assert "requests." not in source
    assert "httpx." not in source


def test_explicit_post_write_app_reruns_remain_present():
    source = UI.read_text(encoding="utf-8")
    assert source.count("st.rerun()") >= 1
