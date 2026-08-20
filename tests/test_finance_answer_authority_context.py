from dataclasses import replace

import pytest

from finance_answer_authority import build_runtime_finance_answer_context
from finance_evidence import FinanceDocumentEvidenceCoverage
from test_finance_answer_authority_models import analysis, manifest_for


def test_context_projects_f4_and_f5_exact_cardinalities_and_metadata():
    a = analysis(); m = manifest_for(a)
    ctx = build_runtime_finance_answer_context(analysis=a, evidence_manifest=m)
    assert ctx.workspace_id == a.workspace_id
    assert ctx.analysis_id == a.analysis_id
    assert ctx.as_of == a.as_of
    assert ctx.document_evidence_manifest_id == m.document_evidence_manifest_id
    assert ctx.document_evidence_coverage is FinanceDocumentEvidenceCoverage.NOT_APPLICABLE
    assert len(ctx.members) == len(a.definition.members) == 6
    assert len(ctx.cells) == len(a.cells) == 54
    assert len(ctx.summaries) == len(a.summaries) == 9
    assert len(ctx.positions) == len(a.positions) == 9
    assert len(ctx.calculations) == len(a.calculation_results) == 42
    assert len(ctx.evidence_bindings) == len(a.source_observations) == 66


def test_context_calculation_observation_provenance_is_derived_through_f4_facts():
    a = analysis(); ctx = build_runtime_finance_answer_context(analysis=a, evidence_manifest=manifest_for(a))
    fact_by_id = {item.fact_id: item for item in a.source_facts}
    result_by_id = {item.result_id: item for item in a.calculation_results}
    for calc in ctx.calculations:
        source = result_by_id[calc.result_id]
        expected = tuple(sorted({oid for fid in source.input_fact_ids for oid in fact_by_id[fid].observation_ids}))
        assert calc.observation_ids == expected


def test_context_has_one_f5_evidence_row_per_f4_observation_and_no_source_text_or_pdf_bytes():
    a = analysis(); ctx = build_runtime_finance_answer_context(analysis=a, evidence_manifest=manifest_for(a))
    assert {item.observation_id for item in ctx.evidence_bindings} == {item.observation_id for item in a.source_observations}
    for item in ctx.evidence_bindings:
        assert not hasattr(item, "exact_bound_text")
        assert not hasattr(item, "exact_page_text")
        assert not hasattr(item, "original_pdf_bytes")


def test_context_fails_closed_for_wrong_f5_analysis_binding():
    a = analysis(); m = manifest_for(a)
    bad = replace(m, source_analysis_id="sha256:" + "1" * 64)
    with pytest.raises(ValueError):
        build_runtime_finance_answer_context(analysis=a, evidence_manifest=bad)


def test_context_preserves_all_f5_source_channels_and_binding_classes_without_blob_resolution():
    from finance_evidence import ObservationDocumentBindingClass, ObservationSourceChannel
    from test_finance_answer_authority_models import mixed_manifest_for
    a = analysis(); m = mixed_manifest_for(a)
    ctx = build_runtime_finance_answer_context(analysis=a, evidence_manifest=m)
    pairs = {(item.source_channel, item.binding_class) for item in ctx.evidence_bindings}
    assert (ObservationSourceChannel.DOCUMENT, ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND) in pairs
    assert (ObservationSourceChannel.DOCUMENT, ObservationDocumentBindingClass.DOCUMENT_UNBOUND) in pairs
    assert (ObservationSourceChannel.STRUCTURED_PROVIDER, ObservationDocumentBindingClass.NOT_APPLICABLE) in pairs
    assert (ObservationSourceChannel.MARKET, ObservationDocumentBindingClass.NOT_APPLICABLE) in pairs
    bound = next(item for item in ctx.evidence_bindings if item.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND)
    assert bound.document_snapshot_id is not None and bound.page_number == 1 and bound.bound_text_sha256 is not None
    assert not hasattr(bound, "exact_bound_text") and not hasattr(bound, "original_pdf_bytes")
