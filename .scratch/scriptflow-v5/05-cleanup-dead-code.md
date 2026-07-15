# 05 · 死代码清理

- **Status**: proposed
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

删除动作 —— 但**保留可能有用的思路以注释形式**记录到 `docs/adr/` 或直接在删除 commit 的 message 里：

- Ralph Loop 六维评审的 prompt 思路 → 到 issue #09 复用
- Foreshadow / Character 从文本抽取的想法 → 明确放弃，让 LLM 用 Toolkit 主动上报（不再事后猜）

## Acceptance criteria

- [ ] `backend/app/agents/` 只剩 `team.py` + 新的 stage-specific agents（如果 03 已实现）
- [ ] `backend/app/core/state.py` 删除
- [ ] `backend/app/core/context_engine.py::save_episode_context` 函数删除；同文件的 `build_context` 保留（还有用）
- [ ] `grep -r "AgentState\|BaseAgent\|save_episode_context" backend/app` 无结果
- [ ] 后端能正常启动，现有端点全部 200
- [ ] Commit message 记录删除清单 + 删除理由指向 ADR-0002

## Notes

- 分两个 commit：先删 agents/*、base.py、state.py 一个 commit；再删 context_engine 里的猜函数一个 commit
- Ralph Loop 的六维 prompt 内容记得移到 `backend/app/skills/review/` 里作为新 skill 输入
