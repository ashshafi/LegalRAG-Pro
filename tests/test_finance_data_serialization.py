from __future__ import annotations

from pathlib import Path

import pytest

from finance_data import (
    FrozenDemoProvider,
    derive_dataset_identity,
    dumps_dataset_document,
    loads_dataset_document,
)


DATASET_PATH = Path(__file__).parents[1] / "src" / "finance_data" / "datasets" / "FIN-DEMO-001.json"


def test_dataset_identity_is_exact_and_stable() -> None:
    data = loads_dataset_document(DATASET_PATH.read_text(encoding="utf-8"))
    assert data["dataset_identity"] == "sha256:d6b79897159646951760b4bc8018a27ed82e3b2e292aaef32675253038fbad78"
    assert derive_dataset_identity(data) == data["dataset_identity"]
    assert FrozenDemoProvider().dataset_identity == data["dataset_identity"]


def test_canonical_dump_round_trips_semantics() -> None:
    data = loads_dataset_document(DATASET_PATH.read_text(encoding="utf-8"))
    canonical = dumps_dataset_document(data)
    assert canonical.endswith("\n")
    assert loads_dataset_document(canonical) == data
    assert derive_dataset_identity(loads_dataset_document(canonical)) == data["dataset_identity"]


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        loads_dataset_document('{"dataset_id":"A","dataset_id":"B"}')


def test_raw_json_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="numeric literal"):
        loads_dataset_document('{"value":1.25}')
    with pytest.raises(ValueError, match="numeric literal"):
        loads_dataset_document('{"value":1}')
