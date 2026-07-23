import asyncio

import pytest
from agentscope.message import Msg, TextBlock, ThinkingBlock

from scriptflow_v7.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database


def test_runtime_separates_text_from_thinking_only_replies() -> None:
    thinking_only = Msg(
        name="reviewer",
        role="assistant",
        content=[ThinkingBlock(thinking="internal planning")],
    )
    with_text = Msg(
        name="reviewer",
        role="assistant",
        content=[
            ThinkingBlock(thinking="internal planning"),
            TextBlock(text="  visible contract output  "),
        ],
    )

    assert AgentRuntime._text_content(thinking_only) == ""
    assert AgentRuntime._text_content(with_text) == "visible contract output"


def test_prompt_context_precedence_keeps_human_revision_above_approved_profile() -> None:
    prompt = AgentRuntime._compose_prompt(
        content="Write chapter two.",
        creative_profile={"language": "en-US", "boundary": "no imitation"},
        approved_source_profile={
            "id": "profile-approved",
            "version": 2,
            "profile": {"relationship_engine": "rejection-as-protection"},
        },
        context_snapshot={
            "prior_chapter_revisions": [
                {
                    "chapter_id": "chapter-1",
                    "revision_number": 3,
                    "source": "human",
                    "blocks": [{"type": "prose", "text": "The revised promise."}],
                }
            ]
        },
    )

    assert "已采纳事实与最新有效人工修订" in prompt
    assert "低优先级内容不得覆盖高优先级事实" in prompt
    assert "profile-approved" in prompt
    assert "The revised promise." in prompt
    assert prompt.index("来源蒸馏画像") < prompt.index("服务端项目事实快照（唯一事实依据")


def test_prompt_context_uses_empty_object_when_no_source_profile_is_approved() -> None:
    prompt = AgentRuntime._compose_prompt(
        content="Continue the novel.",
        creative_profile={},
        approved_source_profile=None,
        context_snapshot={"prior_chapter_revisions": []},
    )

    assert "未批准的来源候选不得使用" in prompt
    assert "用户已批准的来源蒸馏画像（仅作创作策略，不是已采纳事实）：\n{}" in prompt


async def test_runtime_enforces_one_wall_clock_timeout_for_all_agents(monkeypatch) -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    runtime = AgentRuntime(database, Settings(agent_runtime_timeout_seconds=0.01))

    async def stalled(**kwargs):
        del kwargs
        await asyncio.sleep(1)

    monkeypatch.setattr(runtime, "_generate", stalled)
    with pytest.raises(AgentRuntimeError, match="exceeded 0.01 seconds"):
        await runtime.generate(
            tenant_id="tenant",
            run_id="run",
            role="writer",
            content="chapter",
            context_snapshot={},
        )
    await database.dispose()
