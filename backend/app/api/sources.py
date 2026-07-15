"""Source-document API: upload / list / delete / status + retrieval.

Upload spawns a background task to index the file. Client polls
``/sources/{sid}`` to see status flip from pending → parsing → indexing → done.

Ownership: every route resolves the project via ``OwnedProject`` so
non-owners get 404.
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.db import DB_PATH
from app.deps import OwnedProject
from app.services import source_indexer, source_retriever
from app.services.document_parser import SUPPORTED_EXTENSIONS, is_supported

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/{project_id}/sources/upload")
async def upload_source(
    project: OwnedProject,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form("adaptation"),  # informational — future filtering
):
    """Accept a document, save to disk, kick off indexing in the background."""
    if not file.filename:
        raise HTTPException(400, "缺少文件名")
    if not is_supported(file.filename):
        raise HTTPException(
            400, f"仅支持格式: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            400, f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 限制",
        )

    source_id = await source_indexer.create_source(
        project_id=project["id"],
        filename=file.filename,
        mime=file.content_type or "",
        file_bytes=data,
    )
    background_tasks.add_task(source_indexer.run_indexing, source_id)
    return {"id": source_id, "filename": file.filename, "status": "pending"}


@router.get("/{project_id}/sources")
async def list_project_sources(project: OwnedProject):
    return await source_retriever.list_sources(project["id"])


@router.get("/{project_id}/sources/{source_id}")
async def get_source(project: OwnedProject, source_id: int):
    """Return one source's metadata + first few chunk previews."""
    owner_pid = await source_retriever.project_id_for_source(source_id)
    if owner_pid != project["id"]:
        raise HTTPException(404, "文件不存在")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, filename, mime, total_chars, chunk_count, summary, "
            "status, error, created_at "
            "FROM project_sources WHERE id = ?",
            (source_id,),
        )
        meta = dict(await cur.fetchone() or {})
        preview_cur = await db.execute(
            "SELECT id, chunk_index, content FROM source_chunks "
            "WHERE source_id = ? ORDER BY chunk_index LIMIT 3",
            (source_id,),
        )
        previews = [
            {**dict(r), "content": (r["content"] or "")[:200]}
            for r in await preview_cur.fetchall()
        ]
    meta["preview_chunks"] = previews
    return meta


@router.delete("/{project_id}/sources/{source_id}")
async def delete_source(project: OwnedProject, source_id: int):
    owner_pid = await source_retriever.project_id_for_source(source_id)
    if owner_pid != project["id"]:
        raise HTTPException(404, "文件不存在")

    async with aiosqlite.connect(DB_PATH) as db:
        # Find file_path so we can also delete the blob
        cur = await db.execute(
            "SELECT file_path FROM project_sources WHERE id = ?", (source_id,),
        )
        row = await cur.fetchone()
        file_rel = row[0] if row else None

        await db.execute("DELETE FROM source_chunks WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM project_sources WHERE id = ?", (source_id,))
        await db.commit()

    # Best-effort disk cleanup
    if file_rel:
        p = Path(__file__).resolve().parent.parent.parent / file_rel
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass  # pragma: no cover — leave stale file, DB is source of truth

    return {"deleted": source_id}


@router.get("/{project_id}/sources/{source_id}/search")
async def search_in_source(project: OwnedProject, source_id: int, q: str, k: int = 5):
    """Search within a single source. Handy for the Workspace source panel."""
    owner_pid = await source_retriever.project_id_for_source(source_id)
    if owner_pid != project["id"]:
        raise HTTPException(404, "文件不存在")
    # Reuse the project-wide search then filter — simpler than another SQL path
    hits = await source_retriever.search_source(project["id"], q, k=k * 2)
    return [h for h in hits if h["source_id"] == source_id][:k]


@router.get("/{project_id}/sources-search")
async def search_project_sources(project: OwnedProject, q: str, k: int = 5):
    """Cross-source search — the main RAG entrypoint for Agents/UI."""
    return await source_retriever.search_source(project["id"], q, k=k)


@router.get("/{project_id}/chunks/{chunk_id}")
async def get_chunk(project: OwnedProject, chunk_id: int, ctx: int = 0):
    owner_pid = await source_retriever.project_id_for_chunk(chunk_id)
    if owner_pid != project["id"]:
        raise HTTPException(404, "片段不存在")
    return await source_retriever.expand_chunk(chunk_id, ctx=ctx)
