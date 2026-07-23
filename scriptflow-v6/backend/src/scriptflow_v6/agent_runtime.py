from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .runtime_config import runtime_config


@dataclass(frozen=True)
class StoryCoreDraft:
    title: str
    logline: str
    dramatic_question: str
    protagonist: str
    conflict: str
    promise: str
    source_strategy: str


@dataclass(frozen=True)
class ManuscriptDraft:
    title: str
    content: str
    state_delta: dict
    thread_actions: list[dict]


@dataclass(frozen=True)
class SelectionEditDraft:
    replacement_text: str
    rationale: str


class CreativeRuntime(Protocol):
    name: str

    async def shape_story_cores(
        self, *, title: str, goal_type: str, seed: str, source_text: str
    ) -> list[StoryCoreDraft]: ...

    async def draft_opening(self, *, context_pack: dict) -> ManuscriptDraft: ...

    async def rewrite_selection(self, *, command: dict) -> SelectionEditDraft: ...


class MockCreativeRuntime:
    """Deterministic adapter for local demos and tests; never presented as a model run."""

    name = "mock"

    async def shape_story_cores(
        self, *, title: str, goal_type: str, seed: str, source_text: str
    ) -> list[StoryCoreDraft]:
        anchor = (seed or source_text or title).strip()[:70].replace("\n", " ")
        is_adapt = goal_type.startswith("adapt")
        strategies = [
            ("人物驱动", "把无法回避的个人选择放到故事中心", "主角能否在失去重要关系前承认真正的欲望？"),
            ("悬念驱动", "让真相的代价逐层升级", "主角揭开真相时，是否也会摧毁自己想守护的一切？"),
            ("关系驱动", "用两种相反价值观持续碰撞", "彼此需要又彼此伤害的人，能否共同完成一次改变？"),
        ]
        return [StoryCoreDraft(
            title=f"方向 {index} · {name}",
            logline=f"围绕“{anchor}”，一位被迫行动的人进入不断收紧的困境，并为最终选择付出不可逆代价。",
            dramatic_question=question,
            protagonist="一个拥有明确缺口、却不断回避真实需求的行动者",
            conflict="外部目标的时间压力，与人物不愿面对的内在真相互相放大",
            promise=promise,
            source_strategy=("保留原作核心关系与关键因果，重构媒介表达和场景节奏" if is_adapt else "从创作种子推演，不引入项目外部设定"),
        ) for index, (name, promise, question) in enumerate(strategies, 1)]

    async def draft_opening(self, *, context_pack: dict) -> ManuscriptDraft:
        project = context_pack["project"]
        core = context_pack["story_core"]
        ordinal = context_pack["scope"]["unit"]
        is_novel = project["goal_type"].endswith("novel")
        previous = context_pack.get("previous_unit")
        directives = context_pack.get("user_directives", [])
        if is_novel:
            content = ((f"上一章留下的问题仍在发酵。{previous['content_tail']}\n\n" if previous else "") +
                "雨从凌晨开始就没有停。\n\n"
                f"他站在门口，手里攥着那件足以让生活偏离原轨的东西。{core['logline']}"
                "可真正让他迟迟没有推门的，并不是恐惧，而是一个不该再次出现的名字。\n\n"
                "走廊尽头传来电梯抵达的轻响。他终于明白，留在原地也已经是一种选择。"
            )
        else:
            content = ((f"【承接】{previous['content_tail']}\n\n" if previous else "") +
                f"【场景 {ordinal}】内景 · 清晨 · 门厅\n\n"
                "雨声贴着窗玻璃滑落。主角站在门边，手里攥着那件足以改变生活的东西。\n\n"
                "门外，电梯抵达。提示音响起。\n\n"
                "主角没有开门。他低头看见那个不该再次出现的名字，终于抬手按下门把。"
            )
        required_facts = context_pack.get("required_story_facts", [])
        for fact in required_facts:
            if is_novel:
                content += f"\n\n{fact['label']}在这一刻进入故事。{fact['requirement']}"
            else:
                content += f"\n\n【{fact['action']}】{fact['label']}进入场面。{fact['requirement']}"
        return ManuscriptDraft(
            title=(f"第{ordinal}章 · 门外的名字" if is_novel else f"第{ordinal}场 · 门外的名字") + (" · 按导演要求" if directives else ""),
            content=content,
            state_delta={"核心行动者": {"emotion": "戒备转为被迫行动", "knowledge_add": ["异常事件已经主动找上门"]}},
            thread_actions=[{"thread_type": "plot_promise", "action": "plant", "note": "以不该出现的名字首次具象化核心悬念"}],
        )

    async def rewrite_selection(self, *, command: dict) -> SelectionEditDraft:
        text = command["selected_text"].strip()
        mode = command["mode"]
        if mode == "shorten":
            replacement = text[:max(1, int(len(text) * 0.6))].rstrip("，。；：、 ") + "。"
        elif mode == "expand":
            replacement = f"{text}\n\n动作停顿了一瞬，人物没有立刻解释，让未说出口的意图留在场面里。"
        elif mode == "polish":
            replacement = re.sub(r"\s+", " ", text).replace(" ,", "，").replace(" .", "。")
        elif mode == "dialogue":
            replacement = f"“{text.strip('“”')}”"
        elif mode == "pace":
            replacement = text.replace("然后", "").replace("接着", "")
        elif command.get("required_fact"):
            fact = command["required_fact"]
            if command.get("unit_type") == "scene":
                replacement = f"{text}\n\n{fact['label']}进入场面。\n\n{fact['requirement']}"
            else:
                replacement = f"{text}\n\n{fact['label']}不再只是背景信息。{fact['requirement']}"
        else:
            replacement = text
        return SelectionEditDraft(replacement_text=replacement, rationale=f"按 {mode} 模式生成局部候选，未改动选区外正文")


class AgentScopeCreativeRuntime:
    """Thin product adapter over AgentScope 2.0; orchestration remains framework-owned."""

    name = "agentscope"

    def __init__(self, model_id: str = "qwen-plus") -> None:
        self.model_id = model_id

    def _model(self):
        if runtime_config.configured or os.getenv("SCRIPTFLOW_API_KEY"):
            from agentscope.credential import OpenAICredential
            from agentscope.model import OpenAIChatModel

            return OpenAIChatModel(
                credential=OpenAICredential(
                    api_key=runtime_config.api_key or os.environ["SCRIPTFLOW_API_KEY"],
                    base_url=runtime_config.api_base if runtime_config.configured else os.getenv("SCRIPTFLOW_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                ),
                model=self.model_id,
                stream=False,
            )
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel

        return DashScopeChatModel(
            credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
            model=self.model_id,
            stream=False,
        )

    async def shape_story_cores(
        self, *, title: str, goal_type: str, seed: str, source_text: str
    ) -> list[StoryCoreDraft]:
        from agentscope.agent import Agent, ReActConfig
        from agentscope.message import Msg, TextBlock

        skill_path = Path(__file__).parent / "skills" / "story-core-shaping" / "SKILL.md"
        system_prompt = skill_path.read_text(encoding="utf-8")
        model = self._model()
        agent = Agent(
            name="creative_director", system_prompt=system_prompt, model=model,
            react_config=ReActConfig(max_iters=3),
        )
        payload = json.dumps({"title": title, "goal_type": goal_type, "seed": seed, "source": source_text}, ensure_ascii=False)
        reply = await agent.reply(Msg(name="user", role="user", content=[TextBlock(type="text", text=payload)]))
        data = _extract_json(reply.get_text_content())
        drafts = [StoryCoreDraft(**item) for item in data]
        if len(drafts) != 3:
            raise ValueError("Creative Director 必须交付三个 Story Core 候选")
        return drafts

    async def draft_opening(self, *, context_pack: dict) -> ManuscriptDraft:
        from agentscope.agent import Agent, ReActConfig
        from agentscope.message import Msg, TextBlock

        skill_path = Path(__file__).parent / "skills" / "opening-draft" / "SKILL.md"
        model = self._model()
        agent = Agent(name="scene_writer", system_prompt=skill_path.read_text(encoding="utf-8"),
                      model=model, react_config=ReActConfig(max_iters=3))
        message = Msg(name="user", role="user", content=[TextBlock(
            type="text", text=json.dumps(context_pack, ensure_ascii=False))])
        data = _extract_object((await agent.reply(message)).get_text_content())
        return ManuscriptDraft(**data)

    async def rewrite_selection(self, *, command: dict) -> SelectionEditDraft:
        from agentscope.agent import Agent, ReActConfig
        from agentscope.message import Msg, TextBlock

        skill_path = Path(__file__).parent / "skills" / "selection-edit" / "SKILL.md"
        agent = Agent(
            name="manuscript_editor",
            system_prompt=skill_path.read_text(encoding="utf-8"),
            model=self._model(),
            react_config=ReActConfig(max_iters=3),
        )
        message = Msg(name="user", role="user", content=[TextBlock(
            type="text", text=json.dumps(command, ensure_ascii=False),
        )])
        data = _extract_object((await agent.reply(message)).get_text_content())
        return SelectionEditDraft(
            replacement_text=data["replacement_text"], rationale=data["rationale"],
        )


def _extract_json(text: str) -> list[dict[str, str]]:
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError("Agent 未返回 JSON 数组")
    value = json.loads(match.group(0))
    if not isinstance(value, list):
        raise ValueError("Agent 返回结构无效")
    return value


def _extract_object(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Agent 未返回 JSON 对象")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Agent 返回结构无效")
    return value


def creative_runtime() -> CreativeRuntime:
    if runtime_config.configured or os.getenv("SCRIPTFLOW_API_KEY") or os.getenv("DASHSCOPE_API_KEY"):
        model = runtime_config.model if runtime_config.configured else os.getenv("SCRIPTFLOW_MODEL", "qwen-plus")
        return AgentScopeCreativeRuntime(model)
    return MockCreativeRuntime()
