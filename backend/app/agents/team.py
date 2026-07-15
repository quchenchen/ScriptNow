"""AgentTeam — the single agent orchestration entrypoint.

Design (see ADR-0003 Tier 1 and issue #03):
- Tools are plain ``async def`` functions returning :class:`ToolResponse`.
- ``build_toolkit(project_id)`` binds ``project_id`` into each tool via closure
  and registers them with a :class:`Toolkit`.
- The AgentScope :class:`Agent` runs a native ReAct loop (Toolkit + reply_stream)
  — no regex-based tool call parsing anywhere in this repo.
- ``AgentTeam.run(...)`` translates AgentScope's rich event stream into the
  simple SSE shape the frontend already consumes:
  ``{type: "text_delta"|"thinking"|"tool_result"|"error", text: str}``.

History:
- Replaces the old ``app.core.agent_orchestra`` module which parsed tool calls
  with regex (see git log for details).
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import aiosqlite
from agentscope.agent import Agent, ReActConfig
from agentscope.credential import (
    AnthropicCredential,
    DashScopeCredential,
    DeepSeekCredential,
    OpenAICredential,
)
from agentscope.message import Msg, TextBlock
from agentscope.model import (
    AnthropicChatModel,
    ChatModelBase,
    DashScopeChatModel,
    DeepSeekChatModel,
    OpenAIChatModel,
)
from agentscope.tool import FunctionTool, Toolkit, ToolResponse

from app.core.context_engine import build_context
from app.db import DB_PATH

# ═══════════════════════════════════════════
# Tool implementations
# ═══════════════════════════════════════════
#
# Each tool is a closure over ``project_id``. The Agent's ReAct loop invokes
# these through the Toolkit; we never parse tool calls out of raw text.
# ═══════════════════════════════════════════


def _text_response(payload: dict) -> ToolResponse:
    """Wrap a dict payload as a ToolResponse the Agent can consume."""
    return ToolResponse(content=[TextBlock(type="text", text=json.dumps(payload, ensure_ascii=False))])


def make_tools(project_id: int) -> dict[str, Callable[..., Awaitable[ToolResponse]]]:
    """Build the four project-scoped tools as a dict.

    Exposed as a dict (not a Toolkit) so tests can call each tool directly
    without depending on AgentScope's Toolkit dispatch. Use
    :func:`build_toolkit` when you need a Toolkit for an Agent.
    """

    async def save_episode(episode_number: int, title: str, content: str) -> ToolResponse:
        """将生成的剧本剧集保存到数据库。生成完一集后必须调用。

        Args:
            episode_number: 剧集编号（从 1 开始，自动递增到下一集）。
            title: 剧集标题，例如 "第3集 · 相遇"。
            content: 剧本正文（场景 + 动作 + 对白，完整一集，用 【场景N】location·time 分场）。
        """
        from app.services import growth_tree_service as tree_svc
        from app.services.scene_splitter import split_scenes

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT MAX(episode_number) FROM episodes WHERE project_id = ?", (project_id,)
            )
            row = await cur.fetchone()
            next_num = (row[0] or 0) + 1
            ep_num = episode_number if episode_number and episode_number >= next_num else next_num
            word_count = len(content)

            ins = await db.execute(
                "INSERT INTO episodes (project_id, episode_number, title, "
                "word_count, status) VALUES (?,?,?,?,?)",
                (project_id, ep_num, title or f"第{ep_num}集", word_count, "done"),
            )
            episode_id = ins.lastrowid

            scenes = split_scenes(content)
            scene_ids: list[tuple[int, dict]] = []
            for s in scenes:
                sc_ins = await db.execute(
                    "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
                    "VALUES (?,?,?,?,?)",
                    (episode_id, s["scene_number"], s["location"], s["time"], s["content"]),
                )
                scene_ids.append((sc_ins.lastrowid, s))
            await db.commit()

        # Record in the growth tree. Best-effort — a tree hiccup should not
        # prevent the episode from being saved.
        try:
            idea_node = await tree_svc.record_artefact(
                project_id, "idea", project_id, label="项目起点"
            )
            ep_node = await tree_svc.record_artefact(
                project_id, "episode", episode_id,
                label=f"EP{ep_num} {title or ''}",
            )
            await tree_svc.record_derived_from(project_id, idea_node, ep_node)
            for sc_id, s in scene_ids:
                sc_node = await tree_svc.record_artefact(
                    project_id, "scene", sc_id,
                    label=f"S{s['scene_number']} {s['location'] or ''}",
                )
                await tree_svc.record_derived_from(project_id, ep_node, sc_node)
        except Exception as e:  # pragma: no cover — best-effort tree write
            import logging
            logging.getLogger(__name__).warning("growth tree record failed: %s", e)

        return _text_response({
            "ok": True,
            "episode_number": ep_num,
            "words": word_count,
            "scene_count": len(scenes),
        })

    async def query_characters() -> ToolResponse:
        """查询项目中已有的角色列表，用于保持角色一致性。返回所有活跃角色。"""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM characters WHERE project_id = ? AND status != 'deceased'",
                (project_id,),
            )
            chars = [dict(r) for r in await cur.fetchall()]
        return _text_response({"ok": True, "characters": chars})

    async def plant_foreshadow(
        title: str,
        description: str,
        category: str = "mystery",
        importance: float = 0.5,
    ) -> ToolResponse:
        """在当前剧集中埋下一个伏笔，用于后续回收。

        Args:
            title: 伏笔简短标题。
            description: 伏笔详细描述（会在后续被 build_context 显示给未来的 agent）。
            category: 类型枚举: mystery / cliffhanger / identity / relationship / item / event。
            importance: 重要性 0.0-1.0，越高越优先在上下文里被提到。
        """
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO foreshadows (project_id, title, description, category, "
                "importance, status) VALUES (?,?,?,?,?,?)",
                (project_id, title, description, category, importance, "planted"),
            )
            await db.commit()
            fid = cur.lastrowid
        return _text_response({"ok": True, "id": fid})

    async def resolve_foreshadow(foreshadow_id: int, resolution: str = "") -> ToolResponse:
        """回收一个之前埋下的伏笔。将其状态标记为 resolved 并记录回收方式。

        Args:
            foreshadow_id: 要回收的伏笔 ID（由 plant_foreshadow 返回，或从上下文里的伏笔列表拿）。
            resolution: 回收方式的简短描述。
        """
        async with aiosqlite.connect(DB_PATH) as db:
            # Check existence first — refuse cleanly if id is fake
            check = await db.execute(
                "SELECT id FROM foreshadows WHERE id = ? AND project_id = ?",
                (foreshadow_id, project_id),
            )
            if not await check.fetchone():
                return _text_response({"ok": False, "error": f"foreshadow {foreshadow_id} not found"})
            await db.execute(
                "UPDATE foreshadows SET status = 'resolved', resolution_text = ?, "
                "actual_episode = (SELECT COALESCE(MAX(episode_number), 0) FROM episodes "
                "WHERE project_id = ?) WHERE id = ?",
                (resolution, project_id, foreshadow_id),
            )
            await db.commit()
        return _text_response({"ok": True})

    return {
        "save_episode": save_episode,
        "query_characters": query_characters,
        "plant_foreshadow": plant_foreshadow,
        "resolve_foreshadow": resolve_foreshadow,
    }


def build_toolkit(project_id: int) -> Toolkit:
    """Build an AgentScope :class:`Toolkit` bound to ``project_id``.

    Each tool's schema (name, description, parameters) is extracted from the
    function's docstring and type hints by :class:`FunctionTool`.
    """
    tools = make_tools(project_id)
    return Toolkit(
        tools=[
            FunctionTool(fn, name=name) for name, fn in tools.items()
        ]
    )


# ═══════════════════════════════════════════
# Model routing
# ═══════════════════════════════════════════

def _build_model(model_id: str) -> ChatModelBase:
    """Route ``provider:model`` → concrete AgentScope ChatModel instance.

    Raises ``ValueError`` for unknown providers or missing API keys.
    """
    provider, _, model_name = model_id.partition(":")
    if not model_name:
        # Fall back to default provider if user passes bare model name
        provider, model_name = "dashscope", model_id

    api_key_env = {
        "dashscope": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider)
    if not api_key_env:
        raise ValueError(f"Unknown provider: {provider}")

    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise ValueError(f"Missing {api_key_env}. Set it in .env to use provider '{provider}'.")

    if provider == "dashscope":
        return DashScopeChatModel(credential=DashScopeCredential(api_key=api_key), model=model_name, stream=True)
    if provider == "deepseek":
        return DeepSeekChatModel(credential=DeepSeekCredential(api_key=api_key), model=model_name, stream=True)
    if provider == "openai":
        return OpenAIChatModel(credential=OpenAICredential(api_key=api_key), model=model_name, stream=True)
    if provider == "anthropic":
        return AnthropicChatModel(credential=AnthropicCredential(api_key=api_key), model=model_name, stream=True)
    raise ValueError(f"Unknown provider: {provider}")


# ═══════════════════════════════════════════
# Prompt assembly
# ═══════════════════════════════════════════

@dataclass
class PromptPart:
    """One structured chunk of the system prompt."""

    id: str
    title: str
    body: str


def build_system_prompt(
    stage: str,
    project_info: dict,
    skill_text: str,
    memory_context: str,
) -> str:
    """Assemble a structured system prompt from the project + memory context.

    Tools are advertised by the Toolkit itself, not by the prompt text —
    the model receives their JSON schemas natively and no longer needs the
    prompt to spell out how to invoke them.
    """
    stage_label = {
        "ideation": "创意孵化", "structure": "故事架构", "writing": "剧本撰写",
        "review": "质量审核", "polish": "润色定稿",
        "assets": "资产提取", "prompts": "提示词生成",
    }.get(stage, stage)

    parts = [
        PromptPart("agent.core", "Agent 说明", skill_text),
        PromptPart(
            "workflow.project",
            "项目上下文",
            f"项目：{project_info.get('title', '')} | 类型：{project_info.get('type', 'script')} | "
            f"当前阶段：{stage_label}",
        ),
    ]
    if memory_context:
        parts.append(PromptPart("memory.context", "记忆上下文", memory_context))

    return "\n\n".join(f"## {p.title}\n{p.body}" for p in parts)


AGENT_CONFIGS: dict[str, dict] = {
    "ideation": {
        "name": "创意总监",
        "sys_prompt": (
            "你是短剧创意孵化专家。基于用户偏好生成 3 个差异化方案。\n"
            "格式：严格用 <PLAN id=\"A/B/C\" title=\"...\" genre=\"...\" hook=\"...\"> 包裹每个方案。\n"
            "类型约束：严格匹配用户指定的类型标签。风格约束：节奏和人设需体现风格偏好。\n"
            "禁止输出问候语和确认语。"
        ),
    },
    "structure": {
        "name": "编剧架构师",
        "sys_prompt": (
            "你是故事架构专家。基于选中方案，产出完整架构。\n"
            "## 输出格式\n"
            "### 核心梗概（一句话+世界观）\n"
            "### 角色设定（每个角色：姓名·年龄·性别·性格·背景·弧光）\n"
            "### 分集大纲（10 集，每集一句话概要+关键冲突）\n"
            "### 爽点分布图（每集标注 1-3 个爽点类型）\n"
            "创作时可调用 query_characters 查看已有角色，plant_foreshadow 埋设伏笔。"
        ),
    },
    "writing": {
        "name": "写手",
        "sys_prompt": (
            "你是短剧剧本撰写师。严格按格式：\n"
            "【场景N】地点·时间\n"
            "△动作描述\n"
            "角色：对白\n\n"
            "规则：\n"
            "1. 每集 600-1500 字\n"
            "2. 结尾必须埋钩子\n"
            "3. 对话前用 △ 描述动作/表情\n"
            "4. 禁止输出 JSON、问候语、元对话\n"
            "5. 写完一集立即调用 save_episode 保存\n"
            "6. 调用 query_characters 确保角色一致\n"
            "7. 用 plant_foreshadow 埋设伏笔，用 resolve_foreshadow 回收"
        ),
    },
}


def _route(stage: str) -> str:
    """Map project stage → agent config key."""
    return {
        "ideation": "ideation", "story_design": "structure", "structure": "structure",
        "writing": "writing", "outline": "structure",
        "review": "structure", "polish": "writing", "proofread": "writing",
    }.get(stage, "structure")


# ═══════════════════════════════════════════
# AgentTeam
# ═══════════════════════════════════════════

class AgentTeam:
    """The single agent orchestration entrypoint used by ``workspace.py``.

    Public interface (kept stable for the API layer):
        ``async for event in AgentTeam(project_id, model_id).run(message, stage, ep_num, prev_context)``

    Each yielded event is a ``dict`` with keys ``type`` and ``text`` where
    ``type ∈ {"text_delta", "thinking", "tool_result", "error"}``.
    """

    def __init__(self, project_id: int, model_id: str) -> None:
        self.project_id = project_id
        self.model_id = model_id

    async def _load_project(self) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM projects WHERE id = ?", (self.project_id,))
            row = await cur.fetchone()
            return dict(row) if row else {"title": "未知", "type": "script"}

    async def run(
        self,
        message: str,
        stage: str,
        ep_num: int = 0,
        prev_context: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Run one turn of the agent loop. See class docstring for events."""
        project = await self._load_project()
        agent_key = _route(stage)
        cfg = AGENT_CONFIGS.get(agent_key, AGENT_CONFIGS["writing"])
        memory_ctx = await build_context(self.project_id, stage, ep_num)
        merged_memory = "\n\n".join(s for s in [prev_context, memory_ctx] if s)

        system_prompt = build_system_prompt(
            stage=stage, project_info=project,
            skill_text=cfg["sys_prompt"], memory_context=merged_memory,
        )

        yield {"type": "thinking", "text": f"Agent: {cfg['name']} | 阶段: {stage}"}

        try:
            model = _build_model(self.model_id)
        except ValueError as e:
            yield {"type": "error", "text": str(e)}
            return

        toolkit = build_toolkit(self.project_id)
        agent = Agent(
            name=cfg["name"],
            system_prompt=system_prompt,
            model=model,
            toolkit=toolkit,
            react_config=ReActConfig(max_iters=5),
        )
        user_msg = Msg(name="user", role="user", content=[TextBlock(type="text", text=message)])

        # AgentScope handles the ReAct loop natively; we just translate its
        # streamed events into the shape the SSE consumer expects.
        try:
            async for event in agent.reply_stream(user_msg):
                translated = _translate_event(event)
                if translated is not None:
                    yield translated
                await asyncio.sleep(0)
        except Exception as e:  # pragma: no cover — hardening
            yield {"type": "error", "text": f"agent 异常：{e!r}"}


def _translate_event(event) -> dict | None:
    """Translate an AgentScope stream event to our SSE shape.

    Returns None for events we don't surface to the client (start markers,
    finish markers, etc.).
    """
    tname = type(event).__name__

    if tname == "TextBlockDeltaEvent":
        delta = getattr(event, "delta", None) or ""
        return {"type": "text_delta", "text": delta} if delta else None

    if tname == "ToolCallStartEvent":
        # Attempt to surface which tool is being called
        tool_name = getattr(event, "tool_name", None) or getattr(event, "name", None) or "?"
        return {"type": "thinking", "text": f"调用工具: {tool_name}"}

    if tname == "ToolResultEndEvent":
        payload = getattr(event, "text", None) or getattr(event, "result", "")
        return {"type": "tool_result", "text": str(payload)[:300]}

    if tname == "ExceedMaxItersEvent":
        return {"type": "error", "text": "已达到最大迭代次数（ReActConfig.max_iters）。"}

    if tname == "ThinkingBlockDeltaEvent":
        delta = getattr(event, "delta", None) or ""
        return {"type": "thinking", "text": delta} if delta else None

    return None
