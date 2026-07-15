"""Workspace API — Episode, Stage, Agent Chat with real LLM.

All endpoints are project-scoped and require a valid JWT. Ownership is
verified via the ``OwnedProject`` dependency — non-owners get 404 (same as
non-existent project).
"""
from __future__ import annotations

import json
import os

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db import DB_PATH
from app.deps import OwnedProject

router = APIRouter()


async def _save_stage_output(project_id: int, stage: str, content: str) -> None:
    """Save stage output to script_versions for context chaining."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO script_versions (project_id, stage, content) VALUES (?,?,?)",
            (project_id, stage, content),
        )
        await db.commit()


# ── Skill loading ─────────────────────────────────────────────

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


def _load_skill_tree(skill_path: str) -> str:
    """Load a skill file plus all reference files in the same directory."""
    full = os.path.join(SKILLS_DIR, skill_path) if skill_path else ""
    if not full or not os.path.exists(full):
        return ""
    dirpath = os.path.dirname(full)
    parts: list[str] = []
    if os.path.isfile(full):
        with open(full, encoding="utf-8") as fh:
            parts.append(fh.read())
        main_name = os.path.basename(full)
        for f in sorted(os.listdir(dirpath)):
            if f.endswith(".md") and f != main_name:
                with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                    parts.append(f"<!-- ref: {f} -->\n{fh.read()}")
    else:
        for f in sorted(os.listdir(full)):
            if f.endswith(".md"):
                with open(os.path.join(full, f), encoding="utf-8") as fh:
                    parts.append(f"<!-- ref: {f} -->\n{fh.read()}")
    return "\n\n---\n\n".join(parts) if parts else ""


# ── Episode CRUD ──────────────────────────────────────────────

@router.get("/{project_id}/episodes")
async def list_episodes(project: OwnedProject, status: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM episodes WHERE project_id = ?"
        params: list = [project["id"]]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY episode_number"
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


@router.get("/{project_id}/episodes/{ep_number}")
async def get_episode(project: OwnedProject, ep_number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project["id"], ep_number),
        )
        ep = await cursor.fetchone()
        if not ep:
            raise HTTPException(404, "剧集不存在")
        ep_dict = dict(ep)
        # Attach scenes so the client can render without a second round-trip
        scenes_cur = await db.execute(
            "SELECT id, scene_number, location, time, content, characters_involved, "
            "props_used, status FROM scenes WHERE episode_id = ? ORDER BY scene_number",
            (ep_dict["id"],),
        )
        ep_dict["scenes"] = [dict(r) for r in await scenes_cur.fetchall()]
        return ep_dict


@router.put("/{project_id}/episodes/{ep_number}")
async def update_episode(project: OwnedProject, ep_number: int, data: dict):
    """Update episode metadata (title / status / word_count / review_score).

    Scene edits go through the dedicated /scenes endpoints — not this one.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project["id"], ep_number),
        )
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE episodes SET title=?, word_count=?, status=?, "
                "review_score=? WHERE id=?",
                (
                    data.get("title", ""),
                    data.get("word_count", 0),
                    data.get("status", "pending"),
                    data.get("review_score", 0),
                    row[0],
                ),
            )
        else:
            await db.execute(
                "INSERT INTO episodes (project_id, episode_number, title, "
                "word_count, status, review_score) VALUES (?,?,?,?,?,?)",
                (
                    project["id"], ep_number, data.get("title", ""),
                    data.get("word_count", 0), data.get("status", "pending"),
                    data.get("review_score", 0),
                ),
            )
        await db.commit()
    return {"project_id": project["id"], "episode_number": ep_number, "status": "updated"}


# ── Scene CRUD ────────────────────────────────────────────────
# Scenes are project-scoped via episode; we look them up via episode_number
# (project-relative) to keep URLs pretty.

async def _load_episode_id(project_id: int, ep_number: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project_id, ep_number),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "剧集不存在")
        return row[0]


@router.get("/{project_id}/episodes/{ep_number}/scenes")
async def list_scenes(project: OwnedProject, ep_number: int):
    ep_id = await _load_episode_id(project["id"], ep_number)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM scenes WHERE episode_id = ? ORDER BY scene_number", (ep_id,)
        )
        return [dict(r) for r in await cur.fetchall()]


@router.post("/{project_id}/episodes/{ep_number}/scenes")
async def add_scene(project: OwnedProject, ep_number: int, data: dict):
    ep_id = await _load_episode_id(project["id"], ep_number)
    async with aiosqlite.connect(DB_PATH) as db:
        # Determine next scene_number
        cur = await db.execute(
            "SELECT COALESCE(MAX(scene_number), 0) FROM scenes WHERE episode_id = ?", (ep_id,)
        )
        next_n = (await cur.fetchone())[0] + 1
        sn = data.get("scene_number") or next_n
        ins = await db.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content, status) "
            "VALUES (?,?,?,?,?,?)",
            (ep_id, sn, data.get("location", ""), data.get("time", ""),
             data.get("content", ""), data.get("status", "draft")),
        )
        await db.commit()
        return {"id": ins.lastrowid, "scene_number": sn}


@router.put("/{project_id}/episodes/{ep_number}/scenes/{scene_number}")
async def update_scene(project: OwnedProject, ep_number: int, scene_number: int, data: dict):
    ep_id = await _load_episode_id(project["id"], ep_number)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM scenes WHERE episode_id = ? AND scene_number = ?", (ep_id, scene_number)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "场景不存在")
        # Only touch supplied fields
        updates: list[str] = []
        vals: list = []
        for k in ("location", "time", "content", "status", "characters_involved", "props_used"):
            if k in data:
                updates.append(f"{k} = ?")
                v = data[k]
                if isinstance(v, list | dict):
                    v = json.dumps(v, ensure_ascii=False)
                vals.append(v)
        if not updates:
            return {"status": "no-op"}
        vals.append(row[0])
        await db.execute(
            f"UPDATE scenes SET {', '.join(updates)}, updated_at = datetime('now') "
            f"WHERE id = ?",
            vals,
        )
        await db.commit()
    return {"status": "updated"}


@router.delete("/{project_id}/episodes/{ep_number}/scenes/{scene_number}")
async def delete_scene(project: OwnedProject, ep_number: int, scene_number: int):
    ep_id = await _load_episode_id(project["id"], ep_number)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM scenes WHERE episode_id = ? AND scene_number = ?", (ep_id, scene_number)
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "场景不存在")
    return {"deleted": scene_number}


# ── Chat History ──────────────────────────────────────────────

@router.get("/{project_id}/chat")
async def get_chat(project: OwnedProject):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM chat_messages WHERE project_id = ? ORDER BY id", (project["id"],)
        )
        return [dict(r) for r in await cur.fetchall()]


@router.post("/{project_id}/chat")
async def save_chat(project: OwnedProject, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_messages (project_id, role, content, agent_name) "
            "VALUES (?,?,?,?)",
            (project["id"], data["role"], data["content"], data.get("agent_name", "")),
        )
        await db.commit()
    return {"status": "ok"}


# ── Agent Chat ─────────────────────────────────────────────────

@router.post("/{project_id}/agent/chat")
async def agent_chat(project: OwnedProject, data: dict):
    """Kick off a streaming agent conversation for the current stage.

    ⚠ Historical debt: ``AgentTeam`` uses regex-based tool-call parsing.
    Issue #03 (single-llm-path) replaces this with AgentScope's native
    Toolkit — do not extend the current tool loop, migrate it.
    """
    message = data.get("message", "")
    model_id = data.get("model", "dashscope:deepseek-v4-pro")
    project_id = project["id"]
    stage = project["current_stage"]

    # Build memory context: previous stage outputs
    prev_stage_outputs = ""
    try:
        async with aiosqlite.connect(DB_PATH) as db3:
            db3.row_factory = aiosqlite.Row
            cur = await db3.execute(
                "SELECT stage, content FROM script_versions WHERE project_id = ? "
                "ORDER BY id DESC LIMIT 3",
                (project_id,),
            )
            rows = await cur.fetchall()
            if rows:
                lines = ["## 前阶段产出（请基于此继续创作）"]
                for r in reversed(rows):
                    lines.append(f"### {r['stage']}阶段产出\n{r['content'][:2000]}")
                prev_stage_outputs = "\n\n".join(lines)
    except Exception:
        pass

    # Determine episode number for context
    ep_num = 0
    if stage == "writing":
        async with aiosqlite.connect(DB_PATH) as db2:
            cur = await db2.execute(
                "SELECT MAX(episode_number) FROM episodes WHERE project_id = ? "
                "AND status = 'done'",
                (project_id,),
            )
            last = await cur.fetchone()
            ep_num = (last[0] or 0) + 1

    async def event_stream():
        from app.agents.team import AgentTeam
        team = AgentTeam(project_id, model_id)

        full_text = ""
        try:
            async with aiosqlite.connect(DB_PATH) as db2:
                await db2.execute(
                    "INSERT INTO chat_messages (project_id, role, content) VALUES (?,?,?)",
                    (project_id, "user", message),
                )
                await db2.commit()
        except Exception:
            pass

        async for event in team.run(message, stage, ep_num, prev_stage_outputs):
            if event["type"] in ("thinking", "text_delta", "tool_result", "error"):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] == "text_delta":
                full_text += event["text"]

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        if full_text and len(full_text) > 100:
            await _save_stage_output(project_id, stage, full_text[:5000])
        if full_text:
            try:
                async with aiosqlite.connect(DB_PATH) as db3:
                    await db3.execute(
                        "INSERT INTO chat_messages (project_id, role, content, agent_name) "
                        "VALUES (?,?,?,?)",
                        (project_id, "agent", full_text, "Agent"),
                    )
                    await db3.commit()
            except Exception:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")
