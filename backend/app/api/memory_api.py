"""Memory API — uses MemoryService (SQLAlchemy-backed)."""
from fastapi import APIRouter, Depends
from app.database import async_session
from app.services.memory_service import MemoryService

router = APIRouter()


async def get_memory_service():
    async with async_session() as session:
        yield MemoryService(session)


@router.get("/{project_id}/characters")
async def get_characters(project_id: int, svc=Depends(get_memory_service)):
    return await svc.list_characters(project_id)

@router.post("/{project_id}/characters")
async def add_character(project_id: int, data: dict, svc=Depends(get_memory_service)):
    cid = await svc.add_character(project_id, data)
    return {"status": "ok", "id": cid}

@router.put("/{project_id}/characters/{char_id}")
async def update_character(project_id: int, char_id: int, data: dict, svc=Depends(get_memory_service)):
    await svc.update_character(project_id, char_id, data)
    return {"status": "ok"}

@router.delete("/{project_id}/characters/{char_id}")
async def delete_character(project_id: int, char_id: int, svc=Depends(get_memory_service)):
    await svc.delete_character(project_id, char_id)
    return {"status": "ok"}

@router.get("/{project_id}/foreshadows")
async def get_foreshadows(project_id: int, status: str = "", svc=Depends(get_memory_service)):
    return await svc.list_foreshadows(project_id, status)

@router.post("/{project_id}/foreshadows")
async def add_foreshadow(project_id: int, data: dict, svc=Depends(get_memory_service)):
    fid = await svc.add_foreshadow(project_id, data)
    return {"status": "ok", "id": fid}

@router.put("/{project_id}/foreshadows/{f_id}")
async def update_foreshadow(project_id: int, f_id: int, data: dict, svc=Depends(get_memory_service)):
    await svc.update_foreshadow(project_id, f_id, data)
    return {"status": "ok"}

@router.get("/{project_id}/memory")
async def get_memory(project_id: int, svc=Depends(get_memory_service)):
    chars = await svc.list_characters(project_id)
    fores = await svc.list_foreshadows(project_id)
    scenes = await svc.list_scenes(project_id)
    return {"characters": chars, "foreshadows": fores, "scenes": scenes}
