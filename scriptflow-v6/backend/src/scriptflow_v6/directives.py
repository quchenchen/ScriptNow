from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CreativeDirective, Project
from .schemas import CreateDirective, DirectiveView


def directive_view(item: CreativeDirective) -> DirectiveView:
    raw_constraints = json.loads(item.constraints_json)
    metadata = raw_constraints if isinstance(raw_constraints, dict) else {}
    return DirectiveView(id=item.id, scope=item.scope, instruction=item.instruction,
        target_type=metadata.get("target_type", "project"), target_id=metadata.get("target_id"),
        lifetime=metadata.get("lifetime", "project" if item.scope == "project_rule" else "once"),
        preserve=json.loads(item.preserve_json), constraints=metadata.get("rules", raw_constraints if isinstance(raw_constraints, list) else []),
        status=item.status, consumed_by_task_id=item.consumed_by_task_id)


async def create_directive(db: AsyncSession, project_id: int, user_id: int, command: CreateDirective) -> DirectiveView:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    item = CreativeDirective(project_id=project_id, created_by=user_id, scope=command.scope,
        instruction=command.instruction, preserve_json=json.dumps(command.preserve, ensure_ascii=False),
        constraints_json=json.dumps({"rules": command.constraints, "target_type": command.target_type,
            "target_id": command.target_id, "lifetime": command.lifetime}, ensure_ascii=False))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return directive_view(item)


async def list_directives(db: AsyncSession, project_id: int, user_id: int) -> list[DirectiveView]:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    items = (await db.scalars(select(CreativeDirective).where(
        CreativeDirective.project_id == project_id).order_by(CreativeDirective.id.desc()))).all()
    return [directive_view(item) for item in items]
