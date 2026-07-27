# ADR-0012：AgentScope 与创作管线的职责边界

- 状态：Accepted
- 日期：2026-07-28
- 依据：PRD §2、AgentScope 2.0.4 验证记录、P0 tracer、创作流程技术审计

## 问题

ScriptNow 需要把小说、剧本、翻译与归化翻译做成可恢复、可观测、可逐步交付的长流程。AgentScope 已提供 Agent、ReAct、Block 流、工具、Skill、MCP、确认/中断和 AgentState。如果 ScriptNow 再实现一套并行 Agent 运行时，会重复造轮子；如果把完整产品状态机交给 AgentScope，又会丢失领域事务、版本、采纳和租户治理边界。

## 决策

采用“两层一桥”，不建立第二套 Agent 框架：

1. **AgentScope 语义运行层**
   - Agent、模型调用、fallback、ReAct 迭代；
   - Thinking/Text/Data Block 与工具事件；
   - Toolkit、Skill、MCP、工具确认；
   - parked reply 的 AgentState 序列化与恢复；
   - tracing 与模型调用计量原始信号。
2. **ScriptNow 产品管线层**
   - operation/stage/artifact 的持久化状态；
   - tenant、幂等、配额、超时、主动取消和恢复；
   - Script、Novel、Translation、Recreation 各自的领域校验；
   - Candidate、人工修订、采纳、版本、回滚和导出；
   - 用户可见状态、错误分类和事件游标。
3. **Event Bridge**
   - 消费 `Agent.reply_stream()` 的公开事件；
   - Text/Thinking delta 只实时转发，不逐条持久化；
   - 工具、确认、阶段、产物完成和错误形成稳定产品事件；
   - 使用框架事件 ID 与产品 run/stage ID 去重。

## 边界矩阵

| 能力 | 责任归属 | 约束 |
|---|---|---|
| 推理循环与 `max_iters` | AgentScope | 参数来自租户/角色/任务策略 |
| Thinking/Text/Data Block | AgentScope | ScriptNow 不用字符串规则猜测思考与正文 |
| Skill、Tool、MCP | AgentScope Toolkit | ScriptNow 只做准入、挂载和权限治理 |
| 模型 fallback | AgentScope | 每次实际调用仍由 ScriptNow 计量 |
| 等待工具确认 | AgentScope AgentState + ScriptNow run | 状态落库，恢复必须幂等 |
| 活跃生成取消 | ScriptNow task registry | 取消 asyncio task，并持久化 cancelled |
| 长流程 stage/checkpoint | ScriptNow | AgentState 不能替代业务检查点 |
| JSON 解码 | 适配层 | 解码成功不等于任务成功 |
| 领域结构与语义约束 | 各领域 | 校验通过前不得标记 succeeded |
| 候选、修订、采纳、回滚 | 各领域 | Agent 永不直写已采纳事实 |
| SSE 游标、聚合、去重 | ScriptNow | 不复制 AgentScope 内部 span 模型 |

## 强制实现规则

1. 只调用 AgentScope 公开 API；禁止使用 `Agent._reply` 等私有接口。
2. 正文来自 TextBlock，思考来自 ThinkingBlock，工具活动来自工具事件；三者分别投影。
3. `SUCCEEDED` 表示“领域产物已通过校验并可供下一阶段消费”，不能表示“模型有返回”或“JSON 可解析”。
4. Provider 临时错误由 AgentScope 模型层重试/fallback；契约错误由领域层做有上限的定向修复。两种重试不得混用。
5. 主动取消通过任务取消实现；`UserInterruptEvent` 只用于框架支持的 parked reply 恢复路径。
6. DataBlock 结构化输出只有通过当前 Provider/AgentScope tracer 后才能用于生产契约；未验证前使用 TextBlock JSON + 严格领域校验，不宣称原生 schema 保证。
7. Script 与 Novel 只共享上述运行语义，不共享 StoryMap、正文、Writer、审读或导出模型。

## 不采用的方案

### 把 AgentScope 当普通 LLM SDK

会重新实现 Block、工具循环、确认、状态和 tracing，升级成本与行为偏差不可接受。

### 把整个产品工作流塞进一个 ReAct Agent

无法可靠表达领域事务、版本、人工决策和跨请求恢复，也会放大上下文、时延与成本。

### 解析一大段最终文本后再猜产物

无法稳定区分思考、正文与工具信息，且失败发生得太晚。管线必须按阶段产出可校验 artifact。

## 后果

- AgentScope 继续作为唯一 Agent 运行底座，Creative Pipeline Kernel 是产品编排层而非竞争运行时。
- 当前使用私有 `_reply` 的规划流必须迁移到 `reply_stream()`。
- 各领域生成器必须把领域校验纳入 run 成功事务。
- 升级 AgentScope 时以 tracer 与边界契约作为回归门槛。
