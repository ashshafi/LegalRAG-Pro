"""Read-only projection of professionally approved WorkingDraft work products."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Final

from drafting_working_draft_release_adapter import (
    WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
    WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
)
from work_product_artifact_store import WorkProductArtifactStore
from work_product_release import (
    WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION,
    WorkProductReleaseState,
    WorkProductReleaseTarget,
    load_work_product_release_events,
    project_work_product_release,
)


_SHA256_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)


class DraftingApprovedWorkProductError(RuntimeError):
    """Raised when approved WorkingDraft state cannot be validated read-only."""


@dataclass(frozen=True, slots=True)
class ApprovedWorkingDraftProduct:
    """Solicitor-facing read model for one currently approved WorkingDraft."""

    draft_id: str
    approved_at: str
    reviewer_reference: str
    review_note: str
    approved_wording: tuple[str, ...]
    court_or_tribunal_reliance: bool
    target_id: str


def _required(value: object, field_name: str) -> str:
    text = str(value or "").strip()

    if not text:
        raise DraftingApprovedWorkProductError(
            field_name + " is required."
        )

    return text


def _working_draft_id_from_artifact(
    *,
    artifact_bytes: bytes,
    renderer_version: str,
    output_profile: str,
) -> str:
    if renderer_version != WORKING_DRAFT_MARKDOWN_RENDERER_VERSION:
        raise DraftingApprovedWorkProductError(
            "approved artifact renderer is not the supported WorkingDraft renderer."
        )

    if output_profile != WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE:
        raise DraftingApprovedWorkProductError(
            "approved artifact is not a WorkingDraft professional-review product."
        )

    try:
        text = artifact_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact is not valid UTF-8."
        ) from exc

    lines = text.splitlines()

    draft_markers = [
        line[len("Draft ID: "):].strip()
        for line in lines
        if line.startswith("Draft ID: ")
    ]

    if len(draft_markers) != 1:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact does not contain exactly one Draft ID marker."
        )

    draft_id = draft_markers[0]

    if _SHA256_ID_RE.fullmatch(draft_id) is None:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact contains an invalid Draft ID."
        )

    statement_count = sum(
        1
        for line in lines
        if line.startswith("### Statement ")
    )

    authority_check_count = sum(
        1
        for line in lines
        if line.startswith("Authority check: ")
    )

    if statement_count < 1:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact contains no statement sections."
        )

    if statement_count != authority_check_count:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact statement/check structure is inconsistent."
        )

    return draft_id


def _release_target_from_binding(
    binding: object,
) -> WorkProductReleaseTarget:
    try:
        target = WorkProductReleaseTarget(
            schema_version=
                WORK_PRODUCT_RELEASE_TARGET_SCHEMA_VERSION,
            case_id=
                getattr(binding, "case_id"),
            report_projection_id=
                getattr(binding, "report_projection_id"),
            projection_payload_sha256=
                getattr(binding, "projection_payload_sha256"),
            manifest_id=
                getattr(binding, "manifest_id"),
            artifact_format=
                getattr(binding, "artifact_format"),
            artifact_id=
                getattr(binding, "artifact_id"),
            artifact_sha256=
                getattr(binding, "artifact_sha256"),
            renderer_version=
                getattr(binding, "renderer_version"),
            output_profile=
                getattr(binding, "output_profile"),
            target_id=
                getattr(binding, "target_id"),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise DraftingApprovedWorkProductError(
            "immutable approved-work binding is incomplete or invalid."
        ) from exc

    return target


def _approved_wording_from_artifact(
    *,
    artifact_bytes: bytes,
    renderer_version: str,
    output_profile: str,
) -> tuple[str, ...]:
    _working_draft_id_from_artifact(
        artifact_bytes=artifact_bytes,
        renderer_version=renderer_version,
        output_profile=output_profile,
    )

    try:
        markdown = artifact_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact is not valid UTF-8."
        ) from exc

    lines = markdown.splitlines()
    section_heading = "## Proposed wording and current authority checks"

    section_indexes = tuple(
        index
        for index, line in enumerate(lines)
        if line.strip() == section_heading
    )

    if len(section_indexes) != 1:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact does not contain one exact wording section."
        )

    section_start = section_indexes[0] + 1
    statement_headings: list[tuple[int, int]] = []

    for index in range(section_start, len(lines)):
        stripped = lines[index].strip()
        prefix = "### Statement "

        if not stripped.startswith(prefix):
            continue

        suffix = stripped[len(prefix):]

        if not suffix or not suffix.isdigit() or int(suffix) < 1:
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft artifact contains an invalid statement heading."
            )

        statement_headings.append((index, int(suffix)))

    if not statement_headings:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft artifact contains no approved statement wording."
        )

    expected_sequences = tuple(range(1, len(statement_headings) + 1))
    actual_sequences = tuple(
        sequence
        for _index, sequence in statement_headings
    )

    if actual_sequences != expected_sequences:
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft statement sequence is not exact."
        )

    preamble = lines[
        section_start:
        statement_headings[0][0]
    ]

    if any(value.strip() for value in preamble):
        raise DraftingApprovedWorkProductError(
            "approved WorkingDraft wording section contains unexpected preamble content."
        )

    wording: list[str] = []

    for position, (heading_index, sequence) in enumerate(statement_headings):
        next_heading_index = (
            statement_headings[position + 1][0]
            if position + 1 < len(statement_headings)
            else len(lines)
        )

        block = lines[
            heading_index + 1:
            next_heading_index
        ]

        authority_indexes = tuple(
            index
            for index, line in enumerate(block)
            if line.startswith("Authority check: ")
        )

        if len(authority_indexes) != 1:
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft statement "
                + str(sequence)
                + " does not contain one exact authority-check boundary."
            )

        content = list(block[:authority_indexes[0]])

        while content and not content[0].strip():
            content.pop(0)

        while content and not content[-1].strip():
            content.pop()

        if not content:
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft statement "
                + str(sequence)
                + " contains no wording."
            )

        if any(
            value.lstrip().startswith("#")
            for value in content
        ):
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft statement wording contains an unexpected heading."
            )

        statement_text = "\n".join(content)

        if not statement_text.strip():
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft statement wording is empty."
            )

        wording.append(statement_text)

    return tuple(wording)


def load_approved_working_draft_products(
    case_id: str,
    *,
    root: str | Path | None = None,
) -> tuple[ApprovedWorkingDraftProduct, ...]:
    """Load currently approved WorkingDraft products without creating state."""

    clean_case_id = _required(
        case_id,
        "case_id",
    )

    try:
        events = load_work_product_release_events(
            clean_case_id,
            root=root,
        )
        store = WorkProductArtifactStore(
            root=root,
        )
    except Exception as exc:
        raise DraftingApprovedWorkProductError(
            "professional release history could not be loaded."
        ) from exc

    products: list[ApprovedWorkingDraftProduct] = []
    seen_targets: set[str] = set()
    seen_drafts: set[str] = set()

    for event in events:
        target_id = _required(
            getattr(event, "target_id", ""),
            "target_id",
        )

        if target_id in seen_targets:
            continue

        seen_targets.add(target_id)

        try:
            binding = store.load_binding(
                clean_case_id,
                target_id,
            )
        except Exception as exc:
            raise DraftingApprovedWorkProductError(
                "an immutable professional-review binding could not be validated."
            ) from exc

        if getattr(binding, "output_profile", "") != (
            WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE
        ):
            continue

        if getattr(binding, "renderer_version", "") != (
            WORKING_DRAFT_MARKDOWN_RENDERER_VERSION
        ):
            raise DraftingApprovedWorkProductError(
                "a WorkingDraft professional-review binding uses an unsupported renderer."
            )

        if getattr(binding, "artifact_format", "") != "markdown":
            raise DraftingApprovedWorkProductError(
                "a WorkingDraft professional-review binding is not Markdown."
            )

        if getattr(binding, "case_id", "") != clean_case_id:
            raise DraftingApprovedWorkProductError(
                "approved work-product binding belongs to a different case."
            )

        if getattr(binding, "target_id", "") != target_id:
            raise DraftingApprovedWorkProductError(
                "approved work-product binding does not match its release target."
            )

        target = _release_target_from_binding(
            binding
        )

        try:
            projection = project_work_product_release(
                target=target,
                events=events,
            )
        except Exception as exc:
            raise DraftingApprovedWorkProductError(
                "professional release state could not be projected."
            ) from exc

        if projection.state is not (
            WorkProductReleaseState.APPROVED_FOR_RELIANCE
        ):
            continue

        try:
            artifact_bytes = store.read_artifact(
                clean_case_id,
                target_id,
            )
        except Exception as exc:
            raise DraftingApprovedWorkProductError(
                "approved WorkingDraft artifact could not be validated."
            ) from exc

        draft_id = _working_draft_id_from_artifact(
            artifact_bytes=artifact_bytes,
            renderer_version=
                getattr(binding, "renderer_version", ""),
            output_profile=
                getattr(binding, "output_profile", ""),
        )

        approved_wording = _approved_wording_from_artifact(
            artifact_bytes=artifact_bytes,
            renderer_version=
                getattr(binding, "renderer_version", ""),
            output_profile=
                getattr(binding, "output_profile", ""),
        )

        if draft_id in seen_drafts:
            raise DraftingApprovedWorkProductError(
                "more than one current approved product resolves to the same WorkingDraft."
            )

        seen_drafts.add(draft_id)

        approved_at = _required(
            projection.recorded_at,
            "approved_at",
        )

        reviewer_reference = _required(
            projection.reviewer_reference,
            "reviewer_reference",
        )

        current_decision_events = tuple(
            candidate
            for candidate in events
            if getattr(
                candidate,
                "event_id",
                "",
            ) == projection.latest_event_id
            and getattr(
                candidate,
                "target_id",
                "",
            ) == target_id
        )

        if len(current_decision_events) != 1:
            raise DraftingApprovedWorkProductError(
                "the current approved WorkingDraft decision event is not unique."
            )

        current_decision_event = (
            current_decision_events[0]
        )

        decision_recorded_at = _required(
            getattr(
                current_decision_event,
                "recorded_at",
                "",
            ),
            "decision_recorded_at",
        )

        decision_reviewer_reference = _required(
            getattr(
                current_decision_event,
                "reviewer_reference",
                "",
            ),
            "decision_reviewer_reference",
        )

        review_note = _required(
            getattr(
                current_decision_event,
                "review_note",
                "",
            ),
            "review_note",
        )

        if decision_recorded_at != approved_at:
            raise DraftingApprovedWorkProductError(
                "the current professional decision timestamp does not match the approved projection."
            )

        if decision_reviewer_reference != reviewer_reference:
            raise DraftingApprovedWorkProductError(
                "the current professional decision reviewer does not match the approved projection."
            )

        if bool(
            getattr(
                current_decision_event,
                "court_or_tribunal_reliance",
                False,
            )
        ) != bool(
            projection.court_or_tribunal_reliance
        ):
            raise DraftingApprovedWorkProductError(
                "the current professional decision reliance scope does not match the approved projection."
            )

        products.append(
            ApprovedWorkingDraftProduct(
                draft_id=draft_id,
                approved_at=approved_at,
                reviewer_reference=
                    reviewer_reference,
                review_note=
                    review_note,
                approved_wording=
                    approved_wording,
                court_or_tribunal_reliance=
                    bool(
                        projection.court_or_tribunal_reliance
                    ),
                target_id=target_id,
            )
        )

    return tuple(products)
