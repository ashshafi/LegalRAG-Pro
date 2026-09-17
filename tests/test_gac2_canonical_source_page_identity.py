from __future__ import annotations

from new_ai_finding import bind_source_comparison_relied_evidence_keys


def _source(file: str, page: int, key: str) -> dict:
    return {"file": file, "page": page, "evidence_key": key}


def test_multiple_chunks_on_same_document_page_are_one_canonical_source_page():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The email is direct contemporaneous evidence. Appendix E1, p.1.",
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1-chunk-a",
            ),
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1-chunk-b",
            ),
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1-chunk-c",
            ),
        ],
    )

    assert result["citation_binding_complete"] is True
    assert result["explicit_citation_count"] == 1
    assert result["bound_citation_count"] == 1
    assert result["ambiguous_citation_count"] == 0
    assert result["canonical_source_page_count"] == 1
    assert result["relied_evidence_keys"] == [
        "e1-p1-chunk-a",
        "e1-p1-chunk-b",
        "e1-p1-chunk-c",
    ]
    assert result["matched_citations"][0]["evidence_keys"] == [
        "e1-p1-chunk-a",
        "e1-p1-chunk-b",
        "e1-p1-chunk-c",
    ]


def test_short_appendix_alias_is_still_ambiguous_across_distinct_documents():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The relevant material is at Appendix E1, p.1.",
        sources=[
            _source("Appendix E1 - Version A.pdf", 1, "a-chunk-1"),
            _source("Appendix E1 - Version A.pdf", 1, "a-chunk-2"),
            _source("Appendix E1 - Version B.pdf", 1, "b-chunk-1"),
        ],
    )

    assert result["citation_binding_complete"] is False
    assert result["bound_citation_count"] == 0
    assert result["ambiguous_citation_count"] == 1
    ambiguous = result["ambiguous_citations"][0]
    assert len(ambiguous["candidate_source_pages"]) == 2


def test_full_filename_with_duplicate_chunks_binds_without_chunk_level_ambiguity():
    result = bind_source_comparison_relied_evidence_keys(
        answer=(
            "Rehab Referral Documentation 2004_2005.pdf, p.12 records "
            "the agreed therapeutic return."
        ),
        sources=[
            _source("Rehab Referral Documentation 2004_2005.pdf", 12, "rehab-12-a"),
            _source("Rehab Referral Documentation 2004_2005.pdf", 12, "rehab-12-b"),
            _source("Rehab Referral Documentation 2004_2005.pdf", 13, "rehab-13-a"),
        ],
    )

    assert result["citation_binding_complete"] is True
    assert result["bound_citation_count"] == 1
    assert result["ambiguous_citation_count"] == 0
    assert result["relied_evidence_keys"] == ["rehab-12-a", "rehab-12-b"]


def test_page_range_with_multiple_chunks_per_page_binds_each_coordinate():
    result = bind_source_comparison_relied_evidence_keys(
        answer="Rehab Referral Documentation 2004_2005.pdf, pp.12-13.",
        sources=[
            _source("Rehab Referral Documentation 2004_2005.pdf", 12, "rehab-12-a"),
            _source("Rehab Referral Documentation 2004_2005.pdf", 12, "rehab-12-b"),
            _source("Rehab Referral Documentation 2004_2005.pdf", 13, "rehab-13-a"),
            _source("Rehab Referral Documentation 2004_2005.pdf", 13, "rehab-13-b"),
        ],
    )

    assert result["explicit_citation_count"] == 2
    assert result["bound_citation_count"] == 2
    assert result["canonical_source_page_count"] == 2
    assert result["ambiguous_citation_count"] == 0
    assert result["citation_binding_complete"] is True
    assert result["relied_evidence_keys"] == [
        "rehab-12-a",
        "rehab-12-b",
        "rehab-13-a",
        "rehab-13-b",
    ]


def test_repeated_same_coordinate_counts_each_explicit_citation_but_one_page_identity():
    result = bind_source_comparison_relied_evidence_keys(
        answer=(
            "Appendix E1, p.1 supports transmission. "
            "The same point is qualified by Appendix E1, p.1."
        ),
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-a",
            ),
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-b",
            ),
        ],
    )

    assert result["explicit_citation_count"] == 2
    assert result["bound_citation_count"] == 2
    assert result["canonical_source_page_count"] == 1
    assert result["citation_binding_complete"] is True
    assert result["relied_evidence_keys"] == ["e1-a", "e1-b"]


def test_missing_page_remains_unmatched_and_fail_closed():
    result = bind_source_comparison_relied_evidence_keys(
        answer="Appendix E1, p.99.",
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-a",
            )
        ],
    )

    assert result["citation_binding_complete"] is False
    assert result["bound_citation_count"] == 0
    assert result["unmatched_citation_count"] == 1
    assert result["ambiguous_citation_count"] == 0
