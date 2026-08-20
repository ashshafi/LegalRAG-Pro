"""Deterministic projection-only navigation index for the Finance F7B1 workspace."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Iterable, Mapping
import unicodedata

from finance_reporting import FinanceReportProjection, validate_finance_report_projection

FINANCE_WORKSPACE_INDEX_VERSION: Final[str] = "finance-workspace-index/1.0"
_ALLOWED_KINDS: Final[frozenset[str]] = frozenset(
    {"member", "cell", "summary", "position", "calculation", "evidence", "limitation"}
)


class FinanceWorkspaceIndexError(ValueError):
    """Raised when deterministic Finance workspace navigation integrity fails."""


@dataclass(frozen=True, slots=True, order=True)
class FinanceWorkspaceObjectKey:
    """Exact navigation identity for one frozen Finance report object."""

    kind: str
    primary_id: str

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unsupported Finance workspace object kind {self.kind!r}.")
        if not str(self.primary_id).strip():
            raise ValueError("primary_id must not be empty.")


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceBacklink:
    """Mechanical reversal of one explicit frozen source field."""

    source: FinanceWorkspaceObjectKey
    source_field: str

    def __post_init__(self) -> None:
        if not str(self.source_field).strip():
            raise ValueError("source_field must not be empty.")


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceIndex:
    """Immutable ephemeral index over one validated FinanceReportProjection."""

    version: str
    report_projection_id: str
    projection_payload_sha256: str
    manifest_id: str

    members_by_id: Mapping[str, object]
    cells_by_id: Mapping[str, object]
    summaries_by_id: Mapping[str, object]
    positions_by_id: Mapping[str, object]
    calculations_by_id: Mapping[str, object]
    evidence_by_id: Mapping[str, object]
    limitations_by_id: Mapping[str, object]

    object_by_key: Mapping[FinanceWorkspaceObjectKey, object]
    outgoing: Mapping[FinanceWorkspaceObjectKey, tuple[tuple[str, FinanceWorkspaceObjectKey], ...]]
    backlinks: Mapping[FinanceWorkspaceObjectKey, tuple[FinanceWorkspaceBacklink, ...]]

    member_keys: tuple[FinanceWorkspaceObjectKey, ...]
    cell_keys: tuple[FinanceWorkspaceObjectKey, ...]
    summary_keys: tuple[FinanceWorkspaceObjectKey, ...]
    position_keys: tuple[FinanceWorkspaceObjectKey, ...]
    calculation_keys: tuple[FinanceWorkspaceObjectKey, ...]
    evidence_keys: tuple[FinanceWorkspaceObjectKey, ...]
    limitation_keys: tuple[FinanceWorkspaceObjectKey, ...]

    cells_by_company: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    cells_by_metric: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    cells_by_status: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    evidence_by_observation: Mapping[str, FinanceWorkspaceObjectKey]
    evidence_by_company: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    evidence_by_source_channel: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    evidence_by_binding_class: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]
    limitations_by_authority: Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]


def _readonly(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(mapping))


def _readonly_tuple_map(mapping: Mapping[str, list[FinanceWorkspaceObjectKey]]) -> Mapping[str, tuple[FinanceWorkspaceObjectKey, ...]]:
    return MappingProxyType({key: tuple(values) for key, values in mapping.items()})


def _normalise_literal(value: object) -> str:
    return unicodedata.normalize("NFC", str(value)).casefold()


def _candidate_strings(values: Iterable[object]) -> Iterable[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, tuple):
            yield from _candidate_strings(value)
            continue
        yield str(value)


def literal_query_matches(query: str, candidate_values: Iterable[object]) -> bool:
    """Casefolded NFC literal substring match over already-projected values only."""

    prepared = unicodedata.normalize("NFC", str(query).strip()).casefold()
    if not prepared:
        return True
    return any(prepared in _normalise_literal(value) for value in _candidate_strings(candidate_values))


def _unique_by_id(values, attr: str, label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        identifier = getattr(value, attr)
        if identifier in result:
            raise FinanceWorkspaceIndexError(f"Duplicate {label}: {identifier!r}.")
        result[identifier] = value
    return result


def _keys(kind: str, ordered_ids: tuple[str, ...]) -> tuple[FinanceWorkspaceObjectKey, ...]:
    return tuple(FinanceWorkspaceObjectKey(kind, identifier) for identifier in ordered_ids)


def _assert_inventory(keys: tuple[FinanceWorkspaceObjectKey, ...], mapping: Mapping[str, object], label: str) -> None:
    ordered_ids = tuple(key.primary_id for key in keys)
    if len(ordered_ids) != len(set(ordered_ids)):
        raise FinanceWorkspaceIndexError(f"Manifest {label} inventory contains duplicate IDs.")
    if set(ordered_ids) != set(mapping):
        raise FinanceWorkspaceIndexError(f"Manifest {label} inventory does not match projection objects.")


def build_finance_workspace_index(projection: FinanceReportProjection) -> FinanceWorkspaceIndex:
    """Build deterministic mechanical navigation indexes from one F7A projection."""

    validate_finance_report_projection(projection)

    members = _unique_by_id(projection.members, "member_id", "member_id")
    cells = _unique_by_id(projection.cells, "cell_id", "cell_id")
    summaries = _unique_by_id(projection.summaries, "summary_id", "summary_id")
    positions = _unique_by_id(projection.positions, "position_id", "position_id")
    calculations = _unique_by_id(projection.calculations, "result_id", "result_id")
    evidence = _unique_by_id(projection.evidence, "evidence_binding_id", "evidence_binding_id")
    limitations = _unique_by_id(projection.limitations, "limitation_id", "limitation_id")

    manifest = projection.manifest
    member_keys = _keys("member", manifest.ordered_member_ids)
    cell_keys = _keys("cell", manifest.ordered_cell_ids)
    summary_keys = _keys("summary", manifest.ordered_summary_ids)
    position_keys = _keys("position", manifest.ordered_position_ids)
    calculation_keys = _keys("calculation", manifest.ordered_calculation_ids)
    evidence_keys = _keys("evidence", manifest.ordered_evidence_binding_ids)
    limitation_keys = _keys("limitation", manifest.ordered_limitation_ids)

    for keyset, mapping, label in (
        (member_keys, members, "member"),
        (cell_keys, cells, "cell"),
        (summary_keys, summaries, "summary"),
        (position_keys, positions, "position"),
        (calculation_keys, calculations, "calculation"),
        (evidence_keys, evidence, "evidence"),
        (limitation_keys, limitations, "limitation"),
    ):
        _assert_inventory(keyset, mapping, label)

    member_key_by_id = {key.primary_id: key for key in member_keys}
    cell_key_by_id = {key.primary_id: key for key in cell_keys}
    summary_key_by_id = {key.primary_id: key for key in summary_keys}
    calculation_key_by_id = {key.primary_id: key for key in calculation_keys}
    evidence_key_by_id = {key.primary_id: key for key in evidence_keys}

    member_key_by_company: dict[str, FinanceWorkspaceObjectKey] = {}
    for key in member_keys:
        company_id = members[key.primary_id].company_id
        if company_id in member_key_by_company:
            raise FinanceWorkspaceIndexError(f"Multiple members use company_id {company_id!r}.")
        member_key_by_company[company_id] = key

    object_by_key: dict[FinanceWorkspaceObjectKey, object] = {}
    for keyset, mapping in (
        (member_keys, members),
        (cell_keys, cells),
        (summary_keys, summaries),
        (position_keys, positions),
        (calculation_keys, calculations),
        (evidence_keys, evidence),
        (limitation_keys, limitations),
    ):
        for key in keyset:
            if key in object_by_key:
                raise FinanceWorkspaceIndexError(f"Duplicate workspace key {key!r}.")
            object_by_key[key] = mapping[key.primary_id]

    outgoing_mut: dict[FinanceWorkspaceObjectKey, list[tuple[str, FinanceWorkspaceObjectKey]]] = {
        key: [] for key in object_by_key
    }
    backlinks_mut: dict[FinanceWorkspaceObjectKey, list[FinanceWorkspaceBacklink]] = {
        key: [] for key in object_by_key
    }

    def link(source: FinanceWorkspaceObjectKey, source_field: str, target: FinanceWorkspaceObjectKey) -> None:
        if source not in object_by_key:
            raise FinanceWorkspaceIndexError(f"Unknown workspace link source {source!r}.")
        if target not in object_by_key:
            raise FinanceWorkspaceIndexError(
                f"Frozen field {source_field} targets unknown workspace object {target!r}."
            )
        pair = (source_field, target)
        if pair not in outgoing_mut[source]:
            outgoing_mut[source].append(pair)
            backlinks_mut[target].append(FinanceWorkspaceBacklink(source=source, source_field=source_field))

    cells_by_company_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}
    cells_by_metric_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}
    cells_by_status_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}

    for key in cell_keys:
        value = cells[key.primary_id]
        cells_by_company_mut.setdefault(value.company_id, []).append(key)
        cells_by_metric_mut.setdefault(value.metric_code, []).append(key)
        cells_by_status_mut.setdefault(value.analytical_status.value, []).append(key)

    for member_key in member_keys:
        member = members[member_key.primary_id]
        for cell_key in cells_by_company_mut.get(member.company_id, []):
            link(member_key, "FinanceReportMember.company_id/FinanceReportMetricCell.company_id", cell_key)

    for key in cell_keys:
        value = cells[key.primary_id]
        member_key = member_key_by_company.get(value.company_id)
        if member_key is None:
            raise FinanceWorkspaceIndexError(f"Cell company_id {value.company_id!r} has no projected member.")
        link(key, "FinanceReportMetricCell.company_id", member_key)
        if value.source_result_id is not None:
            target = calculation_key_by_id.get(value.source_result_id)
            if target is None:
                raise FinanceWorkspaceIndexError(
                    f"Cell source_result_id {value.source_result_id!r} is not a projected calculation."
                )
            link(key, "FinanceReportMetricCell.source_result_id", target)
        for evidence_id in value.evidence_binding_ids:
            target = evidence_key_by_id.get(evidence_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Cell evidence binding {evidence_id!r} is unknown.")
            link(key, "FinanceReportMetricCell.evidence_binding_ids", target)

    for key in summary_keys:
        value = summaries[key.primary_id]
        for cell_id in value.input_cell_ids:
            target = cell_key_by_id.get(cell_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Summary input cell {cell_id!r} is unknown.")
            link(key, "FinanceReportPeerSummary.input_cell_ids", target)
        for cell_id in value.unavailable_cell_ids:
            target = cell_key_by_id.get(cell_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Summary unavailable cell {cell_id!r} is unknown.")
            link(key, "FinanceReportPeerSummary.unavailable_cell_ids", target)
        for evidence_id in value.evidence_binding_ids:
            target = evidence_key_by_id.get(evidence_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Summary evidence binding {evidence_id!r} is unknown.")
            link(key, "FinanceReportPeerSummary.evidence_binding_ids", target)

    for key in position_keys:
        value = positions[key.primary_id]
        target_cell = cell_key_by_id.get(value.target_cell_id)
        target_summary = summary_key_by_id.get(value.peer_summary_id)
        if target_cell is None or target_summary is None:
            raise FinanceWorkspaceIndexError("Target-position dependency is not projected.")
        link(key, "FinanceReportTargetPosition.target_cell_id", target_cell)
        link(key, "FinanceReportTargetPosition.peer_summary_id", target_summary)
        for evidence_id in value.evidence_binding_ids:
            target = evidence_key_by_id.get(evidence_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Position evidence binding {evidence_id!r} is unknown.")
            link(key, "FinanceReportTargetPosition.evidence_binding_ids", target)

    for key in calculation_keys:
        value = calculations[key.primary_id]
        member_key = member_key_by_company.get(value.company_id)
        if member_key is None:
            raise FinanceWorkspaceIndexError(
                f"Calculation company_id {value.company_id!r} has no projected member."
            )
        link(key, "FinanceReportCalculation.company_id", member_key)
        for evidence_id in value.evidence_binding_ids:
            target = evidence_key_by_id.get(evidence_id)
            if target is None:
                raise FinanceWorkspaceIndexError(f"Calculation evidence binding {evidence_id!r} is unknown.")
            link(key, "FinanceReportCalculation.evidence_binding_ids", target)

    authority_targets: dict[str, FinanceWorkspaceObjectKey] = {}
    for mapping in (cell_key_by_id, summary_key_by_id, evidence_key_by_id):
        authority_targets.update(mapping)
    authority_targets.update({key.primary_id: key for key in position_keys})

    limitations_by_authority_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}
    for key in limitation_keys:
        value = limitations[key.primary_id]
        limitations_by_authority_mut.setdefault(value.authority_id, []).append(key)
        target = authority_targets.get(value.authority_id)
        if target is not None:
            link(key, "FinanceReportLimitation.authority_id", target)
        elif value.authority_id != projection.source_document_evidence_manifest_id:
            raise FinanceWorkspaceIndexError(
                f"Limitation authority_id {value.authority_id!r} is neither projected nor the F5 manifest authority."
            )

    evidence_by_observation_mut: dict[str, FinanceWorkspaceObjectKey] = {}
    evidence_by_company_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}
    evidence_by_source_channel_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}
    evidence_by_binding_class_mut: dict[str, list[FinanceWorkspaceObjectKey]] = {}

    for key in evidence_keys:
        value = evidence[key.primary_id]
        if value.observation_id in evidence_by_observation_mut:
            raise FinanceWorkspaceIndexError(
                f"Multiple evidence records use observation_id {value.observation_id!r}."
            )
        evidence_by_observation_mut[value.observation_id] = key
        evidence_by_company_mut.setdefault(value.company_id, []).append(key)
        evidence_by_source_channel_mut.setdefault(value.source_channel.value, []).append(key)
        evidence_by_binding_class_mut.setdefault(value.binding_class.value, []).append(key)

    return FinanceWorkspaceIndex(
        version=FINANCE_WORKSPACE_INDEX_VERSION,
        report_projection_id=projection.report_projection_id,
        projection_payload_sha256=projection.projection_payload_sha256,
        manifest_id=projection.manifest.manifest_id,
        members_by_id=_readonly(members),
        cells_by_id=_readonly(cells),
        summaries_by_id=_readonly(summaries),
        positions_by_id=_readonly(positions),
        calculations_by_id=_readonly(calculations),
        evidence_by_id=_readonly(evidence),
        limitations_by_id=_readonly(limitations),
        object_by_key=_readonly(object_by_key),
        outgoing=_readonly({key: tuple(values) for key, values in outgoing_mut.items()}),
        backlinks=_readonly({key: tuple(values) for key, values in backlinks_mut.items()}),
        member_keys=member_keys,
        cell_keys=cell_keys,
        summary_keys=summary_keys,
        position_keys=position_keys,
        calculation_keys=calculation_keys,
        evidence_keys=evidence_keys,
        limitation_keys=limitation_keys,
        cells_by_company=_readonly_tuple_map(cells_by_company_mut),
        cells_by_metric=_readonly_tuple_map(cells_by_metric_mut),
        cells_by_status=_readonly_tuple_map(cells_by_status_mut),
        evidence_by_observation=_readonly(evidence_by_observation_mut),
        evidence_by_company=_readonly_tuple_map(evidence_by_company_mut),
        evidence_by_source_channel=_readonly_tuple_map(evidence_by_source_channel_mut),
        evidence_by_binding_class=_readonly_tuple_map(evidence_by_binding_class_mut),
        limitations_by_authority=_readonly_tuple_map(limitations_by_authority_mut),
    )


__all__ = [
    "FINANCE_WORKSPACE_INDEX_VERSION",
    "FinanceWorkspaceIndexError",
    "FinanceWorkspaceObjectKey",
    "FinanceWorkspaceBacklink",
    "FinanceWorkspaceIndex",
    "literal_query_matches",
    "build_finance_workspace_index",
]
