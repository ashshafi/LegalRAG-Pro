from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import marriage_document_live as live
from marriage_document_live import (
    LiveMarriageCandidateBundle,
    build_live_marriage_document_workspace,
    discover_optional_native_marriage_source_context,
    live_marriage_candidate_fingerprint,
    live_marriage_review_fingerprint,
)
from marriage_document_source_native import (
    SourceEvidenceNativePage,
)


def _bundle(
    *,
    source_document_instance_id: str = "11111111-1111-4111-8111-111111111111",
    source_snapshot_id: str = "sha256:" + "a" * 64,
    original_blob_sha256: str = "b" * 64,
    record_char: str = "1",
) -> LiveMarriageCandidateBundle:
    return LiveMarriageCandidateBundle(
        candidate=SimpleNamespace(
            record_id="sha256:" + record_char * 64,
            case_id="22222222-2222-4222-8222-222222222222",
            source_document_instance_id=source_document_instance_id,
            source_snapshot_id=source_snapshot_id,
            original_filename="marriage document.pdf",
            original_blob_sha256=original_blob_sha256,
            original_byte_length=12345,
            page_number=5,
            source_page_text_sha256="c" * 64,
            source_page_text_byte_length=0,
            transcription_sha256="d" * 64,
        ),
        review_projection=SimpleNamespace(
            latest_event_id="sha256:" + "e" * 64
        ),
        binding=SimpleNamespace(
            binding_id="sha256:" + "f" * 64
        ),
        receipt=SimpleNamespace(
            receipt_id="sha256:" + "9" * 64
        ),
        transcription_text="approved fragment",
    )


def _native_texts() -> dict[int, str]:
    return {
        2: """
        2. Name of the bridegroom & his father with their respective residence
        Example Groom S/o Example Father Example Address
        4. Name of the bride & her father with their respective residence
        Example Bride D/o Example Father Example Address
        11. Name of the witnesses to the marriage, with residences
        (1) Witness One S/o Parent One Address
        (2) Witness Two S/o Parent Two Address
        12. Date on which the marriage was contracted 12 August 2000 AD
        13. Amount of dower 5,000/- rupees
        """,
        3: """
        Total has been paid at the time of marriage.
        person by whom the marriage was solemnized Example Registrar
        24. Date of Registration of Marriage 12-8-2000
        25. Registration Fee Paid As per the rule
        """,
        4: """
        Signature and seal of marriage registrar
        Nazim Chairman Arbitration Council
        No. 80 Example Hall Example Town City District
        02/10/09
        """,
    }


class _FakeStore:
    def __init__(self, bundle: LiveMarriageCandidateBundle, texts=None):
        self._bundle = bundle
        source_texts = _native_texts() if texts is None else texts
        self._payloads = {}
        pages = []
        for number in (2, 3, 4):
            payload = source_texts[number].encode("utf-8")
            digest = hashlib.sha256(payload).hexdigest()
            self._payloads[digest] = payload
            pages.append(
                SimpleNamespace(
                    page_number=number,
                    page_text_sha256=digest,
                    page_text_byte_length=len(payload),
                    extraction_method=SimpleNamespace(
                        value="pypdf_text"
                    ),
                    chunk_snapshots=(),
                )
            )
        candidate = bundle.candidate
        self.manifest = SimpleNamespace(
            case_id=candidate.case_id,
            source_document_instance_id=
                candidate.source_document_instance_id,
            source_snapshot_id=candidate.source_snapshot_id,
            original_filename=candidate.original_filename,
            original_blob_sha256=candidate.original_blob_sha256,
            original_byte_length=candidate.original_byte_length,
            pages=tuple(pages),
        )

    def load_document_manifest(self, case_id, source_document_instance_id):
        assert case_id == self.manifest.case_id
        assert (
            source_document_instance_id
            == self.manifest.source_document_instance_id
        )
        return self.manifest

    def read_blob(self, sha256_hex):
        return self._payloads[sha256_hex]


def test_structural_native_context_discovery_is_generic_and_source_bound():
    bundle = _bundle()
    store = _FakeStore(bundle)
    context = discover_optional_native_marriage_source_context(
        (bundle,),
        store=store,
    )
    assert context is not None
    assert context.manifest is store.manifest
    assert tuple(
        value.provenance.page_number
        for value in context.pages
    ) == (2, 3, 4)


def test_noneligible_native_structure_falls_back_to_candidate_only():
    bundle = _bundle()
    texts = _native_texts()
    texts[2] = "ordinary PDF text with no supported marriage form labels"
    store = _FakeStore(bundle, texts=texts)
    context = discover_optional_native_marriage_source_context(
        (bundle,),
        store=store,
    )
    assert context is None


def test_composite_review_fingerprint_changes_with_native_page_identity():
    bundle = _bundle()
    store = _FakeStore(bundle)
    context = discover_optional_native_marriage_source_context(
        (bundle,),
        store=store,
    )
    assert context is not None

    candidate_only = live_marriage_candidate_fingerprint((bundle,))
    composite_one = live_marriage_review_fingerprint(
        (bundle,),
        native_context=context,
    )

    first = context.pages[0]
    changed_provenance = replace(
        first.provenance,
        page_text_sha256="8" * 64,
    )
    changed_context = replace(
        context,
        pages=(
            SourceEvidenceNativePage(
                provenance=changed_provenance,
                text=first.text,
            ),
            *context.pages[1:],
        ),
    )
    composite_two = live_marriage_review_fingerprint(
        (bundle,),
        native_context=changed_context,
    )

    assert composite_one != candidate_only
    assert composite_two != composite_one


def test_live_builder_preserves_candidate_only_fallback(monkeypatch):
    bundle = _bundle()
    candidate_workspace = object()

    monkeypatch.setattr(
        live,
        "extract_marriage_document_intelligence",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        live,
        "build_marriage_document_workspace",
        lambda records: candidate_workspace,
    )

    def unexpected_native_bridge(**kwargs):
        raise AssertionError("native bridge must not run")

    monkeypatch.setattr(
        live,
        "build_source_evidence_native_workspace_bridge",
        unexpected_native_bridge,
    )

    result = build_live_marriage_document_workspace(
        bundles=(bundle,),
        provider=object(),
        model="test-model",
        native_context=None,
    )

    assert result is candidate_workspace


def test_live_builder_applies_native_bridge_after_candidate_workspace(
    monkeypatch,
):
    bundle = _bundle()
    store = _FakeStore(bundle)
    context = discover_optional_native_marriage_source_context(
        (bundle,),
        store=store,
    )
    assert context is not None

    candidate_workspace = object()
    final_workspace = object()
    observed = {}

    monkeypatch.setattr(
        live,
        "extract_marriage_document_intelligence",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        live,
        "build_marriage_document_workspace",
        lambda records: candidate_workspace,
    )

    def bridge(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(workspace=final_workspace)

    monkeypatch.setattr(
        live,
        "build_source_evidence_native_workspace_bridge",
        bridge,
    )

    result = build_live_marriage_document_workspace(
        bundles=(bundle,),
        provider=object(),
        model="test-model",
        native_context=context,
    )

    assert result is final_workspace
    assert observed["base_workspace"] is candidate_workspace
    assert observed["store"] is context.store
    assert observed["manifest"] is context.manifest
    assert observed["page_numbers"] == (2, 3, 4)


def test_entrypoint_resolves_native_context_before_cache_fingerprint():
    source = Path(
        "src/ui/marriage_document_entrypoint.py"
    ).read_text(encoding="utf-8")

    discovery = source.index(
        "discover_optional_native_marriage_source_context("
    )
    fingerprint = source.index(
        "fingerprint = live_marriage_review_fingerprint("
    )
    cache_read = source.index(
        "cached_case = st.session_state.get(_CACHE_CASE)"
    )
    build_call = source.index(
        "workspace = build_live_marriage_document_workspace("
    )

    assert discovery < fingerprint < cache_read < build_call
    assert "native_context=native_context" in source
    assert source.count(
        "OpenAIMarriageFactExtractionProvider("
    ) == 1


def test_candidate_production_sources_contain_no_ackers_identity_constants():
    paths = (
        Path("src/marriage_document_source_native.py"),
        Path("src/marriage_document_live.py"),
        Path("src/ui/marriage_document_entrypoint.py"),
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths
    )

    forbidden = (
        "9e10cd5a-00fd-484e-938d-b5c3358c8dae",
        "19027781-f4e4-5965-887e-16a44304f507",
        "eebf8817e96e09ed4dd53908f258d140be420b1307b9eea0465c08593525164b",
        "ff20275786a90f17b37414ee18aea52cd2e615c1ef15c1717de0ca54ee5a7941",
    )
    for value in forbidden:
        assert value not in source
