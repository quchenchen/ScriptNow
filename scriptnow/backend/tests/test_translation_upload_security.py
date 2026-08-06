from __future__ import annotations

import pytest
from fastapi import HTTPException

from scriptnow.translation.api import (
    _detect_extension,
    _extract_uploaded_text,
    _validate_upload_filename,
)


def test_validate_upload_filename_rejects_path_traversal() -> None:
    for filename in (None, "", " ../evil.txt", "..", "safe/ok.txt", "safe\\ok.txt", "a.."):
        with pytest.raises(HTTPException):
            _validate_upload_filename(filename)


def test_validate_upload_filename_accepts_safe_name() -> None:
    assert _validate_upload_filename("故事提纲.docx") == "故事提纲.docx"


def test_detect_extension_supports_known_suffixes() -> None:
    assert _detect_extension("doc.txt", None) == ".txt"
    assert _detect_extension("doc.pdf", "application/octet-stream") == ".pdf"
    assert _detect_extension("doc.docx", "") == ".docx"
    assert _detect_extension("doc", "text/plain") == ".txt"


def test_detect_extension_rejects_unsupported_type() -> None:
    with pytest.raises(HTTPException):
        _detect_extension("file.exe", None)
    with pytest.raises(HTTPException):
        _detect_extension("file.bin", "application/zip")


def test_extract_uploaded_text_txt() -> None:
    assert _extract_uploaded_text(b"hello world", ".txt", "story.txt") == "hello world"


def test_extract_uploaded_text_empty() -> None:
    with pytest.raises(HTTPException):
        _extract_uploaded_text(b"", ".txt", "story.txt")
