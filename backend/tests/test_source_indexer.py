"""Integration test for :mod:`app.services.source_indexer` end-to-end.

Boots a real SQLite (via alembic in ``app.main`` lifespan) and drives:
    create_source → run_indexing → assert DB state
Files land in an isolated tmp upload root so tests don't pollute the repo.
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_indexing_pipeline_end_to_end(monkeypatch, tmp_path, app_client):
    """A fresh .txt upload gets parsed, chunked, embedded, and marked ``done``."""
    from app import db
    from app.services import source_indexer

    # Redirect the upload dir into pytest's tmp
    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")

    # 1) seed a project row we can attach the source to
    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute(
            "INSERT INTO users (phone, nickname) VALUES ('u_test1', 'test1')"
        )
        uid = cur.lastrowid
        cur = await con.execute(
            "INSERT INTO projects (user_id, title, type, genre) VALUES (?,?,?,?)",
            (uid, "Test", "script", "[]"),
        )
        pid = cur.lastrowid
        await con.commit()

    long_text = "。".join(f"这是第 {i} 段测试内容，用于验证分块" for i in range(30)) + "。"
    src_id = await source_indexer.create_source(
        project_id=pid,
        filename="seed.txt",
        mime="text/plain",
        file_bytes=long_text.encode("utf-8"),
    )
    assert src_id > 0

    result = await source_indexer.run_indexing(src_id)
    assert result["ok"] is True
    assert result["chunk_count"] >= 1

    # DB state — status flipped to done, chunks persisted
    async with aiosqlite.connect(db.DB_PATH) as con:
        con.row_factory = aiosqlite.Row
        row = dict(await (await con.execute(
            "SELECT status, chunk_count, total_chars, summary FROM project_sources WHERE id=?",
            (src_id,),
        )).fetchone())
        chunks = list(await (await con.execute(
            "SELECT id, chunk_index, content, embedding FROM source_chunks "
            "WHERE source_id=? ORDER BY chunk_index",
            (src_id,),
        )).fetchall())

    assert row["status"] == "done"
    assert row["chunk_count"] == len(chunks)
    assert row["total_chars"] > 0
    assert row["summary"]  # not empty
    assert all(c["embedding"] for c in chunks)


@pytest.mark.asyncio
async def test_indexing_marks_failed_on_empty_document(monkeypatch, tmp_path, app_client):
    from app import db
    from app.services import source_indexer

    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")

    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute(
            "INSERT INTO users (phone, nickname) VALUES ('u_test1', 'test1')"
        )
        uid = cur.lastrowid
        cur = await con.execute(
            "INSERT INTO projects (user_id, title, type, genre) VALUES (?,?,?,?)",
            (uid, "T", "script", "[]"),
        )
        pid = cur.lastrowid
        await con.commit()

    src_id = await source_indexer.create_source(
        project_id=pid, filename="empty.txt", mime="text/plain",
        file_bytes=b"   \n\n  ",
    )
    result = await source_indexer.run_indexing(src_id)
    assert result["ok"] is False

    async with aiosqlite.connect(db.DB_PATH) as con:
        status = (await (await con.execute(
            "SELECT status FROM project_sources WHERE id=?", (src_id,),
        )).fetchone())[0]
    assert status == "failed"


@pytest.mark.asyncio
async def test_indexing_is_idempotent(monkeypatch, tmp_path, app_client):
    """Running indexing twice replaces chunks, doesn't duplicate them."""
    from app import db
    from app.services import source_indexer

    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")

    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute("INSERT INTO users (phone, nickname) VALUES ('u_idem', 'idem')")
        uid = cur.lastrowid
        cur = await con.execute(
            "INSERT INTO projects (user_id, title, type, genre) VALUES (?,?,?,?)",
            (uid, "T", "script", "[]"),
        )
        pid = cur.lastrowid
        await con.commit()

    text = "。".join(f"段落 {i}" for i in range(10)) + "。"
    src_id = await source_indexer.create_source(
        project_id=pid, filename="s.txt", mime="text/plain",
        file_bytes=text.encode("utf-8"),
    )
    await source_indexer.run_indexing(src_id)
    await source_indexer.run_indexing(src_id)

    async with aiosqlite.connect(db.DB_PATH) as con:
        n = (await (await con.execute(
            "SELECT COUNT(*) FROM source_chunks WHERE source_id=?", (src_id,),
        )).fetchone())[0]
        recorded = (await (await con.execute(
            "SELECT chunk_count FROM project_sources WHERE id=?", (src_id,),
        )).fetchone())[0]
    assert n == recorded
    assert n > 0
