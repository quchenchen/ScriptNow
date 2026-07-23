from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_runtime import creative_runtime
from .manuscript_documents import get_document, save_document
from .manuscript_impacts import extract_impact_candidate
from .models import ManuscriptEditRevision, ManuscriptUnit, Project
from .schemas import CreateManuscriptAiEdit, ManuscriptEditRevisionView, SaveManuscriptDocument


async def _owned_unit(db: AsyncSession, project_id: int, unit_id: int, user_id: int) -> ManuscriptUnit:
    unit = await db.scalar(
        select(ManuscriptUnit).join(Project, Project.id == ManuscriptUnit.project_id).where(
            ManuscriptUnit.id == unit_id,
            ManuscriptUnit.project_id == project_id,
            Project.owner_id == user_id,
        )
    )
    if unit is None:
        raise HTTPException(404, "正文单元不存在")
    return unit


def view(revision: ManuscriptEditRevision) -> ManuscriptEditRevisionView:
    return ManuscriptEditRevisionView(
        id=revision.id,
        project_id=revision.project_id,
        unit_id=revision.unit_id,
        base_version=revision.base_version,
        selection_start=revision.selection_start,
        selection_end=revision.selection_end,
        selected_text=revision.selected_text,
        replacement_text=revision.replacement_text,
        mode=revision.mode,
        instruction=revision.instruction,
        preserve=json.loads(revision.preserve_json),
        context_before=revision.context_before,
        context_after=revision.context_after,
        rationale=revision.rationale,
        status=revision.status,
        stale_reason=revision.stale_reason,
    )


async def create_edit(
    db: AsyncSession,
    project_id: int,
    unit_id: int,
    user_id: int,
    command: CreateManuscriptAiEdit,
) -> ManuscriptEditRevisionView:
    prepared = await prepare_edit(db, project_id, unit_id, user_id, command)
    return await persist_prepared_edit(db, project_id, unit_id, user_id, command, prepared)


async def prepare_edit(
    db: AsyncSession,
    project_id: int,
    unit_id: int,
    user_id: int,
    command: CreateManuscriptAiEdit,
) -> dict[str, Any]:
    unit = await _owned_unit(db, project_id, unit_id, user_id)
    if unit.status != "adopted":
        raise HTTPException(409, "只有已采用正文可以创建局部修改")
    document = await get_document(db, project_id, unit_id, user_id)
    if command.base_version != document.version:
        raise HTTPException(409, "正文版本已变化，请重新选择文本")
    if command.selection_end > len(document.content) or command.selection_start >= command.selection_end:
        raise HTTPException(422, "选区范围无效")
    actual = document.content[command.selection_start:command.selection_end]
    if actual != command.selected_text:
        raise HTTPException(409, "选区文本与当前正文不一致，请重新选择")
    before = document.content[max(0, command.selection_start - 500):command.selection_start]
    after = document.content[command.selection_end:command.selection_end + 500]
    draft = await creative_runtime().rewrite_selection(command={
        "unit_type": unit.unit_type,
        "metadata": document.metadata,
        "mode": command.mode,
        "selected_text": command.selected_text,
        "context_before": before,
        "context_after": after,
        "instruction": command.instruction,
        "preserve": command.preserve,
    })
    return {"unit": unit, "document": document, "before": before, "after": after, "draft": draft}


async def persist_prepared_edit(
    db: AsyncSession,
    project_id: int,
    unit_id: int,
    user_id: int,
    command: CreateManuscriptAiEdit,
    prepared: dict[str, Any],
) -> ManuscriptEditRevisionView:
    document = await get_document(db, project_id, unit_id, user_id)
    original = prepared["document"]
    if document.version != original.version or document.content != original.content:
        raise HTTPException(409, "正文在候选生成期间发生变化，请重新选择")
    draft = prepared["draft"]
    revision = ManuscriptEditRevision(
        project_id=project_id,
        unit_id=unit_id,
        base_version=document.version,
        selection_start=command.selection_start,
        selection_end=command.selection_end,
        selected_text=command.selected_text,
        replacement_text=draft.replacement_text,
        mode=command.mode,
        instruction=command.instruction,
        preserve_json=json.dumps(command.preserve, ensure_ascii=False),
        context_before=prepared["before"],
        context_after=prepared["after"],
        rationale=draft.rationale,
        created_by=user_id,
    )
    db.add(revision)
    await db.commit()
    await db.refresh(revision)
    return view(revision)


async def resolve_edit(
    db: AsyncSession,
    project_id: int,
    revision_id: int,
    user_id: int,
    action: str,
) -> ManuscriptEditRevisionView:
    revision = await db.scalar(
        select(ManuscriptEditRevision)
        .join(Project, Project.id == ManuscriptEditRevision.project_id)
        .where(
            ManuscriptEditRevision.id == revision_id,
            ManuscriptEditRevision.project_id == project_id,
            Project.owner_id == user_id,
        )
    )
    if revision is None:
        raise HTTPException(404, "局部修改候选不存在")
    if revision.status != "candidate":
        raise HTTPException(409, "局部修改候选已处理")
    if action == "reject":
        revision.status = "rejected"
        revision.resolved_at = datetime.utcnow()
        await db.commit()
        return view(revision)
    if action != "adopt":
        raise HTTPException(422, "未知动作")
    document = await get_document(db, project_id, revision.unit_id, user_id)
    if document.version != revision.base_version:
        revision.status = "stale"
        revision.stale_reason = "正文版本已变化，请重新比较"
        await db.commit()
        raise HTTPException(409, revision.stale_reason)
    if document.content[revision.selection_start:revision.selection_end] != revision.selected_text:
        revision.status = "stale"
        revision.stale_reason = "原选区已变化，请重新选择"
        await db.commit()
        raise HTTPException(409, revision.stale_reason)
    content = (
        document.content[:revision.selection_start]
        + revision.replacement_text
        + document.content[revision.selection_end:]
    )
    await save_document(
        db,
        project_id,
        revision.unit_id,
        user_id,
        SaveManuscriptDocument(base_version=document.version, content=content),
    )
    revision.status = "adopted"
    revision.resolved_at = datetime.utcnow()
    await extract_impact_candidate(db, revision)
    await db.commit()
    return view(revision)
