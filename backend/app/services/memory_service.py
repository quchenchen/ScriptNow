"""Memory Service — Character + Foreshadow + Scene management with SQLAlchemy."""
import json
import re

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, Episode, Foreshadow


class MemoryService:
    """Unified memory CRUD — replaces raw aiosqlite calls."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Characters ──
    async def list_characters(self, project_id: int) -> list[dict]:
        r = await self.db.execute(
            select(Character).where(Character.project_id == project_id).order_by(Character.role, Character.first_appearance)
        )
        return [_model_to_dict(c) for c in r.scalars().all()]

    async def add_character(self, project_id: int, data: dict) -> int:
        c = Character(project_id=project_id, name=data.get("name",""), role=data.get("role","supporting"),
                      traits=data.get("traits",""), arc=data.get("arc",""), age=data.get("age",""),
                      gender=data.get("gender",""), personality=data.get("personality",""),
                      background=data.get("background",""), appearance=data.get("appearance",""),
                      is_organization=data.get("is_organization",0), org_type=data.get("org_type",""),
                      org_purpose=data.get("org_purpose",""))
        self.db.add(c)
        await self.db.commit()
        await self.db.refresh(c)
        return c.id

    async def update_character(self, project_id: int, char_id: int, data: dict) -> bool:
        stmt = update(Character).where(Character.id == char_id, Character.project_id == project_id)
        upd = {k: v for k, v in data.items() if hasattr(Character, k) and k != 'id'}
        if upd:
            await self.db.execute(stmt.values(**upd))
            await self.db.commit()
        return True

    async def delete_character(self, project_id: int, char_id: int):
        await self.db.execute(
            update(Character).where(Character.id == char_id, Character.project_id == project_id).values(status='deceased')
        )
        await self.db.commit()

    # ── Foreshadows ──
    async def list_foreshadows(self, project_id: int, status: str = "") -> list[dict]:
        stmt = select(Foreshadow).where(Foreshadow.project_id == project_id)
        if status:
            stmt = stmt.where(Foreshadow.status == status)
        stmt = stmt.order_by(Foreshadow.importance.desc(), Foreshadow.plant_episode)
        r = await self.db.execute(stmt)
        return [_model_to_dict(f) for f in r.scalars().all()]

    async def add_foreshadow(self, project_id: int, data: dict) -> int:
        f = Foreshadow(project_id=project_id, title=data.get("title",""), description=data.get("description",data.get("title","")),
                       category=data.get("category","mystery"), importance=data.get("importance",0.5),
                       strength=data.get("strength",5), subtlety=data.get("subtlety",5),
                       is_long_term=data.get("is_long_term",0), plant_episode=data.get("plant_episode"),
                       target_episode=data.get("target_episode"), related_characters=json.dumps(data.get("related_characters",[])),
                       tags=json.dumps(data.get("tags",[])))
        self.db.add(f)
        await self.db.commit()
        await self.db.refresh(f)
        return f.id

    async def update_foreshadow(self, project_id: int, fid: int, data: dict) -> bool:
        stmt = update(Foreshadow).where(Foreshadow.id == fid, Foreshadow.project_id == project_id)
        upd = {k: v for k, v in data.items() if hasattr(Foreshadow, k) and k != 'id'}
        if upd:
            await self.db.execute(stmt.values(**upd))
            await self.db.commit()
        return True

    # ── Scenes ──
    async def list_scenes(self, project_id: int) -> list[dict]:
        r = await self.db.execute(select(Episode).where(Episode.project_id == project_id))
        locs: dict[str, int] = {}
        for ep in r.scalars():
            try:
                scs = json.loads(ep.scenes or "[]")
                for sc in scs:
                    m = re.match(r'【场景\d+】(.+?)(?:·|\s*-|\n)', sc.get("content", ""))
                    if m:
                        key = m.group(1).strip()
                        locs[key] = locs.get(key, 0) + 1
            except (json.JSONDecodeError, KeyError, TypeError):
                # Malformed scene JSON — skip, don't crash the whole listing
                pass
        return [{"name": k, "count": v} for k, v in locs.items()]


def _model_to_dict(model) -> dict:
    return {c.name: getattr(model, c.name) for c in model.__table__.columns}
