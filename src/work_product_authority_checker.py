from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


WORK_PRODUCT_AUTHORITY_CHECK_SCHEMA_VERSION = (
    "work-product-authority-check/1.0"
)


class WorkProductAuthorityCheckerError(
    RuntimeError
):
    pass


class WorkProductAuthorityResult(
    StrEnum
):
    ALIGNED = "ALIGNED"
    CAUTION = "CAUTION"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


@dataclass(
    frozen=True
)
class WorkProductAuthorityCheck:

    schema_version: str

    statement: str

    current_status: str
    current_confidence: str

    claimed_status: str
    claimed_confidence: str

    cited_evidence_keys: tuple[
        str,
        ...,
    ]

    result: WorkProductAuthorityResult

    reasons: tuple[
        str,
        ...,
    ]


_CONFIDENCE_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _text(
    value: object,
    *,
    field_name: str,
) -> str:

    if not isinstance(
        value,
        str,
    ):

        raise WorkProductAuthorityCheckerError(
            field_name
            + " must be text."
        )

    result = value.strip()

    if not result:

        raise WorkProductAuthorityCheckerError(
            field_name
            + " must not be blank."
        )

    return result


def _status(
    value: object,
    *,
    field_name: str,
) -> str:

    return (
        _text(
            value,
            field_name=
                field_name,
        )
        .lower()
        .replace(
            " ",
            "_",
        )
    )


def _confidence(
    value: object,
    *,
    field_name: str,
) -> str:

    result = (
        _text(
            value,
            field_name=
                field_name,
        )
        .lower()
    )

    if result not in _CONFIDENCE_RANK:

        raise WorkProductAuthorityCheckerError(
            field_name
            + " must be low, medium or high."
        )

    return result


def check_work_product_authority(
    *,
    statement: str,
    current_status: str,
    current_confidence: str,
    claimed_status: str,
    claimed_confidence: str,
    cited_evidence_keys: tuple[
        str,
        ...,
    ],
    allowed_evidence_keys: tuple[
        str,
        ...,
    ],
    approved_contradiction_count: int = 0,
    unresolved_matter_count: int = 0,
    formal_gap_count: int = 0,
) -> WorkProductAuthorityCheck:

    normalized_statement = _text(
        statement,
        field_name=
            "statement",
    )

    current_status_value = _status(
        current_status,
        field_name=
            "current_status",
    )

    current_confidence_value = (
        _confidence(
            current_confidence,
            field_name=
                "current_confidence",
        )
    )

    claimed_status_value = _status(
        claimed_status,
        field_name=
            "claimed_status",
    )

    claimed_confidence_value = (
        _confidence(
            claimed_confidence,
            field_name=
                "claimed_confidence",
        )
    )

    allowed = tuple(
        sorted(
            set(
                _text(
                    value,
                    field_name=
                        "allowed_evidence_key",
                )
                for value
                in allowed_evidence_keys
            )
        )
    )

    cited = tuple(
        sorted(
            set(
                _text(
                    value,
                    field_name=
                        "cited_evidence_key",
                )
                for value
                in cited_evidence_keys
            )
        )
    )

    reasons: list[
        str
    ] = []

    result = (
        WorkProductAuthorityResult.ALIGNED
    )

    foreign = tuple(
        value
        for value in cited
        if value not in allowed
    )

    if foreign:

        result = (
            WorkProductAuthorityResult.NOT_AUTHORIZED
        )

        reasons.append(
            "The stated evidence basis contains material "
            "outside this governed analytical element."
        )

    if (
        claimed_status_value
        != current_status_value
    ):

        result = (
            WorkProductAuthorityResult.NOT_AUTHORIZED
        )

        reasons.append(
            "The claimed analytical status differs from "
            "the current frozen governed status."
        )

    if (
        _CONFIDENCE_RANK[
            claimed_confidence_value
        ]
        >
        _CONFIDENCE_RANK[
            current_confidence_value
        ]
    ):

        result = (
            WorkProductAuthorityResult.NOT_AUTHORIZED
        )

        reasons.append(
            "The claimed confidence exceeds the current "
            "frozen governed confidence."
        )

    if (
        result
        is not WorkProductAuthorityResult.NOT_AUTHORIZED
        and not cited
    ):

        result = (
            WorkProductAuthorityResult.CAUTION
        )

        reasons.append(
            "No governed evidence item has been declared "
            "as the work-product evidence basis."
        )

    uncertainty_reasons: list[
        str
    ] = []

    if approved_contradiction_count:

        uncertainty_reasons.append(
            str(
                approved_contradiction_count
            )
            + " approved contradiction(s)"
        )

    if unresolved_matter_count:

        uncertainty_reasons.append(
            str(
                unresolved_matter_count
            )
            + " unresolved matter(s)"
        )

    if formal_gap_count:

        uncertainty_reasons.append(
            str(
                formal_gap_count
            )
            + " formal evidential gap(s)"
        )

    if (
        uncertainty_reasons
        and result
        is WorkProductAuthorityResult.ALIGNED
    ):

        result = (
            WorkProductAuthorityResult.CAUTION
        )

    if uncertainty_reasons:

        reasons.append(
            "Current authority carries material uncertainty: "
            + ", ".join(
                uncertainty_reasons
            )
            + "."
        )

    if not reasons:

        reasons.append(
            "The declared analytical status, confidence and "
            "evidence basis are aligned with the current "
            "frozen governed authority."
        )

    return WorkProductAuthorityCheck(
        schema_version=
            WORK_PRODUCT_AUTHORITY_CHECK_SCHEMA_VERSION,

        statement=
            normalized_statement,

        current_status=
            current_status_value,

        current_confidence=
            current_confidence_value,

        claimed_status=
            claimed_status_value,

        claimed_confidence=
            claimed_confidence_value,

        cited_evidence_keys=
            cited,

        result=
            result,

        reasons=
            tuple(
                reasons
            ),
    )


__all__ = [
    "WORK_PRODUCT_AUTHORITY_CHECK_SCHEMA_VERSION",
    "WorkProductAuthorityCheck",
    "WorkProductAuthorityCheckerError",
    "WorkProductAuthorityResult",
    "check_work_product_authority",
]
