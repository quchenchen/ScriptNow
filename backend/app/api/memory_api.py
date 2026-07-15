"""Memory API — Living Asset CRUD (Character, Foreshadow, Scene).

⚠ Transitional: uses ``MemoryService`` (SQLAlchemy async). This layer will be
subsumed by ``LivingAssetRepo`` in issues #07 / #08.

All endpoints project-scoped and JWT-authenticated. Ownership verified via
``OwnedProject`` dependency — non-owners get 404.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.database import async_session
from app.deps import OwnedProject
from app.services.memory_service import MemoryService

router = APIRouter()


async def get_memory_service():
    async with async_session() as session:
        yield MemoryService(session)


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


@router.get("/{project_id}/foreshadows")
async def get_foreshadows(
    project: OwnedProject, status: str = "", svc=Depends(get_memory_service)
):
    return await svc.list_foreshadows(project["id"], status)


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


@router.get("/{project_id}/memory")
async def get_memory(project: OwnedProject, svc=Depends(get_memory_service)):
    chars = await svc.list_characters(project["id"])
    fores = await svc.list_foreshadows(project["id"])
    scenes = await svc.list_scenes(project["id"])
    return {"characters": chars, "foreshadows": fores, "scenes": scenes}
