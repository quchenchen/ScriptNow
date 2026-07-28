# ScriptNow 全系统业务流程逻辑图

| | |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-07-28 |
| 状态 | v1.1 规范修订单 |
| 范围 | Creator、Dock、Admin、AgentScope、Novel、Script、Translation、Recreation |

## 1. 阅读约定

- 实线表示当前规范和已接入的主链路。
- 虚线表示已批准但尚未完成退出门的目标能力。
- 四个创作领域只共享 platform 运行协议，不共享正文、StoryMap、生成器、审读和导出契约。
- 本文是业务与系统边界图，不以图中出现节点作为“已经生产可用”的证据。

## 2. 全系统上下文

```mermaid
flowchart LR
    Creator["创作者"] --> CreatorSPA["Creator SPA"]
    Creator --> Dock["创作搭档 Dock"]
    Admin["平台管理员"] --> AdminSPA["Admin SPA"]
    External["未来 CLI / 外部 Agent<br/>备选计划"] -.-> Adapter["Creative Session Adapter"]

    CreatorSPA --> API["FastAPI / Auth / Tenant Scope"]
    Dock --> API
    AdminSPA --> AdminAPI["Admin API"]
    Adapter -.-> API

    API --> Kernel["Creative Session + Operation Kernel"]
    Kernel --> Runtime["AgentScope Runtime<br/>reply_stream / Block / Tool / AgentState"]
    Runtime --> DomainRouter{"领域路由"}

    DomainRouter --> Novel["Novel 独立领域"]
    DomainRouter --> Script["Script 独立领域"]
    DomainRouter --> Translation["Translation 独立领域"]
    DomainRouter --> Recreation["Recreation 独立领域"]

    Novel --> Artifacts["候选 / 修订 / 正式版本 / 导出"]
    Script --> Artifacts
    Translation --> Artifacts
    Recreation --> Artifacts

    Artifacts --> Review["人工比较、修订与决定"]
    Review --> Kernel

    AdminAPI --> Governance["Provider / Model / Agent / Skill / MCP<br/>权限 / 额度 / 价格 / 记忆策略"]
    Governance --> Runtime
    Kernel --> PlatformFacts["运行事实<br/>Operation / Stage / ArtifactRef / Checkpoint / Decision"]
    Runtime --> Events["Thinking / Text / Data / Tool 事件桥"]
    Events --> CreatorSPA
    Events --> Dock
    PlatformFacts --> CreatorSPA
    PlatformFacts --> AdminSPA
```

## 3. 作品全生命周期

```mermaid
flowchart TD
    Login["登录与租户校验"] --> Create["四步项目向导"]
    Create --> Contract["项目契约<br/>领域 / 来源 / 语言 / 市场 / 读者 / 篇幅 / 结构"]
    Contract --> Source{"来源模式"}

    Source -->|原创| Ideation["创意发散候选"]
    Source -->|改编| Ingest["上传、解析、RAG 与素材图谱"]
    Source -->|忠实翻译| TPipe["忠实翻译管线"]
    Source -->|故事归化| RPipe["故事归化管线"]
    Ingest --> Ideation

    Ideation --> DirectionDecision["比较 / 反馈 / 修订 / 采纳方向"]
    DirectionDecision --> Blueprint["领域蓝图候选"]
    Blueprint --> BlueprintDecision["人工修订与采纳"]
    BlueprintDecision --> StoryMap["Novel 章节 StoryMap<br/>或 Script 集场 StoryMap"]
    StoryMap --> UnitLoop["逐章 / 逐场生产循环"]
    UnitLoop --> Candidate["流式只读候选"]
    Candidate --> Validate["结构与质量校验"]
    Validate --> Edit["解锁人工编辑并另存修订"]
    Edit --> Adopt["明确采纳为正文"]
    Adopt --> More{"还有生产单元？"}
    More -->|是| UnitLoop
    More -->|否| Quality["整书 / 整剧质量审读"]
    Quality --> Package["领域独立包装"]
    Package --> Export["章节选择、格式选择与导出"]
    Export --> History["版本、血缘、回滚与审计"]

    TPipe --> TermContext["术语候选与已确认术语上下文"]
    TermContext --> TranslateUnit["逐章翻译候选"]
    TranslateUnit --> Compare["原文 / 译文对照、人工修订与确认"]
    Compare --> TermContext
    Compare --> Export

    RPipe --> SourceModel["读懂原作：故事功能与不可变项"]
    SourceModel --> Strategy["三套归化策略候选"]
    Strategy --> Trial["代表性试写与人工决定"]
    Trial --> ReBlueprint["归化整书蓝图"]
    ReBlueprint --> ReUnit["逐包 / 逐章生产、审读、修订与采纳"]
    ReUnit --> Package
```

## 4. 一次生成操作的状态机

```mermaid
stateDiagram-v2
    [*] --> Accepted
    Accepted --> Queued
    Queued --> Running
    Running --> Validating
    Validating --> Repairing: 可局部修复且未达策略上限
    Repairing --> Validating
    Validating --> Ready: 领域校验通过且产物已落盘
    Ready --> WaitingDecision: 需要用户决定
    WaitingDecision --> Revised: 人工修订
    Revised --> WaitingDecision
    WaitingDecision --> Adopted: 明确采纳
    WaitingDecision --> Rejected: 拒绝或重新生成
    Running --> Cancelled: 用户取消
    Running --> Failed: Provider / contract / timeout
    Validating --> Failed: 不可修复
    Running --> Interrupted: 进程中断
    Interrupted --> Running: 从完整 Checkpoint 恢复（目标态）
    Adopted --> [*]
    Rejected --> [*]
    Cancelled --> [*]
    Failed --> [*]
```

业务成功必须同时满足：领域校验通过、可消费产物落盘、ArtifactRef 来源完整、完整 Checkpoint
落盘、用户投影已发布。模型返回文本或事件流结束不构成成功。

## 5. 产物、版本与决定血缘

```mermaid
flowchart LR
    Facts["已采纳项目事实"] --> Manifest["Context Manifest"]
    Source["素材 / RAG 引用 / 术语"] --> Manifest
    RuntimeConfig["模型 / Skill / Tool / 权限 / 价格快照"] --> Manifest
    Manifest --> Operation["Creative Operation"]
    Operation --> Stage["Stage Run"]
    Stage --> Candidate["领域候选 v1"]
    Candidate --> HumanEdit["人工修订 v2"]
    HumanEdit --> Decision{"DecisionRequest"}
    Decision -->|采纳| Adopted["正式事实 v2"]
    Decision -->|拒绝| Expired["候选过期但保留历史"]
    Adopted --> Downstream["后续章节 / 场次 / 翻译 / 包装"]
    Adopted --> History["版本历史与影响分析"]
    Downstream --> Manifest
```

后续创作只能读取最新已采纳版本以及获准进入上下文的人工修订，不得回退到旧候选。

## 6. AgentScope 与 ScriptNow 的责任边界

```mermaid
flowchart TB
    subgraph AS["AgentScope 原生职责"]
        Factory["AgentFactory"]
        Model["Model + fallback"]
        Toolkit["Toolkit / Skill / MCP"]
        Reply["reply_stream()"]
        Blocks["Thinking / Text / Data / Tool Blocks"]
        State["AgentState / framework confirmation"]
        Factory --> Model
        Factory --> Toolkit
        Model --> Reply
        Toolkit --> Reply
        Reply --> Blocks
        Reply --> State
    end

    subgraph SN["ScriptNow 产品职责"]
        Session["Creative Session / Turn"]
        Operation["Operation / Stage"]
        Artifact["ArtifactRef / domain version"]
        Checkpoint["Checkpoint / resume policy"]
        Decision["DecisionRequest / idempotency"]
        Budget["quota / metering / config snapshot"]
        Projection["SSE / Dock / page projection"]
        Session --> Operation --> Artifact --> Checkpoint
        Operation --> Decision
        Operation --> Budget
        Artifact --> Projection
        Decision --> Projection
    end

    Blocks --> Projection
    State -.-> Checkpoint
    Decision -.-> State
```

当前已接入公开 `reply_stream()`、Block 投影、最小耐久运行内核及四领域主要生成入口。
Context Manifest、恢复判定矩阵、parked AgentState checkpoint 与 resumption claim 已落地。
真实 MCP 的 `RequireUserConfirmEvent → 进程重启 → UserConfirmResultEvent` 端到端续跑仍需
通过退出门。

## 7. 管理与治理闭环

```mermaid
flowchart LR
    Providers["Provider 与凭据"] --> Routing["模型目录与角色路由"]
    Models["模型能力、上下文与价格"] --> Routing
    Agents["Agent 模板与角色"] --> RuntimeSnapshot["运行配置快照"]
    Skills["Skill 版本、题材与质量基准"] --> RuntimeSnapshot
    MCP["Tool / MCP 白名单与确认策略"] --> RuntimeSnapshot
    Routing --> RuntimeSnapshot
    Tenant["租户 / Tier / 额度 / 点数"] --> Budget["预留 → 消耗/结算 → 释放"]
    RuntimeSnapshot --> Runs["四领域运行"]
    Budget --> Runs
    Runs --> Usage["token / cost / latency / success / repair"]
    Runs --> Quality["采纳率 / 修订率 / 一致性 / 质量锚点"]
    Usage --> Admin["管理端观测与策略调整"]
    Quality --> Admin
    Admin --> Routing
    Admin --> Skills
    Runs -.-> Dream["受控经验候选与离线 Dream（未完成退出门）"]
    Dream -.-> Skills
```

## 8. 当前能力边界

| 状态 | 能力 |
|---|---|
| 已接入 | Creative Session/Operation 最小持久化谱系；四领域主要生成入口；ArtifactRef 与 Checkpoint 成功边界；真实 Block 事件投影；候选、人工修订、采纳与版本原则 |
| 已接入 | Context Manifest；跨进程恢复判定矩阵；parked AgentState checkpoint 与单次 resumption claim；Skill 基准准入闭环；四领域真实 Provider 证据审计工具 |
| 部分完成 | 全阶段状态统一；真实 MCP parked confirmation 续跑；四领域外部 Provider 实跑证据包 |
| 目标态 | 创作搭档完全驱动所有流程；受控 Dreaming；经重新评审后可能启动的 CLI / 外部 Agent |

成本路由已从当前目标态移除。既有模型绑定和用量记账继续有效，但系统不得因价格自动替换
用户或租户已选择的模型。

## 9. 验收使用方式

1. 每个新增功能必须能定位到图中的领域、Operation 阶段、产物和决定。
2. 任何跨领域复用必须证明只复用 platform 协议。
3. 任何“已完成”状态必须提供可读取产物及自动化证据。
4. 新状态、新事件或新产物类型必须先更新本文与对应领域契约。
