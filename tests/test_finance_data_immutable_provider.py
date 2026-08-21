from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from finance_data import FinanceDataLookupError, FinancialDataProvider
from finance_data.frozen_demo import FROZEN_DEMO_PROVIDER_ID
from finance_data.immutable_dataset import (
    IMMUTABLE_DATASET_SCHEMA_VERSION,
    derive_immutable_dataset_identity,
    dumps_immutable_dataset_document,
)
from finance_data.immutable_provider import ImmutableDatasetProvider


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


def _provider(tmp_path: Path) -> ImmutableDatasetProvider:
    document = _document()
    path = tmp_path / "snapshot.json"
    path.write_text(dumps_immutable_dataset_document(document), encoding="utf-8")
    return ImmutableDatasetProvider(
        dataset_path=path,
        expected_provider_id=FROZEN_DEMO_PROVIDER_ID,
        expected_dataset_id=document["dataset_id"],
        expected_dataset_version=document["dataset_version"],
    )


def test_provider_implements_exact_abstract_data_access_contract(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    document = _document()
    assert isinstance(provider, FinancialDataProvider)
    assert provider.provider_id == FROZEN_DEMO_PROVIDER_ID
    assert provider.dataset_id == document["dataset_id"]
    assert provider.dataset_version == document["dataset_version"]
    assert provider.dataset_identity.startswith("sha256:")
    assert len(provider.list_companies()) >= 1
    assert not hasattr(provider, "target_company_id")
    assert not hasattr(provider, "comparable_company_ids")


def test_provider_authority_mismatch_fails_closed(tmp_path: Path) -> None:
    document = _document()
    path = tmp_path / "snapshot.json"
    path.write_text(dumps_immutable_dataset_document(document), encoding="utf-8")
    with pytest.raises(ValueError, match="provider_id"):
        ImmutableDatasetProvider(
            dataset_path=path,
            expected_provider_id=FROZEN_DEMO_PROVIDER_ID + "-mismatch",
            expected_dataset_id=document["dataset_id"],
            expected_dataset_version=document["dataset_version"],
        )


def test_entity_and_period_queries_are_isolated(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    company = provider.list_companies()[0]
    assert provider.get_company(company_id=company.company_id) == company
    assert all(
        item.company_id == company.company_id
        for item in provider.list_securities(company_id=company.company_id)
    )
    assert all(
        item.company_id == company.company_id
        for item in provider.list_periods(company_id=company.company_id)
    )


def test_unknown_authority_fails_closed_but_missing_metric_is_empty(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    unknown_company = "99999999-9999-4999-8999-999999999999"
    with pytest.raises(FinanceDataLookupError):
        provider.list_periods(company_id=unknown_company)

    company = provider.list_companies()[0]
    assert provider.get_observations(
        company_id=company.company_id,
        metric_code="ZZ_NOT_PRESENT",
    ) == ()


def test_provider_requires_canonical_utc_as_of(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    company = provider.list_companies()[0]
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        provider.get_observations(
            company_id=company.company_id,
            as_of=datetime(2025, 1, 1),
        )

    assert isinstance(
        provider.get_observations(
            company_id=company.company_id,
            as_of=datetime(2030, 1, 1, tzinfo=timezone.utc),
        ),
        tuple,
    )
