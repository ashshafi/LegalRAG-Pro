"""Read-only historical source-evidence inventory and provenance classification.

HM1 observes frozen projections, existing immutable source-evidence records,
current Chroma rows, current document bytes, and optionally retained historical
analytical text.  It produces a deterministic audit report only.  It does not
publish, update, delete, recapture, re-index, or otherwise mutate provenance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .identity import canonical_uuid, sha256_bytes
from .models import BindingClass, EvidenceBinding, ProjectionEvidenceBindingManifest
from .store import SourceEvidenceStore, SourceEvidenceStoreError
from .validation import (
    validate_evidence_binding,
    validate_projection_evidence_binding_manifest,
    validate_source_document_manifest,
)
from .verified_retrieval import build_singleton_analysis_receipt

if TYPE_CHECKING:
    from case_reporting.models import CaseReportProjection

HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION = "historical-migration-report/1.0"
_LEGACY_CASE_ID = "__legacy__"


class HistoricalMigrationInspectionError(RuntimeError):
    """Raised when HM1 cannot produce a trustworthy read-only classification."""


class HistoricalMigrationDecisionCode(StrEnum):
    """Deterministic primary audit decision codes."""

    ALREADY_FULL_CHAIN = "already_full_chain"
    ALREADY_BOUND_WEAKER = "already_bound_weaker"
    FROZEN_PROJECTION_UNBOUND = "frozen_projection_unbound"
    FROZEN_PROJECTION_WEAKER = "frozen_projection_weaker"
    HISTORICAL_ANALYTICAL_TEXT_PROVEN = "historical_analytical_text_proven"
    CURRENT_INDEX_SNAPSHOT_ONLY = "current_index_snapshot_only"
    NO_EXACT_TEXT_AUTHORITY = "no_exact_text_authority"
    AMBIGUOUS_CHROMA_ROWS = "ambiguous_chroma_rows"
    AMBIGUOUS_CURRENT_FILES = "ambiguous_current_files"
    AMBIGUOUS_PROJECTION_CITATIONS = "ambiguous_projection_citations"
    CHROMA_CASE_MISMATCH = "chroma_case_mismatch"
    CHROMA_COORDINATE_MISMATCH = "chroma_coordinate_mismatch"
    HISTORICAL_ORIGINAL_IDENTITY_MISSING = "historical_original_identity_missing"
    M5_RECEIPT_MISSING = "m5_receipt_missing"
    LEGACY_KEY_DIFFERS_FROM_M3_KEY = "legacy_key_differs_from_m3_key"
    BINDING_KEY_COLLISION_RISK = "binding_key_collision_risk"
    M6_ALREADY_PUBLISHED = "m6_already_published"
    FORWARD_REINGESTION_CANDIDATE = "forward_reingestion_candidate"
    MALFORMED_CHROMA_ROW = "malformed_chroma_row"


@dataclass(frozen=True, slots=True)
class HistoricalMigrationSourceObservation:
    """Exact, text-free observations used to classify one evidence key."""

    current_chroma_row_count: int
    current_chroma_document_sha256: str | None
    current_chroma_metadata_fingerprint: str | None
    current_pdf_candidate_count: int
    current_pdf_sha256: str | None
    current_pdf_byte_length: int | None
    retained_historical_text_sha256: str | None


@dataclass(frozen=True, slots=True)
class HistoricalMigrationDecision:
    """One deterministic HM1 decision for one case/evidence key."""

    case_id: str
    evidence_key: str
    document_name: str | None
    document_id: str | None
    page: int | None
    chunk_id: str | None
    referencing_report_projection_ids: tuple[str, ...]
    existing_evidence_binding_id: str | None
    existing_binding_class: BindingClass | None
    existing_projection_binding_manifest_ids: tuple[str, ...]
    existing_projection_entry_classes: tuple[tuple[str, BindingClass], ...]
    observation: HistoricalMigrationSourceObservation
    m3_case_scoped_evidence_key_candidate: str | None
    same_key_as_future_m3: bool | None
    binding_key_collision_risk: bool
    maximum_historical_binding_class: BindingClass
    full_chain_projection_eligible: bool
    forward_reingestible: bool
    decision_code: HistoricalMigrationDecisionCode
    blockers: tuple[str, ...]
    recommended_next_action: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "referencing_report_projection_ids",
            tuple(self.referencing_report_projection_ids),
        )
        object.__setattr__(
            self,
            "existing_projection_binding_manifest_ids",
            tuple(self.existing_projection_binding_manifest_ids),
        )
        object.__setattr__(
            self,
            "existing_projection_entry_classes",
            tuple(self.existing_projection_entry_classes),
        )
        object.__setattr__(self, "blockers", tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class HistoricalMigrationReport:
    """Deterministic HM1 audit report.  This is not a source-store schema."""

    schema_version: str
    case_id: str
    projection_ids: tuple[str, ...]
    decisions: tuple[HistoricalMigrationDecision, ...]
    historical_migration_report_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_ids", tuple(self.projection_ids))
        object.__setattr__(self, "decisions", tuple(self.decisions))

    @property
    def projection_decisions(self) -> tuple[HistoricalMigrationDecision, ...]:
        """Return decisions referenced by at least one frozen projection."""
        return tuple(item for item in self.decisions if item.referencing_report_projection_ids)

    @property
    def non_projected_decisions(self) -> tuple[HistoricalMigrationDecision, ...]:
        """Return current case-index rows not referenced by supplied projections."""
        return tuple(item for item in self.decisions if not item.referencing_report_projection_ids)

    @property
    def forward_reingestion_decisions(self) -> tuple[HistoricalMigrationDecision, ...]:
        """Return document/evidence decisions with a unique current PDF candidate."""
        return tuple(item for item in self.decisions if item.forward_reingestible)


@dataclass(frozen=True, slots=True)
class _ChromaRow:
    row_id: str
    document: str | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ProjectionCitationObservation:
    report_projection_id: str
    evidence_key: str
    document_name: str
    document_id: str | None
    page: int | None
    chunk_id: str | None


@dataclass(frozen=True, slots=True)
class _ProjectionState:
    report_projection_id: str
    binding_manifest: ProjectionEvidenceBindingManifest | None


def inspect_historical_evidence(
    *,
    case_id: str,
    projections: tuple["CaseReportProjection", ...],
    collection: object,
    current_documents_root: Path | None = None,
    retained_analytical_text: Mapping[str, str] | None = None,
    store: SourceEvidenceStore | None = None,
) -> HistoricalMigrationReport:
    """Inspect historical evidence without mutating any project or source state.

    The returned report classifies only what the supplied/current evidence can
    prove.  It never publishes a binding, receipt, manifest, Chroma row, or
    projection artifact.
    """
    canonical_case = canonical_uuid(case_id, field_name="case_id")
    projection_values = tuple(projections)
    target_store = store if store is not None else SourceEvidenceStore()
    historical_text = retained_analytical_text or {}

    citation_observations: dict[str, list[_ProjectionCitationObservation]] = {}
    projection_states: dict[str, _ProjectionState] = {}

    for projection in projection_values:
        _validate_projection(projection)
        projection_case = canonical_uuid(
            projection.case_header.case_id,
            field_name="projection.case_header.case_id",
        )
        if projection_case != canonical_case:
            raise HistoricalMigrationInspectionError(
                "Historical migration projection belongs to a different case."
            )
        projection_id = str(projection.report_projection_id)
        binding_manifest = _load_projection_binding_checked(
            target_store,
            projection,
            canonical_case,
        )
        projection_states[projection_id] = _ProjectionState(
            report_projection_id=projection_id,
            binding_manifest=binding_manifest,
        )
        for citation in projection.citations:
            observation = _ProjectionCitationObservation(
                report_projection_id=projection_id,
                evidence_key=str(citation.evidence_key),
                document_name=str(citation.document_name),
                document_id=_optional_string(getattr(citation, "document_id", None)),
                page=_optional_positive_int(getattr(citation, "page", None)),
                chunk_id=_optional_string(getattr(citation, "chunk_id", None)),
            )
            citation_observations.setdefault(observation.evidence_key, []).append(observation)

    projected_keys = tuple(sorted(citation_observations))
    chroma_rows = _observe_chroma(collection, canonical_case, projected_keys)
    all_keys = sorted(set(projected_keys) | set(chroma_rows))
    document_candidates = _inventory_current_documents(current_documents_root)

    decisions: list[HistoricalMigrationDecision] = []
    for evidence_key in all_keys:
        decisions.append(
            _classify_evidence_key(
                case_id=canonical_case,
                evidence_key=evidence_key,
                citations=tuple(citation_observations.get(evidence_key, ())),
                projection_states=projection_states,
                chroma_rows=tuple(chroma_rows.get(evidence_key, ())),
                document_candidates=document_candidates,
                retained_analytical_text=historical_text,
                store=target_store,
            )
        )

    ordered_decisions = tuple(sorted(decisions, key=lambda item: item.evidence_key))
    projection_ids = tuple(sorted(projection_states))
    provisional = HistoricalMigrationReport(
        schema_version=HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION,
        case_id=canonical_case,
        projection_ids=projection_ids,
        decisions=ordered_decisions,
        historical_migration_report_id="sha256:" + ("0" * 64),
    )
    report_id = "sha256:" + sha256_bytes(
        _canonical_json_bytes(_report_identity_payload(provisional))
    )
    return HistoricalMigrationReport(
        schema_version=provisional.schema_version,
        case_id=provisional.case_id,
        projection_ids=provisional.projection_ids,
        decisions=provisional.decisions,
        historical_migration_report_id=report_id,
    )


def historical_migration_report_to_dict(report: HistoricalMigrationReport) -> dict[str, object]:
    """Return a deterministic JSON-compatible HM1 report dictionary."""
    return {
        **_report_identity_payload(report),
        "historical_migration_report_id": report.historical_migration_report_id,
    }


def dumps_historical_migration_report(report: HistoricalMigrationReport) -> str:
    """Return canonical HM1 audit JSON with exactly one trailing newline."""
    return _canonical_json_bytes(historical_migration_report_to_dict(report)).decode("utf-8") + "\n"


def _validate_projection(projection: object) -> None:
    try:
        from case_reporting.validation import validate_case_report_projection

        validate_case_report_projection(projection)
    except HistoricalMigrationInspectionError:
        raise
    except Exception as exc:
        raise HistoricalMigrationInspectionError(
            "Historical migration projection failed frozen validation."
        ) from exc


def _load_projection_binding_checked(
    store: object,
    projection: object,
    case_id: str,
) -> ProjectionEvidenceBindingManifest | None:
    try:
        manifest = store.load_projection_binding(case_id, projection.report_projection_id)
    except Exception as exc:
        raise HistoricalMigrationInspectionError(
            "Unable to load existing projection evidence-binding state."
        ) from exc
    if manifest is None:
        return None
    try:
        validate_projection_evidence_binding_manifest(manifest)
    except Exception as exc:
        raise HistoricalMigrationInspectionError(
            "Existing projection evidence-binding manifest failed validation."
        ) from exc
    if (
        manifest.case_id != case_id
        or manifest.report_projection_id != projection.report_projection_id
        or manifest.projection_payload_sha256 != projection.projection_payload_sha256
        or manifest.manifest_id != projection.manifest.manifest_id
    ):
        raise HistoricalMigrationInspectionError(
            "Existing projection evidence-binding manifest does not match the frozen projection."
        )
    projection_inventory = tuple(
        (str(item.citation_id), str(item.evidence_key)) for item in projection.citations
    )
    manifest_inventory = tuple(
        (item.citation_id, item.evidence_key) for item in manifest.entries
    )
    if manifest_inventory != projection_inventory:
        raise HistoricalMigrationInspectionError(
            "Existing projection evidence-binding inventory does not match the frozen projection."
        )
    return manifest


def _observe_chroma(
    collection: object,
    case_id: str,
    projected_keys: tuple[str, ...],
) -> dict[str, list[_ChromaRow]]:
    if collection is None or not callable(getattr(collection, "get", None)):
        raise HistoricalMigrationInspectionError("collection must provide read-only get().")

    responses: list[object] = []
    try:
        responses.append(
            collection.get(
                where={"case_id": case_id},
                include=["documents", "metadatas"],
            )
        )
        if projected_keys:
            responses.append(
                collection.get(
                    ids=list(projected_keys),
                    include=["documents", "metadatas"],
                )
            )
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Unable to read current Chroma inventory.") from exc

    rows: dict[str, list[_ChromaRow]] = {}
    seen: dict[tuple[str, str | None, str], None] = {}
    for response in responses:
        for row in _parse_chroma_response(response):
            fingerprint = _metadata_fingerprint(row.metadata)
            marker = (row.row_id, row.document, fingerprint)
            if marker in seen:
                continue
            seen[marker] = None
            rows.setdefault(row.row_id, []).append(row)
    return rows


def _parse_chroma_response(response: object) -> tuple[_ChromaRow, ...]:
    if not isinstance(response, Mapping):
        raise HistoricalMigrationInspectionError("Chroma get() returned a malformed response.")
    ids = response.get("ids", [])
    documents = response.get("documents", [])
    metadatas = response.get("metadatas", [])
    if ids is None:
        ids = []
    if documents is None:
        documents = [None] * len(ids)
    if metadatas is None:
        metadatas = [{} for _ in ids]
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        raise HistoricalMigrationInspectionError("Chroma ids are malformed.")
    if not isinstance(documents, Sequence) or isinstance(documents, (str, bytes)):
        raise HistoricalMigrationInspectionError("Chroma documents are malformed.")
    if not isinstance(metadatas, Sequence) or isinstance(metadatas, (str, bytes)):
        raise HistoricalMigrationInspectionError("Chroma metadatas are malformed.")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise HistoricalMigrationInspectionError("Chroma get() row lengths do not match.")

    rows: list[_ChromaRow] = []
    for row_id, document, metadata in zip(ids, documents, metadatas, strict=True):
        if not isinstance(row_id, str) or not row_id:
            raise HistoricalMigrationInspectionError("Chroma row ID is malformed.")
        if document is not None and not isinstance(document, str):
            raise HistoricalMigrationInspectionError("Chroma row document is malformed.")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            raise HistoricalMigrationInspectionError("Chroma row metadata is malformed.")
        rows.append(
            _ChromaRow(
                row_id=row_id,
                document=document,
                metadata={str(key): value for key, value in metadata.items()},
            )
        )
    return tuple(rows)


def _inventory_current_documents(root: Path | None) -> dict[str, tuple[Path, ...]]:
    if root is None:
        return {}
    configured = Path(root).expanduser().resolve(strict=False)
    if not configured.exists():
        return {}
    if not configured.is_dir() or configured.is_symlink():
        raise HistoricalMigrationInspectionError("current_documents_root is not a safe directory.")
    candidates: dict[str, list[Path]] = {}
    try:
        for path in configured.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve(strict=True)
            try:
                resolved.relative_to(configured)
            except ValueError as exc:
                raise HistoricalMigrationInspectionError(
                    "Current document inventory escaped its configured root."
                ) from exc
            candidates.setdefault(path.name, []).append(resolved)
    except HistoricalMigrationInspectionError:
        raise
    except OSError as exc:
        raise HistoricalMigrationInspectionError("Unable to inspect current document inventory.") from exc
    return {
        name: tuple(sorted(paths, key=lambda value: str(value)))
        for name, paths in candidates.items()
    }


def _classify_evidence_key(
    *,
    case_id: str,
    evidence_key: str,
    citations: tuple[_ProjectionCitationObservation, ...],
    projection_states: Mapping[str, _ProjectionState],
    chroma_rows: tuple[_ChromaRow, ...],
    document_candidates: Mapping[str, tuple[Path, ...]],
    retained_analytical_text: Mapping[str, str],
    store: object,
) -> HistoricalMigrationDecision:
    blockers: list[str] = []
    supplemental: list[HistoricalMigrationDecisionCode] = []
    citation_state, citation_ambiguous = _canonical_citation(citations)
    if citation_ambiguous:
        supplemental.append(HistoricalMigrationDecisionCode.AMBIGUOUS_PROJECTION_CITATIONS)
        blockers.append(HistoricalMigrationDecisionCode.AMBIGUOUS_PROJECTION_CITATIONS.value)

    compatible_rows, foreign_rows = _case_compatible_rows(chroma_rows, case_id)
    if foreign_rows:
        supplemental.append(HistoricalMigrationDecisionCode.CHROMA_CASE_MISMATCH)
        blockers.append(HistoricalMigrationDecisionCode.CHROMA_CASE_MISMATCH.value)
    unique_rows = _unique_chroma_rows(compatible_rows)
    chroma_ambiguous = len(unique_rows) > 1
    if chroma_ambiguous:
        supplemental.append(HistoricalMigrationDecisionCode.AMBIGUOUS_CHROMA_ROWS)
        blockers.append(HistoricalMigrationDecisionCode.AMBIGUOUS_CHROMA_ROWS.value)
    exact_row = unique_rows[0] if len(unique_rows) == 1 else None

    if citation_state is None and exact_row is not None:
        document_name = _metadata_string(exact_row.metadata, "file")
        document_id = _metadata_string(exact_row.metadata, "document_id")
        page = _metadata_positive_int(exact_row.metadata, "page")
        chunk_id = evidence_key
    elif citation_state is not None:
        document_name = citation_state.document_name
        document_id = citation_state.document_id
        page = citation_state.page
        chunk_id = citation_state.chunk_id
    else:
        document_name = None
        document_id = None
        page = None
        chunk_id = evidence_key if chroma_rows else None

    coordinate_mismatch = False
    if citation_state is not None and exact_row is not None:
        coordinate_mismatch = not _row_matches_citation(exact_row, citation_state)
        if coordinate_mismatch:
            supplemental.append(HistoricalMigrationDecisionCode.CHROMA_COORDINATE_MISMATCH)
            blockers.append(HistoricalMigrationDecisionCode.CHROMA_COORDINATE_MISMATCH.value)

    projection_entry_classes: list[tuple[str, BindingClass]] = []
    projection_manifest_ids: list[str] = []
    for citation in citations:
        state = projection_states[citation.report_projection_id]
        manifest = state.binding_manifest
        if manifest is None:
            continue
        projection_manifest_ids.append(manifest.projection_evidence_binding_manifest_id)
        matching = [item for item in manifest.entries if item.evidence_key == evidence_key]
        if len(matching) != 1:
            raise HistoricalMigrationInspectionError(
                "Existing projection binding does not contain exactly one expected evidence entry."
            )
        projection_entry_classes.append(
            (citation.report_projection_id, matching[0].binding_class)
        )

    frozen_unbound = any(
        binding_class is BindingClass.UNBOUND
        for _, binding_class in projection_entry_classes
    )
    frozen_weaker = any(
        binding_class in {
            BindingClass.ANALYTICAL_TEXT_BOUND,
            BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        }
        for _, binding_class in projection_entry_classes
    )

    existing_binding = _load_existing_binding(store, case_id, evidence_key)
    existing_full_chain_verified = False
    existing_full_chain_receipt_missing = False
    if existing_binding is not None:
        if existing_binding.binding_class is BindingClass.FULL_CHAIN_BOUND:
            try:
                _verify_existing_full_chain(store, existing_binding)
                existing_full_chain_verified = True
            except _MissingM5Receipt:
                existing_full_chain_receipt_missing = True
                blockers.append(HistoricalMigrationDecisionCode.M5_RECEIPT_MISSING.value)
            except Exception as exc:
                raise HistoricalMigrationInspectionError(
                    "Existing FULL_CHAIN source evidence failed read-only verification."
                ) from exc
        else:
            _verify_existing_weaker_binding(store, existing_binding)

    retained_text = retained_analytical_text.get(evidence_key)
    if retained_text is not None and not isinstance(retained_text, str):
        raise HistoricalMigrationInspectionError(
            "retained_analytical_text values must be exact strings."
        )
    retained_sha = (
        sha256_bytes(retained_text.encode("utf-8")) if retained_text is not None else None
    )

    current_document_sha = None
    metadata_fingerprint = None
    if exact_row is not None and exact_row.document is not None:
        current_document_sha = sha256_bytes(exact_row.document.encode("utf-8"))
        metadata_fingerprint = _metadata_fingerprint(exact_row.metadata)

    pdf_paths = tuple(document_candidates.get(document_name or "", ()))
    pdf_count = len(pdf_paths)
    pdf_sha = None
    pdf_length = None
    if pdf_count == 1:
        try:
            pdf_bytes = pdf_paths[0].read_bytes()
        except OSError as exc:
            raise HistoricalMigrationInspectionError("Unable to read current document candidate.") from exc
        pdf_sha = sha256_bytes(pdf_bytes)
        pdf_length = len(pdf_bytes)
    elif pdf_count > 1:
        supplemental.append(HistoricalMigrationDecisionCode.AMBIGUOUS_CURRENT_FILES)
        blockers.append(HistoricalMigrationDecisionCode.AMBIGUOUS_CURRENT_FILES.value)

    m3_candidate = _future_m3_key(case_id, citation_state, exact_row)
    same_future_key = None if m3_candidate is None else m3_candidate == evidence_key

    maximum_class = BindingClass.UNBOUND
    full_chain_eligible = False

    if existing_binding is not None:
        maximum_class = existing_binding.binding_class
        if existing_binding.binding_class is BindingClass.FULL_CHAIN_BOUND:
            full_chain_eligible = existing_full_chain_verified
    elif not citation_ambiguous and not chroma_ambiguous and not coordinate_mismatch and not foreign_rows:
        if retained_text is not None:
            maximum_class = BindingClass.ANALYTICAL_TEXT_BOUND
        elif exact_row is not None and exact_row.document is not None and document_name:
            maximum_class = BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT

    forward_reingestible = (
        pdf_count == 1
        and bool(document_name)
        and str(document_name).lower().endswith(".pdf")
    )

    collision_risk = bool(
        same_future_key is True
        and maximum_class in {
            BindingClass.ANALYTICAL_TEXT_BOUND,
            BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        }
        and (
            existing_binding is None
            or existing_binding.binding_class is not BindingClass.FULL_CHAIN_BOUND
        )
    )
    if collision_risk:
        blockers.append(HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK.value)

    if frozen_unbound:
        full_chain_eligible = False
    if frozen_weaker:
        full_chain_eligible = False

    decision_code, action = _primary_decision(
        existing_binding=existing_binding,
        existing_full_chain_verified=existing_full_chain_verified,
        existing_full_chain_receipt_missing=existing_full_chain_receipt_missing,
        frozen_unbound=frozen_unbound,
        frozen_weaker=frozen_weaker,
        citation_ambiguous=citation_ambiguous,
        chroma_ambiguous=chroma_ambiguous,
        foreign_rows=bool(foreign_rows),
        coordinate_mismatch=coordinate_mismatch,
        pdf_count=pdf_count,
        retained_text_present=retained_text is not None,
        exact_chroma_text_present=exact_row is not None and exact_row.document is not None,
        collision_risk=collision_risk,
        m3_candidate=m3_candidate,
        evidence_key=evidence_key,
        forward_reingestible=forward_reingestible,
    )

    if (
        maximum_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT
        and pdf_count == 1
        and existing_binding is None
    ):
        blockers.append(HistoricalMigrationDecisionCode.HISTORICAL_ORIGINAL_IDENTITY_MISSING.value)

    observation = HistoricalMigrationSourceObservation(
        current_chroma_row_count=len(unique_rows) + len(foreign_rows),
        current_chroma_document_sha256=current_document_sha,
        current_chroma_metadata_fingerprint=metadata_fingerprint,
        current_pdf_candidate_count=pdf_count,
        current_pdf_sha256=pdf_sha,
        current_pdf_byte_length=pdf_length,
        retained_historical_text_sha256=retained_sha,
    )
    return HistoricalMigrationDecision(
        case_id=case_id,
        evidence_key=evidence_key,
        document_name=document_name,
        document_id=document_id,
        page=page,
        chunk_id=chunk_id,
        referencing_report_projection_ids=tuple(
            sorted({item.report_projection_id for item in citations})
        ),
        existing_evidence_binding_id=(
            existing_binding.evidence_binding_id if existing_binding is not None else None
        ),
        existing_binding_class=(
            existing_binding.binding_class if existing_binding is not None else None
        ),
        existing_projection_binding_manifest_ids=tuple(sorted(set(projection_manifest_ids))),
        existing_projection_entry_classes=tuple(sorted(projection_entry_classes)),
        observation=observation,
        m3_case_scoped_evidence_key_candidate=m3_candidate,
        same_key_as_future_m3=same_future_key,
        binding_key_collision_risk=collision_risk,
        maximum_historical_binding_class=maximum_class,
        full_chain_projection_eligible=full_chain_eligible,
        forward_reingestible=forward_reingestible,
        decision_code=decision_code,
        blockers=tuple(sorted(set(blockers))),
        recommended_next_action=action,
    )


def _canonical_citation(
    citations: tuple[_ProjectionCitationObservation, ...],
) -> tuple[_ProjectionCitationObservation | None, bool]:
    if not citations:
        return None, False
    first = citations[0]
    identity = (first.document_name, first.document_id, first.page, first.chunk_id)
    ambiguous = any(
        (item.document_name, item.document_id, item.page, item.chunk_id) != identity
        for item in citations[1:]
    )
    return first, ambiguous


def _case_compatible_rows(
    rows: tuple[_ChromaRow, ...],
    case_id: str,
) -> tuple[tuple[_ChromaRow, ...], tuple[_ChromaRow, ...]]:
    compatible: list[_ChromaRow] = []
    foreign: list[_ChromaRow] = []
    for row in rows:
        row_case = row.metadata.get("case_id")
        if row_case in (None, "", _LEGACY_CASE_ID, case_id):
            compatible.append(row)
        else:
            foreign.append(row)
    return tuple(compatible), tuple(foreign)


def _unique_chroma_rows(rows: tuple[_ChromaRow, ...]) -> tuple[_ChromaRow, ...]:
    unique: dict[tuple[str | None, str], _ChromaRow] = {}
    for row in rows:
        marker = (row.document, _metadata_fingerprint(row.metadata))
        unique[marker] = row
    return tuple(unique[key] for key in sorted(unique, key=lambda value: repr(value)))


def _row_matches_citation(row: _ChromaRow, citation: _ProjectionCitationObservation) -> bool:
    row_file = _metadata_string(row.metadata, "file")
    row_page = _metadata_positive_int(row.metadata, "page")
    if row_file != citation.document_name:
        return False
    if citation.page is not None and row_page != citation.page:
        return False
    return True


def _load_existing_binding(store: object, case_id: str, evidence_key: str) -> EvidenceBinding | None:
    try:
        binding = store.load_evidence_binding(case_id, evidence_key)
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Unable to load existing evidence binding.") from exc
    if binding is None:
        return None
    try:
        validate_evidence_binding(binding)
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Existing evidence binding failed validation.") from exc
    if binding.case_id != case_id or binding.evidence_key != evidence_key:
        raise HistoricalMigrationInspectionError("Existing evidence binding identity mismatch.")
    return binding


class _MissingM5Receipt(RuntimeError):
    pass


def _verify_existing_full_chain(store: object, binding: EvidenceBinding) -> None:
    assert binding.chunk_text_sha256 is not None
    expected_receipt = build_singleton_analysis_receipt(
        case_id=binding.case_id,
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=binding.chunk_text_sha256,
    )
    try:
        stored_receipt = store.load_analysis_receipt(
            binding.case_id,
            expected_receipt.source_bound_analysis_receipt_id,
        )
    except (FileNotFoundError, SourceEvidenceStoreError, KeyError):
        raise _MissingM5Receipt from None
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Unable to verify existing M5 receipt.") from exc
    if stored_receipt != expected_receipt:
        raise HistoricalMigrationInspectionError("Existing M5 receipt does not match frozen singleton proof.")

    try:
        manifest = store.load_document_manifest(
            binding.case_id,
            binding.source_document_instance_id,
        )
        validate_source_document_manifest(manifest)
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Existing FULL_CHAIN source manifest failed validation.") from exc
    if (
        manifest.case_id != binding.case_id
        or manifest.source_document_instance_id != binding.source_document_instance_id
        or manifest.source_snapshot_id != binding.source_snapshot_id
        or manifest.original_filename != binding.document_name
        or manifest.original_blob_sha256 != binding.original_blob_sha256
        or manifest.extraction_profile.profile_id != binding.extraction_profile_id
        or manifest.chunking_profile.profile_id != binding.chunking_profile_id
    ):
        raise HistoricalMigrationInspectionError("Existing FULL_CHAIN manifest/binding mismatch.")

    pages = [item for item in manifest.pages if item.page_number == binding.page]
    if len(pages) != 1 or pages[0].page_text_sha256 != binding.page_text_sha256:
        raise HistoricalMigrationInspectionError("Existing FULL_CHAIN page lineage mismatch.")
    chunks = [
        item
        for item in pages[0].chunk_snapshots
        if item.chunk_ordinal == binding.chunk_ordinal
    ]
    if (
        len(chunks) != 1
        or chunks[0].chunk_id != binding.evidence_key
        or chunks[0].evidence_key != binding.evidence_key
        or chunks[0].chunk_text_sha256 != binding.chunk_text_sha256
    ):
        raise HistoricalMigrationInspectionError("Existing FULL_CHAIN chunk lineage mismatch.")

    _read_blob_exact(store, manifest.original_blob_sha256, manifest.original_byte_length, utf8=False)
    _read_blob_exact(store, pages[0].page_text_sha256, pages[0].page_text_byte_length, utf8=True)
    _read_blob_exact(store, chunks[0].chunk_text_sha256, chunks[0].chunk_text_byte_length, utf8=True)


def _verify_existing_weaker_binding(store: object, binding: EvidenceBinding) -> None:
    try:
        data = store.read_blob(binding.bound_text_sha256)
        data.decode("utf-8", errors="strict")
    except Exception as exc:
        raise HistoricalMigrationInspectionError(
            "Existing weaker EvidenceBinding does not resolve to exact UTF-8 text."
        ) from exc


def _read_blob_exact(store: object, digest: str, expected_length: int, *, utf8: bool) -> bytes:
    try:
        data = store.read_blob(digest)
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Existing source-evidence blob could not be read.") from exc
    if len(data) != expected_length:
        raise HistoricalMigrationInspectionError("Existing source-evidence blob length mismatch.")
    if utf8:
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise HistoricalMigrationInspectionError("Existing source text is not strict UTF-8.") from exc
    return data


def _future_m3_key(
    case_id: str,
    citation: _ProjectionCitationObservation | None,
    row: _ChromaRow | None,
) -> str | None:
    if row is None:
        return None
    document_name = _metadata_string(row.metadata, "file")
    page = _metadata_positive_int(row.metadata, "page")
    chunk = _metadata_nonnegative_int(row.metadata, "chunk")
    if document_name is None or page is None or chunk is None:
        return None
    if citation is not None:
        if citation.document_name != document_name:
            return None
        if citation.page is not None and citation.page != page:
            return None
    try:
        from case_management.document_context import build_document_id

        return build_document_id(
            pdf_path=document_name,
            page_number=page,
            chunk_number=chunk,
            case_id=case_id,
        )
    except Exception as exc:
        raise HistoricalMigrationInspectionError("Unable to derive frozen M3 candidate evidence key.") from exc


def _primary_decision(
    *,
    existing_binding: EvidenceBinding | None,
    existing_full_chain_verified: bool,
    existing_full_chain_receipt_missing: bool,
    frozen_unbound: bool,
    frozen_weaker: bool,
    citation_ambiguous: bool,
    chroma_ambiguous: bool,
    foreign_rows: bool,
    coordinate_mismatch: bool,
    pdf_count: int,
    retained_text_present: bool,
    exact_chroma_text_present: bool,
    collision_risk: bool,
    m3_candidate: str | None,
    evidence_key: str,
    forward_reingestible: bool,
) -> tuple[HistoricalMigrationDecisionCode, str]:
    if frozen_unbound:
        return (
            HistoricalMigrationDecisionCode.FROZEN_PROJECTION_UNBOUND,
            "preserve_frozen_projection_state",
        )
    if frozen_weaker:
        return (
            HistoricalMigrationDecisionCode.FROZEN_PROJECTION_WEAKER,
            "preserve_frozen_projection_state",
        )
    if existing_binding is not None:
        if existing_binding.binding_class is BindingClass.FULL_CHAIN_BOUND:
            if existing_full_chain_verified:
                return HistoricalMigrationDecisionCode.ALREADY_FULL_CHAIN, "no_migration_required"
            if existing_full_chain_receipt_missing:
                return HistoricalMigrationDecisionCode.M5_RECEIPT_MISSING, "do_not_claim_projection_full_chain"
        return HistoricalMigrationDecisionCode.ALREADY_BOUND_WEAKER, "preserve_existing_binding"
    if citation_ambiguous:
        return HistoricalMigrationDecisionCode.AMBIGUOUS_PROJECTION_CITATIONS, "manual_provenance_review"
    if foreign_rows:
        return HistoricalMigrationDecisionCode.CHROMA_CASE_MISMATCH, "manual_provenance_review"
    if chroma_ambiguous:
        return HistoricalMigrationDecisionCode.AMBIGUOUS_CHROMA_ROWS, "manual_provenance_review"
    if coordinate_mismatch:
        return HistoricalMigrationDecisionCode.CHROMA_COORDINATE_MISMATCH, "manual_provenance_review"
    if pdf_count > 1:
        return HistoricalMigrationDecisionCode.AMBIGUOUS_CURRENT_FILES, "manual_document_identity_review"
    if collision_risk:
        return HistoricalMigrationDecisionCode.BINDING_KEY_COLLISION_RISK, "defer_binding_publication"
    if retained_text_present:
        return (
            HistoricalMigrationDecisionCode.HISTORICAL_ANALYTICAL_TEXT_PROVEN,
            "candidate_for_hm2_analytical_text_binding",
        )
    if exact_chroma_text_present:
        if m3_candidate is not None and m3_candidate != evidence_key:
            return (
                HistoricalMigrationDecisionCode.LEGACY_KEY_DIFFERS_FROM_M3_KEY,
                "preserve_historical_key_consider_forward_reingestion",
            )
        return (
            HistoricalMigrationDecisionCode.CURRENT_INDEX_SNAPSHOT_ONLY,
            "candidate_for_hm2_legacy_snapshot" if not forward_reingestible else "consider_forward_reingestion_before_weak_binding",
        )
    if forward_reingestible:
        return (
            HistoricalMigrationDecisionCode.FORWARD_REINGESTION_CANDIDATE,
            "forward_reingestion_only_no_historical_promotion",
        )
    return HistoricalMigrationDecisionCode.NO_EXACT_TEXT_AUTHORITY, "leave_unbound"


def _metadata_string(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _metadata_positive_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    return _positive_int(value)


def _metadata_nonnegative_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HistoricalMigrationInspectionError("Projection citation contains malformed text metadata.")
    return value or None


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    result = _positive_int(value)
    if result is None:
        raise HistoricalMigrationInspectionError("Projection citation page is malformed.")
    return result


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _metadata_fingerprint(metadata: Mapping[str, object]) -> str:
    payload = _canonical_json_bytes(_json_compatible(dict(metadata)))
    return "sha256:" + sha256_bytes(payload)


def _json_compatible(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    raise HistoricalMigrationInspectionError("Observed metadata is not canonically JSON serializable.")


def _canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HistoricalMigrationInspectionError("HM1 audit payload is not canonical JSON.") from exc


def _report_identity_payload(report: HistoricalMigrationReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "case_id": report.case_id,
        "projection_ids": list(report.projection_ids),
        "decisions": [_decision_to_dict(item) for item in report.decisions],
    }


def _decision_to_dict(value: HistoricalMigrationDecision) -> dict[str, object]:
    return {
        "case_id": value.case_id,
        "evidence_key": value.evidence_key,
        "document_name": value.document_name,
        "document_id": value.document_id,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "referencing_report_projection_ids": list(value.referencing_report_projection_ids),
        "existing_evidence_binding_id": value.existing_evidence_binding_id,
        "existing_binding_class": (
            value.existing_binding_class.value if value.existing_binding_class is not None else None
        ),
        "existing_projection_binding_manifest_ids": list(
            value.existing_projection_binding_manifest_ids
        ),
        "existing_projection_entry_classes": [
            [projection_id, binding_class.value]
            for projection_id, binding_class in value.existing_projection_entry_classes
        ],
        "observation": {
            "current_chroma_row_count": value.observation.current_chroma_row_count,
            "current_chroma_document_sha256": value.observation.current_chroma_document_sha256,
            "current_chroma_metadata_fingerprint": value.observation.current_chroma_metadata_fingerprint,
            "current_pdf_candidate_count": value.observation.current_pdf_candidate_count,
            "current_pdf_sha256": value.observation.current_pdf_sha256,
            "current_pdf_byte_length": value.observation.current_pdf_byte_length,
            "retained_historical_text_sha256": value.observation.retained_historical_text_sha256,
        },
        "m3_case_scoped_evidence_key_candidate": value.m3_case_scoped_evidence_key_candidate,
        "same_key_as_future_m3": value.same_key_as_future_m3,
        "binding_key_collision_risk": value.binding_key_collision_risk,
        "maximum_historical_binding_class": value.maximum_historical_binding_class.value,
        "full_chain_projection_eligible": value.full_chain_projection_eligible,
        "forward_reingestible": value.forward_reingestible,
        "decision_code": value.decision_code.value,
        "blockers": list(value.blockers),
        "recommended_next_action": value.recommended_next_action,
    }


__all__ = [
    "HISTORICAL_MIGRATION_REPORT_SCHEMA_VERSION",
    "HistoricalMigrationDecision",
    "HistoricalMigrationDecisionCode",
    "HistoricalMigrationInspectionError",
    "HistoricalMigrationReport",
    "HistoricalMigrationSourceObservation",
    "dumps_historical_migration_report",
    "historical_migration_report_to_dict",
    "inspect_historical_evidence",
]
