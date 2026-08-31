"""Governed analytical-authority revision core.

GAR1 separates proposal approval, successor construction, immutable publication,
and activation. This module performs successor construction only. It never
publishes, activates, retrieves evidence, accesses a database, or invokes an AI
model.

The existing ``governed_analytical_authority`` package is a frozen eight-file
authority boundary. GAR1 therefore lives outside that package and consumes only
its public identity/model/validation contracts.

An approved MAL1 analytical change targets the authoritative M5
ElementLegalAnalysis status/confidence pair. The affected M5 result is then
made semantically self-consistent by mechanically rebuilding its issue synthesis
and overall limitations from the complete revised element graph. The M2
CaseMatrices projection is rebuilt from that revised M5 graph. U9B and U9C remain
the exact supplied predecessor components because this delta does not alter
evidence-use topology or the frozen synthesis identity.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
import json
from typing import Any, Iterable

from analytical_change_proposals import (
    AnalyticalChangeProposalState,
    project_change_proposals,
)
from case_analysis.m2.evidence_matrix import build_evidence_matrix
from case_analysis.m2.issue_matrix import build_issue_matrix
from governed_analytical_authority.identity import canonical_sha256
from governed_analytical_authority.models import GovernedAnalyticalAuthorityManifest
from governed_analytical_authority.validation import (
    build_governed_analytical_authority_manifest,
    validate_governed_analytical_authority_manifest,
)
from legal_analysis.enums import Materiality
from legal_analysis.legal_analysis import ElementAnalysisStatus, IssueLevelSynthesis


GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION = (
    "governed-authority-revision-receipt/v1"
)


class GovernedAuthorityRevisionError(ValueError):
    """Raised when an approved proposal cannot create one exact successor."""


@dataclass(frozen=True, slots=True)
class GovernedAuthorityRevisionReceipt:
    """Immutable provenance binding predecessor, approval history and successor."""

    schema_version: str
    case_id: str
    predecessor_authority_id: str
    successor_authority_id: str
    proposal_id: str
    approval_event_id: str
    approval_previous_event_id: str | None
    issue_analysis_id: str
    element_id: str
    previous_status: str
    previous_confidence: str
    new_status: str
    new_confidence: str
    proposal_history_sha256: str
    revision_id: str


@dataclass(frozen=True, slots=True)
class GovernedAuthorityRevisionResult:
    """In-memory successor candidate. It is not publication or activation."""

    structured_legal_analysis_results: tuple[Any, ...]
    case_matrices: Any
    governed_issue_evidence_map: Any
    governed_evidential_analysis: Any
    manifest: GovernedAnalyticalAuthorityManifest
    receipt: GovernedAuthorityRevisionReceipt


def _fail(message: str) -> None:
    raise GovernedAuthorityRevisionError(message)


def _text(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _normalise_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _normalise_json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if hasattr(value, "__dict__"):
        return {
            str(key): _normalise_json_value(item)
            for key, item in sorted(vars(value).items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple):
        return [_normalise_json_value(item) for item in value]
    if isinstance(value, list):
        return [_normalise_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalise_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _normalise_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _proposal_history_sha256(events: tuple[Any, ...]) -> str:
    return canonical_sha256(_canonical_json(events))


def _select_approved_proposal(
    *,
    proposal_events: tuple[Any, ...],
    proposal_id: str,
) -> Any:
    matching = tuple(
        event
        for event in proposal_events
        if getattr(event, "proposal_id", None) == proposal_id
    )
    if not matching:
        _fail("Approved proposal was not found in the supplied proposal history.")

    candidate = matching[-1]
    issue_analysis_id = getattr(candidate, "issue_analysis_id", "")
    element_id = getattr(candidate, "element_id", "")

    projected = project_change_proposals(
        events=proposal_events,
        issue_analysis_id=issue_analysis_id,
        element_id=element_id,
    )
    latest = tuple(
        event
        for event in projected
        if getattr(event, "proposal_id", None) == proposal_id
    )
    if len(latest) != 1:
        _fail("Proposal history does not project to exactly one latest proposal event.")

    candidate = latest[0]
    if getattr(candidate, "state", None) is not AnalyticalChangeProposalState.APPROVED:
        _fail("Proposal is not in APPROVED state.")
    return candidate


def _coerce_replacement(current: Any, proposed_text: str, *, field_name: str) -> Any:
    try:
        if isinstance(current, Enum):
            return type(current)(proposed_text)
        if isinstance(current, str):
            return proposed_text
        return type(current)(proposed_text)
    except (TypeError, ValueError) as exc:
        raise GovernedAuthorityRevisionError(
            f"Approved {field_name} value is invalid for the target analytical field."
        ) from exc


def _issue_synthesis(elements: tuple[Any, ...]) -> IssueLevelSynthesis:
    """Rebuild the exact mechanical M5 issue aggregation from revised elements."""

    buckets: dict[ElementAnalysisStatus, list[str]] = {
        status: [] for status in ElementAnalysisStatus
    }
    for item in elements:
        status = getattr(item, "provisional_status")
        if not isinstance(status, ElementAnalysisStatus):
            _fail("Revised M5 element provisional_status has an invalid type.")
        buckets[status].append(str(getattr(item, "element_id")))

    summary = (
        "This synthesis mechanically aggregates provisional element states from the frozen M4 assessment. "
        f"Well-supported factual areas: {len(buckets[ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD])}; "
        f"partially supported: {len(buckets[ElementAnalysisStatus.PARTIALLY_SUPPORTED])}; "
        f"disputed: {len(buckets[ElementAnalysisStatus.DISPUTED])}; "
        f"insufficiently evidenced: {len(buckets[ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED])}; "
        f"unresolved: {len(buckets[ElementAnalysisStatus.UNRESOLVED])}. "
        "The counts are not a merits score and do not determine liability."
    )
    return IssueLevelSynthesis(
        well_supported_elements=tuple(
            buckets[ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD]
        ),
        partially_supported_elements=tuple(
            buckets[ElementAnalysisStatus.PARTIALLY_SUPPORTED]
        ),
        disputed_elements=tuple(buckets[ElementAnalysisStatus.DISPUTED]),
        insufficiently_evidenced_elements=tuple(
            buckets[ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED]
        ),
        unresolved_elements=tuple(buckets[ElementAnalysisStatus.UNRESOLVED]),
        summary=summary,
    )


def _overall_limitations(elements: tuple[Any, ...]) -> tuple[str, ...]:
    """Rebuild exact M5 limitations affected by revised element status."""

    limitations: list[str] = []
    for item in elements:
        element_id = str(getattr(item, "element_id"))
        for gap in tuple(getattr(item, "evidential_gaps", ())):
            if getattr(gap, "materiality", None) in {
                Materiality.HIGH,
                Materiality.MEDIUM,
            }:
                limitations.append(f"{element_id}: {getattr(gap, 'description')}")
        if getattr(item, "provisional_status") is ElementAnalysisStatus.DISPUTED:
            limitations.append(
                f"{element_id}: a material factual dispute remains unresolved."
            )

    if not limitations:
        limitations.append(
            "M5 remains a provisional legal-significance layer and does not determine whether any statutory element is satisfied."
        )
    return tuple(dict.fromkeys(limitations))


def _rewrite_structured_legal_analysis_results(
    *,
    structured_legal_analysis_results: tuple[Any, ...],
    proposal: Any,
) -> tuple[Any, ...]:
    target_issue = str(proposal.issue_analysis_id)
    target_element = str(proposal.element_id)
    expected_status = str(proposal.current_status)
    expected_confidence = str(proposal.current_confidence)
    proposed_status = str(proposal.proposed_status)
    proposed_confidence = str(proposal.proposed_confidence)

    matches = 0
    rewritten_results: list[Any] = []

    for result in structured_legal_analysis_results:
        if str(getattr(result, "issue_analysis_id", "")) != target_issue:
            rewritten_results.append(result)
            continue

        rewritten_elements: list[Any] = []
        changed_result = False

        for element in tuple(getattr(result, "element_analyses", ())):
            if str(getattr(element, "element_id", "")) != target_element:
                rewritten_elements.append(element)
                continue

            matches += 1
            current_status = getattr(element, "provisional_status")
            current_confidence = getattr(element, "analysis_confidence")

            if _text(current_status) != expected_status:
                _fail("Proposal current_status does not match predecessor M5 authority.")
            if _text(current_confidence) != expected_confidence:
                _fail("Proposal current_confidence does not match predecessor M5 authority.")

            new_status = _coerce_replacement(
                current_status,
                proposed_status,
                field_name="proposed_status",
            )
            new_confidence = _coerce_replacement(
                current_confidence,
                proposed_confidence,
                field_name="proposed_confidence",
            )
            if new_status == current_status and new_confidence == current_confidence:
                _fail("Approved proposal is a no-op against the predecessor authority.")

            rewritten_elements.append(
                replace(
                    element,
                    provisional_status=new_status,
                    analysis_confidence=new_confidence,
                )
            )
            changed_result = True

        if changed_result:
            complete_elements = tuple(rewritten_elements)
            rewritten_results.append(
                replace(
                    result,
                    element_analyses=complete_elements,
                    issue_synthesis=_issue_synthesis(complete_elements),
                    overall_limitations=_overall_limitations(complete_elements),
                )
            )
        else:
            rewritten_results.append(result)

    if matches == 0:
        _fail("Approved proposal target was not found in predecessor M5 authority.")
    if matches != 1:
        _fail("Approved proposal target was not unique in predecessor M5 authority.")

    return tuple(rewritten_results)


def _rebuild_case_matrices(
    *,
    predecessor_case_matrices: Any,
    successor_results: tuple[Any, ...],
) -> Any:
    """Reproject the exact M2 matrices from the revised complete M5 graph."""

    successor_issue_matrix = build_issue_matrix(successor_results)
    successor_evidence_matrix = build_evidence_matrix(successor_results)

    successor = replace(
        predecessor_case_matrices,
        issue_matrix=successor_issue_matrix,
        evidence_matrix=successor_evidence_matrix,
    )

    if successor.synthesis_id != predecessor_case_matrices.synthesis_id:
        _fail("Revision changed frozen CaseMatrices.synthesis_id.")
    if successor.source_analysis_ids != predecessor_case_matrices.source_analysis_ids:
        _fail("Revision changed CaseMatrices source-analysis lineage.")
    if successor.schema_version != predecessor_case_matrices.schema_version:
        _fail("Revision changed CaseMatrices schema version.")
    if successor.matrix_builder_version != predecessor_case_matrices.matrix_builder_version:
        _fail("Revision changed CaseMatrices builder version.")
    if successor.evidence_matrix != predecessor_case_matrices.evidence_matrix:
        _fail("Approved status/confidence delta unexpectedly changed the evidence matrix.")
    if successor.issue_matrix == predecessor_case_matrices.issue_matrix:
        _fail("Approved proposal did not change the deterministic issue matrix.")

    return successor


def _revision_receipt(
    *,
    predecessor: GovernedAnalyticalAuthorityManifest,
    successor: GovernedAnalyticalAuthorityManifest,
    proposal: Any,
    proposal_history_sha256: str,
) -> GovernedAuthorityRevisionReceipt:
    base = {
        "schema_version": GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION,
        "case_id": predecessor.case_id,
        "predecessor_authority_id": predecessor.authority_id,
        "successor_authority_id": successor.authority_id,
        "proposal_id": str(proposal.proposal_id),
        "approval_event_id": str(proposal.event_id),
        "approval_previous_event_id": (
            None
            if getattr(proposal, "previous_event_id", None) is None
            else str(proposal.previous_event_id)
        ),
        "issue_analysis_id": str(proposal.issue_analysis_id),
        "element_id": str(proposal.element_id),
        "previous_status": str(proposal.current_status),
        "previous_confidence": str(proposal.current_confidence),
        "new_status": str(proposal.proposed_status),
        "new_confidence": str(proposal.proposed_confidence),
        "proposal_history_sha256": proposal_history_sha256,
    }
    revision_id = canonical_sha256(_canonical_json(base))
    return GovernedAuthorityRevisionReceipt(
        **base,
        revision_id=revision_id,
    )


def dumps_governed_authority_revision_receipt(
    value: GovernedAuthorityRevisionReceipt,
) -> str:
    """Return canonical deterministic JSON for one GAR1 revision receipt."""

    if not isinstance(value, GovernedAuthorityRevisionReceipt):
        _fail("value must be a GovernedAuthorityRevisionReceipt.")
    return _canonical_json(value)


def build_governed_authority_revision(
    *,
    predecessor_manifest: GovernedAnalyticalAuthorityManifest,
    proposal_events: Iterable[Any],
    proposal_id: str,
    structured_legal_analysis_results: Iterable[Any],
    case_matrices: Any,
    governed_issue_evidence_map: Any,
    governed_evidential_analysis: Any,
) -> GovernedAuthorityRevisionResult:
    """Create one in-memory successor authority from exactly one approved delta.

    This function performs no publication and no activation.
    """

    if not isinstance(predecessor_manifest, GovernedAnalyticalAuthorityManifest):
        _fail("predecessor_manifest must be a GovernedAnalyticalAuthorityManifest.")

    results = tuple(structured_legal_analysis_results)
    events = tuple(proposal_events)

    validate_governed_analytical_authority_manifest(
        predecessor_manifest,
        structured_legal_analysis_results=results,
        case_matrices=case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
    )

    proposal = _select_approved_proposal(
        proposal_events=events,
        proposal_id=proposal_id,
    )

    if str(proposal.case_id) != predecessor_manifest.case_id:
        _fail("Approved proposal case_id does not match predecessor authority.")
    if str(proposal.authority_id) != predecessor_manifest.authority_id:
        _fail("Approved proposal authority_id does not match predecessor authority.")

    successor_results = _rewrite_structured_legal_analysis_results(
        structured_legal_analysis_results=results,
        proposal=proposal,
    )
    successor_case_matrices = _rebuild_case_matrices(
        predecessor_case_matrices=case_matrices,
        successor_results=successor_results,
    )

    successor_manifest = build_governed_analytical_authority_manifest(
        structured_legal_analysis_results=successor_results,
        case_matrices=successor_case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
    )

    if successor_manifest.case_id != predecessor_manifest.case_id:
        _fail("Successor authority changed case_id.")
    if (
        successor_manifest.structured_legal_analysis_results_sha256
        == predecessor_manifest.structured_legal_analysis_results_sha256
    ):
        _fail("Approved proposal did not create a new M5 authority generation.")
    if (
        successor_manifest.case_matrices_sha256
        == predecessor_manifest.case_matrices_sha256
    ):
        _fail("Approved proposal did not create a new CaseMatrices generation.")
    if (
        successor_manifest.governed_issue_evidence_map_sha256
        != predecessor_manifest.governed_issue_evidence_map_sha256
    ):
        _fail("Revision changed U9B outside the approved delta.")
    if (
        successor_manifest.governed_evidential_analysis_sha256
        != predecessor_manifest.governed_evidential_analysis_sha256
    ):
        _fail("Revision changed U9C outside the approved delta.")
    if successor_manifest.source_analysis_ids != predecessor_manifest.source_analysis_ids:
        _fail("Revision changed predecessor source-analysis lineage.")
    if successor_manifest.authority_id == predecessor_manifest.authority_id:
        _fail("Approved proposal did not create a new authority identity.")

    history_sha256 = _proposal_history_sha256(events)
    receipt = _revision_receipt(
        predecessor=predecessor_manifest,
        successor=successor_manifest,
        proposal=proposal,
        proposal_history_sha256=history_sha256,
    )

    return GovernedAuthorityRevisionResult(
        structured_legal_analysis_results=successor_results,
        case_matrices=successor_case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
        manifest=successor_manifest,
        receipt=receipt,
    )


__all__ = [
    "GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION",
    "GovernedAuthorityRevisionError",
    "GovernedAuthorityRevisionReceipt",
    "GovernedAuthorityRevisionResult",
    "build_governed_authority_revision",
    "dumps_governed_authority_revision_receipt",
]
