"""Projects API — CRUD + Pipeline Definitions"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import aiosqlite, json
from app.main import DB_PATH
from app.core.pipelines import get_pipeline, PIPELINES

router = APIRouter()


class ProjectCreate(BaseModel):
    user_id: int
    title: str
    type: str = "script"
    genre: Optional[str] = "[]"
    target_audience: str = ""
    cultural_background: str = "国内"
    source_file: Optional[str] = None


class ProjectOut(BaseModel):
    id: int; user_id: int; title: str; type: str; genre: str
    target_audience: str; status: str; current_stage: str
    total_episodes: int; created_at: str; updated_at: str


@router.get("/list")
async def list_projects(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        return [dict(r) for r in await cursor.fetchall()]


def _first_stage(ptype: str) -> str:
    pipe = get_pipeline(ptype)
    if pipe and pipe["stages"]: return pipe["stages"][0]["key"]
    return "ideation"


@router.post("/create", response_model=ProjectOut)
async def create_project(req: ProjectCreate):
    first = _first_stage(req.type)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "INSERT INTO projects (user_id, title, type, genre, target_audience, cultural_background, status, current_stage) VALUES (?,?,?,?,?,?,?,?)",
            (req.user_id, req.title, req.type, req.genre, req.target_audience,
             req.cultural_background, "in_progress", first))
        await db.commit()
        pid = cursor.lastrowid
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (pid,))
        return dict(await cursor.fetchone())


# Must be before /{project_id} to avoid route matching
@router.get("/pipelines")
async def list_pipelines():
    return {k: {"label": v["label"], "stages": v["stages"], "unit_label": v["unit_label"]}
            for k, v in PIPELINES.items()}


@router.get("/{project_id}")
async def get_project(project_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        project = await cursor.fetchone()
        if not project: raise HTTPException(404, "项目不存在")
        ep_cursor = await db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done FROM episodes WHERE project_id = ?",
            (project_id,))
        ep_summary = await ep_cursor.fetchone()
        result = dict(project)
        result["episodes_total"] = ep_summary["total"] or 0
        result["episodes_done"] = ep_summary["done"] or 0
        return result


@router.put("/{project_id}/stage")
async def update_stage(project_id: int, stage: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET current_stage = ?, updated_at = datetime('now') WHERE id = ?",
            (stage, project_id))
        await db.commit()
    return {"project_id": project_id, "current_stage": stage}

@router.delete("/{project_id}")
async def delete_project(project_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM episodes WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM reviews WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM script_versions WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
    return {"deleted": project_id}

@router.put("/{project_id}/settings")
async def update_project_settings(project_id: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        if "genre" in data:
            g = data["genre"]
            val = json.dumps(g) if isinstance(g, list) else g
            await db.execute("UPDATE projects SET genre=? WHERE id=?", (val, project_id))
        if "style_preference" in data:
            await db.execute("UPDATE projects SET style_preference=? WHERE id=?", (data["style_preference"], project_id))
        await db.commit()
    return {"status": "ok"}
