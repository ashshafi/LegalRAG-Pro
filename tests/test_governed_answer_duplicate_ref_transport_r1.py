import json
from pathlib import Path

from governed_answer_output_schema import (
    canonicalize_exact_duplicate_source_proposition_refs,
)


def _payload(refs):
    return json.dumps(
        {
            "statements": [
                {
                    "statement_id": "S1",
                    "text": "A governed statement.",
                    "source_proposition_refs": refs,
                    "evidence_keys": ["e1"],
                    "source_status": "supported_but_not_established",
                }
            ]
        }
    )


def _ref(index=0):
    return {
        "issue_analysis_id": "a1",
        "element_id": "E1",
        "source_proposition_index": index,
    }


def test_exact_duplicate_reference_is_removed_preserving_first_occurrence():
    first = _ref(0)
    raw = _payload([first, dict(first), _ref(1), dict(first)])

    normalized, removed = canonicalize_exact_duplicate_source_proposition_refs(raw)
    data = json.loads(normalized)

    assert removed == 2
    assert data["statements"][0]["source_proposition_refs"] == [_ref(0), _ref(1)]
    assert data["statements"][0]["text"] == "A governed statement."
    assert data["statements"][0]["evidence_keys"] == ["e1"]
    assert data["statements"][0]["source_status"] == "supported_but_not_established"


def test_valid_unique_output_is_byte_for_byte_noop():
    raw = _payload([_ref(0), _ref(1)])
    normalized, removed = canonicalize_exact_duplicate_source_proposition_refs(raw)
    assert normalized == raw
    assert removed == 0


def test_malformed_reference_is_not_repaired_and_remains_for_validator():
    raw = _payload(
        [
            {
                "issue_analysis_id": "a1",
                "element_id": "E1",
                "source_proposition_index": "not-an-int",
            }
        ]
    )
    normalized, removed = canonicalize_exact_duplicate_source_proposition_refs(raw)
    assert normalized == raw
    assert removed == 0


def test_unexpected_reference_field_is_not_repaired():
    ref = _ref(0)
    ref["unexpected"] = "x"
    raw = _payload([ref, dict(ref)])
    normalized, removed = canonicalize_exact_duplicate_source_proposition_refs(raw)
    assert normalized == raw
    assert removed == 0


def test_legalrag_canonicalizes_before_fail_closed_validator():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    normalize_pos = source.index("canonicalize_exact_duplicate_source_proposition_refs(")
    validate_pos = source.index(
        "validate_answer_statement_bindings(",
        normalize_pos,
    )
    assert normalize_pos < validate_pos
    assert "raw_output=normalized_analytical_output" in source


def test_core_binding_validator_still_rejects_raw_duplicate_refs():
    source = Path("src/governed_answer_authority/bindings.py").read_text(
        encoding="utf-8-sig"
    )
    assert 'raise GovernedAnswerBindingError("source_proposition_refs must be unique.")' in source
