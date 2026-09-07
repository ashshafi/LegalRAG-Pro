"""Deterministic professional-review artifact adapter for immutable WorkingDrafts.

This module does not create release state.

It projects one immutable WorkingDraft together with a fresh governed authority
evaluation into a deterministic professional-review snapshot, renders exact
Markdown bytes, and adapts those bytes to the existing work-product release
target contract.

It deliberately does not use the case-report projection/rendering pipeline.
A WorkingDraft is not a deterministic full case report.

Release decisions remain exclusively owned by ``work_product_release``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from drafting_working_draft_authority import (
    evaluate_working_draft_authority,
)
from work_product_release import (
    WorkProductReleaseTarget,
    build_work_product_release_target,
)


WORKING_DRAFT_RELEASE_PROJECTION_SCHEMA_VERSION: Final[str] = (
    "drafting-working-draft-release-projection/1.0"
)

WORKING_DRAFT_RELEASE_MANIFEST_SCHEMA_VERSION: Final[str] = (
    "drafting-working-draft-release-manifest/1.0"
)

WORKING_DRAFT_MARKDOWN_RENDERER_VERSION: Final[str] = (
    "drafting-working-draft-markdown-renderer/1.0"
)

WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE: Final[str] = (
    "working-draft-professional-review/1.0"
)

_PROJECTION_NAMESPACE: Final[UUID] = uuid5(
    NAMESPACE_URL,
    "urn:legalrag:drafting-working-draft-release-projection:1.0",
)

_MANIFEST_NAMESPACE: Final[UUID] = uuid5(
    NAMESPACE_URL,
    "urn:legalrag:drafting-working-draft-release-manifest:1.0",
)

_MARKDOWN_NAMESPACE: Final[UUID] = uuid5(
    NAMESPACE_URL,
    "urn:legalrag:drafting-working-draft-markdown-artifact:1.0",
)


class WorkingDraftReleaseAdapterError(RuntimeError):
    """Raised when an exact professional-review snapshot cannot be trusted."""


def _text(
    value: object,
    *,
    field_name: str,
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
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must be non-empty."
        )

    return result


def _canonical_uuid(
    value: object,
    *,
    field_name: str,
) -> str:
    raw = _text(
        value,
        field_name=field_name,
    )

    try:
        canonical = str(
            UUID(
                raw
            )
        )
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must be a canonical UUID."
        ) from exc

    if canonical != raw:
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must use canonical UUID form."
        )

    return canonical


def _sha256_hex(
    value: object,
    *,
    field_name: str,
) -> str:
    raw = _text(
        value,
        field_name=field_name,
    )

    if (
        len(
            raw
        )
        != 64
        or any(
            character
            not in "0123456789abcdef"
            for character in raw
        )
    ):
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must be a lowercase SHA-256 hex digest."
        )

    return raw


def _sha256_identity(
    value: object,
    *,
    field_name: str,
) -> str:
    raw = _text(
        value,
        field_name=field_name,
    )

    if not raw.startswith(
        "sha256:"
    ):
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must use sha256: identity form."
        )

    _sha256_hex(
        raw[
            len(
                "sha256:"
            ):
        ],
        field_name=field_name,
    )

    return raw


def _canonical_json_bytes(
    value: object,
) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise WorkingDraftReleaseAdapterError(
            "Professional-review projection is not canonically serialisable."
        ) from exc


def _payload_sha256(
    value: object,
) -> str:
    return sha256(
        _canonical_json_bytes(
            value
        )
    ).hexdigest()


def _stable_uuid(
    namespace: UUID,
    identity: str,
) -> str:
    return str(
        uuid5(
            namespace,
            identity,
        )
    )


def _string_tuple(
    values: object,
    *,
    field_name: str,
    non_empty: bool = False,
) -> tuple[str, ...]:
    try:
        items = tuple(
            _text(
                item,
                field_name=field_name,
            )
            for item in values
        )
    except TypeError as exc:
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must be iterable."
        ) from exc

    if (
        non_empty
        and not items
    ):
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must not be empty."
        )

    if len(
        set(
            items
        )
    ) != len(
        items
    ):
        raise WorkingDraftReleaseAdapterError(
            field_name
            + " must not contain duplicates."
        )

    return items


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftReleaseCaseHeader:
    """Minimal case binding required by the existing release-target contract."""

    case_id: str

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "case_id",
            _canonical_uuid(
                self.case_id,
                field_name=
                    "case_id",
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftReleaseStatement:
    """Exact immutable statement carried into professional review."""

    sequence: int
    statement_id: str
    element_id: str
    text: str
    claimed_status: str
    claimed_confidence: str
    cited_evidence_keys: tuple[str, ...]

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.sequence,
                int,
            )
            or isinstance(
                self.sequence,
                bool,
            )
            or self.sequence < 1
        ):
            raise WorkingDraftReleaseAdapterError(
                "statement sequence must be a positive integer."
            )

        object.__setattr__(
            self,
            "statement_id",
            _sha256_identity(
                self.statement_id,
                field_name=
                    "statement_id",
            ),
        )

        for name in (
            "element_id",
            "text",
            "claimed_status",
            "claimed_confidence",
        ):
            object.__setattr__(
                self,
                name,
                _text(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )

        object.__setattr__(
            self,
            "cited_evidence_keys",
            _string_tuple(
                self.cited_evidence_keys,
                field_name=
                    "cited_evidence_keys",
                non_empty=True,
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftReleaseAuthorityCheck:
    """Frozen current-authority check for one exact statement."""

    sequence: int
    statement_id: str
    element_id: str
    result: str
    current_status: str
    current_confidence: str
    reasons: tuple[str, ...]
    cited_evidence_keys: tuple[str, ...]

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.sequence,
                int,
            )
            or isinstance(
                self.sequence,
                bool,
            )
            or self.sequence < 1
        ):
            raise WorkingDraftReleaseAdapterError(
                "authority-check sequence must be a positive integer."
            )

        object.__setattr__(
            self,
            "statement_id",
            _sha256_identity(
                self.statement_id,
                field_name=
                    "authority check statement_id",
            ),
        )

        for name in (
            "element_id",
            "result",
            "current_status",
            "current_confidence",
        ):
            object.__setattr__(
                self,
                name,
                _text(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )

        object.__setattr__(
            self,
            "reasons",
            _string_tuple(
                self.reasons,
                field_name=
                    "authority check reasons",
            ),
        )

        object.__setattr__(
            self,
            "cited_evidence_keys",
            _string_tuple(
                self.cited_evidence_keys,
                field_name=
                    "authority check cited_evidence_keys",
                non_empty=True,
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftReleaseManifest:
    """Deterministic manifest for one professional-review projection."""

    manifest_id: str
    manifest_payload_sha256: str
    schema_version: str
    case_id: str
    draft_id: str
    review_authority_id: str
    report_projection_id: str
    projection_payload_sha256: str
    ordered_statement_ids: tuple[str, ...]
    authority_results: tuple[
        tuple[
            str,
            str,
        ],
        ...,
    ]

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "manifest_id",
            _canonical_uuid(
                self.manifest_id,
                field_name=
                    "manifest_id",
            ),
        )

        object.__setattr__(
            self,
            "manifest_payload_sha256",
            _sha256_hex(
                self.manifest_payload_sha256,
                field_name=
                    "manifest_payload_sha256",
            ),
        )

        if (
            self.schema_version
            != WORKING_DRAFT_RELEASE_MANIFEST_SCHEMA_VERSION
        ):
            raise WorkingDraftReleaseAdapterError(
                "Unsupported working-draft release manifest schema."
            )

        object.__setattr__(
            self,
            "case_id",
            _canonical_uuid(
                self.case_id,
                field_name=
                    "manifest case_id",
            ),
        )

        object.__setattr__(
            self,
            "draft_id",
            _sha256_identity(
                self.draft_id,
                field_name=
                    "manifest draft_id",
            ),
        )

        object.__setattr__(
            self,
            "review_authority_id",
            _sha256_identity(
                self.review_authority_id,
                field_name=
                    "manifest review_authority_id",
            ),
        )

        object.__setattr__(
            self,
            "report_projection_id",
            _canonical_uuid(
                self.report_projection_id,
                field_name=
                    "manifest report_projection_id",
            ),
        )

        object.__setattr__(
            self,
            "projection_payload_sha256",
            _sha256_hex(
                self.projection_payload_sha256,
                field_name=
                    "manifest projection_payload_sha256",
            ),
        )

        ordered = tuple(
            _sha256_identity(
                item,
                field_name=
                    "manifest ordered_statement_ids",
            )
            for item
            in self.ordered_statement_ids
        )

        if not ordered:
            raise WorkingDraftReleaseAdapterError(
                "Release manifest must contain at least one statement."
            )

        if len(
            set(
                ordered
            )
        ) != len(
            ordered
        ):
            raise WorkingDraftReleaseAdapterError(
                "Release manifest statement IDs must be unique."
            )

        object.__setattr__(
            self,
            "ordered_statement_ids",
            ordered,
        )

        results = tuple(
            (
                _sha256_identity(
                    statement_id,
                    field_name=
                        "manifest authority result statement_id",
                ),
                _text(
                    result,
                    field_name=
                        "manifest authority result",
                ),
            )
            for (
                statement_id,
                result,
            )
            in self.authority_results
        )

        if tuple(
            statement_id
            for (
                statement_id,
                _result,
            )
            in results
        ) != ordered:
            raise WorkingDraftReleaseAdapterError(
                "Manifest authority-result order does not match statements."
            )

        object.__setattr__(
            self,
            "authority_results",
            results,
        )

        expected_payload = _manifest_payload(
            case_id=
                self.case_id,
            draft_id=
                self.draft_id,
            review_authority_id=
                self.review_authority_id,
            report_projection_id=
                self.report_projection_id,
            projection_payload_sha256=
                self.projection_payload_sha256,
            ordered_statement_ids=
                self.ordered_statement_ids,
            authority_results=
                self.authority_results,
        )

        expected_sha = _payload_sha256(
            expected_payload
        )

        if (
            self.manifest_payload_sha256
            != expected_sha
        ):
            raise WorkingDraftReleaseAdapterError(
                "manifest_payload_sha256 does not match manifest semantics."
            )

        expected_id = _stable_uuid(
            _MANIFEST_NAMESPACE,
            expected_sha,
        )

        if (
            self.manifest_id
            != expected_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "manifest_id does not match deterministic manifest identity."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftProfessionalReviewProjection:
    """Renderer-neutral exact snapshot of one WorkingDraft and fresh checks.

    ``report_projection_id`` is the compatibility coordinate required by the
    existing generic work-product release target.  This object is deliberately
    not a CaseReportProjection.
    """

    schema_version: str
    report_projection_id: str
    projection_payload_sha256: str
    case_header: WorkingDraftReleaseCaseHeader
    manifest: WorkingDraftReleaseManifest

    draft_id: str
    draft_schema_version: str
    task_id: str
    progress_id: str
    scope_binding_id: str
    draft_authority_id: str
    review_authority_id: str
    issue_analysis_id: str
    issue_definition_id: str
    title: str
    purpose: str
    creator_reference: str
    task_work_recorded_at: str
    task_work_question_sha256: str
    task_work_answer_sha256: str
    draft_recorded_at: str

    statements: tuple[
        WorkingDraftReleaseStatement,
        ...,
    ]

    authority_evaluations: tuple[
        WorkingDraftReleaseAuthorityCheck,
        ...,
    ]

    def __post_init__(
        self,
    ) -> None:
        if (
            self.schema_version
            != WORKING_DRAFT_RELEASE_PROJECTION_SCHEMA_VERSION
        ):
            raise WorkingDraftReleaseAdapterError(
                "Unsupported working-draft release projection schema."
            )

        object.__setattr__(
            self,
            "report_projection_id",
            _canonical_uuid(
                self.report_projection_id,
                field_name=
                    "report_projection_id",
            ),
        )

        object.__setattr__(
            self,
            "projection_payload_sha256",
            _sha256_hex(
                self.projection_payload_sha256,
                field_name=
                    "projection_payload_sha256",
            ),
        )

        object.__setattr__(
            self,
            "draft_id",
            _sha256_identity(
                self.draft_id,
                field_name=
                    "draft_id",
            ),
        )

        object.__setattr__(
            self,
            "task_id",
            _canonical_uuid(
                self.task_id,
                field_name=
                    "task_id",
            ),
        )

        object.__setattr__(
            self,
            "progress_id",
            _canonical_uuid(
                self.progress_id,
                field_name=
                    "progress_id",
            ),
        )

        object.__setattr__(
            self,
            "scope_binding_id",
            _sha256_identity(
                self.scope_binding_id,
                field_name=
                    "scope_binding_id",
            ),
        )

        object.__setattr__(
            self,
            "draft_authority_id",
            _sha256_identity(
                self.draft_authority_id,
                field_name=
                    "draft_authority_id",
            ),
        )

        object.__setattr__(
            self,
            "review_authority_id",
            _sha256_identity(
                self.review_authority_id,
                field_name=
                    "review_authority_id",
            ),
        )

        for name in (
            "draft_schema_version",
            "issue_analysis_id",
            "issue_definition_id",
            "title",
            "purpose",
            "creator_reference",
            "task_work_recorded_at",
            "draft_recorded_at",
        ):
            object.__setattr__(
                self,
                name,
                _text(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )

        object.__setattr__(
            self,
            "task_work_question_sha256",
            _sha256_hex(
                self.task_work_question_sha256,
                field_name=
                    "task_work_question_sha256",
            ),
        )

        object.__setattr__(
            self,
            "task_work_answer_sha256",
            _sha256_hex(
                self.task_work_answer_sha256,
                field_name=
                    "task_work_answer_sha256",
            ),
        )

        statements = tuple(
            self.statements
        )

        checks = tuple(
            self.authority_evaluations
        )

        if not statements:
            raise WorkingDraftReleaseAdapterError(
                "Professional-review projection must contain statements."
            )

        expected_sequences = tuple(
            range(
                1,
                len(
                    statements
                )
                + 1,
            )
        )

        if tuple(
            item.sequence
            for item
            in statements
        ) != expected_sequences:
            raise WorkingDraftReleaseAdapterError(
                "Projection statements are not in canonical sequence."
            )

        if tuple(
            item.sequence
            for item
            in checks
        ) != expected_sequences:
            raise WorkingDraftReleaseAdapterError(
                "Authority checks are not in canonical sequence."
            )

        statement_ids = tuple(
            item.statement_id
            for item
            in statements
        )

        check_ids = tuple(
            item.statement_id
            for item
            in checks
        )

        if (
            statement_ids
            != check_ids
        ):
            raise WorkingDraftReleaseAdapterError(
                "Authority checks do not bind the exact statement sequence."
            )

        for statement, check in zip(
            statements,
            checks,
            strict=True,
        ):
            if (
                statement.element_id
                != check.element_id
            ):
                raise WorkingDraftReleaseAdapterError(
                    "Authority check element does not match statement."
                )

            if (
                statement.cited_evidence_keys
                != check.cited_evidence_keys
            ):
                raise WorkingDraftReleaseAdapterError(
                    "Authority check citations do not match exact statement citations."
                )

        if (
            self.case_header.case_id
            != self.manifest.case_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Projection case and manifest case do not match."
            )

        if (
            self.manifest.draft_id
            != self.draft_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Projection draft and manifest draft do not match."
            )

        if (
            self.manifest.review_authority_id
            != self.review_authority_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Projection and manifest review authority do not match."
            )

        if (
            self.manifest.report_projection_id
            != self.report_projection_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Projection and manifest IDs do not match."
            )

        if (
            self.manifest.projection_payload_sha256
            != self.projection_payload_sha256
        ):
            raise WorkingDraftReleaseAdapterError(
                "Projection and manifest payload hashes do not match."
            )

        if (
            self.manifest.ordered_statement_ids
            != statement_ids
        ):
            raise WorkingDraftReleaseAdapterError(
                "Manifest statement order does not match projection."
            )

        expected_payload = _projection_payload_from_projection(
            self
        )

        expected_sha = _payload_sha256(
            expected_payload
        )

        if (
            self.projection_payload_sha256
            != expected_sha
        ):
            raise WorkingDraftReleaseAdapterError(
                "projection_payload_sha256 does not match projection semantics."
            )

        expected_id = _stable_uuid(
            _PROJECTION_NAMESPACE,
            expected_sha,
        )

        if (
            self.report_projection_id
            != expected_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "report_projection_id does not match deterministic projection identity."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class WorkingDraftProfessionalReviewMarkdown:
    """Immutable exact Markdown bytes for professional reliance review."""

    markdown_report_id: str
    renderer_version: str
    output_profile: str
    report_projection_id: str
    manifest_id: str
    projection_payload_sha256: str
    markdown_sha256: str
    report_manifest: WorkingDraftReleaseManifest
    markdown: str

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "markdown_report_id",
            _canonical_uuid(
                self.markdown_report_id,
                field_name=
                    "markdown_report_id",
            ),
        )

        if (
            self.renderer_version
            != WORKING_DRAFT_MARKDOWN_RENDERER_VERSION
        ):
            raise WorkingDraftReleaseAdapterError(
                "Unsupported working-draft Markdown renderer version."
            )

        if (
            self.output_profile
            != WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE
        ):
            raise WorkingDraftReleaseAdapterError(
                "Unsupported working-draft Markdown output profile."
            )

        object.__setattr__(
            self,
            "report_projection_id",
            _canonical_uuid(
                self.report_projection_id,
                field_name=
                    "artifact report_projection_id",
            ),
        )

        object.__setattr__(
            self,
            "manifest_id",
            _canonical_uuid(
                self.manifest_id,
                field_name=
                    "artifact manifest_id",
            ),
        )

        object.__setattr__(
            self,
            "projection_payload_sha256",
            _sha256_hex(
                self.projection_payload_sha256,
                field_name=
                    "artifact projection_payload_sha256",
            ),
        )

        object.__setattr__(
            self,
            "markdown_sha256",
            _sha256_hex(
                self.markdown_sha256,
                field_name=
                    "markdown_sha256",
            ),
        )

        if (
            not isinstance(
                self.report_manifest,
                WorkingDraftReleaseManifest,
            )
        ):
            raise WorkingDraftReleaseAdapterError(
                "report_manifest must be a WorkingDraftReleaseManifest."
            )

        if (
            not isinstance(
                self.markdown,
                str,
            )
            or not self.markdown
        ):
            raise WorkingDraftReleaseAdapterError(
                "markdown must be non-empty text."
            )

        if "\r" in self.markdown:
            raise WorkingDraftReleaseAdapterError(
                "markdown must use LF newlines only."
            )

        if (
            not self.markdown.endswith(
                "\n"
            )
            or self.markdown.endswith(
                "\n\n"
            )
        ):
            raise WorkingDraftReleaseAdapterError(
                "markdown must end with exactly one LF."
            )

        if "\t" in self.markdown:
            raise WorkingDraftReleaseAdapterError(
                "markdown must not contain literal tabs."
            )

        if any(
            line.endswith(
                " "
            )
            for line
            in self.markdown.splitlines()
        ):
            raise WorkingDraftReleaseAdapterError(
                "markdown must not contain trailing spaces."
            )

        expected_sha = sha256(
            self.markdown.encode(
                "utf-8"
            )
        ).hexdigest()

        if (
            self.markdown_sha256
            != expected_sha
        ):
            raise WorkingDraftReleaseAdapterError(
                "markdown_sha256 does not match exact Markdown bytes."
            )

        if (
            self.report_manifest.manifest_id
            != self.manifest_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Markdown manifest ID does not match report manifest."
            )

        if (
            self.report_manifest.report_projection_id
            != self.report_projection_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Markdown projection ID does not match report manifest."
            )

        if (
            self.report_manifest.projection_payload_sha256
            != self.projection_payload_sha256
        ):
            raise WorkingDraftReleaseAdapterError(
                "Markdown projection hash does not match report manifest."
            )

        expected_id = _stable_uuid(
            _MARKDOWN_NAMESPACE,
            "|".join(
                (
                    self.report_projection_id,
                    self.manifest_id,
                    self.projection_payload_sha256,
                    self.markdown_sha256,
                )
            ),
        )

        if (
            self.markdown_report_id
            != expected_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "markdown_report_id does not match deterministic artifact identity."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedWorkingDraftProfessionalReview:
    """Pure in-memory bundle ready for existing release-state projection."""

    projection: WorkingDraftProfessionalReviewProjection
    artifact: WorkingDraftProfessionalReviewMarkdown
    target: WorkProductReleaseTarget


def _statement_payload(
    value: WorkingDraftReleaseStatement,
) -> dict[str, object]:
    return {
        "sequence":
            value.sequence,
        "statement_id":
            value.statement_id,
        "element_id":
            value.element_id,
        "text":
            value.text,
        "claimed_status":
            value.claimed_status,
        "claimed_confidence":
            value.claimed_confidence,
        "cited_evidence_keys":
            list(
                value.cited_evidence_keys
            ),
    }


def _authority_check_payload(
    value: WorkingDraftReleaseAuthorityCheck,
) -> dict[str, object]:
    return {
        "sequence":
            value.sequence,
        "statement_id":
            value.statement_id,
        "element_id":
            value.element_id,
        "result":
            value.result,
        "current_status":
            value.current_status,
        "current_confidence":
            value.current_confidence,
        "reasons":
            list(
                value.reasons
            ),
        "cited_evidence_keys":
            list(
                value.cited_evidence_keys
            ),
    }


def _projection_payload(
    *,
    case_id: str,
    draft_id: str,
    draft_schema_version: str,
    task_id: str,
    progress_id: str,
    scope_binding_id: str,
    draft_authority_id: str,
    review_authority_id: str,
    issue_analysis_id: str,
    issue_definition_id: str,
    title: str,
    purpose: str,
    creator_reference: str,
    task_work_recorded_at: str,
    task_work_question_sha256: str,
    task_work_answer_sha256: str,
    draft_recorded_at: str,
    statements: tuple[
        WorkingDraftReleaseStatement,
        ...,
    ],
    authority_evaluations: tuple[
        WorkingDraftReleaseAuthorityCheck,
        ...,
    ],
) -> dict[str, object]:
    return {
        "schema_version":
            WORKING_DRAFT_RELEASE_PROJECTION_SCHEMA_VERSION,
        "case_id":
            case_id,
        "draft_id":
            draft_id,
        "draft_schema_version":
            draft_schema_version,
        "task_id":
            task_id,
        "progress_id":
            progress_id,
        "scope_binding_id":
            scope_binding_id,
        "draft_authority_id":
            draft_authority_id,
        "review_authority_id":
            review_authority_id,
        "issue_analysis_id":
            issue_analysis_id,
        "issue_definition_id":
            issue_definition_id,
        "title":
            title,
        "purpose":
            purpose,
        "creator_reference":
            creator_reference,
        "task_work_recorded_at":
            task_work_recorded_at,
        "task_work_question_sha256":
            task_work_question_sha256,
        "task_work_answer_sha256":
            task_work_answer_sha256,
        "draft_recorded_at":
            draft_recorded_at,
        "statements": [
            _statement_payload(
                item
            )
            for item
            in statements
        ],
        "authority_evaluations": [
            _authority_check_payload(
                item
            )
            for item
            in authority_evaluations
        ],
    }


def _projection_payload_from_projection(
    value: WorkingDraftProfessionalReviewProjection,
) -> dict[str, object]:
    return _projection_payload(
        case_id=
            value.case_header.case_id,
        draft_id=
            value.draft_id,
        draft_schema_version=
            value.draft_schema_version,
        task_id=
            value.task_id,
        progress_id=
            value.progress_id,
        scope_binding_id=
            value.scope_binding_id,
        draft_authority_id=
            value.draft_authority_id,
        review_authority_id=
            value.review_authority_id,
        issue_analysis_id=
            value.issue_analysis_id,
        issue_definition_id=
            value.issue_definition_id,
        title=
            value.title,
        purpose=
            value.purpose,
        creator_reference=
            value.creator_reference,
        task_work_recorded_at=
            value.task_work_recorded_at,
        task_work_question_sha256=
            value.task_work_question_sha256,
        task_work_answer_sha256=
            value.task_work_answer_sha256,
        draft_recorded_at=
            value.draft_recorded_at,
        statements=
            value.statements,
        authority_evaluations=
            value.authority_evaluations,
    )


def _manifest_payload(
    *,
    case_id: str,
    draft_id: str,
    review_authority_id: str,
    report_projection_id: str,
    projection_payload_sha256: str,
    ordered_statement_ids: tuple[
        str,
        ...,
    ],
    authority_results: tuple[
        tuple[
            str,
            str,
        ],
        ...,
    ],
) -> dict[str, object]:
    return {
        "schema_version":
            WORKING_DRAFT_RELEASE_MANIFEST_SCHEMA_VERSION,
        "case_id":
            case_id,
        "draft_id":
            draft_id,
        "review_authority_id":
            review_authority_id,
        "report_projection_id":
            report_projection_id,
        "projection_payload_sha256":
            projection_payload_sha256,
        "ordered_statement_ids":
            list(
                ordered_statement_ids
            ),
        "authority_results": [
            {
                "statement_id":
                    statement_id,
                "result":
                    result,
            }
            for (
                statement_id,
                result,
            )
            in authority_results
        ],
    }


def build_working_draft_professional_review_projection(
    *,
    draft: object,
    authority: object,
) -> WorkingDraftProfessionalReviewProjection:
    """Freeze one WorkingDraft plus a fresh current-authority evaluation."""

    case_id = _canonical_uuid(
        getattr(
            draft,
            "case_id",
            None,
        ),
        field_name=
            "draft case_id",
    )

    draft_id = _sha256_identity(
        getattr(
            draft,
            "draft_id",
            None,
        ),
        field_name=
            "draft_id",
    )

    draft_authority_id = _sha256_identity(
        getattr(
            draft,
            "authority_id",
            None,
        ),
        field_name=
            "draft authority_id",
    )

    try:
        review_authority_id = _sha256_identity(
            authority.manifest.authority_id,
            field_name=
                "review authority_id",
        )
    except AttributeError as exc:
        raise WorkingDraftReleaseAdapterError(
            "Current authority manifest identity is unavailable."
        ) from exc

    try:
        evaluation = (
            evaluate_working_draft_authority(
                draft=draft,
                authority=authority,
            )
        )
    except Exception as exc:
        raise WorkingDraftReleaseAdapterError(
            "Fresh working-draft authority evaluation failed."
        ) from exc

    if _canonical_uuid(
        getattr(
            evaluation,
            "case_id",
            None,
        ),
        field_name=
            "evaluation case_id",
    ) != case_id:
        raise WorkingDraftReleaseAdapterError(
            "Authority evaluation belongs to a different case."
        )

    if _sha256_identity(
        getattr(
            evaluation,
            "draft_id",
            None,
        ),
        field_name=
            "evaluation draft_id",
    ) != draft_id:
        raise WorkingDraftReleaseAdapterError(
            "Authority evaluation belongs to a different draft."
        )

    if _sha256_identity(
        getattr(
            evaluation,
            "authority_id",
            None,
        ),
        field_name=
            "evaluation authority_id",
    ) != review_authority_id:
        raise WorkingDraftReleaseAdapterError(
            "Authority evaluation does not bind the current authority."
        )

    issue_analysis_id = _text(
        getattr(
            draft,
            "issue_analysis_id",
            None,
        ),
        field_name=
            "issue_analysis_id",
    )

    if _text(
        getattr(
            evaluation,
            "issue_analysis_id",
            None,
        ),
        field_name=
            "evaluation issue_analysis_id",
    ) != issue_analysis_id:
        raise WorkingDraftReleaseAdapterError(
            "Authority evaluation belongs to a different issue analysis."
        )

    raw_statements = tuple(
        getattr(
            draft,
            "statements",
            (),
        )
    )

    if not raw_statements:
        raise WorkingDraftReleaseAdapterError(
            "WorkingDraft contains no statements."
        )

    statements = tuple(
        WorkingDraftReleaseStatement(
            sequence=
                int(
                    getattr(
                        item,
                        "sequence",
                    )
                ),
            statement_id=
                getattr(
                    item,
                    "statement_id",
                ),
            element_id=
                getattr(
                    item,
                    "element_id",
                ),
            text=
                getattr(
                    item,
                    "text",
                ),
            claimed_status=
                getattr(
                    item,
                    "claimed_status",
                ),
            claimed_confidence=
                getattr(
                    item,
                    "claimed_confidence",
                ),
            cited_evidence_keys=
                tuple(
                    getattr(
                        item,
                        "cited_evidence_keys",
                        (),
                    )
                ),
        )
        for item
        in raw_statements
    )

    raw_evaluations = tuple(
        getattr(
            evaluation,
            "statement_evaluations",
            (),
        )
    )

    if len(
        raw_evaluations
    ) != len(
        statements
    ):
        raise WorkingDraftReleaseAdapterError(
            "Fresh authority evaluation does not cover every statement."
        )

    evaluation_by_statement: dict[
        str,
        object,
    ] = {}

    for item in raw_evaluations:
        statement_id = _sha256_identity(
            getattr(
                item,
                "statement_id",
                None,
            ),
            field_name=
                "evaluation statement_id",
        )

        if (
            statement_id
            in evaluation_by_statement
        ):
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority evaluation contains a duplicate statement."
            )

        evaluation_by_statement[
            statement_id
        ] = item

    authority_checks: list[
        WorkingDraftReleaseAuthorityCheck
    ] = []

    for statement in statements:
        item = evaluation_by_statement.get(
            statement.statement_id
        )

        if item is None:
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority evaluation omitted a draft statement."
            )

        check = getattr(
            item,
            "check",
            None,
        )

        if check is None:
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority evaluation has no statement check."
            )

        evaluation_sequence = int(
            getattr(
                item,
                "sequence",
            )
        )

        evaluation_element_id = _text(
            getattr(
                item,
                "element_id",
                None,
            ),
            field_name=
                "evaluation element_id",
        )

        check_citations = tuple(
            getattr(
                check,
                "cited_evidence_keys",
                (),
            )
        )

        authority_check = (
            WorkingDraftReleaseAuthorityCheck(
                sequence=
                    evaluation_sequence,
                statement_id=
                    statement.statement_id,
                element_id=
                    evaluation_element_id,
                result=
                    getattr(
                        check,
                        "result",
                    ),
                current_status=
                    getattr(
                        check,
                        "current_status",
                    ),
                current_confidence=
                    getattr(
                        check,
                        "current_confidence",
                    ),
                reasons=
                    tuple(
                        getattr(
                            check,
                            "reasons",
                            (),
                        )
                    ),
                cited_evidence_keys=
                    check_citations,
            )
        )

        if (
            authority_check.sequence
            != statement.sequence
        ):
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority check sequence does not match the statement."
            )

        if (
            authority_check.element_id
            != statement.element_id
        ):
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority check element does not match the statement."
            )

        if (
            authority_check.cited_evidence_keys
            != statement.cited_evidence_keys
        ):
            raise WorkingDraftReleaseAdapterError(
                "Fresh authority check citations do not match the statement."
            )

        authority_checks.append(
            authority_check
        )

    checks = tuple(
        authority_checks
    )

    payload = _projection_payload(
        case_id=
            case_id,
        draft_id=
            draft_id,
        draft_schema_version=
            _text(
                getattr(
                    draft,
                    "schema_version",
                    None,
                ),
                field_name=
                    "draft schema_version",
            ),
        task_id=
            _canonical_uuid(
                getattr(
                    draft,
                    "task_id",
                    None,
                ),
                field_name=
                    "task_id",
            ),
        progress_id=
            _canonical_uuid(
                getattr(
                    draft,
                    "progress_id",
                    None,
                ),
                field_name=
                    "progress_id",
            ),
        scope_binding_id=
            _sha256_identity(
                getattr(
                    draft,
                    "scope_binding_id",
                    None,
                ),
                field_name=
                    "scope_binding_id",
            ),
        draft_authority_id=
            draft_authority_id,
        review_authority_id=
            review_authority_id,
        issue_analysis_id=
            issue_analysis_id,
        issue_definition_id=
            _text(
                getattr(
                    draft,
                    "issue_definition_id",
                    None,
                ),
                field_name=
                    "issue_definition_id",
            ),
        title=
            _text(
                getattr(
                    draft,
                    "title",
                    None,
                ),
                field_name=
                    "title",
            ),
        purpose=
            _text(
                getattr(
                    draft,
                    "purpose",
                    None,
                ),
                field_name=
                    "purpose",
            ),
        creator_reference=
            _text(
                getattr(
                    draft,
                    "creator_reference",
                    None,
                ),
                field_name=
                    "creator_reference",
            ),
        task_work_recorded_at=
            _text(
                getattr(
                    draft,
                    "task_work_recorded_at",
                    None,
                ),
                field_name=
                    "task_work_recorded_at",
            ),
        task_work_question_sha256=
            _sha256_hex(
                getattr(
                    draft,
                    "task_work_question_sha256",
                    None,
                ),
                field_name=
                    "task_work_question_sha256",
            ),
        task_work_answer_sha256=
            _sha256_hex(
                getattr(
                    draft,
                    "task_work_answer_sha256",
                    None,
                ),
                field_name=
                    "task_work_answer_sha256",
            ),
        draft_recorded_at=
            _text(
                getattr(
                    draft,
                    "recorded_at",
                    None,
                ),
                field_name=
                    "draft recorded_at",
            ),
        statements=
            statements,
        authority_evaluations=
            checks,
    )

    projection_payload_sha256 = (
        _payload_sha256(
            payload
        )
    )

    report_projection_id = (
        _stable_uuid(
            _PROJECTION_NAMESPACE,
            projection_payload_sha256,
        )
    )

    ordered_statement_ids = tuple(
        item.statement_id
        for item
        in statements
    )

    authority_results = tuple(
        (
            item.statement_id,
            item.result,
        )
        for item
        in checks
    )

    manifest_payload = _manifest_payload(
        case_id=
            case_id,
        draft_id=
            draft_id,
        review_authority_id=
            review_authority_id,
        report_projection_id=
            report_projection_id,
        projection_payload_sha256=
            projection_payload_sha256,
        ordered_statement_ids=
            ordered_statement_ids,
        authority_results=
            authority_results,
    )

    manifest_payload_sha256 = (
        _payload_sha256(
            manifest_payload
        )
    )

    manifest_id = _stable_uuid(
        _MANIFEST_NAMESPACE,
        manifest_payload_sha256,
    )

    manifest = WorkingDraftReleaseManifest(
        manifest_id=
            manifest_id,
        manifest_payload_sha256=
            manifest_payload_sha256,
        schema_version=
            WORKING_DRAFT_RELEASE_MANIFEST_SCHEMA_VERSION,
        case_id=
            case_id,
        draft_id=
            draft_id,
        review_authority_id=
            review_authority_id,
        report_projection_id=
            report_projection_id,
        projection_payload_sha256=
            projection_payload_sha256,
        ordered_statement_ids=
            ordered_statement_ids,
        authority_results=
            authority_results,
    )

    return WorkingDraftProfessionalReviewProjection(
        schema_version=
            WORKING_DRAFT_RELEASE_PROJECTION_SCHEMA_VERSION,
        report_projection_id=
            report_projection_id,
        projection_payload_sha256=
            projection_payload_sha256,
        case_header=
            WorkingDraftReleaseCaseHeader(
                case_id=
                    case_id,
            ),
        manifest=
            manifest,
        draft_id=
            draft_id,
        draft_schema_version=
            payload[
                "draft_schema_version"
            ],
        task_id=
            payload[
                "task_id"
            ],
        progress_id=
            payload[
                "progress_id"
            ],
        scope_binding_id=
            payload[
                "scope_binding_id"
            ],
        draft_authority_id=
            draft_authority_id,
        review_authority_id=
            review_authority_id,
        issue_analysis_id=
            issue_analysis_id,
        issue_definition_id=
            payload[
                "issue_definition_id"
            ],
        title=
            payload[
                "title"
            ],
        purpose=
            payload[
                "purpose"
            ],
        creator_reference=
            payload[
                "creator_reference"
            ],
        task_work_recorded_at=
            payload[
                "task_work_recorded_at"
            ],
        task_work_question_sha256=
            payload[
                "task_work_question_sha256"
            ],
        task_work_answer_sha256=
            payload[
                "task_work_answer_sha256"
            ],
        draft_recorded_at=
            payload[
                "draft_recorded_at"
            ],
        statements=
            statements,
        authority_evaluations=
            checks,
    )


def render_working_draft_professional_review_markdown(
    *,
    projection: WorkingDraftProfessionalReviewProjection,
) -> WorkingDraftProfessionalReviewMarkdown:
    """Render exact neutral review bytes from the frozen projection only."""

    checks = {
        item.statement_id:
            item
        for item
        in projection.authority_evaluations
    }

    lines = [
        "# LegalRAG Pro ? Working Draft Professional Review",
        "",
        "## Reliance status",
        "",
        (
            "This exact review snapshot does not itself establish approval "
            "for reliance. Reliance status is held separately in the governed "
            "work-product release history."
        ),
        "",
        "## Draft",
        "",
        "Title: " + projection.title,
        "",
        "Purpose: " + projection.purpose,
        "",
        "Draft ID: " + projection.draft_id,
        "",
        "Draft authority: " + projection.draft_authority_id,
        "",
        "Review authority: " + projection.review_authority_id,
        "",
        "## Proposed wording and current authority checks",
        "",
    ]

    for statement in projection.statements:
        check = checks[
            statement.statement_id
        ]

        lines.extend(
            [
                "### Statement "
                + str(
                    statement.sequence
                ),
                "",
                statement.text,
                "",
                "Authority check: "
                + check.result,
                "",
                (
                    "Current assessment: "
                    + check.current_status
                    + " / "
                    + check.current_confidence
                ),
                "",
                "Review reasons:",
            ]
        )

        if check.reasons:
            for reason in check.reasons:
                lines.append(
                    "- "
                    + reason
                )
        else:
            lines.append(
                "- None recorded."
            )

        lines.extend(
            [
                "",
                "Evidence:",
            ]
        )

        for evidence_key in statement.cited_evidence_keys:
            lines.append(
                "- "
                + evidence_key
            )

        lines.append(
            ""
        )

    markdown = (
        "\n".join(
            lines
        ).rstrip()
        + "\n"
    )

    markdown_sha256 = sha256(
        markdown.encode(
            "utf-8"
        )
    ).hexdigest()

    markdown_report_id = _stable_uuid(
        _MARKDOWN_NAMESPACE,
        "|".join(
            (
                projection.report_projection_id,
                projection.manifest.manifest_id,
                projection.projection_payload_sha256,
                markdown_sha256,
            )
        ),
    )

    return WorkingDraftProfessionalReviewMarkdown(
        markdown_report_id=
            markdown_report_id,
        renderer_version=
            WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
        output_profile=
            WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
        report_projection_id=
            projection.report_projection_id,
        manifest_id=
            projection.manifest.manifest_id,
        projection_payload_sha256=
            projection.projection_payload_sha256,
        markdown_sha256=
            markdown_sha256,
        report_manifest=
            projection.manifest,
        markdown=
            markdown,
    )


def prepare_working_draft_professional_review(
    *,
    draft: object,
    authority: object,
) -> PreparedWorkingDraftProfessionalReview:
    """Prepare one exact in-memory target for the existing release state machine.

    This function performs no persistence and records no professional decision.
    """

    projection = (
        build_working_draft_professional_review_projection(
            draft=draft,
            authority=authority,
        )
    )

    artifact = (
        render_working_draft_professional_review_markdown(
            projection=projection,
        )
    )

    try:
        target = (
            build_work_product_release_target(
                projection=projection,
                artifact=artifact,
                artifact_format="markdown",
            )
        )
    except Exception as exc:
        raise WorkingDraftReleaseAdapterError(
            "Existing work-product release target rejected the exact "
            "WorkingDraft review artifact."
        ) from exc

    return PreparedWorkingDraftProfessionalReview(
        projection=
            projection,
        artifact=
            artifact,
        target=
            target,
    )


__all__ = [
    "PreparedWorkingDraftProfessionalReview",
    "WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE",
    "WORKING_DRAFT_MARKDOWN_RENDERER_VERSION",
    "WORKING_DRAFT_RELEASE_MANIFEST_SCHEMA_VERSION",
    "WORKING_DRAFT_RELEASE_PROJECTION_SCHEMA_VERSION",
    "WorkingDraftProfessionalReviewMarkdown",
    "WorkingDraftProfessionalReviewProjection",
    "WorkingDraftReleaseAdapterError",
    "WorkingDraftReleaseAuthorityCheck",
    "WorkingDraftReleaseCaseHeader",
    "WorkingDraftReleaseManifest",
    "WorkingDraftReleaseStatement",
    "build_working_draft_professional_review_projection",
    "prepare_working_draft_professional_review",
    "render_working_draft_professional_review_markdown",
]
