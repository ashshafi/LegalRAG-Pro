from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any
import json

import streamlit as st

from governed_analytical_authority.provider import (
    load_active_governed_analytical_authority,
)

from matter_analysis_ledger import (
    MatterAnalysisLedgerError,
    RelationshipReviewState,
    RelationshipType,
    build_matter_analysis_ledger,
    load_relationship_events,
    propose_relationship,
    review_relationship,
)



EVIDENCE_SELECTOR_PRESENTATION_VERSION = (
    "matter-analysis-ledger-evidence-selector/1.0"
)


_ROLE_FIELDS = (
    (
        "SUPPORTING",
        "supporting_evidence_keys",
    ),
    (
        "ADVERSE",
        "adverse_evidence_keys",
    ),
    (
        "CORROBORATIVE",
        "corroborative_evidence_keys",
    ),
    (
        "CONFLICTING",
        "conflicting_evidence_keys",
    ),
    (
        "NEUTRAL/CONTEXT",
        "neutral_evidence_keys",
    ),
)


def _object_items(
    value: Any,
) -> tuple[tuple[str, Any], ...]:

    if isinstance(
        value,
        dict,
    ):
        return tuple(
            (
                str(key),
                item,
            )
            for key, item
            in value.items()
        )

    if is_dataclass(
        value
    ):
        return tuple(
            (
                field.name,
                getattr(
                    value,
                    field.name,
                ),
            )
            for field
            in fields(
                value
            )
        )

    if (
        hasattr(
            value,
            "__dict__",
        )
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
                type,
            ),
        )
    ):
        try:
            return tuple(
                (
                    str(key),
                    item,
                )
                for key, item
                in vars(
                    value
                ).items()
                if not str(
                    key
                ).startswith(
                    "_"
                )
            )
        except Exception:
            return ()

    return ()


def _json_value(
    value: Any,
) -> Any:

    if not isinstance(
        value,
        str,
    ):
        return None

    candidate = value.strip()

    if not candidate:
        return None

    if not (
        candidate.startswith(
            "{"
        )
        or candidate.startswith(
            "["
        )
    ):
        return None

    try:
        return json.loads(
            candidate
        )
    except Exception:
        return None


def _scalar_text(
    value: Any,
) -> str | None:

    if value is None:
        return None

    if isinstance(
        value,
        Enum,
    ):
        value = value.value

    if isinstance(
        value,
        bool,
    ):
        return (
            "true"
            if value
            else "false"
        )

    if isinstance(
        value,
        (
            str,
            int,
            float,
        ),
    ):
        result = str(
            value
        ).strip()

        return (
            result
            if result
            else None
        )

    return None


def _matched_keys(
    value: Any,
    known_keys: set[str],
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> set[str]:

    if depth > 3:
        return set()

    scalar = _scalar_text(
        value
    )

    if scalar is not None:

        if scalar in known_keys:
            return {
                scalar
            }

        parsed = _json_value(
            scalar
        )

        if parsed is not None:
            return _matched_keys(
                parsed,
                known_keys,
                depth=depth + 1,
                seen=seen,
            )

        return set()

    if seen is None:
        seen = set()

    identity = id(
        value
    )

    if identity in seen:
        return set()

    seen.add(
        identity
    )

    matches: set[str] = set()

    if isinstance(
        value,
        (
            tuple,
            list,
            set,
            frozenset,
        ),
    ):

        for item in value:
            matches.update(
                _matched_keys(
                    item,
                    known_keys,
                    depth=depth + 1,
                    seen=seen,
                )
            )

        return matches

    for _name, item in _object_items(
        value
    ):
        matches.update(
            _matched_keys(
                item,
                known_keys,
                depth=depth + 1,
                seen=seen,
            )
        )

    return matches


def _flatten_scalars(
    value: Any,
    *,
    prefix: str = "",
    depth: int = 0,
    seen: set[int] | None = None,
) -> tuple[tuple[str, str], ...]:

    if depth > 3:
        return ()

    scalar = _scalar_text(
        value
    )

    if scalar is not None:

        parsed = _json_value(
            scalar
        )

        if parsed is not None:
            return _flatten_scalars(
                parsed,
                prefix=prefix,
                depth=depth + 1,
                seen=seen,
            )

        return (
            (
                prefix,
                scalar,
            ),
        )

    if seen is None:
        seen = set()

    identity = id(
        value
    )

    if identity in seen:
        return ()

    seen.add(
        identity
    )

    output: list[
        tuple[
            str,
            str,
        ]
    ] = []

    if isinstance(
        value,
        (
            tuple,
            list,
            set,
            frozenset,
        ),
    ):

        for index, item in enumerate(
            value
        ):
            child_prefix = (
                f"{prefix}[{index}]"
                if prefix
                else f"[{index}]"
            )

            output.extend(
                _flatten_scalars(
                    item,
                    prefix=child_prefix,
                    depth=depth + 1,
                    seen=seen,
                )
            )

        return tuple(
            output
        )

    for name, item in _object_items(
        value
    ):

        child_prefix = (
            f"{prefix}.{name}"
            if prefix
            else name
        )

        output.extend(
            _flatten_scalars(
                item,
                prefix=child_prefix,
                depth=depth + 1,
                seen=seen,
            )
        )

    return tuple(
        output
    )


def _source_score(
    path: str,
) -> int:

    name = path.lower()

    if (
        "filename" in name
        or "file_name" in name
    ):
        return 120

    if "document_name" in name:
        return 115

    if "source_name" in name:
        return 110

    if "document_title" in name:
        return 105

    if (
        name.endswith(
            ".title"
        )
        or name == "title"
    ):
        return 95

    if "document_id" in name:
        return 40

    if "source_document_id" in name:
        return 35

    if "source_id" in name:
        return 25

    return 0


def _page_score(
    path: str,
) -> int:

    name = path.lower()

    if "page_number" in name:
        return 120

    if "page_index" in name:
        return 100

    if (
        name.endswith(
            ".page"
        )
        or name == "page"
    ):
        return 90

    return 0


def _text_score(
    path: str,
) -> int:

    name = path.lower()

    if any(
        token in name
        for token in (
            "sha256",
            "hash",
            "schema",
            "version",
            "identity",
        )
    ):
        return 0

    if "excerpt" in name:
        return 140

    if "quotation" in name:
        return 135

    if "quote" in name:
        return 130

    if "chunk_text" in name:
        return 125

    if "source_text" in name:
        return 120

    if "document_text" in name:
        return 115

    if (
        name.endswith(
            ".text"
        )
        or name == "text"
    ):
        return 105

    if "statement" in name:
        return 100

    if "content" in name:
        return 90

    if "proposition" in name:
        return 80

    if "description" in name:
        return 65

    if "rationale" in name:
        return 55

    return 0


def _clean_source(
    value: str,
) -> str:

    text = (
        value
        .replace(
            "\\",
            "/",
        )
        .strip()
    )

    if "/" in text:
        text = text.rsplit(
            "/",
            1,
        )[-1]

    if len(text) > 80:
        text = (
            text[:77]
            + "..."
        )

    return text


def _clean_excerpt(
    value: str,
) -> str:

    text = " ".join(
        value.split()
    )

    if len(text) > 120:
        text = (
            text[:117]
            + "..."
        )

    return text


def _clean_page(
    value: str,
) -> str:

    text = " ".join(
        value.split()
    )

    if not text:
        return ""

    lower = text.lower()

    if lower.startswith(
        "page"
    ):
        return text

    return (
        "p."
        + text
    )


def _update_display_candidate(
    index: dict[
        str,
        dict[
            str,
            tuple[
                int,
                str,
            ],
        ],
    ],
    *,
    evidence_key: str,
    kind: str,
    score: int,
    value: str,
) -> None:

    if score <= 0:
        return

    if not value:
        return

    if value == evidence_key:
        return

    current = (
        index
        .setdefault(
            evidence_key,
            {},
        )
        .get(
            kind
        )
    )

    if (
        current is None
        or score > current[0]
    ):
        index[
            evidence_key
        ][
            kind
        ] = (
            score,
            value,
        )


def _inspect_context_node(
    value: Any,
    known_keys: set[str],
    index: dict[
        str,
        dict[
            str,
            tuple[
                int,
                str,
            ],
        ],
    ],
) -> None:

    matches = _matched_keys(
        value,
        known_keys,
    )

    if not matches:
        return

    scalars = _flatten_scalars(
        value
    )

    if not scalars:
        return

    for evidence_key in matches:

        for path, scalar in scalars:

            if scalar in known_keys:
                continue

            source_score = (
                _source_score(
                    path
                )
            )

            if source_score:
                _update_display_candidate(
                    index,
                    evidence_key=
                        evidence_key,
                    kind=
                        "source",
                    score=
                        source_score,
                    value=
                        _clean_source(
                            scalar
                        ),
                )

            page_score = (
                _page_score(
                    path
                )
            )

            if page_score:
                _update_display_candidate(
                    index,
                    evidence_key=
                        evidence_key,
                    kind=
                        "page",
                    score=
                        page_score,
                    value=
                        _clean_page(
                            scalar
                        ),
                )

            text_score = (
                _text_score(
                    path
                )
            )

            if text_score:
                _update_display_candidate(
                    index,
                    evidence_key=
                        evidence_key,
                    kind=
                        "excerpt",
                    score=
                        text_score,
                    value=
                        _clean_excerpt(
                            scalar
                        ),
                )


def _walk_context_nodes(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
):

    if depth > 9:
        return

    scalar = _scalar_text(
        value
    )

    if scalar is not None:

        parsed = _json_value(
            scalar
        )

        if parsed is not None:
            yield from _walk_context_nodes(
                parsed,
                depth=depth + 1,
                seen=seen,
            )

        return

    if seen is None:
        seen = set()

    identity = id(
        value
    )

    if identity in seen:
        return

    seen.add(
        identity
    )

    items = _object_items(
        value
    )

    if items:
        yield value

        for _name, child in items:
            yield from _walk_context_nodes(
                child,
                depth=depth + 1,
                seen=seen,
            )

        return

    if isinstance(
        value,
        (
            tuple,
            list,
            set,
            frozenset,
        ),
    ):
        for child in value:
            yield from _walk_context_nodes(
                child,
                depth=depth + 1,
                seen=seen,
            )


def _all_ledger_evidence_keys(
    authority,
) -> set[str]:

    keys: set[str] = set()

    matrices = getattr(
        authority,
        "case_matrices",
        None,
    )

    if matrices is None:
        return keys

    for issue in getattr(
        matrices,
        "issue_matrix",
        (),
    ):

        for element in getattr(
            issue,
            "element_records",
            (),
        ):

            for _role, field_name in _ROLE_FIELDS:

                for evidence_key in getattr(
                    element,
                    field_name,
                    (),
                ):
                    if isinstance(
                        evidence_key,
                        str,
                    ):
                        keys.add(
                            evidence_key
                        )

    return keys


def _build_evidence_display_index(
    authority,
    known_keys: set[str],
) -> dict[
    str,
    dict[
        str,
        str,
    ],
]:

    if not known_keys:
        return {}

    raw_index: dict[
        str,
        dict[
            str,
            tuple[
                int,
                str,
            ],
        ],
    ] = {}

    roots = (
        getattr(
            authority,
            "governed_issue_evidence_map",
            None,
        ),
        getattr(
            authority,
            "governed_evidential_analysis",
            None,
        ),
        getattr(
            authority,
            "structured_legal_analysis_results",
            None,
        ),
        getattr(
            authority,
            "case_matrices",
            None,
        ),
    )

    for root in roots:

        if root is None:
            continue

        try:
            for node in _walk_context_nodes(
                root
            ):
                _inspect_context_node(
                    node,
                    known_keys,
                    raw_index,
                )

        except Exception:
            # Presentation enrichment is deliberately
            # fail-soft. It must never prevent governed
            # analytical state from rendering.
            continue

    result: dict[
        str,
        dict[
            str,
            str,
        ],
    ] = {}

    for evidence_key, values in (
        raw_index.items()
    ):

        result[
            evidence_key
        ] = {
            kind:
                scored_value[1]

            for kind, scored_value
            in values.items()
        }

    return result


def _role_index(
    element,
) -> dict[
    str,
    tuple[
        str,
        ...,
    ],
]:

    roles: dict[
        str,
        list[
            str
        ],
    ] = {}

    for role, field_name in _ROLE_FIELDS:

        for evidence_key in getattr(
            element,
            field_name,
            (),
        ):

            bucket = roles.setdefault(
                evidence_key,
                [],
            )

            if role not in bucket:
                bucket.append(
                    role
                )

    return {
        evidence_key:
            tuple(
                values
            )

        for evidence_key, values
        in roles.items()
    }


def _short_evidence_key(
    evidence_key: str,
) -> str:

    if "__" in evidence_key:

        suffix = (
            evidence_key
            .rsplit(
                "__",
                1,
            )[-1]
            .strip()
        )

        if suffix:
            suffix = (
                suffix[:36]
                + "..."
                if len(suffix) > 39
                else suffix
            )

            return (
                evidence_key[:8]
                + "..."
                + " "
                + suffix
            )

    if len(evidence_key) <= 28:
        return evidence_key

    return (
        evidence_key[:12]
        + "..."
        + evidence_key[-8:]
    )


def _format_evidence_option(
    evidence_key: str,
    display_index: dict[
        str,
        dict[
            str,
            str,
        ],
    ],
    role_index: dict[
        str,
        tuple[
            str,
            ...,
        ],
    ],
) -> str:

    metadata = display_index.get(
        evidence_key,
        {},
    )

    roles = role_index.get(
        evidence_key,
        (),
    )

    parts: list[str] = []

    if roles:
        parts.append(
            "+".join(
                roles
            )
        )

    source = metadata.get(
        "source"
    )

    page = metadata.get(
        "page"
    )

    excerpt = metadata.get(
        "excerpt"
    )

    if source and page:
        parts.append(
            source
            + " "
            + page
        )

    elif source:
        parts.append(
            source
        )

    elif page:
        parts.append(
            page
        )

    if excerpt:
        parts.append(
            '"'
            + excerpt
            + '"'
        )

    parts.append(
        _short_evidence_key(
            evidence_key
        )
    )

    return " | ".join(
        parts
    )


def _show_selected_evidence(
    label: str,
    evidence_key: str,
    display_index: dict[
        str,
        dict[
            str,
            str,
        ],
    ],
    role_index: dict[
        str,
        tuple[
            str,
            ...,
        ],
    ],
) -> None:

    metadata = display_index.get(
        evidence_key,
        {},
    )

    roles = role_index.get(
        evidence_key,
        (),
    )

    st.caption(
        f"{label} exact key: {evidence_key}"
    )

    detail_parts: list[str] = []

    if roles:
        detail_parts.append(
            "Role: "
            + ", ".join(
                roles
            )
        )

    source = metadata.get(
        "source"
    )

    page = metadata.get(
        "page"
    )

    excerpt = metadata.get(
        "excerpt"
    )

    if source:
        detail_parts.append(
            "Source: "
            + source
        )

    if page:
        detail_parts.append(
            "Location: "
            + page
        )

    if excerpt:
        detail_parts.append(
            'Text: "'
            + excerpt
            + '"'
        )

    if detail_parts:
        st.caption(
            " | ".join(
                detail_parts
            )
        )


def _evidence_list(
    label: str,
    values: tuple[str, ...],
) -> None:

    st.markdown(
        f"**{label} - {len(values)}**"
    )

    if values:
        st.code(
            "\n".join(
                values
            ),
            language=None,
        )

    else:
        st.caption(
            "None recorded in the "
            "governed analytical matrix."
        )


def show_matter_analysis_ledger(
    active_case_id: str | None,
) -> None:

    if active_case_id is None:
        return

    try:
        authority = (
            load_active_governed_analytical_authority(
                active_case_id
            )
        )

    except Exception as exc:

        st.error(
            "Matter Analysis Ledger could not "
            "load the governed analytical authority."
        )

        st.caption(
            str(exc)
        )

        return

    if authority is None:
        return

    evidence_display_index = (
        _build_evidence_display_index(
            authority,
            _all_ledger_evidence_keys(
                authority
            ),
        )
    )

    try:
        events = (
            load_relationship_events(
                case_id=
                    active_case_id,

                authority_id=
                    authority.manifest.authority_id,
            )
        )

        ledger = (
            build_matter_analysis_ledger(
                authority=
                    authority,

                events=
                    events,
            )
        )

    except MatterAnalysisLedgerError as exc:

        st.error(
            "Matter Analysis Ledger failed closed."
        )

        st.caption(
            str(exc)
        )

        return

    st.divider()

    st.header(
        "Matter Analysis Ledger"
    )

    st.caption(
        "Relationship review is bound to analytical authority "
        f"{ledger.authority_id}. "
        "A relationship begins as PROPOSED and becomes "
        "APPROVED or REJECTED only through an explicit reviewer action. "
        "The underlying source evidence and governed analytical authority "
        "are not silently overwritten."
    )

    for issue in ledger.issues:

        with st.expander(
            issue.issue_name,
            expanded=False,
        ):

            st.caption(
                "Issue analysis: "
                + issue.issue_analysis_id
            )

            if issue.issue_summary:
                st.write(
                    issue.issue_summary
                )

            for element in issue.elements:

                st.markdown(
                    "---"
                )

                st.subheader(
                    element.element_name
                )

                st.caption(
                    element.legal_question
                )

                c1, c2, c3, c4, c5 = (
                    st.columns(
                        5
                    )
                )

                c1.metric(
                    "Supporting",
                    len(
                        element.supporting_evidence_keys
                    ),
                )

                c2.metric(
                    "Adverse",
                    len(
                        element.adverse_evidence_keys
                    ),
                )

                c3.metric(
                    "Corroborative",
                    len(
                        element.corroborative_evidence_keys
                    ),
                )

                c4.metric(
                    "Conflicting",
                    len(
                        element.conflicting_evidence_keys
                    ),
                )

                c5.metric(
                    "Gaps",
                    len(
                        element.evidential_gap_ids
                    ),
                )

                st.write(
                    "**Current analytical status:** "
                    + element.analytical_status
                )

                st.caption(
                    "Confidence: "
                    + element.analytical_confidence
                )

                # ----------------------------------------------------------
                # WHY?
                # ----------------------------------------------------------

                with st.expander(
                    "WHY?",
                    expanded=False,
                ):

                    if element.provisional_analysis:

                        st.write(
                            "**Current analytical explanation**"
                        )

                        st.write(
                            element.provisional_analysis
                        )

                    _evidence_list(
                        "Supporting evidence",
                        element.supporting_evidence_keys,
                    )

                    _evidence_list(
                        "Adverse evidence",
                        element.adverse_evidence_keys,
                    )

                    _evidence_list(
                        "Corroborative evidence",
                        element.corroborative_evidence_keys,
                    )

                    _evidence_list(
                        "Conflicting evidence",
                        element.conflicting_evidence_keys,
                    )

                    _evidence_list(
                        "Neutral/contextual evidence",
                        element.neutral_evidence_keys,
                    )

                    st.markdown(
                        "**Unresolved matters - "
                        f"{len(element.unresolved_matters)}**"
                    )

                    if element.unresolved_matters:

                        for value in (
                            element.unresolved_matters
                        ):
                            st.write(
                                "? "
                                + value
                            )

                    else:
                        st.caption(
                            "None recorded."
                        )

                    st.markdown(
                        "**Evidential gaps - "
                        f"{len(element.evidential_gap_ids)}**"
                    )

                    if element.evidential_gap_ids:

                        for value in (
                            element.evidential_gap_ids
                        ):
                            st.code(
                                value,
                                language=None,
                            )

                    else:
                        st.caption(
                            "None recorded."
                        )

                # ----------------------------------------------------------
                # CURRENT RELATIONSHIP REVIEWS
                # ----------------------------------------------------------

                role_index = (
                    _role_index(
                        element
                    )
                )

                evidence_options = tuple(
                    sorted(
                        set(
                            element.supporting_evidence_keys
                            + element.adverse_evidence_keys
                            + element.corroborative_evidence_keys
                            + element.conflicting_evidence_keys
                            + element.neutral_evidence_keys
                        )
                    )
                )

                st.markdown(
                    "#### Relationship review"
                )

                relationships = (
                    element.relationships
                )

                if relationships:

                    for relationship in relationships:

                        with st.container(
                            border=True
                        ):

                            st.write(
                                "**"
                                + relationship.relationship_type.value
                                + "** - "
                                + relationship.state.value
                            )

                            st.code(
                                relationship.left_evidence_key
                                + "\n<->\n"
                                + relationship.right_evidence_key,
                                language=None,
                            )

                            st.write(
                                relationship.proposal_rationale
                            )

                            st.caption(
                                "Proposed/reviewed by: "
                                + relationship.actor
                            )

                            st.caption(
                                "Event time: "
                                + relationship.created_at
                            )

                            if relationship.review_note:

                                st.caption(
                                    "Review note: "
                                    + relationship.review_note
                                )

                            if (
                                relationship.state
                                is RelationshipReviewState.PROPOSED
                            ):

                                review_note = (
                                    st.text_area(
                                        "Optional review note",
                                        key=(
                                            "mal_review_note_"
                                            + relationship.relationship_id
                                        ),
                                        height=90,
                                    )
                                )

                                approve, reject = (
                                    st.columns(
                                        2
                                    )
                                )

                                if approve.button(
                                    "Approve",
                                    key=(
                                        "mal_approve_"
                                        + relationship.relationship_id
                                    ),
                                ):

                                    try:
                                        review_relationship(
                                            case_id=
                                                ledger.case_id,

                                            authority_id=
                                                ledger.authority_id,

                                            relationship_id=
                                                relationship.relationship_id,

                                            decision=
                                                RelationshipReviewState.APPROVED,

                                            review_note=
                                                review_note,
                                        )

                                    except MatterAnalysisLedgerError as exc:

                                        st.error(
                                            str(exc)
                                        )

                                    else:
                                        st.rerun()

                                if reject.button(
                                    "Reject",
                                    key=(
                                        "mal_reject_"
                                        + relationship.relationship_id
                                    ),
                                ):

                                    try:
                                        review_relationship(
                                            case_id=
                                                ledger.case_id,

                                            authority_id=
                                                ledger.authority_id,

                                            relationship_id=
                                                relationship.relationship_id,

                                            decision=
                                                RelationshipReviewState.REJECTED,

                                            review_note=
                                                review_note,
                                        )

                                    except MatterAnalysisLedgerError as exc:

                                        st.error(
                                            str(exc)
                                        )

                                    else:
                                        st.rerun()

                else:

                    st.caption(
                        "No relationship review "
                        "has been recorded for this element."
                    )

                # ----------------------------------------------------------
                # NEW PROPOSAL
                # ----------------------------------------------------------

                if len(evidence_options) >= 2:

                    form_key = (
                        "mal_proposal_"
                        + issue.issue_analysis_id
                        + "_"
                        + element.element_id
                    )

                    with st.form(
                        form_key
                    ):

                        st.markdown(
                            "**Propose a contradiction "
                            "or corroboration**"
                        )

                        relationship_type = (
                            st.selectbox(
                                "Relationship",
                                options=(
                                    RelationshipType.CONTRADICTS.value,
                                    RelationshipType.CORROBORATES.value,
                                ),
                            )
                        )

                        left = (
                            st.selectbox(
                                "Evidence item A",
                                evidence_options,
                                format_func=lambda evidence_key: (
                                    _format_evidence_option(
                                        evidence_key,
                                        evidence_display_index,
                                        role_index,
                                    )
                                ),
                            )
                        )

                        _show_selected_evidence(
                            "Evidence item A",
                            left,
                            evidence_display_index,
                            role_index,
                        )

                        right = (
                            st.selectbox(
                                "Evidence item B",
                                evidence_options,
                                index=1,
                                format_func=lambda evidence_key: (
                                    _format_evidence_option(
                                        evidence_key,
                                        evidence_display_index,
                                        role_index,
                                    )
                                ),
                            )
                        )

                        _show_selected_evidence(
                            "Evidence item B",
                            right,
                            evidence_display_index,
                            role_index,
                        )

                        rationale = (
                            st.text_area(
                                "Why are these evidence items related?",
                                height=120,
                            )
                        )

                        submitted = (
                            st.form_submit_button(
                                "Propose relationship"
                            )
                        )

                    if submitted:

                        if left == right:

                            st.warning(
                                "Choose two different "
                                "evidence items."
                            )

                        else:

                            try:
                                propose_relationship(
                                    case_id=
                                        ledger.case_id,

                                    authority_id=
                                        ledger.authority_id,

                                    issue_analysis_id=
                                        issue.issue_analysis_id,

                                    element_id=
                                        element.element_id,

                                    relationship_type=
                                        RelationshipType(
                                            relationship_type
                                        ),

                                    left_evidence_key=
                                        left,

                                    right_evidence_key=
                                        right,

                                    rationale=
                                        rationale,
                                )

                            except MatterAnalysisLedgerError as exc:

                                st.error(
                                    str(exc)
                                )

                            else:
                                st.rerun()

                else:

                    st.caption(
                        "At least two governed evidence items "
                        "are required before a relationship "
                        "can be proposed."
                    )


__all__ = [
    "show_matter_analysis_ledger",
]
