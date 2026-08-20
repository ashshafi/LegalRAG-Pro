from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from finance_data import derive_dataset_identity, loads_dataset_document, validate_frozen_dataset_document
from finance_domain import derive_finance_id


DATASET_PATH = Path(__file__).parents[1] / "src" / "finance_data" / "datasets" / "FIN-DEMO-001.json"


def _data():
    return loads_dataset_document(DATASET_PATH.read_text(encoding="utf-8"))


def _reseal(data):
    data["dataset_identity"] = "sha256:" + "0" * 64
    data["dataset_identity"] = derive_dataset_identity(data)


def _reidentify_observation(record):
    payload = dict(record)
    payload.pop("observation_id")
    record["observation_id"] = derive_finance_id(payload)


def test_dataset_identity_tampering_is_rejected() -> None:
    data = _data()
    data["dataset_version"] = "1.1"
    with pytest.raises(ValueError, match="dataset_identity"):
        validate_frozen_dataset_document(data)


def test_duplicate_observation_identity_is_rejected() -> None:
    data = _data()
    data["observations"][1] = deepcopy(data["observations"][0])
    _reseal(data)
    with pytest.raises(ValueError, match="observations identities must be unique"):
        validate_frozen_dataset_document(data)


def test_security_company_lineage_mismatch_is_rejected() -> None:
    data = _data()
    observation = next(item for item in data["observations"] if item["security_id"] is not None)
    security_company = next(
        s["company_id"] for s in data["securities"] if s["security_id"] == observation["security_id"]
    )
    other_company = next(c["company_id"] for c in data["companies"] if c["company_id"] != security_company)
    observation["company_id"] = other_company
    _reidentify_observation(observation)
    data["observations"] = sorted(data["observations"], key=lambda x: x["observation_id"])
    _reseal(data)

    with pytest.raises(ValueError, match="security/company lineage mismatch"):
        validate_frozen_dataset_document(data, expected_provider="frozen-demo")


def test_period_company_lineage_mismatch_is_rejected() -> None:
    data = _data()
    observation = next(item for item in data["observations"] if item["financial_period_id"] is not None and item["security_id"] is None)
    period_company = next(
        p["company_id"] for p in data["periods"] if p["financial_period_id"] == observation["financial_period_id"]
    )
    other_company = next(c["company_id"] for c in data["companies"] if c["company_id"] != period_company)
    observation["company_id"] = other_company
    _reidentify_observation(observation)
    data["observations"] = sorted(data["observations"], key=lambda x: x["observation_id"])
    _reseal(data)

    with pytest.raises(ValueError, match="period/company lineage mismatch"):
        validate_frozen_dataset_document(data, expected_provider="frozen-demo")


def test_provider_and_source_authority_are_enforced() -> None:
    data = _data()
    observation = data["observations"][0]
    observation["provider"] = "other-provider"
    _reidentify_observation(observation)
    data["observations"] = sorted(data["observations"], key=lambda x: x["observation_id"])
    _reseal(data)

    with pytest.raises(ValueError, match="provider differs"):
        validate_frozen_dataset_document(data, expected_provider="frozen-demo")

    data = _data()
    observation = data["observations"][0]
    observation["source_id"] = "FOREIGN-DATA/source"
    _reidentify_observation(observation)
    data["observations"] = sorted(data["observations"], key=lambda x: x["observation_id"])
    _reseal(data)
    with pytest.raises(ValueError, match="outside frozen dataset authority"):
        validate_frozen_dataset_document(data)
