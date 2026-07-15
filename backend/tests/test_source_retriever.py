"""Integration tests for :mod:`app.services.source_retriever`."""
from __future__ import annotations

import aiosqlite
import pytest


async def _seed(monkeypatch, tmp_path, texts: list[str]) -> tuple[int, list[int]]:
    """Insert a user + project + one source per text; run indexing on each."""
    from app import db
    from app.services import source_indexer

    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")

    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute(
            "INSERT INTO users (phone, nickname) VALUES ('u_ret1', 'ret1')"
        )
        uid = cur.lastrowid
        cur = await con.execute(
            "INSERT INTO projects (user_id, title, type, genre) VALUES (?,?,?,?)",
            (uid, "T", "script", "[]"),
        )
        pid = cur.lastrowid
        await con.commit()

    source_ids: list[int] = []
    for i, text in enumerate(texts):
        sid = await source_indexer.create_source(
            project_id=pid, filename=f"doc_{i}.txt", mime="text/plain",
            file_bytes=text.encode("utf-8"),
        )
        await source_indexer.run_indexing(sid)
        source_ids.append(sid)
    return pid, source_ids


@pytest.mark.asyncio
async def test_list_sources_returns_uploaded_docs(monkeypatch, tmp_path, app_client):
    from app.services import source_retriever

    pid, _ = await _seed(monkeypatch, tmp_path, [
        "。".join(f"第 {i} 段" for i in range(6)) + "。",
        "另一份完全不同的资料，讲述海上传说。",
    ])

    listed = await source_retriever.list_sources(pid)
    assert len(listed) == 2
    filenames = {s["filename"] for s in listed}
    assert filenames == {"doc_0.txt", "doc_1.txt"}
    for s in listed:
        assert s["status"] == "done"
        assert s["chunk_count"] >= 1


@pytest.mark.asyncio
async def test_search_returns_top_k_relevant_chunks(monkeypatch, tmp_path, app_client):
    from app.services import source_retriever

    pid, _ = await _seed(monkeypatch, tmp_path, [
        # Doc 1 — 侦探 theme
        "。".join(["侦探在雨夜追踪嫌疑人穿过巷弄" for _ in range(8)]) + "。",
        # Doc 2 — 科幻 theme
        "。".join(["星舰穿越虫洞抵达遥远的殖民地星球" for _ in range(8)]) + "。",
    ])

    hits = await source_retriever.search_source(pid, "侦探追踪嫌疑人", k=3)
    assert hits
    # Top hit should come from doc 1 (侦探 content)
    assert "侦探" in hits[0]["preview"]
    for h in hits:
        assert set(h.keys()) >= {
            "chunk_id", "source_id", "chunk_index", "filename", "score", "preview"
        }


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty(monkeypatch, tmp_path, app_client):
    from app.services import source_retriever
    pid, _ = await _seed(monkeypatch, tmp_path, ["一些文字。"])
    assert await source_retriever.search_source(pid, "", k=3) == []


@pytest.mark.asyncio
async def test_expand_chunk_returns_neighbors(monkeypatch, tmp_path, app_client):
    from app.services import source_retriever

    pid, sids = await _seed(monkeypatch, tmp_path, [
        "。".join(f"内容片段 {i}，反复重复用于生成多个块" * 20 for i in range(6)) + "。",
    ])

    async with aiosqlite.connect(__import__("app.db", fromlist=["DB_PATH"]).DB_PATH) as con:
        con.row_factory = aiosqlite.Row
        chunks = list(await (await con.execute(
            "SELECT id, chunk_index FROM source_chunks WHERE source_id=? ORDER BY chunk_index",
            (sids[0],),
        )).fetchall())

    # Pick a middle chunk so ctx=1 has both neighbours
    target = chunks[len(chunks) // 2]
    result = await source_retriever.expand_chunk(target["id"], ctx=1)

    assert result is not None
    assert result["chunk_id"] == target["id"]
    assert result["chunk_index"] == target["chunk_index"]
    assert len(result["context"]) >= 2  # target + at least 1 neighbour
    assert result["filename"] == "doc_0.txt"


@pytest.mark.asyncio
async def test_expand_chunk_missing_id_returns_none(monkeypatch, tmp_path, app_client):
    from app.services import source_retriever
    result = await source_retriever.expand_chunk(999_999, ctx=1)
    assert result is None
