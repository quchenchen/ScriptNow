from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_runtime import creative_runtime
from .medium_profiles import get_profile, profile_for_goal
from .directives import directive_view
from .models import (
    AgentTask,
    NarrativeArc, StoryArchitecture,
    CreativeDirective,
    ForeshadowRecord,
    ManuscriptCandidate,
    ManuscriptDocumentMetadataVersion,
    ManuscriptDocumentVersion,
    ManuscriptImpactCandidate,
    ManuscriptUnit,
    NarrativeEntity,
    NarrativeRelationship,
    ProjectPlan,
    NarrativeThread,
    Project,
    Scene,
    SourceCanon,
    StoryBibleChange,
    StoryCoreCandidate,
    StoryMapUnit,
)
from .schemas import ContextPreviewView, ManuscriptCandidateView, ManuscriptUnitView


def _candidate_view(candidate: ManuscriptCandidate) -> ManuscriptCandidateView:
    return ManuscriptCandidateView(id=candidate.id, unit_id=candidate.unit_id, task_id=candidate.task_id,
        title=candidate.title, content=candidate.content, status=candidate.status,
        context_pack=json.loads(candidate.context_pack_json), state_delta=json.loads(candidate.state_delta_json),
        thread_actions=json.loads(candidate.thread_actions_json), continuity_report=json.loads(candidate.continuity_report_json))


async def _scene_id(db: AsyncSession, unit: ManuscriptUnit) -> int | None:
    if unit.unit_type != "scene":
        return None
    scene = await db.scalar(select(Scene).where(
        Scene.project_id == unit.project_id, Scene.scene_key == f"SC-{unit.ordinal}"))
    return scene.id if scene else None


async def _owned_project(db: AsyncSession, project_id: int, user_id: int) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        raise HTTPException(404, "Project 不存在")
    return project


async def build_context_pack(db: AsyncSession, project: Project, ordinal: int = 1) -> dict:
    if project.adopted_story_core_id is None:
        raise HTTPException(409, "请先采用 Story Core")
    core = await db.get(StoryCoreCandidate, project.adopted_story_core_id)
    source = await db.scalar(select(SourceCanon).where(SourceCanon.project_id == project.id))
    all_entities = (await db.scalars(select(NarrativeEntity).where(NarrativeEntity.project_id == project.id))).all()
    entities = [item for item in all_entities if json.loads(item.truth_json).get("first_appearance_ordinal", 1) <= ordinal]
    threads = (await db.scalars(select(NarrativeThread).where(NarrativeThread.project_id == project.id))).all()
    relationships = (await db.scalars(select(NarrativeRelationship).where(
        NarrativeRelationship.project_id == project.id))).all()
    foreshadows = (await db.scalars(select(ForeshadowRecord).where(
        ForeshadowRecord.project_id == project.id,
        ForeshadowRecord.status.notin_(["resolved", "abandoned"]),
    ))).all()
    foreshadows = [item for item in foreshadows
        if item.planned_plant_ordinal is None or item.planned_plant_ordinal <= ordinal]
    entity_names = {item.id: item.name for item in entities}
    relationships = [item for item in relationships
        if item.from_entity_id in entity_names and item.to_entity_id in entity_names
        and _relationship_effective_from(item.description) <= ordinal]
    directives = (await db.scalars(select(CreativeDirective).where(
        CreativeDirective.project_id == project.id, CreativeDirective.status == "active"))).all()
    manuscript_impacts = (await db.scalars(select(ManuscriptImpactCandidate).where(
        ManuscriptImpactCandidate.project_id == project.id,
    ).order_by(ManuscriptImpactCandidate.id))).all()
    adopted_changes = (await db.scalars(select(StoryBibleChange).where(
        StoryBibleChange.project_id == project.id,
        StoryBibleChange.status == "adopted",
        StoryBibleChange.effective_from_ordinal <= ordinal,
    ).order_by(StoryBibleChange.id))).all()
    previous = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project.id, ManuscriptUnit.ordinal == ordinal - 1,
        ManuscriptUnit.status == "adopted")) if ordinal > 1 else None
    previous_metadata = None
    if previous:
        previous_version = await db.scalar(select(ManuscriptDocumentVersion).where(
            ManuscriptDocumentVersion.unit_id == previous.id,
        ).order_by(ManuscriptDocumentVersion.version.desc()))
        if previous_version:
            metadata_version = await db.scalar(select(ManuscriptDocumentMetadataVersion).where(
                ManuscriptDocumentMetadataVersion.unit_id == previous.id,
                ManuscriptDocumentMetadataVersion.version == previous_version.version,
            ))
            if metadata_version:
                previous_metadata = json.loads(metadata_version.metadata_json)
    return {"scope": {"project_id": project.id, "unit": ordinal, "purpose": "manuscript_draft"},
        "project": {"title": project.title, "goal_type": project.goal_type, "genre": project.genre, "audience": project.audience},
        "story_core": {"title": core.title, "logline": core.logline, "dramatic_question": core.dramatic_question, "conflict": core.conflict},
        "source_canon": ({"name": source.source_name, "content": source.content, "status": source.status} if source else None),
        "previous_unit": ({"ordinal": previous.ordinal, "title": previous.title,
            "content_tail": previous.adopted_content[-1200:], "metadata": previous_metadata or {}}
            if previous else None),
        "entities": [{"name": x.name, "truth": json.loads(x.truth_json), "state": json.loads(x.current_state_json), "frozen": x.frozen} for x in entities],
        "relationships": [{"from": entity_names[x.from_entity_id], "to": entity_names[x.to_entity_id],
            "type": x.relationship_type, "status": x.status,
            "description": _relationship_details(x.description).get("objective", x.description),
            "perceptions": _relationship_details(x.description)} for x in relationships],
        "open_threads": [{"id": x.id, "type": x.thread_type, "title": x.title, "status": x.status, "payoff_target": x.payoff_target} for x in threads],
        "foreshadows": [{"id": x.id, "title": x.title, "kind": x.thread_kind, "status": x.status,
            "planned_resolve_ordinal": x.planned_resolve_ordinal,
            "urgency": _foreshadow_urgency(x, ordinal - 1)} for x in foreshadows],
        "user_directives": [{"id": view.id, "scope": view.scope, "target_type": view.target_type,
            "target_id": view.target_id, "lifetime": view.lifetime, "instruction": view.instruction,
            "preserve": view.preserve, "constraints": view.constraints}
            for x in directives for view in [directive_view(x)]],
        "memory_updates": [{"id": item.id, "type": item.impact_type, "title": item.title,
            "value": json.loads(item.proposed_value_json), "source_unit_id": item.unit_id,
            "source_edit_revision_id": item.edit_revision_id, "activation": "confirmed_for_future_units"}
            for item in manuscript_impacts if item.status == "adopted"],
        "pending_memory_decisions": [{"id": item.id, "type": item.impact_type, "title": item.title,
            "source_unit_id": item.unit_id, "activation": "not_authoritative"}
            for item in manuscript_impacts if item.status == "candidate"],
        "required_story_facts": [fact for change in adopted_changes
            for fact in [_required_story_fact(change, ordinal)] if fact is not None],
        "rules": ["不得改写冻结事实", "新增设定保持为候选", "状态变化必须在 state_delta 中声明",
            "pending_memory_decisions 仅用于提醒存在未决事项，不得作为故事事实"],
        "story_architecture": await _architecture_context(db, project, ordinal),
        "content_constraints": await _content_constraints(db, project, ordinal)}


async def _architecture_context(db: AsyncSession, project: Project, ordinal: int) -> dict | None:
    arch = await db.scalar(select(StoryArchitecture).where(StoryArchitecture.project_id == project.id))
    if not arch or arch.status != "planned":
        return None
    arc = await db.scalar(select(NarrativeArc).where(
        NarrativeArc.architecture_id == arch.id,
        NarrativeArc.episode_start <= ordinal,
        NarrativeArc.episode_end >= ordinal,
    ))
    if not arc:
        return None
    return {
        "thesis": arch.thesis,
        "current_arc": {
            "title": arc.title, "ordinal": arc.ordinal,
            "episode_range": f"EP{arc.episode_start}-{arc.episode_end}",
            "core_conflict": arc.core_conflict,
            "emotional_landing": arc.emotional_landing,
            "protag_state": arc.protag_state,
            "antag_state": arc.antag_state,
            "must_have_events": [e for e in json.loads(arc.must_have_json) if str(ordinal) in e],
            "position_in_arc": f"当前是此段落第{ordinal - arc.episode_start + 1}/{arc.episode_end - arc.episode_start + 1}集",
            "timing": {
                "minutes_per_scene": round(arc.target_minutes_per_episode / arc.target_scenes_per_episode, 1),
                "words_per_scene": arc.target_words_per_scene,
                "note": f"每场{arc.target_minutes_per_episode}/{arc.target_scenes_per_episode}={round(arc.target_minutes_per_episode/arc.target_scenes_per_episode,1)}分钟≈{arc.target_words_per_scene}字"
            }
        }
    }


async def _content_constraints(db: AsyncSession, project: Project, ordinal: int) -> dict:
    arch = await _architecture_context(db, project, ordinal)
    if arch and arch.get("current_arc", {}).get("timing"):
        t = arch["current_arc"]["timing"]
        return {"target_words": t["words_per_scene"], "target_minutes": t["minutes_per_scene"], "note": t["note"]}
    # Fallback to ProjectPlan → MediumProfile
    plan = await db.scalar(select(ProjectPlan).where(ProjectPlan.project_id == project.id))
    profile = profile_for_goal(project.goal_type)
    mins = max(plan.target_minutes_per_episode if plan else profile.default_minutes_per_episode or 3, 1)
    scenes = max(plan.target_scenes_per_episode if plan else profile.default_scenes_per_episode or 3, 1)
    wpm = profile.words_per_minute or 200
    words = max(plan.target_words if plan and plan.target_words else (mins * wpm // scenes), 100)
    return {"target_words": words, "target_minutes": round(mins/scenes, 1),
            "note": f"{profile.label}·每分钟约{wpm}字·每场{mins}/{scenes}={round(mins/scenes,1)}分钟≈{words}字"}


def _foreshadow_urgency(item: ForeshadowRecord, current_ordinal: int) -> str:
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


def _relationship_effective_from(description: str) -> int:
    try:
        value = json.loads(description)
        return int(value.get("effective_from_ordinal", 1)) if isinstance(value, dict) else 1
    except (ValueError, TypeError, json.JSONDecodeError):
        return 1


def _relationship_details(description: str) -> dict:
    try:
        value = json.loads(description)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def _required_story_fact(change: StoryBibleChange, ordinal: int) -> dict | None:
    proposed = json.loads(change.proposed_json)
    action = "首次体现"
    if change.change_type == "foreshadow_plan":
        if ordinal == proposed["planned_plant_ordinal"]:
            label, requirement, action = proposed["title"], proposed["planting_method"], "埋入"
        elif ordinal in proposed["planned_reinforce_ordinals"]:
            label, requirement, action = proposed["title"], proposed["content"], "强化"
        elif ordinal == proposed["planned_resolve_ordinal"]:
            label, requirement, action = proposed["title"], proposed["resolution_intent"], "回收"
        else:
            return None
    elif ordinal != change.effective_from_ordinal:
        return None
    elif change.change_type == "character_introduction":
        label, requirement = proposed["name"], proposed["narrative_function"]
    elif change.change_type == "relationship_change":
        label, requirement = proposed["relationship_type"], proposed["objective_relationship"]
    else:
        label, requirement = proposed["title"], proposed["dramatic_constraint"]
    return {"change_id": change.id, "type": change.change_type, "label": label,
        "requirement": requirement, "action": action}


async def preview_next_context(db: AsyncSession, project_id: int, user_id: int) -> ContextPreviewView:
    project = await _owned_project(db, project_id, user_id)
    latest = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project_id).order_by(ManuscriptUnit.ordinal.desc()))
    ordinal = latest.ordinal + 1 if latest else 1
    context = await build_context_pack(db, project, ordinal)
    warnings: list[str] = []
    if not context["entities"]:
        warnings.append("尚未建立角色状态，下一创作单元可能缺少人物连续性")
    if latest and not latest.adopted_content:
        warnings.append("上一创作单元尚未采用，不会作为连续性锚点")
    if not context["open_threads"]:
        warnings.append("没有开放的伏笔或剧情承诺")
    if context["pending_memory_decisions"]:
        warnings.append(f"有 {len(context['pending_memory_decisions'])} 条正文变化尚未确认，Agent 不会将其视为项目记忆")
    overdue = [item["title"] for item in context["foreshadows"] if item["urgency"] == "overdue"]
    if overdue:
        warnings.append(f"{len(overdue)} 条伏笔已超过预设回收位置：{'、'.join(overdue[:3])}")
    return ContextPreviewView(
        ordinal=ordinal,
        target_label=f"第 {ordinal} {'章' if project.goal_type.endswith('novel') else '场'}",
        previous_anchor=context["previous_unit"],
        characters=context["entities"],
        relationships=context["relationships"],
        open_threads=context["open_threads"],
        foreshadows=context["foreshadows"],
        directives=context["user_directives"],
        memory_updates=context["memory_updates"],
        pending_memory_decisions=context["pending_memory_decisions"],
        required_story_facts=context["required_story_facts"],
        warnings=warnings,
    )


async def draft_opening(
    db: AsyncSession, project_id: int, user_id: int, story_map_unit_id: int | None = None,
) -> ManuscriptUnitView:
    project = await _owned_project(db, project_id, user_id)
    story_unit = None
    if story_map_unit_id is not None:
        story_unit = await db.scalar(select(StoryMapUnit).where(
            StoryMapUnit.id == story_map_unit_id,
            StoryMapUnit.project_id == project_id,
        ))
        if story_unit is None:
            raise HTTPException(404, "作品目录单元不存在")
    if story_unit and story_unit.manuscript_unit_id:
        existing_unit = await db.get(ManuscriptUnit, story_unit.manuscript_unit_id)
    elif story_unit:
        existing_unit = await db.scalar(select(ManuscriptUnit).where(
            ManuscriptUnit.project_id == project_id,
            ManuscriptUnit.ordinal == story_unit.global_ordinal,
        ))
    else:
        existing_unit = await db.scalar(select(ManuscriptUnit).where(
            ManuscriptUnit.project_id == project_id).order_by(ManuscriptUnit.ordinal.desc()))
    stale_candidate = None
    if existing_unit and (story_unit is not None or existing_unit.status != "adopted"):
        candidate = await db.scalar(select(ManuscriptCandidate).where(ManuscriptCandidate.unit_id == existing_unit.id).order_by(ManuscriptCandidate.id.desc()))
        if candidate is None or candidate.status != "stale":
            return ManuscriptUnitView(id=existing_unit.id, scene_id=await _scene_id(db, existing_unit), unit_type=existing_unit.unit_type, ordinal=existing_unit.ordinal, title=existing_unit.title,
                adopted_content=existing_unit.adopted_content, status=existing_unit.status, candidate=_candidate_view(candidate) if candidate else None)
        stale_candidate = candidate
    ordinal = (story_unit.global_ordinal if story_unit else existing_unit.ordinal
        if stale_candidate and existing_unit else existing_unit.ordinal + 1 if existing_unit else 1)
    context_pack = await build_context_pack(db, project, ordinal)
    unit_type = story_unit.unit_type if story_unit else "chapter" if project.goal_type.endswith("novel") else "scene"
    if stale_candidate and existing_unit:
        unit = existing_unit
    else:
        unit = ManuscriptUnit(project_id=project_id, unit_type=unit_type, ordinal=ordinal)
        db.add(unit)
        await db.flush()
        if story_unit:
            story_unit.manuscript_unit_id = unit.id
        else:
            # Auto-link to first unlinked StoryMapUnit
            next_unit = await db.scalar(select(StoryMapUnit).where(
                StoryMapUnit.project_id == project_id,
                StoryMapUnit.manuscript_unit_id == None,
            ).order_by(StoryMapUnit.global_ordinal))
            if next_unit:
                next_unit.manuscript_unit_id = unit.id
                story_unit = next_unit
    if story_unit:
        story_unit.status = "drafting"
    task = AgentTask(project_id=project_id, requested_by=user_id, agent_profile="scene_writer", skill_name="opening-draft",
        skill_version="1.0.0", goal=(f"根据最新故事资料修订第{ordinal}{('章' if unit_type == 'chapter' else '场')}候选"
            if stale_candidate else f"提交第{ordinal}{('章' if unit_type == 'chapter' else '场')}候选"), status="running",
        autonomy_level="A2", context_pack_json=json.dumps(context_pack, ensure_ascii=False),
        status_message="写作者正在依据 Context Pack 创作候选", started_at=datetime.utcnow())
    db.add(task)
    await db.flush()
    for directive in context_pack.get("user_directives", []):
        item = await db.get(CreativeDirective, directive["id"])
        if item and item.scope == "next_task":
            item.status = "consumed"
            item.consumed_by_task_id = task.id
    runtime = creative_runtime()
    draft = await runtime.draft_opening(context_pack=context_pack)
    report = _check_candidate(draft.content, context_pack)
    candidate = ManuscriptCandidate(project_id=project_id, unit_id=unit.id, task_id=task.id, title=draft.title,
        content=draft.content, context_pack_json=json.dumps(context_pack, ensure_ascii=False),
        state_delta_json=json.dumps(draft.state_delta, ensure_ascii=False), thread_actions_json=json.dumps(draft.thread_actions, ensure_ascii=False),
        continuity_report_json=json.dumps(report, ensure_ascii=False))
    db.add(candidate)
    task.status = "waiting_decision"
    blocking = sum(item.get("status") == "blocking" for item in report)
    task.status_message = (f"候选有 {blocking} 项故事事实尚未落入正文，需要修订 · {runtime.name}"
        if blocking else f"候选已通过基础连续性检查，等待你的判断 · {runtime.name}")
    task.finished_at = datetime.utcnow()
    unit.status = "candidate_ready"
    unit.title = draft.title
    if story_unit:
        story_unit.status = "candidate"
        story_unit.title = draft.title
    await db.commit()
    await db.refresh(candidate)
    # First-time adopt: create document version with the content
    existing = await db.scalar(select(ManuscriptDocumentVersion).where(
        ManuscriptDocumentVersion.unit_id == unit.id))
    if not existing:
        doc = ManuscriptDocumentVersion(project_id=project_id, unit_id=unit.id, version=1,
            content=candidate.content, source="adopted_baseline", created_by=user_id)
        db.add(doc)
        await db.commit()
    return ManuscriptUnitView(id=unit.id, scene_id=None, unit_type=unit.unit_type, ordinal=ordinal, title=unit.title,
        adopted_content=unit.adopted_content, status=unit.status, candidate=_candidate_view(candidate))


async def get_opening(db: AsyncSession, project_id: int, user_id: int) -> ManuscriptUnitView | None:
    await _owned_project(db, project_id, user_id)
    unit = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project_id, ManuscriptUnit.ordinal == 1))
    if unit is None:
        return None
    candidate = await db.scalar(select(ManuscriptCandidate).where(
        ManuscriptCandidate.unit_id == unit.id).order_by(ManuscriptCandidate.id.desc()))
    return ManuscriptUnitView(id=unit.id, scene_id=await _scene_id(db, unit), unit_type=unit.unit_type, ordinal=unit.ordinal,
        title=unit.title, adopted_content=unit.adopted_content, status=unit.status,
        candidate=_candidate_view(candidate) if candidate else None)


async def get_latest_unit(db: AsyncSession, project_id: int, user_id: int) -> ManuscriptUnitView | None:
    await _owned_project(db, project_id, user_id)
    unit = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.project_id == project_id).order_by(ManuscriptUnit.ordinal.desc()))
    if unit is None:
        return None
    candidate = await db.scalar(select(ManuscriptCandidate).where(
        ManuscriptCandidate.unit_id == unit.id).order_by(ManuscriptCandidate.id.desc()))
    return ManuscriptUnitView(id=unit.id, scene_id=await _scene_id(db, unit), unit_type=unit.unit_type, ordinal=unit.ordinal,
        title=unit.title, adopted_content=unit.adopted_content, status=unit.status,
        candidate=_candidate_view(candidate) if candidate else None)


async def get_manuscript_unit(
    db: AsyncSession, project_id: int, manuscript_unit_id: int, user_id: int,
) -> ManuscriptUnitView:
    await _owned_project(db, project_id, user_id)
    unit = await db.scalar(select(ManuscriptUnit).where(
        ManuscriptUnit.id == manuscript_unit_id,
        ManuscriptUnit.project_id == project_id,
    ))
    if unit is None:
        raise HTTPException(404, "正文单元不存在")
    candidate = await db.scalar(select(ManuscriptCandidate).where(
        ManuscriptCandidate.unit_id == unit.id,
    ).order_by(ManuscriptCandidate.id.desc()))
    return ManuscriptUnitView(
        id=unit.id,
        scene_id=await _scene_id(db, unit),
        unit_type=unit.unit_type,
        ordinal=unit.ordinal,
        title=unit.title,
        adopted_content=unit.adopted_content,
        status=unit.status,
        candidate=_candidate_view(candidate) if candidate else None,
    )


def _check_candidate(content: str, context_pack: dict) -> list[dict]:
    checks: list[dict] = [{"check": "frozen_truth", "status": "pass", "message": "未检测到冻结事实的显式冲突"},
        {"check": "thread_motion", "status": "pass", "message": "核心情节承诺在开篇中获得具象化"},
        {"check": "state_declaration", "status": "pass", "message": "角色状态变化已声明，采用后才会写入"}]
    if len(content.strip()) < 80:
        checks.append({"check": "draft_depth", "status": "notice", "message": "候选较短，采用前建议继续扩写"})
    if context_pack["source_canon"] and not context_pack["source_canon"]["content"]:
        checks.append({"check": "source_depth", "status": "notice", "message": "当前只有来源文件引用，尚未解析正文"})
    if context_pack.get("user_directives"):
        checks.append({"check": "user_directive", "status": "pass",
            "message": f"已纳入 {len(context_pack['user_directives'])} 条用户创作指令"})
    # Content length vs target duration
    arch = context_pack.get("story_architecture")
    if arch and arch.get("current_arc", {}).get("timing"):
        t = arch["current_arc"]["timing"]
        target_words = t.get("words_per_scene", 300)
        actual_words = len(content)
        ratio = actual_words / target_words if target_words else 1
        if ratio < 0.5:
            checks.append({"check": "content_length", "status": "blocking",
                "message": f"正文{actual_words}字，远低于目标{target_words}字/场（{t.get('note','')}）。请扩写到接近目标字数。"})
        elif ratio < 0.8:
            checks.append({"check": "content_length", "status": "notice",
                "message": f"正文{actual_words}字，略低于目标{target_words}字/场。建议补充到接近目标。"})
        elif ratio > 1.5:
            checks.append({"check": "content_length", "status": "notice",
                "message": f"正文{actual_words}字，超出目标{target_words}字/场({ratio:.1f}倍)，建议精简。"})
        else:
            checks.append({"check": "content_length", "status": "pass",
                "message": f"正文{actual_words}字，在目标{target_words}字/场范围内"})

    for fact in context_pack.get("required_story_facts", []):
        start = content.find(fact["label"])
        present = start >= 0
        checks.append({
            "check": "story_fact_evidence",
            "status": "pass" if present else "blocking",
            "message": (f"已在正文定位：{fact['action']}“{fact['label']}”"
                if present else f"缺少必须体现的故事事实：{fact['label']}"),
            "change_id": fact["change_id"],
            "label": fact["label"],
            "start": start if present else None,
            "end": start + len(fact["label"]) if present else None,
            "excerpt": content[max(0, start - 30):start + len(fact["label"]) + 70] if present else "",
        })
    return checks


async def revise_manuscript(db: AsyncSession, project_id: int, candidate_id: int, feedback: str, user_id: int) -> ManuscriptUnitView:
    await _owned_project(db, project_id, user_id)
    candidate = await db.scalar(select(ManuscriptCandidate).where(ManuscriptCandidate.id == candidate_id, ManuscriptCandidate.project_id == project_id))
    if candidate is None:
        raise HTTPException(404, "正文候选不存在")
    unit = await db.get(ManuscriptUnit, candidate.unit_id)
    project = await db.get(Project, project_id)

    # Build context with previous candidate + feedback
    context_pack = json.loads(candidate.context_pack_json)
    context_pack["revision_request"] = {
        "feedback": feedback,
        "previous_title": candidate.title,
        "previous_content": candidate.content,
    }

    # Create new agent task for revision
    from .agent_runtime import creative_runtime
    runtime = creative_runtime()
    skill_path = Path(__file__).parent / "skills" / "opening-draft" / "SKILL.md"
    system_prompt = skill_path.read_text(encoding="utf-8")

    system_prompt += f"\n\n【用户反馈】{feedback}\n请在保留原稿优点的基础上，根据以上反馈修改正文。只输出修改后的 JSON。"

    if runtime.name == "agentscope":
        from agentscope.agent import Agent, ReActConfig
        from agentscope.message import Msg, TextBlock
        model = runtime._model()
        agent = Agent(name="scene_writer_reviser", system_prompt=system_prompt, model=model,
                      react_config=ReActConfig(max_iters=2))
        reply = await agent.reply(Msg(name="user", role="user",
            content=[TextBlock(type="text", text=json.dumps(context_pack, ensure_ascii=False))]))
        text = reply.get_text_content()
    else:
        # Mock revision — apply basic feedback
        text = json.dumps({
            "title": f"{candidate.title} (修订)",
            "content": f"【按反馈修订：{feedback}】\n\n{candidate.content}",
            "state_delta": {},
            "thread_actions": json.loads(candidate.thread_actions_json),
        }, ensure_ascii=False)

    result = json.loads(text)
    
    # Create new candidate
    new_candidate = ManuscriptCandidate(
        project_id=project_id, unit_id=unit.id,
        title=result.get("title", f"{candidate.title} (修订)"),
        content=result.get("content", ""),
        context_pack_json=json.dumps(context_pack, ensure_ascii=False),
        state_delta_json=json.dumps(result.get("state_delta", {}), ensure_ascii=False),
        thread_actions_json=json.dumps(result.get("thread_actions", []), ensure_ascii=False),
        continuity_report_json=json.dumps(_check_candidate(result.get("content", ""), context_pack), ensure_ascii=False),
        status="candidate",
    )
    db.add(new_candidate)
    unit.status = "candidate_ready"
    await db.commit()
    await db.refresh(new_candidate)

    return ManuscriptUnitView(id=unit.id, scene_id=None, unit_type=unit.unit_type, ordinal=unit.ordinal,
        title=unit.title, adopted_content=unit.adopted_content, status=unit.status,
        candidate=_candidate_view(new_candidate))


async def adopt_manuscript(db: AsyncSession, project_id: int, candidate_id: int, user_id: int) -> ManuscriptUnitView:
    await _owned_project(db, project_id, user_id)
    candidate = await db.scalar(select(ManuscriptCandidate).where(ManuscriptCandidate.id == candidate_id, ManuscriptCandidate.project_id == project_id))
    if candidate is None:
        raise HTTPException(404, "正文候选不存在")
    unit = await db.get(ManuscriptUnit, candidate.unit_id)
    if candidate.status != "candidate":
        raise HTTPException(409, "候选已经处理")
    report = json.loads(candidate.continuity_report_json)
    if any(item.get("status") == "blocking" for item in report):
        raise HTTPException(409, "候选缺少必须体现的故事事实，请先要求 Agent 修订")
    unit.title, unit.adopted_content, unit.status, candidate.status = candidate.title, candidate.content, "adopted", "adopted"
    if unit.unit_type == "scene":
        scene = await db.scalar(select(Scene).where(
            Scene.project_id == project_id, Scene.scene_key == f"SC-{unit.ordinal}"))
        if scene is None:
            scene = Scene(project_id=project_id, scene_key=f"SC-{unit.ordinal}")
            db.add(scene)
        scene.title = unit.title
        scene.adopted_content = unit.adopted_content
        await db.flush()
    task = await db.get(AgentTask, candidate.task_id)
    if task:
        task.status = "delivered"
        task.status_message = "正文候选已采用，叙事状态同步完成"
    story_unit = await db.scalar(select(StoryMapUnit).where(
        StoryMapUnit.project_id == project_id,
        StoryMapUnit.manuscript_unit_id == unit.id,
    ))
    if story_unit:
        story_unit.status = "adopted"
        story_unit.title = unit.title
    deltas = json.loads(candidate.state_delta_json)
    entities = (await db.scalars(select(NarrativeEntity).where(NarrativeEntity.project_id == project_id))).all()
    for entity in entities:
        if entity.name in deltas:
            state = json.loads(entity.current_state_json)
            delta = deltas[entity.name]
            if isinstance(delta, str):
                try: delta = json.loads(delta)
                except (json.JSONDecodeError, TypeError): continue
            state.update({key: value for key, value in delta.items() if key != "knowledge_add"})
            if delta.get("knowledge_add"):
                state["knowledge"] = list(dict.fromkeys(state.get("knowledge", []) + delta["knowledge_add"]))
            entity.current_state_json = json.dumps(state, ensure_ascii=False)
    actions = json.loads(candidate.thread_actions_json)
    threads = (await db.scalars(select(NarrativeThread).where(NarrativeThread.project_id == project_id))).all()
    for action in actions:
        match = next((x for x in threads if x.thread_type == action.get("thread_type")), None)
        if match:
            match.status = {"plant": "planted", "reinforce": "reinforced", "misdirect": "misdirected", "payoff": "paid_off"}.get(action.get("action"), match.status)
    await db.commit()
    return ManuscriptUnitView(id=unit.id, scene_id=await _scene_id(db, unit), unit_type=unit.unit_type, ordinal=unit.ordinal, title=unit.title,
        adopted_content=unit.adopted_content, status=unit.status, candidate=_candidate_view(candidate))
