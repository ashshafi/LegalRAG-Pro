from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from finance_domain.identity import canonical_json_bytes
from finance_domain.serialization import loads_financial_observation
from finance_data.source_record_authority import (
    FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION,
    build_finance_source_record_authority,
    derive_finance_source_record_authority_id,
    validate_finance_source_record_authority,
)
from finance_data.source_record_serialization import (
    dumps_finance_source_record_authority,
    loads_finance_source_record_authority,
)


def _observation():
    repo = Path(__file__).resolve().parents[1]
    raw = json.loads(
        (repo / "src" / "finance_data" / "datasets" / "FIN-DEMO-001.json").read_text(
            encoding="utf-8"
        )
    )
    return loads_financial_observation(
        canonical_json_bytes(raw["observations"][0]).decode("utf-8")
    )


def _authority():
    observation = _observation()
    return build_finance_source_record_authority(
        provider_id=observation.provider,
        source_id=observation.source_id,
        source_version=observation.source_version,
        publication_at=observation.publication_at,
        retrieved_at=observation.retrieved_at,
        observations=(observation,),
    )


def test_builds_valid_deterministic_source_record_authority():
    first = _authority()
    second = _authority()

    assert first == second
    assert first.schema_version == FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION
    assert first.source_record_authority_id == derive_finance_source_record_authority_id(first)
    validate_finance_source_record_authority(first)


def test_canonical_serialization_round_trip_is_exact():
    authority = _authority()
    payload = dumps_finance_source_record_authority(authority)

    assert loads_finance_source_record_authority(payload) == authority
    assert dumps_finance_source_record_authority(
        loads_finance_source_record_authority(payload)
    ) == payload


def test_noncanonical_serialization_is_rejected():
    payload = dumps_finance_source_record_authority(_authority())

    with pytest.raises(ValueError, match="exact canonical form"):
        loads_finance_source_record_authority(" " + payload)


def test_duplicate_json_key_is_rejected():
    payload = dumps_finance_source_record_authority(_authority())
    data = json.loads(payload)
    duplicate = payload.rstrip("\n")
    duplicate = (
        duplicate[:-1]
        + ',"schema_version":'
        + json.dumps(data["schema_version"])
        + "}\n"
    )

    with pytest.raises(ValueError, match="Invalid Finance source-record authority JSON"):
        loads_finance_source_record_authority(duplicate)


def test_provider_mismatch_is_rejected():
    authority = _authority()

    with pytest.raises(ValueError, match="provider differs"):
        validate_finance_source_record_authority(
            replace(authority, provider_id=authority.provider_id + "-other")
        )


def test_source_id_outside_authority_is_rejected():
    authority = _authority()

    with pytest.raises(ValueError, match="source_id is outside"):
        validate_finance_source_record_authority(
            replace(authority, source_id=authority.source_id + "-other")
        )


def test_source_version_mismatch_is_rejected():
    authority = _authority()

    with pytest.raises(ValueError, match="source_version differs"):
        validate_finance_source_record_authority(
            replace(authority, source_version=authority.source_version + "-other")
        )


def test_publication_mismatch_is_rejected_when_authority_publication_is_present():
    authority = _authority()
    alternate = (
        authority.observations[0].observed_at
        if authority.publication_at is None
        else authority.publication_at + timedelta(seconds=1)
    )

    with pytest.raises(ValueError, match="publication_at differs"):
        validate_finance_source_record_authority(
            replace(authority, publication_at=alternate)
        )


def test_source_retrieval_cannot_precede_observation_time():
    authority = _authority()
    earlier = authority.observations[0].observed_at - timedelta(seconds=1)

    with pytest.raises(ValueError, match="must not precede observation observed_at"):
        validate_finance_source_record_authority(
            replace(authority, retrieved_at=earlier)
        )


def test_duplicate_observation_identity_is_rejected():
    authority = _authority()

    with pytest.raises(ValueError, match="unique by observation_id"):
        validate_finance_source_record_authority(
            replace(
                authority,
                observations=(
                    authority.observations[0],
                    authority.observations[0],
                ),
            )
        )


def test_identity_tampering_is_rejected():
    authority = _authority()
    final = authority.source_record_authority_id[-1]
    replacement = (
        authority.source_record_authority_id[:-1]
        + ("0" if final != "0" else "1")
    )

    with pytest.raises(ValueError, match="canonical identity payload"):
        validate_finance_source_record_authority(
            replace(authority, source_record_authority_id=replacement)
        )
