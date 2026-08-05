from __future__ import annotations

import ast
import importlib.metadata as importlib_metadata
import inspect
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence import chunking, extraction
from source_evidence.identity import sha256_text
from source_evidence.models import ExtractionMethod


class _FakePage:
    def __init__(self, value=None, *, error: Exception | None = None):
        self.value = value
        self.error = error

    def extract_text(self):
        if self.error is not None:
            raise self.error
        return self.value


class _FakeReader:
    pages_value = []
    seen_bytes = None

    def __init__(self, stream):
        assert isinstance(stream, BytesIO)
        type(self).seen_bytes = stream.getvalue()
        self.pages = list(type(self).pages_value)


def _patch_package_versions(monkeypatch, **overrides):
    versions = {
        "pypdf": "6.14.2",
        "pdf2image": "1.17.0",
        "pytesseract": "0.3.13",
        "langchain-text-splitters": "1.1.2",
    }
    versions.update(overrides)

    def fake_version(name):
        if name not in versions:
            raise importlib_metadata.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(importlib_metadata, "version", fake_version)
    monkeypatch.setattr(extraction.metadata, "version", fake_version)
    monkeypatch.setattr(chunking.metadata, "version", fake_version)


def test_extract_pdf_pages_preserves_exact_pypdf_text(monkeypatch):
    _FakeReader.pages_value = [_FakePage("  exact text\n")]
    monkeypatch.setattr(extraction, "PdfReader", _FakeReader)
    _patch_package_versions(monkeypatch)

    result = extraction.extract_pdf_pages(b"%PDF-frozen-bytes")

    assert _FakeReader.seen_bytes == b"%PDF-frozen-bytes"
    assert result.pages[0].page_number == 1
    assert result.pages[0].extraction_method is ExtractionMethod.PYPDF_TEXT
    assert result.pages[0].text == "  exact text\n"
    assert result.extraction_profile.pypdf_package_version == "6.14.2"
    assert result.extraction_profile.pdf2image_package_version is None
    assert result.extraction_profile.pytesseract_package_version is None
    assert result.extraction_profile.tesseract_engine_version is None
    assert result.extraction_profile.poppler_version is None


def test_pypdf_exception_falls_back_to_page_ocr(monkeypatch):
    _FakeReader.pages_value = [_FakePage(error=RuntimeError("boom"))]
    monkeypatch.setattr(extraction, "PdfReader", _FakeReader)
    _patch_package_versions(monkeypatch)
    runtime = extraction._OcrRuntime("1.17.0", "0.3.13", "5.5.0", "25.01.0", None, None)
    monkeypatch.setattr(extraction, "_discover_ocr_runtime", lambda: runtime)
    seen = {}

    def fake_ocr(pdf_bytes, page_number, supplied_runtime):
        seen.update(pdf_bytes=pdf_bytes, page_number=page_number, runtime=supplied_runtime)
        return "OCR exact\n"

    monkeypatch.setattr(extraction, "_ocr_page", fake_ocr)
    result = extraction.extract_pdf_pages(b"original")

    assert seen == {"pdf_bytes": b"original", "page_number": 1, "runtime": runtime}
    assert result.pages[0].extraction_method is ExtractionMethod.PAGE_OCR
    assert result.pages[0].text == "OCR exact\n"
    assert result.extraction_profile.pdf2image_package_version == "1.17.0"
    assert result.extraction_profile.pytesseract_package_version == "0.3.13"
    assert result.extraction_profile.tesseract_engine_version == "5.5.0"
    assert result.extraction_profile.poppler_version == "25.01.0"


def test_whitespace_pypdf_text_falls_back_and_empty_ocr_is_preserved(monkeypatch):
    _FakeReader.pages_value = [_FakePage(" \n\t")]
    monkeypatch.setattr(extraction, "PdfReader", _FakeReader)
    _patch_package_versions(monkeypatch)
    runtime = extraction._OcrRuntime("1.17.0", "0.3.13", "5.5.0", "25.01.0", None, None)
    monkeypatch.setattr(extraction, "_discover_ocr_runtime", lambda: runtime)
    monkeypatch.setattr(extraction, "_ocr_page", lambda *_: "   \n")

    result = extraction.extract_pdf_pages(b"original")

    assert result.pages[0].extraction_method is ExtractionMethod.PAGE_OCR
    assert result.pages[0].text == "   \n"


def test_ocr_page_is_page_scoped_and_preserves_exact_return(monkeypatch):
    calls = {}
    image = object()

    def fake_convert(pdf_bytes, **kwargs):
        calls["convert"] = (pdf_bytes, kwargs)
        return [image]

    def fake_image_to_string(got_image, **kwargs):
        calls["ocr"] = (got_image, kwargs)
        return " exact OCR \n"

    monkeypatch.setattr(extraction, "convert_from_bytes", fake_convert)
    monkeypatch.setattr(extraction.pytesseract, "image_to_string", fake_image_to_string)
    old_cmd = extraction.pytesseract.pytesseract.tesseract_cmd
    runtime = extraction._OcrRuntime(
        "1.17.0",
        "0.3.13",
        "5.5.0",
        "25.01.0",
        "/opt/tesseract",
        "/opt/poppler",
    )

    text = extraction._ocr_page(b"PDF-BYTES", 7, runtime)

    assert text == " exact OCR \n"
    assert calls["convert"] == (
        b"PDF-BYTES",
        {
            "dpi": 200,
            "first_page": 7,
            "last_page": 7,
            "poppler_path": "/opt/poppler",
        },
    )
    assert calls["ocr"] == (image, {"lang": "eng", "config": ""})
    assert extraction.pytesseract.pytesseract.tesseract_cmd == old_cmd


def test_ocr_page_requires_exactly_one_rendered_image(monkeypatch):
    monkeypatch.setattr(extraction, "convert_from_bytes", lambda *args, **kwargs: [])
    runtime = extraction._OcrRuntime("1", "1", "1", "1", None, None)
    with pytest.raises(extraction.SourceEvidenceExtractionError):
        extraction._ocr_page(b"PDF", 1, runtime)


def test_ocr_runtime_requires_poppler_version(monkeypatch):
    _patch_package_versions(monkeypatch)
    monkeypatch.setattr(extraction.pytesseract, "get_tesseract_version", lambda: "5.5.0")
    monkeypatch.setattr(extraction, "_discover_poppler_version", lambda _: (_ for _ in ()).throw(
        extraction.SourceEvidenceExtractionError("missing")
    ))
    with pytest.raises(extraction.SourceEvidenceExtractionError):
        extraction._discover_ocr_runtime()


def test_build_chunking_profile_is_frozen(monkeypatch):
    _patch_package_versions(monkeypatch)
    profile = chunking.build_chunking_profile()
    assert profile.library == "langchain-text-splitters"
    assert profile.library_version == "1.1.2"
    assert profile.chunk_size == 1000
    assert profile.chunk_overlap == 200
    assert profile.separators == ("\n\n", "\n", " ", "")
    assert profile.length_function == "len"
    assert profile.is_separator_regex is False


def test_splitter_constructor_freezes_output_affecting_options(monkeypatch):
    _patch_package_versions(monkeypatch)
    seen = {}

    class FakeSplitter:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def split_text(self, text):
            assert text == "  page text  "
            return ["page text"]

    monkeypatch.setattr(chunking, "_splitter_type", lambda: FakeSplitter)
    assert chunking.split_page_text("  page text  ") == ("page text",)
    assert seen == {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", " ", ""],
        "length_function": len,
        "keep_separator": True,
        "add_start_index": False,
        "strip_whitespace": True,
        "is_separator_regex": False,
    }


def test_split_page_text_does_not_preprocess_input(monkeypatch):
    _patch_package_versions(monkeypatch)
    captured = {}

    class FakeSplitter:
        def __init__(self, **kwargs):
            pass

        def split_text(self, text):
            captured["text"] = text
            return [text]

    monkeypatch.setattr(chunking, "_splitter_type", lambda: FakeSplitter)
    source = " \tÅ\r\n exact \n"
    assert chunking.split_page_text(source) == (source,)
    assert captured["text"] == source


def test_actual_governed_splitter_golden_when_pinned_runtime_available():
    try:
        version = importlib_metadata.version("langchain-text-splitters")
    except importlib_metadata.PackageNotFoundError:
        pytest.skip("governed langchain-text-splitters runtime unavailable")
    if version != "1.1.2":
        pytest.skip(f"requires governed 1.1.2 runtime, found {version}")

    text = "A" * 2200
    chunks = chunking.split_page_text(text)
    assert tuple(map(len, chunks)) == (1000, 1000, 600)
    assert chunks == ("A" * 1000, "A" * 1000, "A" * 600)
    assert tuple(sha256_text(value) for value in chunks) == (
        sha256_text("A" * 1000),
        sha256_text("A" * 1000),
        sha256_text("A" * 600),
    )


def test_source_modules_do_not_reopen_pdf_path_or_import_legacy_ocr():
    extraction_source = inspect.getsource(extraction)
    capture_source = Path(inspect.getsourcefile(__import__("source_evidence.capture", fromlist=["*"])) ).read_text()
    assert "convert_from_path" not in extraction_source
    assert "ocr.extract_text" not in extraction_source
    assert "index_documents" not in extraction_source + capture_source
    assert "from src.ocr" not in extraction_source
    assert "import ocr" not in extraction_source
    assert capture_source.count("read_bytes()") == 1

    tree = ast.parse(extraction_source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    pdf_reader_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Name) and node.func.id == "PdfReader"
    ]
    assert len(pdf_reader_calls) == 1
    assert isinstance(pdf_reader_calls[0].args[0], ast.Call)
    assert isinstance(pdf_reader_calls[0].args[0].func, ast.Name)
    assert pdf_reader_calls[0].args[0].func.id == "BytesIO"


def _minimal_text_pdf(text: str = "Hello M3") -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def test_pinned_pypdf_exact_golden_when_governed_runtime_available():
    try:
        version = importlib_metadata.version("pypdf")
    except importlib_metadata.PackageNotFoundError:
        pytest.skip("pypdf runtime unavailable")
    if version != "6.14.2":
        pytest.skip(f"requires governed pypdf 6.14.2 runtime, found {version}")

    result = extraction.extract_pdf_pages(_minimal_text_pdf())
    assert result.pages == (
        extraction.ExtractedPage(
            page_number=1,
            extraction_method=ExtractionMethod.PYPDF_TEXT,
            text="Hello M3",
        ),
    )
    assert sha256_text(result.pages[0].text) == sha256_text("Hello M3")
