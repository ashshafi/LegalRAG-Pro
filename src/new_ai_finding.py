"""Solicitor-facing New AI Finding routing for exact source comparisons.

This module does not create or mutate analytical authority. It identifies a narrow
interactive situation where an explicitly resolved governed document/location has
already forced complete U8 inspection and the user is asking for a comparison that
may generate a new provisional finding.
"""

from __future__ import annotations

from typing import Any

_COMPARISON_CUES = (
    "compare",
    "contradiction",
    "contradict",
    "inconsistent",
    "inconsistency",
    "conflict",
    "versus",
    " vs ",
    "against",
    "reconcile",
)


def is_source_comparison_new_ai_finding(*, question: str, evidence: Any) -> bool:
    """Return True only for an explicitly resolved, document-complete comparison.

    In the current interactive architecture:
    - ordinary semantic-only questions have search_result=None;
    - explicit source/location questions retain semantic_results and continue into
      document-complete expansion;
    - exhaustive questions have semantic_results=None.

    Therefore search_result + semantic_results is the deterministic state proving
    that an explicit source/location was successfully resolved and completely
    inspected before this routing decision.
    """

    if evidence is None:
        return False
    if getattr(evidence, "search_result", None) is None:
        return False
    if getattr(evidence, "semantic_results", None) is None:
        return False

    text = f" {str(question or '').casefold()} "
    return any(cue in text for cue in _COMPARISON_CUES)


def _explicit_location_integrity_text(explicit_location: Any) -> str:
    if explicit_location is None:
        return (
            "EXPLICIT SOURCE/LOCATION VERIFICATION - DETERMINISTIC\n"
            "No deterministic explicit-location verification record was supplied.\n"
            "Do not assign an exact page to a requested paragraph/location solely "
            "from the wording of the question."
        )

    filename = str(getattr(explicit_location, "matched_filename", "unknown document"))
    kind = str(getattr(explicit_location, "location_kind", "") or "location")
    requested = tuple(getattr(explicit_location, "requested_locations", ()) or ())
    verified_pairs = tuple(
        getattr(explicit_location, "verified_location_pages", ()) or ()
    )
    missing = tuple(getattr(explicit_location, "missing_locations", ()) or ())
    ambiguous = tuple(getattr(explicit_location, "ambiguous_locations", ()) or ())
    verified = {int(location): int(page) for location, page in verified_pairs}

    lines = [
        "EXPLICIT SOURCE/LOCATION VERIFICATION - DETERMINISTIC",
        f"document: {filename}",
        f"location_kind: {kind}",
        "requested_locations: "
        + (", ".join(str(value) for value in requested) if requested else "none"),
    ]
    for location in requested:
        if location in verified:
            lines.append(
                f"{kind} {location}: VERIFIED_PAGE={verified[location]}"
            )
        elif location in ambiguous:
            lines.append(f"{kind} {location}: AMBIGUOUS_PAGE")
        else:
            lines.append(f"{kind} {location}: NOT_VERIFIED")

    complete = bool(requested) and len(verified) == len(requested) and not missing and not ambiguous
    lines.append(f"verification_complete: {'yes' if complete else 'no'}")
    return "\n".join(lines)

def bind_source_comparison_relied_evidence_keys(
    *,
    answer: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind every explicit page-bearing citation to exact governed evidence.

    Search coverage is never treated as reliance. A New AI Finding is citation
    complete only when every explicit document/page coordinate used in the
    answer resolves uniquely to one governed evidence key. Missing or ambiguous
    coordinates remain unbound.
    """

    import re
    import unicodedata

    def _normalise(value: Any) -> str:
        result = unicodedata.normalize("NFKC", str(value or ""))
        result = (
            result.replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u2212", "-")
        )
        return re.sub(r"\s+", " ", result).strip().lower()

    def _source_key(source: dict[str, Any]) -> str | None:
        for name in ("evidence_key", "source_evidence_key"):
            value = source.get(name)
            if isinstance(value, str) and value:
                return value
        return None

    def _source_file(source: dict[str, Any]) -> str | None:
        for name in ("file", "filename", "source_filename", "original_filename"):
            value = source.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _source_page(source: dict[str, Any]) -> int | None:
        for name in ("page", "page_number", "source_page_number"):
            value = source.get(name)
            if isinstance(value, int) and value > 0:
                return value
            if isinstance(value, str) and value.strip().isdigit():
                page = int(value.strip())
                if page > 0:
                    return page
        return None

    def _aliases(filename: str) -> tuple[str, ...]:
        stem = re.sub(r"(?i)\.pdf$", "", filename).strip()
        normalised_stem = _normalise(stem)
        values = [normalised_stem]
        appendix = re.match(r"^(appendix\s+[a-z0-9]+)\b", normalised_stem)
        if appendix:
            values.append(appendix.group(1))
        return tuple(dict.fromkeys(item for item in values if item))

    if not isinstance(answer, str) or not answer.strip() or not isinstance(sources, list):
        return {
            "schema": "new-ai-finding-citation-completeness/v2",
            "status": "unbound",
            "citation_binding_complete": False,
            "explicit_citation_count": 0,
            "bound_citation_count": 0,
            "unmatched_citation_count": 0,
            "ambiguous_citation_count": 0,
            "relied_evidence_keys": [],
            "matched_citations": [],
            "unmatched_citations": [],
            "ambiguous_citations": [],
        }

    source_rows: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        evidence_key = _source_key(source)
        filename = _source_file(source)
        page = _source_page(source)
        if not evidence_key or not filename or page is None:
            continue
        source_rows.append(
            {
                "evidence_key": evidence_key,
                "file": filename,
                "page": page,
                "aliases": _aliases(filename),
            }
        )

    normalised_answer = _normalise(answer)
    citation_specs: list[dict[str, Any]] = []
    page_pattern = re.compile(
        r"\b(pp?|pages?)\s*\.?\s*(\d+)(?:\s*-\s*(\d+))?"
    )

    for page_match in page_pattern.finditer(normalised_answer):
        first_page = int(page_match.group(2))
        last_page = int(page_match.group(3) or first_page)
        low, high = sorted((first_page, last_page))

        prefix_start = max(0, page_match.start() - 260)
        prefix = normalised_answer[prefix_start : page_match.start()]
        label_hits: list[tuple[int, int, int, int, str]] = []

        # Known governed-source aliases.
        for row in source_rows:
            for alias in row["aliases"]:
                pos = prefix.rfind(alias)
                if pos >= 0:
                    label_hits.append(
                        (
                            prefix_start + pos,
                            prefix_start + pos + len(alias),
                            1,  # known-source label wins ties
                            len(alias),
                            alias,
                        )
                    )

        # Generic PDF label nearest the page marker. This is deliberately
        # retained even when it is not in the governed source list so the
        # citation is counted as unmatched rather than silently ignored.
        pdf_end = prefix.rfind(".pdf")
        if pdf_end >= 0:
            suffix = prefix[pdf_end + 4 :]
            if not suffix.strip(" \t,;:()[]*"):
                separators = [
                    (prefix.rfind(". ", 0, pdf_end), 2),
                    (prefix.rfind("; ", 0, pdf_end), 2),
                    (prefix.rfind(": ", 0, pdf_end), 2),
                    (prefix.rfind("\n", 0, pdf_end), 1),
                ]
                boundary, width = max(separators, key=lambda item: item[0])
                generic = prefix[
                    boundary + width if boundary >= 0 else 0 : pdf_end
                ].strip(" \t,;:()[]*")
                if generic:
                    generic = _normalise(generic)
                    label_hits.append(
                        (
                            prefix_start + (
                                boundary + width if boundary >= 0 else 0
                            ),
                            prefix_start + pdf_end,
                            0,
                            len(generic),
                            generic,
                        )
                    )

        # Generic short Appendix coordinate.
        for appendix_match in re.finditer(
            r"(appendix\s+[a-z0-9]+)"
            r"(?:\s*-[^,;\n]{0,150})?\s*[,;:]?\s*$",
            prefix,
        ):
            generic = _normalise(appendix_match.group(1))
            label_hits.append(
                (
                    prefix_start + appendix_match.start(1),
                    prefix_start + appendix_match.end(1),
                    0,
                    len(generic),
                    generic,
                )
            )

        if not label_hits:
            # A bare page number is not enough to identify a source citation.
            continue

        # The citation label nearest to the page marker wins. If a generic
        # label and an exact governed alias end at the same place, prefer the
        # governed alias; then prefer the longer label.
        chosen = max(label_hits, key=lambda item: (item[1], item[2], item[3]))
        label = chosen[4]

        for page in range(low, high + 1):
            citation_specs.append(
                {
                    "label": label,
                    "page": page,
                    "position": page_match.start(),
                }
            )

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for citation in citation_specs:
        candidates = [
            row
            for row in source_rows
            if row["page"] == citation["page"]
            and citation["label"] in row["aliases"]
        ]
        keys = sorted({str(row["evidence_key"]) for row in candidates})

        if len(keys) == 1:
            chosen = sorted(
                (row for row in candidates if row["evidence_key"] == keys[0]),
                key=lambda row: (str(row["file"]).lower(), str(row["evidence_key"])),
            )[0]
            matched.append(
                {
                    "label": citation["label"],
                    "page": citation["page"],
                    "position": citation["position"],
                    "file": chosen["file"],
                    "evidence_key": chosen["evidence_key"],
                }
            )
        elif len(keys) > 1:
            ambiguous.append(
                {
                    "label": citation["label"],
                    "page": citation["page"],
                    "position": citation["position"],
                    "candidate_evidence_keys": keys,
                }
            )
        else:
            unmatched.append(dict(citation))

    matched.sort(
        key=lambda row: (
            int(row["position"]),
            str(row["file"]).lower(),
            int(row["page"]),
            str(row["evidence_key"]),
        )
    )
    unmatched.sort(key=lambda row: (int(row["position"]), str(row["label"]), int(row["page"])))
    ambiguous.sort(key=lambda row: (int(row["position"]), str(row["label"]), int(row["page"])))

    relied: list[str] = []
    seen: set[str] = set()
    for row in matched:
        key = str(row["evidence_key"])
        if key not in seen:
            seen.add(key)
            relied.append(key)

    explicit_count = len(citation_specs)
    bound_count = len(matched)
    unmatched_count = len(unmatched)
    ambiguous_count = len(ambiguous)
    citation_binding_complete = (
        explicit_count > 0
        and bound_count == explicit_count
        and unmatched_count == 0
        and ambiguous_count == 0
    )

    if citation_binding_complete:
        status = "bound"
    elif bound_count:
        status = "incomplete"
    else:
        status = "unbound"

    return {
        "schema": "new-ai-finding-citation-completeness/v2",
        "status": status,
        "citation_binding_complete": citation_binding_complete,
        "explicit_citation_count": explicit_count,
        "bound_citation_count": bound_count,
        "unmatched_citation_count": unmatched_count,
        "ambiguous_citation_count": ambiguous_count,
        "relied_evidence_keys": relied,
        "matched_citations": [
            {
                "file": row["file"],
                "page": row["page"],
                "evidence_key": row["evidence_key"],
            }
            for row in matched
        ],
        "unmatched_citations": [
            {"label": row["label"], "page": row["page"]}
            for row in unmatched
        ],
        "ambiguous_citations": [
            {
                "label": row["label"],
                "page": row["page"],
                "candidate_evidence_keys": row["candidate_evidence_keys"],
            }
            for row in ambiguous
        ],
    }




def wrap_source_comparison_new_ai_finding_prompt(
    *,
    base_prompt: str,
    question: str,
    explicit_location: Any = None,
) -> str:
    """Add a non-authoritative solicitor-facing source-comparison contract."""

    is_bounded_map_pass = "LEGALRAG GOVERNED LARGE-MATTER MAP PASS" in base_prompt
    location_integrity = _explicit_location_integrity_text(explicit_location)

    presentation_rules = (
        """
INTERMEDIATE MAP-PASS RULE:
This is an evidence-analysis batch, not the final solicitor-facing answer.
Follow the map-pass output format in the underlying prompt exactly. Do not write
the executive summary, final headings, or final legal synthesis at this stage.
Preserve every material source/page finding needed by the later synthesis.
""".strip()
        if is_bounded_map_pass
        else """
FINAL SOLICITOR-FACING OUTPUT ORDER - MANDATORY:
1. Begin with the heading "## Key findings".
2. Under it, give 3-5 concise bullets containing only the strongest material
   contradictions, inconsistencies, or qualifications. Keep each bullet to no more
   than two short sentences and normally no more than about 45 words. Lead with the
   practical point, then give only the principal source document/page reference(s).
   Do not reproduce the detailed evidence narrative in this section and do not
   introduce evidence or conclusions that are absent from the detailed analysis.
3. Then use the heading "## Detailed analysis".
4. Give the full source-comparison analysis requested by the user. Identify each
   material contradiction or qualification separately, cite both sides by source
   document and page, and explain why it may matter legally.
5. Consolidate overlapping points and avoid repeating the same evidence merely
   to make the answer longer.
6. End with material qualifications only where they are genuinely needed.
""".strip()
    )

    return f"""NEW AI FINDING - SOURCE COMPARISON

This is a provisional AI finding generated from governed evidence that has already
been inspected for this answer. It is NOT the Current Assessment, does not replace
or amend any frozen analytical authority, and requires professional review before
it can affect the Current Assessment.

{location_integrity}

CITATION-INTEGRITY RULES:
1. The deterministic verification block above is the sole authority for assigning
   an exact page to the explicitly requested paragraph/page location.
2. Cite a requested location as "paragraph/page N, p.X" only
   when that location is marked VERIFIED_PAGE=X above.
3. If a requested location is NOT_VERIFIED or AMBIGUOUS_PAGE, do not invent or
   inherit a page number for it from the question, a summary, a pleading reference,
   or another mapped finding.
4. Other evidence rows may still be cited using their own governed file/page
   metadata, but do not present that as verification of an unverified requested
   paragraph/location.
5. If verification_complete is no, state that limitation clearly in the final
   answer and distinguish verified pleading coordinates from propositions reported
   only by other evidence.

Solicitor-facing rules:
1. Answer the user's exact source-comparison question from the supplied governed
   evidence, including the explicitly requested document/location.
2. Identify each apparent contradiction or inconsistency separately.
3. For each side of each comparison, name the source document and page, subject
   strictly to the citation-integrity rules above.
4. Distinguish contemporaneous primary evidence from later witness evidence,
   pleadings, summaries, or commentary.
5. Explain why each point may matter legally, but do not overstate what it proves.
6. State material qualifications, ambiguities, or authentication issues.
7. Do not expose authority hashes, internal analytical codes, proposition statuses,
   or governance implementation terminology in the working answer.
8. Do not say the Current Assessment has changed. This output is a new finding
   awaiting professional review.
9. Do not invent missing text. If the requested source/location is genuinely absent
   or not deterministically verified in the supplied governed evidence, say so
   specifically.

{presentation_rules}

USER QUESTION:
{question}

{base_prompt}
""".strip()


NEW_AI_FINDING_NOTICE = (
    "New AI finding — not yet part of Current Assessment. "
    "This source comparison has not changed the Current Assessment and requires professional review."
)
