from __future__ import annotations

import os

os.environ["SCRIPTFLOW_V6_DB_PATH"] = "/tmp/scriptflow-v6-test.db"

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from scriptflow_v6.continuity_ledger import (
    create_entity,
    create_foreshadow,
    create_relationship,
    list_foreshadows,
    transition_foreshadow,
)
from scriptflow_v6.db import session_factory
from scriptflow_v6.models import Project, User
from scriptflow_v6.projects import create_project
from scriptflow_v6.schemas import (
    CreateForeshadow,
    CreateNarrativeEntity,
    CreateProject,
    ForeshadowTransition,
    NarrativeRelationshipCommand,
)


@pytest.mark.asyncio
async def test_entity_relationship_and_foreshadow_lifecycle():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(title="账本测试", goal_type="original-script"))
        owner = await db.scalar(select(User).join(Project).where(Project.id == project.id))
        character = await create_entity(db, project.id, owner.id, CreateNarrativeEntity(
            entity_type="character", name="林夏", identity="调查记者", goal="找到失踪妹妹",
        ))
        organization = await create_entity(db, project.id, owner.id, CreateNarrativeEntity(
            entity_type="organization", name="雾港邮政局", identity="控制旧信件流转的机构",
        ))
        relationship = await create_relationship(db, project.id, owner.id, NarrativeRelationshipCommand(
            from_entity_id=character.id, to_entity_id=organization.id,
            relationship_type="调查对象", description="互相隐瞒关键事实",
        ))
        assert relationship.from_name == "林夏"
        assert relationship.to_name == "雾港邮政局"

        clue = await create_foreshadow(db, project.id, owner.id, CreateForeshadow(
            title="十年前的邮戳", content="邮戳日期晚于妹妹失踪时间",
            planned_plant_ordinal=1, planned_resolve_ordinal=3,
            related_entity_ids=[character.id, organization.id],
        ))
        assert clue.status == "planned"
        queued = await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(
            action="queue", evidence="已进入近期创作计划",
        ))
        assert queued.status == "pending"
        planted = await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(
            action="plant", manuscript_ordinal=1, evidence="Scene 1 特写邮戳",
        ))
        assert planted.status == "planted"
        assert planted.actual_plant_ordinal == 1
        partial = await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(
            action="partial_resolve", manuscript_ordinal=2, evidence="确认邮戳来自内部机器",
        ))
        assert partial.status == "partially_resolved"
        resolved = await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(
            action="resolve", manuscript_ordinal=3, evidence="局长承认伪造时间",
        ))
        assert resolved.status == "resolved"
        assert len(resolved.events) == 4

        with pytest.raises(HTTPException) as error:
            await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(action="reinforce"))
        assert error.value.status_code == 409

        ledger = await list_foreshadows(db, project.id, owner.id)
        assert ledger[0].related_entity_ids == [character.id, organization.id]


@pytest.mark.asyncio
async def test_ledger_is_project_owner_scoped():
    async with session_factory() as db:
        project = await create_project(db, CreateProject(title="隔离账本", goal_type="original-novel"))
        outsider = User(public_id="ledger-outsider", display_name="Outsider")
        db.add(outsider)
        await db.commit()
        await db.refresh(outsider)
        with pytest.raises(HTTPException) as error:
            await list_foreshadows(db, project.id, outsider.id)
        assert error.value.status_code == 404
