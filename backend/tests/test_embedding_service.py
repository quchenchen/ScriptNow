"""Unit tests for :mod:`app.services.embedding_service`.

We only exercise the *offline* code paths (hash-based pseudo-embedding). The
DashScope network path is behind an env var check and out of scope for CI.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import embedding_service as es


@pytest.mark.asyncio
async def test_embed_batch_returns_normalized_vectors(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    vecs = await es.embed_batch(["主人公在旧金山的故事", "另一段完全无关的文字"])
    assert len(vecs) == 2
    for v in vecs:
        assert v.dtype == np.float32
        assert v.shape == (es.DEFAULT_DIM,)
        # hash-embed normalises to unit length (or zero for empty text)
        assert abs(np.linalg.norm(v) - 1.0) < 1e-3


@pytest.mark.asyncio
async def test_embed_query_matches_own_text_more_than_unrelated(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    a = await es.embed_query("侦探在雨夜追踪嫌疑人")
    b = await es.embed_query("侦探在雨夜追踪嫌疑人的踪迹")
    c = await es.embed_query("完全不相关的科幻星际飞船设定")
    self_sim = es.cosine(a, b)
    other_sim = es.cosine(a, c)
    assert self_sim > other_sim


def test_bytes_roundtrip_preserves_vector():
    v = np.array([0.1, -0.2, 0.3], dtype=np.float32)
    raw = es.to_bytes(v)
    back = es.from_bytes(raw)
    assert np.allclose(v, back)


def test_from_bytes_handles_none():
    v = es.from_bytes(None)
    assert v.shape == (es.DEFAULT_DIM,)
    assert v.sum() == 0.0


@pytest.mark.asyncio
async def test_embed_batch_empty_input(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    assert await es.embed_batch([]) == []
