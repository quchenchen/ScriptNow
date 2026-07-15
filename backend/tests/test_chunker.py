"""Unit tests for :mod:`app.services.chunker`.

The chunker is a pure function so all tests are synchronous. We care about:
- Short docs collapse to a single chunk
- Long docs get split near ``chunk_size`` boundaries
- Overlap is honoured
- char_start / char_end are consistent
- Blank input yields ``[]``
"""
from __future__ import annotations

from app.services.chunker import chunk_text


def test_empty_input_yields_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_document_produces_one_chunk():
    text = "第一段。第二段。"
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"].strip() == text.strip()


def test_long_document_splits_into_multiple_chunks():
    # ~10 sentences of ~50 chars each ≈ 500 chars total
    sentences = ["这是一段用于测试分块行为的句子内容，反复重复以生成长文档。" for _ in range(20)]
    text = "。".join(sentences) + "。"
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c["content"]) <= 300  # some slack for boundary sentences


def test_chunks_have_monotonic_indices():
    text = "。".join(["句子" * 30 for _ in range(30)]) + "。"
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


def test_char_bounds_are_ordered():
    text = "。".join(["段落" * 40 for _ in range(20)]) + "。"
    chunks = chunk_text(text, chunk_size=250, overlap=30)
    for c in chunks:
        assert c["char_start"] < c["char_end"]
        assert c["char_end"] <= len(text)


def test_invalid_params_raise():
    import pytest
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, overlap=-1)
