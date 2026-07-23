# V7 ADR-0004：产品事件与瞬时运行流分离

- Status: Accepted
- Date: 2026-07-20
- Scope: V7 only

## Context

AgentScope 的 Text/Thinking/Data/Tool 增量用于生成期反馈，而项目活动流用于长期审计和用户回看。若把 delta 直接写入 `project_events`，活动流会被噪声污染，也违背 PRD TR-2.5.2；若完全不持久化运行流，刷新和断线后又无法恢复最终输出与确认状态。

## Decision

- `project_events` 仅保存 `chat/node/decision/system` 产品事件，保持 append-only；同组聚合只在查询投影中完成。
- `run_stream_events` 保存按 `(run_id, sequence)` 排序的可恢复运行事件。SSE cursor 指向 sequence，重复 `event_key` 幂等返回原事件。
- 产品事件完整携带 `event_id/schema_version/actor/aggregate/causation_id/correlation_id/idempotency_key/occurred_at`；业务事实仍由正文、Finding、记忆、账务等领域表承担。
- 上下文压缩在同一事务中追加一条 `memory_audit(operation=compress)` 与一条 `system` 产品事件。事件包含强制保留策略和记忆治理深链，不复制记忆正文。
- 工具细粒度 Start/Delta/End 只进入运行流；完成后映射为不可变 `node` 摘要。查询端可显示 ×N，但不得更新历史行。

## Consequences

- 刷新和 SSE 重连可按 cursor 恢复，同时项目活动流保持可读。
- 运行流与产品事件拥有不同保留期和性能策略，但必须共享 run/correlation 标识。
- 任何新事件类型必须先定义事实源与投影边界，禁止用事件表替代领域表。
