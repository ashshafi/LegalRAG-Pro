from pathlib import Path
from types import SimpleNamespace

import pytest

import drafting_approved_work_product as module
from drafting_working_draft_release_adapter import (
    WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
    WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
)


def _artifact(
    *,
    draft_id: str = (
        "sha256:"
        + ("a" * 64)
    ),
) -> bytes:
    return (
        "# LegalRAG Pro - Working Draft Professional Review\n"
        "\n"
        "## Draft\n"
        "\n"
        "Draft ID: "
        + draft_id
        + "\n"
        "\n"
        "### Statement 1\n"
        "\n"
        "Example wording.\n"
        "\n"
        "Authority check: CAUTION\n"
    ).encode("utf-8")


def test_artifact_parser_is_version_pinned_and_returns_exact_draft_id():
    expected = (
        "sha256:"
        + ("a" * 64)
    )

    actual = module._working_draft_id_from_artifact(
        artifact_bytes=_artifact(
            draft_id=expected
        ),
        renderer_version=
            WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
        output_profile=
            WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
    )

    assert actual == expected


@pytest.mark.parametrize(
    "artifact_bytes",
    (
        b"Draft ID: sha256:" + (b"a" * 64),
        (
            b"Draft ID: sha256:"
            + (b"a" * 64)
            + b"\nDraft ID: sha256:"
            + (b"b" * 64)
            + b"\n### Statement 1\nAuthority check: CAUTION\n"
        ),
        (
            b"Draft ID: not-a-hash\n"
            b"### Statement 1\n"
            b"Authority check: CAUTION\n"
        ),
        (
            b"Draft ID: sha256:"
            + (b"a" * 64)
            + b"\n### Statement 1\n"
        ),
    ),
)
def test_artifact_parser_fails_closed_for_invalid_structure(
    artifact_bytes,
):
    with pytest.raises(
        module.DraftingApprovedWorkProductError
    ):
        module._working_draft_id_from_artifact(
            artifact_bytes=artifact_bytes,
            renderer_version=
                WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
            output_profile=
                WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
        )


def test_artifact_parser_rejects_wrong_renderer_or_profile():
    with pytest.raises(
        module.DraftingApprovedWorkProductError
    ):
        module._working_draft_id_from_artifact(
            artifact_bytes=_artifact(),
            renderer_version="other-renderer/1.0",
            output_profile=
                WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
        )

    with pytest.raises(
        module.DraftingApprovedWorkProductError
    ):
        module._working_draft_id_from_artifact(
            artifact_bytes=_artifact(),
            renderer_version=
                WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
            output_profile="other-profile/1.0",
        )


def test_target_reconstruction_uses_only_immutable_binding_fields():
    binding = SimpleNamespace(
        case_id="case-1",
        target_id="sha256:" + ("1" * 64),
        report_projection_id=
            "00000000-0000-0000-0000-000000000001",
        projection_payload_sha256=
            "2" * 64,
        manifest_id=
            "00000000-0000-0000-0000-000000000002",
        artifact_format="markdown",
        artifact_id=
            "00000000-0000-0000-0000-000000000003",
        artifact_sha256=
            "3" * 64,
        renderer_version=
            WORKING_DRAFT_MARKDOWN_RENDERER_VERSION,
        output_profile=
            WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE,
    )

    target = module._release_target_from_binding(
        binding
    )

    assert target.case_id == binding.case_id
    assert target.target_id == binding.target_id
    assert target.artifact_sha256 == binding.artifact_sha256
    assert target.output_profile == binding.output_profile


def test_read_model_architecture_is_read_only_and_has_no_current_authority():
    source = Path(
        "src/drafting_approved_work_product.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    forbidden = (
        "record_work_product_release(",
        "publish_artifact(",
        "record_working_draft(",
        "load_active_governed_analytical_authority",
        "openai",
        "chromadb",
        "streamlit",
    )

    for token in forbidden:
        assert token not in source

    assert "load_work_product_release_events(" in source
    assert "project_work_product_release(" in source
    assert "store.load_binding(" in source
    assert "store.read_artifact(" in source