"""Export API — .docx download.

`.fdx` (Final Draft) is a P1 add-on; not shipped in this slice.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.db import DB_PATH
from app.deps import OwnedProject
from app.services.docx_exporter import render_project

router = APIRouter()


@router.post("/{project_id}/export")
async def export_project(
    project: OwnedProject,
    format: str = Query("docx", description="Only 'docx' supported for now"),
):
    """Return the project as a .docx download."""
    if format != "docx":
        from fastapi import HTTPException
        raise HTTPException(400, f"unsupported format: {format}")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        ep_cur = await db.execute(
            "SELECT id, episode_number, title FROM episodes "
            "WHERE project_id = ? ORDER BY episode_number",
            (project["id"],),
        )
        eps = [dict(r) for r in await ep_cur.fetchall()]
        for ep in eps:
            sc_cur = await db.execute(
                "SELECT scene_number, location, time, content FROM scenes "
                "WHERE episode_id = ? ORDER BY scene_number",
                (ep["id"],),
            )
            ep["scenes"] = [dict(r) for r in await sc_cur.fetchall()]

    payload = render_project(dict(project), eps)

    filename = (project.get("title") or "script").replace(" ", "_") + ".docx"
    return Response(
        content=payload,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
