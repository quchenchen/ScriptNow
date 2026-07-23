import io
from html.parser import HTMLParser

from docx import Document
from pypdf import PdfReader


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
        return "\n".join(parser.parts)
    if media_type.startswith("text/"):
        return content.decode("utf-8", errors="replace").strip()
    if media_type == "application/pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages).strip()
    if media_type.endswith("wordprocessingml.document"):
        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    return ""
