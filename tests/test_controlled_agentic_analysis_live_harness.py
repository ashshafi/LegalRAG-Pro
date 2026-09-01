from __future__ import annotations

from types import SimpleNamespace

import pytest

import controlled_agentic_analysis_live_harness as harness
from controlled_agentic_analysis_live_harness import ControlledLiveHarnessError
from controlled_agentic_analysis_openai import openai_engine_identity


MODEL = "gpt-test"


def run(identity=None):
    return SimpleNamespace(
        analysis_engine_identity=identity or openai_engine_identity(MODEL)
    )


def test_caa1_harness_rejects_engine_identity_mismatch_before_runner(monkeypatch):
    called = {"runner": 0}

    def fake_runner(**kwargs):
        called["runner"] += 1

    monkeypatch.setattr(
        harness,
        "run_controlled_contradiction_adverse_analysis",
        fake_runner,
    )

    with pytest.raises(ControlledLiveHarnessError, match="identity"):
        harness.run_caa1_openai_dry_run(
            run=run("wrong"),
            evidence_inputs=(),
            client=object(),
            model=MODEL,
        )
    assert called["runner"] == 0


def test_caa1_harness_calls_sealed_runner_without_publication(monkeypatch):
    sentinel = (object(),)
    captured = {}

    monkeypatch.setattr(
        harness,
        "make_caa1_openai_analysis_engine",
        lambda **kwargs: "engine",
    )

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        harness,
        "run_controlled_contradiction_adverse_analysis",
        fake_runner,
    )

    result = harness.run_caa1_openai_dry_run(
        run=run(),
        evidence_inputs=("evidence",),
        client="client",
        model=MODEL,
        authority_loader="loader",
        authority_serializer="serializer",
    )

    assert result is sentinel
    assert captured["analysis_engine"] == "engine"
    assert captured["evidence_inputs"] == ("evidence",)
    assert captured["authority_loader"] == "loader"


def test_caa2_harness_rejects_engine_identity_mismatch_before_executor(monkeypatch):
    called = {"executor": 0}

    def fake_executor(**kwargs):
        called["executor"] += 1

    monkeypatch.setattr(harness, "execute_caa2_analysis", fake_executor)

    with pytest.raises(ControlledLiveHarnessError, match="identity"):
        harness.run_caa2_openai_dry_run(
            run=run("wrong"),
            authority=object(),
            evidence_texts=(),
            client=object(),
            model=MODEL,
        )
    assert called["executor"] == 0


def test_caa2_harness_calls_sealed_executor_without_publication(monkeypatch):
    sentinel = object()
    captured = {}

    monkeypatch.setattr(
        harness,
        "make_caa2_openai_analysis_engine",
        lambda **kwargs: "engine",
    )

    def fake_executor(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(harness, "execute_caa2_analysis", fake_executor)

    result = harness.run_caa2_openai_dry_run(
        run=run(),
        authority="authority",
        evidence_texts=("evidence",),
        client="client",
        model=MODEL,
        authority_loader="loader",
    )

    assert result is sentinel
    assert captured["analysis_engine"] == "engine"
    assert captured["evidence_texts"] == ("evidence",)
    assert captured["active_authority_loader"] == "loader"


def test_harness_module_imports_no_publication_functions():
    names = set(vars(harness))
    assert "publish_caa2_analysis" not in names
    assert "publish_agentic_analysis_run" not in names
