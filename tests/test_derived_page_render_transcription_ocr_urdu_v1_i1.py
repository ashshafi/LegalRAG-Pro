from __future__ import annotations

from dataclasses import replace
import hashlib
from types import SimpleNamespace

from PIL import Image
import pytest

from derived_page_render_transcription import page_render_ocr
from derived_page_render_transcription.models import (
    DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
    PAGE_RENDER_ARTIFACT_ROLE,
    PAGE_RENDER_OCR_DPI,
    PAGE_RENDER_OCR_LANGUAGE,
    PAGE_RENDER_OCR_PREPROCESSING_STEPS,
    PAGE_RENDER_OCR_PROFILE_ID,
    PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION,
    PAGE_RENDER_OCR_PSM,
    PageRenderTranscriptionRecord,
)
from derived_page_render_transcription.page_render_ocr import (
    PageRenderOcrError,
    PageRenderOcrResult,
    transcribe_rendered_pdf_page,
)
from derived_page_render_transcription.serialization import (
    derive_record_id,
    dumps_record,
    loads_record,
)
from derived_page_render_transcription.service import (
    PageRenderTranscriptionServiceError,
    create_page_render_transcription,
)
from derived_page_render_transcription.store import PageRenderTranscriptionStore
from derived_page_render_transcription.validation import (
    validate_page_render_transcription_record,
)
from source_evidence.models import EXTRACTION_PROFILE_ID


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
SNAPSHOT_ID = "sha256:" + ("3" * 64)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record() -> PageRenderTranscriptionRecord:
    artifact = b"rendered-page-png"
    transcription = "نکاح نامہ\nArshad Shafi\n".encode("utf-8")
    provisional = PageRenderTranscriptionRecord(
        schema_version=DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
        record_id="sha256:" + ("0" * 64),
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        original_filename="certificate.pdf",
        original_blob_sha256=_sha(b"original-pdf"),
        original_byte_length=len(b"original-pdf"),
        page_number=5,
        source_extraction_method="page_ocr",
        source_page_text_sha256=_sha(b"existing-english-ocr"),
        source_page_text_byte_length=len(b"existing-english-ocr"),
        profile_id=PAGE_RENDER_OCR_PROFILE_ID,
        profile_schema_version=PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION,
        artifact_role=PAGE_RENDER_ARTIFACT_ROLE,
        derived_artifact_sha256=_sha(artifact),
        derived_artifact_byte_length=len(artifact),
        derived_artifact_width=1653,
        derived_artifact_height=2339,
        render_dpi=PAGE_RENDER_OCR_DPI,
        preprocessing_steps=PAGE_RENDER_OCR_PREPROCESSING_STEPS,
        ocr_language=PAGE_RENDER_OCR_LANGUAGE,
        ocr_psm=PAGE_RENDER_OCR_PSM,
        pdf2image_package_version="1.17.0",
        pillow_package_version="11.0.0",
        pytesseract_package_version="0.3.13",
        tesseract_command=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        tesseract_executable_sha256="4" * 64,
        tesseract_engine_version="5.5.3",
        poppler_version="25.07.0",
        transcription_sha256=_sha(transcription),
        transcription_byte_length=len(transcription),
    )
    return replace(provisional, record_id=derive_record_id(provisional))


def test_record_identity_serialization_and_validation_round_trip():
    value = _record()
    validate_page_render_transcription_record(value)
    decoded = loads_record(dumps_record(value))
    assert decoded == value
    assert derive_record_id(decoded) == value.record_id


def test_record_identity_changes_for_language_or_artifact():
    value = _record()
    assert derive_record_id(replace(value, ocr_language="urd")) != value.record_id
    assert (
        derive_record_id(
            replace(value, derived_artifact_sha256=_sha(b"different-render"))
        )
        != value.record_id
    )


def test_validation_rejects_photo_semantics_or_wrong_language():
    value = _record()
    with pytest.raises(ValueError, match="artifact_role"):
        validate_page_render_transcription_record(
            replace(value, artifact_role="embedded_image")
        )
    with pytest.raises(ValueError, match="ocr_language"):
        validate_page_render_transcription_record(replace(value, ocr_language="eng"))


def test_store_round_trips_record_artifact_and_transcription(tmp_path):
    store = PageRenderTranscriptionStore(tmp_path / "page-render")
    value = _record()
    artifact = b"rendered-page-png"
    text = "نکاح نامہ\nArshad Shafi\n".encode("utf-8")

    assert store.put_blob(artifact) == value.derived_artifact_sha256
    assert store.put_blob(text) == value.transcription_sha256
    store.publish_record(value)
    store.publish_record(value)

    assert store.list_page_records(
        case_id=value.case_id,
        source_document_instance_id=value.source_document_instance_id,
        page_number=value.page_number,
    ) == (value,)
    assert store.read_derived_artifact(value) == artifact
    assert store.read_transcription(value) == text.decode("utf-8")


def test_page_render_ocr_uses_eng_plus_urd_and_exact_page(monkeypatch):
    runtime = page_render_ocr._OcrRuntime(
        pdf2image_package_version="1.17.0",
        pillow_package_version="11.0.0",
        pytesseract_package_version="0.3.13",
        tesseract_command=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        tesseract_executable_sha256="5" * 64,
        tesseract_engine_version="5.5.3",
        poppler_version="25.07.0",
        installed_languages=("eng", "urd"),
    )
    monkeypatch.setattr(
        page_render_ocr,
        "_discover_runtime",
        lambda **kwargs: runtime,
    )

    seen = {}

    def fake_convert(pdf_bytes, **kwargs):
        seen["first_page"] = kwargs["first_page"]
        seen["last_page"] = kwargs["last_page"]
        seen["dpi"] = kwargs["dpi"]
        return [Image.new("RGB", (1653, 2339), "white")]

    monkeypatch.setattr(page_render_ocr, "convert_from_bytes", fake_convert)

    def fake_ocr(image, *, lang, config):
        seen["lang"] = lang
        seen["config"] = config
        return "نکاح نامہ\nArshad Shafi\n"

    monkeypatch.setattr(page_render_ocr.pytesseract, "image_to_string", fake_ocr)

    result = transcribe_rendered_pdf_page(b"%PDF-fake", page_number=5)

    assert seen == {
        "first_page": 5,
        "last_page": 5,
        "dpi": 200,
        "lang": "eng+urd",
        "config": "--psm 6",
    }
    assert result.derived_artifact_width == 1653
    assert result.derived_artifact_height == 2339
    assert "نکاح" in result.transcription_text
    assert result.derived_artifact_sha256 == _sha(result.derived_artifact_bytes)


def test_runtime_discovery_fails_before_ocr_when_urd_missing(monkeypatch, tmp_path):
    tess = tmp_path / "tesseract.exe"
    info = tmp_path / "pdfinfo.exe"
    tess.write_bytes(b"tess")
    info.write_bytes(b"info")

    monkeypatch.setattr(
        page_render_ocr,
        "_resolve_executable",
        lambda explicit, fallback: str(tess if fallback == "tesseract" else info),
    )

    def fake_run(command):
        if command[-1] == "--version":
            return "tesseract 5.5.3\n"
        if command[-1] == "--list-langs":
            return "List of available languages in x (2):\neng\nosd\n"
        if command[-1] == "-v":
            return "pdfinfo version 25.07.0\n"
        raise AssertionError(command)

    monkeypatch.setattr(page_render_ocr, "_run_text", fake_run)

    with pytest.raises(PageRenderOcrError, match="urd"):
        page_render_ocr._discover_runtime(
            tesseract_cmd=str(tess),
            pdfinfo_cmd=str(info),
        )


class _FakeSourceStore:
    def __init__(self, *, manifest, blobs):
        self._manifest = manifest
        self._blobs = blobs

    def load_document_manifest(self, case_id, source_document_instance_id):
        assert case_id == CASE_ID
        assert source_document_instance_id == DOCUMENT_ID
        return self._manifest

    def read_blob(self, digest):
        return self._blobs[digest]


def _source_fixture():
    original = b"exact-original-pdf"
    page_text = b"existing bad English OCR"
    original_sha = _sha(original)
    page_sha = _sha(page_text)

    page = SimpleNamespace(
        page_number=5,
        extraction_method=SimpleNamespace(value="page_ocr"),
        page_text_sha256=page_sha,
        page_text_byte_length=len(page_text),
        chunk_snapshots=(SimpleNamespace(),),
    )
    manifest = SimpleNamespace(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        original_filename="certificate.pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(original),
        extraction_profile=SimpleNamespace(profile_id=EXTRACTION_PROFILE_ID),
        pages=(page,),
    )
    return (
        _FakeSourceStore(
            manifest=manifest,
            blobs={original_sha: original, page_sha: page_text},
        ),
        original_sha,
        page_sha,
    )


def _ocr_result():
    artifact = b"rendered-page-png"
    text = "نکاح نامہ\nArshad Shafi\n"
    return PageRenderOcrResult(
        derived_artifact_bytes=artifact,
        derived_artifact_sha256=_sha(artifact),
        derived_artifact_width=1653,
        derived_artifact_height=2339,
        transcription_text=text,
        transcription_sha256=_sha(text.encode("utf-8")),
        pdf2image_package_version="1.17.0",
        pillow_package_version="11.0.0",
        pytesseract_package_version="0.3.13",
        tesseract_command=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        tesseract_executable_sha256="6" * 64,
        tesseract_engine_version="5.5.3",
        poppler_version="25.07.0",
    )


def test_service_allows_existing_bad_ocr_and_chunk_but_only_writes_sidecar(
    tmp_path,
    monkeypatch,
):
    source_store, original_sha, page_sha = _source_fixture()
    result = _ocr_result()
    monkeypatch.setattr(
        "derived_page_render_transcription.service.transcribe_rendered_pdf_page",
        lambda *args, **kwargs: result,
    )

    derived_root = tmp_path / "page-render"
    derived_store = PageRenderTranscriptionStore(derived_root)

    record = create_page_render_transcription(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        page_number=5,
        expected_original_blob_sha256=original_sha,
        expected_source_page_text_sha256=page_sha,
        source_store=source_store,
        derived_store=derived_store,
    )

    assert record.source_page_text_byte_length > 0
    assert record.artifact_role == "rendered_pdf_page"
    assert record.ocr_language == "eng+urd"
    assert derived_store.read_derived_artifact(record) == result.derived_artifact_bytes
    assert derived_store.read_transcription(record) == result.transcription_text


def test_service_fails_closed_on_wrong_source_coordinate_before_ocr(
    tmp_path,
    monkeypatch,
):
    source_store, original_sha, page_sha = _source_fixture()

    monkeypatch.setattr(
        "derived_page_render_transcription.service.transcribe_rendered_pdf_page",
        lambda *args, **kwargs: pytest.fail("OCR must not run after coordinate mismatch"),
    )

    with pytest.raises(PageRenderTranscriptionServiceError, match="snapshot"):
        create_page_render_transcription(
            case_id=CASE_ID,
            source_document_instance_id=DOCUMENT_ID,
            source_snapshot_id="sha256:" + ("9" * 64),
            page_number=5,
            expected_original_blob_sha256=original_sha,
            expected_source_page_text_sha256=page_sha,
            source_store=source_store,
            derived_store=PageRenderTranscriptionStore(tmp_path / "page-render"),
        )
