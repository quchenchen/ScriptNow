# 03 · LLM 单一路径 + AgentScope 原生 Toolkit

- **Status**: proposed
- **Type**: refactor
- **Blocked by**: 01
- **Blocks**: 05, 09
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #52, #54

## What to build

当前有三份 LLM 访问实现：
- `core/llm_gateway.py`（依赖不存在的 `LLM_CONFIG`）
- `core/llm_client.py`（不同 provider 注册表）
- `core/agent_orchestra.py`（bypass 两套，直接用 AgentScope）

且 `agent_orchestra` 里主动关闭 AgentScope Toolkit（`toolkit=None`），用正则从流式文本抠 JSON 工具调用。

收敛成单一路径 + 用 AgentScope 原生工具调用。

- 新建 `backend/app/agents/team.py` 作为唯一 LLM 出口（`AgentTeam` 类）
- 用 AgentScope `Agent` + `Toolkit` + `register_tool_function` API
- 4 个工具函数：`save_episode_scene`（保存场景）、`query_characters`、`plant_foreshadow`、`resolve_foreshadow`
- 删掉 `llm_gateway.py`、`llm_client.py`（保留 provider 注册信息合并到 config.py 或新的 `llm_providers.py`）
- `api/workspace.py` 的 `/agent/chat` 改成调用 `AgentTeam.run(...)`，不再有正则解析

## Acceptance criteria

- [ ] `backend/tests/test_agent_team.py` 通过（mock model → 验证工具函数被正确调用）
- [ ] `/api/workspace/{pid}/agent/chat` SSE 流保留（前端不需要改）
- [ ] Writing Agent 完成一集 → 通过原生 tool 调用 save_episode_scene → 数据入库正确
- [ ] `llm_gateway.py` 和 `llm_client.py` 删除或降级为薄 shim
- [ ] agent_orchestra.py 里的正则 tool 解析代码块整段删除

## Notes

- Provider 注册（deepseek / dashscope / openai / anthropic）保留可切换
- AgentScope 版本锁定 `>=2.0.0,<3.0.0`
- 工具调用失败要有 fallback（tool 抛异常 → agent 得到错误消息 → 可 retry），不能 500
