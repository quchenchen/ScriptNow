"""Story Architecture — Agent-driven global narrative planning bridging StoryCore → StoryMap."""
from __future__ import annotations

import json, os
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    NarrativeArc, Project, ProjectPlan, StoryArchitecture, StoryCoreCandidate,
    StoryMapGroup, StoryMapUnit,
)
from .medium_profiles import get_profile, profile_for_goal
from .story_structures import get_structure, structure_labels
from .runtime_config import runtime_config


async def get_architecture(db: AsyncSession, project_id: int, user_id: int) -> dict:
    arch = await db.scalar(select(StoryArchitecture).where(StoryArchitecture.project_id == project_id))
    if not arch:
        return {"status": "not_planned", "thesis": "", "approach": "", "arcs": []}
    arcs = (await db.scalars(select(NarrativeArc).where(
        NarrativeArc.architecture_id == arch.id).order_by(NarrativeArc.ordinal))).all()
    return {
        "status": arch.status,
        "thesis": arch.thesis,
        "approach": arch.approach,
        "agent_session": json.loads(arch.agent_session_json),
        "arcs": [_arc_view(a) for a in arcs],
    }


async def plan_architecture(db: AsyncSession, project_id: int, user_id: int) -> dict:
    """Run Story Architecture Agent to generate the global blueprint."""
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.adopted_story_core_id:
        raise HTTPException(400, "请先采用一个 StoryCore")

    core = await db.get(StoryCoreCandidate, project.adopted_story_core_id)
    plan = await db.scalar(select(ProjectPlan).where(ProjectPlan.project_id == project_id))

    # Build context for agent
    profile = profile_for_goal(project.goal_type)
    structure = get_structure((plan.story_structure if plan else "") or "three-act")
    # Read user-configured timing from ProjectPlan
    timing_defaults = {
        "target_minutes_per_episode": plan.target_minutes_per_episode if plan else 3,
        "target_scenes_per_episode": plan.target_scenes_per_episode if plan else 3,
        "target_words": plan.target_words if plan and plan.target_words else 0,
    }
    context = {
        "story_core": {"title": core.title, "logline": core.logline,
            "dramatic_question": core.dramatic_question, "protagonist": core.protagonist,
            "conflict": core.conflict, "promise": core.promise, "source_strategy": core.source_strategy},
        "project_plan": {"total_episodes": plan.target_episode_count if plan else (profile.default_episodes or 80),
            "scenes_per_episode": timing_defaults["target_scenes_per_episode"],
            "minutes_per_episode": timing_defaults["target_minutes_per_episode"],
            "target_words": timing_defaults["target_words"],
            "medium": profile.label, "medium_key": profile.key,
            "story_structure": structure.key, "structure_label": structure.label,
            "arc_names": structure.arc_names, "arc_purposes": structure.arc_purposes,
            "structure_origin": structure.origin,
            "shot_guidance": profile.shot_guidance,
            "scene_pacing": profile.scene_pacing,
            "agent_tone": profile.agent_tone_guidance,
            "style": plan.style_direction if plan else ""},
        "user_directives": [],
        "existing_entities": [],
        "existing_threads": [],
        "source_canon": {"type": project.goal_type},
    }

    # Call AgentScope to generate architecture
    from .agent_runtime import creative_runtime
    runtime = creative_runtime()
    
    skill_path = Path(__file__).parent / "skills" / "story-architecture" / "SKILL.md"
    system_prompt = skill_path.read_text(encoding="utf-8")

    if runtime.name == "agentscope":
        from agentscope.agent import Agent, ReActConfig
        from agentscope.message import Msg, TextBlock
        model = runtime._model()
        agent = Agent(name="story_architect", system_prompt=system_prompt, model=model,
                      react_config=ReActConfig(max_iters=2))
        reply = await agent.reply(Msg(name="user", role="user",
            content=[TextBlock(type="text", text=json.dumps(context, ensure_ascii=False))]))
        text = reply.get_text_content()
    else:
        # Mock mode — return a deterministic example structure
        ep_count = context["project_plan"]["total_episodes"]
        text = json.dumps({
            "thesis": "将原著冰毒帝国线重构为双人博弈心理剧。郭小鹏不是传统反派，他每次违法都是对体制漏洞的一次测试；汪静飞不是正义使者，她每次执法都是对自己信念的一次消磨。",
            "approach": f"以审讯室为核心时空锚点。两人每次交锋发生在不同空间(审讯室/郭宅/码头/法院)，但每次对话都围绕同一个核心张力：'你到底想从我这里得到什么？'",
            "arcs": [
                {"title":"潜入","episode_start":1,"episode_end":max(1,ep_count//6),
                 "core_conflict":"信任如何建立——汪静飞必须让郭小鹏相信她只是个普通刑警，郭小鹏必须让汪静飞相信他只是个普通商人",
                 "emotional_landing":"观众应该开始对郭小鹏产生危险的好感——这个人聪明得让人不安",
                 "protag_state":"从职业冷漠→开始被郭小鹏的智力吸引","antag_state":"从居高临下的试探→发现这个刑警不太一样",
                 "must_have_events":["EP01 戴主席电话开场","EP04 首次审讯——郭小鹏反问汪静飞的法律依据"],
                 "foreshadow_actions":["埋设:郭小鹏对汪静飞档案的异常了解(EP02)"]},
            ]}, ensure_ascii=False)

    # Parse and persist
    data = _extract_json(text)
    
    arch = await db.scalar(select(StoryArchitecture).where(StoryArchitecture.project_id == project_id))
    if not arch:
        arch = StoryArchitecture(project_id=project_id)
        db.add(arch)
    arch.thesis = data.get("thesis", "")
    arch.approach = data.get("approach", "")
    arch.status = "planned"
    arch.agent_session_json = json.dumps({"context": context, "raw_response": text[:2000]}, ensure_ascii=False)
    await db.flush()

    # Delete old arcs and create new ones
    old_arcs = (await db.scalars(select(NarrativeArc).where(NarrativeArc.architecture_id == arch.id))).all()
    for a in old_arcs:
        await db.delete(a)
    
    for i, arc_data in enumerate(data.get("arcs", []), 1):
        arc = NarrativeArc(architecture_id=arch.id, project_id=project_id, ordinal=i,
            title=arc_data["title"], episode_start=arc_data["episode_start"],
            episode_end=arc_data["episode_end"], core_conflict=arc_data.get("core_conflict",""),
            emotional_landing=arc_data.get("emotional_landing",""),
            protag_state=arc_data.get("protag_state",""), antag_state=arc_data.get("antag_state",""),
            must_have_json=json.dumps(arc_data.get("must_have_events",[]), ensure_ascii=False),
            foreshadow_json=json.dumps(arc_data.get("foreshadow_actions",[]), ensure_ascii=False),
            target_minutes_per_episode=arc_data.get("target_minutes_per_episode", timing_defaults["target_minutes_per_episode"]),
            target_scenes_per_episode=arc_data.get("target_scenes_per_episode", timing_defaults["target_scenes_per_episode"]),
            target_words_per_scene=arc_data.get("target_words_per_scene", timing_defaults["target_words"] or 300),
            status="planned")
        db.add(arc)

    # Update StoryMap groups to reflect arc structure
    groups = (await db.scalars(select(StoryMapGroup).where(
        StoryMapGroup.project_id == project_id).order_by(StoryMapGroup.ordinal))).all()
    for group in groups:
        # Find which arc this group belongs to
        arc = next((a for a in data.get("arcs", []) if a["episode_start"] <= group.ordinal <= a["episode_end"]), None)
        if arc:
            group.title = f"第{group.ordinal}集 · {arc['title']}"
            group.goal = f"核心冲突: {arc.get('core_conflict','')[:80]}"

    await db.commit()
    return await get_architecture(db, project_id, user_id)


async def update_arc(db: AsyncSession, project_id: int, arc_id: int, user_id: int, data: dict) -> dict:
    arc = await db.scalar(select(NarrativeArc).where(NarrativeArc.id == arc_id, NarrativeArc.project_id == project_id))
    if not arc:
        raise HTTPException(404, "叙事弧线不存在")
    for key in ("title","episode_start","episode_end","core_conflict","emotional_landing","protag_state","antag_state","status"):
        if key in data:
            setattr(arc, key, data[key])
    if "must_have_events" in data:
        arc.must_have_json = json.dumps(data["must_have_events"], ensure_ascii=False)
    if "foreshadow_actions" in data:
        arc.foreshadow_json = json.dumps(data["foreshadow_actions"], ensure_ascii=False)
    await db.commit()
    return _arc_view(arc)


def _arc_view(arc: NarrativeArc) -> dict:
    return {"id": arc.id, "ordinal": arc.ordinal, "title": arc.title,
        "episode_start": arc.episode_start, "episode_end": arc.episode_end,
        "core_conflict": arc.core_conflict, "emotional_landing": arc.emotional_landing,
        "protag_state": arc.protag_state, "antag_state": arc.antag_state,
        "must_have_events": json.loads(arc.must_have_json),
        "foreshadow_actions": json.loads(arc.foreshadow_json), "status": arc.status,
        "target_minutes_per_episode": arc.target_minutes_per_episode,
        "target_scenes_per_episode": arc.target_scenes_per_episode,
        "target_words_per_scene": arc.target_words_per_scene}


def _extract_json(text: str) -> dict:
    import re
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Agent 未返回有效 JSON")
    return json.loads(match.group(0))
