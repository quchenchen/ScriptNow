from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ForeshadowEvent,
    ForeshadowRecord,
    ManuscriptEditRevision,
    ManuscriptImpactCandidate,
    ManuscriptUnit,
    NarrativeEntity,
    NarrativeRelationship,
    Project,
)
from .schemas import ManuscriptImpactCandidateView


def view(candidate: ManuscriptImpactCandidate) -> ManuscriptImpactCandidateView:
    return ManuscriptImpactCandidateView(
        id=candidate.id,
        project_id=candidate.project_id,
        edit_revision_id=candidate.edit_revision_id,
        unit_id=candidate.unit_id,
        impact_type=candidate.impact_type,
        title=candidate.title,
        proposed_value=json.loads(candidate.proposed_value_json),
        evidence=json.loads(candidate.evidence_json),
        status=candidate.status,
    )


def _detect_impact(revision: ManuscriptEditRevision) -> tuple[str, str] | None:
    text = f"{revision.instruction} {revision.replacement_text}"
    if any(word in text for word in ("伏笔", "线索", "暗示", "秘密", "钩子")):
        return "foreshadow_event", "正文可能新增或改变伏笔"
    if any(word in text for word in ("关系", "盟友", "敌人", "背叛", "信任", "疏远")):
        return "relationship_change", "正文可能改变人物关系"
    if any(word in text for word in ("世界", "规则", "地点", "组织制度", "技术限制", "禁忌")):
        return "world_fact", "正文可能新增世界设定"
    if any(word in text for word in ("角色", "人物", "情绪", "决定", "得知", "受伤", "目标", "动机")):
        return "character_state", "正文可能改变角色状态"
    return None


async def extract_impact_candidate(
    db: AsyncSession, revision: ManuscriptEditRevision,
) -> ManuscriptImpactCandidate | None:
    detected = _detect_impact(revision)
    if detected is None:
        return None
    impact_type, title = detected
    candidate = ManuscriptImpactCandidate(
        project_id=revision.project_id,
        edit_revision_id=revision.id,
        unit_id=revision.unit_id,
        impact_type=impact_type,
        title=title,
        proposed_value_json=json.dumps({
            "instruction": revision.instruction,
            "before": revision.selected_text,
            "after": revision.replacement_text,
        }, ensure_ascii=False),
        evidence_json=json.dumps([{
            "type": "manuscript_edit_revision", "revision_id": revision.id,
            "unit_id": revision.unit_id,
        }], ensure_ascii=False),
    )
    db.add(candidate)
    return candidate


async def list_impact_candidates(
    db: AsyncSession, project_id: int, user_id: int,
) -> list[ManuscriptImpactCandidateView]:
    owned = await db.scalar(select(Project.id).where(Project.id == project_id, Project.owner_id == user_id))
    if owned is None:
        raise HTTPException(404, "Project 不存在")
    candidates = (await db.scalars(select(ManuscriptImpactCandidate).where(
        ManuscriptImpactCandidate.project_id == project_id,
    ).order_by(ManuscriptImpactCandidate.id.desc()))).all()
    return [view(candidate) for candidate in candidates]


async def resolve_impact_candidate(
    db: AsyncSession, project_id: int, candidate_id: int, user_id: int, action: str,
) -> ManuscriptImpactCandidateView:
    candidate = await db.scalar(
        select(ManuscriptImpactCandidate)
        .join(Project, Project.id == ManuscriptImpactCandidate.project_id)
        .where(
            ManuscriptImpactCandidate.id == candidate_id,
            ManuscriptImpactCandidate.project_id == project_id,
            Project.owner_id == user_id,
        )
    )
    if candidate is None:
        raise HTTPException(404, "正文影响候选不存在")
    if candidate.status != "candidate":
        raise HTTPException(409, "正文影响候选已处理")
    if action not in {"adopt", "reject"}:
        raise HTTPException(422, "未知动作")
    if action == "adopt":
        revision = await db.get(ManuscriptEditRevision, candidate.edit_revision_id)
        if revision is None or revision.status != "adopted":
            raise HTTPException(409, "请先采用对应的正文局部修改")
        await _materialize(db, candidate, revision)
    candidate.status = "adopted" if action == "adopt" else "rejected"
    candidate.resolved_at = datetime.utcnow()
    await db.commit()
    return view(candidate)


async def _materialize(
    db: AsyncSession, candidate: ManuscriptImpactCandidate, revision: ManuscriptEditRevision,
) -> None:
    value = json.loads(candidate.proposed_value_json)
    entities = (await db.scalars(select(NarrativeEntity).where(
        NarrativeEntity.project_id == candidate.project_id,
    ).order_by(NarrativeEntity.id))).all()
    unit = await db.get(ManuscriptUnit, candidate.unit_id)
    ordinal = unit.ordinal if unit else None
    if candidate.impact_type == "character_state":
        character = next((entity for entity in entities if entity.entity_type == "character"), None)
        if character is None:
            raise HTTPException(409, "尚无可更新的角色")
        state = json.loads(character.current_state_json)
        state["latest_change"] = value.get("instruction") or candidate.title
        state["source_manuscript_edit_id"] = revision.id
        state["last_changed_ordinal"] = ordinal
        character.current_state_json = json.dumps(state, ensure_ascii=False)
    elif candidate.impact_type == "relationship_change":
        if len(entities) < 2:
            raise HTTPException(409, "关系变化需要至少两个角色或组织")
        db.add(NarrativeRelationship(
            project_id=candidate.project_id,
            from_entity_id=entities[0].id,
            to_entity_id=entities[1].id,
            relationship_type="changed",
            description=value.get("instruction") or candidate.title,
            source_label=f"Manuscript Edit #{revision.id}",
        ))
    elif candidate.impact_type == "foreshadow_event":
        clue = ForeshadowRecord(
            project_id=candidate.project_id,
            title=(value.get("instruction") or candidate.title)[:240],
            content=value.get("after", ""),
            status="planted",
            actual_plant_ordinal=ordinal,
            source_label=f"Manuscript Edit #{revision.id}",
        )
        db.add(clue)
        await db.flush()
        db.add(ForeshadowEvent(
            foreshadow_id=clue.id,
            project_id=candidate.project_id,
            event_type="plant",
            manuscript_ordinal=ordinal,
            evidence=value.get("after", ""),
        ))
    else:
        db.add(NarrativeEntity(
            project_id=candidate.project_id,
            entity_type="world_fact",
            name=(value.get("instruction") or candidate.title)[:200],
            truth_json=json.dumps({
                "identity": value.get("after", ""), "source_manuscript_edit_id": revision.id,
            }, ensure_ascii=False),
            current_state_json="{}",
            source_label=f"Manuscript Edit #{revision.id}",
        ))
