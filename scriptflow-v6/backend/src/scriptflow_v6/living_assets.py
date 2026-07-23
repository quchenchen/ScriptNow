from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CreativeRevision,
    ForeshadowEvent,
    ForeshadowRecord,
    LivingAssetCandidate,
    NarrativeEntity,
    NarrativeRelationship,
    NarrativeThread,
    Scene,
)
from .schemas import LivingAssetCandidateView


def view(candidate: LivingAssetCandidate) -> LivingAssetCandidateView:
    return LivingAssetCandidateView(
        id=candidate.id,
        project_id=candidate.project_id,
        revision_id=candidate.revision_id,
        asset_type=candidate.asset_type,
        title=candidate.title,
        proposed_value=json.loads(candidate.proposed_value_json),
        evidence=json.loads(candidate.evidence_json),
        autonomy_level=candidate.autonomy_level,
        status=candidate.status,
    )


def _classify(goal: str) -> tuple[str, str]:
    if "关系" in goal:
        return "relationship_change", "可能的人物关系变化"
    if "伏笔" in goal or "线索" in goal:
        return "foreshadow_event", "可能的伏笔变化"
    if "设定" in goal or "世界" in goal:
        return "world_fact", "可能的新世界事实"
    if any(word in goal for word in ("人物", "角色", "动机", "状态")):
        return "character_state", "可能的角色状态变化"
    return "timeline_event", "可能的新时间线事件"


async def extract_candidate(db: AsyncSession, revision: CreativeRevision) -> LivingAssetCandidate:
    brief = json.loads(revision.brief_json)
    context = json.loads(revision.context_pack_json)
    asset_type, title = _classify(brief["goal"])
    candidate = LivingAssetCandidate(
        project_id=revision.project_id,
        revision_id=revision.id,
        asset_type=asset_type,
        title=title,
        proposed_value_json=json.dumps({
            "revision_goal": brief["goal"],
            "before": context.get("anchors", {}).get("selected_text", ""),
            "after": revision.candidate_content,
        }, ensure_ascii=False),
        evidence_json=json.dumps([{"type": "revision", "revision_id": revision.id}], ensure_ascii=False),
    )
    db.add(candidate)
    return candidate


async def list_candidates(db: AsyncSession, project_id: int) -> list[LivingAssetCandidateView]:
    items = (await db.scalars(select(LivingAssetCandidate).where(
        LivingAssetCandidate.project_id == project_id,
    ).order_by(LivingAssetCandidate.id.desc()))).all()
    return [view(item) for item in items]


async def resolve_candidate(db: AsyncSession, project_id: int, candidate_id: int, action: str) -> LivingAssetCandidateView:
    candidate = await db.scalar(select(LivingAssetCandidate).where(
        LivingAssetCandidate.id == candidate_id,
        LivingAssetCandidate.project_id == project_id,
    ))
    if candidate is None:
        raise HTTPException(404, "Living Asset Candidate 不存在")
    if candidate.status != "candidate":
        raise HTTPException(409, "Living Asset Candidate 已处理")
    if action not in {"adopt", "reject"}:
        raise HTTPException(422, "未知动作")
    if action == "adopt":
        revision = await db.get(CreativeRevision, candidate.revision_id)
        if revision is None or revision.status != "adopted":
            raise HTTPException(409, "请先采用对应的正文 Revision")
        await _materialize(db, candidate, revision)
    candidate.status = "adopted" if action == "adopt" else "rejected"
    candidate.resolved_at = datetime.utcnow()
    await db.commit()
    return view(candidate)


async def _materialize(db: AsyncSession, candidate: LivingAssetCandidate, revision: CreativeRevision) -> None:
    value = json.loads(candidate.proposed_value_json)
    goal = value.get("revision_goal", candidate.title)
    entities = (await db.scalars(select(NarrativeEntity).where(
        NarrativeEntity.project_id == candidate.project_id,
    ).order_by(NarrativeEntity.id))).all()
    materialized_type, materialized_id = "", None
    if candidate.asset_type == "character_state":
        character = next((item for item in entities if item.entity_type == "character"), None)
        if character is None:
            raise HTTPException(409, "尚无可更新的角色，请先创建或采用角色候选")
        state = json.loads(character.current_state_json)
        state["latest_change"] = goal
        state["source_revision_id"] = revision.id
        scene = await db.get(Scene, revision.scene_id)
        state["last_changed_ordinal"] = (
            int(scene.scene_key.removeprefix("SC-"))
            if scene and scene.scene_key.startswith("SC-") else None
        )
        character.current_state_json = json.dumps(state, ensure_ascii=False)
        materialized_type, materialized_id = "narrative_entity", character.id
    elif candidate.asset_type == "relationship_change":
        if len(entities) < 2:
            raise HTTPException(409, "关系变化需要至少两个已采用实体")
        relationship = NarrativeRelationship(
            project_id=candidate.project_id,
            from_entity_id=entities[0].id,
            to_entity_id=entities[1].id,
            relationship_type="changed",
            description=goal,
            source_label=f"Revision #{revision.id}",
        )
        db.add(relationship)
        await db.flush()
        materialized_type, materialized_id = "narrative_relationship", relationship.id
    elif candidate.asset_type == "foreshadow_event":
        scene = await db.get(Scene, revision.scene_id)
        ordinal = int(scene.scene_key.removeprefix("SC-")) if scene and scene.scene_key.startswith("SC-") else None
        clue = ForeshadowRecord(
            project_id=candidate.project_id,
            title=goal[:240],
            content=value.get("before") or goal,
            status="planted",
            actual_plant_ordinal=ordinal,
            source_label=f"Revision #{revision.id}",
        )
        db.add(clue)
        await db.flush()
        db.add(ForeshadowEvent(
            foreshadow_id=clue.id,
            project_id=candidate.project_id,
            event_type="plant",
            manuscript_ordinal=ordinal,
            evidence=value.get("before", ""),
        ))
        materialized_type, materialized_id = "foreshadow", clue.id
    elif candidate.asset_type == "world_fact":
        fact = NarrativeEntity(
            project_id=candidate.project_id,
            entity_type="world_fact",
            name=goal[:200],
            truth_json=json.dumps({"identity": goal, "source_revision_id": revision.id}, ensure_ascii=False),
            current_state_json="{}",
            source_label=f"Revision #{revision.id}",
        )
        db.add(fact)
        await db.flush()
        materialized_type, materialized_id = "narrative_entity", fact.id
    else:
        event = NarrativeThread(
            project_id=candidate.project_id,
            thread_type="timeline_event",
            title=goal[:240],
            setup=value.get("before", ""),
            payoff_target="已成为采用正文中的时间线事实",
            status="recorded",
            source_label=f"Revision #{revision.id}",
        )
        db.add(event)
        await db.flush()
        materialized_type, materialized_id = "narrative_thread", event.id
    value["materialized"] = {"type": materialized_type, "id": materialized_id}
    candidate.proposed_value_json = json.dumps(value, ensure_ascii=False)
