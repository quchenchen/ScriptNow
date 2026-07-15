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


async def test_update_character_state_persists(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    # Seed a character
    import sqlite3

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO characters (project_id, name, role) VALUES (?, '阿明', 'protagonist')",
            (project_id,),
        )
        char_id = cur.lastrowid
        # And an episode so state_episode fallback works
        conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) VALUES (?, 3, 'done')",
            (project_id,),
        )
        conn.commit()
    finally:
        conn.close()

    tools = make_tools(project_id)
    result = await _call_tool_text(
        tools["update_character_state"],
        character_id=char_id,
        current_state="被通缉",
    )
    assert result["ok"] is True

    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT current_state, state_episode FROM characters WHERE id = ?",
            (char_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "被通缉"
    assert row[1] == 3  # picked up from max(episode_number)


async def test_add_prop_and_mark_used(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    tools = make_tools(project_id)

    result = await _call_tool_text(
        tools["add_prop"],
        name="怀表",
        description="父亲遗物",
        significance="macguffin",
        first_appearance=1,
    )
    assert result["ok"] is True
    prop_id = result["id"]

    result = await _call_tool_text(
        tools["mark_prop_used"], prop_id=prop_id, episode_number=5,
    )
    assert result["ok"] is True

    import sqlite3

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT usage_count, last_appearance FROM props WHERE id = ?", (prop_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 2  # add_prop set to 1, mark_prop_used +1
    assert row[1] == 5


async def test_abandon_foreshadow_via_tool(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    # Seed a planted foreshadow
    import sqlite3

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status) "
            "VALUES (?, 'X', 'x', 'planted')",
            (project_id,),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    tools = make_tools(project_id)
    result = await _call_tool_text(
        tools["abandon_foreshadow"], foreshadow_id=fid, reason="剧情走向变了",
    )
    assert result["ok"] is True
    assert result["new_state"] == "abandoned"


async def test_partial_resolve_then_full_resolve(prepared_project):
    from app.agents.team import make_tools

    project_id = prepared_project
    import sqlite3

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status) "
            "VALUES (?, 'X', 'x', 'planted')",
            (project_id,),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    tools = make_tools(project_id)
    r1 = await _call_tool_text(
        tools["partial_resolve_foreshadow"], foreshadow_id=fid, resolution="揭晓一半",
    )
    assert r1["new_state"] == "partially_resolved"

    r2 = await _call_tool_text(
        tools["resolve_foreshadow"], foreshadow_id=fid, resolution="完整揭晓",
    )
    assert r2["new_state"] == "resolved"


async def test_build_toolkit_registers_all_tools(prepared_project):
    """The Toolkit returned from build_toolkit exposes every declared tool.

    Kept as a single assertion set so adding/removing tools shows a clean diff.
    """
    from app.agents.team import build_toolkit

    project_id = prepared_project
    toolkit = build_toolkit(project_id)

    schemas = await toolkit.get_tool_schemas()
    tool_names = {s["function"]["name"] for s in schemas}
    expected = {
        "save_episode", "query_characters",
        "plant_foreshadow", "resolve_foreshadow",
        "partial_resolve_foreshadow", "abandon_foreshadow",
        "update_character_state",
        "add_prop", "mark_prop_used",
        "list_source_documents", "search_source_documents", "expand_source_chunk",
        "activate_skill", "read_skill_file",
    }
    assert tool_names == expected
