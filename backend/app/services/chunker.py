"""Chunk long text into overlapping windows suitable for RAG.

Strategy: aim for ~``chunk_size`` characters per chunk with ``overlap`` chars
carried into the next chunk, preferring paragraph / sentence boundaries so
the model sees semantically-coherent excerpts.

Returns a list of dicts:
    {"chunk_index": int, "content": str, "char_start": int, "char_end": int}
"""
from __future__ import annotations

import re


_PARA_SEP = re.compile(r"\n\s*\n")


def _split_sentences(text: str) -> list[tuple[int, str]]:
    """Return list of (offset_in_text, sentence) split at Chinese/English terminals."""
    out: list[tuple[int, str]] = []
    if not text:
        return out
    pos = 0
    # Split on 。！？!?\n but keep offsets; use finditer on the delimiter
    last = 0
    for m in re.finditer(r"[。！？!?\n]+", text):
        end = m.end()
        piece = text[last:end]
        if piece.strip():
            out.append((last, piece))
        last = end
        pos = end
    tail = text[last:]
    if tail.strip():
        out.append((last, tail))
    _ = pos  # silence linter
    return out


def chunk_text(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 200,
) -> list[dict]:
    """Split ``text`` into overlapping chunks of ~``chunk_size`` characters.

    Boundaries are preferred at paragraph starts; if paragraphs are too long
    they're further split at sentence terminals. Blank chunks are dropped.
    """
    if not text or not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    sentences = _split_sentences(text)
    chunks: list[dict] = []
    current: list[str] = []
    current_start: int | None = None
    current_len = 0

    def flush() -> None:
        nonlocal current, current_start, current_len
        if not current or current_start is None:
            return
        content = "".join(current).strip()
        if not content:
            current = []
            current_start = None
            current_len = 0
            return
        end = current_start + len("".join(current))
        chunks.append({
            "chunk_index": len(chunks),
            "content": content,
            "char_start": current_start,
            "char_end": end,
        })
        # Carry overlap tail into the next chunk
        if overlap > 0:
            merged = "".join(current)
            tail = merged[-overlap:]
            tail_start = end - len(tail)
            current = [tail]
            current_start = tail_start
            current_len = len(tail)
        else:
            current = []
            current_start = None
            current_len = 0

    for start, sent in sentences:
        if current_start is None:
            current_start = start
        # If adding this sentence would blow past chunk_size and we already
        # have some content, flush first.
        if current_len + len(sent) > chunk_size and current:
            flush()
            if current_start is None:
                current_start = start
        current.append(sent)
        current_len += len(sent)

    flush()

    return chunks
