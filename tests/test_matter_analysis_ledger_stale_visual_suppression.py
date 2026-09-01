from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/ui/matter_analysis_ledger.py"


def test_stale_visual_suppression_is_visual_only():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_suppress_streamlit_stale_visual_dimming"
    )

    helper_source = ast.get_source_segment(source, helper)

    assert '[data-stale="true"]' in helper_source
    assert "opacity: 1 !important" in helper_source
    assert "transition: none !important" in helper_source
    assert "filter: none !important" in helper_source
    assert "unsafe_allow_html=True" in helper_source

    # Do not make stale controls interactive or change execution semantics.
    assert "pointer-events" not in helper_source
    assert "st.rerun" not in helper_source
    assert "session_state" not in helper_source


def test_stale_visual_suppression_runs_once_per_ledger_render():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    calls = [
        node
        for node in ast.walk(ledger)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_suppress_streamlit_stale_visual_dimming"
    ]

    assert len(calls) == 1


def test_fragment_and_submit_only_boundaries_are_not_removed():
    source = UI.read_text(encoding="utf-8")
    tree = ast.parse(source)

    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_matter_analysis_ledger"
    )

    if "_matter_ledger_fragment" in source:
        decorators = [
            node.id
            for node in ledger.decorator_list
            if isinstance(node, ast.Name)
        ]
        assert decorators == ["_matter_ledger_fragment"]

    # If the previously released no-rerun form helpers are present,
    # this release must preserve them.
    if "def _matter_entry_form(" in source:
        assert "def _matter_form_submit_button(" in source
        assert '"Work-product statement or proposition"' in source
        assert '"Proposed analytical status"' in source


def test_stale_visual_release_adds_no_openai_or_network_calls():
    source = UI.read_text(encoding="utf-8").casefold()

    assert "responses.create" not in source
    assert "embeddings.create" not in source
    assert "requests." not in source
    assert "httpx." not in source
