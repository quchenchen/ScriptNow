from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ManuscriptUnit, Project, ProjectPlan, StoryMapGroup, StoryMapUnit
from .schemas import (
    CreateProject,
    CreateStoryMapUnit,
    ProjectPlanChange,
    ProjectPlanImpactView,
    ProjectPlanView,
    ReorderStoryMapUnits,
    StoryMapGroupView,
    StoryMapUnitUpdate,
    StoryMapUnitView,
    StoryMapView,
)


def dimensions(goal_type: str) -> tuple[str, str]:
    source = "adaptation" if goal_type.startswith("adapt-") else "original"
    medium = "novel" if goal_type.endswith("novel") else "script"
    return source, medium


async def create_plan_and_story_map(db: AsyncSession, project: Project, command: CreateProject) -> None:
    source, medium = dimensions(command.goal_type)
    plan = ProjectPlan(
        project_id=project.id,
        creation_source=source,
        delivery_medium=medium,
        seed_maturity=command.seed_maturity,
        planning_mode=command.planning_mode,
        target_volume_count=command.target_volume_count if medium == "novel" else 0,
        target_chapter_count=command.target_chapter_count if medium == "novel" else 0,
        target_episode_count=command.target_episode_count if medium == "script" else 0,
        target_scenes_per_episode=command.target_scenes_per_episode if medium == "script" else 0,
        target_words=command.target_words,
        target_minutes_per_episode=command.target_minutes_per_episode,
        style_direction=command.style_direction,
        medium_key=command.medium_key,
        story_structure=command.story_structure,
        creative_boundaries_json=json.dumps(command.creative_boundaries, ensure_ascii=False),
    )
    db.add(plan)
    await db.flush()
    if medium == "novel":
        await _seed_novel_map(db, project.id, command)
    else:
        await _seed_script_map(db, project.id, command)


async def _seed_novel_map(db: AsyncSession, project_id: int, command: CreateProject) -> None:
    volumes = min(command.target_volume_count, command.target_chapter_count)
    base, remainder = divmod(command.target_chapter_count, volumes)
    global_ordinal = 1
    for volume_ordinal in range(1, volumes + 1):
        group = StoryMapGroup(
            project_id=project_id,
            group_type="volume",
            ordinal=volume_ordinal,
            title=f"第 {volume_ordinal} 卷 · 待规划",
        )
        db.add(group)
        await db.flush()
        count = base + (1 if volume_ordinal <= remainder else 0)
        for chapter_ordinal in range(1, count + 1):
            db.add(StoryMapUnit(
                project_id=project_id,
                group_id=group.id,
                unit_type="chapter",
                ordinal=chapter_ordinal,
                global_ordinal=global_ordinal,
                title=f"第 {global_ordinal} 章 · 待规划",
                target_length=(command.target_words // command.target_chapter_count if command.target_words else 0),
            ))
            global_ordinal += 1


async def _seed_script_map(db: AsyncSession, project_id: int, command: CreateProject) -> None:
    global_ordinal = 1
    for episode_ordinal in range(1, command.target_episode_count + 1):
        group = StoryMapGroup(
            project_id=project_id,
            group_type="episode",
            ordinal=episode_ordinal,
            title=f"第 {episode_ordinal} 集 · 待规划",
        )
        db.add(group)
        await db.flush()
        for scene_ordinal in range(1, command.target_scenes_per_episode + 1):
            db.add(StoryMapUnit(
                project_id=project_id,
                group_id=group.id,
                unit_type="scene",
                ordinal=scene_ordinal,
                global_ordinal=global_ordinal,
                title=f"Scene {scene_ordinal} · 待规划",
                target_length=command.target_minutes_per_episode,
            ))
            global_ordinal += 1


async def _owned_project(db: AsyncSession, project_id: int, user_id: int) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    return project


async def ensure_legacy_plan(db: AsyncSession, project: Project) -> ProjectPlan:
    plan = await db.scalar(select(ProjectPlan).where(ProjectPlan.project_id == project.id))
    if plan:
        return plan
    source, medium = dimensions(project.goal_type)
    manuscripts = (await db.scalars(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project.id,
    ).order_by(ManuscriptUnit.ordinal))).all()
    unit_count = max(len(manuscripts), 1)
    plan = ProjectPlan(
        project_id=project.id,
        creation_source=source,
        delivery_medium=medium,
        planning_mode="progressive",
        target_volume_count=1 if medium == "novel" else 0,
        target_chapter_count=unit_count if medium == "novel" else 0,
        target_episode_count=1 if medium == "script" else 0,
        target_scenes_per_episode=unit_count if medium == "script" else 0,
        status="needs_review",
    )
    db.add(plan)
    group = StoryMapGroup(
        project_id=project.id,
        group_type="volume" if medium == "novel" else "episode",
        ordinal=1,
        title="第 1 卷 · 待确认" if medium == "novel" else "第 1 集 · 待确认",
        status="needs_review",
    )
    db.add(group)
    await db.flush()
    if manuscripts:
        for manuscript in manuscripts:
            db.add(StoryMapUnit(
                project_id=project.id,
                group_id=group.id,
                unit_type="chapter" if medium == "novel" else "scene",
                ordinal=manuscript.ordinal,
                global_ordinal=manuscript.ordinal,
                title=manuscript.title or f"第 {manuscript.ordinal} {'章' if medium == 'novel' else '场'}",
                status=manuscript.status,
                manuscript_unit_id=manuscript.id,
            ))
    else:
        db.add(StoryMapUnit(
            project_id=project.id,
            group_id=group.id,
            unit_type="chapter" if medium == "novel" else "scene",
            ordinal=1,
            global_ordinal=1,
            title="第 1 章 · 待规划" if medium == "novel" else "Scene 1 · 待规划",
        ))
    await db.commit()
    return plan


def plan_view(plan: ProjectPlan) -> ProjectPlanView:
    return ProjectPlanView(
        project_id=plan.project_id,
        creation_source=plan.creation_source,
        delivery_medium=plan.delivery_medium,
        seed_maturity=plan.seed_maturity,
        planning_mode=plan.planning_mode,
        target_volume_count=plan.target_volume_count,
        target_chapter_count=plan.target_chapter_count,
        target_episode_count=plan.target_episode_count,
        target_scenes_per_episode=plan.target_scenes_per_episode,
        target_words=plan.target_words,
        target_minutes_per_episode=plan.target_minutes_per_episode,
        style_direction=plan.style_direction,
        creative_boundaries=json.loads(plan.creative_boundaries_json),
        status=plan.status,
    )


def unit_view(unit: StoryMapUnit) -> StoryMapUnitView:
    return StoryMapUnitView(**{
        field: getattr(unit, field) for field in StoryMapUnitView.model_fields
    })


async def get_plan(db: AsyncSession, project_id: int, user_id: int) -> ProjectPlanView:
    project = await _owned_project(db, project_id, user_id)
    plan = await ensure_legacy_plan(db, project)
    return plan_view(plan)


async def get_story_map(db: AsyncSession, project_id: int, user_id: int) -> StoryMapView:
    project = await _owned_project(db, project_id, user_id)
    plan = await ensure_legacy_plan(db, project)
    groups = (await db.scalars(select(StoryMapGroup).where(
        StoryMapGroup.project_id == project_id,
    ).order_by(StoryMapGroup.ordinal))).all()
    result: list[StoryMapGroupView] = []
    adopted = 0
    planned = 0
    for group in groups:
        units = (await db.scalars(select(StoryMapUnit).where(
            StoryMapUnit.group_id == group.id,
        ).order_by(StoryMapUnit.ordinal))).all()
        planned += len(units)
        adopted += sum(unit.status == "adopted" for unit in units)
        result.append(StoryMapGroupView(
            id=group.id,
            group_type=group.group_type,
            ordinal=group.ordinal,
            title=group.title,
            goal=group.goal,
            status=group.status,
            units=[unit_view(unit) for unit in units],
        ))
    return StoryMapView(
        project_id=project_id,
        delivery_medium=plan.delivery_medium,
        groups=result,
        planned_units=planned,
        adopted_units=adopted,
    )


async def update_story_map_unit(
    db: AsyncSession, project_id: int, user_id: int, unit_id: int, command: StoryMapUnitUpdate,
) -> StoryMapUnitView:
    await _owned_project(db, project_id, user_id)
    unit = await db.scalar(select(StoryMapUnit).where(
        StoryMapUnit.id == unit_id,
        StoryMapUnit.project_id == project_id,
    ))
    if unit is None:
        raise HTTPException(404, "作品目录单元不存在")
    for field, value in command.model_dump(exclude_none=True).items():
        setattr(unit, field, value)
    await db.commit()
    return unit_view(unit)


async def add_story_map_unit(
    db: AsyncSession, project_id: int, user_id: int, group_id: int, command: CreateStoryMapUnit,
) -> StoryMapUnitView:
    await _owned_project(db, project_id, user_id)
    group = await db.scalar(select(StoryMapGroup).where(
        StoryMapGroup.id == group_id,
        StoryMapGroup.project_id == project_id,
    ))
    if group is None:
        raise HTTPException(404, "作品目录分组不存在")
    ordinal = (await db.scalar(select(func.max(StoryMapUnit.ordinal)).where(
        StoryMapUnit.group_id == group.id,
    )) or 0) + 1
    global_ordinal = (await db.scalar(select(func.max(StoryMapUnit.global_ordinal)).where(
        StoryMapUnit.project_id == project_id,
    )) or 0) + 1
    unit = StoryMapUnit(
        project_id=project_id,
        group_id=group.id,
        unit_type="chapter" if group.group_type == "volume" else "scene",
        ordinal=ordinal,
        global_ordinal=global_ordinal,
        title=command.title,
        intent=command.intent,
        target_length=command.target_length,
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return unit_view(unit)


async def reorder_story_map_units(
    db: AsyncSession, project_id: int, user_id: int, group_id: int, command: ReorderStoryMapUnits,
) -> StoryMapView:
    await _owned_project(db, project_id, user_id)
    group = await db.scalar(select(StoryMapGroup).where(
        StoryMapGroup.id == group_id,
        StoryMapGroup.project_id == project_id,
    ))
    if group is None:
        raise HTTPException(404, "作品目录分组不存在")
    units = (await db.scalars(select(StoryMapUnit).where(
        StoryMapUnit.group_id == group_id,
    ).order_by(StoryMapUnit.ordinal))).all()
    current_ids = [unit.id for unit in units]
    ordered_ids = command.ordered_unit_ids
    if len(set(ordered_ids)) != len(ordered_ids):
        raise HTTPException(422, "排序列表不能包含重复单元")
    if set(ordered_ids) != set(current_ids):
        raise HTTPException(422, "排序必须包含当前分组的全部且仅包含这些单元")

    by_id = {unit.id: unit for unit in units}
    # Two-phase ordinal assignment avoids the group/ordinal unique constraint.
    for temporary_ordinal, unit in enumerate(units, start=1):
        unit.ordinal = -temporary_ordinal
    await db.flush()
    for ordinal, unit_id in enumerate(ordered_ids, start=1):
        by_id[unit_id].ordinal = ordinal

    all_groups = (await db.scalars(select(StoryMapGroup).where(
        StoryMapGroup.project_id == project_id,
    ).order_by(StoryMapGroup.ordinal))).all()
    global_ordinal = 1
    for story_group in all_groups:
        group_units = (await db.scalars(select(StoryMapUnit).where(
            StoryMapUnit.group_id == story_group.id,
        ).order_by(StoryMapUnit.ordinal))).all()
        for unit in group_units:
            unit.global_ordinal = global_ordinal
            global_ordinal += 1
    await db.commit()
    return await get_story_map(db, project_id, user_id)


def _target_unit_count(plan: ProjectPlan, command: ProjectPlanChange) -> int:
    if plan.delivery_medium == "novel":
        return command.target_chapter_count or plan.target_chapter_count
    episodes = command.target_episode_count or plan.target_episode_count
    scenes = command.target_scenes_per_episode or plan.target_scenes_per_episode
    return episodes * scenes


async def preview_plan_change(
    db: AsyncSession, project_id: int, user_id: int, command: ProjectPlanChange,
) -> ProjectPlanImpactView:
    project = await _owned_project(db, project_id, user_id)
    plan = await ensure_legacy_plan(db, project)
    units = (await db.scalars(select(StoryMapUnit).where(
        StoryMapUnit.project_id == project_id,
    ))).all()
    current_units = len(units)
    target_units = _target_unit_count(plan, command)
    protected_units = sum(unit.manuscript_unit_id is not None for unit in units)
    if plan.delivery_medium == "novel":
        topology_changed = (
            (command.target_volume_count or plan.target_volume_count) != plan.target_volume_count
            or target_units != current_units
        )
    else:
        topology_changed = (
            (command.target_episode_count or plan.target_episode_count) != plan.target_episode_count
            or (command.target_scenes_per_episode or plan.target_scenes_per_episode)
            != plan.target_scenes_per_episode
        )
    warnings: list[str] = []
    can_apply = True
    if topology_changed:
        warnings.append(f"作品目录将从 {current_units} 个单元调整为 {target_units} 个单元。")
        if protected_units:
            can_apply = False
            warnings.append(
                f"已有 {protected_units} 个单元关联正文，系统不会自动重建；请使用后续结构迁移功能。"
            )
        else:
            warnings.append("现有空目录将被重建，标题和单元创作意图会被清空。")
    return ProjectPlanImpactView(
        current_units=current_units,
        target_units=target_units,
        protected_units=protected_units,
        units_added=max(target_units - current_units, 0),
        units_removed=max(current_units - target_units, 0),
        topology_changed=topology_changed,
        can_apply=can_apply,
        requires_confirmation=topology_changed,
        warnings=warnings,
    )


async def apply_plan_change(
    db: AsyncSession, project_id: int, user_id: int, command: ProjectPlanChange,
) -> ProjectPlanView:
    project = await _owned_project(db, project_id, user_id)
    plan = await ensure_legacy_plan(db, project)
    impact = await preview_plan_change(db, project_id, user_id, command)
    if not impact.can_apply:
        raise HTTPException(409, impact.warnings[-1])
    if impact.requires_confirmation and not command.confirm_rebuild:
        raise HTTPException(409, "目标规模会重建空目录，请先查看影响并明确确认")

    values = command.model_dump(exclude_none=True, exclude={"confirm_rebuild"})
    boundaries = values.pop("creative_boundaries", None)
    if impact.topology_changed:
        units = (await db.scalars(select(StoryMapUnit).where(
            StoryMapUnit.project_id == project_id,
        ))).all()
        for unit in units:
            await db.delete(unit)
        await db.flush()
        groups = (await db.scalars(select(StoryMapGroup).where(
            StoryMapGroup.project_id == project_id,
        ))).all()
        for group in groups:
            await db.delete(group)
        await db.flush()
    for field, value in values.items():
        setattr(plan, field, value)
    if boundaries is not None:
        plan.creative_boundaries_json = json.dumps(boundaries, ensure_ascii=False)
    if impact.topology_changed:
        seed_command = CreateProject(
            title=project.title,
            goal_type=project.goal_type,
            target_volume_count=max(plan.target_volume_count, 1),
            target_chapter_count=max(plan.target_chapter_count, 1),
            target_episode_count=max(plan.target_episode_count, 1),
            target_scenes_per_episode=max(plan.target_scenes_per_episode, 1),
            target_words=plan.target_words,
            target_minutes_per_episode=plan.target_minutes_per_episode,
        )
        if plan.delivery_medium == "novel":
            await _seed_novel_map(db, project_id, seed_command)
        else:
            await _seed_script_map(db, project_id, seed_command)
    plan.status = "adopted"
    await db.commit()
    await db.refresh(plan)
    return plan_view(plan)
