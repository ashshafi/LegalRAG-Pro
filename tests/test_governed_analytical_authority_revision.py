from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from analytical_change_proposals import AnalyticalChangeProposalState
from governed_analytical_authority.models import GovernedAnalyticalAuthorityManifest
from legal_analysis.enums import Confidence, Materiality
from legal_analysis.legal_analysis import ElementAnalysisStatus, IssueLevelSynthesis
import governed_authority_revision as revision


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
ISSUE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ISSUE_ID = "22222222-2222-4222-8222-222222222222"
ELEMENT_ID = "element-a"


@dataclass(frozen=True)
class FakeGap:
    materiality: Materiality
    description: str


@dataclass(frozen=True)
class FakeM5Element:
    element_id: str
    provisional_status: ElementAnalysisStatus
    analysis_confidence: Confidence
    evidential_gaps: tuple[FakeGap, ...] = ()
    untouched: str = "sealed"


@dataclass(frozen=True)
class FakeM5Result:
    issue_analysis_id: str
    element_analyses: tuple[FakeM5Element, ...]
    issue_synthesis: IssueLevelSynthesis
    overall_limitations: tuple[str, ...]
    untouched: str = "sealed-result"


@dataclass(frozen=True)
class FakeMatrices:
    case_id: str
    synthesis_id: str
    source_analysis_ids: tuple[str, ...]
    issue_matrix: tuple[tuple[str, str, str], ...]
    evidence_matrix: tuple[str, ...]
    schema_version: str = "case-matrices/v1"
    matrix_builder_version: str = "case-matrices-builder/v1"


def _h(text):
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def _issue_projection(results):
    rows = []
    for result in results:
        for element in result.element_analyses:
            rows.append(
                (
                    result.issue_analysis_id,
                    element.element_id,
                    element.provisional_status.value
                    + "|"
                    + element.analysis_confidence.value,
                )
            )
    return tuple(rows)


def _evidence_projection(results):
    return ("evidence-topology-sealed",)


def _m5_payload(results):
    return repr(tuple(results))


def _manifest(results, case_matrices):
    m5_hash = _h(_m5_payload(results))
    case_hash = _h(repr(case_matrices))
    authority_id = _h(
        "|".join(
            (
                CASE_ID,
                m5_hash,
                case_hash,
                _h("u9b"),
                _h("u9c"),
            )
        )
    )
    return GovernedAnalyticalAuthorityManifest(
        schema_version="governed-analytical-authority-manifest/v1",
        identity_version="governed-analytical-authority-identity/v1",
        case_id=CASE_ID,
        structured_legal_analysis_results_sha256=m5_hash,
        case_matrices_sha256=case_hash,
        governed_issue_evidence_map_sha256=_h("u9b"),
        governed_evidential_analysis_sha256=_h("u9c"),
        source_analysis_ids=(ISSUE_ID,),
        authority_id=authority_id,
    )


def _results(
    *,
    duplicate=False,
    status=ElementAnalysisStatus.UNRESOLVED,
    confidence=Confidence.LOW,
    gaps=(),
):
    element = FakeM5Element(
        element_id=ELEMENT_ID,
        provisional_status=status,
        analysis_confidence=confidence,
        evidential_gaps=tuple(gaps),
    )
    elements = (element, element) if duplicate else (element,)
    return (
        FakeM5Result(
            issue_analysis_id=ISSUE_ID,
            element_analyses=elements,
            issue_synthesis=revision._issue_synthesis(elements),
            overall_limitations=revision._overall_limitations(elements),
        ),
    )


def _matrices(results):
    return FakeMatrices(
        case_id=CASE_ID,
        synthesis_id="33333333-3333-4333-8333-333333333333",
        source_analysis_ids=(ISSUE_ID,),
        issue_matrix=_issue_projection(results),
        evidence_matrix=_evidence_projection(results),
    )


def _event(
    *,
    authority_id,
    state=AnalyticalChangeProposalState.APPROVED,
    issue_id=ISSUE_ID,
    current_status=ElementAnalysisStatus.UNRESOLVED.value,
    current_confidence=Confidence.LOW.value,
    proposed_status=ElementAnalysisStatus.PARTIALLY_SUPPORTED.value,
    proposed_confidence=Confidence.HIGH.value,
    event_id="approval-event",
):
    return SimpleNamespace(
        schema_version="analytical-change-proposal-event/v1",
        case_id=CASE_ID,
        authority_id=authority_id,
        issue_analysis_id=issue_id,
        element_id=ELEMENT_ID,
        proposal_id="proposal-1",
        event_id=event_id,
        current_status=current_status,
        current_confidence=current_confidence,
        proposed_status=proposed_status,
        proposed_confidence=proposed_confidence,
        rationale="Approved governed change.",
        basis_relationship_ids=(),
        state=state,
        actor="reviewer",
        created_at="2026-08-31T00:00:00+00:00",
        previous_event_id="proposal-event",
    )


def _install(monkeypatch, *, latest_event):
    monkeypatch.setattr(
        revision,
        "validate_governed_analytical_authority_manifest",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        revision,
        "build_issue_matrix",
        lambda results: _issue_projection(tuple(results)),
    )
    monkeypatch.setattr(
        revision,
        "build_evidence_matrix",
        lambda results: _evidence_projection(tuple(results)),
    )
    monkeypatch.setattr(
        revision,
        "build_governed_analytical_authority_manifest",
        lambda **kwargs: _manifest(
            tuple(kwargs["structured_legal_analysis_results"]),
            kwargs["case_matrices"],
        ),
    )
    monkeypatch.setattr(
        revision,
        "project_change_proposals",
        lambda **kwargs: (latest_event,),
    )


def _build(monkeypatch, *, results=None, event=None):
    results = _results() if results is None else results
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id) if event is None else event
    _install(monkeypatch, latest_event=event)

    result = revision.build_governed_authority_revision(
        predecessor_manifest=predecessor,
        proposal_events=(event,),
        proposal_id=event.proposal_id,
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map="u9b",
        governed_evidential_analysis="u9c",
    )
    return predecessor, results, matrices, event, result


def test_gar1_lives_outside_frozen_eight_file_authority_package():
    source_path = Path(revision.__file__).resolve()
    assert source_path.name == "governed_authority_revision.py"
    frozen_package = source_path.parent / "governed_analytical_authority"
    assert not (frozen_package / "revision.py").exists()


def test_approved_exact_predecessor_revises_m5_and_reprojects_matrices(monkeypatch):
    predecessor, results, matrices, event, result = _build(monkeypatch)

    before = results[0].element_analyses[0]
    after_result = result.structured_legal_analysis_results[0]
    after = after_result.element_analyses[0]

    assert before.provisional_status is ElementAnalysisStatus.UNRESOLVED
    assert before.analysis_confidence is Confidence.LOW
    assert after.provisional_status is ElementAnalysisStatus.PARTIALLY_SUPPORTED
    assert after.analysis_confidence is Confidence.HIGH
    assert after.untouched == before.untouched
    assert after_result.untouched == "sealed-result"

    assert ELEMENT_ID not in after_result.issue_synthesis.unresolved_elements
    assert ELEMENT_ID in after_result.issue_synthesis.partially_supported_elements
    assert "partially supported: 1" in after_result.issue_synthesis.summary
    assert "unresolved: 0" in after_result.issue_synthesis.summary

    assert result.case_matrices.issue_matrix != matrices.issue_matrix
    assert result.case_matrices.evidence_matrix == matrices.evidence_matrix
    assert result.case_matrices.synthesis_id == matrices.synthesis_id
    assert result.case_matrices.source_analysis_ids == matrices.source_analysis_ids

    assert result.governed_issue_evidence_map == "u9b"
    assert result.governed_evidential_analysis == "u9c"
    assert (
        result.manifest.structured_legal_analysis_results_sha256
        != predecessor.structured_legal_analysis_results_sha256
    )
    assert result.manifest.case_matrices_sha256 != predecessor.case_matrices_sha256
    assert (
        result.manifest.governed_issue_evidence_map_sha256
        == predecessor.governed_issue_evidence_map_sha256
    )
    assert (
        result.manifest.governed_evidential_analysis_sha256
        == predecessor.governed_evidential_analysis_sha256
    )
    assert result.manifest.authority_id != predecessor.authority_id
    assert result.receipt.predecessor_authority_id == predecessor.authority_id
    assert result.receipt.successor_authority_id == result.manifest.authority_id
    assert result.receipt.proposal_id == event.proposal_id


def test_revision_into_disputed_rebuilds_issue_synthesis_and_limitations(monkeypatch):
    results = _results(status=ElementAnalysisStatus.UNRESOLVED)
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(
        authority_id=predecessor.authority_id,
        current_status=ElementAnalysisStatus.UNRESOLVED.value,
        proposed_status=ElementAnalysisStatus.DISPUTED.value,
    )
    _install(monkeypatch, latest_event=event)

    result = revision.build_governed_authority_revision(
        predecessor_manifest=predecessor,
        proposal_events=(event,),
        proposal_id=event.proposal_id,
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map="u9b",
        governed_evidential_analysis="u9c",
    )
    revised = result.structured_legal_analysis_results[0]

    assert ELEMENT_ID in revised.issue_synthesis.disputed_elements
    assert ELEMENT_ID not in revised.issue_synthesis.unresolved_elements
    assert revised.overall_limitations == (
        f"{ELEMENT_ID}: a material factual dispute remains unresolved.",
    )


def test_revision_out_of_disputed_removes_only_status_derived_limitation(monkeypatch):
    gap = FakeGap(materiality=Materiality.HIGH, description="critical evidence gap")
    results = _results(
        status=ElementAnalysisStatus.DISPUTED,
        gaps=(gap,),
    )
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(
        authority_id=predecessor.authority_id,
        current_status=ElementAnalysisStatus.DISPUTED.value,
        proposed_status=ElementAnalysisStatus.PARTIALLY_SUPPORTED.value,
    )
    _install(monkeypatch, latest_event=event)

    result = revision.build_governed_authority_revision(
        predecessor_manifest=predecessor,
        proposal_events=(event,),
        proposal_id=event.proposal_id,
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map="u9b",
        governed_evidential_analysis="u9c",
    )
    revised = result.structured_legal_analysis_results[0]

    assert revised.overall_limitations == (
        f"{ELEMENT_ID}: critical evidence gap",
    )
    assert ELEMENT_ID not in revised.issue_synthesis.disputed_elements
    assert ELEMENT_ID in revised.issue_synthesis.partially_supported_elements


def test_confidence_only_revision_keeps_status_derived_fields_exact(monkeypatch):
    results = _results(
        status=ElementAnalysisStatus.PARTIALLY_SUPPORTED,
        confidence=Confidence.LOW,
    )
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(
        authority_id=predecessor.authority_id,
        current_status=ElementAnalysisStatus.PARTIALLY_SUPPORTED.value,
        current_confidence=Confidence.LOW.value,
        proposed_status=ElementAnalysisStatus.PARTIALLY_SUPPORTED.value,
        proposed_confidence=Confidence.HIGH.value,
    )
    _install(monkeypatch, latest_event=event)

    result = revision.build_governed_authority_revision(
        predecessor_manifest=predecessor,
        proposal_events=(event,),
        proposal_id=event.proposal_id,
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map="u9b",
        governed_evidential_analysis="u9c",
    )
    revised = result.structured_legal_analysis_results[0]

    assert revised.issue_synthesis == results[0].issue_synthesis
    assert revised.overall_limitations == results[0].overall_limitations


def test_revision_is_deterministic(monkeypatch):
    _, _, _, _, first = _build(monkeypatch)
    _, _, _, _, second = _build(monkeypatch)

    assert first.structured_legal_analysis_results == second.structured_legal_analysis_results
    assert first.case_matrices == second.case_matrices
    assert first.manifest == second.manifest
    assert first.receipt == second.receipt
    assert (
        revision.dumps_governed_authority_revision_receipt(first.receipt)
        == revision.dumps_governed_authority_revision_receipt(second.receipt)
    )


@pytest.mark.parametrize(
    "state",
    [
        AnalyticalChangeProposalState.PROPOSED,
        AnalyticalChangeProposalState.REJECTED,
    ],
)
def test_unapproved_or_rejected_is_blocked(monkeypatch, state):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id, state=state)
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="APPROVED"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_wrong_predecessor_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=_h("wrong-authority"))
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="authority_id"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_wrong_case_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id)
    event.case_id = OTHER_ISSUE_ID
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="case_id"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_wrong_issue_binding_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id, issue_id=OTHER_ISSUE_ID)
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="not found"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("current_status", ElementAnalysisStatus.DISPUTED.value, "current_status"),
        ("current_confidence", Confidence.HIGH.value, "current_confidence"),
    ],
)
def test_wrong_current_m5_state_is_blocked(monkeypatch, field, value, match):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id)
    setattr(event, field, value)
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match=match):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_duplicate_m5_target_is_blocked(monkeypatch):
    results = _results(duplicate=True)
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id)
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="not unique"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_stale_approval_event_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    approved = _event(authority_id=predecessor.authority_id)
    rejected = _event(
        authority_id=predecessor.authority_id,
        state=AnalyticalChangeProposalState.REJECTED,
        event_id="rejection-event",
    )
    _install(monkeypatch, latest_event=rejected)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="APPROVED"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(approved, rejected),
            proposal_id=approved.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_noop_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(
        authority_id=predecessor.authority_id,
        proposed_status=ElementAnalysisStatus.UNRESOLVED.value,
        proposed_confidence=Confidence.LOW.value,
    )
    _install(monkeypatch, latest_event=event)

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="no-op"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )


def test_evidence_matrix_change_is_blocked(monkeypatch):
    results = _results()
    matrices = _matrices(results)
    predecessor = _manifest(results, matrices)
    event = _event(authority_id=predecessor.authority_id)
    _install(monkeypatch, latest_event=event)
    monkeypatch.setattr(
        revision,
        "build_evidence_matrix",
        lambda results: ("unexpected-evidence-change",),
    )

    with pytest.raises(revision.GovernedAuthorityRevisionError, match="evidence matrix"):
        revision.build_governed_authority_revision(
            predecessor_manifest=predecessor,
            proposal_events=(event,),
            proposal_id=event.proposal_id,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map="u9b",
            governed_evidential_analysis="u9c",
        )
