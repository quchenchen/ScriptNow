"""Tests for the agent-side tool functions.

Every tool must:
- Be a real ``async def`` returning ``ToolResponse``
- Actually mutate the DB (or query it) — no fake success
- Refuse cleanly on missing rows / bad args (never crash)

The tool functions are exposed via ``AgentTeam.build_toolkit()``. Tests here
call the underlying implementations directly (bypassing the LLM loop) so we
verify the *tool logic*, not the model integration.
"""
from __future__ import annotations

import json
import sqlite3

import pytest


@pytest.fixture
def prepared_project():
    """Boot the app to run migrations, seed one project, yield project_id."""
    from fastapi.testclient import TestClient

    from app.db import DB_PATH
    from app.main import app

    with TestClient(app):
        pass  # lifespan runs migrations

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "INSERT INTO users (phone, nickname, password_hash) VALUES ('u1', 'alice', 'x:y')"
        )
        conn.execute(
            "INSERT INTO projects (user_id, title, type) VALUES (1, 'TestProject', 'script')"
        )
        conn.commit()
        return 1
    finally:
        conn.close()


async def _call_tool_text(func, **kwargs) -> dict:
    """Run an AgentScope tool function and return the decoded JSON payload."""
    resp = await func(**kwargs)
    # ToolResponse.content is a list of TextBlock; we return the first as JSON
    text = resp.content[0].text
    return json.loads(text)


async def test_save_episode_creates_row(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    tools = make_tools(project_id)

    result = await _call_tool_text(
        tools["save_episode"],
        episode_number=1,
        title="第1集 · 相遇",
        content="【场景1】咖啡馆·白天\n△推门\n小明：你终于来了。",
    )

    assert result["ok"] is True
    assert result["episode_number"] == 1
    assert result["words"] > 0

    # Verify DB
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT episode_number, title, status FROM episodes WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 1
    assert row[1] == "第1集 · 相遇"
    assert row[2] == "done"


async def test_query_characters_returns_list(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project

    # Seed a character
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "INSERT INTO characters (project_id, name, role, personality) "
            "VALUES (?, '小明', 'protagonist', '内敛')",
            (project_id,),
        )
        conn.commit()
    finally:
        conn.close()

    tools = make_tools(project_id)
    result = await _call_tool_text(tools["query_characters"])

    assert result["ok"] is True
    assert len(result["characters"]) == 1
    assert result["characters"][0]["name"] == "小明"


async def test_plant_foreshadow_creates_row(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    tools = make_tools(project_id)

    result = await _call_tool_text(
        tools["plant_foreshadow"],
        title="小明父亲的怀表",
        description="小明父亲留下的怀表，藏着秘密。",
        category="item",
        importance=0.8,
    )

    assert result["ok"] is True
    assert isinstance(result["id"], int)

    # Verify
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT title, category, status FROM foreshadows WHERE id = ?", (result["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row == ("小明父亲的怀表", "item", "planted")


async def test_resolve_foreshadow_updates_status(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project

    # Seed
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status) "
            "VALUES (?, '怀表秘密', '藏着秘密', 'planted')",
            (project_id,),
        )
        conn.commit()
        fid = conn.execute("SELECT id FROM foreshadows LIMIT 1").fetchone()[0]
    finally:
        conn.close()

    tools = make_tools(project_id)
    result = await _call_tool_text(
        tools["resolve_foreshadow"],
        foreshadow_id=fid,
        resolution="第10集揭晓怀表内藏的照片",
    )
    assert result["ok"] is True

    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT status, resolution_text FROM foreshadows WHERE id = ?", (fid,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "resolved"
    assert "第10集" in row[1]


async def test_build_toolkit_registers_all_four_tools(prepared_project):
    """The Toolkit returned from build_toolkit exposes all four expected tools."""
    from app.agents.team import build_toolkit

    project_id = prepared_project
    toolkit = build_toolkit(project_id)

    schemas = await toolkit.get_tool_schemas()
    tool_names = {s["function"]["name"] for s in schemas}
    assert tool_names == {"save_episode", "query_characters", "plant_foreshadow", "resolve_foreshadow"}
