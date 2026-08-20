"""Fail-closed structural validation for Finance F6 runtime contexts."""
from __future__ import annotations

from finance_domain.identity import canonical_uuid, validate_sha256_id

from .models import RuntimeFinanceAnswerAuthorityContext


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label} in F6 runtime context.")


def validate_runtime_finance_answer_context(value: RuntimeFinanceAnswerAuthorityContext) -> None:
    if not isinstance(value, RuntimeFinanceAnswerAuthorityContext):
        raise ValueError("value must be RuntimeFinanceAnswerAuthorityContext.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    for field in ("analysis_id", "dataset_identity", "definition_id", "document_evidence_manifest_id"):
        validate_sha256_id(getattr(value, field), field_name=field)
    if value.as_of.tzinfo is None or value.as_of.utcoffset() is None or value.as_of.utcoffset().total_seconds() != 0:
        raise ValueError("F6 context as_of must be UTC.")
    for field in ("provider_id", "dataset_id", "dataset_version"):
        text = getattr(value, field)
        if not isinstance(text, str) or not text or text != text.strip():
            raise ValueError(f"{field} must be non-empty trimmed text.")

    _unique([item.member_id for item in value.members], "member_id")
    _unique([item.cell_id for item in value.cells], "cell_id")
    _unique([item.summary_id for item in value.summaries], "summary_id")
    _unique([item.position_id for item in value.positions], "position_id")
    _unique([item.result_id for item in value.calculations], "result_id")
    _unique([item.evidence_binding_id for item in value.evidence_bindings], "evidence_binding_id")
    _unique([item.observation_id for item in value.evidence_bindings], "observation_id evidence row")

    cell_ids = {item.cell_id for item in value.cells}
    summary_ids = {item.summary_id for item in value.summaries}
    observation_ids = {item.observation_id for item in value.evidence_bindings}

    for cell in value.cells:
        if cell.observation_ids != tuple(sorted(set(cell.observation_ids))):
            raise ValueError("F6 cell observation IDs must be canonical unique order.")
        if any(item not in observation_ids for item in cell.observation_ids):
            raise ValueError("F6 cell provenance does not resolve to F5 evidence rows.")
    for summary in value.summaries:
        if any(item not in cell_ids for item in summary.input_cell_ids + summary.unavailable_cell_ids):
            raise ValueError("F6 summary cell provenance does not resolve.")
    for position in value.positions:
        if position.target_cell_id not in cell_ids or position.peer_summary_id not in summary_ids:
            raise ValueError("F6 target-position provenance does not resolve.")
    for calculation in value.calculations:
        if calculation.observation_ids != tuple(sorted(set(calculation.observation_ids))):
            raise ValueError("F6 calculation observation IDs must be canonical unique order.")
        if any(item not in observation_ids for item in calculation.observation_ids):
            raise ValueError("F6 calculation provenance does not resolve to F5 evidence rows.")
