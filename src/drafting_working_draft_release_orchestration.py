"""Professional release orchestration for immutable WorkingDraft artifacts.

This module adds no release state machine.

It prepares a fresh exact WorkingDraft professional-review artifact, enforces the
Drafting-specific NOT_AUTHORIZED approval prohibition, and delegates the actual
professional decision to the existing append-only ``work_product_release``
state machine.

No artifact file is written by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from drafting_working_draft_release_adapter import (
    PreparedWorkingDraftProfessionalReview,
    WorkingDraftReleaseAdapterError,
    prepare_working_draft_professional_review,
)
from work_product_artifact_store import (
    WorkProductArtifactStore,
)

from work_product_release import (
    WorkProductReleaseDecision,
    WorkProductReleaseEvent,
    WorkProductReleaseProjection,
    WorkProductReleaseState,
    load_work_product_release_events,
    project_work_product_release,
    record_work_product_release,
)


class WorkingDraftProfessionalReleaseError(RuntimeError):
    """Raised when a WorkingDraft professional release cannot proceed safely."""


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftProfessionalReleaseResult:
    """Exact result of one delegated professional release decision."""

    prepared_review: PreparedWorkingDraftProfessionalReview
    event: WorkProductReleaseEvent
    release_projection: WorkProductReleaseProjection


def _decision(
    value: WorkProductReleaseDecision | str,
) -> WorkProductReleaseDecision:
    try:
        return WorkProductReleaseDecision(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise WorkingDraftProfessionalReleaseError(
            "Professional release decision is invalid."
        ) from exc


def _result_text(
    value: object,
) -> str:
    if isinstance(
        value,
        Enum,
    ):
        value = value.value

    result = str(
        value
    ).strip()

    if not result:
        raise WorkingDraftProfessionalReleaseError(
            "WorkingDraft authority result is unavailable."
        )

    return result


def working_draft_authority_results(
    *,
    prepared_review: PreparedWorkingDraftProfessionalReview,
) -> tuple[str, ...]:
    """Return the exact current-authority result for every projected statement."""

    results = tuple(
        _result_text(
            item.result
        )
        for item
        in prepared_review.projection.authority_evaluations
    )

    if not results:
        raise WorkingDraftProfessionalReleaseError(
            "Professional-review projection contains no authority checks."
        )

    return results


def assert_working_draft_release_decision_allowed(
    *,
    prepared_review: PreparedWorkingDraftProfessionalReview,
    decision: WorkProductReleaseDecision | str,
) -> WorkProductReleaseDecision:
    """Apply Drafting-specific release policy before any release write.

    ALIGNED and CAUTION remain professional-review states, not automatic release
    decisions.  NOT_AUTHORIZED may be rejected but may never be approved for
    reliance.
    """

    decision_value = _decision(
        decision
    )

    results = working_draft_authority_results(
        prepared_review=
            prepared_review,
    )

    if (
        decision_value
        is WorkProductReleaseDecision.APPROVED_FOR_RELIANCE
        and "NOT_AUTHORIZED" in results
    ):
        raise WorkingDraftProfessionalReleaseError(
            "A WorkingDraft containing a NOT_AUTHORIZED statement "
            "cannot be approved for reliance."
        )

    return decision_value


def prepare_working_draft_professional_release(
    *,
    draft: object,
    authority: object,
) -> PreparedWorkingDraftProfessionalReview:
    """Prepare a fresh exact release target without recording a decision."""

    try:
        return (
            prepare_working_draft_professional_review(
                draft=draft,
                authority=authority,
            )
        )
    except WorkingDraftReleaseAdapterError:
        raise
    except Exception as exc:
        raise WorkingDraftProfessionalReleaseError(
            "WorkingDraft professional-review preparation failed."
        ) from exc


def _exact_working_draft_review_artifact_bytes(
    *,
    prepared_review: PreparedWorkingDraftProfessionalReview,
) -> bytes:
    # Return the exact UTF-8 Markdown bytes bound into the release target.

    if (
        prepared_review.target.artifact_format
        != "markdown"
    ):
        raise WorkingDraftProfessionalReleaseError(
            "WorkingDraft professional review artifact format is not markdown."
        )

    try:
        markdown = prepared_review.artifact.markdown
    except AttributeError as exc:
        raise WorkingDraftProfessionalReleaseError(
            "WorkingDraft professional review artifact does not expose markdown."
        ) from exc

    if not isinstance(markdown, str) or not markdown:
        raise WorkingDraftProfessionalReleaseError(
            "WorkingDraft professional review markdown is invalid."
        )

    return markdown.encode(
        "utf-8"
    )


def record_working_draft_professional_release(
    *,
    draft: object,
    authority: object,
    decision: WorkProductReleaseDecision | str,
    factual_basis_reviewed: bool,
    legal_authorities_reviewed: bool,
    unverified_authorities_remaining: int,
    professional_judgment_completed: bool,
    court_or_tribunal_reliance: bool,
    reviewer_reference: str,
    review_note: str,
    expected_target_id: str,
    root=None,
) -> WorkingDraftProfessionalReleaseResult:
    # Record one explicit professional decision for one exact published artifact.
    #
    # Sequence:
    #   1. fresh WorkingDraft/current-authority projection and release target;
    #   2. immutable publication of the exact neutral Markdown artifact;
    #   3. exact stored binding and artifact read-back verification;
    #   4. exact equality with the target the professional reviewed;
    #   5. Drafting-specific approval policy;
    #   6. existing work-product release recorder;
    #   7. reload and project the existing append-only release history.
    #
    # The WorkingDraft, analytical authority and task are not mutated.
    # Release state remains solely in the existing work-product release history.

    prepared = (
        prepare_working_draft_professional_release(
            draft=draft,
            authority=authority,
        )
    )

    artifact_bytes = (
        _exact_working_draft_review_artifact_bytes(
            prepared_review=
                prepared,
        )
    )

    try:
        store = WorkProductArtifactStore(
            root
        )

        published_binding = (
            store.publish_artifact(
                target=
                    prepared.target,
                content=
                    artifact_bytes,
            )
        )

        loaded_binding = (
            store.load_binding(
                prepared.target.case_id,
                prepared.target.target_id,
            )
        )

        stored_artifact_bytes = (
            store.read_artifact(
                prepared.target.case_id,
                prepared.target.target_id,
            )
        )
    except Exception as exc:
        raise WorkingDraftProfessionalReleaseError(
            "Immutable work-product artifact publication failed."
        ) from exc

    if loaded_binding != published_binding:
        raise WorkingDraftProfessionalReleaseError(
            "Published work-product artifact binding failed exact verification."
        )

    if stored_artifact_bytes != artifact_bytes:
        raise WorkingDraftProfessionalReleaseError(
            "Published work-product artifact bytes failed exact verification."
        )

    if (
        published_binding.case_id
        != prepared.target.case_id
        or published_binding.target_id
        != prepared.target.target_id
        or published_binding.artifact_id
        != prepared.target.artifact_id
        or published_binding.artifact_sha256
        != prepared.target.artifact_sha256
    ):
        raise WorkingDraftProfessionalReleaseError(
            "Published work-product artifact binding does not match "
            "the freshly prepared release target."
        )

    reviewed_target_id = str(
        expected_target_id
    ).strip()

    if not reviewed_target_id:
        raise WorkingDraftProfessionalReleaseError(
            "expected_target_id must identify the exact reviewed artifact."
        )

    if (
        prepared.target.target_id
        != reviewed_target_id
    ):
        raise WorkingDraftProfessionalReleaseError(
            "The exact WorkingDraft review target changed after professional "
            "review. Review the freshly prepared artifact before recording "
            "a decision."
        )

    decision_value = (
        assert_working_draft_release_decision_allowed(
            prepared_review=
                prepared,
            decision=
                decision,
        )
    )

    try:
        event = record_work_product_release(
            target=
                prepared.target,
            decision=
                decision_value,
            factual_basis_reviewed=
                factual_basis_reviewed,
            legal_authorities_reviewed=
                legal_authorities_reviewed,
            unverified_authorities_remaining=
                unverified_authorities_remaining,
            professional_judgment_completed=
                professional_judgment_completed,
            court_or_tribunal_reliance=
                court_or_tribunal_reliance,
            reviewer_reference=
                reviewer_reference,
            review_note=
                review_note,
            root=
                root,
        )

        events = load_work_product_release_events(
            prepared.target.case_id,
            root=root,
        )

        projected = (
            project_work_product_release(
                target=
                    prepared.target,
                events=
                    events,
            )
        )
    except Exception as exc:
        raise WorkingDraftProfessionalReleaseError(
            "Existing work-product release processing failed."
        ) from exc

    if (
        projected.latest_event_id
        != event.event_id
    ):
        raise WorkingDraftProfessionalReleaseError(
            "Recorded release event is not the current event for the exact target."
        )

    expected_state = (
        WorkProductReleaseState.APPROVED_FOR_RELIANCE
        if (
            decision_value
            is WorkProductReleaseDecision.APPROVED_FOR_RELIANCE
        )
        else WorkProductReleaseState.REJECTED
    )

    if (
        projected.state
        is not expected_state
    ):
        raise WorkingDraftProfessionalReleaseError(
            "Projected release state does not match the explicit decision."
        )

    if (
        projected.court_or_tribunal_reliance
        is not court_or_tribunal_reliance
    ):
        raise WorkingDraftProfessionalReleaseError(
            "Projected court-or-tribunal reliance does not match the decision."
        )

    return WorkingDraftProfessionalReleaseResult(
        prepared_review=
            prepared,
        event=
            event,
        release_projection=
            projected,
    )




__all__ = [
    "WorkingDraftProfessionalReleaseError",
    "WorkingDraftProfessionalReleaseResult",
    "assert_working_draft_release_decision_allowed",
    "prepare_working_draft_professional_release",
    "record_working_draft_professional_release",
    "working_draft_authority_results",
]
