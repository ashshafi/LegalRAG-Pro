from __future__ import annotations

import json
from pathlib import Path

import pytest

from finance_data.frozen_demo import FROZEN_DEMO_PROVIDER_ID
from finance_data.immutable_dataset import (
    IMMUTABLE_DATASET_SCHEMA_VERSION,
    derive_immutable_dataset_identity,
    dumps_immutable_dataset_document,
    loads_immutable_dataset_document,
    validate_immutable_dataset_document,
)


ROOT = Path(__file__).parents[1]
DEMO_PATH = ROOT / "src" / "finance_data" / "datasets" / "FIN-DEMO-001.json"


def _document() -> dict:
    value = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    value["schema_version"] = IMMUTABLE_DATASET_SCHEMA_VERSION
    value["provider_id"] = FROZEN_DEMO_PROVIDER_ID
    value.pop("target_company_id")
    value.pop("comparable_company_ids")
    value["dataset_identity"] = "sha256:" + "0" * 64
    value["dataset_identity"] = derive_immutable_dataset_identity(value)
    return value


def test_generic_document_is_distinct_and_excludes_demo_selection_metadata() -> None:
    value = _document()
    assert value["schema_version"] == "finance-immutable-dataset/1.0"
    assert value["provider_id"] == FROZEN_DEMO_PROVIDER_ID
    assert "target_company_id" not in value
    assert "comparable_company_ids" not in value

    validated = validate_immutable_dataset_document(
        value,
        expected_provider_id=FROZEN_DEMO_PROVIDER_ID,
        expected_dataset_id=value["dataset_id"],
        expected_dataset_version=value["dataset_version"],
    )
    assert validated.dataset_identity == value["dataset_identity"]
    assert len(validated.companies) >= 1


def test_canonical_document_round_trip_and_identity_are_exact() -> None:
    value = _document()
    payload = dumps_immutable_dataset_document(value)
    loaded = loads_immutable_dataset_document(payload)
    assert loaded == value
    assert derive_immutable_dataset_identity(loaded) == value["dataset_identity"]


def test_noncanonical_json_and_duplicate_keys_fail_closed() -> None:
    value = _document()
    canonical = dumps_immutable_dataset_document(value)
    with pytest.raises(ValueError, match="canonical"):
        loads_immutable_dataset_document(canonical + "\n")

    with pytest.raises(ValueError, match="Duplicate"):
        loads_immutable_dataset_document('{"a":"1","a":"2"}')


def test_raw_json_numbers_fail_closed() -> None:
    with pytest.raises(ValueError, match="Raw JSON numbers"):
        loads_immutable_dataset_document('{"value":1}')


def test_dataset_identity_tampering_fails_closed() -> None:
    value = _document()
    value["dataset_identity"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="dataset_identity"):
        validate_immutable_dataset_document(value)


def test_unknown_or_demo_selection_keys_fail_closed() -> None:
    value = _document()
    value["target_company_id"] = value["companies"][0]["company_id"]
    value["dataset_identity"] = derive_immutable_dataset_identity(value)
    with pytest.raises(ValueError, match="keys"):
        validate_immutable_dataset_document(value)
