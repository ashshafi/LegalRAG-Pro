from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from finance_domain.identity import derive_finance_id
from finance_domain.models import FINANCIAL_OBSERVATION_SCHEMA_VERSION, FinancialObservation
from finance_domain.serialization import (
    dumps_financial_observation,
    financial_observation_identity_payload_to_dict,
    loads_financial_observation,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
COMPANY_ID = "22222222-2222-4222-8222-222222222222"


def _observation():
    value = FinancialObservation(
        schema_version=FINANCIAL_OBSERVATION_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        security_id=None,
        metric_code="EBITDA",
        value=Decimal("240000000.00"),
        currency="GBP",
        unit="currency",
        financial_period_id=None,
        provider="DemoProvider",
        source_id="results-2025",
        source_version="v1",
        publication_at=datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
        effective_at=None,
        observed_at=datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        observation_id="sha256:" + "0" * 64,
    )
    return replace(value, observation_id=derive_finance_id(financial_observation_identity_payload_to_dict(value)))


def test_round_trip_is_exact_canonical_json():
    value = _observation()
    payload = dumps_financial_observation(value)
    assert payload.endswith("\n")
    assert '"value":"240000000"' in payload
    assert '"publication_at":"2026-02-17T07:00:00.000000Z"' in payload
    assert loads_financial_observation(payload) == value
    assert dumps_financial_observation(loads_financial_observation(payload)) == payload


def test_noncanonical_json_is_rejected():
    payload = dumps_financial_observation(_observation())
    with pytest.raises(ValueError, match="canonical"):
        loads_financial_observation(payload.replace('"value":"240000000"', '"value":"240000000.0"'))


def test_duplicate_json_keys_are_rejected():
    payload = dumps_financial_observation(_observation())
    poisoned = payload.replace('{', '{"schema_version":"financial-observation/1.0",', 1)
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        loads_financial_observation(poisoned)


def test_serialization_rejects_non_utc_datetime_without_normalising_it():
    from datetime import timedelta

    value = _observation()
    shifted = replace(
        value,
        publication_at=value.publication_at.astimezone(timezone(timedelta(hours=1))),
    )
    with pytest.raises(ValueError, match="UTC"):
        dumps_financial_observation(shifted)
