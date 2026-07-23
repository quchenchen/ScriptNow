# ScriptFlow V7 开发与完整测试计划

- Version: 1.0
- Date: 2026-07-18
- Status: Approved baseline extension
- Product baseline: `01-PRD-V7.md`

## 1. 终点定义

“可以完整测试”指一个 Release Candidate 能在隔离的测试环境中完成以下闭环，而不是仅能打开页面或调用单个 API：

1. Creator 与 Admin 两个 SPA 均由生产构建运行，不依赖原型 HTML 或硬编码演示数据。
2. Script 与 Novel 各自完成原创、改编、候选、采纳、写作、修订、版本、导出闭环。
3. AgentScope 真实运行与确定性 MockRuntime 使用同一产品事件契约；CI 默认用 Mock，真实模型作为受控 smoke suite。
4. 双租户无法越权；额度预留、消耗、释放、失败和冲正可重复验证。
5. Admin 对模型、等级、Agent 模板、工具、MCP、记忆和租户的变更能在下一次运行中生效并留下审计。
6. 关键失败场景可恢复：SSE 断线、模型失败、工具待确认、额度耗尽、Finding stale、导出重试和版本回滚。
7. 自动化测试、性能基线、安全测试、备份恢复和人工验收全部通过，QA 报告无 blocker/critical。

## 2. Definition of Done

每个 work package 只有同时满足以下条件才能完成：

- 公共接口和状态不变式有自动化测试。
- tenant scope、权限和审计适用于新增写路径。
- 没有从 V7 直接 import legacy 代码；复用代码已迁入 V7 命名空间。
- Creator/Admin 不显示假统计；未接入能力明确显示未接入。
- 错误、空态、加载、取消、重试和幂等行为已定义并测试。
- 后端 `pytest + ruff`、前端 typecheck/build/test 通过。
- API/schema/event 变更同步更新契约 fixture 和文档。
- 删除或迁移旧资产后通过全仓库引用扫描。

## 3. 交付策略与依赖主线

采用垂直切片，不以“先写完全部表，再写全部 API，再写全部页面”的方式推进。

```text
P0 基线与风险验证
  ↓
P1 平台可信内核（identity/run/event/ledger）
  ↓
P2 Creator 壳与项目入口
  ├── P3 Script 创作闭环
  └── P4 Novel 创作闭环
          ↓
P5 修订与版本一致性
  ↓
P6 Agent Dock、事件与恢复
  ↓
P7 导出、快照与回滚
  ↓
P8 商业化与 Admin 治理
  ↓
P9 全链路硬化
  ↓
RC 完整测试与发布判断
```

P3/P4 可以在 P2 后交替切片，但不得通过共享领域模型“提速”。P8 的治理表和服务接口在 P1 建立，完整 Admin UI 后置。

## 4. WBS

### P0 — 基线、契约与高风险 tracer bullet

目标：在规模开发前消除框架语义、领域边界和旧资产污染风险。

| WBS | 交付物 | 依赖 | 退出条件 |
|---|---|---|---|
| P0.1 | 模块化单体、双 SPA、依赖边界 | — | 已完成；后端 4 tests、双 build 通过 |
| P0.2 | AgentScope tracer bullet | P0.1 | 流式、工具、确认续跑、取消、fallback、状态恢复均有录制 fixture |
| P0.3 | SSE run protocol | P0.2 | run_id、cursor、heartbeat、断线恢复、去重、取消测试通过 |
| P0.4 | 安全与租户 threat model | P0.1 | tenant scope 规则、会话模型、凭据模型和负向测试模板冻结 |
| P0.5 | 额度账本状态机 | P0.1 | reserve/finalize/release/expire/reverse 并发模型与 schema 冻结 |
| P0.6 | Script/Novel 契约 | P0.1 | StoryMap、Block、Patch、Writer/Review/Export 契约分别冻结 |
| P0.7 | Legacy inventory | P0.2–P0.6 | 所有旧模块标记 reuse/migrate/isolate/archive/delete |

风险门：P0.2 若证明 AgentScope 2.0.4 无法可靠恢复待确认运行，必须在继续前写 ADR 选择自研 run coordinator 或调整交互，不得把风险推到 P6。

### P1 — 平台可信内核

目标：所有上层能力只能通过可信租户、运行、事件和计费边界工作。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P1.1 | Settings、DB session、迁移基线、测试数据库 fixture | migration up/down、配置缺失失败 |
| P1.2 | Tenant/User/Session、登录刷新注销、CSRF | 双租户矩阵、会话撤销、重放、限流 |
| P1.3 | Provider/Model/Tier 与带认证凭据加密 | 密钥轮换、不回显、可见性公式 |
| P1.4 | AgentFactory 与 runtime config snapshot | 每次 run 固定模板/模型/工具/策略版本 |
| P1.5 | ProjectRun 状态机与 run coordinator | queued/running/waiting/succeeded/failed/cancelled 恢复 |
| P1.6 | append-only project_events 与 SSE gateway | cursor、correlation、幂等、断线恢复 |
| P1.7 | Usage/Reservation/Credit ledger | 并发预留、fallback 计量、失败释放、冲正 |
| P1.8 | Workspace、上传隔离、审计日志 | 路径穿越、伪装类型、配额、审计不可变 |
| P1.9 | AgentState、Memory、RAG 基础服务 | tenant 隔离、索引恢复、删除/纠偏审计 |
| P1.10 | CreativeProfile、SkillResolver 与 SkillPlan 快照 | 角色/阶段/风格匹配、选择解释、digest 固化、冲突阻断 |

退出条件：无需 Creator UI，通过 API integration suite 可完成登录→建项目→启动 Mock run→接收 SSE→入账→查询审计；两租户数据完全隔离。

### P2 — Creator Shell 与项目入口

目标：真实 API 驱动的创作端骨架，原创/改编入口均可进入所属领域。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P2.1 | Router、Pinia、API client、错误规范 | 未认证跳转、401 刷新、全局错误 |
| P2.2 | Login、Welcome、Dashboard、项目切换 | 空态、多项目、租户切换禁止 |
| P2.3 | 四步向导与 direction 配置 | Script/Novel/source 组合、字段校验 |
| P2.4 | 改编上传与索引进度 | txt/docx/pdf、失败重试、删除、引用定位 |
| P2.5 | App Shell、Agent Bar、Dock placeholder | 响应式、键盘、状态来自真实 API |
| P2.6 | 原创/改编创建 vertical slice | Project、Plan、StoryMap 骨架、首个 Run 全部真实持久化 |

退出条件：Playwright 可分别创建 Script/Novel 的原创和改编项目；刷新后状态保持，无演示数据。

### P3 — Script 创作闭环

目标：从 StoryCore 到可采纳剧本场景的完整领域切片。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P3.1 | Script StoryCore 候选与采纳 | 三候选、修订、过期、唯一 adopted |
| P3.2 | Script Blueprint 与锚点实体 | 世界观/人物/弧线/事件/伏笔引用完整 |
| P3.3 | Episode→Scene→StoryBeat StoryMap | 增删重排、影响预览、并发版本检查 |
| P3.4 | Script Writer 与段落数组 | 五类 block schema、格式校验、流式候选 |
| P3.5 | 中国/好莱坞编辑器渲染 | 结构化编辑、稳定 para_id、候选采纳 |
| P3.6 | Script 连续性 context pack | 角色/伏笔/场景上下文引用真实实体 |

退出条件：原创与改编 Script 各完成 StoryCore→蓝图→一集多场写作→采纳；刷新、重试和版本冲突测试通过。

### P4 — Novel 创作闭环

目标：使用独立模型完成小说创作，不借用 Script 的 Episode/Scene/时长/格式逻辑。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P4.1 | Novel StoryCore 与小说蓝图 | POV、章节目标和小说叙事约束 |
| P4.2 | Volume→Chapter→StoryBeat StoryMap | 卷章增删重排、目标字数 |
| P4.3 | Novel Writer 与 block 数组 | heading/prose/dialogue/quote/divider |
| P4.4 | Novel 编辑器与 context pack | 稳定 block_id、章节导航、字数统计 |
| P4.5 | Script/Novel 隔离审计 | AST、前端依赖图和 API schema 无跨域引用 |

退出条件：原创与改编 Novel 各完成 StoryCore→蓝图→多章节写作→采纳；领域隔离测试持续通过。

### P5 — 修订、Finding 与版本一致性

目标：五维修订成为可定位、可冲突检测、可回溯的正式闭环。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P5.1 | Finding schema/scan pipeline | 真实实体锚点、excerpt 定位、schema retry |
| P5.2 | base_revision + structured patch | 原子采纳、幂等、冲突、stale reason |
| P5.3 | 人工意见 | 选区定位、作者、权限、dismiss/accepted |
| P5.4 | 三层修订面板 | severity/domain/unit、来源过滤、虚拟滚动 |
| P5.5 | 定位与反向标记 | 段落/块定位、呼吸高亮、最高严重度标记 |
| P5.6 | Script/Novel 独立审读技能 | 同一 Finding 外壳，不同领域规则和 patch |

退出条件：两个领域均通过 scan→定位→采纳→新版本→事件→回滚；过期 Finding 不得修改新正文。

### P6 — Agent Dock、事件投影与运行恢复

目标：用户能看见、控制并恢复 Agent 团队全过程。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P6.1 | Dock chat/node/decision/system 投影 | 增量加载、过滤、聚合不改历史事件 |
| P6.2 | Streaming UI | Text/Thinking/Tool/Data 事件顺序 fixture |
| P6.3 | 确认、取消、恢复卡 | waiting run 刷新恢复、重复确认幂等 |
| P6.4 | 选区引用与领域编辑技能 | quote、diff、采纳、继续反馈 |
| P6.5 | 上下文/记忆透明化 | 真占用、真条数、压缩事件与治理深链 |

退出条件：运行中刷新/断网/重连不丢最终结果；重复 SSE 与重复确认不产生重复候选或账单。

### P7 — 格式、导出、快照与回滚

目标：产物能够可靠交付，且所有回滚均可逆。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P7.1 | Script DOCX 中国/好莱坞格式 | Golden document + Word/Pages 人工检查 |
| P7.2 | Novel DOCX/约定导出格式 | 标题层级、正文、引文、分页测试 |
| P7.3 | 导出 manifest 与范围选择 | 半选、仅完稿、幂等、失败重试 |
| P7.4 | 手动 snapshot、diff、rollback | 回滚生成新版本、可再回滚、并发冲突 |
| P7.5 | 备份与恢复 | DB+workspace 打包、校验、恢复演练 |

退出条件：两个领域的 Golden Project 可导出、备份、恢复；恢复后版本 hash、事件和余额一致。

### P8 — 商业化与 Admin 治理

目标：平台运营配置可真实控制下一次创作运行。

| WBS | 交付物 | 核心测试 |
|---|---|---|
| P8.1 | User Center、额度、模型选择 | 可见性、锁定、耗尽拦截、赠点恢复 |
| P8.2 | Agent Team 租户覆盖 | 名称/Soul/model，恢复默认，配置快照 |
| P8.3 | 租户/订阅/订单 Admin | 搜索分页、停用、改级、赠点、审计 |
| P8.4 | 用量/成本 Admin | 真聚合、价格快照、trace 深链 |
| P8.5 | Provider/Model/Tier Admin | 连通性、密钥重置、可见性原因 |
| P8.6 | Agent Template/Tool Mount Admin | 草稿发布回滚、下次运行生效 |
| P8.7 | MCP/Sandbox Admin | 发现白名单、断连降级、确认策略 |
| P8.8 | Memory Governance Admin | 浏览、纠偏、删除、压缩审计同源 |
| P8.9 | SkillPlan 与能力进化 Admin | 装配解释、项目 Overlay、提案评估、版本晋升与回滚 |

退出条件：Admin 的每个写操作均有权限、验证、审计和 Creator 侧生效测试；mock 支付明确标识为测试流程。

### P9 — 全链路硬化

目标：把“功能可用”提升为“Release Candidate 可完整测试”。

| WBS | 交付物 | 退出门槛 |
|---|---|---|
| P9.1 | 空态、错误态、重试、取消、响应式、无障碍 | axe 无 serious/critical；键盘主流程可达 |
| P9.2 | 性能基线 | 200 Findings、目标项目规模、事件分页达到 NFR |
| P9.3 | 安全 suite | tenant/IDOR/CSRF/path traversal/secrets 全绿 |
| P9.4 | 故障注入 | 模型/MCP/DB/SSE/导出失败可解释且可恢复 |
| P9.5 | 数据完整性审计 | 无孤儿版本、重复账单、跨租户引用 |
| P9.6 | Legacy 最终清理 | V7 无 legacy import；归档/删除清单闭合 |

## 5. 测试体系

| 层级 | 工具 | 覆盖重点 | 每次 PR |
|---|---|---|---|
| Python unit/domain | pytest | 状态机、契约、不变式、patch | 是 |
| Import/architecture | AST/依赖图 | platform/script/novel 边界 | 是 |
| API integration | pytest + httpx | DB、tenant、事务、权限、幂等 | 是 |
| Agent contract | 录制事件 fixture + MockRuntime | 事件顺序、工具、确认、fallback | 是 |
| Vue unit/component | Vitest + Vue Test Utils | store、组件状态、交互 | 是 |
| Browser E2E | Playwright | Creator/Admin 关键旅程 | 是，核心子集 |
| Security | pytest/自定义攻击矩阵 | IDOR、CSRF、凭据、路径 | 是，核心子集 |
| Performance | k6/Locust + 浏览器指标 | API/SSE/列表/大项目 | 每阶段门与 RC |
| Visual | Playwright screenshots | 原型关键视图和格式 | RC，按需 PR |
| Real LLM smoke | 受控测试账号 | Provider/AgentScope/trace | 每日或 RC，不阻塞普通 PR |
| Document golden | DOCX 解析+人工 | Script/Novel 排版 | P7 后每次 PR |

测试数据分三层：小型 fixture 用于 PR；Golden Project 用于完整 E2E；大规模合成项目用于性能。禁止把原型演示内容作为生产 seed。

## 6. Release Candidate 验收矩阵

### Creator 主路径

| 领域 | 来源 | 必测结果 |
|---|---|---|
| Script 中国格式 | 原创 | 创建→候选→蓝图→多场写作→修订→导出→回滚 |
| Script 好莱坞格式 | 改编 | 上传/RAG→忠实度引用→写作→修订→导出 |
| Novel | 原创 | 创建→卷章目录→多章节→小说审读→导出→回滚 |
| Novel | 改编 | 多文件 RAG→章节写作→引用定位→导出 |

每条路径追加：刷新恢复、SSE 断线、模型失败一次、额度耗尽一次、Finding stale 一次、重复请求一次。

### Admin 主路径

1. 创建/停用租户、改级、赠点。
2. 配置 Provider/Model/Tier 并验证 Creator 可见性。
3. 发布/回滚 Agent 模板并验证运行配置快照。
4. 挂载/禁用 ToolGroup，注册 MCP、白名单、断连降级。
5. 修改记忆策略、纠偏/删除记忆并核对审计。
6. 从 usage run 深链 Studio trace。

### RC 硬门槛

- 所有必需自动化 suite 通过，flake 重跑率低于 1%。
- blocker/critical 缺陷为 0；high 必须有明确批准的延期记录。
- 双租户负向矩阵 100% 通过。
- 账本对账差异为 0，重复 run/call 不重复扣费。
- Golden Project 备份恢复后内容 hash、版本、事件和余额一致。
- 生产构建不包含演示数据、明文凭据、source map 泄密或 legacy import。
- QA 报告包含环境、版本、测试证据、已知限制和回滚方案。

## 7. CI 流水线

```text
format/lint
  → backend unit + architecture
  → backend integration + migration
  → frontend typecheck + unit
  → Creator/Admin production build
  → Playwright core journeys
  → security core matrix
  → artifact + SBOM
```

合并到主开发分支后运行完整 E2E；每日运行真实 LLM smoke 和依赖安全扫描；阶段出口运行性能、故障注入和备份恢复。

## 8. 风险登记

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| AgentScope 恢复/中间件语义不符 | 中 | 致命 | P0 tracer bullet；不通过即 ADR 改方案 |
| Script/Novel 再次错误复用 | 中 | 高 | 自动依赖边界 + 独立契约/测试/owner |
| SQLite 并发导致账本或事件争用 | 中 | 高 | 事务压力测试；P1 设迁 PG 触发阈值 |
| Finding 锚点幻觉或 patch 过期 | 高 | 高 | 实体校验、base revision、stale、Golden corpus |
| Admin 范围拖慢创作核心 | 高 | 中 | P1 先接口/seed，P8 再完整 UI；不阻塞 P3/P4 |
| 真实模型测试不稳定/昂贵 | 高 | 中 | Mock 契约测试为主，真实 smoke 小样本受控运行 |
| 旧资产误迁污染新模型 | 中 | 高 | P0.7 inventory、characterization、禁止 legacy import |
| 上传/MCP 扩大攻击面 | 中 | 致命 | P1 安全边界、默认拒绝、沙箱+确认、故障注入 |

## 9. 执行规则

1. 一次只打开一个主 issue；依赖阻塞时可处理同阶段独立测试/文档，不跨风险门偷跑。
2. 每个阶段先写失败测试或验收 fixture，再实现最小 vertical slice。
3. 每个阶段结束输出 checkpoint：完成项、测试证据、数据迁移、已知风险、下一阶段入口。
4. 任何新共享抽象必须证明至少两个消费者具有相同语义；Script/Novel “字段相似”不构成共享理由。
5. 任何 schema、事件、账务或权限不变式变化必须写 V7 ADR。
6. 完整计划不等于固定日期承诺；以阶段退出条件控制进度，避免用未验证功能换取表面排期。

## 10. PRD 追踪矩阵

| PRD 范围 | 主实施阶段 | 完整验证阶段 |
|---|---|---|
| §2.1–2.4 AgentFactory/Skill/Tool/MCP | P0.2、P1.3–P1.5、P8.5–P8.7 | P6、P9.3–P9.4 |
| §2.5 Events/SSE | P0.3、P1.5–P1.6 | P6、P9.2、P9.4 |
| §2.6 Memory | P1.9、P8.8 | P6.5、P9.3 |
| §2.7 Metering/Budget | P0.5、P1.7 | P8.1、P8.4、P9.5 |
| §2.8 Security/Sandbox | P0.4、P1.2、P1.8 | P8.7、P9.3–P9.4 |
| §2.9 Observability | P0.2、P1.4–P1.6 | P8.4、RC Admin 路径 |
| §2.10 RAG | P1.9、P2.4 | P3/P4 改编路径、P9.4 |
| §2.11 Model/Tier | P1.3–P1.4 | P8.1、P8.5 |
| §3.0–3.3 Creator shell/auth/project | P2 | P9.1、RC Creator 路径 |
| §3.4–3.7 创意/蓝图/目录/写作 | P3、P4 | RC Creator 四路径 |
| §3.8–3.9 修订/选区 | P5、P6.4 | P9.2、RC stale/重复请求 |
| §3.10 Dock | P6 | P9.2、P9.4 |
| §3.11 Agent Team | P8.2 | RC Admin 路径 |
| §3.12–3.13 Export/Version | P7 | RC Creator 路径、备份恢复 |
| §3.14 Account | P8.1 | RC 额度耗尽/赠点恢复 |
| §4.1–4.7 Admin 全部视图 | P8.3–P8.8 | RC Admin 六条路径 |
| §5 BR-1–14 | P0/P1 契约与各领域实现 | P9.3、P9.5、全部 E2E |
| §8 NFR | 全阶段逐步建立基线 | P9 与 RC 硬门槛 |
