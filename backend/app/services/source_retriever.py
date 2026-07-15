"""Retrieval side of the RAG memory: list / search / expand.

Three tools implement the "progressive disclosure" the PRD calls for:
- :func:`list_sources` — overview: every uploaded doc + short summary
- :func:`search_source` — top-k excerpts (200 char preview + chunk_id)
- :func:`expand_chunk` — full text of one chunk, optionally with N adjacent
  chunks as context

The Agent decides how deep to go — starting from summaries, drilling into
search excerpts, and finally pulling full chunks only when needed.
"""
from __future__ import annotations

import aiosqlite
import numpy as np

from app.db import DB_PATH
from app.services import embedding_service


async def list_sources(project_id: int) -> list[dict]:
    """Return every source doc for a project with metadata + summary."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, filename, mime, total_chars, chunk_count, summary, "
            "status, error, created_at "
            "FROM project_sources WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def search_source(
    project_id: int, query: str, k: int = 5, preview_chars: int = 200,
) -> list[dict]:
    """Return top-k relevant chunks by cosine similarity.

    Each hit is ``{chunk_id, source_id, filename, score, preview, chunk_index}``.
    """
    if not query:
        return []

    qvec = await embedding_service.embed_query(query)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT c.id, c.source_id, c.chunk_index, c.content, c.embedding, "
            "s.filename FROM source_chunks c "
            "JOIN project_sources s ON c.source_id = s.id "
            "WHERE s.project_id = ? AND s.status = 'done'",
            (project_id,),
        )
        rows = await cur.fetchall()

    if not rows:
        return []

    scored: list[tuple[float, dict]] = []
    for r in rows:
        cvec = embedding_service.from_bytes(r["embedding"])
        score = embedding_service.cosine(qvec, cvec)
        preview = (r["content"] or "")[:preview_chars]
        if len(r["content"] or "") > preview_chars:
            preview += "…"
        scored.append((score, {
            "chunk_id": r["id"],
            "source_id": r["source_id"],
            "chunk_index": r["chunk_index"],
            "filename": r["filename"],
            "score": round(score, 4),
            "preview": preview,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [hit for _, hit in scored[:k]]


async def expand_chunk(chunk_id: int, ctx: int = 0) -> dict | None:
    """Return the full text of a chunk, optionally with ``ctx`` neighbors each side.

    ``ctx`` is capped at 3 to avoid dumping a whole document.
    """
    ctx = max(0, min(3, ctx))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, source_id, chunk_index, content FROM source_chunks WHERE id = ?",
            (chunk_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        source_id = row["source_id"]
        idx = row["chunk_index"]

        # Fetch surrounding chunks
        cur = await db.execute(
            "SELECT chunk_index, content FROM source_chunks "
            "WHERE source_id = ? AND chunk_index BETWEEN ? AND ? "
            "ORDER BY chunk_index",
            (source_id, max(0, idx - ctx), idx + ctx),
        )
        neighbors = [dict(r) for r in await cur.fetchall()]

        # Include source metadata for citation
        meta_cur = await db.execute(
            "SELECT filename, chunk_count FROM project_sources WHERE id = ?",
            (source_id,),
        )
        meta = dict(await meta_cur.fetchone() or {})

    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "chunk_index": idx,
        "content": row["content"],
        "context": neighbors,
        "filename": meta.get("filename"),
        "total_chunks_in_source": meta.get("chunk_count"),
    }


async def project_id_for_source(source_id: int) -> int | None:
    """Look up which project a source belongs to (ownership checks)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT project_id FROM project_sources WHERE id = ?", (source_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def project_id_for_chunk(chunk_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT s.project_id FROM source_chunks c "
            "JOIN project_sources s ON c.source_id = s.id "
            "WHERE c.id = ?",
            (chunk_id,),
        )
        row = await cur.fetchone()
    return row[0] if row else None


# Compat: expose a sync-friendly numpy import so mypy is happy
_ = np
