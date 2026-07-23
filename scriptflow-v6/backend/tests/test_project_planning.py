from __future__ import annotations

import os

os.environ["SCRIPTFLOW_V6_DB_PATH"] = "/tmp/scriptflow-v6-test.db"

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from scriptflow_v6.db import session_factory
from scriptflow_v6.models import ManuscriptUnit, Project, StoryMapUnit, User
from scriptflow_v6.project_planning import (
    add_story_map_unit,
    apply_plan_change,
    get_plan,
    get_story_map,
    preview_plan_change,
    reorder_story_map_units,
    update_story_map_unit,
)
from scriptflow_v6.projects import create_project
from scriptflow_v6.schemas import (
    CreateProject,
    CreateStoryMapUnit,
    ProjectPlanChange,
    ReorderStoryMapUnits,
    StoryMapUnitUpdate,
)


async def owner_for(db, project_id: int) -> User:
    return await db.scalar(select(User).join(Project).where(Project.id == project_id))


@pytest.mark.asyncio
async def test_novel_plan_creates_real_volume_chapter_map():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="长篇计划",
            goal_type="original-novel",
            target_volume_count=2,
            target_chapter_count=5,
            target_words=50000,
            planning_mode="plan_first",
        ))
        owner = await owner_for(db, project.id)
        plan = await get_plan(db, project.id, owner.id)
        assert plan.creation_source == "original"
        assert plan.delivery_medium == "novel"
        assert plan.target_chapter_count == 5

        story_map = await get_story_map(db, project.id, owner.id)
        assert [len(group.units) for group in story_map.groups] == [3, 2]
        assert story_map.planned_units == 5
        assert all(unit.unit_type == "chapter" for group in story_map.groups for unit in group.units)
        assert story_map.groups[0].units[0].target_length == 10000

        first = story_map.groups[0].units[0]
        updated = await update_story_map_unit(db, project.id, owner.id, first.id, StoryMapUnitUpdate(
            title="第 1 章 · 十年后的来信",
            intent="建立失踪事件与主角拒绝面对真相的缺口",
        ))
        assert updated.title.endswith("十年后的来信")
        assert "建立失踪事件" in updated.intent


@pytest.mark.asyncio
async def test_script_plan_creates_episode_scene_map_and_can_expand():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="三集短剧",
            goal_type="original-script",
            target_episode_count=2,
            target_scenes_per_episode=3,
            target_minutes_per_episode=12,
        ))
        owner = await owner_for(db, project.id)
        story_map = await get_story_map(db, project.id, owner.id)
        assert len(story_map.groups) == 2
        assert story_map.planned_units == 6
        assert story_map.groups[0].group_type == "episode"
        assert story_map.groups[0].units[0].unit_type == "scene"

        added = await add_story_map_unit(db, project.id, owner.id, story_map.groups[0].id, CreateStoryMapUnit(
            title="Scene 4 · 决定追查",
            intent="主角主动进入第二幕",
        ))
        assert added.ordinal == 4
        assert added.global_ordinal == 7

        reordered = await reorder_story_map_units(
            db,
            project.id,
            owner.id,
            story_map.groups[0].id,
            ReorderStoryMapUnits(ordered_unit_ids=[added.id, *[unit.id for unit in story_map.groups[0].units]]),
        )
        first_group = reordered.groups[0]
        assert first_group.units[0].id == added.id
        assert [unit.ordinal for unit in first_group.units] == [1, 2, 3, 4]
        assert [unit.global_ordinal for group in reordered.groups for unit in group.units] == list(range(1, 8))


@pytest.mark.asyncio
async def test_story_map_reorder_rejects_partial_or_duplicate_lists():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="安全排序", goal_type="original-novel", target_chapter_count=3,
        ))
        owner = await owner_for(db, project.id)
        story_map = await get_story_map(db, project.id, owner.id)
        group = story_map.groups[0]
        with pytest.raises(HTTPException) as partial:
            await reorder_story_map_units(
                db, project.id, owner.id, group.id,
                ReorderStoryMapUnits(ordered_unit_ids=[group.units[0].id]),
            )
        assert partial.value.status_code == 422
        with pytest.raises(HTTPException) as duplicate:
            await reorder_story_map_units(
                db, project.id, owner.id, group.id,
                ReorderStoryMapUnits(ordered_unit_ids=[group.units[0].id] * 3),
            )
        assert duplicate.value.status_code == 422


@pytest.mark.asyncio
async def test_plan_scale_change_requires_preview_and_explicit_confirmation():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="规模调整", goal_type="original-novel", target_chapter_count=3,
        ))
        owner = await owner_for(db, project.id)
        command = ProjectPlanChange(target_chapter_count=5)
        impact = await preview_plan_change(db, project.id, owner.id, command)
        assert impact.current_units == 3
        assert impact.target_units == 5
        assert impact.units_added == 2
        assert impact.requires_confirmation is True
        with pytest.raises(HTTPException) as unconfirmed:
            await apply_plan_change(db, project.id, owner.id, command)
        assert unconfirmed.value.status_code == 409

        plan = await apply_plan_change(
            db, project.id, owner.id,
            ProjectPlanChange(target_chapter_count=5, confirm_rebuild=True),
        )
        assert plan.target_chapter_count == 5
        assert (await get_story_map(db, project.id, owner.id)).planned_units == 5


@pytest.mark.asyncio
async def test_plan_scale_change_never_rebuilds_units_linked_to_manuscript():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="保护正文", goal_type="original-script", target_episode_count=1,
            target_scenes_per_episode=2,
        ))
        owner = await owner_for(db, project.id)
        unit = await db.scalar(select(StoryMapUnit).where(StoryMapUnit.project_id == project.id))
        manuscript = ManuscriptUnit(
            project_id=project.id, unit_type="scene", ordinal=unit.global_ordinal,
            title=unit.title, adopted_content="已采用正文", status="adopted",
        )
        db.add(manuscript)
        await db.flush()
        unit.manuscript_unit_id = manuscript.id
        await db.commit()

        command = ProjectPlanChange(target_scenes_per_episode=3, confirm_rebuild=True)
        impact = await preview_plan_change(db, project.id, owner.id, command)
        assert impact.protected_units == 1
        assert impact.can_apply is False
        with pytest.raises(HTTPException) as protected:
            await apply_plan_change(db, project.id, owner.id, command)
        assert protected.value.status_code == 409
        assert (await get_story_map(db, project.id, owner.id)).planned_units == 2


@pytest.mark.asyncio
async def test_story_map_is_owner_scoped():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(title="隔离目录", goal_type="original-novel"))
        outsider = User(public_id="map-outsider", display_name="Outsider")
        db.add(outsider)
        await db.commit()
        await db.refresh(outsider)
        with pytest.raises(HTTPException) as error:
            await get_story_map(db, project.id, outsider.id)
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_legacy_project_gets_additive_plan_without_inventing_scale():
    async with session_factory() as db:
        owner = User(public_id="legacy-owner", display_name="Legacy")
        db.add(owner)
        await db.flush()
        legacy = Project(owner_id=owner.id, title="旧项目", goal_type="original-script")
        db.add(legacy)
        await db.commit()
        await db.refresh(legacy)

        plan = await get_plan(db, legacy.id, owner.id)
        story_map = await get_story_map(db, legacy.id, owner.id)
        assert plan.status == "needs_review"
        assert plan.target_episode_count == 1
        assert plan.target_scenes_per_episode == 1
        assert story_map.planned_units == 1
        assert story_map.groups[0].status == "needs_review"
