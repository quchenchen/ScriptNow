from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ContinuityAlert, NarrativeEntity, NarrativeThread, Project, StoryCoreCandidate
from .schemas import ContinuityAlertView, ContinuityView, NarrativeEntityView, NarrativeThreadView


async def bootstrap_story_core(db: AsyncSession, project: Project, candidate: StoryCoreCandidate) -> None:
    existing = await db.scalar(select(NarrativeEntity).where(NarrativeEntity.project_id == project.id))
    if existing:
        return
    source = f"Story Core #{candidate.id}"
    db.add(NarrativeEntity(
        project_id=project.id, entity_type="character", name="核心行动者",
        truth_json=json.dumps({"identity": candidate.protagonist, "dramatic_need": candidate.dramatic_question}, ensure_ascii=False),
        current_state_json=json.dumps({"emotion": "尚未定义", "knowledge": [], "location": "尚未定义"}, ensure_ascii=False),
        frozen=True, source_label=source,
    ))
    db.add_all([
        NarrativeThread(
            project_id=project.id, thread_type="plot_promise", title=candidate.dramatic_question,
            setup=candidate.conflict, payoff_target="在结局前以不可逆选择回答核心戏剧问题",
            status="planned", urgency="normal", source_label=source,
        ),
        NarrativeThread(
            project_id=project.id, thread_type="emotion_arc", title=candidate.promise,
            setup="建立角色的初始情绪防御与真实缺口", payoff_target="用行动变化而不是说明性台词完成情绪回收",
            status="planned", urgency="normal", source_label=source,
        ),
    ])
    await db.commit()


async def continuity_view(db: AsyncSession, project_id: int, user_id: int) -> ContinuityView:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    entities = (await db.scalars(select(NarrativeEntity).where(NarrativeEntity.project_id == project_id))).all()
    threads = (await db.scalars(select(NarrativeThread).where(NarrativeThread.project_id == project_id))).all()
    alerts = (await db.scalars(select(ContinuityAlert).where(
        ContinuityAlert.project_id == project_id, ContinuityAlert.status == "open"))).all()
    health = "risk" if any(x.severity == "blocking" for x in alerts) else "attention" if alerts else "stable"
    return ContinuityView(
        project_id=project_id, health=health,
        entities=[NarrativeEntityView(id=x.id, entity_type=x.entity_type, name=x.name,
            truth=json.loads(x.truth_json), current_state=json.loads(x.current_state_json),
            frozen=x.frozen, source_label=x.source_label) for x in entities],
        threads=[NarrativeThreadView(id=x.id, thread_type=x.thread_type, title=x.title,
            setup=x.setup, payoff_target=x.payoff_target, status=x.status, urgency=x.urgency,
            source_label=x.source_label) for x in threads],
        alerts=[ContinuityAlertView(id=x.id, alert_type=x.alert_type, severity=x.severity,
            message=x.message, evidence=json.loads(x.evidence_json), status=x.status) for x in alerts],
    )
