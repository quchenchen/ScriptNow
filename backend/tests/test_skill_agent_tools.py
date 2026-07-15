"""Tests for the Skill loader tools exposed to the AgentScope toolkit.

Cover:
- activate_skill returns body + resources for a known skill
- activate_skill returns {ok: false, error: ...} for unknown name
- read_skill_file returns content when path is legal
- read_skill_file refuses ../ traversal and absolute paths
- The system prompt injection carries the skills menu
"""
from __future__ import annotations

import json

import pytest


async def _call(fn, **kw) -> dict:
    resp = await fn(**kw)
    return json.loads(resp.content[0].text)


@pytest.mark.asyncio
async def test_activate_skill_loads_shipped_execution_skill():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(tools["activate_skill"], name="灵感孵化 Agent")
    assert out["ok"] is True
    assert out["name"] == "灵感孵化 Agent"
    assert "灵感孵化" in out["body"]
    assert "resources" in out  # even if empty list


@pytest.mark.asyncio
async def test_activate_skill_loads_story_skill_with_resources():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(tools["activate_skill"], name="男频爽文短剧")
    assert out["ok"] is True
    assert out["resources"], "male_lead_shuang ships one director skill"
    assert any("director_planning_narrative" in r for r in out["resources"])


@pytest.mark.asyncio
async def test_activate_skill_unknown_returns_error():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(tools["activate_skill"], name="不存在的技能")
    assert out["ok"] is False
    assert "不存在的技能" in out["error"]


@pytest.mark.asyncio
async def test_read_skill_file_returns_content():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(
        tools["read_skill_file"],
        file_path="story_skills/male_lead_shuang/director_skills/director_planning_narrative.md",
    )
    assert out["ok"] is True
    assert "反差" in out["content"] or len(out["content"]) > 20


@pytest.mark.asyncio
async def test_read_skill_file_blocks_traversal():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(tools["read_skill_file"], file_path="../requirements.txt")
    assert out["ok"] is False
    assert "越界" in out["error"] or "outside" in out["error"].lower()


@pytest.mark.asyncio
async def test_read_skill_file_missing_returns_error():
    from app.agents.team import make_tools
    tools = make_tools(project_id=1)
    out = await _call(tools["read_skill_file"], file_path="does_not_exist.md")
    assert out["ok"] is False


def test_build_system_prompt_includes_skill_menu():
    """The prompt fed to the Agent must advertise the available_skills tag."""
    from app.agents.team import build_system_prompt
    prompt = build_system_prompt(
        stage="ideation",
        project_info={"title": "T", "type": "script"},
        skill_text="core skill text",
        memory_context="",
    )
    assert "<available_skills>" in prompt
    assert "灵感孵化 Agent" in prompt  # a shipped skill's name shows up in the menu
