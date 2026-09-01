from __future__ import annotations

from hashlib import sha256
from typing import Any

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

from analytical_change_proposals import (
    AnalyticalChangeProposalError,
    AnalyticalChangeProposalState,
    load_change_proposal_events,
    project_change_proposals,
    propose_analytical_change,
    review_analytical_change,
)

from work_product_authority_checker import (
    WorkProductAuthorityCheckerError,
    WorkProductAuthorityResult,
    check_work_product_authority,
)



MAL1_REVIEW_CLARITY_VERSION = "matter-analysis-ledger-review-clarity/1.0"
MAL1_ROLE_AWARE_SELECTOR_VERSION = "matter-analysis-ledger-role-aware-selector/1.0"
MAL1_FOCUSED_WORKSPACE_VERSION = "matter-analysis-ledger-focused-workspace/1.0"
MAL1_COMPACT_HISTORY_VERSION = "matter-analysis-ledger-compact-history/1.0"
MAL1_FINDINGS_GAPS_UNCERTAINTY_VERSION = "matter-analysis-ledger-findings-gaps-uncertainty/1.0"
MAL1_ANALYTICAL_CHANGE_PROPOSAL_VERSION = "matter-analysis-ledger-analytical-change-proposal/1.0"
MAL1_CHALLENGE_FINDING_VERSION = "matter-analysis-ledger-challenge-finding/1.0"
MAL1_WORK_PRODUCT_AUTHORITY_CHECKER_VERSION = "matter-analysis-ledger-work-product-authority-checker/1.0"

EVIDENCE_SELECTOR_PRESENTATION_VERSION = (
    "matter-analysis-ledger-evidence-selector/1.1"
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


def _binding_evidence(
    binding: Any,
) -> Any | None:

    evidence = getattr(
        binding,
        "evidence",
        None,
    )

    if evidence is not None:
        return evidence

    # Test/dependency-injection compatibility:
    # an evidence reference itself may be supplied.
    if isinstance(
        getattr(
            binding,
            "evidence_key",
            None,
        ),
        str,
    ):
        return binding

    return None


def _evidence_signature(
    evidence: Any,
) -> tuple[Any, ...]:

    return (
        getattr(
            evidence,
            "evidence_key",
            None,
        ),
        getattr(
            evidence,
            "source_document_instance_id",
            None,
        ),
        getattr(
            evidence,
            "source_snapshot_id",
            None,
        ),
        getattr(
            evidence,
            "original_filename",
            None,
        ),
        getattr(
            evidence,
            "page_number",
            None,
        ),
        getattr(
            evidence,
            "chunk_ordinal",
            None,
        ),
        getattr(
            evidence,
            "chunk_id",
            None,
        ),
        getattr(
            evidence,
            "evidence_binding_id",
            None,
        ),
        getattr(
            evidence,
            "chunk_text_sha256",
            None,
        ),
        getattr(
            evidence,
            "chunk_text_byte_length",
            None,
        ),
        getattr(
            evidence,
            "citation",
            None,
        ),
        getattr(
            evidence,
            "source_type",
            None,
        ),
        getattr(
            evidence,
            "source_label",
            None,
        ),
        getattr(
            evidence,
            "primary_tier",
            None,
        ),
        getattr(
            evidence,
            "primary_label",
            None,
        ),
    )


def _exact_evidence_refs(
    authority,
    known_keys: set[str],
) -> dict[
    str,
    Any,
]:

    governed_map = getattr(
        authority,
        "governed_issue_evidence_map",
        None,
    )

    if governed_map is None:
        return {}

    refs: dict[
        str,
        Any,
    ] = {}

    signatures: dict[
        str,
        tuple[
            Any,
            ...,
        ],
    ] = {}

    ambiguous: set[str] = set()

    for binding in getattr(
        governed_map,
        "bindings",
        (),
    ):

        evidence = _binding_evidence(
            binding
        )

        if evidence is None:
            continue

        evidence_key = getattr(
            evidence,
            "evidence_key",
            None,
        )

        if (
            not isinstance(
                evidence_key,
                str,
            )
            or evidence_key
            not in known_keys
        ):
            continue

        signature = (
            _evidence_signature(
                evidence
            )
        )

        existing = signatures.get(
            evidence_key
        )

        if existing is None:

            signatures[
                evidence_key
            ] = signature

            refs[
                evidence_key
            ] = evidence

            continue

        if existing != signature:

            ambiguous.add(
                evidence_key
            )


    # Fail closed for any evidence key whose supposedly
    # immutable local reference disagrees across bindings.
    for evidence_key in ambiguous:

        refs.pop(
            evidence_key,
            None,
        )

    return refs


def _clean_source(
    value: str,
) -> str:

    result = (
        value
        .replace(
            "\\",
            "/",
        )
        .strip()
    )

    if "/" in result:
        result = result.rsplit(
            "/",
            1,
        )[-1]

    if len(result) > 90:
        result = (
            result[:87]
            + "..."
        )

    return result


def _clean_excerpt(
    value: str,
) -> str:

    result = " ".join(
        value.split()
    )

    if len(result) > 150:
        result = (
            result[:147]
            + "..."
        )

    return result


def _page_label(
    value: Any,
) -> str | None:

    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    if text.lower().startswith(
        "p."
    ):
        return text

    return (
        "p."
        + text
    )


def _verified_chunk_text(
    evidence: Any,
    *,
    store: Any | None,
) -> str | None:

    # Synthetic/test references may carry the exact text
    # directly. Production GovernedEvidenceRef does not.
    direct_text = getattr(
        evidence,
        "chunk_text",
        None,
    )

    if isinstance(
        direct_text,
        str,
    ) and direct_text.strip():

        return direct_text


    digest_value = getattr(
        evidence,
        "chunk_text_sha256",
        None,
    )

    expected_length = getattr(
        evidence,
        "chunk_text_byte_length",
        None,
    )

    if (
        not isinstance(
            digest_value,
            str,
        )
        or not digest_value.strip()
        or not isinstance(
            expected_length,
            int,
        )
        or expected_length < 0
        or store is None
    ):
        return None

    digest = digest_value.strip()

    if digest.startswith(
        "sha256:"
    ):
        digest = digest[
            len(
                "sha256:"
            ):
        ]

    if len(digest) != 64:
        return None

    try:

        raw = store.read_blob(
            digest
        )

    except Exception:
        return None

    if not isinstance(
        raw,
        bytes,
    ):
        return None

    if len(raw) != expected_length:
        return None

    if sha256(
        raw
    ).hexdigest() != digest.lower():
        return None

    try:

        return raw.decode(
            "utf-8",
            errors="strict",
        )

    except UnicodeDecodeError:
        return None


def _build_evidence_display_index(
    authority,
    known_keys: set[str],
    *,
    store: Any | None = None,
) -> dict[
    str,
    dict[
        str,
        str,
    ],
]:

    refs = _exact_evidence_refs(
        authority,
        known_keys,
    )

    if not refs:
        return {}


    source_store = store
    source_store_attempted = (
        store is not None
    )

    result: dict[
        str,
        dict[
            str,
            str,
        ],
    ] = {}


    for evidence_key, evidence in refs.items():

        metadata: dict[
            str,
            str,
        ] = {}


        source = getattr(
            evidence,
            "original_filename",
            None,
        )

        if not isinstance(
            source,
            str,
        ):
            source = getattr(
                evidence,
                "source_filename",
                None,
            )

        if isinstance(
            source,
            str,
        ) and source.strip():

            metadata[
                "source"
            ] = _clean_source(
                source
            )


        page = _page_label(
            getattr(
                evidence,
                "page_number",
                None,
            )
        )

        if page is not None:

            metadata[
                "page"
            ] = page


        citation = getattr(
            evidence,
            "citation",
            None,
        )

        if isinstance(
            citation,
            str,
        ) and citation.strip():

            metadata[
                "citation"
            ] = citation.strip()


        source_label = getattr(
            evidence,
            "source_label",
            None,
        )

        if isinstance(
            source_label,
            str,
        ) and source_label.strip():

            metadata[
                "source_label"
            ] = source_label.strip()


        primary_label = getattr(
            evidence,
            "primary_label",
            None,
        )

        if isinstance(
            primary_label,
            str,
        ) and primary_label.strip():

            metadata[
                "primary_label"
            ] = primary_label.strip()


        direct_text = getattr(
            evidence,
            "chunk_text",
            None,
        )

        needs_store = not (
            isinstance(
                direct_text,
                str,
            )
            and direct_text.strip()
        )


        if (
            needs_store
            and not source_store_attempted
        ):

            source_store_attempted = True

            try:

                from source_evidence.store import (
                    SourceEvidenceStore,
                )

                source_store = (
                    SourceEvidenceStore()
                )

            except Exception:

                source_store = None


        exact_text = _verified_chunk_text(
            evidence,
            store=source_store,
        )

        if exact_text is not None:

            excerpt = _clean_excerpt(
                exact_text
            )

            if excerpt:

                metadata[
                    "excerpt"
                ] = excerpt


        result[
            evidence_key
        ] = metadata


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
                suffix[:42]
                + "..."
                if len(suffix) > 45
                else suffix
            )

            return (
                evidence_key[:8]
                + "..."
                + " "
                + suffix
            )


    if len(evidence_key) <= 32:
        return evidence_key


    return (
        evidence_key[:14]
        + "..."
        + evidence_key[-10:]
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


    source_label = metadata.get(
        "source_label"
    )

    if source_label:

        parts.append(
            source_label
        )


    excerpt = metadata.get(
        "excerpt"
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


    details: list[str] = []


    if roles:

        details.append(
            "Role: "
            + ", ".join(
                roles
            )
        )


    citation = metadata.get(
        "citation"
    )

    if citation:

        details.append(
            "Citation: "
            + citation
        )

    else:

        source = metadata.get(
            "source"
        )

        page = metadata.get(
            "page"
        )

        if source:

            details.append(
                "Source: "
                + source
            )

        if page:

            details.append(
                "Location: "
                + page
            )


    source_label = metadata.get(
        "source_label"
    )

    if source_label:

        details.append(
            "Source class: "
            + source_label
        )


    primary_label = metadata.get(
        "primary_label"
    )

    if primary_label:

        details.append(
            "Provenance tier: "
            + primary_label
        )


    if details:

        st.caption(
            " | ".join(
                details
            )
        )


    excerpt = metadata.get(
        "excerpt"
    )

    if excerpt:

        st.caption(
            'Verified evidence text: "'
            + excerpt
            + '"'
        )


def _evidence_list(
    label,
    values,
):
    items = tuple(
        values
    )

    if not items:

        st.caption(
            f"{label}: none recorded."
        )

        return

    with st.expander(
        f"{label} - {len(items)} technical evidence keys",
        expanded=False,
    ):

        st.caption(
            "Technical evidence identifiers only. "
            "Use the relationship review evidence display "
            "for document, page, provenance and verified text."
        )

        st.code(
            "\n".join(
                str(item)
                for item in items
            ),
            language=None,
        )





def _show_terminal_relationship_summary(
    relationship: Any,
    evidence_display_index: Any,
    role_index: Any,
) -> None:
    """Render an approved/rejected relationship compactly."""

    state = relationship.state.value

    relationship_name = {
        RelationshipType.CONTRADICTS.value:
            "CONTRADICTION",
        RelationshipType.CORROBORATES.value:
            "CORROBORATION",
    }.get(
        relationship.relationship_type.value,
        relationship.relationship_type.value,
    )

    st.write(
        "**"
        + state
        + " "
        + relationship_name
        + "**"
    )

    left_label = _format_evidence_option(
        relationship.left_evidence_key,
        evidence_display_index,
        role_index,
    )

    right_label = _format_evidence_option(
        relationship.right_evidence_key,
        evidence_display_index,
        role_index,
    )

    st.caption("Evidence A")
    st.write(left_label)

    st.caption("Evidence B")
    st.write(right_label)

    if (
        relationship.state
        is RelationshipReviewState.REJECTED
        and relationship.review_note
    ):
        st.write(
            "**Reason rejected**"
        )
        st.write(
            relationship.review_note
        )

    elif relationship.review_note:
        st.write(
            "**Review note**"
        )
        st.write(
            relationship.review_note
        )

    if relationship.created_at:
        st.caption(
            "Reviewed: "
            + relationship.created_at[:10]
        )

    with st.expander(
        "View evidence details",
        expanded=False,
    ):
        _show_selected_evidence(
            "Evidence A",
            relationship.left_evidence_key,
            evidence_display_index,
            role_index,
        )

        _show_selected_evidence(
            "Evidence B",
            relationship.right_evidence_key,
            evidence_display_index,
            role_index,
        )

    with st.expander(
        "View relationship record",
        expanded=False,
    ):
        st.write(
            "**Original proposal rationale**"
        )
        st.write(
            relationship.proposal_rationale
        )

        st.caption(
            "Recorded actor: "
            + relationship.actor
        )

        st.caption(
            "Recorded event time: "
            + relationship.created_at
        )

        st.code(
            relationship.left_evidence_key
            + "\n<->\n"
            + relationship.right_evidence_key,
            language=None,
        )




def _stable_selectbox(
    *,
    label,
    options,
    default_value,
    format_func,
    state_key,
):
    """Render a selectbox whose semantic value is the persisted widget state."""

    stable_options = tuple(options)
    if not stable_options:
        raise ValueError("options must not be empty.")
    if default_value not in stable_options:
        raise ValueError("default_value must be present in options.")

    current = st.session_state.get(state_key, default_value)
    if current not in stable_options:
        current = default_value

    st.session_state[state_key] = current

    selected = st.selectbox(
        label,
        stable_options,
        format_func=format_func,
        key=state_key,
    )

    if selected not in stable_options:
        raise ValueError("selectbox returned a value outside the supplied options.")

    return selected



def _matter_ledger_fragment(function):
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        return function
    return fragment(function)



def _matter_entry_form(*, key: str):
    form = getattr(st, "form", None)
    if form is None:
        from contextlib import nullcontext
        return nullcontext()
    return form(key=key, clear_on_submit=False)


def _matter_form_submit_button(label: str, **kwargs):
    submit = getattr(st, "form_submit_button", None)
    if submit is None:
        return st.button(label, **kwargs)
    return submit(label, **kwargs)



def _matter_relationship_proposal_editor(
    *,
    element: Any,
    proposal_key: str,
    evidence_display_index: dict[str, Any],
) -> tuple[bool, str, str | None, str | None, str]:
    # Staged forms preserve dependent choices without rerunning on each field.

    with _matter_entry_form(
        key=proposal_key + "_relationship_type_form",
    ):
        relationship_type = st.selectbox(
            "Relationship",
            options=(
                RelationshipType.CONTRADICTS.value,
                RelationshipType.CORROBORATES.value,
            ),
            key=proposal_key + "_relationship_type",
        )

        st.caption(
            "Choose the relationship type, then set it once before "
            "choosing governed evidence roles."
        )

        _matter_form_submit_button(
            "SET RELATIONSHIP TYPE",
            key=proposal_key + "_relationship_type_submit",
            use_container_width=True,
        )

    role_evidence_options = {
        "SUPPORTING": tuple(element.supporting_evidence_keys),
        "ADVERSE": tuple(element.adverse_evidence_keys),
        "CORROBORATIVE": tuple(element.corroborative_evidence_keys),
        "CONFLICTING": tuple(element.conflicting_evidence_keys),
        "NEUTRAL/CONTEXT": tuple(element.neutral_evidence_keys),
    }

    available_roles = tuple(
        role
        for role, keys in role_evidence_options.items()
        if keys
    )

    if not available_roles:
        st.warning(
            "No governed evidence roles are available for this element."
        )
        return False, relationship_type, None, None, ""

    preferred_left_role = (
        "SUPPORTING"
        if "SUPPORTING" in available_roles
        else available_roles[0]
    )

    if relationship_type == RelationshipType.CONTRADICTS.value:
        preferred_right_role = (
            "CONFLICTING"
            if "CONFLICTING" in available_roles
            else (
                "ADVERSE"
                if "ADVERSE" in available_roles
                else available_roles[0]
            )
        )

        st.caption(
            "For a contradiction, Evidence B defaults to CONFLICTING "
            "where governed conflicting evidence exists."
        )
    else:
        preferred_right_role = (
            "CORROBORATIVE"
            if "CORROBORATIVE" in available_roles
            else (
                "SUPPORTING"
                if "SUPPORTING" in available_roles
                else available_roles[0]
            )
        )

        st.caption(
            "For corroboration, Evidence B defaults to CORROBORATIVE "
            "where governed corroborative evidence exists."
        )

    with _matter_entry_form(
        key=(
            proposal_key
            + "_relationship_role_form_"
            + relationship_type
        ),
    ):
        left_role = st.selectbox(
            "Evidence A role",
            available_roles,
            index=available_roles.index(preferred_left_role),
            format_func=lambda role: (
                role
                + " ("
                + str(len(role_evidence_options[role]))
                + ")"
            ),
            key=(
                proposal_key
                + "_left_role_"
                + relationship_type
            ),
        )

        right_role = st.selectbox(
            "Evidence B role",
            available_roles,
            index=available_roles.index(preferred_right_role),
            format_func=lambda role: (
                role
                + " ("
                + str(len(role_evidence_options[role]))
                + ")"
            ),
            key=(
                proposal_key
                + "_right_role_"
                + relationship_type
            ),
        )

        st.caption(
            "Set the evidence roles once. The governed evidence-item "
            "choices below are then filtered to those committed roles."
        )

        _matter_form_submit_button(
            "SET EVIDENCE ROLES",
            key=(
                proposal_key
                + "_role_submit_"
                + relationship_type
            ),
            use_container_width=True,
        )

    left_options = role_evidence_options[left_role]
    right_options = role_evidence_options[right_role]

    if not left_options or not right_options:
        st.warning(
            "The selected governed evidence roles do not provide "
            "usable evidence choices."
        )
        return False, relationship_type, None, None, ""

    st.caption(
        "Evidence A is filtered to "
        + left_role
        + " ("
        + str(len(left_options))
        + ")."
    )

    st.caption(
        "Evidence B is filtered to "
        + right_role
        + " ("
        + str(len(right_options))
        + ")."
    )

    with _matter_entry_form(
        key=(
            proposal_key
            + "_relationship_evidence_form_"
            + relationship_type
            + "_"
            + left_role
            + "_"
            + right_role
        ),
    ):
        left = st.selectbox(
            "Evidence item A",
            left_options,
            format_func=lambda evidence_key: (
                _format_evidence_option(
                    evidence_key,
                    evidence_display_index,
                    {evidence_key: left_role},
                )
            ),
            key=(
                proposal_key
                + "_left_evidence_"
                + relationship_type
                + "_"
                + left_role
            ),
        )

        right = st.selectbox(
            "Evidence item B",
            right_options,
            format_func=lambda evidence_key: (
                _format_evidence_option(
                    evidence_key,
                    evidence_display_index,
                    {evidence_key: right_role},
                )
            ),
            key=(
                proposal_key
                + "_right_evidence_"
                + relationship_type
                + "_"
                + right_role
            ),
        )

        rationale = st.text_area(
            "Why are these evidence items related?",
            height=120,
            key=(
                proposal_key
                + "_rationale_"
                + relationship_type
                + "_"
                + left_role
                + "_"
                + right_role
            ),
        )

        submitted = _matter_form_submit_button(
            "PROPOSE RELATIONSHIP",
            key=proposal_key + "_submit",
            use_container_width=True,
        )

    _show_selected_evidence(
        "Evidence item A",
        left,
        evidence_display_index,
        {left: left_role},
    )

    _show_selected_evidence(
        "Evidence item B",
        right,
        evidence_display_index,
        {right: right_role},
    )

    return (
        submitted,
        relationship_type,
        left,
        right,
        rationale,
    )



def _suppress_streamlit_stale_visual_dimming() -> None:
    # Streamlit marks prior-run elements data-stale=true during a rerun.
    # Preserve rerun semantics but keep the visible workspace at full opacity.
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] [data-stale="true"],
        [data-testid="stAppViewContainer"] [data-stale="true"] * {
            opacity: 1 !important;
            transition: none !important;
            filter: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@_matter_ledger_fragment
def show_matter_analysis_ledger(
    active_case_id: str | None,
) -> None:

    _suppress_streamlit_stale_visual_dimming()

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
        "Issue Review & Decisions"
    )

    st.caption(
        "Technical system: Matter Analysis Ledger. "
        "Only one issue and one focus area are shown at a time."
    )

    st.caption(
        "Relationship review is bound to analytical authority "
        f"{ledger.authority_id}. "
        "A relationship begins as PROPOSED and becomes "
        "APPROVED or REJECTED only through an explicit reviewer action. "
        "The underlying source evidence and governed analytical authority "
        "are not silently overwritten."
    )

    if not ledger.issues:

        st.info(
            "No governed issues are available for review."
        )

        return

    default_issue_index = next(
        (
            index
            for index, candidate
            in enumerate(
                ledger.issues
            )
            if any(
                element.relationships
                for element
                in candidate.elements
            )
        ),
        0,
    )

    issue_by_id = {
        issue.issue_analysis_id: issue
        for issue in ledger.issues
    }
    issue_ids = tuple(
        issue.issue_analysis_id
        for issue in ledger.issues
    )
    default_issue_id = (
        ledger.issues[
            default_issue_index
        ].issue_analysis_id
    )

    selected_issue_id = _stable_selectbox(
        label="Issue to review",
        options=issue_ids,
        default_value=default_issue_id,
        format_func=lambda issue_id: (
            issue_by_id[
                issue_id
            ].issue_name
        ),
        state_key=(
            "mal_focused_issue_state_"
            + ledger.case_id
        ),
    )

    selected_issue = (
        issue_by_id[
            selected_issue_id
        ]
    )

    if not selected_issue.elements:

        st.info(
            "The selected issue contains no governed focus areas."
        )

        return

    default_element_index = next(
        (
            index
            for index, candidate
            in enumerate(
                selected_issue.elements
            )
            if candidate.relationships
        ),
        0,
    )

    element_by_id = {
        element.element_id: element
        for element in selected_issue.elements
    }
    element_ids = tuple(
        element.element_id
        for element in selected_issue.elements
    )
    default_element_id = (
        selected_issue.elements[
            default_element_index
        ].element_id
    )

    selected_element_id = _stable_selectbox(
        label="Focus area",
        options=element_ids,
        default_value=default_element_id,
        format_func=lambda element_id: (
            element_by_id[
                element_id
            ].element_name
        ),
        state_key=(
            "mal_focused_element_state_"
            + ledger.case_id
            + "_"
            + selected_issue.issue_analysis_id
        ),
    )

    selected_element = (
        element_by_id[
            selected_element_id
        ]
    )

    st.caption(
        "Showing one issue and one focus area only. "
        "Change either selector above to move elsewhere."
    )

    for issue in (
        selected_issue,
    ):

        with st.container(
            border=True
        ):

            st.subheader(
                issue.issue_name
            )

            st.caption(
                "Issue analysis: "
                + issue.issue_analysis_id
            )

            if issue.issue_summary:
                st.write(
                    issue.issue_summary
                )

            for element in (
                selected_element,
            ):

                st.markdown(
                    "---"
                )

                st.subheader(
                    element.element_name
                )

                st.caption(
                    element.legal_question
                )

                # ----------------------------------------------------------
                # FINDINGS / GAPS / UNCERTAINTY
                #
                # Presentation-only projection over the already-governed
                # analytical element and append-only MAL1 review history.
                # ----------------------------------------------------------

                approved_contradictions = tuple(
                    relationship
                    for relationship
                    in element.relationships
                    if (
                        relationship.state
                        is RelationshipReviewState.APPROVED
                        and relationship.relationship_type
                        is RelationshipType.CONTRADICTS
                    )
                )

                approved_corroborations = tuple(
                    relationship
                    for relationship
                    in element.relationships
                    if (
                        relationship.state
                        is RelationshipReviewState.APPROVED
                        and relationship.relationship_type
                        is RelationshipType.CORROBORATES
                    )
                )

                rejected_relationships = tuple(
                    relationship
                    for relationship
                    in element.relationships
                    if (
                        relationship.state
                        is RelationshipReviewState.REJECTED
                    )
                )

                pending_relationship_summaries = tuple(
                    relationship
                    for relationship
                    in element.relationships
                    if (
                        relationship.state
                        is RelationshipReviewState.PROPOSED
                    )
                )

                st.markdown(
                    "### Findings, gaps & uncertainty"
                )

                with st.container(
                    border=True
                ):

                    st.write(
                        "**Current position:** "
                        + element.analytical_status
                    )

                    st.caption(
                        "Confidence: "
                        + element.analytical_confidence
                    )

                    with st.expander(
                        "Current governed explanation",
                        expanded=False,
                    ):

                        if element.provisional_analysis:

                            st.write(
                                element.provisional_analysis
                            )

                        else:

                            st.caption(
                                "No provisional analytical "
                                "explanation is recorded."
                            )

                    left, right = (
                        st.columns(
                            2
                        )
                    )

                    left.metric(
                        "Supporting evidence",
                        len(
                            element.supporting_evidence_keys
                        ),
                    )

                    right.metric(
                        "Conflicting evidence",
                        len(
                            element.conflicting_evidence_keys
                        ),
                    )

                    left, right = (
                        st.columns(
                            2
                        )
                    )

                    left.metric(
                        "Adverse evidence",
                        len(
                            element.adverse_evidence_keys
                        ),
                    )

                    right.metric(
                        "Corroborative evidence",
                        len(
                            element.corroborative_evidence_keys
                        ),
                    )

                    left, right = (
                        st.columns(
                            2
                        )
                    )

                    left.metric(
                        "Formal gaps",
                        len(
                            element.evidential_gap_ids
                        ),
                    )

                    right.metric(
                        "Unresolved matters",
                        len(
                            element.unresolved_matters
                        ),
                    )

                    st.write(
                        "**Reviewed relationships**"
                    )

                    st.caption(
                        "Approved contradictions: "
                        + str(
                            len(
                                approved_contradictions
                            )
                        )
                        + " | Approved corroborations: "
                        + str(
                            len(
                                approved_corroborations
                            )
                        )
                        + " | Rejected proposals: "
                        + str(
                            len(
                                rejected_relationships
                            )
                        )
                        + " | Pending review: "
                        + str(
                            len(
                                pending_relationship_summaries
                            )
                        )
                    )

                    st.write(
                        "**What remains unresolved**"
                    )

                    if element.unresolved_matters:

                        for value in (
                            element.unresolved_matters
                        ):

                            st.write(
                                "- "
                                + value
                            )

                    else:

                        st.caption(
                            "No unresolved matters are recorded."
                        )

                    if element.evidential_gap_ids:

                        with st.expander(
                            "View formal gap identifiers",
                            expanded=False,
                        ):

                            st.caption(
                                "Technical governed identifiers."
                            )

                            for value in (
                                element.evidential_gap_ids
                            ):

                                st.code(
                                    value,
                                    language=None,
                                )

                    else:

                        st.caption(
                            "No formal evidential gaps are recorded."
                        )

                # ----------------------------------------------------------
                # CHALLENGE THIS FINDING
                #
                # Read-only adversarial projection over existing governed
                # evidence roles, unresolved matters, gaps and reviewed MAL1
                # relationships. No analytical or persistence state is changed.
                # ----------------------------------------------------------

                st.markdown(
                    "### Challenge this finding"
                )

                st.caption(
                    "Test the current position against the material "
                    "that could weaken, qualify or prevent reliance on it. "
                    "This is a read-only challenge view."
                )

                show_finding_challenge = (
                    st.toggle(
                        "+ Challenge this finding",
                        value=False,
                        key=(
                            "mal_challenge_finding_"
                            + issue.issue_analysis_id
                            + "_"
                            + element.element_id
                        ),
                    )
                )

                if show_finding_challenge:

                    with st.container(
                        border=True
                    ):

                        st.write(
                            "**Position being challenged:** "
                            + element.analytical_status
                        )

                        st.caption(
                            "Current frozen confidence: "
                            + element.analytical_confidence
                        )

                        left, right = (
                            st.columns(
                                2
                            )
                        )

                        left.metric(
                            "Adverse evidence",
                            len(
                                element.adverse_evidence_keys
                            ),
                        )

                        right.metric(
                            "Conflicting evidence",
                            len(
                                element.conflicting_evidence_keys
                            ),
                        )

                        left, right = (
                            st.columns(
                                2
                            )
                        )

                        left.metric(
                            "Approved contradictions",
                            len(
                                approved_contradictions
                            ),
                        )

                        right.metric(
                            "Unresolved matters",
                            len(
                                element.unresolved_matters
                            ),
                        )

                        left, right = (
                            st.columns(
                                2
                            )
                        )

                        left.metric(
                            "Formal gaps",
                            len(
                                element.evidential_gap_ids
                            ),
                        )

                        right.metric(
                            "Approved corroborations",
                            len(
                                approved_corroborations
                            ),
                        )

                        challenge_questions: list[
                            str
                        ] = []

                        if element.conflicting_evidence_keys:

                            challenge_questions.append(
                                "How is the mapped conflicting evidence "
                                "reconciled with the current position?"
                            )

                        if element.adverse_evidence_keys:

                            challenge_questions.append(
                                "What weight should be given to the mapped "
                                "adverse evidence before relying on this "
                                "position?"
                            )

                        if approved_contradictions:

                            challenge_questions.append(
                                "Does the approved contradiction materially "
                                "weaken or qualify the present position?"
                            )

                        if element.unresolved_matters:

                            challenge_questions.append(
                                "Could any unresolved matter change the "
                                "analytical position if resolved differently?"
                            )

                        if element.evidential_gap_ids:

                            challenge_questions.append(
                                "Could a formal evidential gap make the "
                                "current position premature or incomplete?"
                            )

                        challenge_questions.append(
                            "Does the current confidence remain justified "
                            "after considering the strongest contrary "
                            "material?"
                        )

                        st.write(
                            "**Questions the finding must withstand**"
                        )

                        for question in (
                            challenge_questions
                        ):

                            st.write(
                                "- "
                                + question
                            )

                        if element.unresolved_matters:

                            with st.expander(
                                "Unresolved matters to test",
                                expanded=False,
                            ):

                                for value in (
                                    element.unresolved_matters
                                ):

                                    st.write(
                                        "- "
                                        + value
                                    )

                        if element.evidential_gap_ids:

                            with st.expander(
                                "Formal gaps to test",
                                expanded=False,
                            ):

                                st.caption(
                                    "Governed technical identifiers."
                                )

                                for value in (
                                    element.evidential_gap_ids
                                ):

                                    st.code(
                                        value,
                                        language=None,
                                    )

                        challenge_pressure = any(
                            (
                                element.adverse_evidence_keys,
                                element.conflicting_evidence_keys,
                                approved_contradictions,
                                element.unresolved_matters,
                                element.evidential_gap_ids,
                            )
                        )

                        if challenge_pressure:

                            st.warning(
                                "Challenge signal: contrary or unresolved "
                                "material exists. The finding should not be "
                                "treated as free from challenge merely because "
                                "it has a current analytical classification."
                            )

                        else:

                            st.info(
                                "No mapped adverse, conflicting, contradiction, "
                                "gap or unresolved signal is currently recorded. "
                                "That does not prove the finding is correct."
                            )

                        st.caption(
                            "Read-only challenge. No evidence role, "
                            "relationship, analytical proposal or governed "
                            "authority has been changed."
                        )


                # ----------------------------------------------------------
                # WORK-PRODUCT AUTHORITY CHECKER
                #
                # Deterministic structured authority check only.
                # It does not infer the meaning of arbitrary prose.
                # ----------------------------------------------------------

                st.markdown(
                    "### Work-product authority checker"
                )

                st.caption(
                    "Check whether the analytical status, confidence "
                    "and evidence basis you intend to use in a draft "
                    "stay within the current frozen governed authority. "
                    "This deterministic check does not infer the semantic "
                    "meaning of arbitrary prose."
                )

                show_work_product_checker = (
                    st.toggle(
                        "+ Check work product",
                        value=False,
                        key=(
                            "mal_work_product_checker_"
                            + issue.issue_analysis_id
                            + "_"
                            + element.element_id
                        ),
                    )
                )

                if show_work_product_checker:

                    with st.container(
                        border=True
                    ):

                        with _matter_entry_form(key="mal_work_product_form_" + element.element_id):
                            work_product_statement = (
                                st.text_area(
                                    "Work-product statement or proposition",
                                    height=120,
                                    key=(
                                        "mal_work_product_statement_"
                                        + element.element_id
                                    ),
                                )
                            )

                            checker_status_options = tuple(
                                dict.fromkeys(
                                    (
                                        element.analytical_status,
                                        "well_supported",
                                        "partially_supported",
                                        "disputed",
                                        "insufficiently_evidenced",
                                        "unresolved",
                                    )
                                )
                            )

                            checker_confidence_options = tuple(
                                dict.fromkeys(
                                    (
                                        element.analytical_confidence,
                                        "high",
                                        "medium",
                                        "low",
                                    )
                                )
                            )

                            claimed_status = (
                                st.selectbox(
                                    "Status expressed by the work product",
                                    checker_status_options,
                                    format_func=lambda value: (
                                        value.replace(
                                            "_",
                                            " ",
                                        ).title()
                                    ),
                                    key=(
                                        "mal_work_product_status_"
                                        + element.element_id
                                    ),
                                )
                            )

                            claimed_confidence = (
                                st.selectbox(
                                    "Confidence expressed by the work product",
                                    checker_confidence_options,
                                    format_func=lambda value: (
                                        value.replace(
                                            "_",
                                            " ",
                                        ).title()
                                    ),
                                    key=(
                                        "mal_work_product_confidence_"
                                        + element.element_id
                                    ),
                                )
                            )

                            work_product_role_index = (
                                _role_index(
                                    element
                                )
                            )

                            work_product_evidence_options = tuple(
                                sorted(
                                    set(
                                        element.supporting_evidence_keys
                                        + element.adverse_evidence_keys
                                        + element.corroborative_evidence_keys
                                        + element.conflicting_evidence_keys
                                    )
                                )
                            )

                            cited_work_product_evidence = (
                                st.multiselect(
                                    "Governed evidence cited",
                                    work_product_evidence_options,
                                    format_func=lambda evidence_key: (
                                        _format_evidence_option(
                                            evidence_key,
                                            evidence_display_index,
                                            work_product_role_index,
                                        )
                                    ),
                                    key=(
                                        "mal_work_product_evidence_"
                                        + element.element_id
                                    ),
                                )
                            )

                            st.caption(
                                "The checker uses the frozen authority shown "
                                "above. An approved but unapplied analytical "
                                "change proposal does not replace that authority."
                            )

                            if _matter_form_submit_button(
                                "CHECK AGAINST CURRENT AUTHORITY",
                                key=(
                                    "mal_check_work_product_"
                                    + element.element_id
                                ),
                                use_container_width=True,
                            ):

                                try:

                                    authority_check = (
                                        check_work_product_authority(
                                            statement=
                                                work_product_statement,

                                            current_status=
                                                element.analytical_status,

                                            current_confidence=
                                                element.analytical_confidence,

                                            claimed_status=
                                                claimed_status,

                                            claimed_confidence=
                                                claimed_confidence,

                                            cited_evidence_keys=
                                                tuple(
                                                    cited_work_product_evidence
                                                ),

                                            allowed_evidence_keys=
                                                work_product_evidence_options,

                                            approved_contradiction_count=
                                                len(
                                                    approved_contradictions
                                                ),

                                            unresolved_matter_count=
                                                len(
                                                    element.unresolved_matters
                                                ),

                                            formal_gap_count=
                                                len(
                                                    element.evidential_gap_ids
                                                ),
                                        )
                                    )

                                except WorkProductAuthorityCheckerError as exc:

                                    st.error(
                                        str(
                                            exc
                                        )
                                    )

                                else:

                                    if (
                                        authority_check.result
                                        is WorkProductAuthorityResult.ALIGNED
                                    ):

                                        st.success(
                                            "ALIGNED WITH CURRENT AUTHORITY"
                                        )

                                    elif (
                                        authority_check.result
                                        is WorkProductAuthorityResult.CAUTION
                                    ):

                                        st.warning(
                                            "CAUTION - AUTHORITY HAS "
                                            "LIMITATIONS OR UNCERTAINTY"
                                        )

                                    else:

                                        st.error(
                                            "NOT AUTHORIZED BY CURRENT "
                                            "FROZEN AUTHORITY"
                                        )

                                    st.write(
                                        "**Authority-check reasons**"
                                    )

                                    for reason in (
                                        authority_check.reasons
                                    ):

                                        st.write(
                                            "- "
                                            + reason
                                        )

                                    st.caption(
                                        "No analytical state, evidence role, "
                                        "review history or governed authority "
                                        "has been changed."
                                    )


                # ----------------------------------------------------------
                # ANALYTICAL CHANGE PROPOSAL
                #
                # Approval records a reviewed proposal only.
                # It does NOT rewrite the frozen analytical authority.
                # ----------------------------------------------------------

                st.markdown(
                    "### Analytical change proposal"
                )

                st.caption(
                    "Propose a change to this analytical position. "
                    "Every proposal requires explicit review. "
                    "Even an approved proposal does not silently "
                    "rewrite the frozen governed authority."
                )

                try:

                    change_events = (
                        load_change_proposal_events(
                            case_id=
                                ledger.case_id,
                            authority_id=
                                ledger.authority_id,
                        )
                    )

                    element_change_proposals = (
                        project_change_proposals(
                            events=
                                change_events,
                            issue_analysis_id=
                                issue.issue_analysis_id,
                            element_id=
                                element.element_id,
                        )
                    )

                except AnalyticalChangeProposalError as exc:

                    st.error(
                        "Analytical change proposal history "
                        "failed closed."
                    )

                    st.caption(
                        str(
                            exc
                        )
                    )

                    element_change_proposals = ()

                pending_change_proposals = tuple(
                    proposal
                    for proposal
                    in element_change_proposals
                    if (
                        proposal.state
                        is AnalyticalChangeProposalState.PROPOSED
                    )
                )

                terminal_change_proposals = tuple(
                    proposal
                    for proposal
                    in element_change_proposals
                    if (
                        proposal.state
                        is not AnalyticalChangeProposalState.PROPOSED
                    )
                )

                if terminal_change_proposals:

                    with st.expander(
                        "Previous analytical change proposals - "
                        + str(
                            len(
                                terminal_change_proposals
                            )
                        ),
                        expanded=False,
                    ):

                        for proposal in (
                            terminal_change_proposals
                        ):

                            st.write(
                                "**"
                                + proposal.state.value
                                + " CHANGE PROPOSAL**"
                            )

                            st.write(
                                proposal.current_status
                                + " / "
                                + proposal.current_confidence
                                + "  ->  "
                                + proposal.proposed_status
                                + " / "
                                + proposal.proposed_confidence
                            )

                            st.caption(
                                proposal.rationale
                            )

                            if proposal.review_note:

                                st.caption(
                                    "Review note: "
                                    + proposal.review_note
                                )

                            if (
                                proposal.state
                                is AnalyticalChangeProposalState.APPROVED
                            ):

                                st.info(
                                    "Approved proposal only. "
                                    "The current frozen analytical "
                                    "authority has not been replaced."
                                )

                if pending_change_proposals:

                    for proposal in (
                        pending_change_proposals
                    ):

                        with st.container(
                            border=True
                        ):

                            st.warning(
                                "PENDING ANALYTICAL CHANGE REVIEW"
                            )

                            st.write(
                                "**Current:** "
                                + proposal.current_status
                                + " / "
                                + proposal.current_confidence
                            )

                            st.write(
                                "**Proposed:** "
                                + proposal.proposed_status
                                + " / "
                                + proposal.proposed_confidence
                            )

                            st.write(
                                "**Reason for proposed change**"
                            )

                            st.write(
                                proposal.rationale
                            )

                            st.caption(
                                "Reviewed relationship basis: "
                                + str(
                                    len(
                                        proposal.basis_relationship_ids
                                    )
                                )
                            )

                            change_review_note = (
                                st.text_area(
                                    "Optional reviewer note "
                                    "for this analytical change",
                                    key=(
                                        "mal_change_review_note_"
                                        + proposal.proposal_id
                                    ),
                                    height=90,
                                )
                            )

                            approve_change, reject_change = (
                                st.columns(
                                    2
                                )
                            )

                            if approve_change.button(
                                "APPROVE CHANGE PROPOSAL",
                                key=(
                                    "mal_approve_change_"
                                    + proposal.proposal_id
                                ),
                                use_container_width=True,
                            ):

                                try:

                                    review_analytical_change(
                                        case_id=
                                            ledger.case_id,
                                        authority_id=
                                            ledger.authority_id,
                                        proposal_id=
                                            proposal.proposal_id,
                                        decision=
                                            AnalyticalChangeProposalState.APPROVED,
                                        actor=
                                            "interactive_user",
                                        review_note=
                                            change_review_note,
                                    )

                                except AnalyticalChangeProposalError as exc:

                                    st.error(
                                        str(
                                            exc
                                        )
                                    )

                                else:

                                    st.rerun()

                            if reject_change.button(
                                "REJECT CHANGE PROPOSAL",
                                key=(
                                    "mal_reject_change_"
                                    + proposal.proposal_id
                                ),
                                use_container_width=True,
                            ):

                                try:

                                    review_analytical_change(
                                        case_id=
                                            ledger.case_id,
                                        authority_id=
                                            ledger.authority_id,
                                        proposal_id=
                                            proposal.proposal_id,
                                        decision=
                                            AnalyticalChangeProposalState.REJECTED,
                                        actor=
                                            "interactive_user",
                                        review_note=
                                            change_review_note,
                                    )

                                except AnalyticalChangeProposalError as exc:

                                    st.error(
                                        str(
                                            exc
                                        )
                                    )

                                else:

                                    st.rerun()

                elif pending_relationship_summaries:

                    st.info(
                        "Resolve the pending evidence-relationship "
                        "review before proposing an analytical change."
                    )

                else:

                    show_change_proposal = (
                        st.toggle(
                            "+ Propose analytical change",
                            value=False,
                            key=(
                                "mal_show_change_proposal_"
                                + issue.issue_analysis_id
                                + "_"
                                + element.element_id
                            ),
                        )
                    )

                    if show_change_proposal:

                        status_options = tuple(
                            dict.fromkeys(
                                (
                                    element.analytical_status,
                                    "well_supported",
                                    "partially_supported",
                                    "disputed",
                                    "insufficiently_evidenced",
                                    "unresolved",
                                )
                            )
                        )

                        confidence_options = tuple(
                            dict.fromkeys(
                                (
                                    element.analytical_confidence,
                                    "high",
                                    "medium",
                                    "low",
                                )
                            )
                        )

                        with _matter_entry_form(key="mal_analytical_change_form_" + element.element_id):
                            proposed_status = (
                                st.selectbox(
                                    "Proposed analytical status",
                                    status_options,
                                    format_func=lambda value: (
                                        value.replace(
                                            "_",
                                            " ",
                                        ).title()
                                    ),
                                    key=(
                                        "mal_change_status_"
                                        + element.element_id
                                    ),
                                )
                            )

                            proposed_confidence = (
                                st.selectbox(
                                    "Proposed confidence",
                                    confidence_options,
                                    format_func=lambda value: (
                                        value.replace(
                                            "_",
                                            " ",
                                        ).title()
                                    ),
                                    key=(
                                        "mal_change_confidence_"
                                        + element.element_id
                                    ),
                                )
                            )

                            change_rationale = (
                                st.text_area(
                                    "Why should the analytical "
                                    "position change?",
                                    height=140,
                                    key=(
                                        "mal_change_rationale_"
                                        + element.element_id
                                    ),
                                )
                            )

                            st.caption(
                                "The proposal will be bound to the "
                                "current authority and to "
                                + str(
                                    len(
                                        approved_contradictions
                                        + approved_corroborations
                                    )
                                )
                                + " approved reviewed evidence "
                                "relationship(s)."
                            )

                            if _matter_form_submit_button(
                                "PROPOSE ANALYTICAL CHANGE",
                                key=(
                                    "mal_submit_change_"
                                    + element.element_id
                                ),
                                use_container_width=True,
                            ):

                                basis_relationship_ids = tuple(
                                    sorted(
                                        {
                                            relationship.relationship_id
                                            for relationship
                                            in (
                                                approved_contradictions
                                                + approved_corroborations
                                            )
                                        }
                                    )
                                )

                                try:

                                    propose_analytical_change(
                                        case_id=
                                            ledger.case_id,
                                        authority_id=
                                            ledger.authority_id,
                                        issue_analysis_id=
                                            issue.issue_analysis_id,
                                        element_id=
                                            element.element_id,
                                        current_status=
                                            element.analytical_status,
                                        current_confidence=
                                            element.analytical_confidence,
                                        proposed_status=
                                            proposed_status,
                                        proposed_confidence=
                                            proposed_confidence,
                                        rationale=
                                            change_rationale,
                                        actor=
                                            "interactive_user",
                                        basis_relationship_ids=
                                            basis_relationship_ids,
                                    )

                                except AnalyticalChangeProposalError as exc:

                                    st.error(
                                        str(
                                            exc
                                        )
                                    )

                                else:

                                    st.rerun()


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
                    "#### Review & decisions"
                )

                relationships = (
                    element.relationships
                )

                if relationships:

                    for relationship in relationships:

                        with st.container(
                            border=True
                        ):

                            if (
                                relationship.state
                                is not RelationshipReviewState.PROPOSED
                            ):

                                _show_terminal_relationship_summary(
                                    relationship,
                                    evidence_display_index,
                                    role_index,
                                )

                                continue

                            st.write(
                                "**"
                                + relationship.relationship_type.value
                                + "** - "
                                + relationship.state.value
                            )

                            st.markdown(
                                "**Evidence A**"
                            )

                            _show_selected_evidence(
                                "Evidence A",
                                relationship.left_evidence_key,
                                evidence_display_index,
                                role_index,
                            )

                            st.markdown(
                                "**Evidence B**"
                            )

                            _show_selected_evidence(
                                "Evidence B",
                                relationship.right_evidence_key,
                                evidence_display_index,
                                role_index,
                            )

                            st.markdown(
                                "**Reason for proposed relationship**"
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

                                st.warning(
                                    "PENDING RELATIONSHIP REVIEW - "
                                    "choose APPROVE or REJECT below. "
                                    "The decision is append-only."
                                )

                                review_note = (
                                    st.text_area(
                                        "Optional reviewer note for this relationship",
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
                                    "APPROVE THIS RELATIONSHIP",
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
                                    "REJECT THIS RELATIONSHIP",
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

                pending_relationships = tuple(
                    relationship
                    for relationship in relationships
                    if (
                        relationship.state
                        is RelationshipReviewState.PROPOSED
                    )
                )

                if pending_relationships:

                    st.info(
                        "A relationship is awaiting review above. "
                        "New proposal controls are hidden until "
                        "that relationship is approved or rejected."
                    )

                elif len(evidence_options) >= 2:

                    proposal_visibility_key = (
                        "mal_show_proposal_"
                        + issue.issue_analysis_id
                        + "_"
                        + element.element_id
                    )

                    if not st.toggle(
                        "+ Propose relationship",
                        value=False,
                        key=
                            proposal_visibility_key,
                    ):

                        continue

                    proposal_key = (
                        "mal_proposal_"
                        + issue.issue_analysis_id
                        + "_"
                        + element.element_id
                    )

                    st.markdown(
                        "**Propose a contradiction "
                        "or corroboration**"
                    )

                    (
                        submitted,
                        relationship_type,
                        left,
                        right,
                        rationale,
                    ) = _matter_relationship_proposal_editor(
                        element=element,
                        proposal_key=proposal_key,
                        evidence_display_index=evidence_display_index,
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
