from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentTask, Project

ALLOWED_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"delivered", "waiting_decision", "blocked", "failed", "cancelled"},
    "blocked": {"queued", "cancelled"},
    "failed": {"queued", "cancelled"},
}


async def create_initial_story_core_task(
    db: AsyncSession, *, user_id: int, project_id: int, seed: str
) -> AgentTask:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    if project is None:
        raise HTTPException(404, "Project 不存在")
    task = AgentTask(
        project_id=project_id,
        requested_by=user_id,
        agent_profile="creative_director",
        skill_name="story-core-shaping",
        skill_version="1.0.0",
        goal="基于创作种子提交 3 个差异化 Story Core 候选",
        status="queued",
        autonomy_level="A2",
        context_pack_json=json.dumps({"seed": seed}, ensure_ascii=False),
        status_message="等待模型配置检查",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


def transition(task: AgentTask, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(task.status, set()):
        raise ValueError(f"invalid AgentTask transition: {task.status} -> {target}")
    task.status = target
