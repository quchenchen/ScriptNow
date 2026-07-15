"""Source indexing pipeline: save upload → parse → chunk → embed → persist.

The upload endpoint returns immediately after the DB row is created. Actual
parse+embed is run in a background task via :func:`run_indexing` so a slow
PDF doesn't block the HTTP request.

The pipeline is idempotent — running it twice on the same source_id will
wipe existing chunks and rebuild.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import aiosqlite

from app.db import DB_PATH
from app.services import embedding_service
from app.services.chunker import chunk_text
from app.services.document_parser import parse

log = logging.getLogger(__name__)

# Where uploaded files land. Relative to the backend package so the tests
# can override via app.db config if needed.
UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


def upload_path(project_id: int, source_id: int, filename: str) -> Path:
    """Compute the on-disk path for a stored source file."""
    d = UPLOAD_ROOT / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    # Prefix with source_id to make removal + de-dup safe
    safe_name = re.sub(r"[^\w.\-]+", "_", filename)
    return d / f"{source_id}_{safe_name}"


async def create_source(
    project_id: int,
    filename: str,
    mime: str,
    file_bytes: bytes,
) -> int:
    """Persist file to disk + insert a ``project_sources`` row (pending status).

    Returns the new source_id. Actual indexing is triggered via
    :func:`run_indexing` — usually as a background task.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO project_sources (project_id, filename, mime, size_bytes, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (project_id, filename, mime, len(file_bytes)),
        )
        source_id = cur.lastrowid

        # Save to disk after we have the id (path needs it)
        path = upload_path(project_id, source_id, filename)
        path.write_bytes(file_bytes)

        await db.execute(
            "UPDATE project_sources SET file_path = ? WHERE id = ?",
            (str(path.relative_to(path.parent.parent.parent)), source_id),
        )
        await db.commit()

    return source_id


async def _set_status(source_id: int, status: str, error: str = "") -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE project_sources SET status = ?, error = ? WHERE id = ?",
            (status, error, source_id),
        )
        await db.commit()


def _generate_summary(text: str, max_chars: int = 400) -> str:
    """Simple heuristic summary: first paragraph, capped.

    LLM-based summary lands in a follow-up slice — this keeps the indexing
    pipeline fully offline for the first pass.
    """
    if not text:
        return ""
    # Grab the first substantial paragraph
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return ""
    head = " ".join(paragraphs[:3])
    if len(head) <= max_chars:
        return head
    return head[:max_chars].rstrip() + "…"


async def run_indexing(source_id: int) -> dict:
    """Run parse → chunk → embed → save for one source. Idempotent."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM project_sources WHERE id = ?", (source_id,)
        )).fetchone()
        if not row:
            return {"ok": False, "error": "source not found"}
        source = dict(row)

    file_path = UPLOAD_ROOT.parent / source["file_path"] if source["file_path"] else None
    if not file_path or not file_path.exists():
        # file_path stored relative to backend/; walk up to find it
        file_path = Path(__file__).resolve().parent.parent.parent / source["file_path"]
    if not file_path.exists():
        await _set_status(source_id, "failed", f"file not found: {file_path}")
        return {"ok": False, "error": "file missing"}

    # Wipe old chunks so re-index is clean
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM source_chunks WHERE source_id = ?", (source_id,))
        await db.commit()

    # Parse
    await _set_status(source_id, "parsing")
    try:
        text = parse(file_path)
    except Exception as e:
        await _set_status(source_id, "failed", f"parse error: {e}")
        return {"ok": False, "error": str(e)}

    if not text or not text.strip():
        await _set_status(source_id, "failed", "empty document")
        return {"ok": False, "error": "empty document"}

    # Chunk
    chunks = chunk_text(text)
    summary = _generate_summary(text)

    # Embed (batched)
    await _set_status(source_id, "indexing")
    try:
        vecs = await embedding_service.embed_batch([c["content"] for c in chunks])
    except Exception as e:  # pragma: no cover — network path
        log.warning("embedding batch failed, storing null vectors: %s", e)
        vecs = [None] * len(chunks)

    # Persist
    async with aiosqlite.connect(DB_PATH) as db:
        for i, c in enumerate(chunks):
            emb = embedding_service.to_bytes(vecs[i]) if vecs[i] is not None else None
            await db.execute(
                "INSERT INTO source_chunks "
                "(source_id, chunk_index, content, char_start, char_end, embedding) "
                "VALUES (?,?,?,?,?,?)",
                (source_id, i, c["content"], c["char_start"], c["char_end"], emb),
            )
        await db.execute(
            "UPDATE project_sources SET total_chars = ?, chunk_count = ?, "
            "summary = ?, status = 'done', error = '' WHERE id = ?",
            (len(text), len(chunks), summary, source_id),
        )
        await db.commit()

    return {
        "ok": True, "chunk_count": len(chunks),
        "total_chars": len(text), "summary": summary,
    }
