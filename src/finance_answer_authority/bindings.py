"""Strict model-output binding validation and deterministic Finance F6 rendering."""
from __future__ import annotations

import json
from decimal import Decimal

from finance_calculations.models import AnalyticalStatus
from finance_comps.models import CellValueClassification

from .models import (
    FinanceAnswerMode,
    FinanceAnswerStatementBinding,
    FinanceClaimType,
    FinanceContentClassification,
    FinanceSummarySelector,
    FinanceUnavailableReason,
    RuntimeFinanceAnswerAuthorityContext,
    ValidatedFinanceAnswer,
)
from .validation import validate_runtime_finance_answer_context

_ROOT_FIELDS = {"analysis_id", "document_evidence_manifest_id", "mode", "claims", "unavailable_reason"}
_CLAIM_FIELDS = {"claim_id", "claim_type", "authority_id", "selector"}

_UNAVAILABLE_TEXT = {
    FinanceUnavailableReason.OUTSIDE_FROZEN_AUTHORITY: "The requested conclusion is outside the frozen F1-F5 finance authority.",
    FinanceUnavailableReason.METRIC_NOT_ESTABLISHED: "The requested metric is not established in the frozen finance authority.",
    FinanceUnavailableReason.CALCULATION_NOT_PRESENT: "The requested calculation is not present in the frozen finance authority.",
    FinanceUnavailableReason.ANALYST_INTERPRETATION_NOT_AVAILABLE: "No governed analyst interpretation is available in the frozen F1-F5 finance authority.",
    FinanceUnavailableReason.QUESTION_AMBIGUOUS: "The question is ambiguous relative to the frozen finance authority.",
}


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json(raw_output: str):
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ValueError("raw_output must be non-empty JSON text.")
    try:
        return json.loads(
            raw_output,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {value}")),
        )
    except json.JSONDecodeError as exc:
        raise ValueError("raw_output must be strict JSON.") from exc


def _format_value(value: Decimal, currency: str | None, unit: str | None) -> str:
    pieces = [str(value)]
    if currency is not None:
        pieces.append(currency)
    if unit is not None:
        pieces.append(unit)
    return " ".join(pieces)


def _evidence_ids(context, observation_ids: tuple[str, ...]) -> tuple[str, ...]:
    by_observation = {item.observation_id: item.evidence_binding_id for item in context.evidence_bindings}
    return tuple(by_observation[item] for item in observation_ids)


def _summary_observations(context, summary) -> tuple[str, ...]:
    cells = {item.cell_id: item for item in context.cells}
    return tuple(sorted({oid for cell_id in summary.input_cell_ids for oid in cells[cell_id].observation_ids}))


def _position_observations(context, position) -> tuple[str, ...]:
    cells = {item.cell_id: item for item in context.cells}
    summaries = {item.summary_id: item for item in context.summaries}
    summary = summaries[position.peer_summary_id]
    return tuple(sorted(set(cells[position.target_cell_id].observation_ids) | set(_summary_observations(context, summary))))


def _classifications_for_cell(cell):
    if cell.value_classification is CellValueClassification.SOURCE_FACT:
        return (FinanceContentClassification.SOURCE_FACT, FinanceContentClassification.AI_GENERATED_COMMENTARY)
    return (
        FinanceContentClassification.DERIVED_METRIC,
        FinanceContentClassification.MODEL_CALCULATION,
        FinanceContentClassification.AI_GENERATED_COMMENTARY,
    )


def _claim_binding(context, claim_id, claim_type, authority_id, selector):
    members = {item.member_id: item for item in context.members}
    cells = {item.cell_id: item for item in context.cells}
    summaries = {item.summary_id: item for item in context.summaries}
    positions = {item.position_id: item for item in context.positions}
    calculations = {item.result_id: item for item in context.calculations}
    evidence = {item.evidence_binding_id: item for item in context.evidence_bindings}

    if claim_type is FinanceClaimType.ANALYSIS_AS_OF:
        if authority_id != context.analysis_id or selector is not None:
            raise ValueError("ANALYSIS_AS_OF must reference the exact analysis_id with selector null.")
        statement = f"The comparable-company analysis is frozen as of {context.as_of.isoformat().replace('+00:00','Z')}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, None, statement, (FinanceContentClassification.AI_GENERATED_COMMENTARY,), None, (), ())

    if claim_type is FinanceClaimType.DATASET_IDENTITY:
        if authority_id != context.analysis_id or selector is not None:
            raise ValueError("DATASET_IDENTITY must reference the exact analysis_id with selector null.")
        statement = f"The analysis uses provider {context.provider_id}, dataset {context.dataset_id} version {context.dataset_version}, identity {context.dataset_identity}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, None, statement, (FinanceContentClassification.AI_GENERATED_COMMENTARY,), None, (), ())

    if claim_type is FinanceClaimType.MEMBER_STATUS:
        if selector is not None or authority_id not in members:
            raise ValueError("MEMBER_STATUS must reference one exact member_id with selector null.")
        item = members[authority_id]
        statement = f"{item.company_name} is the {item.role.value} and is {item.inclusion_state.value} in the governed comparable set."
        if item.exclusion_reason is not None:
            statement += f" Exclusion reason: {item.exclusion_reason}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, None, statement, (FinanceContentClassification.AI_GENERATED_COMMENTARY,), None, (), ())

    if claim_type in {FinanceClaimType.CELL_VALUE, FinanceClaimType.CELL_STATUS}:
        if selector is not None or authority_id not in cells:
            raise ValueError("CELL claim must reference one exact cell_id with selector null.")
        item = cells[authority_id]
        classifications = _classifications_for_cell(item)
        observations = item.observation_ids
        evidence_ids = _evidence_ids(context, observations)
        if claim_type is FinanceClaimType.CELL_VALUE:
            if item.status is not AnalyticalStatus.ESTABLISHED or item.value is None or item.unit is None:
                raise ValueError("CELL_VALUE requires an ESTABLISHED cell with a value and unit.")
            period = f" for {item.financial_period_label}" if item.financial_period_label is not None else ""
            statement = f"{item.company_name} {item.metric_code} is {_format_value(item.value, item.currency, item.unit)}{period}, with status {item.status.value}."
        else:
            note = f": {item.note}" if item.note is not None else ""
            statement = f"{item.company_name} {item.metric_code} has status {item.status.value}{note}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, None, statement, classifications, item.status, observations, evidence_ids)

    if claim_type in {FinanceClaimType.PEER_SUMMARY_VALUE, FinanceClaimType.PEER_SUMMARY_STATUS}:
        if authority_id not in summaries:
            raise ValueError("Peer-summary claim must reference one exact summary_id.")
        item = summaries[authority_id]
        observations = _summary_observations(context, item)
        evidence_ids = _evidence_ids(context, observations)
        classifications = (
            FinanceContentClassification.DERIVED_METRIC,
            FinanceContentClassification.MODEL_CALCULATION,
            FinanceContentClassification.AI_GENERATED_COMMENTARY,
        )
        if claim_type is FinanceClaimType.PEER_SUMMARY_VALUE:
            if item.status is not AnalyticalStatus.ESTABLISHED:
                raise ValueError("PEER_SUMMARY_VALUE requires an ESTABLISHED summary.")
            if not isinstance(selector, FinanceSummarySelector):
                raise ValueError("PEER_SUMMARY_VALUE requires one exact statistic selector.")
            value = getattr(item, selector.value.lower())
            if value is None or item.unit is None:
                raise ValueError("Selected peer summary statistic is unavailable.")
            statement = (
                f"For included peers, {selector.value} {item.metric_code} is {_format_value(value, item.currency, item.unit)} as of "
                f"{item.as_of.isoformat().replace('+00:00','Z')}; {item.established_peer_count}/{item.selected_peer_count} selected peer values are established."
            )
        else:
            if selector is not None:
                raise ValueError("PEER_SUMMARY_STATUS requires selector null.")
            note = f": {item.note}" if item.note is not None else ""
            statement = f"Peer summary {item.metric_code} has status {item.status.value}{note}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, selector, statement, classifications, item.status, observations, evidence_ids)

    if claim_type is FinanceClaimType.TARGET_PEER_RELATIONSHIP:
        if selector is not None or authority_id not in positions:
            raise ValueError("TARGET_PEER_RELATIONSHIP must reference one exact position_id with selector null.")
        item = positions[authority_id]
        if item.status is not AnalyticalStatus.ESTABLISHED or item.relationship is None:
            raise ValueError("TARGET_PEER_RELATIONSHIP requires an established relationship.")
        target_cell = cells[item.target_cell_id]
        observations = _position_observations(context, item)
        statement = f"{target_cell.company_name} is {item.relationship.value} on {item.metric_code} relative to the governed peer median."
        return FinanceAnswerStatementBinding(
            claim_id,
            claim_type,
            authority_id,
            None,
            statement,
            (FinanceContentClassification.MODEL_CALCULATION, FinanceContentClassification.AI_GENERATED_COMMENTARY),
            item.status,
            observations,
            _evidence_ids(context, observations),
        )

    if claim_type is FinanceClaimType.CALCULATION_FORMULA:
        if selector is not None or authority_id not in calculations:
            raise ValueError("CALCULATION_FORMULA must reference one exact F4-contained result_id with selector null.")
        item = calculations[authority_id]
        statement = f"{item.company_name} {item.metric_code} uses calculation {item.calculation_code} version {item.calculation_version} with frozen formula: {item.formula}."
        return FinanceAnswerStatementBinding(
            claim_id,
            claim_type,
            authority_id,
            None,
            statement,
            (FinanceContentClassification.MODEL_CALCULATION, FinanceContentClassification.AI_GENERATED_COMMENTARY),
            item.status,
            item.observation_ids,
            _evidence_ids(context, item.observation_ids),
        )

    if claim_type is FinanceClaimType.EVIDENCE_BINDING:
        if selector is not None or authority_id not in evidence:
            raise ValueError("EVIDENCE_BINDING must reference one exact evidence_binding_id with selector null.")
        item = evidence[authority_id]
        publication = item.publication_at.isoformat().replace('+00:00','Z') if item.publication_at is not None else "NONE"
        statement = (
            f"Observation {item.observation_id} from provider {item.provider}, source {item.source_id}, version {item.source_version}, publication {publication} "
            f"is classified {item.source_channel.value} / {item.binding_class.value}."
        )
        if item.document_snapshot_id is not None:
            statement += f" Document snapshot {item.document_snapshot_id}, page {item.page_number}, bound-text SHA256 {item.bound_text_sha256}."
        if item.note is not None:
            statement += f" Note: {item.note}."
        return FinanceAnswerStatementBinding(
            claim_id,
            claim_type,
            authority_id,
            None,
            statement,
            (FinanceContentClassification.AI_GENERATED_COMMENTARY,),
            None,
            (item.observation_id,),
            (item.evidence_binding_id,),
        )

    if claim_type is FinanceClaimType.EVIDENCE_COVERAGE:
        if authority_id != context.document_evidence_manifest_id or selector is not None:
            raise ValueError("EVIDENCE_COVERAGE must reference the exact F5 manifest ID with selector null.")
        statement = f"The F5 document-evidence coverage is {context.document_evidence_coverage.value}."
        return FinanceAnswerStatementBinding(claim_id, claim_type, authority_id, None, statement, (FinanceContentClassification.AI_GENERATED_COMMENTARY,), None, (), ())

    raise ValueError("Unsupported Finance F6 claim type.")


def validate_finance_answer_output(*, raw_output: str, context: RuntimeFinanceAnswerAuthorityContext) -> ValidatedFinanceAnswer:
    validate_runtime_finance_answer_context(context)
    payload = _parse_json(raw_output)
    if not isinstance(payload, dict) or set(payload) != _ROOT_FIELDS:
        raise ValueError("Finance F6 root JSON fields are not exact.")
    if payload["analysis_id"] != context.analysis_id:
        raise ValueError("analysis_id does not match frozen F4 authority.")
    if payload["document_evidence_manifest_id"] != context.document_evidence_manifest_id:
        raise ValueError("document_evidence_manifest_id does not match frozen F5 authority.")
    try:
        mode = FinanceAnswerMode(payload["mode"])
    except (TypeError, ValueError) as exc:
        raise ValueError("mode is invalid.") from exc
    claims = payload["claims"]
    if not isinstance(claims, list):
        raise ValueError("claims must be an array.")

    if mode is FinanceAnswerMode.UNAVAILABLE:
        if claims:
            raise ValueError("UNAVAILABLE must contain no claims.")
        try:
            reason = FinanceUnavailableReason(payload["unavailable_reason"])
        except (TypeError, ValueError) as exc:
            raise ValueError("UNAVAILABLE requires one exact unavailable reason.") from exc
        return ValidatedFinanceAnswer(mode, _UNAVAILABLE_TEXT[reason], (), (), (), (), reason)

    if not claims:
        raise ValueError("ANSWER requires at least one claim.")
    if payload["unavailable_reason"] is not None:
        raise ValueError("ANSWER requires unavailable_reason null.")

    bindings = []
    claim_ids = set()
    semantic_claims = set()
    for raw_claim in claims:
        if not isinstance(raw_claim, dict) or set(raw_claim) != _CLAIM_FIELDS:
            raise ValueError("Finance F6 claim JSON fields are not exact.")
        claim_id = raw_claim["claim_id"]
        if not isinstance(claim_id, str) or not claim_id or claim_id != claim_id.strip():
            raise ValueError("claim_id must be non-empty trimmed text.")
        if claim_id in claim_ids:
            raise ValueError("Duplicate claim_id.")
        claim_ids.add(claim_id)
        authority_id = raw_claim["authority_id"]
        if not isinstance(authority_id, str) or not authority_id or authority_id != authority_id.strip():
            raise ValueError("authority_id must be non-empty trimmed text.")
        try:
            claim_type = FinanceClaimType(raw_claim["claim_type"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Unknown claim_type.") from exc
        selector_raw = raw_claim["selector"]
        selector = None
        if selector_raw is not None:
            try:
                selector = FinanceSummarySelector(selector_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid selector.") from exc
        semantic_key = (claim_type.value, authority_id, None if selector is None else selector.value)
        if semantic_key in semantic_claims:
            raise ValueError("Duplicate semantic claim selection.")
        semantic_claims.add(semantic_key)
        bindings.append(_claim_binding(context, claim_id, claim_type, authority_id, selector))

    binding_tuple = tuple(bindings)
    authority_ids = tuple(dict.fromkeys(item.authority_id for item in binding_tuple))
    observation_ids = tuple(dict.fromkeys(oid for item in binding_tuple for oid in item.observation_ids))
    evidence_ids = tuple(dict.fromkeys(eid for item in binding_tuple for eid in item.evidence_binding_ids))
    answer = "\n".join(item.statement_text for item in binding_tuple)
    return ValidatedFinanceAnswer(mode, answer, binding_tuple, authority_ids, observation_ids, evidence_ids, None)
