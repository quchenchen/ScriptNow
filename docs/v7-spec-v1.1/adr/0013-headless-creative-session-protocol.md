# ADR-0013：无界面创作会话协议

- 状态：Accepted
- 日期：2026-07-28
- 依据：PRD §2、§3.10、ADR-0012、AgentScope 2.0.4 tracer、创作流程技术审计

## 问题

当前创作搭档被实现为创作端页面里的 Dock。它同时承载聊天、创作决定、领域进度和
运行调试信息，并通过前端状态拼接用户对流程的理解。这样会产生三个结构性问题：

1. Web 页面成为事实上的编排入口，CLI 或外部 Agent 无法复用同一条创作链路；
2. “重点、对话、确认、过程、运行”把不同层级的信息并列，用户无法判断当前在讨论、
   等待决定、执行任务，还是查看技术日志；
3. 页面刷新、换端或服务重启后，Agent 对话、等待确认和领域产物不能依赖同一份耐久状态恢复。

ScriptNow 的目标是：从一句创意到审读、包装和导出均可通过创作搭档完成；Web、CLI
和经授权的外部 Agent 只是不同客户端，最终作品可在管理界面运营。

## 决策

在 ADR-0012 的“两层一桥”之上建立 **Creative Session Protocol（CSP）**。CSP 是
ScriptNow 的公开应用协议，不是第二套 Agent 框架，也不属于任一前端。

### 1. 协议事实

- `CreativeSession`：一次可跨设备、跨进程恢复的创作协作；
- `CreativeTurn`：作者或 Agent 的一次输入及其响应边界；
- `CreativeOperation`：可执行、可取消、可恢复的领域任务；
- `DecisionRequest`：AgentScope parked reply 或领域采纳门形成的待决定事项；
- `ArtifactRef`：候选、修订、审读报告、术语表、包装和导出的版本引用；
- `CreativeEvent`：带全局顺序、因果关系和幂等键的耐久事件信封。

Web、CLI、MCP/A2A 适配器只能通过 CSP 命令和查询访问创作能力，不直接调用领域数据库、
前端 store 或 AgentScope 私有状态。

### 2. AgentScope 边界

- 每个交互回合只通过公开 `reply_stream()` 驱动；
- ThinkingBlock、TextBlock、Tool 事件保持原生身份进入 Event Bridge；
- 原始隐藏思维不作为用户内容输出；用户看到的是可审计的计划摘要、工具活动和决定理由；
- `RequireUserConfirmEvent` 到达时保存 AgentState 与恢复元数据，operation 进入
  `waiting_for_decision`；
- 用户决定通过 `UserConfirmResultEvent` 恢复同一 parked reply，且副作用至多执行一次；
- `UserInterruptEvent` 只打断 parked reply；活跃生成通过取消所属 asyncio task 终止；
- ScriptNow 负责 operation、领域事务、产物、版本和事件游标，AgentScope 负责 Agent
  行为、Block 流、工具循环和框架状态。

### 3. 领域边界

Novel、Script、Translation、Recreation 分别注册自己的命令、输入 schema、阶段图、
候选与采纳规则。CSP 只提供通用会话、运行、决定、产物引用和授权信封，禁止抽象出共享
正文、StoryMap、Writer、审读或导出 DTO。

### 4. 客户端边界

- Web 创作搭档：CSP 的可视化客户端；
- CLI：CSP 的终端客户端，不包含业务逻辑；
- 外部 Agent：通过受限能力适配器调用 CSP；
- 运营管理端：查询已确认产物、版本、用量、审计和发布状态，不承担创作编排。

## 交互信息架构

不再把五个旧标签视为同级导航：

| 信息 | 新位置 | 说明 |
|---|---|---|
| 当前任务与下一步 | 会话首页 | 单一状态摘要，不是事件类型 |
| 作者与创作搭档交流 | 对话 | 只保留可读消息、引用和产物卡 |
| 待批准工具或待采纳候选 | 待决定 | 可操作收件箱，显示影响与恢复点 |
| 阶段、进度与产物 | 工作进度 | 面向创作的 operation/stage 投影 |
| Block、工具、模型、token、trace | 诊断 | 默认隐藏，仅开发或授权角色可见 |

“重点”被取消为固定页签，改为根据未完成决定、失败、风险和新产物生成的会话摘要。

## 后果

- 页面不再是创作工作流的唯一入口；
- CLI 和外部 Agent 可以与 Web 共享会话、确认、进度和产物；
- Dock 必须停止补造 AgentScope 事件和模拟确认恢复；
- 所有领域功能必须能够声明为 CSP command，无法无界面调用的功能不算完成；
- CSP 需要稳定版本、权限、幂等、事件游标和兼容策略。

