"""Ralph loop API — history + manual trigger.

Auto-trigger (Writing Agent → Review → loop) is wired in the workspace agent
chat flow separately; this endpoint is the manual escape hatch for the UI
"重审" button.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.db import DB_PATH
from app.deps import OwnedProject
from app.services import ralph_service

router = APIRouter()


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


@router.get("/{project_id}/episodes/{ep_number}/ralph")
async def get_ralph_history(project: OwnedProject, ep_number: int):
    """Return the full iteration history for one episode."""
    ep_id = await _load_episode_id(project["id"], ep_number)
    iterations = await ralph_service.list_iterations(ep_id)
    return {"episode_id": ep_id, "iterations": iterations}


@router.post("/{project_id}/episodes/{ep_number}/ralph")
async def trigger_ralph(project: OwnedProject, ep_number: int, data: dict):
    """Kick off a new Ralph iteration.

    Body: ``{"model": "dashscope:qwen-turbo"}`` (optional, sensible default).
    Returns the new iteration row + the decision the engine reached.
    """
    ep_id = await _load_episode_id(project["id"], ep_number)
    model_id = (data or {}).get("model") or "dashscope:qwen-turbo"
    result = await ralph_service.run_iteration(project["id"], ep_id, model_id)
    return result
