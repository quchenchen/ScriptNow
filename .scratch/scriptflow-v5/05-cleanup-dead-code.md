# 05 · 死代码清理

- **Status**: done
- **Type**: refactor
- **Blocked by**: 03
- **Blocks**: 09, 13
- **Est**: S
- **Parent PRD**: docs/PRD-V5.md §User Stories #53

## What to build

以下代码不被任何 caller 使用，且干扰未来 contributor 阅读：

- `backend/app/agents/{writing,structure,review,asset_prompt}_agent.py` — LangGraph 风 BaseAgent 子类，依赖损坏的 `get_llm()` 和 config 里不存在的常量
- `backend/app/agents/base.py` — 上述基类
- `backend/app/core/state.py` — LangGraph 风 AgentState TypedDict（未使用）
- `backend/app/core/context_engine.py::save_episode_context` — 用中文正则 + 黑名单从 LLM 输出猜角色/伏笔的浅模块

删除动作 —— 保留可能有用的思路以注释形式记录到 team.py / context_engine.py 的模块 docstring 里（未来读者能追溯到"为什么删了"）。

## Acceptance criteria

- [x] `backend/app/agents/` 只剩 `team.py` + `__init__.py`
- [x] `backend/app/core/state.py` 删除
- [x] `backend/app/core/agent_orchestra.py` 删除（issue #03 完成）
- [x] `backend/app/core/llm_gateway.py` 删除（issue #03 完成）
- [x] `backend/app/core/context_engine.py::save_episode_context` 函数删除；同文件的 `build_context` 保留（agent memory 上下文注入还在用）
- [x] `grep -r "AgentState\|BaseAgent\|save_episode_context" backend/app` 只在注释里出现（解释为什么删了）
- [x] 后端能正常启动 — smoke test（health + OpenAPI）通过
- [x] `ruff check app/ tests/` 全通过

## Notes

- 一次 commit 完成（因为 #03 大重构 + #05 清理紧耦合，split 反而增加读者理解成本）
- Ralph Loop 六维评审的 prompt 内容留在 `docs/adr/0003-agent-tiered-decision.md` 里，issue #09 复用时按 skill 形式落地
- Character/Foreshadow 从文本正则抽取的想法**明确放弃** — 让 LLM 用 Toolkit 主动上报（这是 issue #03 引入的新纪律）
