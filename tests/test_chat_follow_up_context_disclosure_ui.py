from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_PATH = ROOT / "src" / "ui" / "chat.py"
FOLLOW_UP_PATH = ROOT / "src" / "follow_up_context.py"
FOCUSED_TEST_PATH = ROOT / "tests" / "test_chat_follow_up_context_ui.py"

EXPECTED_DISCLOSURE = (
    "Session-local history for this case only. Prior completed turns are not legal or "
    "evidential authority; their rendered results are presentation-only. For an active "
    "case, a bounded same-case excerpt may be used only to resolve a context-dependent "
    "follow-up into a standalone current question. That question then follows the normal "
    "governed answer/retrieval path; prior-result metadata, evidence, provenance, and "
    "authority are not inherited."
)
OLD_DISCLOSURE = (
    "Session-local history for this case only. Previous turns are presentation-only "
    "and are never supplied to retrieval, prompts, or analytical authority."
)
EXPECTED_FOLLOW_UP_SHA256 = "99715f545cceb6832d08d6603b96421a8bae746dd6584709d3b11ad771b91e08"
EXPECTED_FOCUSED_TEST_SHA256 = "d37b249329b38c23f7716c026375099531feeea0f5bb0dc5a1d34fff63de865e"


def _caption_text() -> str:
    tree = ast.parse(CHAT_PATH.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_show_conversation_history"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "caption"
    ]
    assert len(calls) == 1
    assert len(calls[0].args) == 1
    value = ast.literal_eval(calls[0].args[0])
    assert isinstance(value, str)
    return value


def test_disclosure_caption_is_exact_and_unique():
    assert _caption_text() == EXPECTED_DISCLOSURE


def test_disclosure_states_the_frozen_b18_trust_boundary():
    caption = _caption_text()
    for required in (
        "not legal or evidential authority",
        "rendered results are presentation-only",
        "bounded same-case excerpt",
        "only to resolve a context-dependent follow-up",
        "standalone current question",
        "normal governed answer/retrieval path",
        "prior-result metadata, evidence, provenance, and authority are not inherited",
    ):
        assert required in caption


def test_disclosure_removes_the_false_never_supplied_to_prompts_claim():
    source = CHAT_PATH.read_text(encoding="utf-8")
    assert OLD_DISCLOSURE not in source
    assert "never supplied to retrieval, prompts, or analytical authority" not in source


# The B18 trust-boundary behaviour remains frozen. The resolver file identity
# is deliberately superseded by SRA-C1 provider-policy gating and the R2
# Responses API store=False control; neither authorises a change to B18
# conversational/evidential semantics. The focused UI test seal below is the
# exact released-HEAD generation captured at the SRA-C1 implementation input.
def test_post_s1_b18_semantic_file_seals_are_exact():
    assert hashlib.sha256(FOLLOW_UP_PATH.read_bytes()).hexdigest() == EXPECTED_FOLLOW_UP_SHA256
    assert hashlib.sha256(FOCUSED_TEST_PATH.read_bytes()).hexdigest() == EXPECTED_FOCUSED_TEST_SHA256
