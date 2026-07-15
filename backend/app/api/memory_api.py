"""Memory API — Living Asset CRUD (Character / Foreshadow / Prop / Scene).

All endpoints project-scoped and JWT-authenticated. Ownership verified via
``OwnedProject`` dependency — non-owners get 404.
"""
from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.database import async_session
from app.db import DB_PATH
from app.deps import OwnedProject
from app.services import growth_tree_service as tree_svc
from app.services.foreshadow_state import (
    InvalidStateTransition,
    is_overdue,
)
from app.services.foreshadow_state import (
    transition as fs_transition,
)
from app.services.memory_service import MemoryService

router = APIRouter()


async def get_memory_service():
    async with async_session() as session:
        yield MemoryService(session)


# ── Characters ────────────────────────────────────────────────

@router.get("/{project_id}/characters")
async def get_characters(project: OwnedProject, svc=Depends(get_memory_service)):
    return await svc.list_characters(project["id"])


@router.post("/{project_id}/characters")
async def add_character(project: OwnedProject, data: dict, svc=Depends(get_memory_service)):
    cid = await svc.add_character(project["id"], data)
    return {"status": "ok", "id": cid}


@router.put("/{project_id}/characters/{char_id}")
async def update_character(
    project: OwnedProject, char_id: int, data: dict, svc=Depends(get_memory_service)
):
    await svc.update_character(project["id"], char_id, data)
    return {"status": "ok"}


@router.delete("/{project_id}/characters/{char_id}")
async def delete_character(
    project: OwnedProject, char_id: int, svc=Depends(get_memory_service)
):
    await svc.delete_character(project["id"], char_id)
    return {"status": "ok"}


@router.get("/{project_id}/characters/{char_id}/dirty-episodes")
async def character_dirty_episodes(project: OwnedProject, char_id: int):
    """Preview episodes affected if this character is edited.

    Uses the growth tree: find the character's asset node, then run
    ``mark_dirty`` on it. Returns an empty list if the character has no
    node yet (never appeared in a saved episode's growth-tree write).
    """
    node = await tree_svc.find_node(project["id"], "asset", char_id)
    if not node:
        return {"character_id": char_id, "affected": []}
    affected = await tree_svc.mark_dirty(node.id)
    return {"character_id": char_id, "affected": [n.__dict__ for n in affected]}


# ── Foreshadows ───────────────────────────────────────────────

def _annotate_overdue(fores: list[dict], project_id: int) -> list[dict]:
    """Attach ``is_overdue`` computed field based on max episode number."""
    # We can compute this cheaply here without a joined query
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "SELECT COALESCE(MAX(episode_number), 0) FROM episodes WHERE project_id = ?",
            (project_id,),
        )
        current_ep = cur.fetchone()[0]
    finally:
        conn.close()
    for f in fores:
        f["is_overdue"] = is_overdue(
            state=f.get("status", ""),
            target_episode=f.get("target_episode"),
            current_episode=current_ep,
            remind_before=f.get("remind_before", 5),
        )
    return fores


@router.get("/{project_id}/foreshadows")
async def get_foreshadows(
    project: OwnedProject, status: str = "", svc=Depends(get_memory_service)
):
    fores = await svc.list_foreshadows(project["id"], status)
    return _annotate_overdue(fores, project["id"])


@router.post("/{project_id}/foreshadows")
async def add_foreshadow(project: OwnedProject, data: dict, svc=Depends(get_memory_service)):
    fid = await svc.add_foreshadow(project["id"], data)
    return {"status": "ok", "id": fid}


@router.put("/{project_id}/foreshadows/{f_id}")
async def update_foreshadow(
    project: OwnedProject, f_id: int, data: dict, svc=Depends(get_memory_service)
):
    await svc.update_foreshadow(project["id"], f_id, data)
    return {"status": "ok"}


@router.patch("/{project_id}/foreshadows/{f_id}/status")
async def transition_foreshadow_status(
    project: OwnedProject, f_id: int, data: dict,
):
    """Move a foreshadow through the state machine.

    Body: ``{"target": "planted"|..., "resolution_text": "..."}`` (optional).
    """
    target = (data or {}).get("target", "").strip()
    if not target:
        raise HTTPException(400, "target 必需")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status FROM foreshadows WHERE id = ? AND project_id = ?",
            (f_id, project["id"]),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "伏笔不存在")

        try:
            new_state = fs_transition(row["status"], target)
        except InvalidStateTransition as e:
            raise HTTPException(400, str(e)) from None

        updates = ["status = ?"]
        vals: list = [new_state.value]
        if "resolution_text" in (data or {}):
            updates.append("resolution_text = ?")
            vals.append(data["resolution_text"])
        vals.append(f_id)
        await db.execute(
            f"UPDATE foreshadows SET {', '.join(updates)} WHERE id = ?", vals
        )
        await db.commit()
    return {"status": "ok", "new_state": new_state.value}


# ── Props ─────────────────────────────────────────────────────

@router.get("/{project_id}/props")
async def list_props(project: OwnedProject, significance: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM props WHERE project_id = ?"
        params: list = [project["id"]]
        if significance:
            query += " AND significance = ?"
            params.append(significance)
        query += " ORDER BY first_appearance, id"
        cur = await db.execute(query, params)
        return [dict(r) for r in await cur.fetchall()]


@router.post("/{project_id}/props")
async def add_prop(project: OwnedProject, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO props (project_id, name, description, significance, "
            "first_appearance, last_appearance, usage_count) VALUES (?,?,?,?,?,?,?)",
            (
                project["id"], data.get("name", ""), data.get("description", ""),
                data.get("significance", "background"),
                data.get("first_appearance", 0), data.get("last_appearance", 0),
                data.get("usage_count", 0),
            ),
        )
        await db.commit()
    return {"status": "ok", "id": cur.lastrowid}


@router.put("/{project_id}/props/{prop_id}")
async def update_prop(project: OwnedProject, prop_id: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM props WHERE id = ? AND project_id = ?",
            (prop_id, project["id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(404, "道具不存在")
        updates: list[str] = []
        vals: list = []
        for k in ("name", "description", "significance", "first_appearance",
                  "last_appearance", "usage_count"):
            if k in data:
                updates.append(f"{k} = ?")
                vals.append(data[k])
        if not updates:
            return {"status": "no-op"}
        vals.append(prop_id)
        await db.execute(
            f"UPDATE props SET {', '.join(updates)} WHERE id = ?", vals
        )
        await db.commit()
    return {"status": "ok"}


@router.delete("/{project_id}/props/{prop_id}")
async def delete_prop(project: OwnedProject, prop_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM props WHERE id = ? AND project_id = ?",
            (prop_id, project["id"]),
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "道具不存在")
    return {"deleted": prop_id}


# ── Summary ───────────────────────────────────────────────────

@router.get("/{project_id}/memory")
async def get_memory(project: OwnedProject, svc=Depends(get_memory_service)):
    chars = await svc.list_characters(project["id"])
    fores = _annotate_overdue(await svc.list_foreshadows(project["id"]), project["id"])
    scenes = await svc.list_scenes(project["id"])
    props = await list_props(project)
    return {
        "characters": chars,
        "foreshadows": fores,
        "scenes": scenes,
        "props": props,
    }


# Re-export json for backward compat with other files that may import it
__all__ = ["router"]
_ = json  # keep import from being auto-pruned; used by legacy consumers
