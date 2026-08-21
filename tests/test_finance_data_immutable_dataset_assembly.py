from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from finance_data.frozen_demo import FROZEN_DEMO_PROVIDER_ID
from finance_data.immutable_dataset import (
    IMMUTABLE_DATASET_SCHEMA_VERSION,
    derive_immutable_dataset_identity,
    validate_immutable_dataset_document,
)
from finance_data.immutable_dataset_assembly import assemble_immutable_finance_dataset
from finance_data.source_record_authority import (
    build_finance_source_record_authority,
)


def _demo_document() -> dict[str, object]:
    repo = Path(__file__).resolve().parents[1]
    value = json.loads(
        (repo / "src" / "finance_data" / "datasets" / "FIN-DEMO-001.json").read_text(
            encoding="utf-8"
        )
    )
    value["schema_version"] = IMMUTABLE_DATASET_SCHEMA_VERSION
    value["provider_id"] = FROZEN_DEMO_PROVIDER_ID
    value.pop("target_company_id")
    value.pop("comparable_company_ids")
    value["dataset_identity"] = "sha256:" + "0" * 64
    value["dataset_identity"] = derive_immutable_dataset_identity(value)
    return value


def _validated_demo():
    raw = _demo_document()
    return validate_immutable_dataset_document(
        raw,
        expected_provider_id=FROZEN_DEMO_PROVIDER_ID,
        expected_dataset_id=raw["dataset_id"],
        expected_dataset_version=raw["dataset_version"],
    )


def _authority_for(observation):
    return build_finance_source_record_authority(
        provider_id=observation.provider,
        source_id=observation.source_id,
        source_version=observation.source_version,
        publication_at=observation.publication_at,
        retrieved_at=observation.retrieved_at,
        observations=(observation,),
    )


def _authorities(dataset):
    return tuple(_authority_for(observation) for observation in dataset.observations)


def _assemble(dataset, *, authorities=None, dataset_id=None, companies=None):
    return assemble_immutable_finance_dataset(
        provider_id=dataset.provider_id,
        dataset_id=dataset.dataset_id if dataset_id is None else dataset_id,
        dataset_version=dataset.dataset_version,
        workspace=dataset.workspace,
        companies=dataset.companies if companies is None else companies,
        securities=dataset.securities,
        periods=dataset.periods,
        source_record_authorities=(
            _authorities(dataset) if authorities is None else authorities
        ),
    )


def test_assembly_reconstructs_existing_validated_demo_dataset_exactly():
    expected = _validated_demo()

    observed = _assemble(expected)

    assert observed == expected
    assert observed.dataset_identity == expected.dataset_identity


def test_assembly_is_deterministic_under_reversed_explicit_input_order():
    expected = _validated_demo()
    authorities = _authorities(expected)

    observed = assemble_immutable_finance_dataset(
        provider_id=expected.provider_id,
        dataset_id=expected.dataset_id,
        dataset_version=expected.dataset_version,
        workspace=expected.workspace,
        companies=tuple(reversed(expected.companies)),
        securities=tuple(reversed(expected.securities)),
        periods=tuple(reversed(expected.periods)),
        source_record_authorities=tuple(reversed(authorities)),
    )

    assert observed == expected


def test_source_record_authority_provider_must_match_dataset_provider():
    expected = _validated_demo()
    authority = _authorities(expected)[0]
    tampered = replace(
        authority,
        provider_id=authority.provider_id + "-other",
    )

    with pytest.raises(ValueError):
        _assemble(expected, authorities=(tampered,))


def test_dataset_id_must_govern_every_observation_source_id():
    expected = _validated_demo()

    with pytest.raises(ValueError, match="source_id is outside immutable dataset_id authority"):
        _assemble(expected, dataset_id=expected.dataset_id + "-other")


def test_duplicate_observation_ids_across_authorities_are_rejected():
    expected = _validated_demo()
    authority = _authorities(expected)[0]

    with pytest.raises(ValueError):
        _assemble(expected, authorities=(authority, authority))


def test_entities_are_explicit_and_missing_company_is_not_inferred():
    expected = _validated_demo()
    referenced_company = expected.observations[0].company_id
    companies = tuple(
        company
        for company in expected.companies
        if company.company_id != referenced_company
    )

    with pytest.raises(ValueError, match="unknown company_id"):
        _assemble(expected, companies=companies)


def test_invalid_source_record_authority_identity_is_rejected():
    expected = _validated_demo()
    authority = _authorities(expected)[0]
    final = authority.source_record_authority_id[-1]
    bad_id = authority.source_record_authority_id[:-1] + (
        "0" if final != "0" else "1"
    )

    with pytest.raises(ValueError):
        _assemble(
            expected,
            authorities=(replace(authority, source_record_authority_id=bad_id),),
        )


def test_source_record_authorities_must_be_non_empty():
    expected = _validated_demo()

    with pytest.raises(ValueError, match="must not be empty"):
        _assemble(expected, authorities=())


def test_mutable_collection_inputs_are_rejected():
    expected = _validated_demo()

    with pytest.raises(ValueError, match="companies must be a tuple"):
        assemble_immutable_finance_dataset(
            provider_id=expected.provider_id,
            dataset_id=expected.dataset_id,
            dataset_version=expected.dataset_version,
            workspace=expected.workspace,
            companies=list(expected.companies),
            securities=expected.securities,
            periods=expected.periods,
            source_record_authorities=_authorities(expected),
        )
