# AgentScope 对齐的创作管线实施计划

| | |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-07-28 |
| 状态 | 执行中 |
| 架构决策 | ADR-0012 |
| 技术审计 | `13-CREATIVE-FLOW-TECHNICAL-AUDIT.md` |
| 无界面会话规划 | `15-HEADLESS-CREATIVE-PARTNER-ARCHITECTURE.md` |
| 全系统流程图 | `19-SYSTEM-BUSINESS-FLOW-MAP.md` |

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

创作搭档的运行事实仍按 ADR-0013 的 Creative Session Protocol 边界设计，Web Dock
只是协议客户端，不承担编排或恢复事实源。CLI 与外部 Agent 已降级为备选演进计划，
当前不进入研发主线；详见 `15-HEADLESS-CREATIVE-PARTNER-ARCHITECTURE.md` 的启动条件。

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
- [x] 将 active task registry 扩展到 Script、Translation、Recreation 的全部生成型后台入口；
  Recreation 的源作品分析、归化策略、代表性试写、整书规划和逐章生产均已接入。
- [x] Dock Confirm 通道已接入 DecisionRequest、产品事件和等待态恢复；四领域领域确认仍待
  P3 分批接入。
- [ ] parked confirmation 使用 AgentState 恢复，验证只执行一次。
- [x] 删除 Dock 在完整生成后补造的 thinking/tool fixtures；Data/Text 只投影真实上下文与
  AgentScope 回复。

退出门槛：

- 无 AgentScope 私有 API；
- 刷新、断线重连、取消、确认均可测试；
- 同一框架事件不会生成重复产品事件。

### P2：耐久 Creative Operation

- [x] 新增 session/turn/operation/stage/artifact/checkpoint/decision 最小持久化契约与迁移；
  平台谱系、幂等决定与四领域生成入口已经接入，跨进程精确恢复仍不宣称完成。
- [x] Novel、Script、Translation 与 Recreation 的生成入口在创建耐久 operation 后立即返回；
  重任务由应用级 task registry 在后台继续，前端只轮询持久化运行事实。
- [ ] 每阶段独立状态：queued/running/validating/repairing/ready/failed/cancelled。
- [x] artifact ref 记录 schema version、输入摘要、依赖版本和 provenance；领域产物内容仍留在
  各自模块。
- [ ] 支持从最后一个完整 checkpoint 恢复，不重跑已成功阶段。
- [x] 建立 CreativeSession/Turn/Decision/ArtifactRef 数据契约；Web、创作搭档和未来适配器
  共享该契约。
- [x] Dock 消息入口已持久化 Session、Turn、Operation、StageRun 与 DecisionRequest，
  并在消息响应和运行恢复列表中公开 operation/session/status 标识。
- [x] Novel、Script、Translation、Recreation 领域入口接入相同 Operation 协议。
  - [x] Novel 章节候选生成已接入 CreativeSession / Turn / Operation / StageRun /
    ArtifactRef / Checkpoint；HTTP 入口立即返回 run 与 operation 标识，前端按耐久状态轮询。
  - [x] Novel 的 Run 终态只在候选稿、产物引用、完整检查点和 Operation 终态全部持久化后发布；
    Writer 接受外部 run，消除 API 与 Writer 各创建一次运行的双 Run 问题。
  - [x] Script 场次候选生成已按独立剧本契约接入同一运行协议；Generator 接受平台 run，
    候选场次、ArtifactRef 与 Checkpoint 全部落库后才发布成功终态。
  - [x] Translation 章节翻译已按独立翻译契约接入；单章快速返回运行标识，批量翻译逐章串行
    推进，译文修订、ArtifactRef 与 Checkpoint 落库后才发布成功终态。
  - [x] Recreation 按独立归化领域契约接入，禁止复用 Novel/Script/Translation DTO 或生成器。
    - [x] “读懂原作”已接入后台运行协议；源故事模型落库、ArtifactRef、Checkpoint、
      Stage、Operation 与 Run 共用同一成功边界。
    - [x] “选择策略”已接入后台运行协议；三套候选分别登记 ArtifactRef，共享同一完整
      Checkpoint，生成后保持候选状态，必须由创作者明确采纳。
    - [x] 代表性试写、整书扩展方案与逐章生产均快速返回运行标识；领域候选、
      ArtifactRef 与完整 Checkpoint 落库后才发布成功终态，采纳仍由创作者明确执行。
    - [x] 审读、人工修订与采纳保留为快速领域事务：人工修订创建独立版本并回到待审状态，
      只有再次审读通过并明确采纳后才改变正式事实；这些操作不伪装成长耗时 Agent 生成。

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
- 章节采纳后的创作图谱抽取统一进入串行队列，队列任务由同一 registry 持有；
  应用关闭会先取消并等待图谱任务完成清理，不再遗留异步数据库会话。

当前取消注册范围覆盖后台章节生成、后台剧本场次生成、忠实翻译章节运行、Recreation
源作品分析、归化策略、代表性试写、整书规划、逐章生产与创作图谱队列。后续新增生成阶段
必须接入同一 registry，不得在领域内重新创建无所有者的 task。

Novel 章节生成现已完成第一条领域接入：

- 浏览器只提交一次后台命令并获得 `creative_session_id / operation_id / run_id`；
- `NovelChapterGenerator` 在平台已分配 run 时不再自行创建或提前结束第二个 run；
- AgentScope TextBlock 仍由 Novel Writer 解析为独立 Novel blocks；
- 候选修订落库后登记 `chapter_revision` ArtifactRef，并保存可恢复的完整 Checkpoint；
- Stage 与 Operation 先完成，终止事件落库后 Run 才进入 `SUCCEEDED`，因此外部观察到成功时
  候选稿已经可读；
- run 幂等键包含 project、chapter 与调用方键，防止同租户不同项目互相复用运行。

Script 场次生成现已完成第二条领域接入：

- 浏览器提交后台场次命令后轮询耐久 run，不再让单次 HTTP 请求阻塞至模型完成；
- `ScriptCreativeGenerator` 接受平台预分配 run，保留 Script block 与格式契约，不复用
  Novel Writer 或章节 DTO；
- 候选场次落库后登记 `scene_revision` ArtifactRef，并保存包含场次、修订与产物引用的
  完整 Checkpoint；
- Stage、Operation、终止事件与 Run 使用同一成功边界；前端看到成功时候选已可读取；
- 同步端点继续作为兼容路径，生产创作端默认使用后台运行入口。

## 5. 风险与控制

| 风险 | 控制 |
|---|---|
| 把管线层做成第二套 Agent 框架 | ADR-0012 边界审查；Agent 行为必须走 AgentScope |
| 为追求流式而持久化每个 token | delta 只转发，阶段/产物完成才落库 |
| DataBlock 能力因 Provider 不一致 | 先 tracer，再启用；保留严格 Text JSON 路径 |
| 自动修复掩盖模型或 Skill 缺陷 | 修复次数有上限，原始拒绝原因与 trace 保留 |
| 跨领域“复用”再次污染 | 只共享 platform kernel，各领域 schema 与服务独立 |
| 性能优化降低创作质量 | Fast/Deep 分道，质量基准与人工改写率共同评估 |
