"""Workspace API — Episode, Stage, Agent Chat with real LLM"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
import json, asyncio, re, os
import aiosqlite
from app.db import DB_PATH
from app.core.context_engine import build_context, save_episode_context


async def _save_stage_output(project_id: int, stage: str, content: str):
    """Save stage output to script_versions for context chaining."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO script_versions (project_id, stage, content) VALUES (?,?,?)",
            (project_id, stage, content))
        await db.commit()

router = APIRouter()

# ── Skill loading ─────────────────────────────────────────────

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")

def _load_skill(name: str) -> str:
    path = os.path.join(SKILLS_DIR, name)
    if os.path.exists(path):
        return open(path).read()
    return ""

def _load_skill_tree(skill_path: str) -> str:
    """Load a skill file plus all reference files in the same directory."""
    full = os.path.join(SKILLS_DIR, skill_path) if skill_path else ""
    if not full or not os.path.exists(full):
        return ""
    dirpath = os.path.dirname(full)
    parts = []
    if os.path.isfile(full):
        parts.append(open(full).read())
        # Also load reference files from same dir (but not the main file itself)
        main_name = os.path.basename(full)
        for f in sorted(os.listdir(dirpath)):
            if f.endswith('.md') and f != main_name:
                parts.append(f"<!-- ref: {f} -->\n{open(os.path.join(dirpath, f)).read()}")
    else:
        for f in sorted(os.listdir(full)):
            if f.endswith('.md'):
                parts.append(f"<!-- ref: {f} -->\n{open(os.path.join(full, f)).read()}")
    return "\n\n---\n\n".join(parts) if parts else ""

# ── Episode CRUD ──────────────────────────────────────────────

@router.get("/{project_id}/episodes")
async def list_episodes(project_id: int, status: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM episodes WHERE project_id = ?"
        params = [project_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY episode_number"
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]

@router.get("/{project_id}/episodes/{ep_number}")
async def get_episode(project_id: int, ep_number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project_id, ep_number))
        ep = await cursor.fetchone()
        if not ep: raise HTTPException(404, "剧集不存在")
        return dict(ep)

@router.put("/{project_id}/episodes/{ep_number}")
async def update_episode(project_id: int, ep_number: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project_id, ep_number))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE episodes SET title=?, scenes=?, word_count=?, status=?, review_score=? WHERE id=?",
                (data.get("title",""), json.dumps(data.get("scenes",[]), ensure_ascii=False),
                 data.get("word_count",0), data.get("status","pending"),
                 data.get("review_score",0), row[0]))
        else:
            await db.execute(
                "INSERT INTO episodes (project_id, episode_number, title, scenes, word_count, status, review_score) VALUES (?,?,?,?,?,?,?)",
                (project_id, ep_number, data.get("title",""),
                 json.dumps(data.get("scenes",[]), ensure_ascii=False),
                 data.get("word_count",0), data.get("status","pending"),
                 data.get("review_score",0)))
        await db.commit()
    return {"project_id": project_id, "episode_number": ep_number, "status": "updated"}

# ── Chat History ──────────────────────────────────────────────

@router.get("/{project_id}/chat")
async def get_chat(project_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM chat_messages WHERE project_id = ? ORDER BY id", (project_id,))
        return [dict(r) for r in await cur.fetchall()]


@router.post("/{project_id}/chat")
async def save_chat(project_id: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_messages (project_id, role, content, agent_name) VALUES (?,?,?,?)",
            (project_id, data["role"], data["content"], data.get("agent_name","")))
        await db.commit()
    return {"status": "ok"}

# ── Agent Chat ─────────────────────────────────────────────────

@router.post("/{project_id}/agent/chat")
async def agent_chat(project_id: int, data: dict):
    message = data.get("message", "")
    model_id = data.get("model", "dashscope:deepseek-v4-pro")

    # Load project context
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        project = await cur.fetchone()
        if not project: raise HTTPException(404, "项目不存在")

    stage = project["current_stage"]
    ptype = project["type"] or "script"
    project_info = f"项目：《{project['title']}》\n类型：{ptype}\n受众：{project['target_audience']}\n当前阶段：{stage}"

    # Build system prompt from pipeline skill map
    from app.core.pipelines import get_pipeline
    pipe = get_pipeline(ptype)
    skill_path = None
    if pipe:
        for s in pipe["stages"]:
            if s["key"] == stage:
                skill_path = s.get("skill")
                break
    skill = _load_skill_tree(skill_path) if skill_path else ""

    # Determine episode number for context
    ep_num = 0
    if stage in ("writing",):
        async with aiosqlite.connect(DB_PATH) as db2:
            cur = await db2.execute(
                "SELECT MAX(episode_number) FROM episodes WHERE project_id = ? AND status = 'done'",
                (project_id,))
            last = await cur.fetchone()
            ep_num = (last[0] or 0) + 1

    # Build memory context
    # Inject previous stage outputs into context
    prev_stage_outputs = ""
    try:
        async with aiosqlite.connect(DB_PATH) as db3:
            db3.row_factory = aiosqlite.Row
            cur = await db3.execute(
                "SELECT stage, content FROM script_versions WHERE project_id = ? ORDER BY id DESC LIMIT 3",
                (project_id,))
            rows = await cur.fetchall()
            if rows:
                lines = ["## 前阶段产出（请基于此继续创作）"]
                for r in reversed(rows):
                    lines.append(f"### {r['stage']}阶段产出\n{r['content'][:2000]}")
                prev_stage_outputs = "\n\n".join(lines)
    except: pass

    # (AgentRouter handles all of this internally now)
    
    async def event_stream():
        from app.core.agent_orchestra import AgentTeam
        team = AgentTeam(project_id, model_id)

        full_text = ""
        tool_called = False
        # Save user message to chat history
        try:
            async with aiosqlite.connect(DB_PATH) as db2:
                await db2.execute(
                    "INSERT INTO chat_messages (project_id, role, content) VALUES (?,?,?)",
                    (project_id, "user", message))
                await db2.commit()
        except: pass

        async for event in team.run(message, stage, ep_num, prev_stage_outputs):
            if event["type"] in ("thinking", "text_delta", "tool_result", "error"):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] == "text_delta":
                full_text += event["text"]
            if event["type"] == "tool_result":
                tool_called = True

        # Auto-save if agent generated content but didn't call save tool
        if stage in ("writing",) and len(full_text) > 50 and not tool_called:
            from app.core.agent_orchestra import tool_save_episode
            result = await tool_save_episode(project_id, ep_num, full_text)
            save_msg = f'自动保存 EP{ep_num}: {result["words"]}字'
            yield f"data: {json.dumps({'type': 'tool_result', 'text': save_msg}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        # Save stage output for context chaining
        if full_text and len(full_text) > 100:
            await _save_stage_output(project_id, stage, full_text[:5000])
        # Save agent response to chat history
        if full_text:
            try:
                async with aiosqlite.connect(DB_PATH) as db3:
                    await db3.execute(
                        "INSERT INTO chat_messages (project_id, role, content, agent_name) VALUES (?,?,?,?)",
                        (project_id, "agent", full_text, "Agent"))
                    await db3.commit()
            except: pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")
