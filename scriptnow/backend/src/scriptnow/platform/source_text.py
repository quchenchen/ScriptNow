import io
from html.parser import HTMLParser

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def _extract_pdf_text(content: bytes, strict: bool = True) -> str:
    reader = PdfReader(io.BytesIO(content), strict=strict)
    # Best effort: if encrypted file is not provided with a password,
    # avoid exposing internal parser details and fallback to 400-level handling.
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise PdfReadError("encrypted pdf cannot be read without a password")
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if value := data.strip():
            self.parts.append(value)


def extract_source_text(content: bytes, media_type: str) -> str:
    if media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(content.decode("utf-8", errors="replace"))
        return " ".join(parser.parts)
    if media_type.startswith("text/"):
        return content.decode("utf-8", errors="replace").strip()
    if media_type == "application/pdf":
        try:
            return _extract_pdf_text(content, strict=True)
        except PdfReadError:
            # Some exported PDF objects are tolerant to non-strict parsing and can
            # still extract usable content in permissive mode.
            return _extract_pdf_text(content, strict=False)
    if media_type.endswith("wordprocessingml.document"):
        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    return ""
