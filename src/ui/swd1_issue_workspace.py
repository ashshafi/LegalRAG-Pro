"""Solicitor-first legal issue register and core issue workspace."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from legal_issue_dashboard import (
    LegalIssueDashboardError,
    build_legal_issue_dashboard,
    build_swd1_evidence_items,
)

AuthorityLoader = Callable[[str], Any]

_TECHNICAL_MAPPING_TEXT = (
    "M4 does not promote the raw excerpt itself into an established proposition"
)
_PREVIEW_LIMIT = 520


def _issue_position(issue) -> str:
    counts = issue.synthesis_counts
    if counts.disputed:
        return "DISPUTED"
    if counts.insufficiently_evidenced:
        return "EVIDENCE INCOMPLETE"
    if counts.unresolved:
        return "UNRESOLVED"
    if counts.partially_supported:
        return "PARTIALLY SUPPORTED"
    if counts.well_supported:
        return "WELL SUPPORTED"
    return "NOT ASSESSED"


def _issue_confidence(issue) -> str:
    counts = issue.confidence_counts
    if counts.low:
        return "LOW"
    if counts.medium:
        return "MEDIUM"
    if counts.high:
        return "HIGH"
    return "NOT RECORDED"


def _position_explanation(position: str) -> str:
    return {
        "DISPUTED": "Material parts of this issue remain contested on the current evidence.",
        "EVIDENCE INCOMPLETE": "The current evidence is not yet sufficient for a secure assessment.",
        "UNRESOLVED": "A material legal question remains unresolved on the current evidence.",
        "PARTIALLY SUPPORTED": "The evidence provides meaningful support, but the issue is not fully established.",
        "WELL SUPPORTED": "The issue is well supported on the current evidential record.",
        "NOT ASSESSED": "No current assessment is recorded for this issue.",
    }[position]


def _label(value: str) -> str:
    return str(value).replace("_", " ").strip().upper()


def _unique_statements(*groups):
    seen = set()
    result = []
    for group in groups:
        for statement in tuple(group):
            key = (
                statement.text,
                tuple(statement.evidence_keys),
                tuple(statement.citations),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(statement)
    return tuple(result)


def _display_text(value: str) -> str:
    text = str(value).strip()
    if text.lower().startswith("source assertion:"):
        text = text[len("source assertion:"):].strip()
    return text


def _group_display_statements(statements):
    """Group repeated legal propositions while retaining all source citations."""
    substantive: dict[str, list[str]] = {}
    technical: dict[str, list[str]] = {}

    for statement in tuple(statements):
        text = _display_text(statement.text)
        bucket = technical if _TECHNICAL_MAPPING_TEXT in text else substantive
        citations = bucket.setdefault(text, [])
        for citation in tuple(statement.citations):
            value = str(citation).strip()
            if value and value not in citations:
                citations.append(value)

    return (
        tuple((text, tuple(citations)) for text, citations in substantive.items()),
        tuple((text, tuple(citations)) for text, citations in technical.items()),
    )


def _citation_caption(citations) -> str:
    values = tuple(citations)
    if not values:
        return ""
    shown = values[:3]
    suffix = (
        ""
        if len(values) <= 3
        else f" · +{len(values) - 3} more source"
        + ("s" if len(values) - 3 != 1 else "")
    )
    return "Source" + ("s" if len(values) > 1 else "") + ": " + " | ".join(shown) + suffix


def _write_statement(text: str, citations, *, allow_full_text: bool) -> None:
    with st.container(border=True):
        if len(text) <= _PREVIEW_LIMIT:
            st.write(_solicitor_working_text(text))
        else:
            preview = text[:_PREVIEW_LIMIT].rsplit(" ", 1)[0].rstrip()
            st.write(_solicitor_working_text(preview + "…"))
            if allow_full_text:
                with st.expander("Read full passage", expanded=False):
                    st.write(_solicitor_working_text(text))
            else:
                st.caption(_solicitor_working_text("Full passage available in the cited source."))

        caption = _citation_caption(citations)
        if caption:
            st.caption(_solicitor_working_text(caption))


def _first_open_point(issue) -> str | None:
    for element in issue.elements:
        if element.unresolved_matters:
            return element.unresolved_matters[0]
    for element in issue.elements:
        if element.limitations:
            return element.limitations[0]
    if issue.overall_limitations:
        return issue.overall_limitations[0]
    return None


def _default_element(issue):
    precedence = (
        "disputed",
        "insufficiently_evidenced",
        "unresolved",
        "partially_supported",
        "well_supported_on_current_record",
    )
    elements = tuple(issue.elements)
    for status in precedence:
        for element in elements:
            if str(element.provisional_status).strip().lower() == status:
                return element
    return elements[0] if elements else None


def _recommended_next_action(element) -> str:
    if element.unresolved_matters:
        return (
            "Check the contemporaneous record for evidence that directly "
            "resolves the selected question."
        )
    if element.limitations:
        return (
            "Review the recorded limitation against the source material "
            "before changing the current assessment."
        )
    return (
        "Review the principal evidence and confirm whether the current "
        "assessment remains appropriate."
    )


def _render_evidence(title: str, statements, *, empty_message: str) -> None:
    st.subheader(title)
    substantive, technical = _group_display_statements(statements)

    if not substantive:
        st.caption(_solicitor_working_text(empty_message))
    else:
        for text, citations in substantive[:3]:
            _write_statement(text, citations, allow_full_text=True)

        if len(substantive) > 3:
            with st.expander(
                f"More supporting material ({len(substantive) - 3})",
                expanded=False,
            ):
                for text, citations in substantive[3:]:
                    _write_statement(text, citations, allow_full_text=False)

    if technical:
        with st.expander(
            f"Additional source mappings ({len(technical)})",
            expanded=False,
        ):
            st.caption(
                _solicitor_working_text("Technical mapping material is retained here for traceability "
                "but is not part of the primary solicitor view.")
            )
            for text, citations in technical:
                _write_statement(text, citations, allow_full_text=False)


def _i3_source_character(item) -> str:
    value = str(item.evidence_status).strip().lower()
    return {
        "claimant_evidence": "Claimant evidence",
        "respondent_evidence": "Respondent position",
        "employer_evidence": "Employer record",
        "insurer_evidence": "Insurer record",
        "medical_evidence": "Medical evidence",
        "occupational_health_evidence": "Occupational health evidence",
        "source_assertion": "Source assertion",
        "mixed_evidence": "Mixed-source evidence",
    }.get(value, str(item.evidence_status).replace("_", " ").strip().title())


def _i3_is_low_signal_summary(summary: str) -> bool:
    text = str(summary).lower()
    boilerplate = (
        "this electronic message contains information",
        "virus free",
        "registered in england & wales",
        "registration no.",
        "intended to be used solely by the recipient",
        "if you are not an intended recipient",
    )
    return any(marker in text for marker in boilerplate)


def _i3_is_technical_proposition(text: str) -> bool:
    value = str(text)
    low = value.lower()
    return (
        _TECHNICAL_MAPPING_TEXT in value
        or "mapped respondent evidence contains factual material" in low
        or "mapped employer evidence contains factual material" in low
        or "mapped claimant evidence contains factual material" in low
    )


def _i3_is_procedural_material(item) -> bool:
    """Presentation-only gate for obvious procedural/form material.

    This does not change the governed analytical role.  It only prevents
    routine tribunal/form administration from occupying the primary merits
    evidence surface.
    """

    source_markers = " ".join(
        (
            str(item.evidence_status),
            str(item.provenance_type),
            str(item.source_type),
        )
    ).lower()

    if any(
        marker in source_markers
        for marker in (
            "procedural",
            "tribunal_form",
            "court_form",
            "administrative_form",
        )
    ):
        return True

    name = str(item.document_name).lower()
    if "atos_export" in name:
        return True
    if name.startswith("et hearing") or "et hearing (" in name:
        return True

    summary = str(item.summary).lower()
    procedural_markers = (
        "judicial mediation?",
        "are you interested in attending a judicial mediation",
        "judicial use only",
        "name of representative",
        "name of organisation",
        "how would you prefer us to communicate",
        "which types of hearing can you attend",
    )
    return any(marker in summary for marker in procedural_markers)


def _i3_group_by_document(items):
    groups = []
    index_by_key = {}

    for item in tuple(items):
        key = (
            str(item.document_name).strip()
            or str(item.citation).split(", p.")[0].strip()
            or str(item.evidence_key)
        )
        if key not in index_by_key:
            index_by_key[key] = len(groups)
            groups.append([item])
        else:
            groups[index_by_key[key]].append(item)

    return tuple(tuple(group) for group in groups)


def _i3_group_source_characters(group) -> tuple[str, ...]:
    values = []
    for item in group:
        label = _i3_source_character(item)
        if label and label not in values:
            values.append(label)
    return tuple(values)


def _i3_group_unique_text(group, selector):
    values = []
    for item in group:
        value = selector(item)
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _i3_write_grouped_passages(group) -> None:
    passages = tuple(
        item for item in group
        if item.summary and not _i3_is_low_signal_summary(item.summary)
    )

    if not passages:
        return

    st.markdown(_solicitor_working_text("**Relevant passage" + ("s" if len(passages) != 1 else "") + "**"))

    for item in passages[:3]:
        prefix = (
            f"p.{item.page}: "
            if item.page is not None
            else ""
        )
        text = str(item.summary).strip()

        if len(text) > 360:
            preview = text[:360].rsplit(" ", 1)[0].rstrip() + "…"
        else:
            preview = text

        st.write(_solicitor_working_text(prefix + preview))

    if len(passages) > 3:
        with st.expander(
            f"More passages from this source ({len(passages) - 3})",
            expanded=False,
        ):
            for item in passages[3:]:
                prefix = (
                    f"p.{item.page}: "
                    if item.page is not None
                    else ""
                )
                st.write(_solicitor_working_text(prefix + str(item.summary).strip()))


def _i3_write_grouped_propositions(group) -> None:
    propositions = []
    seen = set()

    for item in group:
        for proposition in _i3_substantive_propositions(item):
            key = (
                proposition.text,
                proposition.status,
                proposition.confidence,
            )
            if key in seen:
                continue
            seen.add(key)
            propositions.append(proposition)

    for proposition in propositions[:2]:
        status = str(proposition.status).strip().lower()
        if status == "established_by_current_evidence":
            st.markdown(_solicitor_working_text("**What the current evidence establishes**"))
        else:
            st.markdown(_solicitor_working_text("**What it may support**"))
        st.write(_solicitor_working_text(proposition.text))

    if len(propositions) > 2:
        st.caption(
            _solicitor_working_text(f"{len(propositions) - 2} additional governed proposition link"
            + ("s" if len(propositions) - 2 != 1 else "")
            + " retained.")
        )


def _render_i3_document_group(group) -> None:
    first = group[0]

    with st.container(border=True):
        title = str(first.document_name).strip() or _i3_item_title(first)
        st.markdown(_solicitor_working_text("**" + title + "**"))

        characters = _i3_group_source_characters(group)
        if characters:
            st.caption(_solicitor_working_text(" · ".join(characters)))

        _i3_write_grouped_passages(group)

        why_values = []
        limitation_values = []

        for item in group:
            why, rationale_limitation = _i3_rationale_parts(item)
            if why and why not in why_values:
                why_values.append(why)

            limitation = _i3_limitation(
                item,
                rationale_limitation,
            )
            if limitation and limitation not in limitation_values:
                limitation_values.append(limitation)

        if why_values:
            st.markdown(_solicitor_working_text("**Why it matters**"))
            for value in why_values[:2]:
                st.write(_solicitor_working_text(value))

        _i3_write_grouped_propositions(group)

        if limitation_values:
            st.markdown(_solicitor_working_text("**Limitation**"))
            for value in limitation_values[:2]:
                st.write(_solicitor_working_text(value))

        citations = _i3_group_unique_text(
            group,
            lambda item: str(item.citation).strip(),
        )
        if citations:
            st.caption(
                _solicitor_working_text("Source"
                + ("s" if len(citations) != 1 else "")
                + ": "
                + " | ".join(citations[:3])
                + (
                    f" · +{len(citations) - 3} more"
                    if len(citations) > 3
                    else ""
                ))
            )



def _i3_rationale_parts(item) -> tuple[str, str]:
    rationale = str(item.assessment_rationale).strip()
    low = rationale.lower()

    if (
        "source makes a relevant assertion" in low
        and "not independently established" in low
    ):
        return (
            "This source contains a relevant assertion about the selected question.",
            "The assertion does not by itself establish that the underlying fact is true.",
        )

    if "direct/non-derivative mapped record" in low:
        return (
            "This is a direct record bearing on the factual question.",
            "",
        )

    if "expressly records a denial or contrary position" in low:
        return (
            "This source records a denial or contrary position relevant to the question.",
            "It records a party position; the interface does not treat that position as an established fact.",
        )

    if "claimant-authored evidence is relevant" in low:
        return (
            "This records the claimant's account relevant to the selected question.",
            "It remains party evidence rather than independent confirmation.",
        )

    if "independent or third-party record" in low:
        return (
            "This is an independent or third-party record relevant to the factual question.",
            "Corroborative status is assigned only where another source independently records the same matter.",
        )

    if (
        "relevant to the element" in low
        and "cannot be classified safely" in low
    ):
        return (
            "This item is relevant context for the selected question.",
            "The current assessment does not safely classify it as helping or challenging the proposition.",
        )

    return (rationale, "")


def _i3_substantive_propositions(item):
    return tuple(
        proposition
        for proposition in tuple(item.proposition_links)
        if proposition.text
        and not _i3_is_technical_proposition(proposition.text)
    )


def _i3_item_title(item) -> str:
    if item.document_name:
        if item.page is not None:
            return f"{item.document_name} — p.{item.page}"
        return item.document_name
    if item.citation:
        return item.citation
    return "Evidence item"


def _i3_write_summary(summary: str, *, allow_expander: bool) -> None:
    text = str(summary).strip()
    if not text or _i3_is_low_signal_summary(text):
        return

    st.markdown(_solicitor_working_text("**Relevant passage**"))
    if len(text) <= _PREVIEW_LIMIT:
        st.write(_solicitor_working_text(text))
        return

    preview = text[:_PREVIEW_LIMIT].rsplit(" ", 1)[0].rstrip()
    st.write(_solicitor_working_text(preview + "…"))
    if allow_expander:
        with st.expander("Read full passage", expanded=False):
            st.write(_solicitor_working_text(text))


def _i3_write_propositions(item) -> None:
    propositions = _i3_substantive_propositions(item)
    if not propositions:
        return

    for proposition in propositions[:2]:
        status = str(proposition.status).strip().lower()

        if status == "established_by_current_evidence":
            st.markdown(_solicitor_working_text("**What the current evidence establishes**"))
        else:
            st.markdown(_solicitor_working_text("**What it may support**"))

        st.write(_solicitor_working_text(proposition.text))

        if proposition.confidence:
            st.caption(
                _solicitor_working_text("Evidential confidence: "
                + str(proposition.confidence).replace("_", " ").title())
            )

    if len(propositions) > 2:
        st.caption(
            _solicitor_working_text(f"{len(propositions) - 2} additional proposition link"
            + ("s" if len(propositions) - 2 != 1 else "")
            + " retained in the governed assessment.")
        )


def _i3_limitation(item, rationale_limitation: str) -> str:
    if rationale_limitation:
        return rationale_limitation

    evidence_status = str(item.evidence_status).strip().lower()
    if evidence_status == "source_assertion":
        return (
            "This is a source assertion. It does not by itself establish "
            "the truth of the underlying proposition."
        )

    if evidence_status == "respondent_evidence":
        return (
            "This records the respondent's position. It is not treated here "
            "as an established fact."
        )

    return ""


def _render_i3_evidence_item(item, *, allow_expander: bool = True) -> None:
    with st.container(border=True):
        st.markdown(_solicitor_working_text("**" + _i3_item_title(item) + "**"))

        source_character = _i3_source_character(item)
        if source_character:
            st.caption(_solicitor_working_text(source_character))

        _i3_write_summary(
            item.summary,
            allow_expander=allow_expander,
        )

        why, rationale_limitation = _i3_rationale_parts(item)
        if why:
            st.markdown(_solicitor_working_text("**Why it matters**"))
            st.write(_solicitor_working_text(why))

        _i3_write_propositions(item)

        limitation = _i3_limitation(item, rationale_limitation)
        if limitation:
            st.markdown(_solicitor_working_text("**Limitation**"))
            st.write(_solicitor_working_text(limitation))

        if item.citation:
            st.caption(_solicitor_working_text("Source: " + item.citation))


def _render_i3_evidence_group(
    title: str,
    items,
    *,
    empty_message: str,
) -> None:
    st.subheader(title)

    ordered = tuple(items)

    primary = tuple(
        item
        for item in ordered
        if not _i3_is_low_signal_summary(item.summary)
        and not _i3_is_procedural_material(item)
    )
    secondary = tuple(
        item
        for item in ordered
        if item not in primary
    )

    grouped = _i3_group_by_document(primary)

    if not grouped:
        st.caption(_solicitor_working_text(empty_message))
    else:
        for group in grouped[:3]:
            _render_i3_document_group(group)

        if len(grouped) > 3:
            with st.expander(
                f"Show more evidence sources ({len(grouped) - 3})",
                expanded=False,
            ):
                for group in grouped[3:]:
                    _render_i3_document_group(group)

    if secondary:
        with st.expander(
            f"Additional evidence ({len(secondary)})",
            expanded=False,
        ):
            st.caption(
                _solicitor_working_text("Routine form, procedural, footer or other low-signal material "
                "is retained for traceability but kept out of the primary legal view.")
            )
            for item in secondary:
                if item.citation:
                    st.write(_solicitor_working_text("• " + item.citation))
def _render_i3_secondary_context(items) -> None:
    ordered = tuple(items)
    if not ordered:
        return

    with st.expander(
        f"Other relevant context ({len(ordered)})",
        expanded=False,
    ):
        st.caption(
            _solicitor_working_text("The governed assessment records these items as context rather "
            "than evidence helping or challenging the selected proposition.")
        )
        for item in ordered:
            label = item.citation or _i3_item_title(item)
            why, _ = _i3_rationale_parts(item)
            st.write(_solicitor_working_text("**" + label + "**"))
            if why:
                st.caption(_solicitor_working_text(why))



# ---------------------------------------------------------------------------
# SWD1 solicitor-facing post-validation refinement.
# Presentation only: no analytical state, ranking or authority mutation.
# ---------------------------------------------------------------------------

def _solicitor_working_text(value):
    if not isinstance(value, str):
        return value

    text = value

    replacements = (
        (
            "M4 does not determine credibility",
            "The current material does not determine credibility",
        ),
        (
            "M4 does not resolve credibility",
            "The current material does not resolve credibility",
        ),
        (
            "M4 does not promote the raw excerpt itself into an established proposition",
            "The current assessment does not treat the raw excerpt itself as an established proposition",
        ),
        (
            "Mapped evidence",
            "Current evidence",
        ),
        (
            "mapped evidence",
            "current evidence",
        ),
    )

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def _issue_requires_attention(issue) -> bool:
    elements = tuple(getattr(issue, "elements", ()) or ())

    for element in elements:
        unresolved = tuple(
            getattr(element, "unresolved_matters", ()) or ()
        )
        gaps = tuple(
            getattr(element, "evidential_gaps", ()) or ()
        )
        status = str(
            getattr(element, "provisional_status", "") or ""
        ).strip().lower().replace(" ", "_")

        if unresolved or gaps:
            return True

        if status and status not in {
            "well_supported",
            "established",
            "supported",
        }:
            return True

    return bool(tuple(getattr(issue, "overall_limitations", ()) or ()))


def _attention_issues(dashboard):
    """Return attention-bearing issues in frozen/canonical case order."""

    return tuple(
        issue
        for issue in tuple(getattr(dashboard, "issues", ()) or ())
        if _issue_requires_attention(issue)
    )


def _first_open_point(issue) -> str:
    for element in tuple(getattr(issue, "elements", ()) or ()):
        unresolved = tuple(
            getattr(element, "unresolved_matters", ()) or ()
        )
        if unresolved:
            return _solicitor_working_text(str(unresolved[0]))

        gaps = tuple(
            getattr(element, "evidential_gaps", ()) or ()
        )
        if gaps:
            gap = gaps[0]
            for attr in ("description", "text", "gap", "question"):
                value = getattr(gap, attr, None)
                if value:
                    return _solicitor_working_text(str(value))

    return ""


def _render_issue_attention(dashboard) -> None:
    issues = _attention_issues(dashboard)
    if not issues:
        return

    st.subheader("Issues requiring attention")
    st.caption(
        _solicitor_working_text("These issues contain unresolved or disputed matters in the current "
        "assessment. They are shown in case order, not ranked by importance.")
    )

    for issue in issues:
        with st.container(border=True):
            st.markdown(
                _solicitor_working_text("**" + _solicitor_working_text(str(issue.issue_name)) + "**")
            )
            open_point = _first_open_point(issue)
            if open_point:
                st.write(_solicitor_working_text(open_point))



def show_swd1_issue_workspace(
    active_case_id: str | None,
    *,
    authority_loader: AuthorityLoader = load_active_governed_analytical_authority,
) -> None:
    """Render SWD1-I1/I2 without changing analytical or authority state."""

    st.header("Legal Issues")
    st.caption(
        _solicitor_working_text("Current case assessment — work the legal issue, evidence and next action here.")
    )

    if active_case_id is None:
        st.info("Select an active matter to work on its legal issues.")
        return

    try:
        authority = authority_loader(active_case_id)
    except GovernedAnalyticalAuthorityProviderError:
        st.error(
            "The current case assessment could not be validated. "
            "No legal analysis has been displayed."
        )
        return

    if authority is None:
        st.info("No current case assessment is available for this matter.")
        return

    try:
        dashboard = build_legal_issue_dashboard(
            active_case_id=active_case_id,
            authority=authority,
        )
    except LegalIssueDashboardError:
        st.error(
            "The current case assessment could not be projected safely. "
            "No legal analysis has been displayed."
        )
        return

    selected_id = st.session_state.get("swd1_selected_issue_id")
    selected_issue = next(
        (
            issue
            for issue in dashboard.issues
            if issue.issue_analysis_id == selected_id
        ),
        None,
    )

    if selected_issue is None:
        st.info(
            "Choose an issue to see where the case stands, what is weak, "
            "and what should be done next."
        )

        _render_issue_attention(dashboard)

        for issue in dashboard.issues:
            position = _issue_position(issue)
            support = _issue_confidence(issue)
            open_point = _first_open_point(issue)

            with st.container(border=True):
                st.subheader(issue.issue_name)

                left, right = st.columns(2)
                with left:
                    st.caption(_solicitor_working_text("CURRENT POSITION"))
                    st.write(_solicitor_working_text(position))
                with right:
                    st.caption(_solicitor_working_text("EVIDENTIAL SUPPORT"))
                    st.write(_solicitor_working_text(support.title()))

                st.write(_solicitor_working_text(_position_explanation(position)))

                if open_point:
                    st.markdown(_solicitor_working_text("**Main weakness**"))
                    st.write(_solicitor_working_text(open_point))
                else:
                    st.caption(
                        _solicitor_working_text("No specific unresolved point is recorded for this issue.")
                    )

                st.caption(
                    _solicitor_working_text("Open the issue to review the evidence and decide the next legal action.")
                )

                if st.button(
                    "Open issue",
                    key="swd1_open_issue::" + issue.issue_analysis_id,
                    type="primary",
                ):
                    st.session_state["swd1_selected_issue_id"] = (
                        issue.issue_analysis_id
                    )
                    st.session_state.pop("swd1_selected_element_id", None)
                    st.rerun()

        with st.expander("Audit", expanded=False):
            st.caption(_solicitor_working_text("Current governed authority: " + dashboard.authority_id))
            st.caption(_solicitor_working_text("Activation: " + dashboard.activation_id))
        return

    if st.button("← Back to issues", key="swd1_back_to_issues"):
        st.session_state.pop("swd1_selected_issue_id", None)
        st.session_state.pop("swd1_selected_element_id", None)
        st.rerun()

    st.header(selected_issue.issue_name)
    st.caption(_solicitor_working_text("Legal question: " + selected_issue.original_user_question))

    position = _issue_position(selected_issue)
    support = _issue_confidence(selected_issue)

    with st.container(border=True):
        st.caption(_solicitor_working_text("CURRENT POSITION"))
        st.subheader(position)
        st.write(_solicitor_working_text("Overall issue evidential support: " + support.title()))
        st.write(_solicitor_working_text(_position_explanation(position)))

    elements = tuple(selected_issue.elements)
    if not elements:
        st.info("No governed legal questions are available for this issue.")
        return

    default = _default_element(selected_issue)
    ids = tuple(element.element_id for element in elements)
    chosen = st.session_state.get("swd1_selected_element_id")
    if chosen not in ids:
        chosen = default.element_id

    chosen = st.selectbox(
        "Question to work on",
        ids,
        index=ids.index(chosen),
        format_func=lambda element_id: next(
            (
                element.legal_question
                for element in elements
                if element.element_id == element_id
            ),
            element_id,
        ),
        key="swd1_question_select",
    )
    st.session_state["swd1_selected_element_id"] = chosen
    element = next(item for item in elements if item.element_id == chosen)

    st.caption(
        _solicitor_working_text("Selected question — position: "
        + _label(element.provisional_status)
        + " · Evidential support: "
        + _label(element.analysis_confidence).title())
    )

    weakness = (
        element.unresolved_matters[0]
        if element.unresolved_matters
        else (
            element.limitations[0]
            if element.limitations
            else None
        )
    )

    if weakness:
        with st.container(border=True):
            st.subheader("Main weakness")
            st.write(_solicitor_working_text(weakness))

    st.subheader("Why this matters")
    st.write(_solicitor_working_text(element.legal_significance))

    evidence_items = build_swd1_evidence_items(
        authority=authority,
        issue_analysis_id=selected_issue.issue_analysis_id,
        element_id=element.element_id,
    )

    indicating = tuple(
        item
        for item in evidence_items
        if str(item.analytical_role).strip().lower()
        in {"supporting", "corroborative"}
    )
    challenging = tuple(
        item
        for item in evidence_items
        if str(item.analytical_role).strip().lower()
        in {"adverse", "conflicting"}
    )
    context = tuple(
        item
        for item in evidence_items
        if str(item.analytical_role).strip().lower()
        in {"neutral", "contextual"}
    )
    classified_ids = {id(item) for item in indicating + challenging + context}
    other = tuple(
        item
        for item in evidence_items
        if id(item) not in classified_ids
    )

    _render_i3_evidence_group(
        "Evidence indicating the proposition",
        indicating,
        empty_message=(
            "No governed evidence item is presently classified as supporting "
            "or corroborative for this question."
        ),
    )
    _render_i3_evidence_group(
        "Evidence challenging or limiting that conclusion",
        challenging,
        empty_message=(
            "No governed evidence item is presently classified as adverse "
            "or conflicting for this question."
        ),
    )

    _render_i3_secondary_context(context)

    if other:
        with st.expander(
            f"Other governed evidence ({len(other)})",
            expanded=False,
        ):
            for item in other:
                label = item.citation or _i3_item_title(item)
                st.write(_solicitor_working_text("• " + label))

    st.subheader("What remains unclear")
    if element.unresolved_matters:
        for item in element.unresolved_matters:
            st.write(_solicitor_working_text("• " + item))
    else:
        st.caption(_solicitor_working_text("No unresolved matter is recorded for this question."))

    if element.limitations:
        with st.expander("Important limitations", expanded=False):
            for item in element.limitations:
                st.write(_solicitor_working_text("• " + item))

    st.subheader("Next legal action")
    st.write(_solicitor_working_text(_recommended_next_action(element)))

    with st.expander("Audit", expanded=False):
        st.caption(_solicitor_working_text("Issue analysis ID: " + selected_issue.issue_analysis_id))
        st.caption(
            _solicitor_working_text("Issue definition: "
            + selected_issue.issue_definition_id
            + "/"
            + selected_issue.issue_definition_version)
        )
        st.caption(_solicitor_working_text("Element ID: " + element.element_id))
        st.caption(_solicitor_working_text("Raw question position: " + element.provisional_status))
        st.caption(_solicitor_working_text("Raw analysis confidence: " + element.analysis_confidence))
        st.caption(_solicitor_working_text("Current governed authority: " + dashboard.authority_id))
        st.caption(_solicitor_working_text("Activation: " + dashboard.activation_id))


__all__ = ["show_swd1_issue_workspace"]
