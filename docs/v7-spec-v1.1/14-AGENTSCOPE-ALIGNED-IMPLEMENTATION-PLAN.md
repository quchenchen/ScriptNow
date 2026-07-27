# AgentScope 对齐的创作管线实施计划

| | |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-07-28 |
| 状态 | 执行中 |
| 架构决策 | ADR-0012 |
| 技术审计 | `13-CREATIVE-FLOW-TECHNICAL-AUDIT.md` |

## 1. 目标

把小说、剧本、翻译和归化翻译统一到同一套**运行语义**，同时保持四套领域产物独立。用户发起任务后应立即看到准确进度，正文或结构逐步可见，失败可定位、可修复、可恢复，不再让一个巨型 Agent 调用阻塞整个环节。

管线基线：

```text
accept
  → prepare_context
  → semantic_plan
  → generate
  → decode
  → domain_validate
  → quality_gate
  → persist_candidate
  → publish
```

任何阶段均必须有明确输入、输出、状态、超时、错误类型和重试责任。

## 2. 与 AgentScope 的吻合性结论

| 规划项 | AgentScope 对应能力 | 结论 |
|---|---|---|
| 思考、正文、工具分离 | Thinking/Text/Data Block、tool events | 原生吻合 |
| 流式候选 | `reply_stream()` Block 事件 | 原生吻合 |
| 多步推理与工具 | ReActConfig、Toolkit、Skill、MCP | 原生吻合 |
| 人工确认后续跑 | confirm/interrupt event + AgentState | 原生吻合 |
| Provider fallback | ModelConfig/fallback | 原生吻合 |
| 领域契约与候选版本 | 无 | 必须由 ScriptNow 实现 |
| 长任务持久化检查点 | AgentState 只覆盖 Agent 状态 | 必须由 ScriptNow 实现 |
| 主动生成取消 | 取消 asyncio task | ScriptNow 负责生命周期 |
| 产品事件游标与恢复 | 框架事件可桥接 | ScriptNow 负责耐久投影 |

因此方案不是绕开 AgentScope，而是补齐它有意不承担的产品领域与持久化职责。

## 3. 实施顺序

### P0：正确性止血

- [x] Script StoryMap 兼容等价 Provider 包装，并规范化可判定的锚点引用。
- [x] 契约错误不再把 Pydantic/AgentScope 原始异常直接展示给用户。
- [x] Script 运行只有在领域校验通过后才标记 `SUCCEEDED`。
- [ ] 将相同成功边界审计扩展到 Novel、Translation、Recreation。
- [ ] 为每条入口增加“成功状态必须存在可消费 artifact”的集成测试。

退出门槛：

- 不存在 run succeeded 但页面拿不到产物的路径；
- 契约失败统一记录 `contract_invalid`，Provider 失败单独分类；
- 重试次数、时限均来自运行策略而非业务硬编码。

### P1：公开事件桥与取消语义

- [x] 用 `Agent.reply_stream()` 替换 `Agent._reply`。
- [x] 建立 AgentScope event → product event 映射表及契约测试。
- [x] Thinking、Text、Tool 分通道投影，正文不再靠字符串剥离。
- [x] 建立应用级活跃 task registry；首批接入后台章节生成与关闭回收。
- [ ] 将 active task registry 扩展到 Script、Translation、Recreation 的全部后台入口。
- [ ] Confirm 通道接入产品事件并实现等待态恢复。
- [ ] parked confirmation 使用 AgentState 恢复，验证只执行一次。

退出门槛：

- 无 AgentScope 私有 API；
- 刷新、断线重连、取消、确认均可测试；
- 同一框架事件不会生成重复产品事件。

### P2：耐久 Creative Operation

- [ ] 新增 operation/stage/artifact/checkpoint 契约与迁移。
- [ ] API 在 500ms 内返回 operation ID；重任务在后台继续。
- [ ] 每阶段独立状态：queued/running/validating/repairing/ready/failed/cancelled。
- [ ] artifact 记录 schema version、输入摘要、依赖版本和 provenance。
- [ ] 支持从最后一个完整 checkpoint 恢复，不重跑已成功阶段。

退出门槛：

- 服务重启后任务状态与已完成产物不丢失；
- 页面状态由 stage 事实投影，不使用定时重复提示；
- 可按 operation/run/stage/trace 追踪一次创作。

### P3：四领域接入

1. **Script**：StoryCore → Blueprint → Episode/Scene/Beat → Scene blocks → Review。
2. **Novel**：StoryCore → Novel Blueprint → Volume/Chapter/Beat → Chapter revision → Review。
3. **Translation**：Chapter source → terminology context → translated revision → compare → confirm。
4. **Recreation**：source analysis → protected invariants → strategy → trial → blueprint → chapter pipeline。

每个领域分别声明：

- stage graph；
- Pydantic/TypeScript schema；
- context selector；
- validator 与 targeted repair；
- candidate/adopt/version 规则；
- quality gate 与人类决策点。

退出门槛：

- 不共享领域 DTO 或 Writer；
- 后续章节只读取最新已确认版本与已确认术语；
- 页面栏目与后台 stage 一一对应，不再“一页全落下来”。

### P4：速度、成本与质量闭环

- [ ] Fast/Deep 两条执行车道；由任务风险和用户选择决定。
- [ ] Context manifest 只装载变更影响范围，不重复发送完整工程。
- [ ] 低成本模型承担抽取、分类、图谱增量和格式检查；高质量模型承担创意判断与正文。
- [ ] 以阶段统计首响应、首正文、完成时长、tokens、修复率、人工改写率。
- [ ] 建立题材/语言/媒介分层质量基准与回归集。

首批目标值：

| 指标 | 目标 |
|---|---:|
| 接受请求 | < 500 ms |
| 首个真实状态 | < 1 s |
| 正文首段 | < 12 s |
| 约 1200 词章节候选 | < 75 s |
| StoryMap 完整候选 | < 45 s |
| 刷新恢复视图 | < 2 s |

目标值作为运行策略和监控阈值配置，不写入领域代码。

## 4. 已落地的实现

本轮先修改 Script 生成器的成功边界：

```text
AgentScope 返回
  → JSON 解码/修复
  → 领域 validator
  → validator 通过
  → run = SUCCEEDED
```

若领域 validator 失败，run 记为 `FAILED / script_contract_invalid`，调用方可以执行一次有界、带拒绝原因的定向修复。该修复不冒充成功，也不覆盖已有候选。

P1 首批实现已完成：

- 规划阶段只使用 AgentScope 公共 `reply_stream()`，不再调用私有 `_reply`；
- 公开 Text delta 聚合为可审计的创作策略，Thinking delta 不进入正文或策略输入；
- Thinking、Text、Tool、Phase 事件继续使用 AgentScope block/event identity；
- 应用级 `ActiveRunRegistry` 持有可取消任务，后台章节取消会终止 asyncio task；
- 章节任务收到取消后释放预算、停止心跳、记录 `CANCELLED`，应用关闭也会回收活跃任务。

当前取消注册范围仅覆盖后台章节生成。Script、Translation、Recreation 入口必须在
P1 退出前全部接入同一 registry；不得把当前局部接入描述为全系统完成。

## 5. 风险与控制

| 风险 | 控制 |
|---|---|
| 把管线层做成第二套 Agent 框架 | ADR-0012 边界审查；Agent 行为必须走 AgentScope |
| 为追求流式而持久化每个 token | delta 只转发，阶段/产物完成才落库 |
| DataBlock 能力因 Provider 不一致 | 先 tracer，再启用；保留严格 Text JSON 路径 |
| 自动修复掩盖模型或 Skill 缺陷 | 修复次数有上限，原始拒绝原因与 trace 保留 |
| 跨领域“复用”再次污染 | 只共享 platform kernel，各领域 schema 与服务独立 |
| 性能优化降低创作质量 | Fast/Deep 分道，质量基准与人工改写率共同评估 |
