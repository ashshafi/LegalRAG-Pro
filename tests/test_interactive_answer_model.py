from pathlib import Path

SOURCE = Path("src/legalrag.py").read_text(encoding="utf-8-sig")

def test_interactive_model_defaults_to_terra():
    assert 'LEGALRAG_INTERACTIVE_CHAT_MODEL' in SOURCE
    assert '"gpt-5.6-terra"' in SOURCE

def test_interactive_reasoning_defaults_to_none():
    assert 'LEGALRAG_INTERACTIVE_REASONING_EFFORT' in SOURCE
    assert '"none"' in SOURCE
    assert 'reasoning={"effort": INTERACTIVE_REASONING_EFFORT}' in SOURCE

def test_direct_provider_call_uses_interactive_model():
    assert 'model=INTERACTIVE_CHAT_MODEL' in SOURCE
    assert 'openai_client.responses.create(' in SOURCE

def test_actual_interactive_model_is_policy_gated():
    assert 'model=INTERACTIVE_CHAT_MODEL,' in SOURCE
    assert 'AIProcessingPurpose.LEGAL_ANSWER' in SOURCE

def test_bounded_path_remains_present():
    assert 'create_bounded_governed_response' in SOURCE

def test_chat_model_remains_for_strong_path():
    assert 'CHAT_MODEL' in SOURCE

def test_store_false_remains_present():
    assert 'store=False' in SOURCE
