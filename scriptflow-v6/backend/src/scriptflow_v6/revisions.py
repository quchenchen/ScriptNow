from __future__ import annotations

import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .living_assets import extract_candidate
from .models import CreativeRevision, ManuscriptUnit, Scene
from .schemas import CreateRevision, RevisionView


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def view(revision: CreativeRevision) -> RevisionView:
    return RevisionView(
        id=revision.id, project_id=revision.project_id, scene_id=revision.scene_id,
        status=revision.status, candidate_content=revision.candidate_content,
        brief=json.loads(revision.brief_json), context_pack=json.loads(revision.context_pack_json),
        evidence=json.loads(revision.evidence_json), impact=json.loads(revision.impact_json),
        stale_reason=revision.stale_reason,
    )


async def create(db: AsyncSession, project_id: int, command: CreateRevision) -> RevisionView:
    scene = await db.scalar(select(Scene).where(Scene.id == command.scene_id, Scene.project_id == project_id))
    if scene is None:
        raise HTTPException(404, "Scene 不存在")
    context = command.context_pack.model_dump()
    context["target"] = {"type": "scene", "id": scene.id}
    context["base_hash"] = content_hash(scene.adopted_content)
    revision = CreativeRevision(
        project_id=project_id, scene_id=scene.id, base_hash=context["base_hash"],
        candidate_content=command.candidate_content, status="candidate",
        brief_json=command.brief.model_dump_json(), context_pack_json=json.dumps(context, ensure_ascii=False),
        evidence_json=json.dumps(command.evidence, ensure_ascii=False), impact_json=json.dumps(command.impact, ensure_ascii=False),
    )
    db.add(revision)
    await db.flush()
    await extract_candidate(db, revision)
    await db.commit()
    await db.refresh(revision)
    return view(revision)


async def resolve(db: AsyncSession, project_id: int, revision_id: int, action: str) -> RevisionView:
    revision = await db.scalar(select(CreativeRevision).where(CreativeRevision.id == revision_id, CreativeRevision.project_id == project_id))
    if revision is None:
        raise HTTPException(404, "Revision 不存在")
    if revision.status != "candidate":
        raise HTTPException(409, "Revision 已处理")
    scene = await db.scalar(select(Scene).where(Scene.id == revision.scene_id, Scene.project_id == project_id))
    if scene is None:
        raise HTTPException(404, "Scene 不存在")
    if action == "adopt":
        if content_hash(scene.adopted_content) != revision.base_hash:
            revision.status = "stale"
            revision.stale_reason = "基线内容已变化，请重新比较"
            await db.commit()
            raise HTTPException(409, revision.stale_reason)
        scene.adopted_content = revision.candidate_content
        if scene.scene_key.startswith("SC-"):
            ordinal = int(scene.scene_key.removeprefix("SC-"))
            unit = await db.scalar(select(ManuscriptUnit).where(
                ManuscriptUnit.project_id == project_id,
                ManuscriptUnit.unit_type == "scene",
                ManuscriptUnit.ordinal == ordinal,
            ))
            if unit:
                unit.adopted_content = revision.candidate_content
        revision.status = "adopted"
    elif action == "reject":
        revision.status = "rejected"
    else:
        raise HTTPException(422, "未知动作")
    revision.resolved_at = datetime.utcnow()
    await db.commit()
    return view(revision)
