from __future__ import annotations

from dataclasses import replace
import hashlib
from types import SimpleNamespace

from PIL import Image
import pytest

from derived_transcription import photo_ocr
from derived_transcription.models import (
    DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
    PHOTO_IMAGE_SELECTION_ID,
    PHOTO_OCR_LANGUAGE,
    PHOTO_OCR_PREPROCESSING_STEPS,
    PHOTO_OCR_PROFILE_ID,
    PHOTO_OCR_PROFILE_SCHEMA_VERSION,
    PHOTO_OCR_PSM,
    DerivedTranscriptionRecord,
)
from derived_transcription.photo_ocr import (
    PhotoOcrError,
    PhotoOcrResult,
    transcribe_embedded_photo_page,
)
from derived_transcription.serialization import (
    derive_record_id,
    dumps_record,
    loads_record,
)
from derived_transcription.service import (
    DerivedTranscriptionServiceError,
    create_photo_derived_transcription,
)
from derived_transcription.store import (
    DerivedTranscriptionStore,
)
from derived_transcription.validation import (
    validate_derived_transcription_record,
)
from source_evidence.models import EXTRACTION_PROFILE_ID


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
SNAPSHOT_ID = "sha256:" + ("3" * 64)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record() -> DerivedTranscriptionRecord:
    embedded = b"embedded-image"
    transcription = b"Arshad Shafi\nNabila Shafi\n"

    provisional = DerivedTranscriptionRecord(
        schema_version=(
            DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION
        ),
        record_id="sha256:" + ("0" * 64),
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        original_filename="certificate.pdf",
        original_blob_sha256=_sha(b"original-pdf"),
        original_byte_length=len(b"original-pdf"),
        page_number=1,
        source_extraction_method="page_ocr",
        source_page_text_sha256=_sha(b""),
        source_page_text_byte_length=0,
        profile_id=PHOTO_OCR_PROFILE_ID,
        profile_schema_version=(
            PHOTO_OCR_PROFILE_SCHEMA_VERSION
        ),
        image_selection_id=PHOTO_IMAGE_SELECTION_ID,
        embedded_image_name="Image5.jpg",
        embedded_image_sha256=_sha(embedded),
        embedded_image_byte_length=len(embedded),
        embedded_image_width=1127,
        embedded_image_height=1562,
        preprocessing_steps=(
            PHOTO_OCR_PREPROCESSING_STEPS
        ),
        ocr_language=PHOTO_OCR_LANGUAGE,
        ocr_psm=PHOTO_OCR_PSM,
        pypdf_package_version="6.0.0",
        pillow_package_version="11.0.0",
        pytesseract_package_version="0.3.13",
        tesseract_command=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        tesseract_executable_sha256="4" * 64,
        tesseract_engine_version="5.5.3",
        transcription_sha256=_sha(transcription),
        transcription_byte_length=len(transcription),
    )

    return replace(
        provisional,
        record_id=derive_record_id(
            provisional
        ),
    )


def test_record_identity_serialization_round_trip() -> None:
    value = _record()

    validate_derived_transcription_record(
        value
    )

    encoded = dumps_record(
        value
    )

    decoded = loads_record(
        encoded
    )

    assert decoded == value
    assert derive_record_id(decoded) == value.record_id


def test_record_identity_rejects_mutated_payload() -> None:
    value = _record()

    altered = replace(
        value,
        embedded_image_width=1128,
    )

    with pytest.raises(
        ValueError,
        match="record_id",
    ):
        validate_derived_transcription_record(
            altered
        )


def test_store_requires_explicit_root() -> None:
    with pytest.raises(TypeError):
        DerivedTranscriptionStore()  # type: ignore[call-arg]


def test_store_round_trips_record_and_blobs(
    tmp_path,
) -> None:
    store = DerivedTranscriptionStore(
        tmp_path / "derived"
    )

    value = _record()

    embedded = b"embedded-image"
    transcription = b"Arshad Shafi\nNabila Shafi\n"

    assert store.put_blob(embedded) == value.embedded_image_sha256
    assert store.put_blob(transcription) == value.transcription_sha256

    store.publish_record(value)
    store.publish_record(value)

    loaded = store.load_record(
        case_id=value.case_id,
        source_document_instance_id=(
            value.source_document_instance_id
        ),
        page_number=value.page_number,
        record_id=value.record_id,
    )

    assert loaded == value

    assert store.list_page_records(
        case_id=value.case_id,
        source_document_instance_id=(
            value.source_document_instance_id
        ),
        page_number=1,
    ) == (value,)

    assert (
        store.read_embedded_image(value)
        == embedded
    )

    assert (
        store.read_transcription(value)
        == transcription.decode("utf-8")
    )


def _install_fake_reader(
    monkeypatch,
    *,
    image_count: int,
) -> None:
    images = tuple(
        SimpleNamespace(
            name=f"Image{index}.jpg",
            data=f"image-{index}".encode("ascii"),
            image=Image.new(
                "RGB",
                (1127, 1562),
                "white",
            ),
        )
        for index in range(
            image_count
        )
    )

    reader = SimpleNamespace(
        pages=(
            SimpleNamespace(
                images=images
            ),
        )
    )

    monkeypatch.setattr(
        photo_ocr,
        "PdfReader",
        lambda source: reader,
    )


def _install_fake_runtime(
    monkeypatch,
    *,
    text: str,
) -> dict[str, str]:
    seen: dict[str, str] = {}

    monkeypatch.setattr(
        photo_ocr,
        "_package_version",
        lambda package_name: {
            "pypdf": "6.0.0",
            "Pillow": "11.0.0",
            "pytesseract": "0.3.13",
        }[package_name],
    )

    monkeypatch.setattr(
        photo_ocr,
        "_tesseract_executable_identity",
        lambda command: (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            "5" * 64,
        ),
    )

    monkeypatch.setattr(
        photo_ocr.pytesseract,
        "get_tesseract_version",
        lambda: "5.5.3",
    )

    def fake_image_to_string(
        image,
        *,
        lang,
        config,
    ):
        seen["lang"] = lang
        seen["config"] = config
        seen["mode"] = image.mode
        seen["size"] = str(image.size)
        return text

    monkeypatch.setattr(
        photo_ocr.pytesseract,
        "image_to_string",
        fake_image_to_string,
    )

    return seen


def test_photo_ocr_uses_exact_single_embedded_image_profile(
    monkeypatch,
) -> None:
    _install_fake_reader(
        monkeypatch,
        image_count=1,
    )

    seen = _install_fake_runtime(
        monkeypatch,
        text="Government of the Punjab Pakistan\nArshad Shafi\n",
    )

    result = transcribe_embedded_photo_page(
        b"%PDF-fake",
        page_number=1,
    )

    assert result.embedded_image_name == "Image0.jpg"
    assert result.embedded_image_bytes == b"image-0"
    assert result.embedded_image_width == 1127
    assert result.embedded_image_height == 1562

    assert seen["lang"] == "eng"
    assert seen["config"] == "--psm 6"
    assert seen["mode"] == "L"

    assert (
        result.transcription_sha256
        == _sha(
            result.transcription_text.encode(
                "utf-8"
            )
        )
    )


@pytest.mark.parametrize(
    "image_count",
    [0, 2],
)
def test_photo_ocr_fails_closed_without_exactly_one_image(
    monkeypatch,
    image_count: int,
) -> None:
    _install_fake_reader(
        monkeypatch,
        image_count=image_count,
    )

    with pytest.raises(
        PhotoOcrError,
        match="exactly one embedded image",
    ):
        transcribe_embedded_photo_page(
            b"%PDF-fake",
            page_number=1,
        )


def test_photo_ocr_fails_closed_on_empty_text(
    monkeypatch,
) -> None:
    _install_fake_reader(
        monkeypatch,
        image_count=1,
    )

    _install_fake_runtime(
        monkeypatch,
        text=" \n\t",
    )

    with pytest.raises(
        PhotoOcrError,
        match="no usable text",
    ):
        transcribe_embedded_photo_page(
            b"%PDF-fake",
            page_number=1,
        )


class _FakeSourceStore:
    def __init__(
        self,
        *,
        manifest,
        blobs,
    ) -> None:
        self._manifest = manifest
        self._blobs = blobs

    def load_document_manifest(
        self,
        case_id,
        source_document_instance_id,
    ):
        assert case_id == CASE_ID
        assert source_document_instance_id == DOCUMENT_ID
        return self._manifest

    def read_blob(
        self,
        digest,
    ):
        return self._blobs[digest]


def _source_fixture():
    original = b"exact-original-pdf"
    page_text = b""

    original_sha = _sha(
        original
    )

    page_sha = _sha(
        page_text
    )

    page = SimpleNamespace(
        page_number=1,
        extraction_method=SimpleNamespace(
            value="page_ocr"
        ),
        page_text_sha256=page_sha,
        page_text_byte_length=len(
            page_text
        ),
        chunk_snapshots=(),
    )

    manifest = SimpleNamespace(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        original_filename="nadra.pdf",
        original_blob_sha256=original_sha,
        original_byte_length=len(
            original
        ),
        extraction_profile=SimpleNamespace(
            profile_id=EXTRACTION_PROFILE_ID
        ),
        pages=(page,),
    )

    store = _FakeSourceStore(
        manifest=manifest,
        blobs={
            original_sha: original,
            page_sha: page_text,
        },
    )

    return (
        store,
        manifest,
        original_sha,
        page_sha,
    )


def _photo_result() -> PhotoOcrResult:
    embedded = b"exact-embedded-image"

    text = (
        "GOVERNMENT OF THE PUNJAB PAKISTAN\n"
        "Marriage Registration Certificate\n"
        "Arshad Shafi\n"
        "Nabila Shafi\n"
        "12 Aug 2000\n"
    )

    return PhotoOcrResult(
        embedded_image_name="Image5.jpg",
        embedded_image_bytes=embedded,
        embedded_image_sha256=_sha(
            embedded
        ),
        embedded_image_width=1127,
        embedded_image_height=1562,
        transcription_text=text,
        transcription_sha256=_sha(
            text.encode("utf-8")
        ),
        pypdf_package_version="6.0.0",
        pillow_package_version="11.0.0",
        pytesseract_package_version="0.3.13",
        tesseract_command=(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        ),
        tesseract_executable_sha256="6" * 64,
        tesseract_engine_version="5.5.3",
    )


def test_service_publishes_only_to_explicit_derived_store(
    tmp_path,
    monkeypatch,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    result = _photo_result()

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: result,
    )

    derived_store = DerivedTranscriptionStore(
        tmp_path / "derived"
    )

    record = create_photo_derived_transcription(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        page_number=1,
        expected_original_blob_sha256=original_sha,
        expected_source_page_text_sha256=page_sha,
        source_store=source_store,  # type: ignore[arg-type]
        derived_store=derived_store,
        expected_embedded_image_sha256=(
            result.embedded_image_sha256
        ),
    )

    assert record.original_blob_sha256 == original_sha
    assert record.source_page_text_sha256 == page_sha
    assert record.source_page_text_byte_length == 0
    assert record.profile_id == PHOTO_OCR_PROFILE_ID

    assert (
        derived_store.read_transcription(
            record
        )
        == result.transcription_text
    )

    assert (
        derived_store.read_embedded_image(
            record
        )
        == result.embedded_image_bytes
    )

    second = create_photo_derived_transcription(
        case_id=CASE_ID,
        source_document_instance_id=DOCUMENT_ID,
        source_snapshot_id=SNAPSHOT_ID,
        page_number=1,
        expected_original_blob_sha256=original_sha,
        expected_source_page_text_sha256=page_sha,
        source_store=source_store,  # type: ignore[arg-type]
        derived_store=derived_store,
        expected_embedded_image_sha256=(
            result.embedded_image_sha256
        ),
    )

    assert second == record


@pytest.mark.parametrize(
    (
        "override",
        "message",
    ),
    (
        (
            {
                "source_snapshot_id":
                    "sha256:" + ("9" * 64)
            },
            "snapshot",
        ),
        (
            {
                "expected_original_blob_sha256":
                    "8" * 64
            },
            "Original PDF SHA-256",
        ),
        (
            {
                "expected_source_page_text_sha256":
                    "7" * 64
            },
            "page-text SHA-256",
        ),
        (
            {
                "page_number": 2
            },
            "not uniquely present",
        ),
    ),
)
def test_service_fails_closed_on_wrong_source_coordinates(
    tmp_path,
    monkeypatch,
    override,
    message,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: pytest.fail(
            "OCR must not run after a source-coordinate mismatch."
        ),
    )

    kwargs = {
        "case_id": CASE_ID,
        "source_document_instance_id": DOCUMENT_ID,
        "source_snapshot_id": SNAPSHOT_ID,
        "page_number": 1,
        "expected_original_blob_sha256": original_sha,
        "expected_source_page_text_sha256": page_sha,
        "source_store": source_store,
        "derived_store": DerivedTranscriptionStore(
            tmp_path / "derived"
        ),
    }

    kwargs.update(
        override
    )

    with pytest.raises(
        DerivedTranscriptionServiceError,
        match=message,
    ):
        create_photo_derived_transcription(
            **kwargs
        )


def test_service_fails_closed_on_wrong_embedded_image(
    tmp_path,
    monkeypatch,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    result = _photo_result()

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: result,
    )

    with pytest.raises(
        DerivedTranscriptionServiceError,
        match="Embedded image SHA-256",
    ):
        create_photo_derived_transcription(
            case_id=CASE_ID,
            source_document_instance_id=DOCUMENT_ID,
            source_snapshot_id=SNAPSHOT_ID,
            page_number=1,
            expected_original_blob_sha256=original_sha,
            expected_source_page_text_sha256=page_sha,
            source_store=source_store,  # type: ignore[arg-type]
            derived_store=DerivedTranscriptionStore(
                tmp_path / "derived"
            ),
            expected_embedded_image_sha256="7" * 64,
        )


@pytest.mark.parametrize(
    (
        "page_override",
        "message",
    ),
    (
        (
            {
                "extraction_method":
                    SimpleNamespace(value="pypdf_text")
            },
            "page_ocr",
        ),
        (
            {
                "page_text_byte_length": 1
            },
            "zero-byte",
        ),
        (
            {
                "chunk_snapshots":
                    (SimpleNamespace(),)
            },
            "zero searchable chunks",
        ),
    ),
)
def test_service_rejects_source_pages_outside_c1_scope_before_ocr(
    tmp_path,
    monkeypatch,
    page_override,
    message,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    source_page = manifest.pages[0]

    replacement_page = SimpleNamespace(
        page_number=source_page.page_number,
        extraction_method=source_page.extraction_method,
        page_text_sha256=source_page.page_text_sha256,
        page_text_byte_length=source_page.page_text_byte_length,
        chunk_snapshots=source_page.chunk_snapshots,
    )

    for key, value in page_override.items():
        setattr(
            replacement_page,
            key,
            value,
        )

    replacement_manifest = SimpleNamespace(
        case_id=manifest.case_id,
        source_document_instance_id=(
            manifest.source_document_instance_id
        ),
        source_snapshot_id=manifest.source_snapshot_id,
        original_filename=manifest.original_filename,
        original_blob_sha256=manifest.original_blob_sha256,
        original_byte_length=manifest.original_byte_length,
        extraction_profile=manifest.extraction_profile,
        pages=(replacement_page,),
    )

    source_store._manifest = replacement_manifest

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: pytest.fail(
            "OCR must not run outside PHOTO-OCR-C1 source scope."
        ),
    )

    derived_root = tmp_path / "derived"

    with pytest.raises(
        DerivedTranscriptionServiceError,
        match=message,
    ):
        create_photo_derived_transcription(
            case_id=CASE_ID,
            source_document_instance_id=DOCUMENT_ID,
            source_snapshot_id=SNAPSHOT_ID,
            page_number=1,
            expected_original_blob_sha256=original_sha,
            expected_source_page_text_sha256=page_sha,
            source_store=source_store,  # type: ignore[arg-type]
            derived_store=DerivedTranscriptionStore(
                derived_root
            ),
        )

    assert not derived_root.exists()


def test_service_semantic_record_failure_precedes_all_publication(
    tmp_path,
    monkeypatch,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    result = _photo_result()

    invalid_result = replace(
        result,
        embedded_image_width=0,
    )

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: invalid_result,
    )

    derived_root = tmp_path / "derived"

    with pytest.raises(
        ValueError,
        match="embedded_image_width",
    ):
        create_photo_derived_transcription(
            case_id=CASE_ID,
            source_document_instance_id=DOCUMENT_ID,
            source_snapshot_id=SNAPSHOT_ID,
            page_number=1,
            expected_original_blob_sha256=original_sha,
            expected_source_page_text_sha256=page_sha,
            source_store=source_store,  # type: ignore[arg-type]
            derived_store=DerivedTranscriptionStore(
                derived_root
            ),
        )

    assert not derived_root.exists()


def test_service_rejects_inconsistent_embedded_image_hash_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    (
        source_store,
        manifest,
        original_sha,
        page_sha,
    ) = _source_fixture()

    result = _photo_result()

    invalid_result = replace(
        result,
        embedded_image_sha256="9" * 64,
    )

    monkeypatch.setattr(
        "derived_transcription.service.transcribe_embedded_photo_page",
        lambda *args, **kwargs: invalid_result,
    )

    derived_root = tmp_path / "derived"

    with pytest.raises(
        DerivedTranscriptionServiceError,
        match="embedded-image hash",
    ):
        create_photo_derived_transcription(
            case_id=CASE_ID,
            source_document_instance_id=DOCUMENT_ID,
            source_snapshot_id=SNAPSHOT_ID,
            page_number=1,
            expected_original_blob_sha256=original_sha,
            expected_source_page_text_sha256=page_sha,
            source_store=source_store,  # type: ignore[arg-type]
            derived_store=DerivedTranscriptionStore(
                derived_root
            ),
        )

    assert not derived_root.exists()
