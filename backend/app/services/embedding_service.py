"""Embedding provider.

Default backend: **DashScope ``text-embedding-v3``** (same API key as chat
models). When ``DASHSCOPE_API_KEY`` is missing we degrade gracefully — chunks
still get indexed (via FTS-like keyword fallback), just without semantic
retrieval quality.

Design decisions:
- Vectors are ``numpy.float32`` arrays, stored as raw bytes in the DB.
- Batches capped at 10 to stay under DashScope's per-request input limit.
- Callers may monkeypatch :func:`embed_batch` in tests to avoid network I/O.
"""
from __future__ import annotations

import os
from typing import Iterable

import numpy as np

# 1024 is DashScope text-embedding-v3's default dimension
DEFAULT_DIM = 1024
BATCH_SIZE = 10


def _dashscope_available() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY"))


def _hash_embed(text: str, dim: int = DEFAULT_DIM) -> np.ndarray:
    """Deterministic hash-based pseudo-embedding used when DashScope key is absent.

    Not a real semantic embedding — but keeps the storage schema consistent
    and allows retrieval to fall back to a keyword-overlap similarity. Tests
    also use this to avoid network I/O.
    """
    # Bag-of-char-ngram vector — cheap, deterministic, gives non-zero overlap
    # between texts that share substrings.
    vec = np.zeros(dim, dtype=np.float32)
    if not text:
        return vec
    for i in range(len(text) - 1):
        gram = text[i:i + 2]
        h = abs(hash(gram)) % dim
        vec[h] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


async def _dashscope_embed(texts: list[str]) -> list[np.ndarray]:
    """Call DashScope text-embedding-v3 for a batch of texts.

    Raises on network / auth failure; the ``embed_batch`` wrapper handles
    the fallback path.
    """
    import dashscope  # type: ignore

    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")
    # DashScope SDK is sync; wrap in a thread so we don't block the loop
    import asyncio

    def _call():
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=texts,
            dimension=DEFAULT_DIM,
        )
        return resp

    resp = await asyncio.to_thread(_call)
    if resp.status_code != 200:
        raise RuntimeError(f"dashscope embedding failed: {resp.message}")
    out: list[np.ndarray] = []
    for item in resp.output["embeddings"]:
        v = np.asarray(item["embedding"], dtype=np.float32)
        n = np.linalg.norm(v)
        if n > 0:
            v = v / n
        out.append(v)
    return out


async def embed_batch(texts: Iterable[str]) -> list[np.ndarray]:
    """Return embeddings for each input text, normalized (L2)."""
    texts_list = list(texts)
    if not texts_list:
        return []

    if _dashscope_available():
        try:
            out: list[np.ndarray] = []
            for i in range(0, len(texts_list), BATCH_SIZE):
                batch = texts_list[i:i + BATCH_SIZE]
                out.extend(await _dashscope_embed(batch))
            return out
        except Exception:  # pragma: no cover — network / auth failures
            # Fall through to hash embed
            pass

    return [_hash_embed(t) for t in texts_list]


async def embed_query(text: str) -> np.ndarray:
    """Embed a single query string."""
    vecs = await embed_batch([text])
    return vecs[0] if vecs else np.zeros(DEFAULT_DIM, dtype=np.float32)


def to_bytes(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(raw: bytes | None) -> np.ndarray:
    if not raw:
        return np.zeros(DEFAULT_DIM, dtype=np.float32)
    return np.frombuffer(raw, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors (assumed already normalized, but robust)."""
    if a.size == 0 or b.size == 0 or a.shape != b.shape:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
