from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import finance_runtime


def test_runtime_composes_exact_four_stage_chain(monkeypatch):
    calls = []
    provider = object()
    analysis = object()
    evidence_manifest = object()
    projection = object()
    definition = object()
    documents = object()
    entries = object()
    dataset_path = Path.cwd() / "sealed-finance-dataset.json"

    def fake_select(**kwargs):
        calls.append(("select", kwargs))
        return provider

    def fake_analysis(**kwargs):
        calls.append(("analysis", kwargs))
        return analysis

    def fake_evidence(**kwargs):
        calls.append(("evidence", kwargs))
        return evidence_manifest

    def fake_projection(**kwargs):
        calls.append(("projection", kwargs))
        return projection

    monkeypatch.setattr(finance_runtime, "select_financial_data_provider", fake_select)
    monkeypatch.setattr(finance_runtime, "build_comparable_company_analysis", fake_analysis)
    monkeypatch.setattr(
        finance_runtime,
        "build_finance_observation_evidence_manifest",
        fake_evidence,
    )
    monkeypatch.setattr(finance_runtime, "build_finance_report_projection", fake_projection)

    result = finance_runtime.build_finance_runtime_projection(
        provider_mode="immutable",
        definition=definition,
        documents=documents,
        entries=entries,
        dataset_path=dataset_path,
        expected_provider_id="provider-1",
        expected_dataset_id="dataset-1",
        expected_dataset_version="v1",
    )

    assert result is projection
    assert calls == [
        (
            "select",
            {
                "mode": "immutable",
                "dataset_path": dataset_path,
                "expected_provider_id": "provider-1",
                "expected_dataset_id": "dataset-1",
                "expected_dataset_version": "v1",
            },
        ),
        (
            "analysis",
            {
                "provider": provider,
                "definition": definition,
            },
        ),
        (
            "evidence",
            {
                "analysis": analysis,
                "documents": documents,
                "entries": entries,
            },
        ),
        (
            "projection",
            {
                "analysis": analysis,
                "evidence_manifest": evidence_manifest,
            },
        ),
    ]


def test_runtime_forwards_demo_defaults_without_inventing_authority(monkeypatch):
    seen = {}
    provider = object()
    analysis = object()
    manifest = object()
    projection = object()

    def fake_select(**kwargs):
        seen["selector"] = kwargs
        return provider

    monkeypatch.setattr(finance_runtime, "select_financial_data_provider", fake_select)
    monkeypatch.setattr(
        finance_runtime,
        "build_comparable_company_analysis",
        lambda **kwargs: analysis,
    )
    monkeypatch.setattr(
        finance_runtime,
        "build_finance_observation_evidence_manifest",
        lambda **kwargs: manifest,
    )
    monkeypatch.setattr(
        finance_runtime,
        "build_finance_report_projection",
        lambda **kwargs: projection,
    )

    result = finance_runtime.build_finance_runtime_projection(
        provider_mode="frozen-demo",
        definition=object(),
        documents=(),
        entries=(),
    )

    assert result is projection
    assert seen["selector"] == {
        "mode": "frozen-demo",
        "dataset_path": None,
        "expected_provider_id": None,
        "expected_dataset_id": None,
        "expected_dataset_version": None,
    }


@pytest.mark.parametrize(
    ("failing_stage", "expected_calls"),
    (
        ("select", ("select",)),
        ("analysis", ("select", "analysis")),
        ("evidence", ("select", "analysis", "evidence")),
        ("projection", ("select", "analysis", "evidence", "projection")),
    ),
)
def test_runtime_fails_closed_at_exact_stage(monkeypatch, failing_stage, expected_calls):
    calls = []
    provider = object()
    analysis = object()
    manifest = object()

    def stage(name, result):
        def invoke(**kwargs):
            calls.append(name)
            if name == failing_stage:
                raise RuntimeError(name)
            return result
        return invoke

    monkeypatch.setattr(
        finance_runtime,
        "select_financial_data_provider",
        stage("select", provider),
    )
    monkeypatch.setattr(
        finance_runtime,
        "build_comparable_company_analysis",
        stage("analysis", analysis),
    )
    monkeypatch.setattr(
        finance_runtime,
        "build_finance_observation_evidence_manifest",
        stage("evidence", manifest),
    )
    monkeypatch.setattr(
        finance_runtime,
        "build_finance_report_projection",
        stage("projection", object()),
    )

    with pytest.raises(RuntimeError, match=failing_stage):
        finance_runtime.build_finance_runtime_projection(
            provider_mode="frozen-demo",
            definition=object(),
            documents=(),
            entries=(),
        )

    assert tuple(calls) == expected_calls


def test_runtime_public_signature_is_keyword_only_and_projection_typed():
    signature = inspect.signature(finance_runtime.build_finance_runtime_projection)

    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert tuple(signature.parameters) == (
        "provider_mode",
        "definition",
        "documents",
        "entries",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    )
    assert signature.return_annotation == "FinanceReportProjection"
