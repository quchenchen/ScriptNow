from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_runtime import creative_runtime
from .continuity import bootstrap_story_core
from .models import (
    AgentTask,
    ManuscriptCandidate,
    ManuscriptUnit,
    Project,
    SourceCanon,
    StoryCoreCandidate,
    User,
)
from .project_planning import create_plan_and_story_map
from .schemas import CreateProject, ProjectPulseView, ProjectView, StoryCoreView, TaskView
from .tasks import create_initial_story_core_task


async def demo_user(db: AsyncSession) -> User:
    user = await db.scalar(select(User).where(User.public_id == "local-demo-user"))
    if user is None:
        user = User(public_id="local-demo-user", display_name="本地创作者")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def create_project(db: AsyncSession, command: CreateProject) -> ProjectView:
    user = await demo_user(db)
    project = Project(
        owner_id=user.id, title=command.title, goal_type=command.goal_type,
        genre=command.genre, audience=command.audience, seed=command.seed,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    await create_plan_and_story_map(db, project, command)
    await db.commit()
    if command.source_type != "none":
        db.add(SourceCanon(
            project_id=project.id, source_name=command.source_name,
            source_type=command.source_type, content=command.source_content,
            file_name=command.source_file_name, status="available",
        ))
        await db.commit()
    task = await create_initial_story_core_task(db, user_id=user.id, project_id=project.id, seed=command.seed or command.source_content)
    return await project_view(db, project.id, user.id, task)


async def list_projects(db: AsyncSession, user_id: int) -> list[ProjectView]:
    ids = (await db.scalars(
        select(Project.id).where(Project.owner_id == user_id).order_by(Project.id.desc())
    )).all()
    return [await project_view(db, project_id, user_id) for project_id in ids]


def candidate_view(item: StoryCoreCandidate) -> StoryCoreView:
    return StoryCoreView(**{key: getattr(item, key) for key in StoryCoreView.model_fields})


async def task_view(db: AsyncSession, task: AgentTask) -> TaskView:
    candidates = (await db.scalars(select(StoryCoreCandidate).where(StoryCoreCandidate.task_id == task.id).order_by(StoryCoreCandidate.id))).all()
    return TaskView(id=task.id, status=task.status, goal=task.goal, agent_profile=task.agent_profile,
                    status_message=task.status_message, candidates=[candidate_view(x) for x in candidates])


async def project_view(db: AsyncSession, project_id: int, user_id: int, task: AgentTask | None = None) -> ProjectView:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    source = await db.scalar(select(SourceCanon).where(SourceCanon.project_id == project.id))
    task = task or await db.scalar(select(AgentTask).where(
        AgentTask.project_id == project.id,
        AgentTask.agent_profile == "creative_director",
    ).order_by(AgentTask.id.desc()))
    return ProjectView(
        id=project.id, title=project.title, goal_type=project.goal_type, genre=project.genre,
        audience=project.audience, seed=project.seed, status=project.status,
        adopted_story_core_id=project.adopted_story_core_id,
        source_name=source.source_name if source else "", source_status=source.status if source else "",
        task=await task_view(db, task) if task else None,
        pulse=await project_pulse(db, project),
    )


async def project_pulse(db: AsyncSession, project: Project) -> ProjectPulseView:
    latest_task = await db.scalar(select(AgentTask).where(
        AgentTask.project_id == project.id).order_by(AgentTask.id.desc()))
    unit = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project.id).order_by(ManuscriptUnit.ordinal.desc()))
    candidate = None
    if unit:
        candidate = await db.scalar(select(ManuscriptCandidate).where(
            ManuscriptCandidate.unit_id == unit.id).order_by(ManuscriptCandidate.id.desc()))
    if latest_task and latest_task.status in {"queued", "running"}:
        return ProjectPulseView(phase=latest_task.skill_name, state="working",
            headline="Agent Team 正在工作", detail=latest_task.status_message or latest_task.goal,
            needs_user=False, next_action="等待当前交付", capability_tier="专业创作", estimated_credits=8)
    if latest_task and latest_task.status == "waiting_decision":
        return ProjectPulseView(phase=latest_task.skill_name, state="waiting_user",
            headline="有一项创作决定等待你", detail=latest_task.status_message or latest_task.goal,
            needs_user=True, next_action="审阅并采用、拒绝或要求重做", capability_tier="专业创作", estimated_credits=0)
    if project.adopted_story_core_id is None:
        return ProjectPulseView(phase="story_core", state="ready", headline="作品种子已经就绪",
            detail="创意导演可以形成三个差异化 Story Core", needs_user=False,
            next_action="启动创意方向任务", capability_tier="专业创作", estimated_credits=12)
    if unit is None:
        return ProjectPulseView(phase="opening", state="ready", headline="故事方向已经确定",
            detail="Project Truth 已建立，可以生成第一章或第一场候选", needs_user=False,
            next_action=f"生成第一{('章' if project.goal_type.endswith('novel') else '场')}候选",
            capability_tier="专业创作", estimated_credits=18)
    if candidate and candidate.status == "candidate":
        return ProjectPulseView(phase="opening", state="waiting_user", headline="正文候选等待你的判断",
            detail="连续性检查已完成；采用后才会更新角色状态与伏笔账本", needs_user=True,
            next_action="审阅正文与影响后决定是否采用", capability_tier="专业创作", estimated_credits=0)
    return ProjectPulseView(phase="manuscript", state="ready", headline=f"第 {unit.ordinal} 个创作单元已经进入正文",
        detail="角色状态与 Promise–Payoff 账本已同步", needs_user=False,
        next_action="规划下一章节", capability_tier="专业创作", estimated_credits=10)


async def run_task(db: AsyncSession, project_id: int, task_id: int) -> TaskView:
    user = await demo_user(db)
    task = await db.scalar(select(AgentTask).join(Project).where(
        AgentTask.id == task_id, AgentTask.project_id == project_id, Project.owner_id == user.id))
    if task is None:
        raise HTTPException(404, "Task 不存在")
    if task.status == "delivered" or task.status == "waiting_decision":
        return await task_view(db, task)
    existing = (await db.scalars(select(StoryCoreCandidate).where(StoryCoreCandidate.task_id == task.id))).all()
    if existing:
        task.status = "waiting_decision"
        task.status_message = "已提交 3 个差异化 Story Core，等待你的判断"
        await db.commit()
        return await task_view(db, task)
    task.status = "running"
    task.started_at = datetime.utcnow()
    task.status_message = "创意导演正在比较人物欲望、核心冲突与叙事承诺"
    await db.commit()
    project = await db.get(Project, project_id)
    source = await db.scalar(select(SourceCanon).where(SourceCanon.project_id == project_id))
    runtime = creative_runtime()
    drafts = await runtime.shape_story_cores(
        title=project.title, goal_type=project.goal_type, seed=project.seed,
        source_text=source.content if source else "",
    )
    for draft in drafts:
        db.add(StoryCoreCandidate(
            project_id=project_id, task_id=task.id, **draft.__dict__,
        ))
    task.status = "waiting_decision"
    task.finished_at = datetime.utcnow()
    task.status_message = f"已提交 3 个差异化 Story Core，等待你的判断 · {runtime.name}"
    await db.commit()
    return await task_view(db, task)


async def adopt_candidate(db: AsyncSession, project_id: int, candidate_id: int) -> ProjectView:
    user = await demo_user(db)
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    candidate = await db.scalar(select(StoryCoreCandidate).where(
        StoryCoreCandidate.id == candidate_id, StoryCoreCandidate.project_id == project_id))
    if project is None or candidate is None:
        raise HTTPException(404, "候选不存在")
    others = (await db.scalars(select(StoryCoreCandidate).where(StoryCoreCandidate.project_id == project_id))).all()
    for item in others:
        item.status = "adopted" if item.id == candidate_id else "not_selected"
    project.adopted_story_core_id = candidate_id
    project.status = "growing"
    task = await db.get(AgentTask, candidate.task_id)
    if task:
        task.status = "delivered"
        task.status_message = "Story Core 已由用户采用并写入 Project Truth"
    await db.commit()
    await bootstrap_story_core(db, project, candidate)
    return await project_view(db, project_id, user.id)
