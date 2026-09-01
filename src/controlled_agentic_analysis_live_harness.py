"""No-publication live dry-run harness for LegalRAG CAA1 and CAA2."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from controlled_agentic_analysis import (
    CAA1EvidenceInput,
    FrozenInspectionUniverse,
    run_controlled_contradiction_adverse_analysis,
)
from controlled_agentic_analysis_gaps import (
    CAA2AnalysisResult,
    CAA2EvidenceText,
    execute_caa2_analysis,
)
from controlled_agentic_analysis_openai import (
    make_caa1_openai_analysis_engine,
    make_caa2_openai_analysis_engine,
    openai_engine_identity,
)


class ControlledLiveHarnessError(RuntimeError):
    """Raised when a dry-run configuration is not governance-bound."""


def _assert_engine_binding(
    *,
    run: FrozenInspectionUniverse,
    model: str,
) -> None:
    expected = openai_engine_identity(model)
    if run.analysis_engine_identity != expected:
        raise ControlledLiveHarnessError(
            "Frozen run analysis_engine_identity does not equal the selected "
            "OpenAI adapter identity."
        )


def run_caa1_openai_dry_run(
    *,
    run: FrozenInspectionUniverse,
    evidence_inputs: Iterable[CAA1EvidenceInput],
    client: Any,
    model: str,
    authority_loader: Callable[[str], Any] | None = None,
    authority_serializer: Callable[[Any], Any] | None = None,
):
    """Run CAA1 against a live OpenAI model without publishing observations."""

    _assert_engine_binding(run=run, model=model)
    engine = make_caa1_openai_analysis_engine(
        client=client,
        model=model,
        authority_serializer=authority_serializer,
    )
    return run_controlled_contradiction_adverse_analysis(
        run=run,
        evidence_inputs=tuple(evidence_inputs),
        analysis_engine=engine,
        authority_loader=authority_loader,
    )


def run_caa2_openai_dry_run(
    *,
    run: FrozenInspectionUniverse,
    authority: Any,
    evidence_texts: Iterable[CAA2EvidenceText],
    client: Any,
    model: str,
    candidate_scope: tuple[str, str] | None = None,
    authority_loader: Callable[[str], Any] | None = None,
) -> CAA2AnalysisResult:
    """Run CAA2 against a live OpenAI model without publishing observations."""

    _assert_engine_binding(run=run, model=model)
    engine = make_caa2_openai_analysis_engine(
        client=client,
        model=model,
    )
    return execute_caa2_analysis(
        run=run,
        authority=authority,
        evidence_texts=tuple(evidence_texts),
        analysis_engine=engine,
        candidate_scope=candidate_scope,
        active_authority_loader=authority_loader,
    )


__all__ = [
    "ControlledLiveHarnessError",
    "run_caa1_openai_dry_run",
    "run_caa2_openai_dry_run",
]
