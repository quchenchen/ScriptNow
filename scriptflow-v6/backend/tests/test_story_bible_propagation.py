from __future__ import annotations

import pytest
from sqlalchemy import select

from scriptflow_v6.cascade_revisions import list_cascade_revisions, resolve_cascade_revision
from scriptflow_v6.db import session_factory
from scriptflow_v6.manuscript_documents import get_document
from scriptflow_v6.models import (
    ManuscriptCandidate,
    ManuscriptUnit,
    NarrativeEntity,
    Project,
    StoryMapUnit,
    User,
)
from scriptflow_v6.project_planning import get_story_map
from scriptflow_v6.projects import adopt_candidate, create_project, run_task
from scriptflow_v6.schemas import (
    CreateCharacterIntroduction,
    CreateForeshadowPlanChange,
    CreateProject,
    CreateRelationshipChange,
    CreateWorldRuleChange,
)
from scriptflow_v6.story_bible_changes import (
    create_character_introduction,
    create_foreshadow_plan_change,
    create_relationship_change,
    create_world_rule_change,
    resolve_change,
)
from scriptflow_v6.writing import _check_candidate, build_context_pack, draft_opening


@pytest.mark.asyncio
async def test_character_introduction_propagates_from_chapter_nine_without_rewriting_one_to_eight(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    async with session_factory() as db:
        created = await create_project(db, CreateProject(
            title="传播测试", goal_type="original-novel", seed="值夜名单失踪",
            target_volume_count=1, target_chapter_count=12,
        ))
        delivery = await run_task(db, created.id, created.task.id)
        await adopt_candidate(db, created.id, delivery.candidates[0].id)
        project = await db.get(Project, created.id)
        owner = await db.scalar(select(User).where(User.id == project.owner_id))
        story_map = await get_story_map(db, project.id, owner.id)
        units = story_map.groups[0].units

        for planned in units[:8]:
            manuscript = ManuscriptUnit(
                project_id=project.id, unit_type="chapter", ordinal=planned.global_ordinal,
                title=planned.title, adopted_content=f"第 {planned.global_ordinal} 章既有正文", status="adopted",
            )
            db.add(manuscript)
            await db.flush()
            stored = await db.get(StoryMapUnit, planned.id)
            stored.manuscript_unit_id = manuscript.id
            stored.status = "adopted"
        await db.commit()

        ninth = await draft_opening(db, project.id, owner.id, units[8].id)
        assert ninth.candidate.status == "candidate"
        change = await create_character_introduction(
            db, project.id, owner.id,
            CreateCharacterIntroduction(
                name="二丫",
                identity="值夜名单保管人的女儿",
                narrative_function="以对手身份阻止主角取得值夜名单",
                voice="短句，回避直接回答",
                first_appearance_ordinal=9,
                relationship_to_entity_id=(await db.scalar(select(NarrativeEntity.id).where(
                    NarrativeEntity.project_id == project.id,
                    NarrativeEntity.name == "核心行动者",
                ))),
                relationship_type="对手",
                relationship_description="双方争夺值夜名单，但二丫隐瞒真正动机",
            ),
        )
        assert change.status == "candidate"
        assert change.unaffected_adopted_before == 8
        assert [(item.ordinal, item.proposed_action) for item in change.impacts] == [
            (9, "mark_stale"), (10, "future_context"), (11, "future_context"), (12, "future_context"),
        ]
        assert ninth.candidate.status == "candidate"

        adopted = await resolve_change(db, project.id, change.id, owner.id, "adopt")
        assert adopted.status == "adopted"
        stale = await db.get(ManuscriptCandidate, ninth.candidate.id)
        assert stale.status == "stale"
        before = await build_context_pack(db, project, 8)
        from_nine = await build_context_pack(db, project, 9)
        assert all(item["name"] != "二丫" for item in before["entities"])
        assert next(item for item in from_nine["entities"] if item["name"] == "二丫")["truth"]["narrative_function"].startswith("以对手身份")
        assert any(item["from"] == "二丫" and item["type"] == "对手" for item in from_nine["relationships"])
        regenerated = await draft_opening(db, project.id, owner.id, units[8].id)
        assert regenerated.id == ninth.id
        assert regenerated.candidate.id != ninth.candidate.id
        assert "二丫" in regenerated.candidate.content
        evidence = [item for item in regenerated.candidate.continuity_report
            if item["check"] == "story_fact_evidence"]
        assert evidence[0]["status"] == "pass"
        assert evidence[0]["label"] == "二丫"
        unchanged = (await db.scalars(select(ManuscriptUnit).where(
            ManuscriptUnit.project_id == project.id,
            ManuscriptUnit.ordinal <= 8,
        ).order_by(ManuscriptUnit.ordinal))).all()
        assert [item.adopted_content for item in unchanged] == [f"第 {index} 章既有正文" for index in range(1, 9)]


@pytest.mark.asyncio
async def test_adopted_manuscript_gets_reviewable_cascade_revision_before_any_overwrite(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    async with session_factory() as db:
        created = await create_project(db, CreateProject(
            title="Cascade 测试", goal_type="original-novel", seed="名单争夺",
            target_volume_count=1, target_chapter_count=10,
        ))
        delivery = await run_task(db, created.id, created.task.id)
        await adopt_candidate(db, created.id, delivery.candidates[0].id)
        project = await db.get(Project, created.id)
        owner = await db.scalar(select(User).where(User.id == project.owner_id))
        story_map = await get_story_map(db, project.id, owner.id)
        target = story_map.groups[0].units[8]
        manuscript = ManuscriptUnit(
            project_id=project.id, unit_type="chapter", ordinal=9,
            title="第九章", adopted_content="主角走向值夜室。", status="adopted",
        )
        db.add(manuscript)
        await db.flush()
        stored = await db.get(StoryMapUnit, target.id)
        stored.manuscript_unit_id = manuscript.id
        stored.status = "adopted"
        await db.commit()
        baseline = await get_document(db, project.id, manuscript.id, owner.id)
        core_id = await db.scalar(select(NarrativeEntity.id).where(
            NarrativeEntity.project_id == project.id,
            NarrativeEntity.name == "核心行动者",
        ))
        change = await create_character_introduction(
            db, project.id, owner.id,
            CreateCharacterIntroduction(
                name="二丫", narrative_function="阻止主角取得值夜名单",
                first_appearance_ordinal=9, relationship_to_entity_id=core_id,
                relationship_type="对手",
            ),
        )
        assert change.impacts[0].proposed_action == "cascade_candidate"
        await resolve_change(db, project.id, change.id, owner.id, "adopt")
        revisions = await list_cascade_revisions(db, project.id, owner.id)
        assert len(revisions) == 1
        assert revisions[0].status == "candidate"
        assert revisions[0].original_content == baseline.content
        assert "二丫" in revisions[0].candidate_content
        assert revisions[0].evidence[0]["status"] == "present"
        assert (await get_document(db, project.id, manuscript.id, owner.id)).version == 1

        adopted = await resolve_cascade_revision(db, project.id, revisions[0].id, owner.id, "adopt")
        assert adopted.status == "adopted"
        updated = await get_document(db, project.id, manuscript.id, owner.id)
        assert updated.version == 2
        assert "二丫" in updated.content


@pytest.mark.asyncio
async def test_relationship_world_rule_and_foreshadow_share_scoped_change_protocol(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    async with session_factory() as db:
        created = await create_project(db, CreateProject(
            title="通用传播", goal_type="original-novel", seed="封闭城镇",
            target_volume_count=1, target_chapter_count=5,
        ))
        delivery = await run_task(db, created.id, created.task.id)
        await adopt_candidate(db, created.id, delivery.candidates[0].id)
        project = await db.get(Project, created.id)
        owner = await db.scalar(select(User).where(User.id == project.owner_id))
        core = await db.scalar(select(NarrativeEntity).where(
            NarrativeEntity.project_id == project.id,
            NarrativeEntity.name == "核心行动者",
        ))
        second = NarrativeEntity(
            project_id=project.id, entity_type="character", name="守门人",
            truth_json='{"identity":"城门守卫"}', current_state_json="{}",
        )
        db.add(second)
        await db.commit()
        await db.refresh(second)

        relationship = await create_relationship_change(
            db, project.id, owner.id,
            CreateRelationshipChange(
                from_entity_id=second.id, to_entity_id=core.id, relationship_type="监视者",
                objective_relationship="守门人奉命监视主角", from_perception="目标人物",
                to_perception="普通守卫", hidden_information="命令来自议会",
                effective_from_ordinal=3,
            ),
        )
        world = await create_world_rule_change(
            db, project.id, owner.id,
            CreateWorldRuleChange(
                title="日落封城", rule="日落后城门无法开启",
                dramatic_constraint="所有逃离行动必须在日落前完成", effective_from_ordinal=4,
            ),
        )
        foreshadow = await create_foreshadow_plan_change(
            db, project.id, owner.id,
            CreateForeshadowPlanChange(
                title="缺角通行证", content="通行证右下角被撕掉",
                planting_method="第二章检查证件时给特写", planned_plant_ordinal=2,
                planned_reinforce_ordinals=[3], planned_resolve_ordinal=5,
                resolution_intent="证明守门人早已替换通行证",
            ),
        )
        assert all(item.proposed_action == "future_context" for item in relationship.impacts)
        for change in (relationship, world, foreshadow):
            await resolve_change(db, project.id, change.id, owner.id, "adopt")

        chapter_two = await build_context_pack(db, project, 2)
        chapter_three = await build_context_pack(db, project, 3)
        chapter_four = await build_context_pack(db, project, 4)
        assert any(item["title"] == "缺角通行证" for item in chapter_two["foreshadows"])
        assert not chapter_two["relationships"]
        assert any(item["type"] == "监视者" for item in chapter_three["relationships"])
        assert all(item["name"] != "日落封城" for item in chapter_three["entities"])
        assert any(item["name"] == "日落封城" for item in chapter_four["entities"])

        story_map = await get_story_map(db, project.id, owner.id)
        chapter_two_candidate = await draft_opening(db, project.id, owner.id, story_map.groups[0].units[1].id)
        evidence = [item for item in chapter_two_candidate.candidate.continuity_report
            if item["check"] == "story_fact_evidence"]
        assert evidence[0]["status"] == "pass"
        assert evidence[0]["label"] == "缺角通行证"
        assert evidence[0]["start"] >= 0
        assert "缺角通行证" in evidence[0]["excerpt"]

        missing = _check_candidate("这段正文完全没有使用指定信息。" * 5, chapter_two)
        missing_evidence = [item for item in missing if item["check"] == "story_fact_evidence"]
        assert missing_evidence[0]["status"] == "blocking"
