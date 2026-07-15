"""
Agent Orchestra — ViMax-inspired multi-agent pipeline.

Patterns absorbed from ViMax:
  - PromptBuilder: structured system prompt parts with zones (stable/dynamic)
  - AgentLoop: multi-pass tool use with context compaction
  - ToolSpec: typed tool definitions with JSON schemas
  - SessionIndex: persistent agent state across turns
"""
import json, os, re, aiosqlite, asyncio, hashlib
from typing import AsyncGenerator, Any
from dataclasses import dataclass, field
from datetime import datetime

from agentscope.agent import Agent, ReActConfig
from agentscope.model import DashScopeChatModel
from agentscope.credential import DashScopeCredential
from agentscope.message import Msg

from app.db import DB_PATH
from app.core.context_engine import build_context


# ═══════════════════════════════════════════
# Prompt Parts (ViMax PromptBuilder pattern)
# ═══════════════════════════════════════════

@dataclass
class PromptPart:
    id: str
    title: str
    body: str
    zone: str  # stable | dynamic
    category: str  # agent | workflow | tooling | session | memory | request


def build_prompt_parts(user_input: str, stage: str, project_info: dict,
                       skill_text: str, memory_context: str,
                       tool_schemas: str) -> list[PromptPart]:
    """Build structured prompt parts following ViMax's zone-based architecture."""
    stage_label = {
        'ideation': '创意孵化', 'structure': '故事架构', 'writing': '剧本撰写',
        'review': '质量审核', 'polish': '润色定稿', 'assets': '资产提取', 'prompts': '提示词生成'
    }.get(stage, stage)

    parts = [
        PromptPart("agent.core", "Agent", skill_text, "stable", "agent"),
        PromptPart("workflow.project", "项目上下文",
                   f"项目：{project_info.get('title','')} | 类型：{project_info.get('type','script')} | 阶段：{stage_label}",
                   "stable", "workflow"),
    ]

    if memory_context:
        parts.append(PromptPart("memory.context", "记忆上下文", memory_context, "dynamic", "memory"))
    if tool_schemas:
        parts.append(PromptPart("tool.manifest", "可用工具", tool_schemas, "dynamic", "tooling"))
    parts.append(PromptPart("request.user", "用户指令", user_input, "dynamic", "request"))

    return parts


def assemble_system_prompt(parts: list[PromptPart]) -> str:
    """Assemble system prompt from prompt parts."""
    sections = []
    for p in parts:
        if p.id == "request.user":
            continue
        sections.append(f"## {p.title}\n{p.body}")
    return "\n\n".join(sections)


# ═══════════════════════════════════════════
# Tool Specifications (ViMax ToolSpec pattern)
# ═══════════════════════════════════════════

TOOL_SPECS = {
    "save_episode": {
        "name": "save_episode",
        "description": "将生成的剧本剧集保存到数据库。生成完一集后必须调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "episode_number": {"type": "integer", "description": "剧集编号"},
                "title": {"type": "string", "description": "剧集标题"},
                "content": {"type": "string", "description": "剧本正文"}
            },
            "required": ["episode_number", "title", "content"]
        }
    },
    "query_characters": {
        "name": "query_characters",
        "description": "查询项目中已有的角色列表，用于保持角色一致性。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "plant_foreshadow": {
        "name": "plant_foreshadow",
        "description": "在当前剧集中埋下一个伏笔，用于后续回收。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "伏笔标题"},
                "description": {"type": "string", "description": "伏笔详细描述"},
                "category": {"type": "string", "description": "类别: mystery/cliffhanger/identity/relationship/item/event",
                             "enum": ["mystery", "cliffhanger", "identity", "relationship", "item", "event"]},
                "importance": {"type": "number", "description": "重要性 0.0-1.0"}
            },
            "required": ["title", "description"]
        }
    },
    "resolve_foreshadow": {
        "name": "resolve_foreshadow",
        "description": "回收一个之前埋下的伏笔。",
        "parameters": {
            "type": "object",
            "properties": {
                "foreshadow_id": {"type": "integer", "description": "要回收的伏笔ID"},
                "resolution": {"type": "string", "description": "回收方式描述"}
            },
            "required": ["foreshadow_id"]
        }
    },
}

TOOL_SCHEMAS_JSON = json.dumps([v for v in TOOL_SPECS.values()], ensure_ascii=False)


# ═══════════════════════════════════════════
# Tool Executor (ViMax pattern)
# ═══════════════════════════════════════════

async def execute_tool(name: str, args: dict, project_id: int) -> dict:
    """Execute a tool and return result."""
    if name == "save_episode":
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT MAX(episode_number) FROM episodes WHERE project_id=?", (project_id,))
            row = await cur.fetchone()
            ep_num = (row[0] or 0) + 1
            content = args.get("content", "")
            title = args.get("title", f"第{ep_num}集")
            word_count = len(content)
            scenes = json.dumps([{"content": content}], ensure_ascii=False)
            await db.execute(
                "INSERT INTO episodes (project_id, episode_number, title, scenes, word_count, status) VALUES (?,?,?,?,?,?)",
                (project_id, ep_num, title, scenes, word_count, "done"))
            await db.commit()
        return {"ok": True, "episode_number": ep_num, "words": word_count}

    if name == "query_characters":
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM characters WHERE project_id=?", (project_id,))
            chars = [dict(r) for r in await cur.fetchall()]
        return {"ok": True, "characters": chars}

    if name == "plant_foreshadow":
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO foreshadows (project_id, title, description, category, importance, status) VALUES (?,?,?,?,?,?)",
                (project_id, args["title"], args.get("description", ""),
                 args.get("category", "mystery"), args.get("importance", 0.5), "planted"))
            await db.commit()
        return {"ok": True, "id": cur.lastrowid}

    if name == "resolve_foreshadow":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE foreshadows SET status='resolved', resolution_text=?, actual_episode=(SELECT MAX(episode_number) FROM episodes WHERE project_id=?) WHERE id=?",
                (args.get("resolution", ""), project_id, args["foreshadow_id"]))
            await db.commit()
        return {"ok": True}

    return {"ok": False, "error": f"Unknown tool: {name}"}


# ═══════════════════════════════════════════
# Agent Configs
# ═══════════════════════════════════════════

AGENT_CONFIGS = {
    "ideation": {
        "name": "创意总监",
        "sys_prompt": """你是短剧创意孵化专家。基于用户偏好生成3个差异化方案。
格式：严格用 <PLAN id="A/B/C" title="..." genre="..." hook="..."> 包裹每个方案。
类型约束：严格匹配用户指定的类型标签。风格约束：节奏和人设需体现风格偏好。
禁止输出问候语和确认语。"""
    },
    "structure": {
        "name": "编剧架构师",
        "sys_prompt": """你是故事架构专家。基于选中方案，产出完整架构。
## 输出格式
### 核心梗概（一句话+世界观）
### 角色设定（每个角色：姓名·年龄·性别·性格·背景·弧光）
### 分集大纲（10集，每集一句话概要+关键冲突）
### 爽点分布图（每集标注1-3个爽点类型）
使用 tool: query_characters 查看已有角色，plant_foreshadow 埋设伏笔。"""
    },
    "writing": {
        "name": "WritingAgent",
        "sys_prompt": """你是短剧剧本撰写师。严格按格式：\n【场景N】地点·时间\n△动作描述\n角色：对白\n\n规则：\n1. 每集600-1500字\n2. 结尾必须埋钩子\n3. 对话前用△描述动作/表情\n4. 禁止输出JSON/问候语/元对话\n5. 写完后调用 save_episode 保存\n6. 使用 query_characters 确保角色一致\n7. 用 plant_foreshadow 埋设伏笔"""
    },
}


class AgentTeam:
    """ViMax-inspired AgentTeam with structured prompts + tool use."""

    def __init__(self, project_id: int, model_id: str):
        self.project_id = project_id
        self.model_id = model_id
        self._history: list[dict] = []
        self._compact_summary: str = ""

    async def _load_project(self) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM projects WHERE id=?", (self.project_id,))
            row = await cur.fetchone()
            return dict(row) if row else {"title": "未知", "type": "script"}

    def _route(self, stage: str) -> str:
        route_map = {
            "ideation": "ideation", "story_design": "structure", "structure": "structure",
            "writing": "writing", "outline": "structure",
            "review": "structure", "polish": "writing", "proofread": "writing",
        }
        return route_map.get(stage, "structure")

    async def _should_compact(self, messages: list, system_tokens: int = 0) -> bool:
        """Check if context compaction is needed (ViMax pattern)."""
        total = sum(len(str(m.get("content", ""))) // 4 for m in messages) + system_tokens
        return total > 8000  # Compact at ~8k tokens

    async def _compact_history(self) -> str:
        """Summarize conversation history (ViMax ContextCompactor pattern)."""
        if not self._history or len(self._history) < 6:
            return self._compact_summary

        # Simple extractive summary - take last user+assistant pair + key info
        recent_user = ""
        recent_agent = ""
        for m in reversed(self._history):
            if not recent_agent and m["role"] == "assistant":
                recent_agent = str(m.get("content", ""))[:500]
            if not recent_user and m["role"] == "user":
                recent_user = str(m.get("content", ""))[:200]
            if recent_user and recent_agent:
                break

        self._compact_summary = f"## 前情摘要\n用户：{recent_user}\nAgent产出：{recent_agent[:300]}"
        self._history = []  # Reset history after compaction
        return self._compact_summary

    async def run(self, message: str, stage: str, ep_num: int = 0, prev_context: str = "") -> AsyncGenerator[dict, None]:
        """Run agent with ViMax-style tool loop — multi-pass with tool execution feedback."""
        project = await self._load_project()
        agent_type = self._route(stage)
        memory_ctx = await build_context(self.project_id, stage, ep_num)
        config = AGENT_CONFIGS.get(agent_type, AGENT_CONFIGS["writing"])

        parts = build_prompt_parts(
            user_input=message, stage=stage, project_info=project,
            skill_text=config["sys_prompt"],
            memory_context=f"{prev_context}\n\n{memory_ctx}".strip(),
            tool_schemas=TOOL_SCHEMAS_JSON
        )
        system_prompt = assemble_system_prompt(parts)

        if await self._should_compact(self._history, len(system_prompt) // 4):
            yield {"type": "thinking", "text": "上下文压缩中…"}
            self._compact_summary = await self._compact_history()
        if self._compact_summary:
            system_prompt = f"{self._compact_summary}\n\n{system_prompt}"

        yield {"type": "thinking", "text": f"Agent: {config['name']} | 阶段: {stage}"}

        model_name = self.model_id.split(":", 1)[1] if ":" in self.model_id else self.model_id
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        cred = DashScopeCredential(api_key=api_key)
        model = DashScopeChatModel(credential=cred, model=model_name, stream=True)

        # Multi-pass tool loop (ViMax pattern)
        full_text = ""
        max_passes = 5
        current_message = message

        for tool_pass in range(max_passes):
            agent = Agent(name=config["name"], system_prompt=system_prompt, model=model,
                          toolkit=None, react_config=ReActConfig(verbose=False))
            user_msg = Msg(name="user", role="user", content=[{"type": "text", "text": current_message}])

            turn_text = ""
            async for response in agent.reply_stream(user_msg):
                tname = type(response).__name__
                if tname == 'TextBlockDeltaEvent' and hasattr(response, 'delta'):
                    turn_text += response.delta
                    full_text += response.delta
                    yield {"type": "text_delta", "text": response.delta}
                    await asyncio.sleep(0)

            # Try to extract JSON tool calls from response
            import re
            tool_pattern = re.compile(r'(?:调用|使用|执行)\s*(save_episode|query_characters|plant_foreshadow|resolve_foreshadow)\s*[：:]\s*(\{.*?\})', re.DOTALL)
            tool_calls_found = tool_pattern.findall(turn_text)

            if not tool_calls_found:
                # Also try to find bare JSON tool calls
                json_pattern = re.compile(r'\{"tool":\s*"(save_episode|query_characters|plant_foreshadow|resolve_foreshadow)".*?\}', re.DOTALL)
                for m in json_pattern.finditer(turn_text):
                    try:
                        data = json.loads(m.group(0))
                        tool_calls_found.append((data["tool"], json.dumps(data.get("args", {}))))
                    except: pass

            if tool_calls_found:
                for tool_name, args_str in tool_calls_found:
                    try:
                        args = json.loads(args_str)
                    except:
                        args = {}
                    yield {"type": "thinking", "text": f"执行工具: {tool_name}"}
                    result = await execute_tool(tool_name, args, self.project_id)
                    result_text = json.dumps(result, ensure_ascii=False)
                    yield {"type": "tool_result", "text": result_text[:200]}

                    # Feed result back as next message
                    current_message = f"工具 {tool_name} 执行结果：\n{result_text}\n\n请基于以上结果继续。"
                    break  # One tool per pass, continue to next pass
                else:
                    break  # All tools processed
            else:
                break  # No tool calls, agent finished

        # Save final output
        if tool_pass > 0:
            yield {"type": "tool_result", "text": f"完成 {tool_pass+1} 轮交互"}

    def add_to_history(self, role: str, content: str):
        self._history.append({"role": role, "content": content})
