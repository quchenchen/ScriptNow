# P0-02 AgentScope 端到端 tracer bullet

- Label: ready-for-agent
- Status: completed-with-production-environment-gate

## 验收

- 流式运行、工具调用、用户确认续跑与取消均有测试。
- fallback/retry 的 token 计量不重不漏。
- AgentState 可持久化并恢复 pending 状态。
- SSE 支持 run_id、游标、heartbeat、断线恢复和去重。
- Studio trace 深链与 DockerWorkspace 路径隔离实测通过。

## 已完成

- 11 个新增 tracer/协议/观测测试覆盖流式、确认、恢复、中断、fallback、usage、SSE cursor 与 OTel spans。
- 结果与风险：`docs/v7-spec-v1.1/references/P0-02-AGENTSCOPE-TRACER-RESULT.md`。

## 环境门

- Studio/agentscope-runtime 未安装。
- Docker daemon 未运行；生产沙箱能力不得宣称已验证。
