from __future__ import annotations

import inspect
from types import SimpleNamespace

import controlled_agentic_analysis_live_harness as harness


def test_caa2_live_harness_exposes_optional_candidate_scope():
    signature = inspect.signature(harness.run_caa2_openai_dry_run)
    parameter = signature.parameters["candidate_scope"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_caa2_live_harness_forwards_candidate_scope_exactly(monkeypatch):
    model = "scope-forwarding-test-model"
    run = SimpleNamespace(
        analysis_engine_identity=harness.openai_engine_identity(model),
    )
    client = object()
    authority = object()
    evidence_texts = (object(),)
    scope = ("issue-analysis-id", "element-id")
    sentinel_engine = object()
    sentinel_result = object()
    captured = {}

    def fake_engine_factory(*, client, model):
        captured["factory_client"] = client
        captured["factory_model"] = model
        return sentinel_engine

    def fake_execute(**kwargs):
        captured["execute_kwargs"] = kwargs
        return sentinel_result

    monkeypatch.setattr(
        harness,
        "make_caa2_openai_analysis_engine",
        fake_engine_factory,
    )
    monkeypatch.setattr(
        harness,
        "execute_caa2_analysis",
        fake_execute,
    )

    result = harness.run_caa2_openai_dry_run(
        run=run,
        authority=authority,
        evidence_texts=evidence_texts,
        client=client,
        model=model,
        candidate_scope=scope,
    )

    assert result is sentinel_result
    assert captured["factory_client"] is client
    assert captured["factory_model"] == model

    execute_kwargs = captured["execute_kwargs"]
    assert execute_kwargs["run"] is run
    assert execute_kwargs["authority"] is authority
    assert execute_kwargs["evidence_texts"] == evidence_texts
    assert execute_kwargs["analysis_engine"] is sentinel_engine
    assert execute_kwargs["candidate_scope"] == scope
    assert execute_kwargs["active_authority_loader"] is None
