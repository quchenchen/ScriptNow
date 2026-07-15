# 03 · LLM 单一路径 + AgentScope 原生 Toolkit

- **Status**: done
- **Type**: refactor
- **Blocked by**: 01
- **Blocks**: 05, 09
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #52, #54

## What to build

当前有三份 LLM 访问实现：
- `core/llm_gateway.py`（依赖不存在的 `LLM_CONFIG`）— 完全无法 import
- `core/llm_client.py::LLMClient`（另一份 provider 抽象）— 未被任何模块 import
- `core/agent_orchestra.py::AgentTeam`（生产链路，正则解析工具调用）

且 `agent_orchestra` 里主动关闭 AgentScope Toolkit（`toolkit=None`），用正则从流式文本抠 JSON 工具调用。

收敛成单一路径 + 用 AgentScope 原生工具调用。

- 新建 `backend/app/agents/team.py` 作为唯一 LLM 出口（`AgentTeam` 类）
- 用 AgentScope `Agent` + `Toolkit` + `FunctionTool` API
- 4 个工具函数：`save_episode`、`query_characters`、`plant_foreshadow`、`resolve_foreshadow`
- 删掉 `llm_gateway.py`；`llm_client.py` 修剪成薄 registry（保留 PROVIDERS + list_available_models 供 model picker 用）
- `api/workspace.py` 的 `/agent/chat` 改成调用 `AgentTeam.run(...)`，不再有正则解析

## Acceptance criteria

- [x] `backend/tests/test_agent_tools.py` 通过 — 5 test 验证 4 个工具函数各自能读写 DB + Toolkit schema 提取
- [x] `/api/workspace/{pid}/agent/chat` SSE 流保留（前端不需要改）— 事件形状不变：`{type: "text_delta" | "thinking" | "tool_result" | "error", text: str}`
- [x] Writing Agent 完成一集 → 通过 AgentScope 原生 tool 调用 save_episode → 数据入库（test_save_episode_creates_row 覆盖）
- [x] `llm_gateway.py` 删除；`llm_client.py` 降级为薄 registry（无 LLMClient 类）
- [x] `agent_orchestra.py` 整个文件删除（含 250 行的正则 tool 解析）

## Notes

- Provider 注册（deepseek / dashscope / openai / anthropic）保留在 `core/llm_client.py`
- 路由：`_build_model(model_id)` 根据 `provider:model` 派发到 AgentScope 对应的 ChatModel + Credential
- AgentScope 事件流由 `_translate_event(event)` 转换成前端 SSE 事件，无 tool 参数格式硬编码
- Tool 调用失败会自然回落到 agent — tool 返 `{ok: False, error: ...}` 被喂回下一轮，agent 可 retry；不会 500
