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
