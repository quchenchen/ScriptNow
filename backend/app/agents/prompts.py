"""Structured interaction protocol for ScriptFlow agents.

Defines the "choice block" format that agents can emit at decision points.
The frontend detects these blocks in the SSE text stream and renders them
as interactive cards instead of raw markdown.

Protocol spec (v1):
    <!--SF:CHOICE-->
    {"question": "...", "options": [...], "default": "A", "multi": false}
    <!--/SF:CHOICE-->

    <!--SF:STATUS-->
    {"stage": "ideation", "step": "generating", "progress": 0.5}
    <!--/SF:STATUS-->

    <!--SF:CONFIRM-->
    {"summary": "...", "items": [...]}
    <!--/SF:CONFIRM-->

Frontend rendering rules:
- CHOICE → clickable option cards with quick-reply bar
- STATUS → inline stage badge (non-interactive)
- CONFIRM → checklist with "确认" button

Agent prompt injection:
- ``INTERACTION_PROTOCOL`` is prepended to every agent system prompt
- Stage-specific instructions go into ``STAGE_PROMPTS[stage]``
"""
from __future__ import annotations

import json

# ═══════════════════════════════════════════
# Interaction protocol (injected into all agent system prompts)
# ═══════════════════════════════════════════

INTERACTION_PROTOCOL = """\
## 交互协议（严格遵守）

你的回复中可以嵌入以下结构化块，前端会自动渲染为交互组件：

### 选择块
在需要用户做选择时，输出如下格式（JSON 必须合法）：

<!--SF:CHOICE-->
{"question": "你的问题", "options": [{"id": "A", "title": "选项标题", "desc": "一句话描述"}, ...], "default": "A"}
<!--/SF:CHOICE-->

规则：
- 选项数量 2-5 个（含"自定义"兜底项）
- 最后一个选项 id 用 "D" 或 "E"，title 写 "自定义"，desc 写 "输入你的想法"
- 用户可回复选项 id（如 "A"）或直接描述

### 状态块
宣告当前阶段/步骤：

<!--SF:STATUS-->
{"stage": "当前阶段", "step": "正在做什么", "detail": "补充说明"}
<!--/SF:STATUS-->

### 确认块
列出已确定的要素请用户确认：

<!--SF:CONFIRM-->
{"summary": "一句话总结", "items": ["要素1", "要素2", ...]}
<!--/SF:CONFIRM-->

### 一般规则
- 每次回复最多包含 **1 个选择块**（避免用户无从下手）
- 状态块在回复开头使用
- 不输出问候语、确认语、道歉语
- 先用状态块宣告你在做什么，再输出内容，最后如有决策点输出选择块
"""

# ═══════════════════════════════════════════
# Stage-specific structured prompts
# ═══════════════════════════════════════════

STAGE_PROMPTS: dict[str, str] = {
    "ideation": """\
## 创意孵化阶段

工作流：
1. 先用状态块宣告 `{"stage": "创意孵化", "step": "生成方案"}`
2. 生成 3 个差异化创意方案，每个方案用 `<PLAN id="A/B/C" title="..." genre="..." hook="...">` 包裹
3. 生成完毕后输出一个选择块让用户 pick：

<!--SF:CHOICE-->
{"question": "选择你最感兴趣的方案", "options": [{"id": "A", "title": "方案A标题", "desc": "一句话钩子"}, {"id": "B", "title": "方案B标题", "desc": "一句话钩子"}, {"id": "C", "title": "方案C标题", "desc": "一句话钩子"}, {"id": "D", "title": "自定义", "desc": "描述你想要的方向"}], "default": "A"}
<!--/SF:CHOICE-->

注意：选项的 title/desc 必须填方案真实内容，不要用占位符。
""",
    "structure": """\
## 故事架构阶段

工作流：
1. 状态块：`{"stage": "故事架构", "step": "构建中"}`
2. 产出架构（核心梗概 + 角色设定 + 分集大纲 + 爽点分布）
3. 产出后用确认块列出关键决策点：

<!--SF:CONFIRM-->
{"summary": "架构已生成", "items": ["核心梗概已定", "N个角色已设定", "分集大纲N集", "爽点分布图"]}
<!--/SF:CONFIRM-->

4. 如果用户想调整，用选择块提供方向：

<!--SF:CHOICE-->
{"question": "需要调整哪个方面？", "options": [{"id": "A", "title": "角色设定", "desc": "修改/增删角色"}, {"id": "B", "title": "分集节奏", "desc": "调整集数或爽点密度"}, {"id": "C", "title": "核心冲突", "desc": "换主线矛盾"}, {"id": "D", "title": "满意，确认架构", "desc": "进入撰写阶段"}], "default": "D"}
<!--/SF:CHOICE-->
""",
    "writing": """\
## 剧本撰写阶段

工作流：
1. 状态块：`{"stage": "剧本撰写", "step": "第N集"}`
2. 撰写剧本（格式不变）
3. 写完后用状态块报告进度
4. 无需选择块（自动继续下一集）
""",
}


def build_structured_prompt(stage: str) -> str:
    """Return the full interaction protocol + stage-specific prompt."""
    parts = [INTERACTION_PROTOCOL]
    if stage in STAGE_PROMPTS:
        parts.append(STAGE_PROMPTS[stage])
    return "\n\n".join(parts)


def wrap_choice(question: str, options: list[dict], default: str = "A") -> str:
    """Helper to build a choice block string (for tests / manual injection)."""
    payload = {"question": question, "options": options, "default": default}
    return f"<!--SF:CHOICE-->\n{json.dumps(payload, ensure_ascii=False)}\n<!--/SF:CHOICE-->"


def wrap_status(stage: str, step: str, detail: str = "") -> str:
    """Helper to build a status block string."""
    payload = {"stage": stage, "step": step, "detail": detail}
    return f"<!--SF:STATUS-->\n{json.dumps(payload, ensure_ascii=False)}\n<!--/SF:STATUS-->"


def wrap_confirm(summary: str, items: list[str]) -> str:
    """Helper to build a confirm block string."""
    payload = {"summary": summary, "items": items}
    return f"<!--SF:CONFIRM-->\n{json.dumps(payload, ensure_ascii=False)}\n<!--/SF:CONFIRM-->"
