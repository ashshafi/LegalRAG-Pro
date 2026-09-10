from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from marriage_document_live import (
    LiveMarriageCandidateBundle,
    live_marriage_candidate_fingerprint,
    looks_like_marriage_document_filename,
)


def test_marriage_filename_detection_is_conservative():
    assert looks_like_marriage_document_filename(
        "Nikah Nama.pdf"
    )
    assert looks_like_marriage_document_filename(
        "Pakistani marriage certificate.pdf"
    )
    assert not looks_like_marriage_document_filename(
        "bank statement.pdf"
    )


def test_candidate_fingerprint_is_deterministic_and_review_bound():
    def bundle(review: str):
        return LiveMarriageCandidateBundle(
            candidate=SimpleNamespace(
                record_id="sha256:" + "1" * 64,
                case_id="case-a",
                transcription_sha256="2" * 64,
            ),
            review_projection=SimpleNamespace(
                latest_event_id=review
            ),
            binding=SimpleNamespace(
                binding_id="sha256:" + "4" * 64
            ),
            receipt=SimpleNamespace(
                receipt_id="sha256:" + "5" * 64
            ),
            transcription_text="text",
        )

    one = live_marriage_candidate_fingerprint(
        (bundle("sha256:" + "3" * 64),)
    )
    two = live_marriage_candidate_fingerprint(
        (bundle("sha256:" + "3" * 64),)
    )
    changed = live_marriage_candidate_fingerprint(
        (bundle("sha256:" + "6" * 64),)
    )

    assert one == two
    assert one != changed


def test_production_live_route_contains_no_preview_case_facts():
    paths = (
        Path("src/marriage_document_live.py"),
        Path("src/ui/marriage_document_entrypoint.py"),
    )
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths
    )

    for forbidden in (
        "Ward 203",
        "02/10/09",
        "marriage certifacte rosetta.pdf",
        "6fc25ac8d434a68c",
        "70aacfb22b106360",
        "d98763353de53eaf",
        "9e10cd5a-00fd-484e-938d-b5c3358c8dae",
    ):
        assert forbidden not in text


def test_live_core_does_not_open_chroma():
    text = Path(
        "src/marriage_document_live.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "chromadb",
        "persistentclient",
        "get_collection(",
        "collection.query(",
    ):
        assert forbidden not in text


def test_main_app_routes_live_review():
    text = Path("src/app.py").read_text(encoding="utf-8")
    assert (
        "from ui.marriage_document_entrypoint import "
        "show_marriage_document_entrypoint"
    ) in text
    assert (
        'st.session_state.get("mdi_marriage_document_view", False)'
        in text
    )
    assert "show_marriage_document_entrypoint(active_case_id)" in text


def test_sidebar_places_review_inside_document_selection_expander():
    import ast

    text = Path(
        "src/ui/sidebar.py"
    ).read_text(encoding="utf-8-sig")

    tree = ast.parse(text, filename="src/ui/sidebar.py")

    def dotted(node):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With) or len(node.items) != 1:
            continue
        context = node.items[0].context_expr
        if not isinstance(context, ast.Call):
            continue
        if dotted(context.func) != "st.sidebar.expander":
            continue
        block = ast.get_source_segment(text, node) or ""
        if "selected_documents" in block:
            matches.append(block)

    assert len(matches) == 1
    block = matches[0]
    assert '"Nikah Nama review"' in block
    assert (
        'st.session_state["mdi_marriage_document_view"] = True'
        in block
    )


def test_other_sidebar_routes_clear_marriage_review():
    text = Path(
        "src/ui/sidebar.py"
    ).read_text(encoding="utf-8")
    assert text.count(
        'st.session_state["mdi_marriage_document_view"] = False'
    ) >= 8


def test_openai_extraction_has_policy_guard_before_sdk_call():
    text = Path(
        "src/marriage_document_extraction/openai_provider.py"
    ).read_text(encoding="utf-8")

    guard = text.index("assert_ai_processing_allowed(")
    call = text.index("self._client.responses.create(")

    assert guard < call
    assert "AIProcessingPurpose.CONTROLLED_ANALYSIS" in text
    assert "AIDataClassification.PRIVILEGED" in text
    assert "store=False" in text
