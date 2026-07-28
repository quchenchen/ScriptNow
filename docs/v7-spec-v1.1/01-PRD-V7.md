# ScriptNow 产品需求规格说明书（PRD / SRS）

| | |
|---|---|
| 文档版本 | v1.1（初始批准 2026-07-18；修订至 2026-07-28） |
| 状态 | 已批准，持续修订 |
| 依据 | ① v1.1 规格与领域契约 ② 当前 `scriptnow/` 实现、Alembic 迁移及自动化测试 ③ AgentScope 2.0.4 本地 API 反射验证 ④ 冻结原型的交互研究结论；历史 V6 材料不构成现行需求 |
| 取代关系 | 本文档取代 `v7-spec-v1.0/01-PRD-V7.md`；V5/V6 文档仅作历史研究材料 |
| 读者 | 产品 / 前端 / 后端 / Agent 工程 / QA |

---

## 1. 产品概述

### 1.1 定位与主张

ScriptNow 是 **AI Agent 团队驱动的剧本/小说创作平台**。核心隐喻是 **Growing（生长）**：用户不是在"填表生成内容"，而是与一支人格化的 Agent 团队（创意导演、架构规划师、写作者、审读编辑）协作，让作品从创意种子逐步生长为可交付内容。

**V7 是全新产品基线。** 它可以复用 V6 的技术资产，但不继承 V5/V6 的领域模型约束。旧 `CONTEXT.md`、旧 PRD 与 ADR 仅作历史研究材料。复用以契约和测试为依据：匹配则复用，不匹配则迁移或重新实现，不为了复用保留长期兼容分支。

**Script 与 Novel 分域。** 二者只共享认证、租户、AgentScope 运行时、事件、模型供给、计量、权限、文件工作区和观测等平台能力；正文模型、StoryMap、Writer 技能、审读规则、格式渲染和导出分别实现，禁止跨域直接复用。

V6 已回答"作品如何长出来"（发散 → 采纳 → 蓝图 → 逐场写作）。**V7 回答两个新问题：**

1. **「写出来之后，怎么改好？」** —— 修订成为一等公民：审读编辑 Agent 对正文进行五维扫描，每条修订意见锚定到故事蓝图中的具体实体，用户在三层渐进聚焦的修订面板中处理。
2. **「平台如何运营？」** —— 补齐商业化与治理闭环：租户 / 等级 / 额度 / 点数、模型与等级池、Agent 模板、工具与 MCP 治理、记忆治理，构成管理后台。

**V7 的技术主张：深度落座 AgentScope 2.0 底座。** V6 只把 AgentScope 当"带重试的 LLM 调用器"（每次现场 new Agent、无工具、无记忆、正则抠 JSON）。V7 将 Agent 团队、技能、工具、MCP、事件流、记忆、预算计量、权限沙箱、可观测性全部落在 AgentScope 原生机制上，产品自建代码只做**领域逻辑与治理**，不重复造运行时。

### 1.2 系统组成（三端一底座）

```
┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐
│ 创作端 Creator SPA  │  │ 管理后台 Admin SPA  │  │ 观测面 AgentScope     │
│ (Vue3 · 6 视图     │  │ (Vue3 · 7 视图)    │  │ Studio (OTel 深链)   │
│  + Dock + 3 Modal) │  │                    │  │                      │
└─────────┬──────────┘  └─────────┬──────────┘  └──────────▲───────────┘
          │ REST + SSE            │ REST                    │ OTLP
┌─────────▼────────────────────────▼──────────────────────────────────┐
│                    FastAPI 应用层（scriptnow）                    │
│  领域 API（项目/蓝图/正文/修订/事件/导出/版本） · 治理 API（租户/等级/  │
│  模型池/工具挂载/MCP/记忆） · 认证与计量中间件                         │
├──────────────────────────────────────────────────────────────────────┤
│                 Agent 运行时层（AgentScope 2.0.4 原生）               │
│  AgentFactory 组装：Agent(model·toolkit·middlewares·state·context)   │
│  Skill(LocalSkillLoader) · Toolkit(ToolGroup/FunctionTool/MCPTool)   │
│  reply_stream 事件流 · AgenticMemory/RAG/Budget/Tracing 中间件        │
│  PermissionEngine + Workspace(Local→Docker) 沙箱                     │
├──────────────────────────────────────────────────────────────────────┤
│  SQLite + Alembic：平台事实 + 四领域独立事实  ·  项目工作区文件系统   │
│  （原著文档 / RAG 索引(MilvusLite) / Agent 记忆 markdown / 快照）      │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.3 术语表（新增/变更项）

| 术语 | 定义 |
|---|---|
| 租户 Tenant | 计费与治理主体。V7 阶段 1 租户 = 1 用户（个人工作室），表结构预留组织扩展 |
| 等级 Tier | Plus / Pro / Max 三档订阅等级，决定可用模型池、月度 token 额度、点数包规格 |
| 点数 Credits | 按等级区分的补充 token 余额，购买/赠送获得，不过期，月度额度耗尽后自动抵扣 |
| Agent 模板 | 系统级的角色定义（Soul、默认模型、能力挂载），管理员发布，全租户生效 |
| Soul | Agent 的人格化系统提示词片段，与只读的"职责/系统能力"拼接为 system_prompt |
| 工具组 ToolGroup | AgentScope Toolkit 中可整组激活的工具集合：内置组 / 领域组 / MCP 透传组 |
| MCP 透传组 | MCP Server 白名单工具打包成的工具组，可挂载到 Agent |
| Finding（修订条目） | 审读编辑扫描或人工标注产生的一条修订意见（五维 × 三级严重度 × 锚点） |
| 锚点 Anchor | Finding 与蓝图实体（角色/世界规则/弧线/事件/伏笔）的结构化关联 |
| 事件流 Project Events | 项目级 append-only 事件总线，四类事件；一切记录类视图是它的过滤投影 |
| 框架事件 | AgentScope `reply_stream` 产出的 30 种细粒度事件（delta 级），事件桥将其映射/聚合为产品事件 |
| 记忆治理 | 对 Agent 长期记忆（markdown 文件化）的浏览、纠偏、删除与压缩审计 |
| Trace | 一次 Agent 运行的 OTel 追踪单元，admin 可深链到 AgentScope Studio 查看明细 |
| Creative Session | 一次可持续的人机创作协作会话；承载 Turn，但不替代领域项目或作品版本 |
| Creative Operation | 一次有明确目标、状态、阶段、预算和幂等边界的创作操作 |
| Stage Run | Operation 内可单独超时、重试、观测和恢复的阶段执行 |
| ArtifactRef | 指向领域候选或正式产物的带版本、依赖摘要和来源信息的引用 |
| Checkpoint | 只在阶段产物完整且可读取后创建的恢复点 |
| DecisionRequest | 需要创作者确认、采纳、拒绝或修订的持久化决定请求 |
| Context Manifest | 一次运行实际使用的项目事实、已采纳版本、术语、Skill、工具和模型配置清单 |

### 1.4 角色与权限

| 角色 | 入口 | 权限边界 |
|---|---|---|
| 创作者（租户用户） | 创作端 | 自己租户内的项目全操作；Agent 仅可改名/微调 Soul/在等级池内选模型；不可见 Provider、API Key、路由细节 |
| 平台管理员 | 管理后台 | 租户/订单/赠点、Provider 与模型池、等级配置、Agent 模板发布、工具挂载矩阵、MCP 注册与白名单、记忆治理、沙箱策略 |
| Agent（系统） | 运行时 | 由 Toolkit 挂载决定工具面；写操作一律产出候选（Candidate），不可直写项目真理；受 PermissionEngine 与沙箱约束 |

---

## 2. 总体架构与 AgentScope 深度整合规格

> 本章为 V7 的技术宪法。所有 Agent 相关实现必须落在本章定义的机制上，禁止绕开框架另造平行系统。依据：AgentScope 2.0.4 已验证 API。

### 2.1 运行时组装（AgentFactory）

**TR-2.1.1** 系统提供唯一的 `AgentFactory.build(tenant, project, role) -> Agent`，按以下规则组装 AgentScope `Agent`：

| Agent 参数 | 来源 |
|---|---|
| `name` / `system_prompt` | Agent 模板（发布版）+ 租户覆盖（改名/Soul 微调）；system_prompt = 职责（只读）+ Soul + 项目上下文纲要 |
| `model` | 解析链：租户项目级选择 → 角色默认模型 → 等级内回退模型；实例化为对应 AgentScope 模型类（`DashScopeChatModel`/`DeepSeekChatModel`/`AnthropicChatModel`/`OpenAIChatModel`/`GeminiChatModel`/`MoonshotChatModel`/`XAIChatModel`/`OllamaChatModel`），凭据仅取自服务端 Provider 配置 |
| `model_config` | `ModelConfig(max_retries, fallback_model=等级池内回退模型实例)` |
| `toolkit` | 见 2.3：按挂载矩阵组装 ToolGroup + 领域 FunctionTool + MCP 透传 + Skill 加载器 |
| `middlewares` | 固定顺序：`TracingMiddleware` → `UsageMeteringMiddleware`(自研) → `TierBudgetMiddleware`(自研，含 `ReplyBudgetControlMiddleware` 语义) → `EventBridgeMiddleware`(自研) → `AgenticMemoryMiddleware` → `RAGMiddleware`(改编项目按需) |
| `state` | `AgentState` 从 `agent_states` 表反序列化（pydantic JSON），运行后回写 —— Agent 跨请求连续性 |
| `context_config` | `ContextConfig(trigger_ratio, reserve_ratio, compression_prompt, summary_schema, tool_result_limit)`，取值来自管理后台"记忆策略"，压缩提示词强制包含"创作决策必须保留"条款 |
| `react_config` | `ReActConfig(max_iters=角色配置, stop_on_reject=True)` |

**TR-2.1.2** 四角色的职责-视图-产物映射（与创作端 Agent Bar / 事件流一致）：

| 角色 | 挂载视图 | 核心产物 | 默认领域工具组 |
|---|---|---|---|
| 创意导演 Director | 向导 / 创意发散 | StoryCore 候选 ×3、方向修订 | `story-read`、`source-retrieval` |
| 架构规划师 Architect | 蓝图 / StoryMap | 世界观/人物/弧线/事件/伏笔候选、结构调整影响分析 | `story-read`、`blueprint-propose` |
| 写作者 Writer | 逐场写作 | 场景正文候选、选区改稿候选 | `story-read`、`manuscript-propose` |
| 审读编辑 Editor | 逐场写作（修订模式） | 五维 Finding、修订建议稿 | `story-read`、`review-propose` |

**TR-2.1.3 Mock 双轨保留**：无凭据环境回落 MockRuntime（确定性输出，UI 明确标注"未接入模型"，禁止伪装为真实运行）。

### 2.2 技能体系（agentscope.skill）

**TR-2.2.1** 现有 `skills/*/SKILL.md` 迁移到 AgentScope 约定：frontmatter 含 `name`/`description`，经 `LocalSkillLoader(directory, scan_subdir=True)` 装载，通过 `Toolkit(skills_or_loaders=[...])` 注入。

**TR-2.2.2 渐进披露**：采用框架内建机制——skill 索引进入 system prompt（`<agent-skills>` 模板），Agent 需要时经 `skill_viewer` 工具读取全文。**禁止 V6 的"SKILL.md 全文当 system_prompt"用法**（上下文浪费 + 无法多技能）。

**TR-2.2.3** V7 技能清单（按角色包组织）：

```
skills/
├─ director/   story-core-shaping · direction-revision
├─ architect/  story-architecture · blueprint-worldview · character-profiles
│              · key-events · foreshadow-network
├─ writer/     opening-draft · scene-draft · selection-edit(扩/缩/润/对白/节奏)
│              · script-format-chinese · script-format-hollywood
└─ editor/     editorial-review(五维总纲) · review-worldview · review-character
               · review-arc · review-event · review-foreshadow
```

每个 SKILL.md 必须包含：触发条件、输入契约（依赖的 context/工具）、输出 JSON Schema、质量红线（叙事结构术语铁律、黑名单词、锚点必须引用真实实体 ID）。

### 2.3 工具体系（agentscope.tool）

**TR-2.3.1 领域工具（FunctionTool）**——ScriptNow 的核心资产，让 Agent 可以**主动查询**项目真理而非被动接收 context dump：

| 工具组 | 函数（示例） | 读写性 |
|---|---|---|
| `story-read` | `read_project_brief` `read_blueprint(section)` `read_arc(ordinal)` `list_scenes(episode)` `read_manuscript(unit_id)` `query_continuity(entity)` `list_foreshadows(status)` `read_source_chunk(query)` | `is_read_only=True` |
| `blueprint-propose` | `propose_entity_change` `propose_arc_adjustment` `propose_foreshadow_plan` | 写=产出候选 |
| `manuscript-propose` | `propose_scene_draft` `propose_selection_edit` | 写=产出候选 |
| `review-propose` | `propose_finding(domain, severity, anchor, excerpt, diagnosis, suggestion, confidence)` | 写=产出候选 |
| `task-tracker` | 框架内置 `TaskCreate/TaskUpdate/TaskGet/TaskList`（Agent 自我规划多步任务，进度映射为 node 事件） | — |
| `source-workspace` | 框架内置 `Read/Grep/Glob`，限定于项目工作区（原著文档目录） | 只读挂载 |

**TR-2.3.2 候选不变式**：所有 `propose_*` 工具只能形成候选并返回候选 ID，**永不直写用户已采纳的创作事实**。诊断、运行状态、审计与派生索引走各自领域写入规则，不伪装成 Candidate。

**TR-2.3.3 工具组治理**：每个 ToolGroup 携带 `min_tier` 与 `enabled`；`Toolkit` 按管理后台**挂载矩阵**（Agent × 工具组）组装。Agent 模板页展示的能力清单是矩阵的只读投影。

**TR-2.3.4 工具确认**：破坏性/外呼工具可标记需确认——运行时发出 `RequireUserConfirmEvent`，创作端 Dock 渲染确认卡，用户决定后以 `UserConfirmResultEvent` 续跑（`Agent.reply(inputs=UserConfirmResultEvent)`）。V7 默认仅 MCP 透传工具与 Bash 类工具需确认。

### 2.4 MCP 集成（agentscope.mcp）

**TR-2.4.1** 管理后台维护 MCP Server 注册表：`StdioMCPConfig{command,args,env,cwd}` 或 `HttpMCPConfig{url,headers,timeout}`（对应原型"StdIO / Streamable HTTP 两种传输"）。

**TR-2.4.2** 注册后执行发现：`MCPClient.connect() → list_tools()`，工具逐个进入白名单审核；仅白名单工具打包为「MCP 透传工具组」（`MCPTool`）供挂载矩阵使用。Server 级 `min_tier` 控制租户可用性。

**TR-2.4.3** 健康监测：定期 `is_connected`/延迟采样，展示于注册表（状态点 + 延迟毫秒）；断连的 Server 其透传组自动降级为不可用并事件留痕。

**TR-2.4.4** MCP 调用默认走工具确认（TR-2.3.4），全部计入 Trace 与事件流。

### 2.5 事件体系（agentscope.event → 产品事件总线）

**TR-2.5.1 两层事件模型**：

- **框架层**：`Agent.reply_stream()` 产出 30 种事件（Reply/ModelCall/TextBlock·ThinkingBlock·DataBlock 的 Start/Delta/End、ToolCall*/ToolResult*、RequireUserConfirm、UserInterrupt、ExceedMaxIters、CustomEvent…）。
- **产品层**：`project_events` 表（append-only），四类：`chat`（对话）/`node`（节点产出）/`decision`（用户决策）/`system`（系统）。

**TR-2.5.2 事件桥（EventBridgeMiddleware + SSE 网关）映射规则**：

| 框架事件 | 产品处理 |
|---|---|
| TextBlockDelta / ThinkingBlockDelta | 仅 SSE 转发（打字机/思考指示），**不入库** |
| ToolCallStart/End、ToolResultEnd | 聚合为一条 `node` 事件（同 group 计数聚合，防噪与原型一致） |
| ModelCallEndEvent(usage) | 驱动计量（2.7），不单独入流 |
| ReplyStart/ReplyEnd | `chat` 事件（Agent 回复完整文本落库） |
| RequireUserConfirmEvent | SSE 推送确认卡；用户决定落 `decision` 事件 |
| ExceedMaxIters / 异常 | `system` 事件（含降级说明） |
| 压缩（on_compress_context 钩子） | `system` 事件 + `memory_audit` 双写（同源，admin 审计与创作端压缩卡一致） |
| CustomEvent | 领域自定义（如"伏笔回收提醒"）按 payload.type 归类 |

**TR-2.5.3 事实源边界**：正文版本、Finding、快照、订单、额度和记忆等领域表是各自业务事实源；`project_events` 是不可变活动日志，不代替领域表。修订时间线、导出活动和决策流默认由事件过滤投影；聚合仅在查询层完成，禁止更新历史事件。事件必须携带 `event_id/schema_version/actor/aggregate/causation_id/correlation_id/idempotency_key/occurred_at`。

**TR-2.5.4** 传输：创作端通过 `GET /projects/{id}/events?after_id=` 增量拉取 + 生成期 SSE（`/agents/{role}/stream`）双通道。刷新不丢流（DB 持久化，替代原型的 localStorage 模拟）。

### 2.6 记忆体系（middleware + 治理）

**TR-2.6.1** 每 (项目, 角色) 挂 `AgenticMemoryMiddleware(workdir=项目工作区, memory_dir=Memory/<role>)`：长期记忆以 markdown 文件为事实源；`Parameters(memory_max_tokens, memory_instructions, retrieval_*)` 取自管理后台记忆策略。

**TR-2.6.2** 短期上下文自管理：`ContextConfig.trigger_ratio` 触发 `compress_context()`；压缩摘要 schema 强制保留「创作决策、用户偏好、项目禁用词」三类（admin 端"创作决策强制保留，不可关闭"）。

**TR-2.6.3 透明化数据源**：创作端 Agent 状态条的「上下文 n% · 记忆 m 条」必须来自真实运行时（AgentState 上下文占用估算 + 记忆索引计数），**禁止假数字**；未接入时显示"未接入"态。

**TR-2.6.4 记忆治理闭环**：`memory_entries` 索引表镜像文件（浏览器展示）；纠偏 = 编辑文件内容；删除 = 移除文件。两者均写 `memory_audit` 并即时生效于后续注入。Mem0Middleware 作为可选增强（Phase 后期评估，默认不启用）。

### 2.7 计量、额度与预算

**TR-2.7.1 单点计量**：`UsageMeteringMiddleware.on_model_call` 后置捕获 `ChatUsage`，写 `token_usage(trace_id, tenant, project, agent_role, model_key, input_tokens, output_tokens, cost_est)`。成本按模型单价（¥/1M 进出）估算。**禁止调用方自报用量。**

**TR-2.7.2 额度拦截链**：发起生成类任务前校验 `月度剩余 + 等级内点数 > 0`；耗尽 → HTTP 402 语义错误，创作端引导充值，admin 可赠点恢复（原型"运行时拦截生成请求"）。运行中超限由 `ReplyBudgetControlMiddleware(token_budget=剩余额度)` 兜底收尾，防止单次运行击穿。

**TR-2.7.3 消耗顺序**：先月度额度，后点数（点数按等级作用域约束：Plus 点数仅驱动 Plus 池模型，依此类推）。所有变动入 `credit_ledger`。

**TR-2.7.4 事务化额度**：每次 Agent 运行以 `run_id + idempotency_key` 在同一事务内执行 `reserve → consume/finalize → release`。并发运行不得重复占用余额；失败、取消与超时必须释放或冲正预留。fallback/retry 的实际模型调用均计量，但同一调用事件只能入账一次。

**TR-2.7.5 账务审计**：账本记录周期、tier scope、币种、价格快照、变动前后余额、关联订单/运行和冲正关系。月度额度、永久点数、赠点、退款及等级变更分别定义状态转换，禁止直接覆盖余额。

### 2.8 权限与沙箱

**TR-2.8.1** 工具执行经 `PermissionEngine`（PermissionRule/Mode/Behavior）：领域只读工具直通；`propose_*` 直通（本身即候选）；文件类工具限定项目工作区路径（AdditionalWorkingDirectory）；Bash/MCP 默认需确认。

**TR-2.8.2** 工作区：开发期 `LocalWorkspace`；生产切 `DockerWorkspace`（admin"沙箱执行策略"面板的三档策略：直通 / 沙箱 / 沙箱+确认）。`agentscope-runtime` 作为部署期可选组件在 Phase 0 验证，不构成本版依赖。

**TR-2.8.3 租户与会话安全**：所有项目级表、查询、工作区、RAG 库、记忆和 AgentState 必须以服务端解析的 `tenant_id` 约束；禁止信任请求体中的租户标识。HttpOnly 会话同时定义 SameSite、CSRF、防重放、刷新、注销、撤销、密码哈希与登录限流策略，并以双租户负向测试验收。

**TR-2.8.4 凭据与文件安全**：Provider Key、MCP headers/env 等机密使用带认证加密并记录密钥版本，主密钥来自部署环境或密钥服务，任何 API 不回显明文。上传文件执行路径规范化、类型嗅探、大小/数量配额、恶意文档隔离；文件工具只能访问解析后的项目工作区。

### 2.9 可观测性

**TR-2.9.1** `TracingMiddleware` + OTLP exporter（环境已具备 opentelemetry-sdk 1.43）上报 AgentScope Studio；trace_id 贯穿 `token_usage` 与 `project_events`。

**TR-2.9.2** admin「最近运行」表提供每次运行的 Trace 行（租户/Agent/模型/tokens/状态）与 **Studio 深链**；平台侧不重建逐 span 明细视图（原型明示"观测明细不在此重建"）。

### 2.10 RAG（改编项目）

**TR-2.10.1** 改编向导上传原著（.txt/.docx/.pdf ≤50MB，多文件）→ 落项目工作区 → `TextParser/PDFParser` + `ApproxTokenChunker` → `MilvusLiteStore` 建 `KnowledgeBase`（每项目一库）→ 索引状态与分块数记录于 `knowledge_bases` 表并事件留痕。

**TR-2.10.2** 改编项目的 Director/Architect/Editor 挂 `RAGMiddleware(knowledge_bases=[项目库])`；写作者按需通过 `read_source_chunk` 工具主动检索。原著引用在产出中标注来源（chunk 定位），支撑"忠实度"审读。

### 2.11 模型路由与等级池（V7 新 ADR 待 P0 固化）

**TR-2.11.1** 修订原则：用户**可见并可选**等级池内的具体模型（V7 原型明示模型名）；**不可见**Provider 凭据、Base URL、降级/重试/供应商切换细节。ADR-0002 的"完全黑盒"条款废止，其余安全边界保留。

**TR-2.11.2 创作端可见性公式**（唯一来源，admin 原型原文）：

```
creator_visible(model, tenant) = model.enabled ∧ provider(model).connected ∧ tenant.tier ≥ model.min_tier
```

**TR-2.11.3** 等级配置（月度额度、点数包价格/规格、模型作用域）全部为 admin 可配数据，创作端账户面板即时同步。**任何等级/价格/模型清单禁止硬编码。**

### 2.12 全系统业务流程与运行真相边界

**TR-2.12.1 单一运行入口**：Creator SPA、创作搭档 Dock 与未来获批的协议适配器，都必须
建立或加入 `CreativeSession`，并通过 `CreativeOperation` 发起生成型任务。页面不得另建
一套不可恢复的业务编排。

**TR-2.12.2 责任边界**：

- AgentScope 负责 `reply_stream()`、Thinking/Text/Data/Tool Block、Toolkit/MCP、
  AgentState、模型调用和框架级确认事件；
- ScriptNow platform 负责 Operation/Stage 状态、ArtifactRef、Checkpoint、DecisionRequest、
  配置快照、幂等、预算、事件投影与恢复；
- Novel、Script、Translation、Recreation 各自负责领域校验、候选、人工修订、采纳、正式
  版本和导出，不得跨域复用正文 DTO、Writer、StoryMap 或审读规则。

**TR-2.12.3 真实成功边界**：

```text
operation succeeded
  ⇔ domain validation passed
  ∧ consumable artifact persisted
  ∧ artifact provenance and dependency versions persisted
  ∧ complete checkpoint persisted
  ∧ user projection published
```

模型结束、SSE 结束或出现文本均不等于业务成功。结构化输出失败不得用兜底文本伪装完成。

**TR-2.12.4 状态表达**：产品必须区分当前已实现、部分实现与目标态。跨进程 Checkpoint
恢复、parked confirmation 的 AgentState 恢复、完整 Context Manifest、四领域真实 Provider
黄金回放和受控 Dreaming，在通过对应退出门前不得标记为生产完成。

全系统流程、状态机、领域分支和治理闭环见 `19-SYSTEM-BUSINESS-FLOW-MAP.md`；实施顺序见
`14-AGENTSCOPE-ALIGNED-IMPLEMENTATION-PLAN.md` 与
`17-SYSTEM-UPGRADE-ITERATION-ROADMAP.md`。

---

## 3. 创作端功能规格（Creator SPA）

> 视觉与交互以 `scriptnow-revision-focus.html` 为验收基准：oklch 暖纸色系、衬线显示字体、`--sidebar-w:240px`、侧栏拖拽收起(⌘B)、移动端响应式。原型中的《长安十二时辰》内容全部为演示数据——**实现中一律由 Agent 生成或用户输入，禁止写入代码**。

### 3.0 全局框架

- **FR-3.0.1 App Shell**：侧栏（品牌 / 项目切换器 / 创作导航×4 / 项目导航×4 / 账户卡）+ topbar（视图标题 / 保存状态 / 用量徽章）+ Agent Bar + 视图容器 + Agent Dock。
- **FR-3.0.2 项目切换器**：select 直切多项目 + "新建项目"；切换即重载全部项目态并事件留痕（system）。
- **FR-3.0.3 Agent Bar**：显示当前视图对应 Agent（头像/角色名）、模式标签（总览/项目设置/发散/蓝图/目录/修订）、运行状态点、上下文 chips（项目/方向/阶段）、"⚙ 设置"入口。视图切换产生 `system` 事件（同 group 聚合）。
- **FR-3.0.4 线性门控**：阶段由 V7 项目状态推导（未采纳 StoryCore → 发散；未规划 → 蓝图；已规划 → 写作），未达阶段的导航项禁用并给出原因提示。
- **FR-3.0.5 保存状态**：topbar 显示 已自动保存/保存中/冲突；数据以服务端为准。

### 3.1 认证与欢迎

- **FR-3.1.1 登录页**：邮箱+密码，JWT 会话（HttpOnly）；失败态、Enter 提交。注册/找回在 V7 由管理员开通租户替代（后台创建）。
- **FR-3.1.2 Welcome 屏**：登录后无活跃项目时展示（品牌 + "让好故事长出来" + 创建新项目/进入控制台）；有活跃项目直入仪表盘。

### 3.2 项目仪表盘

- **FR-3.2.1** 项目卡：名称、方向标签、阶段进度（发散/蓝图/写作/修订四段）、最近事件摘要（事件流投影）、继续创作入口。
- **FR-3.2.2** 空态：引导创建第一个项目（插画 + CTA）。

### 3.3 创建向导（4 步）

- **FR-3.3.1 Step1 作品方向**：9 个方向卡（竖屏短剧/横屏网剧/电影/动画/长篇小说/中短篇小说/互动叙事/舞台剧/自定义），**类型×媒介互锁**；方向决定 Step4 的体量字段标签与提示文案（`direction_defs` 服务端配置下发）。
- **FR-3.3.2 Step2 创作来源**：原创（灵感/一句话梗概 textarea）｜改编（原著名称·作者 + 上传区：拖拽/点击、.txt/.docx/.pdf、≤50MB、多文件、列表可删）。改编上传即触发 RAG 入库（TR-2.10.1），向导展示索引进度。
- **FR-3.3.3 Step3 叙事结构 + 剧本格式**：8 结构卡（英雄之旅/三幕/五幕/救猫咪/八序列/哈蒙圆环/弗雷塔格金字塔/自定义——全部为公认方法论，禁止自创术语）；剧本类方向追加格式选择：**中国剧本格式 / 好莱坞标准格式，创建后锁定不可切换**（Writer 中仅展示锁定徽章）。
- **FR-3.3.4 Step4 故事体量**：3 个动态标签数值（如 竖屏短剧=篇章数量/每章场景/场景节奏分钟）+ 项目预览卡（方向/来源/结构/体量汇总）。
- **FR-3.3.5** 创建提交：生成 Project + ProjectPlan（含 `direction_key`/`script_format`/体量三元组）+ StoryMap 骨架 + 首个 AgentTask；事件留痕；跳转创意发散。

### 3.4 创意发散（StoryCore）

- **FR-3.4.1** 创意导演生成 3 个候选卡：序号/标题/概念段 + 5 角度标签；展开详情四块：叙事引擎/视角锚定/节奏配方/市场判断（pill 组）。生成过程流式（SSE 思考/文本 delta 反映在 Dock）。
- **FR-3.4.2** 卡片操作：**采用此方向**（写 `decision` 事件，门控放行蓝图）｜**请求修订**（输入意见 → Director 重发散，旧候选标记过期，全程对话入流）。

### 3.5 蓝图规划（6 Tab）

- **FR-3.5.1 世界观**：6 类设定卡（时代背景/地理范围/世界规则/社会结构/氛围基调/媒介参数），媒介参数卡由 ProjectPlan 推导（只读）。
- **FR-3.5.2 人物角色**：人物小传卡（头像字/姓名/身份链/叙事性小传/特质 chips）。
- **FR-3.5.3 叙事弧线**：结构曲线图（SVG，按所选叙事结构的阶段点）+ 阶段列表（名称/集数范围/描述/关键节点高亮）。阶段名称严格来自 `story_structures` 模板。
- **FR-3.5.4 人物弧线**：每角色 起点→中点→终点 弧线标签 + 完成度条（完成度=已采纳正文覆盖的弧线节拍占比，真实计算）。
- **FR-3.5.5 关键事件**：时间线卡（集数·时辰式标签/标题/描述）。
- **FR-3.5.6 伏笔网络**：埋设→回收卡（埋设集数/描述/回收集数与方式/状态色）。
- **FR-3.5.7** 所有蓝图内容由 Architect 生成为候选 → 用户采纳后写入 V7 领域表；蓝图实体是修订锚点的引用目标（FR-3.8）。改编项目生成时经 RAG 引用原著。
- **FR-3.5.8 动态蓝图**：蓝图是版本化创作计划，不是冻结清单。Writer/Reviewer 可在写作中提交新增、修改、合并、退场角色/场景/情节/世界规则的 `CreativeChangeProposal`；Architect 负责形成结构化候选与影响分析，用户采纳后才进入领域事实。禁止 Agent 静默新增全局事实。
- **FR-3.5.9 短篇覆盖检查**：进入 StoryMap 前执行角色、场景、关键道具、信息来源、伏笔回收和结构节拍覆盖检查。覆盖充分不等于锁定；临时群众角色和一次性地点可作为局部事实，跨场复用时必须升级为蓝图锚点。

### 3.6 StoryMap（分域目录）

- **FR-3.6.1 Script**：Episode → Scene → Story Beat；集头展示编号/标题/弧线/场数，场行展示场号/标题/时长目标。
- **FR-3.6.2 Novel**：Volume → Chapter → Story Beat；章节展示标题/目标字数/视角/状态。Novel 不复用 Script 的 Episode、Scene 或时长字段。
- **FR-3.6.3** 点击创作单元 → 跳转对应领域 Writer。结构调整走 V7 候选与影响确认流，不直接沿用未经契约验证的 V6 实现。
- **FR-3.6.4 结构可塑性**：所选叙事结构决定初始节拍约束和结构 Skill，但允许通过候选迁移到另一结构。迁移必须展示旧节拍→新节拍映射、未覆盖单元、受影响正文、伏笔与人物弧线，不覆盖已采纳版本。

### 3.7 创作单元编辑（领域独立 Writer）

- **FR-3.7.1 左栏领域目录**：Script 显示本集场次；Novel 显示卷/章节。两者共享状态视觉语言，但不共享领域组件和数据类型。
- **FR-3.7.2 Script 编辑器**：正文为 `{type: slugline|action|character|dialogue|transition, text, para_id}` 段落数组；中国/好莱坞格式分别渲染和导出。
- **FR-3.7.3 Novel 编辑器**：正文为独立契约 `{type: heading|prose|dialogue|quote|divider, text, block_id}`；使用 Novel Writer、章节导航、字数目标和小说审读规则。Novel 代码不得依赖 Script 段落类型。
- **FR-3.7.4 生成与采纳**：对应领域 Writer 按自己的 context pack 与技能产出候选；用户在 Dock 中采纳或反馈修订。只复用通过 V7 契约测试的 V6 实现。
- **FR-3.7.5 右栏双 Tab**：📋 上下文（由对应领域查询模型提供）｜📝 修订痕迹（badge=未处理 Finding 数）。

### 3.8 五维修订体系（本版核心）

**数据结构（`review_findings`）**：

```
id · project_id · unit_id · base_revision_id · para_id/block_id · domain(worldview|character|arc|event|foreshadow)
severity(blocker|major|minor) · source(ai|human) · author(编辑名/Agent) 
anchor_type + anchor_id(entity|arc|event|foreshadow|thread) · anchor_note(如"弧线节拍2·初次动摇")
original_excerpt + locator · diagnosis · suggestion · suggested_patch · confidence(high|mid|low)
status(open|accepted|dismissed|stale) · stale_reason · superseded_by · idempotency_key · created_at · decided_at · trace_id
```

- **FR-3.8.1 扫描触发**：①用户点击"审读本场"②场景采纳后自动预扫描（可配置）。审读编辑 Agent 经 `review-propose` 工具产出 Finding（DataBlock 结构化输出，服务端 Schema 校验：**锚点必须命中真实实体 ID、original_excerpt 必须能在正文中定位，否则丢弃该条并降级重试**）。扫描过程事件实时进 Dock。
- **FR-3.8.2 修订面板（三层渐进聚焦）**：
  - 聚焦模式：**按严重度**（blocker→major→minor 分组排序，组标签"● 阻断—必须立即处理/● 重要/○ 建议"）｜**按维度**（Layer1 五维汇总行：图标+徽章+计数+→，点击下钻该维度）｜**按场次**（当前场过滤）。
  - 来源过滤：全部 / 🙋人工 / 🤖AI（+维度下钻时出现临时"🎯维度"chip）。
  - 修订卡（收起态）：严重度点 + 维度徽章 + 来源徽章 + 时间 + 一句话摘要；展开态：锚点卡 → 原文块 → 诊断 → 建议稿 → 置信度/影响行 → 操作行（📍定位 / ✓采纳 / ✗忽略）。
- **FR-3.8.3 定位**：滚动至段落 + 呼吸高亮 1.8s（locator 精确到段内文本）；正文段落侧缘显示修订标记点（按最高严重度着色），点击反向聚焦面板对应条目。
- **FR-3.8.4 采纳语义**：采纳前比较当前 revision 与 `base_revision_id`。一致时原子应用结构化 patch、生成新版本、更新 Finding 并追加 decision 事件；不一致时重新定位或进入冲突处理，禁止静默套用旧 locator。忽略保留为 dismissed；正文或锚点变化导致前置条件失效时记录 stale 与原因。
- **FR-3.8.5 人工意见**：正文划选 →「添加修订意见」→ 表单（维度/严重度/诊断/建议稿可选）→ source=human 入同一列表（标注者=当前用户名）。
- **FR-3.8.6 修订时间线**：modal，`project_events` 中修订相关事件的时间倒序投影（扫描/新增/采纳/忽略/失效）。

### 3.9 选区 → Agent 引用（扩/缩/润/修订）

- **FR-3.9.1** 编辑器内划选 ≥2 字 → 浮出 popover（扩写/缩写/润色/修订 四操作）；点击 → Dock 展开、引用 chip（操作名 + 60 字截断摘录）停靠输入框上方、placeholder 变化、toast 确认。Esc/滚动/点击外部关闭 popover；chip 可清除。
- **FR-3.9.2** 发送（可附加指令）→ 用户消息连同 quote 入流 → 路由至所属领域的 selection-edit 技能；Script 与 Novel 使用不同编辑规则。流式返回替换候选（diff 视图）后在对话流内采纳或继续反馈。

### 3.10 Agent Dock 与事件流

- **FR-3.10.1 Dock**：底部悬浮（left=sidebar-w），收起态=标题条 + 状态摘要 + ticker（最新事件滚动）+ 未读徽标；展开态=事件流列表 + 过滤 chips（全部/对话/节点/决策/系统）+ 输入区（Enter 发送 / Shift+Enter 换行）。
- **FR-3.10.2 事件行**：类型色点 + 标签 + 时间 + 标题；聚合行显示 ×N 并可展开明细；含 quote 的对话行渲染引用块；`decision` 行可跳转对应对象（候选/Finding/版本）。
- **FR-3.10.3 对话路由**：消息按当前 phase 路由至对应 Agent（Dock 常驻跨视图）；Agent 流式回复（思考中指示 → 文本增量）。
- **FR-3.10.4 状态条**：模式 + 上下文 n% + 记忆 m 条（真实数据，TR-2.6.3）；压缩发生时插入 `system` 压缩卡（含保留策略说明，点击可进记忆查看）。

### 3.11 Agent 团队设置（modal）

- **FR-3.11.1** 4 角色卡：头像/角色名（只读）+ 挂载范围与产出 chips（只读，来自挂载矩阵投影）+ 系统能力行（只读）+ 名称输入（可改）+ Soul 文本域（微调，叠加于模板 Soul）+ 模型选择器（**仅列可见性公式通过的模型**，锁定项显示"🔒 升级解锁"）。
- **FR-3.11.2** 保存 → `tenant_agent_configs` 生效于下次运行；`system` 事件留痕。恢复默认=清除租户覆盖。

### 3.12 导出剧本（modal）

- **FR-3.12.1** 集×场勾选树：全选/集级半选(indeterminate)/场级复选；每场显示状态徽章与字数；「仅完稿可选」开关将非 done 场禁用；无稿件集份折叠为汇总行。
- **FR-3.12.2** 形态：纯净稿（交付格式）/ 工作稿（含场景元信息与修订摘要）；底部汇总（已选 n 场·约 x 字）+ 上次导出记录行。
- **FR-3.12.3** 生成 DOCX（python-docx，按 script_format 排版：中国式 vs 好莱坞式）→ 下载 + `node` 事件留痕（范围/形态）。

### 3.13 历史版本（modal）

- **FR-3.13.1** **仅手动保存**：命名 + 自动捕获范围/字数/较上版增减；列表行（v 号/名称/时间/触发/范围/字数/Δ）。
- **FR-3.13.2** 行内展开：预览（节选）/ 对比（相对当前稿的段落级 same/add/del diff）/ **回滚**（双击确认；回滚生成新版本而非覆盖，可再回滚；`decision` 事件留痕）。
- **FR-3.13.3** 数据：`project_snapshots` + 内容引用（复用文稿版本链），列表视图同时是事件流投影的特化。

### 3.14 用户中心（modal）

- **FR-3.14.1 会员与额度卡**：等级 pill + 价格 + 权益一句话；本月已用/总额度进度条；点数余额与消耗顺序说明；升级 CTA。
- **FR-3.14.2 当前项目 LLM 卡**：模型单选列表（名称+等级 tag+一句话定位+当前使用标记；锁定项置灰+解锁提示）；选择即设为**项目级默认模型**（Agent 未单独指定时继承）。
- **FR-3.14.3 点数充值卡**：三档点数包（等级/价格/tokens/作用域），当前等级高亮，越级包置灰；购买（V7 为 mock 支付、真实记账入 `orders`+`credit_ledger`）→ toast + `system` 事件。
- **FR-3.14.4** 侧栏账户卡与 topbar 徽章实时反映用量（来源 `token_usage` 聚合）。

---

## 4. 管理后台功能规格（Admin SPA）

> 依据 `scriptnow-admin.html`（初步原型：结构与语义完整，JS 占位）。设计系统：Arc 风格暖色 token 契约（原样绑定），Inter 字体，侧栏 232px 毛玻璃。为独立 SPA（/admin），管理员角色 JWT 保护。列表均需真实分页/搜索；KPI 为真实聚合。

### 4.1 租户与订阅（经营）

- **FR-4.1.1 KPI 区**：总租户/活跃租户/本月订阅收入/本月点数收入（真实聚合）。
- **FR-4.1.2 租户列表**：租户（名称+邮箱）/ 等级 chip（Plus/Pro/Max，行内可改，**即时生效**）/ 状态（正常/额度耗尽/停用）/ 本月用量条（用量/额度，>90% 警示色）/ 点数余额 / 加入时间 / 操作（赠点、停用/恢复）。搜索（名称/邮箱）。
- **FR-4.1.3 赠点弹窗**：等级作用域 + 数量 + 备注 → 入 `credit_ledger`（type=grant）与订单流水（运营赠送留痕）；额度耗尽租户获赠后自动解除拦截（TR-2.7.2）。
- **FR-4.1.4 充值订单流水**：订单号/租户/类型（订阅续费|点数包|运营赠送）/金额/tokens/状态/时间。

### 4.2 用量与计费（经营）

- **FR-4.2.1 KPI**：本月总调用/总 tokens（进/出）/估算总成本/毛利估算。
- **FR-4.2.2 按模型用量与成本**：模型/调用数/输入/输出/估算成本/占比条——`token_usage` × 模型单价聚合；标注"OpenTelemetry tracing"。
- **FR-4.2.3 按等级消耗** 与 **Top 消耗租户**（前 N，含用量条）。
- **FR-4.2.4 最近运行**：Trace ID/租户/Agent 角色/模型/tokens/状态（成功/失败/超限）+ **「在 Studio 打开」深链**（TR-2.9.2）。平台不重建 span 明细。

### 4.3 模型与等级池（供给）

- **FR-4.3.1 Provider 接入表**：Provider/Base URL/API Key（●●● 掩码，仅服务端存储，可重置不可回显）/模型数/状态（已接入/未配置/异常——启动时连通性探测）/操作（配置弹窗）。**未接入 Provider 的模型不会出现在创作端**。
- **FR-4.3.2 模型 → 等级映射表**：模型名/Provider/**AgentScope 模型类**（枚举：DashScope/DeepSeek/Anthropic/OpenAI/Gemini/Moonshot/XAI/Ollama ChatModel）/定价 ¥/1M（进/出，可编辑）/最低等级（Plus|Pro|Max）/启用开关/**创作端可见性**列（实时按 TR-2.11.2 公式计算并展示原因）。
- **FR-4.3.3 等级与额度配置**：三档卡片（月费/月度 token 额度/点数包价格与规格/模型作用域说明），保存后创作端账户面板即时同步（FR-3.14）。

### 4.4 Agent 模板（Agent 运行时）

- **FR-4.4.1** 说明条（原型原文语义）：Soul 与默认模型为**系统级模板**，发布后对全部租户生效；租户侧仅可改名与微调 Soul；能力挂载在挂载矩阵中调整；运行时模型按租户等级过滤。
- **FR-4.4.2** 4 角色卡：角色名+状态 chip / Soul 编辑域 / 默认模型选择 / 回退模型选择 / ReAct 参数（max_iters）/ 能力清单 chips（挂载矩阵只读投影）/ **版本 chips**（历史版本可查看回滚，live 版本高亮）/ 操作：保存草稿 · 发布新版本。
- **FR-4.4.3** 发布 = 快照 `agent_templates` 新版本（version+1, status=live），旧版本归档；运行时永远取 live 版 + 租户覆盖。

### 4.5 能力与工具（Agent 运行时）

- **FR-4.5.1 工具组注册表**：工具组名/类型（内置|领域|MCP 透传）/函数数/最低等级/启用开关/已挂载 Agent 数。标注"AgentScope Toolkit"。内置与领域组由代码注册（表内只读元数据+治理字段），透传组来自 MCP 白名单（4.6）。
- **FR-4.5.2 挂载矩阵**：行=工具组，列=4 Agent；勾选格 = 该组激活进该 Agent 的 Toolkit（TR-2.3.3）；禁用组置灰。变更即时生效于下次 Agent 组装并审计留痕。
- **FR-4.5.3 沙箱执行策略**：按工具类别配置 直通/沙箱/沙箱+确认 三档（TR-2.8.2）；标注"agentscope-runtime sandbox"；策略变更即时下发。

### 4.6 MCP 注册表（Agent 运行时）

- **FR-4.6.1 Server 表**：名称/传输（StdIO|Streamable HTTP）/端点（命令或 URL）/延迟（健康采样）/工具数（白名单数/发现数）/最低等级/操作（详情抽屉/重连/删除）。
- **FR-4.6.2 详情抽屉**：连接配置（Stdio: command+args+env+cwd；HTTP: url+headers+timeout）/连接测试/发现的工具列表（名称+描述+schema 摘要+白名单开关）/白名单保存 → 生成或更新对应 MCP 透传工具组（TR-2.4.2）。
- **FR-4.6.3** 断连降级与事件留痕（TR-2.4.3）。

### 4.7 记忆治理（Agent 运行时）

- **FR-4.7.1 记忆策略卡**：短期上下文压缩阈值（trigger_ratio）/保留比例（reserve_ratio）/长期记忆 token 上限/检索参数；「创作决策强制保留」显示为**不可关闭**的锁定项。标注"InMemory + Mem0"。保存即更新 AgentFactory 的 ContextConfig/Memory Parameters 来源。
- **FR-4.7.2 压缩事件审计**：每次压缩的时间/项目/Agent/压缩前后轮次/新增记忆数/策略说明——与创作端事件流压缩卡**同源**（`memory_audit`，TR-2.5.2）。
- **FR-4.7.3 记忆浏览器**：租户+项目选择器 × Agent 过滤 → 逐条记忆（文本/来源 Agent/时间/项目）；操作：**纠偏**（编辑内容）/ **删除**；均写审计并即时生效于后续注入（TR-2.6.4）。

---

## 5. 关键业务规则汇总（跨端不变式）

| # | 规则 |
|---|---|
| BR-1 | **候选不变式**：Agent 不得直接改写用户已采纳的创作事实；诊断、运行状态、审计和派生索引不属于 Candidate；采纳/拒绝/过期全程可追溯 |
| BR-2 | **事件边界**：领域表是业务事实源；`project_events` 是不可变活动日志，聚合只在查询投影层发生 |
| BR-3 | **可见性公式**：创作端模型可见 = enabled ∧ provider.connected ∧ tier ≥ min_tier（admin 为唯一配置源） |
| BR-4 | **额度拦截链**：额度+点数耗尽 → 拦截生成类请求（读操作不拦）→ 充值/赠点恢复；运行中由预算中间件兜底 |
| BR-5 | **点数作用域**：各档点数仅驱动对应等级池模型；消耗顺序=月度额度→点数 |
| BR-6 | **格式锁定**：script_format 创建时锁定；全链路（技能→校验→渲染→导出）一致 |
| BR-7 | **叙事结构术语**：仅用公认方法论模板（story_structures），禁止 LLM 自创段落名 |
| BR-8 | **锚点真实性**：Finding 锚点必须命中真实实体 ID 且原文可定位，否则服务端丢弃重试 |
| BR-9 | **决策记忆保留**：上下文压缩强制保留创作决策/用户偏好/禁用词，管理端不可关闭 |
| BR-10 | **假数据禁令**：一切统计（用量/上下文%/记忆数/完成度）来自真实数据，未接入显示"未接入"态 |
| BR-11 | **凭据边界**：Provider Key 仅存服务端（加密），任何 API 不回显明文 |
| BR-12 | **计量单点**：token 用量仅由 UsageMeteringMiddleware 记录，禁止调用方自报 |
| BR-13 | **产品分域**：Script 与 Novel 不共享正文、目录、Writer、审读、格式或导出领域模块，只共享平台基础设施 |
| BR-14 | **运行配置快照**：每次运行固定并记录模板、模型、工具、权限、记忆和价格配置版本；运行中配置变化只影响后续运行 |
| BR-15 | **真实完成边界**：只有领域校验、可消费产物、来源信息、完整检查点和用户投影全部成功后，Operation 才能成功 |
| BR-16 | **版本与采纳**：生成只产生候选；人工保存形成独立修订版本；明确采纳后才改变正式事实，历史版本不得覆盖 |
| BR-17 | **恢复恰好一次**：重试、刷新、确认和恢复共用 Operation 与幂等键；已成功阶段及已执行副作用不得重复 |
| BR-18 | **四领域独立管线**：Novel、Script、Translation、Recreation 共享运行协议，不共享领域产物、生成器、审读或导出契约 |

---

## 6. 数据模型（全新基线，Alembic 演进）

开发树只维护 ScriptNow 当前模型与 Alembic 迁移，不保留可执行 V6 数据模型。历史表述只用于
迁移研究，不构成现行 schema 约束。

**账务域**：`tenants` · `subscriptions` · `orders` · `credit_ledger`（append-only）· `usage_reservations`（run/idempotency/status/reserved/finalized/expires_at）· `token_usage`（call_id/run_id/价格与币种快照）

**事件域**：`project_events`（type/title/actor/detail/group_key/count/refs_json/quote_json/trace_id/created_at，(project_id,id) 索引）

**修订域**：`review_findings`（见 3.8）· `project_snapshots`（name/scope_label/words/delta/content_ref/created_at）

**Agent 治理域**：`agent_templates`（role/name/soul/default_model_key/fallback_model_key/react_params/version/status/published_at）· `tenant_agent_configs`（tenant/project?/role/custom_name/soul_override/model_key）· `agent_states`（project/role/state_json pydantic/updated_at）

**供给域**：`providers`（key/base_url/api_key_enc/status）· `models`（key/provider_key/agentscope_class/price_in/price_out/min_tier/enabled）· `tiers`（key/price/monthly_tokens/pack_price/pack_tokens/scope_desc）

**工具与 MCP 域**：`tool_groups`（key/name/kind/functions_count/min_tier/enabled）· `agent_tool_mounts`（agent_role/tool_group_key/enabled）· `mcp_servers`（name/transport/config_json/status/latency_ms/min_tier）· `mcp_tool_whitelist`（server_id/tool_name/enabled/schema_digest）· `sandbox_policies`（tool_category/mode）

**记忆与 RAG 域**：`memory_entries`（tenant/project/agent_role/file_path/excerpt/updated_at，文件为源）· `memory_audit`（project/agent_role/event=compress|correct|delete/detail/created_at）· `knowledge_bases`（project/source_file/status/chunks/created_at）

**安全与审计域**：`sessions`（refresh hash/revoked/expires）· `admin_audit_log`（actor/action/target/before/after/request_id/created_at）· `runtime_config_snapshots`（run_id + 各配置版本）。所有租户数据表必须具有显式 `tenant_id`、外键、唯一约束和租户复合索引。

**运行协议域**：Creative Session、Turn、Operation、Stage Run、ArtifactRef、Checkpoint 与
DecisionRequest 采用平台级持久化模型；领域正文与候选仍存放在各自领域表，仅通过
ArtifactRef 建立血缘。

迁移策略：所有 schema 变更必须新增 Alembic migration，并通过空库升级、现存开发库升级和
关键数据回读测试；禁止以删库重建代替迁移正确性。

---

## 7. API 增量概要

**认证**：`POST /auth/login` · `GET /auth/me` ｜ **事件**：`GET /projects/{id}/events?after_id=&types=` · `GET /projects/{id}/agents/{role}/stream`（SSE：框架事件桥接）· `POST /projects/{id}/agents/{role}/messages`（Dock 对话，支持 quote）· `POST /projects/{id}/agents/{role}/confirm`（工具确认回执）

**修订**：`POST /projects/{id}/units/{uid}/review/scan` · `GET /projects/{id}/findings?domain=&severity=&source=&status=` · `POST /findings/{fid}/accept|dismiss` · `POST /projects/{id}/findings`（人工意见）

**导出/版本**：`GET /projects/{id}/export/manifest`（集×场树+状态+字数）· `POST /projects/{id}/export/docx`（scope+form → 文件）· `GET|POST /projects/{id}/snapshots` · `POST /snapshots/{sid}/rollback`

**账户**：`GET /account/summary`（等级/额度/点数/用量）· `GET /projects/{id}/models`（可见模型池）· `PUT /projects/{id}/model` · `POST /account/packs/{tier}/purchase`（mock 支付真记账）· `GET|PUT /projects/{id}/agent-team`

**管理端（/admin/api，管理员鉴权）**：`tenants`（列表/改级/停用/赠点）· `orders` · `usage/summary|by-model|by-tier|top-tenants|recent-runs` · `providers`（CRUD/test）· `models`（CRUD/映射）· `tiers` · `agent-templates`（CRUD/publish/versions）· `tool-groups` · `mounts`（矩阵批量）· `mcp/servers`（CRUD/connect/discover）· `mcp/servers/{id}/whitelist` · `sandbox-policies` · `memory/policy|audit|entries`（浏览/纠偏/删除）

---

## 8. 非功能需求（NFR）

- **性能**：事件流增量拉取 P95 < 200ms；修订面板 200+ Finding 虚拟滚动不掉帧；SSE 首 token 延迟仅受模型限制；admin 列表分页（50/页）。
- **可靠性**：Agent 运行失败降级留痕（system 事件 + trace 状态）；SQLite WAL；快照/导出幂等。
- **安全**：租户强制隔离；HttpOnly+SameSite 会话、CSRF、防重放、刷新撤销、密码哈希与登录限流；Provider/MCP 凭据使用带认证加密和密钥版本；管理 API 全审计；上传隔离；MCP/Bash 默认沙箱+确认；CORS 白名单。
- **可观测**：全部 Agent 运行有 trace_id 贯穿（usage/events/findings）；Studio 深链可用性作为验收项。
- **国际化**：V7 中文单语；文案集中管理。
- **数据**：项目工作区目录结构规范（sources/ memory/ snapshots/ rag/）；备份=DB 文件+工作区打包。

---

## 9. 里程碑（修订版，取代 PLAN 文档 §3）

| Phase | 范围 | 关键验收 |
|---|---|---|
| **P0 定案与地基** | V7 新基线与 Legacy Decontamination；Script/Novel 契约；正文 block 与版本前置条件；新 ADR 编号空间；AgentScope 端到端 tracer bullet；双 SPA 骨架 | 关键运行语义实测；资产分类清单；双 build 绿 |
| **P1 平台底座** | 最小认证与 tenant scope；AgentFactory；事件桥+run_id/SSE 恢复；事务化额度；计量/记忆/权限；agent_states；供给域 seed | 双租户负向测试；reserve/finalize 并发测试；真实运行 usage/events 入库 |
| **P2 创作端骨架+主链路** | App Shell/6 视图/门控/新向导（含 RAG 入库）/Dock 基础渲染 | 新 UI 完成原创+改编各一次全流程 |
| **P3 修订后端** | review_findings/扫描/校验丢弃重试/采纳应用/人工意见/级联联动 | 扫描→采纳→版本演进→留痕 pytest 全绿 |
| **P4 修订前端** | 三层聚焦面板/定位呼吸高亮/标记点/时间线/人工意见入口 | Playwright 全交互回归 |
| **P5 Dock 完整体+选区引用** | 事件流投影视图/确认卡/quote popover→ai-edits/状态条真数据 | 跨视图留痕一致性验收 |
| **P6 格式+导出+版本** | 基于 P0 已冻结正文契约完成双格式渲染、领域独立导出、快照 diff 回滚 | Word/Pages 排版正确；回滚可逆；Script/Novel 无跨域依赖 |
| **P7 创作端商业化** | 登录/Welcome/User Center/额度拦截链/Agent 团队设置 | 双租户隔离+计量+拦截演练 |
| **P8 管理后台** | 7 视图全量（对接 P1 已建治理表）+ Studio 深链 | admin 全操作→创作端即时生效验证 |
| **P9 全链路 QA 与打磨** | QA 报告/空态错误态/响应式/动效/性能/文档与技能沉淀 | QA-REPORT-V7 零 blocker |

依赖说明：P1 是一切上层功能的地基（用户强调的"深度整合"落点）；P8 仅做 UI——治理数据结构在 P1 落库、seed 脚本先行，避免后台阻塞创作端。

---

## 10. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| 审读扫描质量（幻觉锚点/泛泛而谈） | Schema 严格校验+丢弃重试（BR-8）；技能按维度拆分小步扫描；置信度门槛可配 |
| 结构化正文契约返工 | P2 前定型段落数组契约并写 ADR；V6 存量纯文本正文提供一次性解析迁移 |
| reply_stream 事件语义与 UI 契合度 | P1 事件桥先以录制回放做联调（真实事件序列存 fixture） |
| SQLite 并发（多租户+SSE） | WAL+写队列；租户量超阈值时评估 PG（表结构已按可迁移设计） |
| AgentScope 版本演进 | 锁定 2.0.4；升级需过 P1 回归套件 |
| 双 SPA 维护成本 | 共享 tokens/组件包（pnpm workspace）；admin 复用创作端 API 客户端层 |

**开放问题**（P0 需批复）：①租户=个人的简化是否接受（组织版后置）②审读"采纳后自动预扫描"默认开关③Mem0 是否纳入 V7（建议：AgenticMemory 文件化先行，Mem0 观察）④admin 原型 JS 为占位，7 视图的次级交互（如订单筛选、KPI 时间范围）按本 PRD 语义补全，是否需要先出高保真。

---

## 附录 A · AgentScope 2.0.4 能力映射速查

| 产品需求 | 框架机制（已验证） |
|---|---|
| Agent 团队/Soul/模型绑定 | `Agent(name, system_prompt, model, ...)` + 9 种 ChatModel 类 + `ModelConfig.fallback_model` |
| 技能渐进披露 | `Skill`/`LocalSkillLoader` + `Toolkit(skills_or_loaders)` + skill_viewer 元工具 |
| 工具组/挂载矩阵 | `Toolkit(tool_groups)` + `ToolGroup` 激活机制 + `FunctionTool(is_read_only, middlewares)` |
| MCP 注册/白名单/透传 | `MCPClient` + `StdioMCPConfig/HttpMCPConfig` + `list_tools/get_tool` → `MCPTool` |
| 事件总线/流式 UI | `Agent.reply_stream() → AsyncGenerator[30 种事件]`（Text/Thinking/Data/Tool 的 Start/Delta/End 等） |
| 候选确认/打断 | `RequireUserConfirmEvent`/`UserConfirmResultEvent`/`UserInterruptEvent`/`ExternalExecutionResultEvent` 作为 `reply()` 输入 |
| 上下文自压缩透明化 | `ContextConfig(trigger_ratio, reserve_ratio, compression_prompt, summary_schema)` + `compress_context()` + `on_compress_context` 钩子 |
| 长期记忆/治理 | `AgenticMemoryMiddleware(workdir, memory_dir, Parameters)`（markdown 文件化）；可选 `Mem0Middleware` |
| 改编 RAG | `TextParser/PDFParser` + `ApproxTokenChunker` + `MilvusLiteStore` + `KnowledgeBase` + `RAGMiddleware` |
| 计量/预算 | `ModelCallEndEvent(ChatUsage)` + `ReplyBudgetControlMiddleware(token_budget)` + 自研 `on_model_call` 中间件 |
| 沙箱/权限 | `PermissionEngine/Rule/Mode` + `LocalWorkspace/DockerWorkspace/E2BWorkspace` |
| 可观测/Studio 深链 | `TracingMiddleware` + OTLP（opentelemetry-sdk 1.43 已具备） |
| Agent 跨请求状态 | `AgentState`（pydantic 可序列化）+ `state` 参数注入 |
| Agent 自我任务规划 | 内置 `TaskCreate/TaskUpdate/TaskGet/TaskList` 工具 |

*附录 B（术语表）见 §1.3；旧资产复用与清理规则见 `02-LEGACY-DECONTAMINATION.md`。*
