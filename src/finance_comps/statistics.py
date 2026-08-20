"""Deterministic peer aggregation for Finance F4."""

from __future__ import annotations

from decimal import Decimal

from finance_calculations import AnalyticalStatus, CalculationClassification
from finance_domain import derive_finance_id

from .models import (
    PEER_SUMMARY_SCHEMA_VERSION,
    CellValueClassification,
    ComparableMetricCell,
    PeerMetricSummary,
)
from .serialization import peer_metric_summary_identity_payload_to_dict

_BLOCKING_PRECEDENCE = (
    AnalyticalStatus.SOURCE_CONFLICT,
    AnalyticalStatus.ASSUMPTION_REQUIRED,
    AnalyticalStatus.STALE_DATA,
)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def build_peer_metric_summary(
    *,
    workspace_id: str,
    metric_code: str,
    selected_peer_cells: tuple[ComparableMetricCell, ...],
    as_of,
) -> PeerMetricSummary:
    """Aggregate included peers only; never infer peer exclusion from data state."""

    cells = tuple(selected_peer_cells)
    selected_count = len(cells)
    established = tuple(cell for cell in cells if cell.status is AnalyticalStatus.ESTABLISHED)
    unavailable = tuple(cell for cell in cells if cell.status is not AnalyticalStatus.ESTABLISHED)

    status: AnalyticalStatus
    note: str | None
    mean = median = minimum = maximum = None
    currency = unit = None
    input_ids: tuple[str, ...] = ()

    blocker = next(
        (candidate for candidate in _BLOCKING_PRECEDENCE if any(cell.status is candidate for cell in cells)),
        None,
    )
    if blocker is not None:
        status = blocker
        note = f"Included peer cells contain blocking status {blocker.value}."
    elif len(established) < 2:
        status = AnalyticalStatus.INSUFFICIENT_DATA
        note = "Fewer than two established included-peer values are available."
    else:
        semantics = {(cell.currency, cell.unit) for cell in established}
        if len(semantics) != 1:
            status = AnalyticalStatus.ASSUMPTION_REQUIRED
            note = "Peer currency/unit normalisation would require an assumption."
        else:
            status = AnalyticalStatus.ESTABLISHED
            note = None
            currency, unit = next(iter(semantics))
            values = tuple(cell.value for cell in established)
            assert all(value is not None for value in values)
            numeric = tuple(value for value in values if value is not None)
            mean = sum(numeric, Decimal(0)) / Decimal(len(numeric))
            median = _median(numeric)
            minimum = min(numeric)
            maximum = max(numeric)
            input_ids = tuple(sorted(cell.cell_id for cell in established))

    provisional = PeerMetricSummary(
        schema_version=PEER_SUMMARY_SCHEMA_VERSION,
        workspace_id=workspace_id,
        metric_code=metric_code,
        status=status,
        value_classification=CellValueClassification.DERIVED_METRIC,
        calculation_classification=CalculationClassification.MODEL_CALCULATION,
        selected_peer_count=selected_count,
        established_peer_count=len(established),
        currency=currency,
        unit=unit,
        mean=mean,
        median=median,
        minimum=minimum,
        maximum=maximum,
        input_cell_ids=input_ids,
        unavailable_cell_ids=tuple(sorted(cell.cell_id for cell in unavailable)),
        as_of=as_of,
        note=note,
        summary_id="sha256:" + "0" * 64,
    )
    summary_id = derive_finance_id(peer_metric_summary_identity_payload_to_dict(provisional))
    return PeerMetricSummary(**{**provisional.__dict__} if hasattr(provisional, "__dict__") else {
        "schema_version": provisional.schema_version,
        "workspace_id": provisional.workspace_id,
        "metric_code": provisional.metric_code,
        "status": provisional.status,
        "value_classification": provisional.value_classification,
        "calculation_classification": provisional.calculation_classification,
        "selected_peer_count": provisional.selected_peer_count,
        "established_peer_count": provisional.established_peer_count,
        "currency": provisional.currency,
        "unit": provisional.unit,
        "mean": provisional.mean,
        "median": provisional.median,
        "minimum": provisional.minimum,
        "maximum": provisional.maximum,
        "input_cell_ids": provisional.input_cell_ids,
        "unavailable_cell_ids": provisional.unavailable_cell_ids,
        "as_of": provisional.as_of,
        "note": provisional.note,
        "summary_id": summary_id,
    })


__all__ = ["build_peer_metric_summary"]
