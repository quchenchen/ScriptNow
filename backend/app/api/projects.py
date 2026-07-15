"""Projects API — CRUD + Pipeline Definitions.

All endpoints require a valid JWT and operate scoped to ``current_user``.
Client-supplied ``user_id`` is *ignored* — the server always uses the id
carried by the token.
"""
from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.pipelines import PIPELINES, get_pipeline
from app.db import DB_PATH
from app.deps import CurrentUser

router = APIRouter()


class ProjectCreate(BaseModel):
    title: str
    type: str = "script"
    genre: str | None = "[]"
    target_audience: str = ""
    cultural_background: str = "国内"
    style_preference: str = ""
    source_mode: str = "original_pitch"
    seed_content: str = ""
    original_work: str = ""
    source_file: str | None = None


class ProjectOut(BaseModel):
    id: int
    user_id: int
    title: str
    type: str
    genre: str
    target_audience: str
    style_preference: str = ""
    source_mode: str = "original_pitch"
    seed_content: str = ""
    original_work: str = ""
    status: str
    current_stage: str
    total_episodes: int
    created_at: str
    updated_at: str


def _first_stage(ptype: str) -> str:
    pipe = get_pipeline(ptype)
    if pipe and pipe["stages"]:
        return pipe["stages"][0]["key"]
    return "ideation"


# NOTE: /pipelines must be declared before /{project_id} so route matching lands right
@router.get("/pipelines")
async def list_pipelines(user: CurrentUser):
    return {
        k: {"label": v["label"], "stages": v["stages"], "unit_label": v["unit_label"]}
        for k, v in PIPELINES.items()
    }


@router.get("/list")
async def list_projects(user: CurrentUser):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)
        )
        return [dict(r) for r in await cursor.fetchall()]


@router.post("/create", response_model=ProjectOut)
async def create_project(req: ProjectCreate, user: CurrentUser):
    first = _first_stage(req.type)
    # Normalize genre — accept either a JSON string or a bare list from the
    # client, always store as JSON text.
    genre_raw = req.genre or "[]"
    if isinstance(genre_raw, list):
        genre_raw = json.dumps(genre_raw, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "INSERT INTO projects (user_id, title, type, genre, target_audience, "
            "cultural_background, style_preference, source_mode, seed_content, "
            "original_work, status, current_stage) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user["id"], req.title, req.type, genre_raw, req.target_audience,
                req.cultural_background, req.style_preference,
                req.source_mode, req.seed_content, req.original_work,
                "in_progress", first,
            ),
        )
        await db.commit()
        pid = cursor.lastrowid
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (pid,))
        return dict(await cursor.fetchone())


async def _load_owned_project(project_id: int, user: dict) -> dict:
    """Load a project verifying ownership. Raises 404 on mismatch to avoid
    leaking existence to unauthorized callers."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "项目不存在")
        return dict(row)


@router.get("/{project_id}")
async def get_project(project_id: int, user: CurrentUser):
    project = await _load_owned_project(project_id, user)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        ep_cursor = await db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done "
            "FROM episodes WHERE project_id = ?",
            (project_id,),
        )
        ep_summary = await ep_cursor.fetchone()
    project["episodes_total"] = ep_summary["total"] or 0
    project["episodes_done"] = ep_summary["done"] or 0
    return project


@router.put("/{project_id}/stage")
async def update_stage(project_id: int, stage: str, user: CurrentUser):
    await _load_owned_project(project_id, user)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET current_stage = ?, updated_at = datetime('now') WHERE id = ?",
            (stage, project_id),
        )
        await db.commit()
    return {"project_id": project_id, "current_stage": stage}


@router.delete("/{project_id}")
async def delete_project(project_id: int, user: CurrentUser):
    await _load_owned_project(project_id, user)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM episodes WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM reviews WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM script_versions WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
    return {"deleted": project_id}


@router.put("/{project_id}/settings")
async def update_project_settings(project_id: int, data: dict, user: CurrentUser):
    await _load_owned_project(project_id, user)
    async with aiosqlite.connect(DB_PATH) as db:
        if "genre" in data:
            g = data["genre"]
            val = json.dumps(g) if isinstance(g, list) else g
            await db.execute("UPDATE projects SET genre=? WHERE id=?", (val, project_id))
        if "style_preference" in data:
            await db.execute(
                "UPDATE projects SET style_preference=? WHERE id=?",
                (data["style_preference"], project_id),
            )
        await db.commit()
    return {"status": "ok"}
