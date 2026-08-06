from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from scriptnow.platform.source_text import _extract_pdf_text, extract_source_text


def test_extract_source_text_pdf_uses_flexible_parse(monkeypatch) -> None:
    call_count = 0

    class FakeReader:
        def __init__(self, *_args, strict: bool = True, **_kwargs):
            nonlocal call_count
            call_count += 1
            if strict and call_count == 1:
                raise PdfReadError("strict mode parse failed")

            class _page:
                def extract_text(self) -> str:
                    return "fallback text"

            self.is_encrypted = False
            self.pages = [_page()]

    monkeypatch.setattr("scriptnow.platform.source_text.PdfReader", FakeReader)

    assert extract_source_text(b"%PDF-1.4", "application/pdf") == "fallback text"
    assert call_count == 2


def test_extract_source_text_pdf_raises_for_broken_document() -> None:
    with pytest.raises(PdfReadError):
        _extract_pdf_text(b"not-a-pdf", strict=True)


def test_extract_source_text_unknown_type_returns_empty() -> None:
    assert extract_source_text(b"abc", "application/octet-stream") == ""


def test_html_source_text_extractor_strips_markup() -> None:
    assert (
        extract_source_text(b"<div>hello <b>world</b></div>", "text/html")
        == "hello world"
    )


def test_pdf_binary_roundtrip() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    content = buffer.getvalue()

    assert isinstance(extract_source_text(content, "application/pdf"), str)
