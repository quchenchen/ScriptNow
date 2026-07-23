from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .cascade_revisions import create_for_change
from .models import (
    ForeshadowRecord,
    ManuscriptCandidate,
    ManuscriptUnit,
    NarrativeEntity,
    NarrativeRelationship,
    Project,
    StoryBibleChange,
    StoryBibleImpact,
    StoryMapUnit,
)
from .schemas import (
    CreateCharacterIntroduction,
    CreateForeshadowPlanChange,
    CreateRelationshipChange,
    CreateWorldRuleChange,
    StoryBibleChangeView,
    StoryBibleImpactView,
)


async def _owned_project(db: AsyncSession, project_id: int, user_id: int) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    return project


async def _view(db: AsyncSession, change: StoryBibleChange) -> StoryBibleChangeView:
    impacts = (await db.scalars(select(StoryBibleImpact).where(
        StoryBibleImpact.change_id == change.id,
    ).order_by(StoryBibleImpact.ordinal))).all()
    unaffected = await db.scalars(
        select(StoryMapUnit)
        .join(ManuscriptUnit, ManuscriptUnit.id == StoryMapUnit.manuscript_unit_id)
        .where(
            StoryMapUnit.project_id == change.project_id,
            StoryMapUnit.global_ordinal < change.effective_from_ordinal,
            ManuscriptUnit.status == "adopted",
        )
    )
    return StoryBibleChangeView(
        id=change.id,
        project_id=change.project_id,
        change_type=change.change_type,
        title=change.title,
        proposed=json.loads(change.proposed_json),
        effective_from_ordinal=change.effective_from_ordinal,
        status=change.status,
        impacts=[StoryBibleImpactView(
            story_map_unit_id=item.story_map_unit_id,
            ordinal=item.ordinal,
            artifact_state=item.artifact_state,
            proposed_action=item.proposed_action,
            status=item.status,
        ) for item in impacts],
        unaffected_adopted_before=len(unaffected.all()),
    )


async def _plan_change(
    db: AsyncSession, project_id: int, user_id: int, change_type: str,
    title: str, proposed: dict, effective_from_ordinal: int,
) -> StoryBibleChangeView:
    change = StoryBibleChange(
        project_id=project_id,
        change_type=change_type,
        title=title,
        proposed_json=json.dumps(proposed, ensure_ascii=False),
        effective_from_ordinal=effective_from_ordinal,
        created_by=user_id,
    )
    db.add(change)
    await db.flush()
    units = (await db.scalars(select(StoryMapUnit).where(
        StoryMapUnit.project_id == project_id,
        StoryMapUnit.global_ordinal >= effective_from_ordinal,
    ).order_by(StoryMapUnit.global_ordinal))).all()
    for unit in units:
        manuscript = await db.get(ManuscriptUnit, unit.manuscript_unit_id) if unit.manuscript_unit_id else None
        candidate = None
        if manuscript:
            candidate = await db.scalar(select(ManuscriptCandidate).where(
                ManuscriptCandidate.unit_id == manuscript.id,
                ManuscriptCandidate.status == "candidate",
            ).order_by(ManuscriptCandidate.id.desc()))
        if manuscript and manuscript.status == "adopted":
            artifact_state, action = "adopted_manuscript", "cascade_candidate"
        elif candidate:
            artifact_state, action = "current_candidate", "mark_stale"
        else:
            artifact_state, action = "future_plan", "future_context"
        db.add(StoryBibleImpact(
            change_id=change.id,
            project_id=project_id,
            story_map_unit_id=unit.id,
            ordinal=unit.global_ordinal,
            artifact_state=artifact_state,
            proposed_action=action,
        ))
    await db.commit()
    await db.refresh(change)
    return await _view(db, change)


async def _validate_entities(db: AsyncSession, project_id: int, entity_ids: list[int]) -> None:
    found = (await db.scalars(select(NarrativeEntity.id).where(
        NarrativeEntity.project_id == project_id,
        NarrativeEntity.id.in_(entity_ids),
    ))).all()
    if len(set(found)) != len(set(entity_ids)):
        raise HTTPException(422, "关系对象不属于当前项目")


async def create_character_introduction(
    db: AsyncSession, project_id: int, user_id: int, command: CreateCharacterIntroduction,
) -> StoryBibleChangeView:
    await _owned_project(db, project_id, user_id)
    duplicate = await db.scalar(select(NarrativeEntity.id).where(
        NarrativeEntity.project_id == project_id,
        NarrativeEntity.entity_type == "character",
        NarrativeEntity.name == command.name,
    ))
    if duplicate:
        raise HTTPException(409, "同名角色已在故事圣经中")
    if command.relationship_to_entity_id is not None:
        await _validate_entities(db, project_id, [command.relationship_to_entity_id])
    return await _plan_change(
        db, project_id, user_id, "character_introduction", f"{command.name}加入故事圣经",
        command.model_dump(), command.first_appearance_ordinal,
    )


async def create_relationship_change(
    db: AsyncSession, project_id: int, user_id: int, command: CreateRelationshipChange,
) -> StoryBibleChangeView:
    await _owned_project(db, project_id, user_id)
    if command.from_entity_id == command.to_entity_id:
        raise HTTPException(422, "关系双方必须不同")
    await _validate_entities(db, project_id, [command.from_entity_id, command.to_entity_id])
    return await _plan_change(
        db, project_id, user_id, "relationship_change", "人物关系发生变化",
        command.model_dump(), command.effective_from_ordinal,
    )


async def create_world_rule_change(
    db: AsyncSession, project_id: int, user_id: int, command: CreateWorldRuleChange,
) -> StoryBibleChangeView:
    await _owned_project(db, project_id, user_id)
    return await _plan_change(
        db, project_id, user_id, "world_rule", f"世界规则：{command.title}",
        command.model_dump(), command.effective_from_ordinal,
    )


async def create_foreshadow_plan_change(
    db: AsyncSession, project_id: int, user_id: int, command: CreateForeshadowPlanChange,
) -> StoryBibleChangeView:
    await _owned_project(db, project_id, user_id)
    if command.planned_resolve_ordinal <= command.planned_plant_ordinal:
        raise HTTPException(422, "伏笔回收位置必须晚于埋入位置")
    return await _plan_change(
        db, project_id, user_id, "foreshadow_plan", f"伏笔计划：{command.title}",
        command.model_dump(), command.planned_plant_ordinal,
    )


async def list_changes(db: AsyncSession, project_id: int, user_id: int) -> list[StoryBibleChangeView]:
    await _owned_project(db, project_id, user_id)
    items = (await db.scalars(select(StoryBibleChange).where(
        StoryBibleChange.project_id == project_id,
    ).order_by(StoryBibleChange.id.desc()))).all()
    return [await _view(db, item) for item in items]


async def _materialize_change(
    db: AsyncSession, change: StoryBibleChange, proposed: dict,
) -> None:
    source = f"Story Bible Change #{change.id}"
    if change.change_type == "character_introduction":
        entity = NarrativeEntity(
            project_id=change.project_id, entity_type="character", name=proposed["name"],
            truth_json=json.dumps({
                "identity": proposed["identity"], "narrative_function": proposed["narrative_function"],
                "voice": proposed["voice"], "first_appearance_ordinal": proposed["first_appearance_ordinal"],
            }, ensure_ascii=False),
            current_state_json=json.dumps({
                "emotion": "尚未定义", "location": "尚未定义", "goal": "", "knowledge": [],
            }, ensure_ascii=False),
            source_label=source,
        )
        db.add(entity)
        await db.flush()
        if proposed.get("relationship_to_entity_id") and proposed.get("relationship_type"):
            db.add(NarrativeRelationship(
                project_id=change.project_id, from_entity_id=entity.id,
                to_entity_id=proposed["relationship_to_entity_id"],
                relationship_type=proposed["relationship_type"],
                description=proposed.get("relationship_description", ""),
                story_time=f"第 {proposed['first_appearance_ordinal']} 单元起", source_label=source,
            ))
    elif change.change_type == "relationship_change":
        db.add(NarrativeRelationship(
            project_id=change.project_id, from_entity_id=proposed["from_entity_id"],
            to_entity_id=proposed["to_entity_id"], relationship_type=proposed["relationship_type"],
            description=json.dumps({
                "objective": proposed["objective_relationship"],
                "from_perception": proposed["from_perception"], "to_perception": proposed["to_perception"],
                "hidden_information": proposed["hidden_information"],
                "effective_from_ordinal": proposed["effective_from_ordinal"],
            }, ensure_ascii=False),
            story_time=f"第 {proposed['effective_from_ordinal']} 单元起", source_label=source,
        ))
    elif change.change_type == "world_rule":
        db.add(NarrativeEntity(
            project_id=change.project_id, entity_type="world_fact", name=proposed["title"],
            truth_json=json.dumps({
                "identity": proposed["rule"], "dramatic_constraint": proposed["dramatic_constraint"],
                "exceptions": proposed["exceptions"],
                "first_appearance_ordinal": proposed["effective_from_ordinal"],
            }, ensure_ascii=False),
            current_state_json="{}", frozen=True, source_label=source,
        ))
    else:
        db.add(ForeshadowRecord(
            project_id=change.project_id, title=proposed["title"], content=proposed["content"],
            thread_kind="foreshadow", planned_plant_ordinal=proposed["planned_plant_ordinal"],
            planned_resolve_ordinal=proposed["planned_resolve_ordinal"],
            resolution_notes=json.dumps({
                "planting_method": proposed["planting_method"],
                "reinforce_ordinals": proposed["planned_reinforce_ordinals"],
                "resolution_intent": proposed["resolution_intent"],
            }, ensure_ascii=False),
            source_label=source,
        ))


async def resolve_change(
    db: AsyncSession, project_id: int, change_id: int, user_id: int, action: str,
) -> StoryBibleChangeView:
    await _owned_project(db, project_id, user_id)
    change = await db.scalar(select(StoryBibleChange).where(
        StoryBibleChange.id == change_id,
        StoryBibleChange.project_id == project_id,
    ))
    if change is None:
        raise HTTPException(404, "故事资料变化不存在")
    if change.status != "candidate":
        raise HTTPException(409, "故事资料变化已处理")
    if action == "reject":
        change.status = "rejected"
        change.resolved_at = datetime.utcnow()
        await db.commit()
        return await _view(db, change)
    if action != "adopt":
        raise HTTPException(422, "未知动作")
    proposed = json.loads(change.proposed_json)
    await _materialize_change(db, change, proposed)
    impacts = (await db.scalars(select(StoryBibleImpact).where(
        StoryBibleImpact.change_id == change.id,
    ))).all()
    for impact in impacts:
        unit = await db.get(StoryMapUnit, impact.story_map_unit_id)
        if impact.proposed_action == "mark_stale" and unit and unit.manuscript_unit_id:
            candidates = (await db.scalars(select(ManuscriptCandidate).where(
                ManuscriptCandidate.unit_id == unit.manuscript_unit_id,
                ManuscriptCandidate.status == "candidate",
            ))).all()
            for candidate in candidates:
                candidate.status = "stale"
            unit.risk_count += 1
            impact.status = "applied"
        elif impact.proposed_action == "future_context":
            impact.status = "applied"
        else:
            impact.status = "awaiting_creator"
            if unit:
                unit.risk_count += 1
                if unit.manuscript_unit_id:
                    manuscript = await db.get(ManuscriptUnit, unit.manuscript_unit_id)
                    if manuscript and manuscript.status == "adopted":
                        await create_for_change(db, change, manuscript, proposed, user_id)
    change.status = "adopted"
    change.resolved_at = datetime.utcnow()
    await db.commit()
    return await _view(db, change)
