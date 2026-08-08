# ScriptNow 全系统业务流程逻辑图

| | |
|---|---|
| 版本 | v1.1 |
| 日期 | 2026-07-31 |
| 状态 | 与 0.2.0-rc.1 对齐 |
| 范围 | Creator、Dock、Admin、AgentScope、Novel、Script、Translation、Recreation、Review、Package |

## 1. 阅读约定

- 实线表示当前规范和已接入的主链路。
- 虚线表示已批准但尚未完成退出门的目标能力。
- **粗体** 表示自 v1.0 (2026-07-28) 以来新增或重大变更的子系统。
- 四个创作领域只共享 platform 运行协议，不共享正文、StoryMap、生成器、审读和导出契约。
- 本文是业务与系统边界图，不以图中出现节点作为"已经生产可用"的证据。

## 2. 全系统上下文

```mermaid
flowchart LR
    Creator["创作者"] --> CreatorSPA["Creator SPA"]
    Creator --> Dock["创作搭档 Dock<br/><b>滚动锚点 · 进度可见 · 对话记录</b>"]
    Admin["平台管理员"] --> AdminSPA["Admin SPA"]
    External["未来 CLI / 外部 Agent<br/>备选计划"] -.-> Adapter["Creative Session Adapter"]

    CreatorSPA --> API["FastAPI / Auth / Tenant Scope<br/><b>RunCoordinator 启动中断调解</b>"]
    Dock --> API
    AdminSPA --> AdminAPI["Admin API"]
    Adapter -.-> API

    API --> Kernel["Creative Session + Operation Kernel<br/><b>Context Manifest 持久化</b>"]
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

    Artifacts --> Review["<b>Review Workbench</b><br/>人工比较、修订与决定<br/><b>独立审读案例</b>"]
    Review --> Kernel

    Novel -.-> CreativeGraph["<b>创作图谱<br/>采纳后自动提取 + 惰性补全</b>"]
    CreativeGraph -.-> Novel

    AdminAPI --> Governance["Provider / Model / Agent / Skill / MCP<br/>权限 / 额度 / 价格 / 记忆策略<br/><b>Skill 基准准入</b>"]
    Governance --> Runtime
    Kernel --> PlatformFacts["运行事实<br/>Operation / Stage / ArtifactRef / Checkpoint / Decision"]
    Runtime --> Events["Thinking / Text / Data / Tool 事件桥"]
    Events --> CreatorSPA
    Events --> Dock
    PlatformFacts --> CreatorSPA
    PlatformFacts --> AdminSPA

    Kernel --> ActiveRuns["<b>Active Runs Registry<br/>SSE 进度 + phase 可见性</b>"]
    ActiveRuns --> CreatorSPA
    ActiveRuns --> Dock
```

## 3. 作品全生命周期

```mermaid
flowchart TD
    Login["登录与租户校验"] --> Create["四步项目向导<br/>形态选择: Novel / Script / Translation / Recreation"]
    Create --> Contract["项目契约<br/>领域 / 来源 / 语言 / 市场 / 读者 / 篇幅 / 结构"]
    Contract --> Source{"来源模式"}

    Source -->|原创| Ideation["创意发散候选<br/>Novel: StoryCore · Script: 方向提案"]
    Source -->|改编| Ingest["上传、解析、RAG 与素材图谱<br/><b>SourceDistillationPanel</b>"]
    Source -->|忠实翻译| TPipe["忠实翻译管线"]
    Source -->|故事归化| RPipe["故事归化管线"]
    Ingest --> Ideation

    Ideation --> DirectionDecision["比较 / 反馈 / 修订 / 采纳方向<br/>Dock 对话辅助"]
    DirectionDecision --> Blueprint["领域蓝图候选<br/>Novel: 角色+锚点 · Script: 幕/集规划"]
    Blueprint --> BlueprintDecision["人工修订与采纳<br/>plan.status → blueprint_adopted"]
    BlueprintDecision --> StoryMap["<b>Novel 章节 StoryMap</b><br/>或 Script 集场 StoryMap<br/><b>反馈触发生成 (不走 Dock 中转)</b>"]
    StoryMap --> UnitLoop["逐章 / 逐场生产循环<br/><b>?background=true 异步模式</b>"]

    UnitLoop --> Candidate["流式只读候选<br/><b>Active Runs 进度可见</b>"]
    Candidate --> Validate["<b>三柱质量系统</b><br/>continuity / pacing / emotional-depth"]
    Validate --> Edit["解锁人工编辑并另存修订"]
    Edit --> Adopt["明确采纳为正文"]

    Adopt --> CreativeExtract["<b>创作图谱自动提取<br/>单章后台串行队列</b>"]
    CreativeExtract --> More{"还有生产单元？"}
    More -->|是| UnitLoop
    More -->|否| Quality["整书 / 整剧质量审读<br/><b>Review Workbench</b>"]
    Quality --> Package["领域独立包装<br/><b>Cover 本地持久化 + 删除</b>"]
    Package --> Export["<b>打包导出 (含封面+简介)</b><br/>章节选择、格式选择与导出"]
    Export --> History["版本、血缘、回滚与审计"]

    TPipe --> TermContext["术语候选与已确认术语上下文<br/><b>Glossary 自动提取</b>"]
    TermContext --> TranslateUnit["<b>逐章翻译候选 · 文件上传 (TXT/PDF/DOCX)</b>"]
    TranslateUnit --> Compare["原文 / 译文对照、人工修订与确认<br/><b>批量 translate-all</b>"]
    Compare --> TermContext
    Compare --> Export

    RPipe --> SourceModel["读懂原作：故事功能与不可变项"]
    SourceModel --> Strategy["三套归化策略候选"]
    Strategy --> Trial["代表性试写与人工决定"]
    Trial --> ReBlueprint["归化整书蓝图"]
    ReBlueprint --> ReUnit["<b>逐包 / 逐章生产、审读、修订与采纳</b>"]
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
    Running --> Interrupted: <b>进程中断</b>
    Interrupted --> Running: <b>RunCoordinator 启动时从 Checkpoint 恢复</b>
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
    Facts["已采纳项目事实"] --> Manifest["Context Manifest<br/><b>持久化 + operation 绑定</b>"]
    Source["素材 / RAG 引用 / 术语"] --> Manifest
    RuntimeConfig["模型 / Skill / Tool / 权限 / 价格快照"] --> Manifest
    Manifest --> Operation["Creative Operation"]
    Operation --> Stage["Stage Run"]
    Stage --> Candidate["领域候选 v1"]
    Candidate --> HumanEdit["人工修订 v2"]
    HumanEdit --> Decision{"DecisionRequest"}
    Decision -->|采纳| Adopted["正式事实 v2"]
    Decision -->|拒绝| Expired["候选过期但保留历史"]
    Adopted --> CreativeGraph["<b>创作图谱节点/边 + Summary</b>"]
    CreativeGraph --> Downstream["<b>Writer 上下文注入<br/>Hot/Warm/Cold 三层</b>"]
    Adopted --> Downstream
    Adopted --> History["版本历史与影响分析"]
    Downstream --> Manifest

    Package["<b>Work Package 领域</b>"] --> Cover["<b>封面本地持久化<br/>/files/covers/{project_id}/</b>"]
    Package --> PackagedExport["<b>打包 DOCX<br/>封面 + 简介 + 标签 + 正文</b>"]
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
        Checkpoint["Checkpoint / resume policy<br/><b>RunCoordinator 中断调解</b>"]
        Decision["DecisionRequest / idempotency"]
        Budget["quota / metering / config snapshot"]
        Projection["SSE / Dock / page projection"]
        Manifest["<b>Context Manifest<br/>三层上下文: Hot/Warm/Cold</b>"]
        ActiveRuns["<b>Active Runs Registry<br/>进度 + phase 事件</b>"]
        Session --> Operation --> Artifact --> Checkpoint
        Operation --> Decision
        Operation --> Budget
        Artifact --> Projection
        Decision --> Projection
        Manifest --> Operation
        ActiveRuns --> Projection
    end

    Blocks --> Projection
    State -.-> Checkpoint
    Decision -.-> State
```

当前已接入公开 `reply_stream()`、Block 投影、最小耐久运行内核及四领域主要生成入口。
Context Manifest、恢复判定矩阵、parked AgentState checkpoint 与 resumption claim 已落地。
Active Runs Registry 实现 SSE 进度推送和 AgentDock pulse-animated 进度指示。

## 7. 审读与质量闭环 (新增)

```mermaid
flowchart TD
    ChapterAdopted["章节采纳"] --> AutoReview["<b>自动质量审读<br/>continuity / pacing / emotional-depth</b>"]
    AutoReview --> Findings["质量发现<br/>blocking / major / minor / suggestion"]
    Findings --> WriterInjection["<b>Review Highlights → Writer WARM 上下文<br/>下章生成前注入</b>"]
    WriterInjection --> NextChapterGenerate["下章生成"]
    NextChapterGenerate --> ChapterAdopted

    Findings --> ReviewWorkbench["<b>Review Workbench<br/>独立审读案例 · 项目上下文</b>"]
    ReviewWorkbench --> ManualReview["人工审读与标记"]
    ManualReview --> Findings

    WholeBook["全本完成"] --> FullReview["<b>整书质量报告</b>"]
    FullReview --> Package["进入包装/导出"]
```

## 8. 跨域上下文检索 (新增)

```mermaid
flowchart LR
    WriterContext["Writer 上下文装配"] --> RetrievalAPI["Context Retrieval Service"]
    RetrievalAPI --> Lexical["<b>词汇检索</b><br/>RAG 语义匹配"]
    RetrievalAPI --> Graph["<b>图谱检索</b><br/>创作图谱节点/边"]
    RetrievalAPI --> Manifest["<b>Manifest 检索</b><br/>已采纳事实快照"]
    RetrievalAPI --> Policy["<b>检索策略</b><br/>token 预算 · 超时 · 冲突处理"]
    Policy --> ContextAssembly["<b>三层上下文装配</b><br/>HOT (~1K) · WARM (6K cap) · COLD (1K cap)"]
    ContextAssembly --> WriterContext
```

## 9. 管理与治理闭环

```mermaid
flowchart LR
    Providers["Provider 与凭据"] --> Routing["模型目录与角色路由"]
    Models["模型能力、上下文与价格"] --> Routing
    Agents["Agent 模板与角色"] --> RuntimeSnapshot["运行配置快照"]
    Skills["<b>Skill 版本、题材与质量基准<br/>基准报告驱动准入</b>"] --> RuntimeSnapshot
    MCP["<b>Tool / MCP 白名单与确认策略<br/>沙盒治理</b>"] --> RuntimeSnapshot
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

## 10. 当前能力边界

| 状态 | 能力 |
|---|---|
| 已接入 | Creative Session/Operation 最小持久化谱系；四领域主要生成入口；ArtifactRef 与 Checkpoint 成功边界；真实 Block 事件投影；候选、人工修订、采纳与版本原则 |
| 已接入 | Context Manifest 持久化 + operation 绑定；跨进程恢复判定矩阵；parked AgentState checkpoint 与单次 resumption claim；Skill 基准准入闭环；四领域真实 Provider 证据审计工具 |
| **已接入** | **RunCoordinator 启动时中断调解；Active Runs Registry + SSE 进度推送；AgentDock 滚动锚点 + 对话记录；创作图谱自动提取 + 惰性补全 + 后台串行队列** |
| **已接入** | **Writer 三柱质量系统 (continuity/pacing/emotional-depth)；Reviewer→Writer 反馈闭环；Review Workbench 独立审读案例；Context Retrieval 跨域服务 (lexical/graph/manifest)** |
| **已接入** | **Cover 本地持久化 + 打包导出 (含封面+简介)；翻译文件上传 (TXT/PDF/DOCX) + 批量翻译 + 术语表自动提取；故事归化全管线** |
| 部分完成 | 全阶段状态统一；真实 MCP parked confirmation 续跑；四领域外部 Provider 实跑证据包 |
| 目标态 | 创作搭档完全驱动所有流程；受控 Dreaming；经重新评审后可能启动的 CLI / 外部 Agent |

成本路由已从当前目标态移除。既有模型绑定和用量记账继续有效，但系统不得因价格自动替换
用户或租户已选择的模型。

## 11. 领域模块对照表 (新增)

| 模块 | 后端文件数 | 前端组件 | 核心能力 |
|------|-----------|----------|----------|
| **Novel** | 19 | NovelStudio · NovelDeliveryPanel · NovelQualityPanel · NovelStoryMapEditor | StoryCore → Blueprint → StoryMap → 逐章写作 + 图谱 |
| **Script** | 13 | ScriptStudio · ScriptDeliveryPanel · ScriptStoryMapEditor | 方向 → 蓝图 → StoryMap → 逐场写作 |
| **Translation** | 4 | TranslationStudio · TranslationOptions | 忠实翻译 + 文件上传 + 术语表 |
| **Recreation** | 5 | CrossCulturalRecreationStudio | 故事归化: 分析 → 策略 → 试写 → 生产 |
| **Review** | 6 | ReviewPanel · ReviewWorkbenchPage | 三柱质量 + 独立审读案例 |
| **Work Package** | 3 | PackagingPage | 封面生成/管理 + 打包导出 |
| **Dock** | 3 | AgentDock · AgentMessage | 创作搭档: 对话 + 进度 + 滚动锚点 |
| **Platform** | 61 | (N/A) | Auth · DB · Skills · Agent Runtime · Graph · Config |

## 12. 验收使用方式

1. 每个新增功能必须能定位到图中的领域、Operation 阶段、产物和决定。
2. 任何跨领域复用必须证明只复用 platform 协议。
3. 任何"已完成"状态必须提供可读取产物及自动化证据。
4. 新状态、新事件或新产物类型必须先更新本文与对应领域契约。

## 13. 版本变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-07-28 | 初始版本，四领域主链路 + 状态机 + AgentScope 边界 |
| **v1.1** | **2026-07-31** | **新增: 创作图谱 · 审读质量闭环 · Review Workbench · Context Retrieval · Active Runs · Cover 持久化 · 打包导出 · 翻译上传 · 故事归化全管线 · 领域模块对照表** |
