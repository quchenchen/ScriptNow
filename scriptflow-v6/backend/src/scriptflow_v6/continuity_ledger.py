from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ForeshadowEvent,
    ForeshadowRecord,
    ManuscriptUnit,
    NarrativeEntity,
    NarrativeRelationship,
    Project,
)
from .schemas import (
    CreateForeshadow,
    CreateNarrativeEntity,
    ForeshadowTransition,
    ForeshadowView,
    NarrativeEntityView,
    NarrativeRelationshipCommand,
    NarrativeRelationshipView,
)


async def _owned_project(db: AsyncSession, project_id: int, user_id: int) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    return project


def entity_view(entity: NarrativeEntity) -> NarrativeEntityView:
    return NarrativeEntityView(
        id=entity.id,
        entity_type=entity.entity_type,
        name=entity.name,
        truth=json.loads(entity.truth_json),
        current_state=json.loads(entity.current_state_json),
        frozen=entity.frozen,
        source_label=entity.source_label,
    )


async def create_entity(db: AsyncSession, project_id: int, user_id: int, command: CreateNarrativeEntity) -> NarrativeEntityView:
    await _owned_project(db, project_id, user_id)
    duplicate = await db.scalar(select(NarrativeEntity).where(
        NarrativeEntity.project_id == project_id,
        NarrativeEntity.entity_type == command.entity_type,
        NarrativeEntity.name == command.name,
    ))
    if duplicate:
        raise HTTPException(409, "同名叙事实体已存在")
    entity = NarrativeEntity(
        project_id=project_id,
        entity_type=command.entity_type,
        name=command.name,
        truth_json=json.dumps({"identity": command.identity}, ensure_ascii=False),
        current_state_json=json.dumps({
            "emotion": command.emotion,
            "location": command.location,
            "goal": command.goal,
            "knowledge": [],
        }, ensure_ascii=False),
        source_label="manual",
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity_view(entity)


async def create_relationship(
    db: AsyncSession, project_id: int, user_id: int, command: NarrativeRelationshipCommand,
) -> NarrativeRelationshipView:
    await _owned_project(db, project_id, user_id)
    entities = (await db.scalars(select(NarrativeEntity).where(
        NarrativeEntity.project_id == project_id,
        NarrativeEntity.id.in_([command.from_entity_id, command.to_entity_id]),
    ))).all()
    if len(entities) != 2 or command.from_entity_id == command.to_entity_id:
        raise HTTPException(422, "关系双方必须是项目内不同实体")
    relationship = NarrativeRelationship(
        project_id=project_id,
        from_entity_id=command.from_entity_id,
        to_entity_id=command.to_entity_id,
        relationship_type=command.relationship_type,
        description=command.description,
        story_time=command.story_time,
    )
    db.add(relationship)
    await db.commit()
    await db.refresh(relationship)
    names = {item.id: item.name for item in entities}
    return relationship_view(relationship, names)


def relationship_view(item: NarrativeRelationship, names: dict[int, str]) -> NarrativeRelationshipView:
    return NarrativeRelationshipView(
        id=item.id,
        from_entity_id=item.from_entity_id,
        from_name=names[item.from_entity_id],
        to_entity_id=item.to_entity_id,
        to_name=names[item.to_entity_id],
        relationship_type=item.relationship_type,
        status=item.status,
        description=item.description,
        story_time=item.story_time,
    )


async def list_relationships(db: AsyncSession, project_id: int, user_id: int) -> list[NarrativeRelationshipView]:
    await _owned_project(db, project_id, user_id)
    entities = (await db.scalars(select(NarrativeEntity).where(NarrativeEntity.project_id == project_id))).all()
    names = {item.id: item.name for item in entities}
    items = (await db.scalars(select(NarrativeRelationship).where(
        NarrativeRelationship.project_id == project_id,
    ).order_by(NarrativeRelationship.id))).all()
    return [relationship_view(item, names) for item in items]


async def _current_ordinal(db: AsyncSession, project_id: int) -> int:
    latest = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project_id,
        ManuscriptUnit.status == "adopted",
    ).order_by(ManuscriptUnit.ordinal.desc()))
    return latest.ordinal if latest else 0


def urgency(item: ForeshadowRecord, current_ordinal: int) -> str:
    if item.status not in {"planted", "reinforced", "partially_resolved"} or item.planned_resolve_ordinal is None:
        return "normal"
    remaining = item.planned_resolve_ordinal - current_ordinal
    if remaining < 0:
        return "overdue"
    if remaining <= 1:
        return "urgent"
    if remaining <= item.remind_before_units:
        return "attention"
    return "normal"


async def foreshadow_view(db: AsyncSession, item: ForeshadowRecord, current_ordinal: int) -> ForeshadowView:
    events = (await db.scalars(select(ForeshadowEvent).where(
        ForeshadowEvent.foreshadow_id == item.id,
    ).order_by(ForeshadowEvent.id))).all()
    return ForeshadowView(
        id=item.id,
        title=item.title,
        content=item.content,
        thread_kind=item.thread_kind,
        status=item.status,
        planned_plant_ordinal=item.planned_plant_ordinal,
        actual_plant_ordinal=item.actual_plant_ordinal,
        planned_resolve_ordinal=item.planned_resolve_ordinal,
        actual_resolve_ordinal=item.actual_resolve_ordinal,
        importance=item.importance,
        subtlety=item.subtlety,
        remind_before_units=item.remind_before_units,
        related_entity_ids=json.loads(item.related_entity_ids_json),
        resolution_notes=item.resolution_notes,
        urgency=urgency(item, current_ordinal),
        events=[{"event_type": event.event_type, "manuscript_ordinal": event.manuscript_ordinal,
            "evidence": event.evidence} for event in events],
    )


async def create_foreshadow(
    db: AsyncSession, project_id: int, user_id: int, command: CreateForeshadow,
) -> ForeshadowView:
    await _owned_project(db, project_id, user_id)
    if command.related_entity_ids:
        count = len((await db.scalars(select(NarrativeEntity.id).where(
            NarrativeEntity.project_id == project_id,
            NarrativeEntity.id.in_(command.related_entity_ids),
        ))).all())
        if count != len(set(command.related_entity_ids)):
            raise HTTPException(422, "关联实体不属于当前项目")
    item = ForeshadowRecord(
        project_id=project_id,
        title=command.title,
        content=command.content,
        thread_kind=command.thread_kind,
        planned_plant_ordinal=command.planned_plant_ordinal,
        planned_resolve_ordinal=command.planned_resolve_ordinal,
        importance=command.importance,
        subtlety=command.subtlety,
        remind_before_units=command.remind_before_units,
        related_entity_ids_json=json.dumps(command.related_entity_ids),
        resolution_notes=command.resolution_notes,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await foreshadow_view(db, item, await _current_ordinal(db, project_id))


async def list_foreshadows(db: AsyncSession, project_id: int, user_id: int) -> list[ForeshadowView]:
    await _owned_project(db, project_id, user_id)
    current = await _current_ordinal(db, project_id)
    items = (await db.scalars(select(ForeshadowRecord).where(
        ForeshadowRecord.project_id == project_id,
    ).order_by(ForeshadowRecord.id))).all()
    return [await foreshadow_view(db, item, current) for item in items]


TRANSITIONS = {
    "queue": ({"planned"}, "pending"),
    "plant": ({"planned", "pending"}, "planted"),
    "reinforce": ({"planted", "reinforced", "partially_resolved"}, "reinforced"),
    "partial_resolve": ({"planted", "reinforced", "partially_resolved"}, "partially_resolved"),
    "resolve": ({"planted", "reinforced", "partially_resolved"}, "resolved"),
    "abandon": ({"planned", "planted", "reinforced", "partially_resolved"}, "abandoned"),
}


async def transition_foreshadow(
    db: AsyncSession, project_id: int, user_id: int, foreshadow_id: int, command: ForeshadowTransition,
) -> ForeshadowView:
    await _owned_project(db, project_id, user_id)
    item = await db.scalar(select(ForeshadowRecord).where(
        ForeshadowRecord.id == foreshadow_id,
        ForeshadowRecord.project_id == project_id,
    ))
    if item is None:
        raise HTTPException(404, "伏笔不存在")
    allowed, target = TRANSITIONS[command.action]
    if item.status not in allowed:
        raise HTTPException(409, f"不能从 {item.status} 执行 {command.action}")
    item.status = target
    if command.action == "plant":
        item.actual_plant_ordinal = command.manuscript_ordinal
    if command.action == "resolve":
        item.actual_resolve_ordinal = command.manuscript_ordinal
    db.add(ForeshadowEvent(
        foreshadow_id=item.id,
        project_id=project_id,
        event_type=command.action,
        manuscript_ordinal=command.manuscript_ordinal,
        evidence=command.evidence,
    ))
    await db.commit()
    return await foreshadow_view(db, item, await _current_ordinal(db, project_id))
