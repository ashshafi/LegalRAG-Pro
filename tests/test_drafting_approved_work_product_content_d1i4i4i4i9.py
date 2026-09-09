from __future__ import annotations

import dataclasses
import inspect

import pytest

import drafting_approved_work_product as approved


RENDERER = "drafting-working-draft-markdown-renderer/1.0"
PROFILE = "working-draft-professional-review/1.0"


def _artifact(*statement_texts: str) -> bytes:
    lines = [
        "# LegalRAG Pro - Working Draft Professional Review",
        "",
        "## Reliance status",
        "",
        "Working review.",
        "",
        "## Draft",
        "",
        "Title: Example",
        "",
        "Purpose: Example",
        "",
        "Draft ID: " + "sha256:" + ("a" * 64),
        "",
        "Draft authority: " + "sha256:" + ("b" * 64),
        "",
        "Review authority: " + "sha256:" + ("b" * 64),
        "",
        "## Proposed wording and current authority checks",
        "",
    ]

    for sequence, text in enumerate(statement_texts, start=1):
        lines.extend(
            [
                "### Statement " + str(sequence),
                "",
                text,
                "",
                "Authority check: CAUTION",
                "",
                "Current assessment: partially_supported / medium",
                "",
                "Review reasons:",
                "- Example",
                "",
                "Evidence:",
                "- source-key",
                "",
            ]
        )

    return (
        "\n".join(lines).rstrip() + "\n"
    ).encode("utf-8")


def test_approved_product_exposes_exact_approved_wording_tuple():
    fields = tuple(
        field.name
        for field in dataclasses.fields(
            approved.ApprovedWorkingDraftProduct
        )
    )

    assert "approved_wording" in fields


def test_exact_artifact_parser_extracts_only_statement_wording():
    value = approved._approved_wording_from_artifact(
        artifact_bytes=_artifact(
            "First exact approved statement.",
            "Second exact approved statement.",
        ),
        renderer_version=RENDERER,
        output_profile=PROFILE,
    )

    assert value == (
        "First exact approved statement.",
        "Second exact approved statement.",
    )


def test_exact_artifact_parser_preserves_multiline_statement_text():
    value = approved._approved_wording_from_artifact(
        artifact_bytes=_artifact(
            "Line one.\nLine two.",
        ),
        renderer_version=RENDERER,
        output_profile=PROFILE,
    )

    assert value == (
        "Line one.\nLine two.",
    )


def test_exact_artifact_parser_rejects_missing_wording_section():
    artifact = _artifact(
        "Statement."
    ).replace(
        b"## Proposed wording and current authority checks",
        b"## Something else",
    )

    with pytest.raises(
        approved.DraftingApprovedWorkProductError
    ):
        approved._approved_wording_from_artifact(
            artifact_bytes=artifact,
            renderer_version=RENDERER,
            output_profile=PROFILE,
        )


def test_exact_artifact_parser_rejects_nonsequential_statement_headings():
    artifact = _artifact(
        "First.",
        "Second.",
    ).replace(
        b"### Statement 2",
        b"### Statement 3",
    )

    with pytest.raises(
        approved.DraftingApprovedWorkProductError
    ):
        approved._approved_wording_from_artifact(
            artifact_bytes=artifact,
            renderer_version=RENDERER,
            output_profile=PROFILE,
        )


def test_exact_artifact_parser_does_not_return_governance_metadata():
    value = approved._approved_wording_from_artifact(
        artifact_bytes=_artifact(
            "Exact wording."
        ),
        renderer_version=RENDERER,
        output_profile=PROFILE,
    )

    assert value == ("Exact wording.",)
    assert "CAUTION" not in value[0]
    assert "partially_supported" not in value[0]
    assert "source-key" not in value[0]


def test_loader_uses_existing_immutable_artifact_bytes_and_no_write_path():
    source = inspect.getsource(
        approved.load_approved_working_draft_products
    )

    assert "store.read_artifact(" in source
    assert "_approved_wording_from_artifact(" in source
    assert "approved_wording=" in source

    forbidden = (
        "record_work_product_release(",
        "publish_artifact(",
        "record_working_draft_professional_release(",
        "build_working_draft_professional_review_projection(",
        "prepare_working_draft_professional_review(",
    )

    for token in forbidden:
        assert token not in source


def test_wording_parser_validates_existing_artifact_identity_contract_first():
    source = inspect.getsource(
        approved._approved_wording_from_artifact
    )

    assert "_working_draft_id_from_artifact(" in source