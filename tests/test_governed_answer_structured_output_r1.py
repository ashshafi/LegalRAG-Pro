from pathlib import Path

LEGALRAG = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
SCHEMA = Path("src/governed_answer_output_schema.py").read_text(encoding="utf-8-sig")


def test_applied_governed_answer_uses_strict_json_schema_output():
    assert '"type": "json_schema"' in LEGALRAG
    assert '"name": "governed_analytical_answer"' in LEGALRAG
    assert '"strict": True' in LEGALRAG
    assert "build_governed_answer_output_schema(analytical_context)" in LEGALRAG

    # Exact schema mechanics now live in the dedicated status-aware helper.
    assert '"additionalProperties": False' in SCHEMA
    for field in (
        "statement_id",
        "text",
        "source_proposition_refs",
        "evidence_keys",
        "source_status",
    ):
        assert f'"{field}"' in SCHEMA


def test_existing_interactive_provider_contract_is_preserved():
    assert 'reasoning={"effort": INTERACTIVE_REASONING_EFFORT}' in LEGALRAG
    assert 'store=False' in LEGALRAG


def test_structured_output_is_only_enabled_for_applied_analytical_mode():
    gate = (
        'case_id is not None\n'
        '            and analytical_mode is not None\n'
        '            and analytical_mode.value == "applied"'
    )
    assert gate in LEGALRAG
