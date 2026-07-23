from __future__ import annotations

import os

os.environ["SCRIPTFLOW_V6_DB_PATH"] = "/tmp/scriptflow-v6-test.db"

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from scriptflow_v6.continuity import continuity_view
from scriptflow_v6.continuity_ledger import (
    create_entity,
    create_foreshadow,
    create_relationship,
    transition_foreshadow,
)
from scriptflow_v6.db import session_factory
from scriptflow_v6.directives import create_directive, list_directives
from scriptflow_v6.models import Project, User
from scriptflow_v6.project_planning import get_story_map
from scriptflow_v6.projects import adopt_candidate, create_project, project_view, run_task
from scriptflow_v6.schemas import (
    CreateDirective,
    CreateForeshadow,
    CreateNarrativeEntity,
    CreateProject,
    ForeshadowTransition,
    NarrativeRelationshipCommand,
)
from scriptflow_v6.writing import (
    adopt_manuscript,
    draft_opening,
    get_manuscript_unit,
    preview_next_context,
)


@pytest.mark.asyncio
async def test_project_task_decision_bootstraps_continuity(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    async with session_factory() as db:
        project = await create_project(db, CreateProject(
            title="雾港来信", goal_type="original-script",
            seed="邮差收到十年前失踪妹妹寄出的信", genre="悬疑", audience="大众",
        ))
        assert project.task is not None
        assert project.task.status == "queued"

        delivery = await run_task(db, project.id, project.task.id)
        assert delivery.status == "waiting_decision"
        assert len(delivery.candidates) == 3
        assert "mock" in delivery.status_message

        adopted = await adopt_candidate(db, project.id, delivery.candidates[0].id)
        assert adopted.status == "growing"
        assert adopted.adopted_story_core_id == delivery.candidates[0].id
        assert adopted.pulse.state == "ready"
        assert "第一" in adopted.pulse.next_action

        owner = await db.scalar(select(User).join(Project).where(Project.id == project.id))
        control = await continuity_view(db, project.id, owner.id)
        assert control.health == "stable"
        assert control.entities[0].frozen is True
        assert {item.thread_type for item in control.threads} == {"plot_promise", "emotion_arc"}
        organization = await create_entity(db, project.id, owner.id, CreateNarrativeEntity(
            entity_type="organization", name="雾港邮政局", identity="控制旧信件流转",
        ))
        await create_relationship(db, project.id, owner.id, NarrativeRelationshipCommand(
            from_entity_id=control.entities[0].id, to_entity_id=organization.id,
            relationship_type="调查对象",
        ))
        clue = await create_foreshadow(db, project.id, owner.id, CreateForeshadow(
            title="十年前的邮戳", content="日期晚于失踪时间", planned_resolve_ordinal=2,
        ))

        story_map = await get_story_map(db, project.id, owner.id)
        selected_scene = story_map.groups[0].units[0]
        opening = await draft_opening(db, project.id, owner.id, selected_scene.id)
        assert opening.status == "candidate_ready"
        assert opening.candidate is not None
        assert opening.adopted_content == ""
        assert all(item["status"] in {"pass", "notice"} for item in opening.candidate.continuity_report)
        waiting = await project_view(db, project.id, owner.id)
        assert waiting.pulse.needs_user is True

        manuscript = await adopt_manuscript(db, project.id, opening.candidate.id, owner.id)
        assert manuscript.status == "adopted"
        assert manuscript.adopted_content == opening.candidate.content
        updated_map = await get_story_map(db, project.id, owner.id)
        assert updated_map.groups[0].units[0].status == "adopted"
        assert updated_map.groups[0].units[0].manuscript_unit_id == manuscript.id
        restored = await get_manuscript_unit(db, project.id, manuscript.id, owner.id)
        assert restored.adopted_content == manuscript.adopted_content
        await transition_foreshadow(db, project.id, owner.id, clue.id, ForeshadowTransition(
            action="plant", manuscript_ordinal=1, evidence="第一场邮戳特写",
        ))
        updated_control = await continuity_view(db, project.id, owner.id)
        assert updated_control.entities[0].current_state["emotion"] == "戒备转为被迫行动"
        assert next(x for x in updated_control.threads if x.thread_type == "plot_promise").status == "planted"
        resumed = await project_view(db, project.id, owner.id)
        assert resumed.pulse.needs_user is False
        assert resumed.pulse.next_action == "规划下一章节"

        preview = await preview_next_context(db, project.id, owner.id)
        assert preview.ordinal == 2
        assert preview.previous_anchor["ordinal"] == 1
        assert preview.characters[0]["state"]["emotion"] == "戒备转为被迫行动"
        assert any(thread["status"] == "planted" for thread in preview.open_threads)
        assert preview.relationships[0]["to"] == "雾港邮政局"
        assert preview.foreshadows[0]["urgency"] == "urgent"

        directive = await create_directive(db, project.id, owner.id, CreateDirective(
            scope="next_task", target_type="manuscript_unit", target_id=1, lifetime="unit",
            instruction="下一章加强人物之间的不信任，但保留妹妹来信这一线索"))
        assert directive.status == "active"
        assert directive.target_type == "manuscript_unit"
        assert directive.target_id == 1
        assert directive.lifetime == "unit"
        second = await draft_opening(db, project.id, owner.id)
        assert second.ordinal == 2
        assert second.candidate.context_pack["previous_unit"]["ordinal"] == 1
        assert second.candidate.context_pack["user_directives"][0]["instruction"].startswith("下一章")
        ledger = await list_directives(db, project.id, owner.id)
        assert ledger[0].status == "consumed"
        assert ledger[0].consumed_by_task_id == second.candidate.task_id


@pytest.mark.asyncio
async def test_continuity_is_project_owner_scoped(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    async with session_factory() as db:
        project = await create_project(db, CreateProject(title="隔离项目", goal_type="original-novel"))
        outsider = User(public_id="outsider", display_name="Outsider")
        db.add(outsider)
        await db.commit()
        await db.refresh(outsider)
        with pytest.raises(HTTPException) as error:
            await continuity_view(db, project.id, outsider.id)
        assert error.value.status_code == 404
