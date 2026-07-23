from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_runtime import creative_runtime
from .manuscript_documents import get_document, save_document
from .models import CascadeRevision, ManuscriptUnit, Project, StoryBibleChange
from .schemas import CascadeRevisionView, SaveManuscriptDocument


def view(item: CascadeRevision) -> CascadeRevisionView:
    return CascadeRevisionView(
        id=item.id,
        project_id=item.project_id,
        change_id=item.change_id,
        unit_id=item.unit_id,
        base_version=item.base_version,
        original_content=item.original_content,
        candidate_content=item.candidate_content,
        rationale=item.rationale,
        evidence=json.loads(item.evidence_json),
        status=item.status,
    )


async def create_for_change(
    db: AsyncSession,
    change: StoryBibleChange,
    unit: ManuscriptUnit,
    proposed: dict,
    user_id: int,
) -> CascadeRevision:
    document = await get_document(db, change.project_id, unit.id, user_id)
    if change.change_type == "character_introduction":
        label, requirement = proposed["name"], proposed["narrative_function"]
    elif change.change_type == "relationship_change":
        label, requirement = proposed["relationship_type"], proposed["objective_relationship"]
    elif change.change_type == "world_rule":
        label, requirement = proposed["title"], proposed["dramatic_constraint"]
    else:
        label, requirement = proposed["title"], proposed["planting_method"]
    fact = {"label": label, "requirement": requirement, "change_type": change.change_type}
    draft = await creative_runtime().rewrite_selection(command={
        "unit_type": unit.unit_type,
        "mode": "custom",
        "selected_text": document.content,
        "context_before": "",
        "context_after": "",
        "instruction": "STORY_BIBLE_CASCADE：让已确认角色变化在正文中有可定位行动证据",
        "preserve": ["原有情节因果", "人物语气", "已冻结事实"],
        "required_fact": fact,
        "metadata": document.metadata,
    })
    evidence_present = label in draft.replacement_text
    item = CascadeRevision(
        project_id=change.project_id,
        change_id=change.id,
        unit_id=unit.id,
        base_version=document.version,
        original_content=document.content,
        candidate_content=draft.replacement_text,
        rationale=draft.rationale,
        evidence_json=json.dumps([{
            "required_fact": fact,
            "locator": label if evidence_present else None,
            "status": "present" if evidence_present else "missing",
        }], ensure_ascii=False),
        created_by=user_id,
    )
    db.add(item)
    return item


async def list_cascade_revisions(
    db: AsyncSession, project_id: int, user_id: int,
) -> list[CascadeRevisionView]:
    owned = await db.scalar(select(Project.id).where(Project.id == project_id, Project.owner_id == user_id))
    if owned is None:
        raise HTTPException(404, "Project 不存在")
    items = (await db.scalars(select(CascadeRevision).where(
        CascadeRevision.project_id == project_id,
    ).order_by(CascadeRevision.id.desc()))).all()
    return [view(item) for item in items]


async def resolve_cascade_revision(
    db: AsyncSession, project_id: int, revision_id: int, user_id: int, action: str,
) -> CascadeRevisionView:
    item = await db.scalar(
        select(CascadeRevision)
        .join(Project, Project.id == CascadeRevision.project_id)
        .where(
            CascadeRevision.id == revision_id,
            CascadeRevision.project_id == project_id,
            Project.owner_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(404, "Cascade Revision 不存在")
    if item.status != "candidate":
        raise HTTPException(409, "Cascade Revision 已处理")
    if action == "reject":
        item.status = "rejected"
        item.resolved_at = datetime.utcnow()
        await db.commit()
        return view(item)
    if action != "adopt":
        raise HTTPException(422, "未知动作")
    document = await get_document(db, project_id, item.unit_id, user_id)
    if document.version != item.base_version or document.content != item.original_content:
        item.status = "stale"
        await db.commit()
        raise HTTPException(409, "正文基线已变化，请重新生成 Cascade Revision")
    if any(evidence["status"] != "present" for evidence in json.loads(item.evidence_json)):
        raise HTTPException(409, "候选缺少设定落入正文的证据，不能采用")
    await save_document(
        db, project_id, item.unit_id, user_id,
        SaveManuscriptDocument(
            base_version=item.base_version,
            content=item.candidate_content,
            metadata=document.metadata,
        ),
        source=f"cascade_change_{item.change_id}",
    )
    item.status = "adopted"
    item.resolved_at = datetime.utcnow()
    await db.commit()
    return view(item)
