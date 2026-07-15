"""Tests for the source-retrieval tools exposed to the AgentScope Toolkit.

These are the "progressive disclosure" trio:
- list_source_documents
- search_source_documents
- expand_source_chunk

We test each tool's payload shape and ownership handling. Indexing is driven
through :func:`source_indexer.run_indexing` so we hit the real embedding
path (offline hash fallback) end-to-end.
"""
from __future__ import annotations

import json
import sqlite3

import pytest


@pytest.fixture
def two_projects_with_docs(tmp_path, monkeypatch):
    """Boot the app, seed 2 projects — one with a doc, one empty."""
    from fastapi.testclient import TestClient

    from app.db import DB_PATH
    from app.main import app
    from app.services import source_indexer

    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")

    with TestClient(app):
        pass  # lifespan runs migrations

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("INSERT INTO users (phone, nickname) VALUES ('u1', 'alice')")
        conn.execute(
            "INSERT INTO projects (user_id, title, type) VALUES (1, 'P_own', 'script')"
        )
        conn.execute(
            "INSERT INTO projects (user_id, title, type) VALUES (1, 'P_other', 'script')"
        )
        conn.commit()
    finally:
        conn.close()

    import asyncio
    text = "。".join(
        f"侦探在雨夜的巷弄里追踪嫌疑人的第 {i} 次尝试" for i in range(10)
    ) + "。"
    sid = asyncio.run(source_indexer.create_source(
        project_id=1, filename="ref.txt", mime="text/plain",
        file_bytes=text.encode("utf-8"),
    ))
    asyncio.run(source_indexer.run_indexing(sid))
    return {"own_pid": 1, "other_pid": 2, "source_id": sid}


async def _call(fn, **kw) -> dict:
    resp = await fn(**kw)
    return json.loads(resp.content[0].text)


@pytest.mark.asyncio
async def test_list_source_documents_returns_summary(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["own_pid"])
    out = await _call(tools["list_source_documents"])
    assert "sources" in out
    assert len(out["sources"]) == 1
    entry = out["sources"][0]
    assert entry["filename"] == "ref.txt"
    assert entry["status"] == "done"
    assert entry["chunks"] >= 1
    assert entry["summary"]  # non-empty
    # Must NOT leak file path or created_at (trim schema)
    assert "file_path" not in entry
    assert "created_at" not in entry


@pytest.mark.asyncio
async def test_list_source_documents_empty_project(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["other_pid"])
    out = await _call(tools["list_source_documents"])
    assert out == {"sources": []}


@pytest.mark.asyncio
async def test_search_source_documents_returns_hits(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["own_pid"])
    out = await _call(tools["search_source_documents"], query="雨夜 追踪", k=3)
    assert out["hits"]
    for h in out["hits"]:
        assert "chunk_id" in h and "preview" in h and "score" in h


@pytest.mark.asyncio
async def test_search_clamps_k(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["own_pid"])
    out = await _call(tools["search_source_documents"], query="嫌疑人", k=999)
    # Even a huge k should still return <=10
    assert len(out["hits"]) <= 10


@pytest.mark.asyncio
async def test_expand_source_chunk_returns_full_text(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["own_pid"])
    hits = (await _call(
        tools["search_source_documents"], query="侦探", k=1,
    ))["hits"]
    chunk_id = hits[0]["chunk_id"]

    out = await _call(tools["expand_source_chunk"], chunk_id=chunk_id, ctx=1)
    assert out["ok"] is True
    assert out["chunk_id"] == chunk_id
    assert out["content"]
    assert "context" in out
    assert out["filename"] == "ref.txt"


@pytest.mark.asyncio
async def test_expand_source_chunk_denies_cross_project(two_projects_with_docs):
    """A chunk owned by project 1 must not be readable via project 2's toolkit."""
    from app.agents.team import make_tools

    # Ask via own_pid to obtain a chunk id first
    own_tools = make_tools(two_projects_with_docs["own_pid"])
    hits = (await _call(
        own_tools["search_source_documents"], query="侦探", k=1,
    ))["hits"]
    chunk_id = hits[0]["chunk_id"]

    # Now try via the other project's tools — must be refused
    other_tools = make_tools(two_projects_with_docs["other_pid"])
    out = await _call(other_tools["expand_source_chunk"], chunk_id=chunk_id, ctx=0)
    assert out["ok"] is False
    assert "not in this project" in out["error"]


@pytest.mark.asyncio
async def test_expand_source_chunk_missing_id(two_projects_with_docs):
    from app.agents.team import make_tools
    tools = make_tools(two_projects_with_docs["own_pid"])
    out = await _call(tools["expand_source_chunk"], chunk_id=99_999_999, ctx=0)
    assert out["ok"] is False
    assert "not found" in out["error"]
